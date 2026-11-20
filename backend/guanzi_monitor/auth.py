"""网页版账号：邀请码注册、账号密码登录、会话 Cookie、给 Agent 用的访问令牌。

账号库单独一个文件 SERVER_ROOT/accounts.db，和用户的采集数据分开。
只在 GM_MODE=server 时用到；本地版完全不碰。
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time

from . import db

SESSION_DAYS = 30
COOKIE = "gm_session"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL COLLATE NOCASE, pw_hash TEXT NOT NULL,
  is_admin INTEGER DEFAULT 0, invite_code TEXT, api_token_hash TEXT, api_token_tail TEXT,
  disabled INTEGER DEFAULT 0, created REAL, last_login REAL);
CREATE TABLE IF NOT EXISTS invites (
  code TEXT PRIMARY KEY, note TEXT, is_admin INTEGER DEFAULT 0, created REAL, used_by INTEGER, used_at REAL);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created REAL, expires REAL, ua TEXT);
"""

_lock = threading.RLock()
_local = threading.local()


class AuthError(Exception):
    pass


def _conn() -> sqlite3.Connection:
    c = getattr(_local, "c", None)
    if c is None:
        db.SERVER_ROOT.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(db.SERVER_ROOT / "accounts.db", timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        cols = {r[1] for r in c.execute("PRAGMA table_info(invites)")}
        for col, typ in (("sent_to", "TEXT"), ("sent_at", "REAL"), ("expires", "REAL")):   # v0.1.3 新增
            if col not in cols:
                c.execute(f"ALTER TABLE invites ADD COLUMN {col} {typ}")
        c.commit()
        _local.c = c
    return c


def _q1(sql, a=()):
    r = _conn().execute(sql, a).fetchone()
    return dict(r) if r else None


def _q(sql, a=()):
    return [dict(r) for r in _conn().execute(sql, a).fetchall()]


def _x(sql, a=()):
    with _lock:
        c = _conn()
        cur = c.execute(sql, a)
        c.commit()
        return cur.lastrowid


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ---------- 密码 ----------
def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_pw(pw: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1)
        return hmac.compare_digest(got.hex(), h)
    except Exception:  # noqa
        return False


# ---------- 邀请码 ----------
def create_invite(note: str = "", is_admin: bool = False, days: float | None = None) -> str:
    """days：有效期（天），不填就一直有效。"""
    code = "GZ-" + secrets.token_hex(3).upper()
    exp = time.time() + float(days) * 86400 if days else None
    _x("INSERT INTO invites(code, note, is_admin, created, expires) VALUES(?,?,?,?,?)",
       (code, note, int(is_admin), time.time(), exp))
    return code


def update_invite(code: str, sent_to: str | None = None, mark_sent: bool = False):
    """登记发给了谁；mark_sent=True 时记下发出时间（复制邀请话术时自动调用）。"""
    inv = _q1("SELECT * FROM invites WHERE code=?", (code,))
    if not inv:
        raise AuthError("没有这个邀请码")
    if sent_to is not None:
        _x("UPDATE invites SET sent_to=? WHERE code=?", (sent_to.strip()[:40], code))
    if mark_sent and not inv.get("sent_at"):
        _x("UPDATE invites SET sent_at=? WHERE code=?", (time.time(), code))
    return _q1("SELECT * FROM invites WHERE code=?", (code,))


def delete_invite(code: str):
    """作废没用过的邀请码（用过的不能删，账号还挂着它）。"""
    inv = _q1("SELECT * FROM invites WHERE code=?", (code,))
    if not inv:
        raise AuthError("没有这个邀请码")
    if inv["used_by"]:
        raise AuthError("已经用过的邀请码不能作废")
    _x("DELETE FROM invites WHERE code=?", (code,))


def list_invites():
    return _q("""SELECT i.*, u.username used_by_name FROM invites i LEFT JOIN users u ON u.id=i.used_by
                 ORDER BY i.created DESC""")


# ---------- 防暴力尝试 ----------
# 15 分钟内：同一 IP 登录失败 10 次、同一账号失败 20 次、同一 IP 注册失败 10 次（猜邀请码），就先挡住
WINDOW = 15 * 60
LIMITS = {"ip": 10, "user": 20, "reg": 10}
_fails: dict[str, list[float]] = {}
_flock = threading.Lock()


def _keys(kind_vals: dict) -> list[str]:
    return [f"{k}:{v}" for k, v in kind_vals.items() if v]


def _throttle(kind_vals: dict):
    now = time.time()
    with _flock:
        for key in _keys(kind_vals):
            ts = [t for t in _fails.get(key, []) if now - t < WINDOW]
            _fails[key] = ts
            if len(ts) >= LIMITS[key.split(":", 1)[0]]:
                raise AuthError("尝试次数太多，请 15 分钟后再试")


def _failed(kind_vals: dict):
    with _flock:
        for key in _keys(kind_vals):
            _fails.setdefault(key, []).append(time.time())
        if len(_fails) > 5000:   # 防止内存被刷爆：清掉过期的
            now = time.time()
            for k in [k for k, v in _fails.items() if not v or now - v[-1] > WINDOW]:
                del _fails[k]


# ---------- 注册 / 登录 ----------
USER_RE = re.compile(r"^[A-Za-z0-9_一-鿿]{2,20}$")


def register(username: str, password: str, code: str, ip: str = "") -> dict:
    username, code = (username or "").strip(), (code or "").strip().upper()
    _throttle({"reg": ip})
    if not USER_RE.match(username):
        raise AuthError("账号 2–20 位，只能用中文、字母、数字、下划线")
    if len(password or "") < 8:
        raise AuthError("密码至少 8 位")
    with _lock:
        inv = _q1("SELECT * FROM invites WHERE code=?", (code,))
        if not inv or inv["used_by"]:
            _failed({"reg": ip})
            raise AuthError("邀请码不对" if not inv else "这个邀请码已经用过了")
        if inv.get("expires") and inv["expires"] < time.time():
            raise AuthError("这个邀请码已过期，请联系发码的人要一个新的")
        if _q1("SELECT id FROM users WHERE username=?", (username,)):
            raise AuthError("这个账号名已经有人用了")
        uid = _x("INSERT INTO users(username, pw_hash, is_admin, invite_code, created) VALUES(?,?,?,?,?)",
                 (username, hash_pw(password), inv["is_admin"], code, time.time()))
        _x("UPDATE invites SET used_by=?, used_at=? WHERE code=?", (uid, time.time(), code))
    return get_user(uid)


def login(username: str, password: str, ua: str = "", ip: str = "") -> tuple[str, dict]:
    who = {"ip": ip, "user": (username or "").strip().lower()}
    _throttle(who)
    u = _q1("SELECT * FROM users WHERE username=?", ((username or "").strip(),))
    if not u or not check_pw(password or "", u["pw_hash"]):
        _failed(who)
        time.sleep(0.5)  # 拖慢暴力尝试
        raise AuthError("账号或密码不对")
    if u["disabled"]:
        raise AuthError("这个账号已停用，请联系管理员")
    tok = secrets.token_urlsafe(32)
    _x("INSERT INTO sessions(token_hash, user_id, created, expires, ua) VALUES(?,?,?,?,?)",
       (_sha(tok), u["id"], time.time(), time.time() + SESSION_DAYS * 86400, (ua or "")[:200]))
    _x("UPDATE users SET last_login=? WHERE id=?", (time.time(), u["id"]))
    return tok, get_user(u["id"])


def logout(tok: str):
    _x("DELETE FROM sessions WHERE token_hash=?", (_sha(tok),))


def user_from_session(tok: str | None) -> dict | None:
    if not tok:
        return None
    s = _q1("SELECT * FROM sessions WHERE token_hash=? AND expires>?", (_sha(tok), time.time()))
    if not s:
        return None
    u = get_user(s["user_id"])
    return u if u and not u["disabled"] else None


def user_from_api_token(tok: str | None) -> dict | None:
    if not tok:
        return None
    u = _q1("SELECT id FROM users WHERE api_token_hash=? AND disabled=0", (_sha(tok),))
    return get_user(u["id"]) if u else None


def new_api_token(uid: int) -> str:
    tok = "gzm_" + secrets.token_urlsafe(32)
    _x("UPDATE users SET api_token_hash=?, api_token_tail=? WHERE id=?", (_sha(tok), tok[-4:], uid))
    return tok


def clear_api_token(uid: int):
    _x("UPDATE users SET api_token_hash=NULL, api_token_tail=NULL WHERE id=?", (uid,))


def change_password(uid: int, old: str, new: str):
    u = _q1("SELECT * FROM users WHERE id=?", (uid,))
    if not u or not check_pw(old or "", u["pw_hash"]):
        raise AuthError("原密码不对")
    if len(new or "") < 8:
        raise AuthError("新密码至少 8 位")
    _x("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(new), uid))
    _x("DELETE FROM sessions WHERE user_id=?", (uid,))


def reset_password(username: str, new: str):
    u = _q1("SELECT id FROM users WHERE username=?", (username,))
    if not u:
        raise AuthError("没有这个账号")
    _x("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(new), u["id"]))
    _x("DELETE FROM sessions WHERE user_id=?", (u["id"],))


def get_user(uid: int) -> dict | None:
    u = _q1("""SELECT id, username, is_admin, disabled, created, last_login, api_token_tail
               FROM users WHERE id=?""", (uid,))
    if u:
        u["is_admin"] = bool(u["is_admin"])
        u["disabled"] = bool(u["disabled"])
    return u


def list_users():
    return _q("SELECT id, username, is_admin, disabled, created, last_login, invite_code FROM users ORDER BY id")


def active_user_ids() -> list[int]:
    return [r["id"] for r in _q("SELECT id FROM users WHERE disabled=0")]
