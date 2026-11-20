"""网页版：用户填的 API Key 加密后再存进数据库。

主密钥只放在服务器的 systemd 环境变量 GM_SECRET_KEY 里（/etc/guanzi-monitor/secret.env，root 600），
不在 /srv/guanzi 里，所以数据库或备份包单独泄露时 Key 也读不出来。
本地版不加密：数据本来就只在用户自己电脑上。

生成主密钥：python -m guanzi_monitor.secretbox new-key
"""
from __future__ import annotations

import os
import sys

PREFIX = "enc:v1:"
_fernet = None


class SecretError(RuntimeError):
    pass


def _f():
    global _fernet
    if _fernet is None:
        key = os.environ.get("GM_SECRET_KEY", "").strip()
        if not key:
            raise SecretError("网页版缺少主密钥 GM_SECRET_KEY（见 secretbox.py 说明），不能读写 API Key")
        try:
            from cryptography.fernet import Fernet
        except ImportError as e:  # pragma: no cover
            raise SecretError("网页版需要 cryptography：pip install '.[server]'") from e
        _fernet = Fernet(key.encode())
    return _fernet


def check():
    """启动时调用：网页版没配好主密钥就直接退出，不要带着明文跑。"""
    _f()


def is_encrypted(v) -> bool:
    return isinstance(v, str) and v.startswith(PREFIX)


def encrypt(v: str) -> str:
    if not v or is_encrypted(v):
        return v
    return PREFIX + _f().encrypt(v.encode()).decode()


def decrypt(v):
    if not is_encrypted(v):
        return v
    from cryptography.fernet import InvalidToken
    try:
        return _f().decrypt(v[len(PREFIX):].encode()).decode()
    except InvalidToken:
        # 主密钥换过或数据损坏：当成没填，让用户重新填，而不是把密文当 Key 发出去
        print("[secretbox] 有一个 Key 解不开（主密钥不匹配），按未填处理", file=sys.stderr)
        return ""


if __name__ == "__main__":
    if sys.argv[1:] == ["new-key"]:
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
    else:
        print(__doc__)
