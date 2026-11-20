"""Monid 渠道（第一期主力）。

抖音、小红书走 anyapi 的规范化接口；视频号走 Monid 代理的 TikHub 接口。全部从 Monid 余额扣费。
接口与价格见 probe/monid_接口参考.md（2026-11-19 inspect）。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .base import Page, Provider, ProviderError, find, first_str, num, ts
from . import sph_map
from .tikhub import xhs_video_url

EP = {
    ("douyin", "video"): ("anyapi", "/douyin.video"),
    ("douyin", "video_tk"): ("tikhub", "/api/v1/douyin/app/v3/fetch_one_video_v2"),
    ("douyin", "search"): ("anyapi", "/douyin.search_videos"),
    ("douyin", "index_search"): ("tikhub", "/api/v1/douyin/index/fetch_item_query"),
    ("douyin", "profile"): ("anyapi", "/douyin.profile"),
    ("douyin", "posts"): ("anyapi", "/douyin.user_posts"),
    ("xhs", "video"): ("anyapi", "/rednote.note"),          # 只有元数据，没有视频地址
    ("xhs", "video_dl"): ("tikhub", "/api/v1/xiaohongshu/app_v2/get_video_note_detail"),  # 转写取直链用
    ("xhs", "search"): ("anyapi", "/rednote.search"),
    ("xhs", "profile"): ("anyapi", "/rednote.profile"),
    ("xhs", "posts"): ("anyapi", "/rednote.user_notes"),
    ("sph", "video"): ("tikhub", "/api/v1/wechat_channels/v2/fetch_video_detail"),
    ("sph", "search"): ("tikhub", "/api/v1/wechat_search/v2/fetch_search_videos"),
    ("sph", "profile"): ("tikhub", "/api/v1/wechat_channels/v2/fetch_user_profile"),
    ("sph", "posts"): ("tikhub", "/api/v1/wechat_channels/v2/fetch_user_videos"),
    ("sph", "id2user"): ("tikhub", "/api/v1/wechat_channels/v2/fetch_channel_id_to_username"),
}


class MonidProvider(Provider):
    name = "monid"
    PRICES = {
        ("douyin", "video"): 0.001, ("douyin", "search"): 0.012, ("douyin", "index_search"): 0.001,
        ("douyin", "profile"): 0.001,
        ("douyin", "posts"): 0.0012, ("xhs", "video"): 0.012, ("xhs", "video_dl"): 0.01, ("xhs", "search"): 0.01,
        ("xhs", "profile"): 0.01, ("xhs", "posts"): 0.01, ("sph", "video"): 0.01,
        ("sph", "search"): 0.01, ("sph", "profile"): 0.01, ("sph", "posts"): 0.01,
    }

    # ---------------- 底层调用 ----------------
    def _http(self, method, path, body=None, timeout=90):
        token = (self.s.get("monid_token") or "").strip()
        if not token:
            raise ProviderError("没有填 Monid Token：到「设置」里填（monid_live_ 开头）", fatal=True)
        base = (self.s.get("monid_api_base") or "https://api.monid.ai").rstrip("/")
        req = urllib.request.Request(base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                              "User-Agent": "guanzi-monitor"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            txt = e.read().decode(errors="ignore")[:300]
            if e.code in (401, 402, 403):
                raise ProviderError(f"Monid {e.code}：Token 无效或余额不足。{txt}", fatal=True)
            raise ProviderError(f"Monid HTTP {e.code}：{txt}")
        except urllib.error.URLError as e:
            raise ProviderError(f"连不上 Monid：{e.reason}")

    def run(self, platform, cap, body=None, query=None, max_wait=240):
        """上游临时故障（5xx、all providers failed、运行 FAILED）自动再试一次；失败的调用 Monid 不扣费。"""
        try:
            return self._run_once(platform, cap, body, query, max_wait)
        except ProviderError as e:
            if e.fatal or not getattr(e, "retryable", False):
                raise
            time.sleep(2)
            return self._run_once(platform, cap, body, query, max_wait)

    def _run_once(self, platform, cap, body=None, query=None, max_wait=240):
        provider, endpoint = EP[(platform, cap)]
        inp = {}
        if body is not None:
            inp["body"] = body
        if query is not None:
            inp["queryParams"] = query
        t0 = time.time()
        try:
            r = self._http("POST", "/v1/run", {"provider": provider, "endpoint": endpoint, "input": inp})
            while r.get("status") in ("READY", "RUNNING", "STOPPING") and time.time() - t0 < max_wait:
                time.sleep(3)
                r = self._http("GET", f"/v1/runs/{r['runId']}", timeout=60)
            status = r.get("status")
            if status == "BLOCKED":
                raise ProviderError(f"Monid 拒绝执行（预算或余额不足）：{r.get('reason')}", fatal=True)
            if status != "COMPLETED":
                e = ProviderError(f"Monid 运行状态 {status}：{str(r.get('reason') or r.get('providerResponse'))[:200]}")
                e.retryable = True
                raise e
            http = (r.get("providerResponse") or {}).get("httpStatus")
            if http and int(http) >= 400:
                err = (r.get("providerResponse") or {}).get("error")
                e = ProviderError(f"{provider}{endpoint} 返回 {http}：{str(err)[:200]}")
                e.retryable = int(http) >= 500 or int(http) == 429
                raise e
            cost = _cost(r)
            self.on_call(f"monid/{provider}", endpoint, cost, True, int((time.time() - t0) * 1000), None)
            return r.get("output")
        except ProviderError as e:
            self.on_call(f"monid/{provider}", endpoint, 0, False, int((time.time() - t0) * 1000), str(e))
            raise

    def test(self):
        b = self._http("GET", "/v1/wallet/balance")
        return {"ok": True, "balance_usd": (b.get("balance") or {}).get("value"), "raw": b}

    # ---------------- 四个能力 ----------------
    def video(self, platform, ref):
        if platform == "douyin":
            return self._douyin_video(ref)
        if platform == "xhs":
            out = self.run("xhs", "video", {"noteId": ref["content_id"]})
            return xhs_item(_data(out))
        if platform == "sph":
            body = {"raw": False}
            for k in ("object_id", "export_id", "object_nonce_id", "share_url"):
                if ref.get(k):
                    body[k] = ref[k]
            if ref.get("url") and "share_url" not in body:
                body["share_url"] = ref["url"]
            out = self.run("sph", "video", body)
            return sph_map.item(out)
        raise ProviderError(f"不支持的平台 {platform}")

    def media_url(self, platform, ref):
        """小红书：anyapi 的 rednote.note 不给视频地址，转写时改走 TikHub 视频笔记详情取 master_url。"""
        if platform == "xhs" and ref.get("content_id"):
            out = self.run("xhs", "video_dl", query={"note_id": ref["content_id"]})
            return xhs_video_url(out)
        return None

    def _douyin_video(self, ref):
        """抖音单条：anyapi（分享链接）→ anyapi（长链接）→ TikHub fetch_one_video_v2（视频 ID）。每层约 $0.001。"""
        aid = ref.get("content_id")
        if not aid and ref.get("url"):
            import re
            from ..services.links import resolve
            m = re.search(r"/(?:video|note)/(\d+)", resolve(ref["url"]))
            aid = m.group(1) if m else None
        tries = []
        if ref.get("url"):
            tries.append(("anyapi", ref["url"]))
        if aid and f"/video/{aid}" not in (ref.get("url") or ""):
            tries.append(("anyapi", f"https://www.douyin.com/video/{aid}"))
        if aid:
            tries.append(("tikhub", aid))
        errs = []
        for kind, arg in tries:
            try:
                if kind == "anyapi":
                    raw = self.run("douyin", "video", {"url": arg})
                    if isinstance(raw, dict) and raw.get("found") is False:
                        raise ProviderError("视频不存在或已删除")
                    it = dy_item(_data(raw))
                else:
                    from .tikhub import aweme_item
                    out = self.run("douyin", "video_tk", query={"aweme_id": arg})
                    it = aweme_item(find(out, "aweme_detail") or {})
                if it.get("content_id"):
                    return it
                errs.append(f"{kind} 没返回视频 ID")
            except ProviderError as e:
                if e.fatal:
                    raise
                errs.append(str(e)[:120])
        raise ProviderError("抖音单条三条路线都失败：" + " ｜ ".join(errs))

    def search(self, platform, keyword, sort="relevance", days=0, cursor=None, opts=None):
        cur = cursor or {}
        opts = opts or {}
        if platform == "douyin" and (opts.get("engine") or self.s.get("douyin_search_engine", "index")) == "index":
            return self.index_search(keyword, sort, days, opts)
        if platform == "douyin":
            body = {"query": keyword, "sort": {"relevance": "relevance", "likes": "most-liked", "newest": "date-posted"}.get(sort, "relevance"),
                    "publishedWithin": int(days or 0)}
            body.update({k: v for k, v in cur.items() if v})
            d = _data(self.run("douyin", "search", body))
            items = [dy_item(x) for x in _list(d, "videos", "posts", "items")]
            return Page(items, {"cursor": d.get("nextCursor"), "searchId": d.get("searchId"), "backtrace": d.get("backtrace")},
                        bool(d.get("hasMore", d.get("nextCursor") is not None)))
        if platform == "xhs":
            body = {"query": keyword, "sort": {"relevance": "general", "likes": "hot", "newest": "time"}.get(sort, "general")}
            if cur.get("cursor"):
                body["cursor"] = cur["cursor"]
            d = _data(self.run("xhs", "search", body))
            items = [xhs_item(x) for x in _list(d, "notes", "items")]
            if days:  # 小红书搜索不能按时间筛选，本地筛
                cutoff = time.time() - days * 86400
                items = [i for i in items if not i["published_at"] or i["published_at"] >= cutoff]
            return Page(items, {"cursor": d.get("nextCursor")}, bool(d.get("hasMore", d.get("nextCursor"))))
        if platform == "sph":
            body = {"keyword": keyword, "raw": False,
                    "sort": {"relevance": 0, "newest": 1, "likes": 2}.get(sort, 0),
                    "publish_time": {0: 0, 1: 1, 7: 2, 180: 3}.get(int(days or 0), 0)}
            if cur.get("cursor"):
                body["cursor"] = cur["cursor"]
            out = self.run("sph", "search", body)
            items, nxt = sph_map.items(out)
            return Page(items, {"cursor": nxt} if nxt else None, bool(nxt))
        raise ProviderError(f"不支持的平台 {platform}")

    def index_search(self, keyword, sort, days, opts):
        """抖音指数视频搜索：一次返回整批（带播放量、视频指数、爆款标签），不翻页。"""
        date_type = 0 if not days else min((3, 7, 30), key=lambda x: abs(x - int(days))) if int(days) <= 30 else 0
        q = {"query": keyword, "date_type": date_type, "category_id": str(opts.get("category_id") or "0"),
             "label_type": int(opts.get("label_type") or 0), "duration_type": int(opts.get("duration_type") or 0)}
        out = self.run("douyin", "index_search", query=q)
        rows = out.get("data") if isinstance(out, dict) else out
        if isinstance(rows, dict):
            rows = find(rows, "list", "items", "data") or []
        rows = rows or []
        items = [dy_index_item(r, i + 1) for i, r in enumerate(rows) if isinstance(r, dict)]
        items = [i for i in items if i["content_id"]]
        if sort == "likes":
            items.sort(key=lambda x: -(x["likes"] or 0))
        elif sort == "newest":
            items.sort(key=lambda x: -(x["published_at"] or 0))
        return Page(items, None, False, {"engine": "index"})

    def profile(self, platform, ref):
        if platform == "douyin":
            return dy_author(_data(self.run("douyin", "profile", {"secUserId": ref.get("sec_uid") or ref["author_id"]})))
        if platform == "xhs":
            return xhs_author(_data(self.run("xhs", "profile", {"userId": ref["author_id"]})))
        if platform == "sph":
            return sph_map.author(self.run("sph", "profile", {"username": self.sph_username(ref), "raw": False}))
        raise ProviderError(f"不支持的平台 {platform}")

    def posts(self, platform, ref, cursor=None):
        cur = cursor or {}
        if platform == "douyin":
            sec = ref.get("sec_uid") or ref["author_id"]
            body = {"secUserId": sec, "limit": 20, "sort": "newest"}
            if cur.get("cursor"):
                body["cursor"] = cur["cursor"]
            d = _data(self.run("douyin", "posts", body))
            items = [dy_item(x) for x in _list(d, "posts", "videos", "items")]
            # 文档提示：可能混进别人的作品
            items = [i for i in items if not i["author"].get("sec_uid") or i["author"]["sec_uid"] == sec]
            return Page(items, {"cursor": d.get("nextCursor")}, bool(d.get("hasMore")))
        if platform == "xhs":
            body = {"userId": ref["author_id"]}
            if cur.get("cursor"):
                body["cursor"] = cur["cursor"]
            d = _data(self.run("xhs", "posts", body))
            return Page([xhs_item(x) for x in _list(d, "notes", "items")], {"cursor": d.get("nextCursor")},
                        bool(d.get("hasMore")))
        if platform == "sph":
            body = {"username": self.sph_username(ref), "raw": False}
            if cur.get("cursor"):
                body["last_buffer"] = cur["cursor"]
            out = self.run("sph", "posts", body)
            items, nxt = sph_map.items(out)
            return Page(items, {"cursor": nxt} if nxt else None, bool(nxt))
        raise ProviderError(f"不支持的平台 {platform}")

    def sph_username(self, ref):
        u = ref.get("username") or ref.get("author_id") or ""
        if u.endswith("@finder"):
            return u
        if u.startswith("sph"):
            out = self.run("sph", "id2user", {"channel_id": u})
            v = find(out, "username")
            if v:
                return v
        return u


# ---------------- 字段映射 ----------------
def _cost(run):
    for path in (("cost", "value"), ("billing", "charged", "value"), ("billing", "amount", "value"),
                 ("billing", "total", "value"), ("billing", "value")):
        v = run
        for k in path:
            v = v.get(k) if isinstance(v, dict) else None
        if isinstance(v, (int, float)):
            return float(v)
    b = run.get("billing")
    if isinstance(b, (int, float)):
        return float(b)
    return 0.0


def _data(out):
    if isinstance(out, dict):
        d = out.get("data", out)
        if isinstance(d, dict) and isinstance(d.get("data"), dict):
            d = d["data"]
        return d if isinstance(d, dict) else {"items": d}
    if isinstance(out, list):
        return {"items": out}
    return {}


def _list(d, *keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, list):
            return v
    return []


def dy_item(x):
    vid = str(x.get("id") or x.get("awemeId") or "")
    images = x.get("images")
    return {
        "platform": "douyin", "content_id": vid,
        "url": x.get("url") or (f"https://www.douyin.com/video/{vid}" if vid else None),
        "title": (x.get("caption") or "").split("\n")[0][:120], "caption": x.get("caption") or "",
        "type": "image" if images else "video",
        "published_at": ts(x.get("createdUtc")), "duration_s": (num(x.get("durationMs")) or 0) / 1000 or None,
        "cover": first_str(x.get("image")), "media_url": first_str(x.get("videoUrl"), x.get("videos")),
        "tags": [t for t in (x.get("hashtags") or []) if isinstance(t, str)],
        "views": num(x.get("views")), "likes": num(x.get("likes")), "comments": num(x.get("comments")),
        "saves": num(x.get("saves")), "shares": num(x.get("shares")),
        "author": {"platform": "douyin", "author_id": x.get("authorSecUserId") or x.get("authorUserId") or x.get("authorUniqueId"),
                   "sec_uid": x.get("authorSecUserId"), "unique_id": x.get("authorUniqueId"),
                   "nickname": x.get("authorNickname"), "avatar": first_str(x.get("authorImage")),
                   "verified": x.get("authorVerified")},
        "extra": {k: x.get(k) for k in ("region", "width", "height") if x.get(k) is not None},
    }


INDEX_LABELS = (("isLowFansButHot", "低粉爆款"), ("isHighLikeRate", "高点赞率"),
                ("isHighPlayOverRate", "高完播率"), ("isHighFansRiseRate", "高涨粉率"))


def dy_index_item(x, rank=None):
    """抖音指数 itemQuery 的一行 → 统一格式。字段名按旧版 keyword_watch 见过的 + 常见变体宽松取。"""
    vid = str(x.get("itemId") or x.get("item_id") or x.get("awemeId") or x.get("id") or "")
    title = x.get("itemTitle") or x.get("title") or x.get("desc") or ""
    labels = [n for k, n in INDEX_LABELS if x.get(k)]
    # 抖音指数不给作者 ID，只有昵称：先用「nick:昵称」占位，之后拿到真 ID 时按昵称合并
    aid = x.get("authorSecUid") or x.get("secUid") or x.get("authorId") or x.get("userId") or \
        (f"nick:{x['nickname']}" if x.get("nickname") else None)
    dur = num(x.get("duration"))
    return {
        "platform": "douyin", "content_id": vid, "url": x.get("url") or (f"https://www.douyin.com/video/{vid}" if vid else None),
        "title": title.split("\n")[0][:120], "caption": title, "type": "video",
        "published_at": ts(x.get("createTime") or x.get("publishTime") or x.get("create_time")),
        "duration_s": (dur / 1000 if dur and dur > 3600 else dur),
        "cover": first_str(x.get("thumbnail"), x.get("itemCover"), x.get("cover")), "media_url": None,
        "tags": labels,
        "views": num(x.get("playCnt") or x.get("play") or x.get("playCount") or x.get("play_cnt")),
        "likes": num(x.get("likeCnt") or x.get("like") or x.get("likes") or x.get("diggCount")),
        "comments": num(x.get("commentCnt") or x.get("comment") or x.get("comments")),
        "saves": num(x.get("collectCnt") or x.get("collect")),
        "shares": num(x.get("shareCnt") or x.get("share") or x.get("shares")),
        "author": {"platform": "douyin", "author_id": aid, "sec_uid": x.get("authorSecUid") or x.get("secUid"),
                   "nickname": x.get("nickname") or x.get("authorName") or x.get("authorNickname"),
                   "avatar": first_str(x.get("avatarUrl"), x.get("avatar"))},
        "extra": {k: v for k, v in {"index": num(x.get("index")), "index_rank": rank, "index_labels": labels,
                                    "author_fans": num(x.get("fans") or x.get("followerCnt")), "engine": "抖音指数"}.items()
                  if v not in (None, [], "")},
    }


def dy_author(x):
    sec = x.get("secUserId")
    return {"platform": "douyin", "author_id": sec or x.get("userId"), "sec_uid": sec,
            "unique_id": x.get("uniqueId") or x.get("shortId"), "nickname": x.get("nickname"),
            "avatar": first_str(x.get("image")), "bio": x.get("bio"), "verified": x.get("verified"),
            "url": f"https://www.douyin.com/user/{sec}" if sec else None,
            "followers": num(x.get("followers")), "following": num(x.get("following")),
            "likes": num(x.get("likes")), "posts": num(x.get("posts"))}


def xhs_item(x):
    nid = str(x.get("noteId") or x.get("id") or "")
    t = (x.get("type") or "").lower()
    return {
        "platform": "xhs", "content_id": nid,
        "url": x.get("url") or (f"https://www.xiaohongshu.com/explore/{nid}" if nid else None),
        "title": x.get("title") or (x.get("description") or "").split("\n")[0][:80],
        "caption": x.get("description") or "", "type": "video" if "video" in t else "image",
        "published_at": ts(x.get("createdUtc")), "duration_s": None,
        "cover": first_str(x.get("image")), "media_url": first_str(x.get("videoUrl")),
        "tags": [t for t in (x.get("tags") or []) if isinstance(t, str)],
        "views": None, "likes": num(x.get("likeCount")), "comments": num(x.get("commentCount")),
        "saves": num(x.get("collectCount")), "shares": num(x.get("shareCount")),
        "author": {"platform": "xhs", "author_id": x.get("authorUserId"), "unique_id": x.get("authorRedId"),
                   "nickname": x.get("authorNickname"), "avatar": first_str(x.get("authorImage")),
                   "verified": x.get("authorVerified")},
        "extra": {k: x.get(k) for k in ("xsecToken", "location", "images") if x.get(k)},
    }


def xhs_author(x):
    uid = x.get("userId")
    return {"platform": "xhs", "author_id": uid, "unique_id": x.get("redId"), "nickname": x.get("nickname"),
            "avatar": first_str(x.get("image")), "bio": x.get("description"), "verified": x.get("verified"),
            "url": x.get("shareUrl") or (f"https://www.xiaohongshu.com/user/profile/{uid}" if uid else None),
            "followers": num(x.get("followers")), "following": num(x.get("following")),
            "likes": (num(x.get("likedCount")) or 0) + (num(x.get("collectedCount")) or 0) or None,
            "posts": num(x.get("postedNotes"))}

