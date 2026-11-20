"""监控定时器：工作台开着时每 30 秒看一次哪些监控到点了，到点就建一个任务。

关键词监控：重新搜一次，第一次出现的内容算「新」；老内容追加一条数据快照。
博主监控：只要该博主库里最新一条之后发布的作品。
"""
from __future__ import annotations

import json
import threading
import time

from . import db, jobs

_started = False


def start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="scheduler").start()


def _loop():
    time.sleep(5)
    while True:
        try:
            tick()
        except Exception as e:  # noqa
            print("[scheduler]", repr(e))
        time.sleep(30)


def tick():
    t = db.now()
    for m in db.q("SELECT * FROM monitors WHERE enabled=1 AND (next_run IS NULL OR next_run<=?)", (t,)):
        running = db.q1("SELECT id FROM jobs WHERE monitor_id=? AND status IN ('queued','running')", (m["id"],))
        if not running:
            run_monitor(m["id"])


def run_monitor(mid: int) -> int:
    m = db.q1("SELECT * FROM monitors WHERE id=?", (mid,))
    params = json.loads(m.get("params") or "{}")
    # 先把 next_run 往后挪，防止重复触发
    db.x("UPDATE monitors SET next_run=? WHERE id=?", (db.now() + float(m["interval_hours"]) * 3600, mid))
    if m["kind"] == "keyword":
        p = {"platform": m["platform"], "keyword": m["target"], "sort": params.get("sort", "relevance"),
             "days": params.get("days", 7), "limit": m["max_items"], "transcribe": bool(m["auto_transcribe"]),
             "opts": {k: v for k, v in params.items() if k not in ("sort", "days")}}
        return jobs.create("keyword", p, title=f"监控 · 关键词「{m['target']}」", platform=m["platform"], monitor_id=mid)
    apk = int(m["target"])
    a = db.q1("SELECT * FROM authors WHERE id=?", (apk,))
    latest = db.q1("SELECT MAX(published_at) v FROM contents WHERE author_pk=?", (apk,))["v"] or 0
    p = {"platform": m["platform"], "ref": {"author_id": a["author_id"], "sec_uid": a.get("sec_uid"),
                                            "username": a["author_id"]},
         "limit": m["max_items"], "since": latest, "transcribe": bool(m["auto_transcribe"])}
    return jobs.create("blogger", p, title=f"监控 · 博主「{a.get('nickname') or a['author_id']}」",
                       platform=m["platform"], monitor_id=mid)


def after_monitor_job(mid: int, jid: int):
    j = db.q1("SELECT new_count, status FROM jobs WHERE id=?", (jid,))
    db.x("UPDATE monitors SET last_run=?, last_new=? WHERE id=?", (db.now(), j["new_count"] if j else 0, mid))
