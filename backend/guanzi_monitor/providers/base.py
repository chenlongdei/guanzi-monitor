"""渠道适配层的统一接口和统一数据格式。

页面和服务层只认这里的格式，不关心底下是 Monid 还是 TikHub。

Item（一条内容）:
  platform, content_id, url, title, caption, type(video|image), published_at(epoch 秒),
  duration_s, cover, media_url, tags[list], views, likes, comments, saves, shares,
  author{AuthorRef}, extra{}
Author:
  platform, author_id, sec_uid, unique_id, nickname, avatar, verified, bio, url,
  followers, following, likes, posts
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

PLATFORMS = {"douyin": "抖音", "xhs": "小红书", "sph": "视频号"}


class ProviderError(Exception):
    """fatal=True：余额不足、Token 无效这类，整个任务停下，不再继续调用。"""

    def __init__(self, msg, fatal=False):
        super().__init__(msg)
        self.fatal = fatal


@dataclass
class Page:
    items: list = field(default_factory=list)
    next_cursor: object = None
    has_more: bool = False
    extra: dict = field(default_factory=dict)


class Provider:
    name = "base"

    def __init__(self, settings: dict, on_call=None):
        self.s = settings
        # on_call(provider, endpoint, cost_usd, ok, ms, error) —— 记账回调
        self.on_call = on_call or (lambda *a, **k: None)

    # 四个能力 ------------------------------------------------------------
    def video(self, platform: str, ref: dict) -> dict:
        """ref: {url} 或 {content_id, xsec_token, export_id ...}。返回 Item。"""
        raise NotImplementedError

    def search(self, platform: str, keyword: str, sort: str = "relevance", days: int = 0, cursor=None,
               opts: dict | None = None) -> Page:
        """sort: relevance | likes | newest。days: 0 不限 / 1 / 3 / 7 / 30 / 180（各接口取最接近的档）。
        opts: 平台专属筛选，如抖音指数的 label_type / category_id / duration_type。"""
        raise NotImplementedError

    def profile(self, platform: str, author_ref: dict) -> dict:
        """author_ref: {author_id, sec_uid, username ...}。返回 Author。"""
        raise NotImplementedError

    def posts(self, platform: str, author_ref: dict, cursor=None) -> Page:
        raise NotImplementedError

    def media_url(self, platform: str, ref: dict) -> str | None:
        """只在转写时调用：用比 video() 更直接的接口拿可下载的音视频直链。
        返回 None 表示这个渠道没有更好的取法，调用方回退到 video() 刷新。"""
        return None

    def test(self) -> dict:
        raise NotImplementedError

    # 计价（给「先报数」用，单位美元/次） --------------------------------------
    PRICES: dict = {}

    def price(self, platform: str, cap: str) -> float:
        return self.PRICES.get((platform, cap), 0.01)


# ---------- 公共小工具 ----------
def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "")
    try:
        if s.endswith("万") or s.lower().endswith("w"):
            return int(float(s[:-1]) * 10000)
        if s.endswith("亿"):
            return int(float(s[:-1]) * 1e8)
        return int(float(s))
    except ValueError:
        return None


def ts(v):
    """各种时间格式 → epoch 秒。"""
    if v in (None, "", 0):
        return None
    if isinstance(v, (int, float)):
        return float(v / 1000 if v > 1e12 else v)
    s = str(v).strip()
    if s.isdigit():
        return ts(int(s))
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def find(x, *keys):
    """深度找第一个出现的 key。"""
    if isinstance(x, dict):
        for k in keys:
            if k in x and x[k] not in (None, "", [], {}):
                return x[k]
        for v in x.values():
            r = find(v, *keys)
            if r is not None:
                return r
    elif isinstance(x, list):
        for v in x:
            r = find(v, *keys)
            if r is not None:
                return r
    return None


def first_str(*vals):
    for v in vals:
        if isinstance(v, str) and v:
            return v
        if isinstance(v, list) and v and isinstance(v[0], str):
            return v[0]
        if isinstance(v, dict):
            for k in ("url", "url_list", "urlList"):
                if v.get(k):
                    return first_str(v[k])
    return None
