"""TikHub 直连渠道（备用）。充值后在设置页切换。

视频号映射与 Monid 共用（Monid 本来就是代理的 TikHub 接口）；抖音、小红书是 TikHub 原始结构，宽松映射。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .base import Page, Provider, ProviderError, find, first_str, num, ts
from . import sph_map

API = "https://api.tikhub.io"


class TikHubProvider(Provider):
    name = "tikhub"
    PRICES = {("douyin", "video"): 0.001, ("douyin", "search"): 0.01, ("douyin", "profile"): 0.001,
              ("douyin", "posts"): 0.001, ("xhs", "video"): 0.01, ("xhs", "search"): 0.01,
              ("xhs", "profile"): 0.01, ("xhs", "posts"): 0.01, ("sph", "video"): 0.01,
              ("sph", "search"): 0.01, ("sph", "profile"): 0.01, ("sph", "posts"): 0.01}

    def call(self, path, params=None, body=None, est=0.01):
        token = (self.s.get("tikhub_token") or "").strip()
        if not token:
            raise ProviderError("没有填 TikHub Token", fatal=True)
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                              "User-Agent": "guanzi-monitor"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                j = json.loads(r.read())
            self.on_call("tikhub", path, est, True, int((time.time() - t0) * 1000), None)
            return j
        except urllib.error.HTTPError as e:
            txt = e.read().decode(errors="ignore")[:300]
            self.on_call("tikhub", path, 0, False, int((time.time() - t0) * 1000), txt)
            raise ProviderError(f"TikHub {e.code}：{txt}", fatal=e.code in (401, 402, 403))

    def test(self):
        j = self.call("/api/v1/tikhub/user/get_user_info", est=0)
        return {"ok": True, "balance_usd": find(j, "balance"), "raw": j.get("data")}

    # ---- 抖音 ----
    def video(self, platform, ref):
        if platform == "douyin":
            if ref.get("content_id"):
                j = self.call("/api/v1/douyin/app/v3/fetch_one_video_v2", {"aweme_id": ref["content_id"]}, est=0.001)
            else:
                j = self.call("/api/v1/douyin/app/v3/fetch_one_video_by_share_url", {"share_url": ref["url"]}, est=0.001)
            return aweme_item(find(j, "aweme_detail") or find(j, "aweme_details") or {})
        if platform == "xhs":
            j = self.call("/api/v1/xiaohongshu/app_v2/get_video_note_detail" if ref.get("is_video")
                          else "/api/v1/xiaohongshu/app_v2/get_image_note_detail", {"note_id": ref["content_id"]})
            return xhs_raw_item(find(j, "note_list") or find(j, "data") or {})
        if platform == "sph":
            body = {"raw": False, **{k: ref[k] for k in ("object_id", "export_id", "share_url") if ref.get(k)}}
            return sph_map.item(self.call("/api/v1/wechat_channels/v2/fetch_video_detail", body=body))
        raise ProviderError(platform)

    def search(self, platform, keyword, sort="relevance", days=0, cursor=None, opts=None):
        cur = cursor or {}
        if platform == "douyin":
            body = {"keyword": keyword, "sort_type": {"relevance": "0", "likes": "1", "newest": "2"}[sort],
                    "publish_time": str(days or 0), "content_type": "1", "cursor": cur.get("cursor") or 0,
                    "search_id": cur.get("search_id") or "", "backtrace": cur.get("backtrace") or ""}
            j = self.call("/api/v1/douyin/search/fetch_video_search_v2", body=body)
            d = j.get("data") or {}
            rows = _awemes(d)
            return Page([aweme_item(a) for a in rows],
                        {"cursor": find(d, "cursor"), "search_id": find(d, "search_id"), "backtrace": find(d, "backtrace")},
                        bool(find(d, "has_more")))
        if platform == "xhs":
            p = {"keyword": keyword, "sort_type": {"relevance": "general", "likes": "popularity_descending",
                                                   "newest": "time_descending"}[sort], "page": cur.get("page", 1)}
            j = self.call("/api/v1/xiaohongshu/app_v2/search_notes", p)
            rows = [i.get("note") or i for i in (find(j, "items") or []) if isinstance(i, dict)]
            return Page([xhs_raw_item(r) for r in rows if r.get("id")], {"page": p["page"] + 1}, bool(rows))
        if platform == "sph":
            body = {"keyword": keyword, "raw": False, "sort": {"relevance": 0, "newest": 1, "likes": 2}[sort],
                    "publish_time": {0: 0, 1: 1, 7: 2, 180: 3}.get(int(days or 0), 0)}
            if cur.get("cursor"):
                body["cursor"] = cur["cursor"]
            items, nxt = sph_map.items(self.call("/api/v1/wechat_search/v2/fetch_search_videos", body=body))
            return Page(items, {"cursor": nxt} if nxt else None, bool(nxt))
        raise ProviderError(platform)

    def profile(self, platform, ref):
        if platform == "douyin":
            j = self.call("/api/v1/douyin/web/handler_user_profile", {"sec_user_id": ref.get("sec_uid") or ref["author_id"]}, est=0.001)
            u = find(j, "user") or {}
            sec = u.get("sec_uid")
            return {"platform": "douyin", "author_id": sec, "sec_uid": sec, "unique_id": u.get("unique_id") or u.get("short_id"),
                    "nickname": u.get("nickname"), "avatar": first_str(u.get("avatar_larger"), u.get("avatar_thumb")),
                    "bio": u.get("signature"), "url": f"https://www.douyin.com/user/{sec}",
                    "followers": num(u.get("follower_count")), "following": num(u.get("following_count")),
                    "likes": num(u.get("total_favorited")), "posts": num(u.get("aweme_count"))}
        if platform == "xhs":
            j = self.call("/api/v1/xiaohongshu/app_v2/get_user_info", {"user_id": ref["author_id"]})
            d = find(j, "data") or {}
            return {"platform": "xhs", "author_id": ref["author_id"], "nickname": find(d, "nickname"),
                    "avatar": find(d, "images", "imageb"), "bio": find(d, "desc"),
                    "followers": num(find(d, "fans")), "following": num(find(d, "follows")),
                    "likes": num(find(d, "liked")), "posts": num(find(d, "ndiscovery"))}
        if platform == "sph":
            return sph_map.author(self.call("/api/v1/wechat_channels/v2/fetch_user_profile",
                                            body={"username": ref.get("username") or ref["author_id"], "raw": False}))
        raise ProviderError(platform)

    def posts(self, platform, ref, cursor=None):
        cur = cursor or {}
        if platform == "douyin":
            j = self.call("/api/v1/douyin/app/v3/fetch_user_post_videos",
                          {"sec_user_id": ref.get("sec_uid") or ref["author_id"], "max_cursor": cur.get("cursor") or 0, "count": 20},
                          est=0.001)
            d = j.get("data") or {}
            return Page([aweme_item(a) for a in d.get("aweme_list") or []], {"cursor": d.get("max_cursor")}, bool(d.get("has_more")))
        if platform == "xhs":
            p = {"user_id": ref["author_id"]}
            if cur.get("cursor"):
                p["cursor"] = cur["cursor"]
            j = self.call("/api/v1/xiaohongshu/app_v2/get_user_posted_notes", p)
            rows = find(j, "notes") or []
            return Page([xhs_raw_item(r) for r in rows], {"cursor": rows[-1].get("cursor") if rows else None}, bool(find(j, "has_more")))
        if platform == "sph":
            body = {"username": ref.get("username") or ref["author_id"], "raw": False}
            if cur.get("cursor"):
                body["last_buffer"] = cur["cursor"]
            items, nxt = sph_map.items(self.call("/api/v1/wechat_channels/v2/fetch_user_videos", body=body))
            return Page(items, {"cursor": nxt} if nxt else None, bool(nxt))
        raise ProviderError(platform)


def _awemes(d):
    rows = []
    for x in (d.get("data") or d.get("business_data") or []):
        a = x.get("aweme_info") or (x.get("data") or {}).get("aweme_info") if isinstance(x, dict) else None
        if a:
            rows.append(a)
    return rows or (find(d, "aweme_list") or [])


def aweme_item(a):
    st = a.get("statistics") or {}
    au = a.get("author") or {}
    v = a.get("video") or {}
    vid = str(a.get("aweme_id") or "")
    return {"platform": "douyin", "content_id": vid, "url": f"https://www.douyin.com/video/{vid}",
            "title": (a.get("desc") or "").split("\n")[0][:120], "caption": a.get("desc") or "",
            "type": "image" if a.get("images") else "video", "published_at": ts(a.get("create_time")),
            "duration_s": (num(v.get("duration")) or 0) / 1000 or None,
            "cover": first_str(v.get("cover"), v.get("origin_cover")), "media_url": first_str(v.get("play_addr")),
            "tags": [t.get("hashtag_name") for t in (a.get("text_extra") or []) if isinstance(t, dict) and t.get("hashtag_name")],
            "views": num(st.get("play_count")) or None, "likes": num(st.get("digg_count")),
            "comments": num(st.get("comment_count")), "saves": num(st.get("collect_count")), "shares": num(st.get("share_count")),
            "author": {"platform": "douyin", "author_id": au.get("sec_uid"), "sec_uid": au.get("sec_uid"),
                       "unique_id": au.get("unique_id") or au.get("short_id"), "nickname": au.get("nickname"),
                       "avatar": first_str(au.get("avatar_thumb"))},
            "extra": {}}


def xhs_raw_item(n):
    if isinstance(n, list):
        n = n[0] if n else {}
    u = n.get("user") or {}
    nid = str(n.get("id") or n.get("note_id") or "")
    return {"platform": "xhs", "content_id": nid, "url": f"https://www.xiaohongshu.com/explore/{nid}",
            "title": n.get("title") or n.get("display_title") or "", "caption": n.get("desc") or "",
            "type": "video" if n.get("type") == "video" else "image", "published_at": ts(n.get("time") or n.get("create_time")),
            "duration_s": None, "cover": first_str(find(n, "url_default", "url")), "media_url": None, "tags": [],
            "views": None, "likes": num(n.get("liked_count") or n.get("likes")), "comments": num(n.get("comments_count")),
            "saves": num(n.get("collected_count")), "shares": num(n.get("shared_count")),
            "author": {"platform": "xhs", "author_id": u.get("userid") or u.get("user_id") or u.get("id"),
                       "nickname": u.get("nickname") or u.get("name"), "avatar": u.get("images") or u.get("image")},
            "extra": {}}
