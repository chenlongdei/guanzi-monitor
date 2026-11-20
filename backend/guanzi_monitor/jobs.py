"""任务：单条 / 关键词 / 博主 / 转写。后台线程跑，进度写进 jobs 表，前端轮询或 SSE 读。"""
from __future__ import annotations

import contextvars
import json
import math
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import db
from .providers import PLATFORMS, ProviderError, get_provider
from .services import links, store
from .services.transcribe import PARAFORMER_CNY_PER_SEC, TranscribeError, transcribe_content

POOL = ThreadPoolExecutor(max_workers=6 if db.SERVER else 3, thread_name_prefix="job")   # 同时跑的任务数（网页版所有人共用）
ENRICH_PARALLEL = 10                                                  # 单个任务里补详情的并发数
TPOOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="asr")
_cancel: set[tuple] = set()   # (用户, 任务 id)：网页版每个用户的任务 id 各自从 1 开始


def _ck(jid: int) -> tuple:
    return (db.current_user(), jid)


def _submit(pool, fn, *a):
    """提交到线程池时带上当前用户（contextvars 不会自动传进线程）。"""
    return pool.submit(contextvars.copy_context().run, fn, *a)
_jlock = threading.Lock()

KIND_LABEL = {"single": "单条采集", "keyword": "关键词", "blogger": "博主", "transcribe": "转写", "refresh": "刷新数据", "style": "文风 DNA"}


class Stop(Exception):
    pass


class Job:
    def __init__(self, jid: int):
        self.id = jid
        self.row = db.q1("SELECT * FROM jobs WHERE id=?", (jid,))
        self.p = json.loads(self.row["params"] or "{}")
        self.s = db.get_settings()
        self.provider = get_provider(self.s, self.on_call)
        self.logs = []
        self._ll = threading.Lock()

    def on_call(self, provider, endpoint, cost, ok, ms, err):
        db.x("INSERT INTO calls(job_id, provider, endpoint, cost_usd, ok, ms, ts, error) VALUES(?,?,?,?,?,?,?,?)",
             (self.id, provider, endpoint, cost, int(ok), ms, db.now(), err))
        if cost:
            db.x("UPDATE jobs SET cost_usd = cost_usd + ? WHERE id=?", (cost, self.id))

    def log(self, msg, level="info"):
        with self._ll:  # 转写线程也会写日志
            self.logs.append({"t": time.time(), "level": level, "msg": msg})
            self.logs = self.logs[-300:]
            db.x("UPDATE jobs SET log=? WHERE id=?", (json.dumps(self.logs, ensure_ascii=False), self.id))
        if _ck(self.id) in _cancel:
            raise Stop()

    def inc(self, **kw):
        sets = ", ".join(f"{k} = {k} + ?" for k in kw)
        db.x(f"UPDATE jobs SET {sets} WHERE id=?", (*kw.values(), self.id))

    def set(self, **kw):
        sets = ", ".join(f"{k}=?" for k in kw)
        db.x(f"UPDATE jobs SET {sets} WHERE id=?", (*kw.values(), self.id))


def create(kind: str, params: dict, title: str = "", platform: str | None = None, monitor_id: int | None = None) -> int:
    jid = db.x("INSERT INTO jobs(kind, platform, title, params, status, created, monitor_id) VALUES(?,?,?,?,?,?,?)",
               (kind, platform, title, json.dumps(params, ensure_ascii=False), "queued", db.now(), monitor_id))
    _submit(POOL, _run, jid)
    return jid


def cancel(jid: int):
    _cancel.add(_ck(jid))


def _run(jid: int):
    j = Job(jid)
    j.set(status="running", started=db.now())
    try:
        {"single": run_single, "keyword": run_keyword, "blogger": run_blogger,
         "transcribe": run_transcribe, "refresh": run_refresh, "style": run_style}[j.row["kind"]](j)
        row = db.q1("SELECT failed, done FROM jobs WHERE id=?", (jid,))
        j.set(status="partial" if row["failed"] and row["done"] else ("failed" if row["failed"] else "done"), finished=db.now())
        j.log("完成")
    except Stop:
        j.set(status="canceled", finished=db.now())
    except ProviderError as e:
        j.logs.append({"t": time.time(), "level": "error", "msg": str(e)})
        j.set(status="failed", error=str(e), finished=db.now(), log=json.dumps(j.logs, ensure_ascii=False))
    except Exception as e:  # noqa
        traceback.print_exc()
        j.logs.append({"t": time.time(), "level": "error", "msg": repr(e)})
        j.set(status="failed", error=repr(e)[:500], finished=db.now(), log=json.dumps(j.logs, ensure_ascii=False))
    finally:
        _cancel.discard(_ck(jid))
        if j.row.get("monitor_id"):
            from .scheduler import after_monitor_job
            after_monitor_job(j.row["monitor_id"], jid)


def _safe_log(j: Job):
    """给转写线程用的日志：写库失败或任务被取消都不打断转写本身（取消由主线程处理）。"""
    def log(msg, level="info"):
        try:
            j.log(msg, level)
        except Exception:  # noqa
            pass
    return log


# ---------------- 转写（并发 3） ----------------
def _transcribe_many(j: Job, pks: list[int]):
    if not pks:
        return
    j.log(f"开始转写 {len(pks)} 条")
    futs = {_submit(TPOOL, transcribe_content, pk, j.provider, j.s, j.p.get("force", False), _safe_log(j)): pk for pk in pks}
    for f, pk in futs.items():
        try:
            r = f.result()
            if r.get("skipped"):
                j.log(f"#{pk} 跳过：{r['reason']}")
            else:
                j.inc(cost_cny=r.get("cost_cny") or 0)
                j.log(f"#{pk} 转写完成")
        except (TranscribeError, ProviderError, Exception) as e:  # noqa
            j.log(f"#{pk} 转写失败：{e}", "warn")


# ---------------- 单条 ----------------
def run_single(j: Job):
    entries = links.parse_video(j.p.get("text", ""))
    j.set(total=len(entries))
    pks = []
    for i, e in enumerate(entries, 1):
        if e.get("error"):
            j.log(f"{e['raw'][:60]}：{e['error']}", "warn")
            j.inc(failed=1)
            continue
        try:
            j.log(f"[{i}/{len(entries)}] {PLATFORMS[e['platform']]} {e['raw'][:60]}")
            item = j.provider.video(e["platform"], e["ref"])
            if not item.get("content_id"):
                raise ProviderError("接口没返回内容 ID")
            pk, new = store.upsert_content(item, j.provider.name, "single", ref=e["raw"][:200], label="单条采集", job_id=j.id)
            pks.append(pk)
            j.inc(done=1, new_count=int(new))
        except ProviderError as ex:
            j.log(f"失败：{ex}", "warn")
            j.inc(failed=1)
            if ex.fatal:
                raise
    if j.p.get("transcribe"):
        _transcribe_many(j, pks)


# ---------------- 关键词 ----------------
def run_keyword(j: Job):
    plat, kw = j.p["platform"], j.p["keyword"].strip()
    limit = int(j.p.get("limit") or 20)
    opts = j.p.get("opts") or {}
    mid = j.row.get("monitor_id")
    j.set(total=limit)
    seen, pks, cursor, rank, empty_pages = set(), [], None, 0, 0
    for page in range(1, 30):
        j.log(f"{PLATFORMS[plat]} 搜「{kw}」第 {page} 页")
        pg = j.provider.search(plat, kw, j.p.get("sort", "relevance"), int(j.p.get("days") or 0), cursor, opts)
        fresh = []
        for it in pg.items:
            if it.get("content_id") and it["content_id"] not in seen and rank + len(fresh) < limit:
                seen.add(it["content_id"])
                fresh.append(it)
        if not fresh:
            empty_pages += 1
        if fresh and opts.get("enrich", True) and _needs_enrich(plat, fresh[0]):
            fresh = _enrich_many(j, plat, fresh)
        # 一次事务写完这一页（逐条提交在外接盘上很慢）
        with db.tx():
            for it in fresh:
                rank += 1
                seen_by_monitor = mid and db.q1(
                    "SELECT 1 FROM sources s JOIN contents c ON c.id=s.content_pk WHERE c.platform=? AND c.content_id=? AND s.monitor_id=?",
                    (plat, str(it["content_id"]), mid))
                pk, new = store.upsert_content(it, j.provider.name, "keyword", ref=f"{plat}:{kw}", label=f"关键词「{kw}」",
                                               rank=rank, job_id=j.id, monitor_id=mid)
                if mid:  # 监控里的「新」= 这个监控以前没见过（新上榜）
                    new = not seen_by_monitor
                pks.append(pk)
                j.inc(done=1, new_count=int(new))
        if rank >= limit or not pg.has_more or not pg.next_cursor or empty_pages >= 2:
            break
        cursor = pg.next_cursor
    j.set(total=rank)
    j.log(f"共 {rank} 条")
    if j.p.get("transcribe"):
        _transcribe_many(j, pks)


def _needs_enrich(plat: str, it: dict) -> bool:
    """抖音指数只给点赞；视频号搜索连点赞都没有 → 需要逐条补详情。"""
    if plat == "sph":
        return bool((it.get("extra") or {}).get("needs_detail"))
    if plat == "douyin":
        return (it.get("extra") or {}).get("engine") == "抖音指数"
    return False


def _enrich_one(j: Job, plat: str, it: dict) -> dict:
    if plat == "sph":
        return _sph_enrich(j, it)
    have = db.q1("SELECT comments FROM contents WHERE platform=? AND content_id=?", (plat, it["content_id"]))
    if have and have["comments"] is not None:
        return it  # 库里已有完整数据，不重复花钱
    try:
        d = j.provider.video(plat, {"content_id": it["content_id"], "url": it.get("url")})
        if d.get("content_id") != it["content_id"]:
            return it
        d["extra"] = {**(d.get("extra") or {}), **(it.get("extra") or {})}  # 保留视频指数、爆款标签
        d["tags"] = it.get("tags") or d.get("tags")
        d["cover"] = d.get("cover") or it.get("cover")
        d["views"] = d.get("views") if d.get("views") is not None else it.get("views")
        return d
    except ProviderError as e:
        if e.fatal:
            raise
        j.log(f"补详情失败：{it.get('title', '')[:20]}：{e}", "warn")
        return it


def _enrich_many(j: Job, plat: str, items: list) -> list:
    j.log(f"补全详情 {len(items)} 条（并行 {ENRICH_PARALLEL}）")
    with ThreadPoolExecutor(max_workers=ENRICH_PARALLEL) as ex:
        futs = [_submit(ex, _enrich_one, j, plat, it) for it in items]
        out = []
        for f, it in zip(futs, items):
            try:
                out.append(f.result())
            except ProviderError as e:
                if e.fatal:
                    raise
                out.append(it)
    return out


# ---------------- 博主 ----------------
def run_blogger(j: Job):
    plat = j.p["platform"]
    ref = j.p.get("ref")
    if not ref:
        parsed = links.parse_author(j.p.get("input", ""), plat)
        if parsed.get("error"):
            raise ProviderError(parsed["error"])
        plat, ref = parsed["platform"], parsed["ref"]
        j.set(platform=plat)
    if plat == "douyin" and not str(ref.get("sec_uid") or "").startswith("MS4w"):
        ref = _resolve_douyin_sec(j, ref)
    if plat == "sph" and not str(ref.get("username") or ref.get("author_id") or "").endswith("@finder") \
            and not str(ref.get("author_id") or "").startswith("sph"):
        ref = _resolve_sph_user(j, ref)
    j.log(f"获取{PLATFORMS[plat]}博主资料")
    try:
        prof = j.provider.profile(plat, ref)
        apk = store.upsert_author(prof, source="profile", full_profile=True)
        j.set(title=f"博主「{prof.get('nickname') or ref.get('author_id')}」")
        ref = {**ref, **{k: prof.get(k) for k in ("author_id", "sec_uid", "username") if prof.get(k)}}
    except ProviderError as e:
        if e.fatal:
            raise
        j.log(f"资料获取失败，继续拉作品：{e}", "warn")
        apk = None
    limit = int(j.p.get("limit") or 20)
    since = float(j.p.get("since") or 0)  # 监控：只要这个时间之后发布的
    j.set(total=limit)
    seen, pks, cursor, n, old_streak = set(), [], None, 0, 0
    for page in range(1, 50):
        j.log(f"拉作品第 {page} 页")
        pg = j.provider.posts(plat, ref, cursor)
        items = sorted([i for i in pg.items if i.get("content_id")], key=lambda x: -(x.get("published_at") or 0))
        fresh = [i for i in items if i["content_id"] not in seen]
        for it in fresh:
            seen.add(it["content_id"])
            if since and (it.get("published_at") or 0) <= since:
                old_streak += 1
                # 置顶作品可能很老，也照样记一次数据快照
                store.upsert_content(it, j.provider.name, "blogger", ref=str(apk or ref.get("author_id")),
                                     label="博主监控", job_id=j.id, monitor_id=j.row.get("monitor_id"))
                continue
            if n >= limit:
                break
            n += 1
            pk, new = store.upsert_content(it, j.provider.name, "blogger", ref=str(apk or ref.get("author_id")),
                                           label="博主监控" if j.row.get("monitor_id") else "博主采集", rank=n,
                                           job_id=j.id, monitor_id=j.row.get("monitor_id"))
            if apk is None:
                apk = db.q1("SELECT author_pk FROM contents WHERE id=?", (pk,))["author_pk"]
            pks.append(pk)
            j.inc(done=1, new_count=int(new))
        if n >= limit or not pg.has_more or not pg.next_cursor or not fresh or (since and old_streak >= 6):
            break
        cursor = pg.next_cursor
    j.set(total=n)
    j.p["author_pk"] = apk
    j.set(params=json.dumps(j.p, ensure_ascii=False))
    j.log(f"共 {n} 条")
    if j.p.get("transcribe"):
        _transcribe_many(j, pks)


def _resolve_douyin_sec(j: Job, ref: dict) -> dict:
    """抖音指数 / 站内搜索给的作者没有 sec_uid：拿他库里的一条作品查一次详情（$0.001），补上 sec_uid。"""
    a = db.q1("SELECT * FROM authors WHERE platform='douyin' AND (author_id=? OR sec_uid=?)",
              (str(ref.get("author_id")), str(ref.get("sec_uid") or ref.get("author_id"))))
    if a and str(a.get("sec_uid") or "").startswith("MS4w"):
        return {**ref, "sec_uid": a["sec_uid"]}
    c = a and db.q1("SELECT * FROM contents WHERE author_pk=? ORDER BY published_at DESC LIMIT 1", (a["id"],))
    if not c:
        raise ProviderError("这个博主还没有抖音主页 ID：请粘贴他的主页链接")
    j.log("补全博主主页 ID（查一条作品详情）")
    item = j.provider.video("douyin", store.content_ref(c))
    sec = (item.get("author") or {}).get("sec_uid")
    if not sec:
        raise ProviderError("作品详情里也没有博主主页 ID：请粘贴他的主页链接")
    store.upsert_content(item, j.provider.name, "refresh", label="补全博主 ID", job_id=j.id)
    db.x("UPDATE authors SET sec_uid=? WHERE id=?", (sec, a["id"]))
    return {**ref, "sec_uid": sec, "author_id": sec}


def _sph_enrich(j: Job, it: dict) -> dict:
    """视频号搜索结果没有点赞数据和 username：用 exportId 查一次详情（$0.01）。已经在库里有数据的跳过。"""
    have = db.q1("SELECT likes FROM contents WHERE platform='sph' AND content_id=?", (it["content_id"],))
    if have and have["likes"] is not None:
        return it
    try:
        d = j.provider.video("sph", {k: it["extra"].get(k) for k in ("export_id", "object_nonce_id") if it["extra"].get(k)})
        if d.get("content_id") == it["content_id"]:
            d["cover"] = d.get("cover") or it.get("cover")
            d["duration_s"] = d.get("duration_s") or it.get("duration_s")
            return d
        j.log(f"详情 ID 对不上，保留搜索结果：{it['title'][:20]}", "warn")
    except ProviderError as e:
        if e.fatal:
            raise
        j.log(f"补详情失败：{e}", "warn")
    return it


def _resolve_sph_user(j: Job, ref: dict) -> dict:
    a = db.q1("SELECT * FROM authors WHERE platform='sph' AND author_id=?", (str(ref.get("author_id")),))
    c = a and db.q1("SELECT * FROM contents WHERE author_pk=? ORDER BY published_at DESC LIMIT 1", (a["id"],))
    if not c:
        raise ProviderError("这个视频号还没有 ID：请粘贴 sph 开头的视频号 ID")
    j.log("补全视频号 ID（查一条作品详情）")
    item = j.provider.video("sph", store.content_ref(c))
    u = (item.get("author") or {}).get("username")
    if not u:
        raise ProviderError("作品详情里没有视频号 ID")
    store.upsert_content(item, j.provider.name, "refresh", label="补全视频号 ID", job_id=j.id)
    return {**ref, "author_id": u, "username": u}


def run_transcribe(j: Job):
    pks = [int(x) for x in j.p.get("content_ids", [])]
    j.set(total=len(pks))
    _transcribe_many(j, pks)
    rows = db.q(f"SELECT transcript_status FROM contents WHERE id IN ({','.join('?' * len(pks))})", pks) if pks else []
    j.set(done=sum(r["transcript_status"] in ("done", "na") for r in rows),
          failed=sum(r["transcript_status"] == "failed" for r in rows))


def run_refresh(j: Job):
    pks = [int(x) for x in j.p.get("content_ids", [])]
    j.set(total=len(pks))
    for pk in pks:
        c = db.q1("SELECT * FROM contents WHERE id=?", (pk,))
        try:
            item = j.provider.video(c["platform"], store.content_ref(c))
            store.upsert_content(item, j.provider.name, "refresh", ref="", label="刷新数据", job_id=j.id)
            j.inc(done=1)
        except ProviderError as e:
            j.log(f"#{pk} 刷新失败：{e}", "warn")
            j.inc(failed=1)
            if e.fatal:
                raise


# ---------------- 文风 DNA ----------------
def run_style(j: Job):
    from .services import style
    apk = int(j.p["author_pk"])
    author = db.q1("SELECT * FROM authors WHERE id=?", (apk,))
    if not author:
        raise ProviderError("博主不存在")
    limit = int(j.p.get("limit") or 0)
    if j.p.get("transcribe_missing"):
        sql = """SELECT id FROM contents WHERE author_pk=? AND transcript_status IN ('none','failed')
                 AND COALESCE(type,'video')<>'image' AND platform<>'sph'
                 AND id IN (SELECT id FROM contents WHERE author_pk=? ORDER BY published_at IS NULL, published_at DESC {})"""
        todo = [r["id"] for r in db.q(sql.format("LIMIT ?" if limit else ""), (apk, apk, limit) if limit else (apk, apk))]
        if todo:
            _transcribe_many(j, todo)
    items = style.collect(apk, limit)
    if not items:
        raise ProviderError("这个博主库里还没有带文字的内容：先拉取作品或转写")
    j.set(total=1)
    j.log(f"取到 {len(items)} 条，其中有逐字稿 {sum(1 for i in items if i['transcript'])} 条")
    try:
        r = style.analyze(author, items, j.s, j.log)
    except style.StyleError as e:
        raise ProviderError(str(e), fatal=True) from e
    j.inc(cost_usd=r["cost_usd"])
    path = style.write_md(author, r)
    meta = r["meta"] or {}
    rid = db.x("""INSERT INTO style_reports(author_pk, job_id, model, n_items, n_cut, summary, scores, meta, stats, report, path,
                  in_tokens, out_tokens, cost_usd, created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (apk, j.id, r["model"], r["used"], r["cut"], meta.get("summary"),
                json.dumps(meta.get("scores") or {}, ensure_ascii=False), json.dumps(meta, ensure_ascii=False),
                json.dumps(r["stats"], ensure_ascii=False), r["report"], str(path), r["in_tokens"], r["out_tokens"],
                r["cost_usd"], db.now()))
    j.p["report_id"] = rid
    j.set(params=json.dumps(j.p, ensure_ascii=False), done=1)
    j.log(f"报告已保存：{path}")


# ---------------- 预估（计费前先报数） ----------------
def estimate(kind: str, p: dict) -> dict:
    s = db.get_settings()
    prov = get_provider(s)
    plat = p.get("platform") or "douyin"
    limit = int(p.get("limit") or s.get("default_limit") or 20)
    calls = []
    if kind == "single":
        es = links.parse_video(p.get("text", ""))
        for e in es:
            if e.get("platform"):
                calls.append(prov.price(e["platform"], "video"))
        n = len([e for e in es if e.get("platform")])
    elif kind == "keyword":
        eng = (p.get("opts") or {}).get("engine") or s.get("douyin_search_engine", "index")
        if plat == "douyin" and eng == "index":
            calls = [prov.price("douyin", "index_search")]  # 抖音指数一次返回整批
            if (p.get("opts") or {}).get("enrich", True):
                calls += [prov.price("douyin", "video") * 1.2] * limit  # 逐条补评论/收藏/分享
        else:
            per = 10 if plat != "douyin" else 12
            calls = [prov.price(plat, "search")] * math.ceil(limit / per)
            if plat == "sph" and (p.get("opts") or {}).get("enrich", True):
                calls += [prov.price("sph", "video")] * limit  # 视频号逐条补详情
        n = limit
    elif kind == "blogger":
        per = 20 if plat == "douyin" else 10
        calls = [prov.price(plat, "profile")] + [prov.price(plat, "posts")] * math.ceil(limit / per)
        n = limit
    elif kind == "style":
        from .services import style
        model = s.get("style_model") or "claude-opus-5-5"
        e = style.estimate(int(p["author_pk"]), int(p.get("limit") or 0), model)
        asr = 0.0
        if p.get("transcribe_missing"):
            lim = int(p.get("limit") or 0)
            ids = [r["id"] for r in db.q("SELECT id, transcript_status, type, platform FROM contents WHERE author_pk=? "
                                          "ORDER BY published_at IS NULL, published_at DESC" + (" LIMIT ?" if lim else ""),
                                          (p["author_pk"], lim) if lim else (p["author_pk"],))
                   if r["transcript_status"] in ("none", "failed") and r["type"] != "image" and r["platform"] != "sph"]
            asr = round(len(ids) * 90 * PARAFORMER_CNY_PER_SEC, 3)
            e["to_transcribe"] = len(ids)
            # 新转写的逐字稿也会进材料：按每条 90 秒、每秒约 4 字补进输入估算
            pi, _ = style.MODEL_PRICES.get(model, (4.0, 20.0))
            e["usd"] = round(e["usd"] + len(ids) * 360 * 1.1 * pi / 1e6, 3)
        rate = float(s.get("usd_cny") or 7.2)
        return {**e, "calls": 1, "asr_cny": asr, "total_cny": round(e["usd"] * rate + asr, 2),
                "need_confirm": True, "provider": style.MODEL_LABELS.get(model, model), "kind": "style"}
    else:
        n = len(p.get("content_ids") or [])
    usd = round(sum(calls), 4)
    asr_cny = round(n * 90 * PARAFORMER_CNY_PER_SEC, 3) if p.get("transcribe") and plat != "sph" else 0
    rate = float(s.get("usd_cny") or 7.2)
    total_cny = round(usd * rate + asr_cny, 3)
    return {"items": n, "calls": len(calls), "usd": usd, "asr_cny": asr_cny, "total_cny": total_cny,
            "need_confirm": n > int(s.get("confirm_over_items") or 20), "provider": prov.name}
