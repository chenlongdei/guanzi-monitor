"""视频号（TikHub wechat_channels v2 / wechat_search v2，raw=false）→ 统一格式。2026-11-19 按真实返回校对。

- 搜索结果项：docID / exportId / jumpInfo.extInfo(JSON 字符串，含 feedNonceId) / source.title(昵称) / source.iconUrl /
  title(带 <em class=…> 高亮) / duration("02:35") / pubTime / image。**没有点赞等数据，也没有 username**。
- 详情 / 作品列表：id(objectId) / object_nonce_id / username(v2_…@finder) / nickname / title / description /
  create_time / like_count / fav_count / forward_count / comment_count / read_count(常为 0) / media(加密)。
- 唯一键：object_nonce_id —— 搜索、详情、作品列表三处一致（objectId 在搜索里拿不到）。
"""
from __future__ import annotations

import json
import re

from .base import first_str, num, ts


def _data(out):
    d = out.get("data", out) if isinstance(out, dict) else {}
    if isinstance(d, dict) and isinstance(d.get("data"), dict):
        d = d["data"]
    return d if isinstance(d, dict) else {}


def _clean(s):
    return re.sub(r"</?em[^>]*>", "", s or "").lstrip(".… ")


def _dur(v):
    if isinstance(v, str) and ":" in v:
        parts = [int(x) for x in v.split(":") if x.isdigit()]
        sec = 0
        for p in parts:
            sec = sec * 60 + p
        return sec or None
    return num(v)


def item(out_or_obj, from_search=False):
    v = out_or_obj if from_search else _data(out_or_obj)
    if not from_search and isinstance(v.get("videos"), list) and v["videos"]:
        v = v["videos"][0]
    media = v.get("media") if isinstance(v.get("media"), dict) else {}
    src = v.get("source") if isinstance(v.get("source"), dict) else {}
    ext = (v.get("jumpInfo") or {}).get("extInfo")
    if isinstance(ext, str):
        try:
            ext = json.loads(ext)
        except ValueError:
            ext = {}
    ext = ext or {}
    nonce = str(v.get("object_nonce_id") or v.get("objectNonceId") or ext.get("feedNonceId") or "")
    oid = str(v.get("id") or v.get("object_id") or "") if not from_search else ""
    export_id = v.get("exportId") or v.get("export_id") or ext.get("encryptedObjectId")
    full = _clean(v.get("description") or v.get("title") or "")
    username = v.get("username")
    nickname = v.get("nickname") or src.get("title")
    likes = num(v.get("like_count"))
    return {
        "platform": "sph", "content_id": nonce or oid or export_id or "",
        "url": v.get("share_url") or None,
        "title": _clean(v.get("title") or full).split("\n")[0][:120], "caption": full,
        "type": "video",
        "published_at": ts(v.get("create_time") or v.get("pubTime")),
        "duration_s": _dur(v.get("duration") or media.get("video_play_len") or media.get("duration")),
        "cover": first_str(v.get("cover_img_url"), v.get("image"), media.get("cover_url"), media.get("thumb_url")),
        "media_url": None,  # 视频号文件是加密的，不能直接转写
        "tags": re.findall(r"#([^#\s]+)", full)[:10],
        "views": num(v.get("read_count")) or None, "likes": likes,
        "comments": num(v.get("comment_count")), "saves": num(v.get("fav_count")),
        "shares": num(v.get("forward_count")),
        "author": {"platform": "sph", "author_id": username or (f"nick:{nickname}" if nickname else None),
                   "username": username, "nickname": nickname,
                   "avatar": first_str(v.get("head_url"), src.get("iconUrl"))},
        "extra": {k: val for k, val in {"object_id": oid or None, "export_id": export_id, "object_nonce_id": nonce or None,
                                        "needs_detail": from_search or None}.items() if val},
    }


def items(out):
    d = _data(out)
    rows = d.get("videos") if isinstance(d.get("videos"), list) else d.get("items") or []
    from_search = "videos" not in d
    res = [item(r, from_search=from_search) for r in rows if isinstance(r, dict)]
    res = [r for r in res if r["content_id"]]
    more = d.get("up_continue", d.get("continue_flag"))
    nxt = d.get("last_buffer") or d.get("cursor")
    return res, (nxt if more else None)


def author(out):
    d = _data(out)
    u = d.get("username")
    return {"platform": "sph", "author_id": u, "username": u, "nickname": d.get("nickname"),
            "avatar": d.get("head_url"), "bio": d.get("signature"), "verified": bool(d.get("verify_desc")),
            "url": None, "followers": num(d.get("fans_count")) or None, "following": None,
            "likes": num(d.get("like_count")) or None, "posts": num(d.get("feeds_count")),
            "extra": {k: d.get(k) for k in ("region", "verify_desc", "linked_accounts") if d.get(k)}}
