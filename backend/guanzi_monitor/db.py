"""SQLite 存储。一条内容只存一份（平台 + 原生 ID 唯一），会变的数据进快照表，来源进来源表。"""
from __future__ import annotations

import contextvars
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
VERSION = "0.1.2"

# 网页版：GM_MODE=server 时要求登录，每个用户一个文件夹、一个数据库（天然隔离，不用改表结构）
SERVER = os.environ.get("GM_MODE") == "server"
SERVER_ROOT = Path(os.environ.get("GM_SERVER_ROOT") or "/srv/guanzi")
_uid: contextvars.ContextVar[int | None] = contextvars.ContextVar("gm_uid", default=None)


def current_user() -> int | None:
    return _uid.get()


@contextmanager
def as_user(uid: int | None):
    """在这个代码块里，所有 db / data_root 调用都落到该用户的库。"""
    tok = _uid.set(uid)
    try:
        yield
    finally:
        _uid.reset(tok)


def set_user(uid: int | None):
    return _uid.set(uid)


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
    """采集结果的根目录：环境变量 > ~/.guanzi-monitor/config.json > ~/观自行深监控台。
    网页版：SERVER_ROOT/users/<用户 id>。"""
    if SERVER:
        uid = _uid.get()
        if not uid:
            raise RuntimeError("网页版：当前没有登录用户，不能读写数据")
        return SERVER_ROOT / "users" / str(int(uid))
    p = os.environ.get("GM_DATA") or os.environ.get("DEI_WB_DATA") or boot_config().get("data_root") or str(DEFAULT_DATA)
    return Path(p).expanduser()


def db_path() -> Path:
    if os.environ.get("DEI_WB_DEMO"):
        return BOOT / "demo.db"
    return data_root() / "_工作台" / "workbench.db"


_local = threading.local()
_lock = threading.RLock()


_inited: set[str] = set()


def conn() -> sqlite3.Connection:
    """每个线程、每个库文件一个连接（网页版一个线程会先后服务多个用户）。"""
    p = db_path()
    key = str(p)
    cs = getattr(_local, "cs", None)
    if cs is None:
        cs = _local.cs = {}
    c = cs.get(key)
    if c is None:
        p.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(p, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        with _lock:
            if key not in _inited:
                c.executescript(SCHEMA)
                c.commit()
                _inited.add(key)
        cs[key] = c
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
    # 百炼接口地址。2026-11 实测旧地址仍可用；阿里云新文档改成按业务空间的
    # https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com ，旧地址停用时只改这里
    "dashscope_base_url": "https://dashscope.aliyuncs.com",
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
    if SERVER:
        from . import secretbox
        for k in SECRET_KEYS:
            s[k] = secretbox.decrypt(s.get(k) or "")
    return s


def set_settings(d: dict):
    for k, v in d.items():
        if k in DEFAULT_SETTINGS:
            if SERVER and k in SECRET_KEYS and isinstance(v, str):
                from . import secretbox
                v = secretbox.encrypt(v.strip())
            x("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              (k, json.dumps(v, ensure_ascii=False)))


def encrypt_existing_secrets() -> int:
    """网页版启动时：把当前用户库里还是明文的 Key 改成密文。返回改了几个。"""
    from . import secretbox
    n = 0
    for r in q(f"SELECT key, value FROM settings WHERE key IN ({','.join('?' * len(SECRET_KEYS))})", tuple(SECRET_KEYS)):
        try:
            v = json.loads(r["value"])
        except Exception:
            v = r["value"]
        if isinstance(v, str) and v and not secretbox.is_encrypted(v):
            x("UPDATE settings SET value=? WHERE key=?", (json.dumps(secretbox.encrypt(v)), r["key"]))
            n += 1
    return n


def public_settings() -> dict:
    """给前端看的设置：密钥只显示是否已填和尾号。"""
    s = get_settings()
    for k in SECRET_KEYS:
        v = s.get(k) or ""
        s[k] = {"set": bool(v), "tail": v[-4:] if v else ""}
    s["server"] = SERVER
    s["data_root"] = "云端（你的账号专属空间）" if SERVER else str(data_root())
    s["db_path"] = "" if SERVER else str(db_path())
    s["demo"] = bool(os.environ.get("DEI_WB_DEMO"))
    s["has_dei_capture"] = (not SERVER) and dei_capture_config() is not None
    s["version"] = VERSION
    s["ready"] = bool(s["monid_token"]["set"] if s.get("provider") != "tikhub" else s["tikhub_token"]["set"])
    return s


AGENT_HOMES = (".claude", ".workbuddy", ".codex", ".agents")


def dei_capture_config() -> Path | None:
    """dei-capture 的 config.json：Claude Code / WorkBuddy / Codex / 其他 Agent 的 skills 目录依次找。"""
    for h in AGENT_HOMES:
        p = Path.home() / h / "skills" / "dei-capture" / "config.json"
        if p.exists():
            return p
    return None
