"""演示渠道：不联网、不花钱，生成假数据，只在 DEI_WB_DEMO=1 时启用（独立的 demo.db）。"""
from __future__ import annotations

import hashlib
import random
import time

from .base import Page, Provider

NAMES = ["AI 办公研究所", "效率小林", "职场老周说", "Excel 女王", "PPT 设计师阿哲", "数据分析 Joyce"]
TOPICS = ["3 分钟学会用 AI 写周报", "这个 AI 工具让我每天早下班 2 小时", "别再手动做表格了",
          "用 Kimi 一键生成 PPT", "老板夸我的汇报其实是 AI 写的", "AI 办公的 5 个误区", "DeepSeek 新功能实测",
          "打工人必备的 AI 提示词", "一个人顶一个团队的工作流", "我用 AI 做了 100 条短视频"]


def _rng(*k):
    return random.Random(int(hashlib.md5("|".join(map(str, k)).encode()).hexdigest()[:8], 16))


def _author(platform, i):
    return {"platform": platform, "author_id": f"{platform}_author_{i}", "sec_uid": f"MS4wDEMO{i}",
            "nickname": NAMES[i % len(NAMES)], "avatar": f"https://api.dicebear.com/9.x/shapes/svg?seed={platform}{i}"}


def _item(platform, seed, ai=None, t_shift=0):
    r = _rng(platform, seed)
    ai = r.randrange(len(NAMES)) if ai is None else ai
    cid = f"{platform[:2]}{abs(hash((platform, seed))) % 10**12}"
    likes = int(r.lognormvariate(7, 1.4))
    title = r.choice(TOPICS)
    drift = 1 + (time.time() - 1.79e9) / 86400 * 0.03  # 每天涨 3%，好看出快照走势
    return {"platform": platform, "content_id": cid, "url": f"https://example.com/{platform}/{cid}",
            "title": title, "caption": title + "\n#AI办公 #效率工具", "type": "video" if platform != "xhs" or r.random() < .5 else "image",
            "published_at": time.time() - r.randrange(1, 30 * 86400) - t_shift, "duration_s": r.randrange(20, 300),
            "cover": f"https://picsum.photos/seed/{cid}/360/480", "media_url": None, "tags": ["AI办公", "效率工具"],
            "views": int(likes * r.uniform(8, 30) * drift) if platform != "xhs" else None, "likes": int(likes * drift),
            "comments": int(likes * r.uniform(.02, .1) * drift), "saves": int(likes * r.uniform(.1, .5) * drift),
            "shares": int(likes * r.uniform(.02, .2) * drift), "author": _author(platform, ai), "extra": {"demo": True}}


class DemoProvider(Provider):
    name = "demo"
    PRICES = {}

    def _bill(self, ep):
        self.on_call("demo", ep, 0.0, True, 300, None)
        time.sleep(0.4)

    def test(self):
        return {"ok": True, "balance_usd": 99.0, "raw": {"demo": True}}

    def video(self, platform, ref):
        self._bill("video")
        return _item(platform, ref.get("url") or ref.get("content_id"))

    def search(self, platform, keyword, sort="relevance", days=0, cursor=None, opts=None):
        self._bill("search")
        page = (cursor or {}).get("page", 0)
        items = [_item(platform, f"{keyword}-{page}-{i}") for i in range(10)]
        if sort == "likes":
            items.sort(key=lambda x: -x["likes"])
        elif sort == "newest":
            items.sort(key=lambda x: -x["published_at"])
        return Page(items, {"page": page + 1}, page < 4)

    def profile(self, platform, ref):
        self._bill("profile")
        i = int(str(ref.get("author_id", "0")).rsplit("_", 1)[-1]) if str(ref.get("author_id", "")).rsplit("_", 1)[-1].isdigit() else 0
        r = _rng("p", platform, i)
        a = _author(platform, i)
        a.update({"bio": "分享 AI 办公技巧，每天进步一点点", "url": "https://example.com/u",
                  "followers": r.randrange(5000, 500000), "following": r.randrange(10, 500),
                  "likes": r.randrange(10000, 9000000), "posts": r.randrange(50, 800)})
        return a

    def posts(self, platform, ref, cursor=None):
        self._bill("posts")
        page = (cursor or {}).get("page", 0)
        aid = str(ref.get("author_id", "x_0"))
        ai = int(aid.rsplit("_", 1)[-1]) if aid.rsplit("_", 1)[-1].isdigit() else 0
        items = [_item(platform, f"{aid}-{page}-{i}", ai=ai, t_shift=page * 10 * 86400) for i in range(10)]
        return Page(sorted(items, key=lambda x: -x["published_at"]), {"page": page + 1}, page < 3)
