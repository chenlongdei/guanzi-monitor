"""图片中转 + 本地缓存。

- 抖音不少封面、头像是 HEIC，浏览器显示不了 → 转成 JPEG
- 抖音 / 小红书 / 视频号的图片链接会过期、有防盗链 → 第一次看到就缓存到本地，以后一直能看
缓存在 <数据目录>/_工作台/img/，按链接去掉签名参数后的路径做键（同一张图换了签名也命中）。
"""
from __future__ import annotations

import hashlib
import io
import urllib.parse
import urllib.request
from pathlib import Path

from .. import db

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def cache_dir() -> Path:
    p = (db.BOOT / "img_demo") if db.os.environ.get("DEI_WB_DEMO") else db.data_root() / "_工作台" / "img"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _key(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    return hashlib.sha1((u.netloc + u.path).encode()).hexdigest()


def get(url: str) -> tuple[Path, str] | None:
    if not url.startswith("http"):
        return None
    d = cache_dir()
    k = _key(url)
    for ext, mime in ((".jpg", "image/jpeg"), (".png", "image/png"), (".webp", "image/webp"), (".gif", "image/gif"),
                      (".svg", "image/svg+xml")):
        f = d / (k + ext)
        if f.exists():
            return f, mime
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].lower()
    except Exception:  # noqa
        return None
    is_heif = "heic" in ctype or "heif" in ctype or data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftypavif")
    if is_heif or ctype in ("image/avif",):
        try:
            import pillow_heif
            from PIL import Image
            pillow_heif.register_heif_opener()
            try:
                pillow_heif.register_avif_opener()
            except Exception:  # noqa
                pass
            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((720, 720))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
            data, ext, mime = buf.getvalue(), ".jpg", "image/jpeg"
        except Exception:  # noqa
            return None
    else:
        ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/svg+xml": ".svg"}.get(ctype, ".jpg")
        mime = {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml"}.get(ext, "image/jpeg")
    f = d / (k + ext)
    f.write_bytes(data)
    return f, mime
