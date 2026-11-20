"""入库规则（方案 2.5「数据冲突」）：

- 唯一键：平台 + 平台原生 ID。无论从单条、关键词、博主哪条路进来，都只存一份。
- 不变的字段（标题、文案、发布时间、时长、作者……）：首次写入，之后只补空，不覆盖。
- 会变的数据（播放、点赞、评论、收藏、分享）：主表放最新值，同时追加一条快照。
- 来源：sources 表一对多，记下每次是从哪来的。
- 媒体直链会过期：每次用最新的。
"""
from __future__ import annotations

import json

from .. import db

METRICS = ("views", "likes", "comments", "saves", "shares")
STATIC = ("url", "title", "caption", "type", "published_at", "duration_s", "cover")
A_STATIC = ("sec_uid", "unique_id", "nickname", "avatar", "bio", "url", "verified")


def upsert_author(a: dict, source: str = "", full_profile: bool = False) -> int | None:
    if not a or not a.get("author_id"):
        return None
    platform, aid = a["platform"], str(a["author_id"])
    row = db.q1("SELECT * FROM authors WHERE platform=? AND author_id=?", (platform, aid))
    # 抖音：同一个人可能先以 unique_id 进来，后来才拿到 sec_uid，这里按 sec_uid 再找一次
    if not row and a.get("sec_uid"):
        row = db.q1("SELECT * FROM authors WHERE platform=? AND sec_uid=?", (platform, a["sec_uid"]))
    # 抖音指数等来源可能只给数字 ID、不给 sec_uid：同平台同昵称且有一方缺 sec_uid 时视为同一人
    if not row and a.get("nickname"):
        row = db.q1("""SELECT * FROM authors WHERE platform=? AND nickname=? AND (sec_uid IS NULL OR ? IS NULL)
                       ORDER BY sec_uid IS NULL LIMIT 1""", (platform, a["nickname"], a.get("sec_uid")))
    t = db.now()
    if row:
        sets, args = ["last_seen=?"], [t]
        # 占位 ID（nick:昵称）升级成真实 ID
        if str(row["author_id"]).startswith("nick:") and not aid.startswith("nick:") and \
                not db.q1("SELECT 1 FROM authors WHERE platform=? AND author_id=?", (platform, aid)):
            sets.append("author_id=?")
            args.append(aid)
        for k in A_STATIC:
            v = a.get(k)
            if v not in (None, "") and (row.get(k) in (None, "") or (full_profile and k in ("nickname", "avatar", "bio"))):
                sets.append(f"{k}=?")
                args.append(int(v) if k == "verified" else v)
        if a.get("extra"):
            ex = json.loads(row.get("extra") or "{}")
            ex.update(a["extra"])
            sets.append("extra=?")
            args.append(json.dumps(ex, ensure_ascii=False))
        if full_profile:
            sets.append("profile_fetched=?")
            args.append(t)
        db.x(f"UPDATE authors SET {', '.join(sets)} WHERE id=?", (*args, row["id"]))
        pk = row["id"]
    else:
        pk = db.x("""INSERT INTO authors(platform, author_id, sec_uid, unique_id, nickname, avatar, bio, url, verified,
                     extra, first_seen, last_seen, profile_fetched) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (platform, aid, a.get("sec_uid"), a.get("unique_id"), a.get("nickname"), a.get("avatar"),
                   a.get("bio"), a.get("url"), int(bool(a.get("verified"))) if a.get("verified") is not None else None,
                   json.dumps(a.get("extra") or {}, ensure_ascii=False), t, t, t if full_profile else None))
    if any(a.get(k) is not None for k in ("followers", "following", "likes", "posts")):
        db.x("INSERT INTO author_snapshots(author_pk, ts, followers, following, likes, posts, source) VALUES(?,?,?,?,?,?,?)",
             (pk, t, a.get("followers"), a.get("following"), a.get("likes"), a.get("posts"), source))
    return pk


def upsert_content(item: dict, provider: str, kind: str, ref: str = "", label: str = "", rank: int | None = None,
                   job_id: int | None = None, monitor_id: int | None = None) -> tuple[int, bool]:
    """返回 (内容 pk, 是否第一次见到)。"""
    platform, cid = item["platform"], str(item["content_id"])
    author_pk = upsert_author(item.get("author") or {}, source=kind)
    row = db.q1("SELECT * FROM contents WHERE platform=? AND content_id=?", (platform, cid))
    t = db.now()
    is_new = row is None
    if is_new:
        pk = db.x(f"""INSERT INTO contents(platform, content_id, {', '.join(STATIC)}, author_pk, media_url, tags, provider,
                     extra, first_seen, last_seen, {', '.join(METRICS)}, transcript_status)
                     VALUES({','.join('?' * (len(STATIC) + 10 + len(METRICS)))})""",
                  (platform, cid, *[item.get(k) for k in STATIC], author_pk, item.get("media_url"),
                   json.dumps(item.get("tags") or [], ensure_ascii=False), provider,
                   json.dumps(item.get("extra") or {}, ensure_ascii=False), t, t,
                   *[item.get(k) for k in METRICS],
                   "na" if item.get("type") == "image" else "none"))
    else:
        pk = row["id"]
        sets, args = ["last_seen=?"], [t]
        for k in STATIC:
            if item.get(k) not in (None, "") and row.get(k) in (None, ""):
                sets.append(f"{k}=?")
                args.append(item[k])
        if author_pk and not row.get("author_pk"):
            sets.append("author_pk=?")
            args.append(author_pk)
        if item.get("media_url"):
            sets.append("media_url=?")
            args.append(item["media_url"])
        for k in METRICS:
            if item.get(k) is not None:
                sets.append(f"{k}=?")
                args.append(item[k])
        if not json.loads(row.get("tags") or "[]") and item.get("tags"):
            sets.append("tags=?")
            args.append(json.dumps(item["tags"], ensure_ascii=False))
        if item.get("extra"):
            ex = json.loads(row.get("extra") or "{}")
            ex.update(item["extra"])
            sets.append("extra=?")
            args.append(json.dumps(ex, ensure_ascii=False))
        db.x(f"UPDATE contents SET {', '.join(sets)} WHERE id=?", (*args, pk))
    if any(item.get(k) is not None for k in METRICS):
        db.x(f"INSERT INTO metric_snapshots(content_pk, ts, {', '.join(METRICS)}, source) VALUES(?,?,?,?,?,?,?,?)",
             (pk, t, *[item.get(k) for k in METRICS], kind))
    db.x("""INSERT OR IGNORE INTO sources(content_pk, kind, ref, label, rank, job_id, monitor_id, ts)
            VALUES(?,?,?,?,?,?,?,?)""", (pk, kind, str(ref or ""), label, rank, job_id, monitor_id, t))
    return pk, is_new


def author_ref(author_pk: int) -> dict:
    a = db.q1("SELECT * FROM authors WHERE id=?", (author_pk,))
    if not a:
        return {}
    return {"author_id": a["author_id"], "sec_uid": a.get("sec_uid"),
            "username": a["author_id"], "platform": a["platform"]}


def content_ref(c: dict) -> dict:
    ex = json.loads(c.get("extra") or "{}")
    ref = {"content_id": c["content_id"], "url": c.get("url")}
    if c["platform"] == "sph":
        ref = {k: v for k, v in {"object_id": ex.get("object_id"), "export_id": ex.get("export_id"),
                                 "object_nonce_id": ex.get("object_nonce_id") or c["content_id"],
                                 "share_url": c.get("url") if "weixin.qq.com/sph" in (c.get("url") or "") else None}.items() if v}
        ref["content_id"] = c["content_id"]
    if c["platform"] == "xhs":
        ref["is_video"] = c.get("type") == "video"
        ref["xsec_token"] = ex.get("xsecToken")
    return ref
