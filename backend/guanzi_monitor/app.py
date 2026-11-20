"""FastAPI：/api/* 是接口，其余路径返回打包好的前端页面。"""
from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import db, jobs, scheduler
from .providers import PLATFORMS, ProviderError, get_provider
from .services import images, insights, links

app = FastAPI(title="观自行深监控台")
WEB = Path(os.environ.get("DEI_WB_WEB") or Path(__file__).parent / "web")


def _mark_interrupted():
    db.init()
    # 运行中被中断的任务标成中断
    db.x("UPDATE jobs SET status='interrupted', finished=? WHERE status IN ('queued','running')", (db.now(),))
    db.x("UPDATE contents SET transcript_status='failed', transcript_error='工作台重启，转写中断' WHERE transcript_status='running'")


@app.on_event("startup")
def _startup():
    if db.SERVER:
        from . import auth, secretbox
        secretbox.check()
        for uid in [u["id"] for u in auth.list_users()]:   # 含停用账号：它们的 Key 也要加密
            with db.as_user(uid):
                _mark_interrupted()
                n = db.encrypt_existing_secrets()
                if n:
                    print(f"[secretbox] 用户 {uid}：{n} 个 Key 已改为加密存储")
    else:
        _mark_interrupted()
    scheduler.start()


# ---------------- 网页版：登录 ----------------
class AuthGate:
    """纯 ASGI 中间件：网页版下 /api 必须登录（Cookie 或 Bearer 令牌），并把当前用户放进上下文。"""
    OPEN = ("/api/auth/login", "/api/auth/register", "/api/auth/me", "/api/auth/logout")

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if not db.SERVER or scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.inner(scope, receive, send)
        from . import auth
        req = Request(scope)
        u = auth.user_from_session(req.cookies.get(auth.COOKIE))
        if not u:
            h = req.headers.get("authorization") or ""
            if h.lower().startswith("bearer "):
                u = auth.user_from_api_token(h[7:].strip())
        if not u and scope["path"] not in self.OPEN:
            return await JSONResponse({"detail": "请先登录"}, status_code=401)(scope, receive, send)
        scope.setdefault("state", {})["user"] = u
        tok = db.set_user(u["id"] if u else None)
        try:
            await self.inner(scope, receive, send)
        finally:
            db._uid.reset(tok)


app.add_middleware(AuthGate)


@app.exception_handler(jobs.LimitError)
def _limit_error(_req: Request, e: jobs.LimitError):
    return JSONResponse({"detail": str(e)}, status_code=429)


def _me(req: Request) -> dict:
    u = req.scope.get("state", {}).get("user")
    if not u:
        raise HTTPException(401, "请先登录")
    return u


def _ip(req: Request) -> str:
    """真实 IP：服务只监听 127.0.0.1，前面是 Caddy，取它加的 X-Forwarded-For 第一个。"""
    xf = req.headers.get("x-forwarded-for") or ""
    return xf.split(",")[0].strip() or (req.client.host if req.client else "")


def _set_cookie(resp, tok: str):
    from . import auth
    resp.set_cookie(auth.COOKIE, tok, max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                    secure=os.environ.get("GM_INSECURE_COOKIE") != "1", path="/")


@app.get("/api/auth/me")
def auth_me(req: Request):
    if not db.SERVER:
        return {"server": False, "user": None}
    return {"server": True, "user": req.scope.get("state", {}).get("user")}


@app.post("/api/auth/login")
def auth_login(req: Request, d: dict = Body(...)):
    from . import auth
    try:
        tok, u = auth.login(d.get("username", ""), d.get("password", ""), req.headers.get("user-agent", ""), _ip(req))
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    resp = JSONResponse({"user": u})
    _set_cookie(resp, tok)
    return resp


@app.post("/api/auth/register")
def auth_register(req: Request, d: dict = Body(...)):
    from . import auth
    try:
        auth.register(d.get("username", ""), d.get("password", ""), d.get("code", ""), _ip(req))
        tok, u = auth.login(d.get("username", ""), d.get("password", ""), req.headers.get("user-agent", ""), _ip(req))
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    resp = JSONResponse({"user": u})
    _set_cookie(resp, tok)
    return resp


@app.post("/api/auth/logout")
def auth_logout(req: Request):
    from . import auth
    t = req.cookies.get(auth.COOKIE)
    if t:
        auth.logout(t)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


@app.post("/api/auth/password")
def auth_password(req: Request, d: dict = Body(...)):
    from . import auth
    try:
        auth.change_password(_me(req)["id"], d.get("old", ""), d.get("new", ""))
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/auth/token")
def auth_token(req: Request):
    """生成给 Claude 等 Agent 用的访问令牌（只显示这一次）。"""
    from . import auth
    return {"token": auth.new_api_token(_me(req)["id"])}


@app.delete("/api/auth/token")
def auth_token_clear(req: Request):
    from . import auth
    auth.clear_api_token(_me(req)["id"])
    return {"ok": True}


def _admin(req: Request) -> dict:
    u = _me(req)
    if not u.get("is_admin"):
        raise HTTPException(403, "只有管理员能看")
    return u


@app.get("/api/admin/invites")
def admin_invites(req: Request):
    from . import auth
    _admin(req)
    return {"invites": auth.list_invites(), "users": auth.list_users()}


@app.post("/api/admin/invites")
def admin_new_invite(req: Request, d: dict = Body({})):
    from . import auth
    _admin(req)
    return {"code": auth.create_invite(d.get("note", ""), bool(d.get("is_admin")))}


def _j(v, default=None):
    try:
        return json.loads(v) if v else default
    except Exception:
        return default


def content_row(c: dict, full=False) -> dict:
    c = dict(c)
    c["tags"] = _j(c.get("tags"), [])
    c["extra"] = _j(c.get("extra"), {})
    if not full:
        c.pop("transcript_text", None)
    else:
        c["transcript"] = _j(c.pop("transcript_text", None), None)
    return c


# ---------------- 总览 ----------------
@app.get("/api/overview")
def overview():
    day0 = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
    month0 = time.mktime(time.localtime()[:2] + (1, 0, 0, 0, 0, 0, -1))
    s = db.get_settings()
    rate = float(s.get("usd_cny") or 7.2)
    spend = db.q1("SELECT COALESCE(SUM(cost_usd),0) usd, COALESCE(SUM(cost_cny),0) cny FROM jobs WHERE created>=?", (month0,))
    return {
        "today_new": db.q1("SELECT COUNT(*) n FROM contents WHERE first_seen>=?", (day0,))["n"],
        "total_contents": db.q1("SELECT COUNT(*) n FROM contents")["n"],
        "total_authors": db.q1("SELECT COUNT(*) n FROM authors")["n"],
        "transcripts": db.q1("SELECT COUNT(*) n FROM contents WHERE transcript_status='done'")["n"],
        "monitors": db.q1("SELECT COUNT(*) n FROM monitors WHERE enabled=1")["n"],
        "month_usd": round(spend["usd"], 4), "month_asr_cny": round(spend["cny"], 3),
        "month_cny": round(spend["usd"] * rate + spend["cny"], 2),
        "by_platform": db.q("SELECT platform, COUNT(*) n FROM contents GROUP BY platform"),
        "recent_jobs": [job_row(j) for j in db.q("SELECT * FROM jobs ORDER BY id DESC LIMIT 8")],
        "monitor_feed": db.q("""SELECT m.*, a.nickname, a.avatar FROM monitors m LEFT JOIN authors a
                                ON m.kind='blogger' AND a.id=CAST(m.target AS INTEGER)
                                WHERE m.last_run IS NOT NULL ORDER BY m.last_run DESC LIMIT 8"""),
        "daily": db.q("""SELECT date(first_seen,'unixepoch','localtime') d, COUNT(*) n FROM contents
                         WHERE first_seen>=? GROUP BY d ORDER BY d""", (db.now() - 14 * 86400,)),
        "provider": "demo" if os.environ.get("DEI_WB_DEMO") else s.get("provider"),
    }


# ---------------- 设置 / 个人信息 ----------------
@app.get("/api/settings")
def get_settings():
    return db.public_settings()


@app.put("/api/settings")
def put_settings(d: dict = Body(...)):
    # 密钥字段传空字符串表示不修改
    clean = {k: v for k, v in d.items() if not (k in db.SECRET_KEYS and (v is None or v == "" or isinstance(v, dict)))}
    if "data_root" in d and d["data_root"] and not db.SERVER:
        cfg = db.boot_config()
        cfg["data_root"] = d["data_root"]
        db.save_boot_config(cfg)
    db.set_settings(clean)
    return db.public_settings()


@app.post("/api/settings/clear")
def clear_secret(key: str = Body(..., embed=True)):
    if key in db.SECRET_KEYS:
        db.set_settings({key: ""})
    return db.public_settings()


@app.post("/api/settings/test")
def test_provider(name: str = Body("", embed=True)):
    s = db.get_settings()
    try:
        if name == "anthropic":
            return _test_anthropic(s)
        if name == "dashscope":
            from .services.transcribe import test_key
            return test_key(s)
        return get_provider(s, name=name or None).test()
    except ProviderError as e:
        return {"ok": False, "msg": str(e)}
    except Exception as e:  # noqa
        return {"ok": False, "msg": repr(e)}


def _test_anthropic(s: dict) -> dict:
    import anthropic
    if not ((s.get("anthropic_api_key") or "").strip() or os.environ.get("ANTHROPIC_API_KEY")):
        return {"ok": False, "msg": "还没填 Key"}
    try:
        c = anthropic.Anthropic(api_key=(s.get("anthropic_api_key") or "").strip() or None, timeout=30)
        m = c.models.retrieve(s.get("style_model") or "claude-opus-5-5")
        return {"ok": True, "msg": m.display_name}
    except anthropic.AuthenticationError:
        return {"ok": False, "msg": "Key 无效"}
    except anthropic.NotFoundError:
        return {"ok": False, "msg": "这个 Key 用不了所选模型"}
    except anthropic.APIConnectionError as e:
        return {"ok": False, "msg": f"连不上：{e}"}
    except anthropic.AnthropicError as e:
        return {"ok": False, "msg": str(e)[:120]}


@app.post("/api/settings/import-dei-capture")
def import_dei_capture():
    if db.SERVER:
        raise HTTPException(403, "网页版不支持从本机导入")
    p = db.dei_capture_config()
    if not p:
        raise HTTPException(404, "没找到 dei-capture 的 config.json（找过 ~/.claude、~/.workbuddy、~/.codex、~/.agents 下的 skills）")
    c = json.loads(p.read_text(encoding="utf-8"))
    dy = c.get("douyin") or {}
    m = {"monid_token": (dy.get("monid") or {}).get("token"), "tikhub_token": (c.get("tikhub") or {}).get("token"),
         "dashscope_api_key": (c.get("dashscope") or {}).get("api_key"),
         "dasheng_uid": (dy.get("dasheng") or {}).get("uid"), "dasheng_key": (dy.get("dasheng") or {}).get("key")}
    got = {k: v for k, v in m.items() if v}
    db.set_settings(got)
    return {"imported": sorted(got), "settings": db.public_settings()}


@app.get("/api/profile")
def profile():
    s = db.get_settings()
    bal = None
    try:
        bal = get_provider(s).test().get("balance_usd")
    except Exception:  # noqa
        pass
    rate = float(s.get("usd_cny") or 7.2)
    months = db.q("""SELECT strftime('%Y-%m', created, 'unixepoch', 'localtime') m, SUM(cost_usd) usd, SUM(cost_cny) cny,
                     COUNT(*) jobs FROM jobs GROUP BY m ORDER BY m DESC LIMIT 6""")
    for r in months:
        r["total_cny"] = round((r["usd"] or 0) * rate + (r["cny"] or 0), 2)
    return {"name": s.get("profile_name"), "avatar": s.get("profile_avatar"), "bio": s.get("profile_bio"),
            "provider": "demo" if os.environ.get("DEI_WB_DEMO") else s.get("provider"), "balance_usd": bal,
            "months": months, "contents": db.q1("SELECT COUNT(*) n FROM contents")["n"],
            "authors": db.q1("SELECT COUNT(*) n FROM authors")["n"]}


# ---------------- 任务 ----------------
def job_row(j: dict, with_log=False) -> dict:
    j = dict(j)
    j["params"] = _j(j.get("params"), {})
    j["kind_label"] = jobs.KIND_LABEL.get(j["kind"], j["kind"])
    lg = _j(j.pop("log", None), [])
    if with_log:
        j["log"] = lg
    else:
        j["last_log"] = lg[-1]["msg"] if lg else ""
    return j


@app.post("/api/estimate")
def estimate(d: dict = Body(...)):
    return jobs.estimate(d.pop("kind"), d)


@app.post("/api/jobs/single")
def job_single(d: dict = Body(...)):
    es = links.parse_video(d.get("text", ""))
    if not es:
        raise HTTPException(400, "没有识别到链接")
    plats = {e["platform"] for e in es if e.get("platform")}
    title = f"单条采集 {len(es)} 条"
    return {"job_id": jobs.create("single", d, title=title, platform=plats.pop() if len(plats) == 1 else None)}


@app.post("/api/jobs/keyword")
def job_keyword(d: dict = Body(...)):
    if not d.get("keyword", "").strip():
        raise HTTPException(400, "关键词不能为空")
    return {"job_id": jobs.create("keyword", d, title=f"关键词「{d['keyword'].strip()}」", platform=d["platform"])}


@app.post("/api/jobs/blogger")
def job_blogger(d: dict = Body(...)):
    if not d.get("ref"):
        parsed = links.parse_author(d.get("input", ""), d.get("platform"))
        if parsed.get("error"):
            raise HTTPException(400, parsed["error"])
        d["platform"], d["ref"] = parsed["platform"], parsed["ref"]
    return {"job_id": jobs.create("blogger", d, title="博主采集", platform=d["platform"])}


@app.post("/api/jobs/transcribe")
def job_transcribe(d: dict = Body(...)):
    ids = d.get("content_ids") or []
    return {"job_id": jobs.create("transcribe", d, title=f"转写 {len(ids)} 条")}


@app.post("/api/jobs/refresh")
def job_refresh(d: dict = Body(...)):
    ids = d.get("content_ids") or []
    return {"job_id": jobs.create("refresh", d, title=f"刷新数据 {len(ids)} 条")}


@app.post("/api/jobs/style")
def job_style(d: dict = Body(...)):
    a = db.q1("SELECT * FROM authors WHERE id=?", (int(d.get("author_pk") or 0),))
    if not a:
        raise HTTPException(400, "博主不存在")
    n = int(d.get("limit") or 0)
    return {"job_id": jobs.create("style", d, title=f"文风 DNA「{a.get('nickname')}」{n or '全部'}条", platform=a["platform"])}


@app.get("/api/jobs")
def list_jobs(limit: int = 50, kind: str = "", status: str = ""):
    w, a = ["1=1"], []
    if kind:
        w.append("kind=?")
        a.append(kind)
    if status:
        w.append("status=?")
        a.append(status)
    return [job_row(j) for j in db.q(f"SELECT * FROM jobs WHERE {' AND '.join(w)} ORDER BY id DESC LIMIT ?", (*a, limit))]


@app.get("/api/jobs/{jid}")
def get_job(jid: int):
    j = db.q1("SELECT * FROM jobs WHERE id=?", (jid,))
    if not j:
        raise HTTPException(404)
    rows = db.q("""SELECT c.*, s.rank, a.nickname author_name, a.avatar author_avatar,
                   (SELECT COUNT(*) FROM sources s2 WHERE s2.content_pk=c.id AND s2.job_id<>s.job_id) seen_before
                   FROM sources s JOIN contents c ON c.id=s.content_pk LEFT JOIN authors a ON a.id=c.author_pk
                   WHERE s.job_id=? ORDER BY COALESCE(s.rank, 9999), s.id""", (jid,))
    calls = db.q1("SELECT COUNT(*) n, SUM(1-ok) failed FROM calls WHERE job_id=?", (jid,))
    return {**job_row(j, with_log=True), "results": insights.add([content_row(r) for r in rows]), "calls": calls}


@app.post("/api/jobs/{jid}/cancel")
def cancel_job(jid: int):
    jobs.cancel(jid)
    return {"ok": True}


@app.post("/api/jobs/{jid}/retry")
def retry_job(jid: int):
    j = db.q1("SELECT * FROM jobs WHERE id=?", (jid,))
    return {"job_id": jobs.create(j["kind"], _j(j["params"], {}), title=(j["title"] or "") + "（重试）", platform=j["platform"])}


# ---------------- 内容 ----------------
@app.get("/api/contents")
def list_contents(platform: str = "", q: str = "", author: int = 0, transcript: str = "", source: str = "",
                  keyword: str = "", sort: str = "first_seen", order: str = "desc", page: int = 1, size: int = 50):
    w, a = ["1=1"], []
    if platform:
        w.append("c.platform=?")
        a.append(platform)
    if q:
        w.append("(c.title LIKE ? OR c.caption LIKE ? OR a.nickname LIKE ? OR c.transcript_text LIKE ?)")
        a += [f"%{q}%"] * 4
    if author:
        w.append("c.author_pk=?")
        a.append(author)
    if transcript:
        w.append("c.transcript_status=?")
        a.append(transcript)
    if source:
        w.append("EXISTS(SELECT 1 FROM sources s WHERE s.content_pk=c.id AND s.kind=?)")
        a.append(source)
    if keyword:
        w.append("EXISTS(SELECT 1 FROM sources s WHERE s.content_pk=c.id AND s.kind='keyword' AND s.ref LIKE ?)")
        a.append(f"%:{keyword}")
    col = {"first_seen": "c.first_seen", "published_at": "c.published_at", "likes": "c.likes", "comments": "c.comments",
           "saves": "c.saves", "shares": "c.shares", "views": "c.views"}.get(sort, "c.first_seen")
    od = "ASC" if order == "asc" else "DESC"
    where = " AND ".join(w)
    total = db.q1(f"SELECT COUNT(*) n FROM contents c LEFT JOIN authors a ON a.id=c.author_pk WHERE {where}", a)["n"]
    rows = db.q(f"""SELECT c.*, a.nickname author_name, a.avatar author_avatar,
                    (SELECT COUNT(*) FROM sources s WHERE s.content_pk=c.id) source_count
                    FROM contents c LEFT JOIN authors a ON a.id=c.author_pk WHERE {where}
                    ORDER BY {col} IS NULL, {col} {od} LIMIT ? OFFSET ?""", (*a, size, (page - 1) * size))
    return {"total": total, "items": insights.add([content_row(r) for r in rows])}


@app.get("/api/contents/export")
def export_contents(platform: str = "", author: int = 0, keyword: str = "", ids: str = ""):
    from openpyxl import Workbook
    w, a = ["1=1"], []
    if platform:
        w.append("c.platform=?")
        a.append(platform)
    if author:
        w.append("c.author_pk=?")
        a.append(author)
    if keyword:
        w.append("EXISTS(SELECT 1 FROM sources s WHERE s.content_pk=c.id AND s.kind='keyword' AND s.ref LIKE ?)")
        a.append(f"%:{keyword}")
    if ids:
        idl = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        w.append(f"c.id IN ({','.join('?' * len(idl))})")
        a += idl
    rows = db.q(f"""SELECT c.*, a.nickname author_name FROM contents c LEFT JOIN authors a ON a.id=c.author_pk
                    WHERE {' AND '.join(w)} ORDER BY c.published_at DESC""", a)
    wb = Workbook()
    ws = wb.active
    ws.title = "内容"
    head = ["平台", "博主", "标题", "发布时间", "时长(秒)", "播放", "点赞", "评论", "收藏", "分享", "链接", "逐字稿", "前5秒", "文件"]
    ws.append(head)
    for r in rows:
        cues = _j(r.get("transcript_text"), []) or []
        ws.append([PLATFORMS.get(r["platform"]), r.get("author_name"), r.get("title"),
                   time.strftime("%Y-%m-%d %H:%M", time.localtime(r["published_at"])) if r.get("published_at") else "",
                   r.get("duration_s"), r.get("views"), r.get("likes"), r.get("comments"), r.get("saves"), r.get("shares"),
                   r.get("url"), "".join(t for _, t in cues)[:32000], "".join(t for s, t in cues if s < 5),
                   r.get("transcript_path")])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    name = f"观自行深监控台_{time.strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{__import__('urllib.parse').parse.quote(name)}"})


@app.get("/api/contents/{pk}")
def get_content(pk: int):
    c = db.q1("SELECT * FROM contents WHERE id=?", (pk,))
    if not c:
        raise HTTPException(404)
    a = db.q1("SELECT * FROM authors WHERE id=?", (c["author_pk"],)) if c.get("author_pk") else None
    if a:
        a["snap"] = db.q1("SELECT * FROM author_snapshots WHERE author_pk=? ORDER BY ts DESC LIMIT 1", (a["id"],))
        a["monitor"] = db.q1("SELECT * FROM monitors WHERE kind='blogger' AND target=?", (str(a["id"]),))
    return {**insights.add([content_row(c, full=True)])[0], "author": a,
            "snapshots": db.q("SELECT * FROM metric_snapshots WHERE content_pk=? ORDER BY ts", (pk,)),
            "sources": db.q("SELECT * FROM sources WHERE content_pk=? ORDER BY ts DESC", (pk,))}


# ---------------- 博主 ----------------
def _user_file(path: str | None) -> Path:
    """只允许下载当前用户数据目录里的文件。"""
    if not path:
        raise HTTPException(404, "没有文件")
    f = Path(path).resolve()
    root = db.data_root().resolve()
    if root not in f.parents or not f.is_file():
        raise HTTPException(404, "文件不存在")
    return f


@app.get("/api/contents/{pk}/transcript.md")
def download_transcript(pk: int):
    c = db.q1("SELECT transcript_path FROM contents WHERE id=?", (pk,))
    f = _user_file(c and c["transcript_path"])
    return FileResponse(f, media_type="text/markdown; charset=utf-8", filename=f.name)


@app.get("/api/authors")
def list_authors(platform: str = "", q: str = "", monitored: int = 0):
    w, a = ["1=1"], []
    if platform:
        w.append("a.platform=?")
        a.append(platform)
    if q:
        w.append("a.nickname LIKE ?")
        a.append(f"%{q}%")
    if monitored:
        w.append("EXISTS(SELECT 1 FROM monitors m WHERE m.kind='blogger' AND m.target=CAST(a.id AS TEXT))")
    return db.q(f"""SELECT a.*, (SELECT COUNT(*) FROM contents c WHERE c.author_pk=a.id) content_count,
                    (SELECT followers FROM author_snapshots s WHERE s.author_pk=a.id ORDER BY ts DESC LIMIT 1) followers,
                    (SELECT id FROM monitors m WHERE m.kind='blogger' AND m.target=CAST(a.id AS TEXT)) monitor_id
                    FROM authors a WHERE {' AND '.join(w)} ORDER BY a.last_seen DESC LIMIT 300""", a)


@app.get("/api/authors/{pk}")
def get_author(pk: int):
    a = db.q1("SELECT * FROM authors WHERE id=?", (pk,))
    if not a:
        raise HTTPException(404)
    a["extra"] = _j(a.get("extra"), {})
    snaps = db.q("SELECT * FROM author_snapshots WHERE author_pk=? ORDER BY ts", (pk,))
    contents = [content_row(r) for r in db.q("""SELECT c.*, (SELECT MIN(s.ts) FROM sources s WHERE s.content_pk=c.id
                 AND s.kind='blogger') first_blogger_ts FROM contents c WHERE author_pk=? ORDER BY published_at DESC""", (pk,))]
    insights.add(contents)
    cutoff = db.now() - 30 * 86400
    recent = [c for c in contents if (c.get("published_at") or 0) >= cutoff]
    likes = [c["likes"] for c in contents if c.get("likes") is not None]
    avg = sum(likes) / len(likes) if likes else 0
    for c in contents:
        c["hot"] = bool(avg and (c.get("likes") or 0) >= 3 * avg)
    stats = {"recent_posts": len(recent),
             "recent_avg_likes": round(sum(c.get("likes") or 0 for c in recent) / len(recent)) if recent else None,
             "avg_likes": round(avg) if avg else None, "hot": sum(c["hot"] for c in contents),
             "transcribed": sum(c["transcript_status"] == "done" for c in contents), "total": len(contents),
             "baseline": insights.author_baseline(contents)}
    mon = db.q1("SELECT * FROM monitors WHERE kind='blogger' AND target=?", (str(pk),))
    return {**a, "snapshots": snaps, "latest": snaps[-1] if snaps else None, "contents": contents, "stats": stats, "monitor": mon}


@app.post("/api/authors/{pk}/fetch")
def author_fetch(pk: int, d: dict = Body({})):
    a = db.q1("SELECT * FROM authors WHERE id=?", (pk,))
    p = {"platform": a["platform"], "ref": {"author_id": a["author_id"], "sec_uid": a.get("sec_uid"),
                                            "username": a["author_id"]},
         "limit": d.get("limit", 20), "transcribe": d.get("transcribe", False)}
    return {"job_id": jobs.create("blogger", p, title=f"博主「{a.get('nickname')}」", platform=a["platform"])}


# ---------------- 文风 DNA ----------------
def style_row(r: dict, full=False) -> dict:
    r = dict(r)
    for k in ("scores", "meta", "stats"):
        r[k] = _j(r.get(k), {})
    if not full:
        r.pop("report", None)
        r.pop("stats", None)
    return r


@app.get("/api/authors/{pk}/style-reports")
def author_style_reports(pk: int):
    return [style_row(r) for r in db.q("SELECT * FROM style_reports WHERE author_pk=? ORDER BY id DESC", (pk,))]


@app.get("/api/style-reports/{rid}")
def get_style_report(rid: int):
    r = db.q1("SELECT * FROM style_reports WHERE id=?", (rid,))
    if not r:
        raise HTTPException(404)
    a = db.q1("SELECT id, nickname, avatar, platform FROM authors WHERE id=?", (r["author_pk"],))
    return {**style_row(r, full=True), "author": a}


@app.get("/api/style-reports/{rid}/report.md")
def download_style_report(rid: int):
    r = db.q1("SELECT path FROM style_reports WHERE id=?", (rid,))
    f = _user_file(r and r["path"])
    return FileResponse(f, media_type="text/markdown; charset=utf-8", filename=f.name)


@app.delete("/api/style-reports/{rid}")
def delete_style_report(rid: int):
    db.x("DELETE FROM style_reports WHERE id=?", (rid,))
    return {"ok": True}


# ---------------- 监控 ----------------
@app.get("/api/monitors")
def list_monitors(kind: str = ""):
    rows = db.q(f"""SELECT m.*, a.nickname, a.avatar, a.platform a_platform FROM monitors m
                    LEFT JOIN authors a ON m.kind='blogger' AND a.id=CAST(m.target AS INTEGER)
                    {'WHERE m.kind=?' if kind else ''} ORDER BY m.id DESC""", (kind,) if kind else ())
    for r in rows:
        r["params"] = _j(r.get("params"), {})
        r["total_found"] = db.q1("SELECT COUNT(DISTINCT content_pk) n FROM sources WHERE monitor_id=?", (r["id"],))["n"]
        r["running"] = bool(db.q1("SELECT 1 FROM jobs WHERE monitor_id=? AND status IN ('queued','running')", (r["id"],)))
    return rows


MAX_MONITORS = 20          # 网页版每人最多几个监控
MIN_INTERVAL_HOURS = 6     # 最短间隔（和前端最小选项一致）
MAX_MONITOR_ITEMS = 100    # 每次监控最多采多少条


def _check_monitor(d: dict):
    if "interval_hours" in d and float(d["interval_hours"] or 0) < MIN_INTERVAL_HOURS:
        raise HTTPException(400, f"监控间隔最短 {MIN_INTERVAL_HOURS} 小时")
    if "max_items" in d and int(d["max_items"] or 0) > MAX_MONITOR_ITEMS:
        raise HTTPException(400, f"每次监控最多采 {MAX_MONITOR_ITEMS} 条")


@app.post("/api/monitors")
def create_monitor(d: dict = Body(...)):
    kind = d["kind"]
    target = str(d["target"]).strip()
    if kind == "blogger" and not target.isdigit():
        raise HTTPException(400, "博主监控要先把博主采集进库")
    ex = db.q1("SELECT * FROM monitors WHERE kind=? AND platform=? AND target=?", (kind, d["platform"], target))
    if db.SERVER:
        _check_monitor(d)
        if not ex and db.q1("SELECT COUNT(*) n FROM monitors")["n"] >= MAX_MONITORS:
            raise HTTPException(429, f"每个账号最多 {MAX_MONITORS} 个监控，先删掉不用的")
    if ex:
        db.x("UPDATE monitors SET enabled=1 WHERE id=?", (ex["id"],))
        return {"id": ex["id"], "existed": True}
    mid = db.x("""INSERT INTO monitors(kind, platform, target, label, params, interval_hours, auto_transcribe, max_items,
                  enabled, next_run, created) VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
               (kind, d["platform"], target, d.get("label") or target, json.dumps(d.get("params") or {}, ensure_ascii=False),
                d.get("interval_hours", 24), int(bool(d.get("auto_transcribe"))), d.get("max_items", 20),
                db.now() + float(d.get("interval_hours", 24)) * 3600 if d.get("skip_first") else db.now() + 5, db.now()))
    return {"id": mid}


@app.patch("/api/monitors/{mid}")
def patch_monitor(mid: int, d: dict = Body(...)):
    if db.SERVER:
        _check_monitor(d)
    allowed = {"interval_hours", "auto_transcribe", "max_items", "enabled", "label", "params"}
    for k, v in d.items():
        if k in allowed:
            if k == "params":
                v = json.dumps(v, ensure_ascii=False)
            if k in ("auto_transcribe", "enabled"):
                v = int(bool(v))
            db.x(f"UPDATE monitors SET {k}=? WHERE id=?", (v, mid))
    if "interval_hours" in d:
        m = db.q1("SELECT * FROM monitors WHERE id=?", (mid,))
        base = m.get("last_run") or db.now()
        db.x("UPDATE monitors SET next_run=? WHERE id=?", (base + float(d["interval_hours"]) * 3600, mid))
    return db.q1("SELECT * FROM monitors WHERE id=?", (mid,))


@app.delete("/api/monitors/{mid}")
def delete_monitor(mid: int):
    db.x("DELETE FROM monitors WHERE id=?", (mid,))
    return {"ok": True}


@app.post("/api/monitors/{mid}/run")
def run_monitor(mid: int):
    return {"job_id": scheduler.run_monitor(mid)}


@app.get("/api/monitors/{mid}/runs")
def monitor_runs(mid: int):
    return [job_row(j) for j in db.q("SELECT * FROM jobs WHERE monitor_id=? ORDER BY id DESC LIMIT 30", (mid,))]


@app.get("/api/parse")
def parse(text: str = Query(""), kind: str = "video"):
    return links.parse_video(text) if kind == "video" else links.parse_author(text)


@app.get("/api/img")
def img(u: str):
    r = images.get(u)
    if not r:
        raise HTTPException(404)
    f, mime = r
    return FileResponse(f, media_type=mime, headers={"Cache-Control": "public, max-age=31536000"})


# ---------------- 前端 ----------------
if (WEB / "assets").exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")


@app.get("/{path:path}")
def spa(path: str):
    f = WEB / path
    if path and f.is_file():
        return FileResponse(f)
    idx = WEB / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return {"msg": "前端还没打包：cd web && pnpm build"}
