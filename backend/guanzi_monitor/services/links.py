"""把用户粘进来的分享文案 / 链接 / ID 识别成 (平台, 视频引用) 或 (平台, 博主引用)。短链在本地跟一次跳转，不计费。"""
from __future__ import annotations

import re
import urllib.request

URL_RE = re.compile(r"https?://[^\s，。,；;）)】\]\"'<>]+")
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def extract_urls(text: str) -> list[str]:
    out = []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(".!?")
        if u not in out:
            out.append(u)
    return out


def resolve(url: str) -> str:
    """跟一次短链跳转，拿最终地址；失败就原样返回。"""
    if not re.search(r"(v\.douyin\.com|xhslink\.com|b23\.tv|v\.kuaishou\.com)", url):
        return url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.geturl()
    except Exception:
        return url


def platform_of(url: str) -> str | None:
    if re.search(r"douyin\.com|iesdouyin\.com", url):
        return "douyin"
    if re.search(r"xiaohongshu\.com|xhslink\.com", url):
        return "xhs"
    if re.search(r"weixin\.qq\.com|channels\.weixin", url):
        return "sph"
    return None


def parse_video(text: str) -> list[dict]:
    """每行 / 每个链接 → {platform, ref, raw, error}。"""
    res = []
    urls = extract_urls(text)
    if not urls:
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            if re.fullmatch(r"\d{15,21}", line):
                res.append({"platform": "douyin", "ref": {"content_id": line}, "raw": line})
            elif re.fullmatch(r"[0-9a-f]{24}", line):
                res.append({"platform": "xhs", "ref": {"content_id": line}, "raw": line})
            elif line.startswith("export/"):
                res.append({"platform": "sph", "ref": {"export_id": line}, "raw": line})
            else:
                res.append({"platform": None, "ref": {}, "raw": line, "error": "认不出平台：请粘贴分享链接"})
        return res
    for u in urls:
        p = platform_of(u)
        if p == "douyin":
            full = resolve(u)
            m = re.search(r"/(?:video|note)/(\d+)", full) or re.search(r"modal_id=(\d+)", full)
            ref = {"url": u}
            if m:
                ref["content_id"] = m.group(1)
            res.append({"platform": "douyin", "ref": ref, "raw": u})
        elif p == "xhs":
            full = resolve(u)
            m = re.search(r"/(?:explore|discovery/item|item)/([0-9a-f]{24})", full)
            tok = re.search(r"xsec_token=([^&]+)", full)
            if m:
                ref = {"content_id": m.group(1), "url": f"https://www.xiaohongshu.com/explore/{m.group(1)}"}
                if tok:
                    ref["xsec_token"] = tok.group(1)
                res.append({"platform": "xhs", "ref": ref, "raw": u})
            else:
                res.append({"platform": "xhs", "ref": {}, "raw": u, "error": "没从链接里找到笔记 ID"})
        elif p == "sph":
            res.append({"platform": "sph", "ref": {"share_url": u, "url": u}, "raw": u})
        else:
            res.append({"platform": None, "ref": {}, "raw": u, "error": "暂不支持这个平台（支持抖音、小红书、视频号）"})
    return res


def parse_author(text: str, platform_hint: str | None = None) -> dict:
    """博主主页链接 / ID → {platform, ref} 或 {error}。"""
    text = (text or "").strip()
    urls = extract_urls(text)
    if urls:
        u = resolve(urls[0])
        p = platform_of(u) or platform_of(urls[0])
        if p == "douyin":
            m = re.search(r"/user/([A-Za-z0-9_\-]+)", u) or re.search(r"sec_uid=([A-Za-z0-9_\-]+)", u)
            if m:
                return {"platform": "douyin", "ref": {"author_id": m.group(1), "sec_uid": m.group(1)}}
            return {"error": "没从抖音链接里找到博主 ID（要主页链接，不是视频链接）"}
        if p == "xhs":
            m = re.search(r"/user/profile/([0-9a-f]{24})", u)
            if m:
                return {"platform": "xhs", "ref": {"author_id": m.group(1)}}
            return {"error": "没从小红书链接里找到用户 ID"}
        return {"error": "视频号没有主页链接：请粘贴 sph 开头的视频号 ID，或 v2_…@finder"}
    if text.endswith("@finder") or re.fullmatch(r"sph[A-Za-z0-9]+", text):
        return {"platform": "sph", "ref": {"author_id": text, "username": text}}
    if text.startswith("MS4wLjAB"):
        return {"platform": "douyin", "ref": {"author_id": text, "sec_uid": text}}
    if re.fullmatch(r"[0-9a-f]{24}", text):
        return {"platform": "xhs", "ref": {"author_id": text}}
    if platform_hint:
        return {"platform": platform_hint, "ref": {"author_id": text, "sec_uid": text, "username": text}}
    return {"error": "认不出来：请粘贴博主主页链接"}
