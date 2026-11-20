"""SQLite 存储。一条内容只存一份（平台 + 原生 ID 唯一），会变的数据进快照表，来源进来源表。"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
import time
from pathlib import Path

BOOT = Path(os.environ.get("GM_HOME") or os.environ.get("DEI_WB_HOME") or Path.home() / ".guanzi-monitor")
BOOT_FILE = BOOT / "config.json"
DEFAULT_DATA = Path.home() / "观自行深监控台"
VERSION = "0.1.0"


def _migrate_old_home():
    """旧版配置目录 ~/.dei-workbench → ~/.guanzi-monitor（只搬一次）。"""
    old = Path.home() / ".dei-workbench"
    if old.is_dir() and not BOOT.exists() and not os.environ.get("GM_HOME"):
        import shutil
        shutil.copytree(old, BOOT)


_migrate_old_home()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS authors (
  id INTEGER PRIMARY KEY, platform TEXT NOT NULL, author_id TEXT NOT NULL,
  sec_uid TEXT, unique_id TEXT, nickname TEXT, avatar TEXT, bio TEXT, url TEXT,
  verified INTEGER, extra TEXT, first_seen REAL, last_seen REAL, profile_fetched REAL,
  UNIQUE(platform, author_id));

CREATE TABLE IF NOT EXISTS author_snapshots (
  id INTEGER PRIMARY KEY, author_pk INTEGER NOT NULL, ts REAL NOT NULL,
  followers INTEGER, following INTEGER, likes INTEGER, posts INTEGER, source TEXT);

CREATE TABLE IF NOT EXISTS contents (
  id INTEGER PRIMARY KEY, platform TEXT NOT NULL, content_id TEXT NOT NULL,
  url TEXT, title TEXT, caption TEXT, type TEXT, author_pk INTEGER,
  published_at REAL, duration_s REAL, cover TEXT, media_url TEXT, tags TEXT,
  provider TEXT, extra TEXT, first_seen REAL, last_seen REAL,
  views INTEGER, likes INTEGER, comments INTEGER, saves INTEGER, shares INTEGER,
  transcript_status TEXT DEFAULT 'none', transcript_text TEXT, transcript_path TEXT,
  transcript_error TEXT, transcript_cost REAL,
  UNIQUE(platform, content_id));
CREATE INDEX IF NOT EXISTS idx_contents_author ON contents(author_pk);
CREATE INDEX IF NOT EXISTS idx_contents_pub ON contents(published_at);

CREATE TABLE IF NOT EXISTS metric_snapshots (
  id INTEGER PRIMARY KEY, content_pk INTEGER NOT NULL, ts REAL NOT NULL,
  views INTEGER, likes INTEGER, comments INTEGER, saves INTEGER, shares INTEGER, source TEXT);
CREATE INDEX IF NOT EXISTS idx_ms_content ON metric_snapshots(content_pk);

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY, content_pk INTEGER NOT NULL, kind TEXT NOT NULL, ref TEXT,
  label TEXT, rank INTEGER, job_id INTEGER, monitor_id INTEGER, ts REAL,
  UNIQUE(content_pk, kind, ref, job_id));
CREATE INDEX IF NOT EXISTS idx_src_content ON sources(content_pk);
CREATE INDEX IF NOT EXISTS idx_src_job ON sources(job_id);

CREATE TABLE IF NOT EXISTS monitors (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, platform TEXT NOT NULL, target TEXT NOT NULL,
  label TEXT, params TEXT, interval_hours REAL DEFAULT 24, auto_transcribe INTEGER DEFAULT 0,
  max_items INTEGER DEFAULT 20, enabled INTEGER DEFAULT 1, last_run REAL, next_run REAL,
  last_new INTEGER, created REAL);

CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, platform TEXT, title TEXT, params TEXT,
  status TEXT DEFAULT 'queued', total INTEGER DEFAULT 0, done INTEGER DEFAULT 0,
  failed INTEGER DEFAULT 0, new_count INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0,
  cost_cny REAL DEFAULT 0, log TEXT DEFAULT '[]', error TEXT, monitor_id INTEGER,
  created REAL, started REAL, finished REAL);

CREATE TABLE IF NOT EXISTS style_reports (
  id INTEGER PRIMARY KEY, author_pk INTEGER NOT NULL, job_id INTEGER, model TEXT, n_items INTEGER,
  n_cut INTEGER, summary TEXT, scores TEXT, meta TEXT, stats TEXT, report TEXT, path TEXT,
  in_tokens INTEGER, out_tokens INTEGER, cost_usd REAL, created REAL);
CREATE INDEX IF NOT EXISTS idx_style_author ON style_reports(author_pk);

CREATE TABLE IF NOT EXISTS calls (
  id INTEGER PRIMARY KEY, job_id INTEGER, provider TEXT, endpoint TEXT,
  cost_usd REAL, ok INTEGER, ms INTEGER, ts REAL, error TEXT);
"""


def boot_config() -> dict:
    if BOOT_FILE.exists():
        return json.loads(BOOT_FILE.read_text())
    return {}


def save_boot_config(cfg: dict):
    BOOT.mkdir(parents=True, exist_ok=True)
    BOOT_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))


def data_root() -> Path:
    """采集结果的根目录：环境变量 > ~/.guanzi-monitor/config.json > ~/观自行深监控台。"""
    p = os.environ.get("GM_DATA") or os.environ.get("DEI_WB_DATA") or boot_config().get("data_root") or str(DEFAULT_DATA)
    return Path(p).expanduser()


def db_path() -> Path:
    if os.environ.get("DEI_WB_DEMO"):
        return BOOT / "demo.db"
    return data_root() / "_工作台" / "workbench.db"


_local = threading.local()
_lock = threading.RLock()


def conn() -> sqlite3.Connection:
    c = getattr(_local, "c", None)
    if c is None:
        p = db_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(p, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        _local.c = c
    return c


def init():
    c = conn()
    c.executescript(SCHEMA)
    c.commit()


def q(sql, args=()):
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def q1(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def x(sql, args=()):
    with _lock:
        c = conn()
        cur = c.execute(sql, args)
        if not getattr(_local, "in_tx", 0):
            c.commit()
        return cur.lastrowid


@contextmanager
def tx():
    """批量写：期间的 x() 不逐条提交，结束时一次提交（外接盘上逐条 fsync 很慢）。"""
    with _lock:
        _local.in_tx = getattr(_local, "in_tx", 0) + 1
        try:
            yield
        finally:
            _local.in_tx -= 1
            if _local.in_tx == 0:
                conn().commit()


def now() -> float:
    return time.time()


# ---------- settings ----------
DEFAULT_SETTINGS = {
    "provider": "monid",               # monid | tikhub
    "douyin_search_engine": "index",   # index=抖音指数视频搜索 | search=抖音站内搜索
    "monid_token": "",
    "monid_api_base": "https://api.monid.ai",
    "tikhub_token": "",
    "dashscope_api_key": "",
    "dashscope_model": "paraformer-v2",
    "dasheng_uid": "",
    "dasheng_key": "",
    "anthropic_api_key": "",
    "style_model": "claude-opus-5-5",  # 文风 DNA 用的模型
    "style_effort": "high",
    "usd_cny": 7.2,
    "confirm_over_items": 20,          # 超过这么多条先确认（铁律：计费前先报数）
    "default_limit": 20,
    "profile_name": "",
    "profile_avatar": "",
    "profile_bio": "",
}
SECRET_KEYS = {"monid_token", "tikhub_token", "dashscope_api_key", "dasheng_key", "anthropic_api_key"}


def get_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    for r in q("SELECT key, value FROM settings"):
        try:
            s[r["key"]] = json.loads(r["value"])
        except Exception:
            s[r["key"]] = r["value"]
    return s


def set_settings(d: dict):
    for k, v in d.items():
        if k in DEFAULT_SETTINGS:
            x("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              (k, json.dumps(v, ensure_ascii=False)))


def public_settings() -> dict:
    """给前端看的设置：密钥只显示是否已填和尾号。"""
    s = get_settings()
    for k in SECRET_KEYS:
        v = s.get(k) or ""
        s[k] = {"set": bool(v), "tail": v[-4:] if v else ""}
    s["data_root"] = str(data_root())
    s["db_path"] = str(db_path())
    s["demo"] = bool(os.environ.get("DEI_WB_DEMO"))
    s["has_dei_capture"] = (Path.home() / ".claude/skills/dei-capture/config.json").exists()
    s["version"] = VERSION
    s["ready"] = bool(s["monid_token"]["set"] if s.get("provider") != "tikhub" else s["tikhub_token"]["set"])
    return s
