"""把单纯的数字变成能判断的指标（不额外花钱，全部用已有数据算）。

没有播放量，所以一律以「点赞」为分母：
- 收藏率 = 收藏 / 点赞：越高越「干货」，看的人想留着回看、照着做
- 转发率 = 分享 / 点赞：越高越有「社交货币」，看的人愿意转给别人
- 评论率 = 评论 / 点赞：越高越有「话题 / 争议」，适合引互动
- 赞粉比 = 点赞 / 博主粉丝：> 1 说明火出了自己的粉丝盘子（被推荐流量带起来）
- 超常倍数 = 点赞 / 该博主库里平均点赞：看它在博主自己的作品里是不是异常值
- 日均赞 = 点赞 / 发布天数：新发的高日均才是「正在起量」
"""
from __future__ import annotations

import time

from .. import db


def _r(a, b):
    return round(a / b, 4) if a is not None and b else None


def add(rows: list[dict]) -> list[dict]:
    if not rows:
        return rows
    apks = sorted({r["author_pk"] for r in rows if r.get("author_pk")})
    fans, avg = {}, {}
    if apks:
        ph = ",".join("?" * len(apks))
        for x in db.q(f"""SELECT author_pk, followers FROM author_snapshots WHERE id IN (
                          SELECT MAX(id) FROM author_snapshots WHERE author_pk IN ({ph}) AND followers IS NOT NULL
                          GROUP BY author_pk)""", apks):
            fans[x["author_pk"]] = x["followers"]
        for x in db.q(f"""SELECT author_pk, AVG(likes) a, COUNT(*) n FROM contents
                          WHERE author_pk IN ({ph}) AND likes IS NOT NULL GROUP BY author_pk""", apks):
            if x["n"] >= 5:  # 少于 5 条算出来的平均没意义
                avg[x["author_pk"]] = x["a"]
    now = time.time()
    for r in rows:
        likes = r.get("likes")
        f = fans.get(r.get("author_pk")) or (r.get("extra") or {}).get("author_fans")
        age = (now - r["published_at"]) / 86400 if r.get("published_at") else None
        a = avg.get(r.get("author_pk"))
        r["ins"] = {
            "save_rate": _r(r.get("saves"), likes),
            "share_rate": _r(r.get("shares"), likes),
            "comment_rate": _r(r.get("comments"), likes),
            "fans": f,
            "like_fan": _r(likes, f),
            "multiple": round(likes / a, 2) if likes is not None and a else None,
            "age_days": round(age, 1) if age is not None else None,
            "per_day": round(likes / max(age, 0.5)) if likes is not None and age is not None else None,
        }
    return rows


def author_baseline(contents: list[dict]) -> dict:
    """博主自己的基线：用来判断单条作品是高于还是低于他平时的水平。"""
    def med(k):
        v = sorted(c["ins"][k] for c in contents if c.get("ins", {}).get(k) is not None)
        return v[len(v) // 2] if v else None
    return {"save_rate": med("save_rate"), "share_rate": med("share_rate"), "comment_rate": med("comment_rate"),
            "per_day": med("per_day")}
