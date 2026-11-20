"""转写：媒体直链 → 阿里云 Paraformer → 句子列表 → 入库 + 写 Markdown。

一条内容只转一次（除非 force）。直链拿不到或过期时：先让渠道重新取一次详情，再试大圣去水印。
视频号的视频文件是加密的，第一期不支持转写。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .. import db
from ..providers import PLATFORMS, ProviderError
from . import store

PARAFORMER_CNY_PER_SEC = 0.288 / 3600  # paraformer-v2 录音文件识别：0.288 元/小时


class TranscribeError(Exception):
    pass


class KeyError_(TranscribeError):
    """百炼 Key 本身的问题（无效、没开通模型、欠费）：重取直链也没用，直接停。"""


DASHSCOPE_HINT = {
    "AccessDenied.Unpurchased": "这个百炼 Key 所在的业务空间没开通 Paraformer 语音识别（换主账号的 Key，或在百炼控制台开通/授权该模型）",
    "InvalidApiKey": "百炼 Key 无效（检查是否复制完整、是否已删除）",
    "Arrearage": "阿里云账户欠费，充值后再试",
    "AccessDenied": "百炼拒绝访问：Key 没有这个模型的权限",
}


def _post(url, key, body=None, extra=None):
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **(extra or {})}
    req = urllib.request.Request(url, data=json.dumps(body or {}).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode(errors="ignore")
        try:
            code = json.loads(body_txt).get("code") or ""
        except ValueError:
            code = ""
        hint = DASHSCOPE_HINT.get(code) or next((v for k, v in DASHSCOPE_HINT.items() if code.startswith(k)), "")
        msg = f"阿里云百炼 {e.code} {code}：{hint or body_txt[:160]}"
        if e.code in (401, 403) or code in DASHSCOPE_HINT:
            raise KeyError_(msg)
        raise TranscribeError(msg)


def test_key(s: dict) -> dict:
    """提交一段官方示例音频（几秒，费用可忽略）验证 Key 能不能用 Paraformer。"""
    key = (s.get("dashscope_api_key") or "").strip()
    if not key:
        return {"ok": False, "msg": "没有填百炼 Key"}
    try:
        _post("https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription", key,
              {"model": s.get("dashscope_model") or "paraformer-v2",
               "input": {"file_urls": ["https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/hello_world_female2.wav"]},
               "parameters": {"channel_id": [0]}}, {"X-DashScope-Async": "enable"})
        return {"ok": True, "msg": "可以调用 Paraformer"}
    except TranscribeError as e:
        return {"ok": False, "msg": str(e)}


def paraformer(media_url: str, s: dict, max_wait=1800):
    key = (s.get("dashscope_api_key") or "").strip()
    if not key:
        raise TranscribeError("没有填阿里云百炼 Key（设置页，sk- 开头）")
    base = "https://dashscope.aliyuncs.com"
    resp = _post(base + "/api/v1/services/audio/asr/transcription", key,
                 {"model": s.get("dashscope_model") or "paraformer-v2", "input": {"file_urls": [media_url]},
                  "parameters": {"channel_id": [0], "language_hints": ["zh", "en"]}},
                 {"X-DashScope-Async": "enable"})
    task = (resp.get("output") or {}).get("task_id")
    if not task:
        raise TranscribeError(f"提交转写失败：{json.dumps(resp, ensure_ascii=False)[:200]}")
    t0 = time.time()
    while time.time() - t0 < max_wait:
        out = _post(f"{base}/api/v1/tasks/{task}", key).get("output") or {}
        st = out.get("task_status")
        if st == "SUCCEEDED":
            res = (out.get("results") or [{}])[0]
            if res.get("subtask_status") != "SUCCEEDED":
                raise TranscribeError(f"{res.get('code')}: {res.get('message', '')}")
            with urllib.request.urlopen(res["transcription_url"], timeout=120) as r:
                data = json.loads(r.read())
            tr = (data.get("transcripts") or [{}])[0]
            cues = [[round(x.get("begin_time", 0) / 1000, 1), x.get("text", "")] for x in tr.get("sentences", [])]
            if not cues and tr.get("text"):
                cues = [[0.0, tr["text"]]]
            ms = (data.get("properties") or {}).get("original_duration_in_milliseconds")
            return cues, (ms / 1000 if ms else None)
        if st in ("FAILED", "CANCELED", "UNKNOWN"):
            raise TranscribeError(f"转写任务失败：{json.dumps(out, ensure_ascii=False)[:200]}")
        time.sleep(4)
    raise TranscribeError("转写超时")


def dasheng(url: str, s: dict) -> str | None:
    uid, key = s.get("dasheng_uid"), s.get("dasheng_key")
    if not (uid and key and url):
        return None
    form = urllib.parse.urlencode({"type": "dsp", "uid": uid, "key": key, "url": url}).encode()
    req = urllib.request.Request("https://api.zhuceka.cn/home/api", data=form,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        p = json.loads(r.read())
    d = p.get("data") or {}
    for k in ("video", "video_url", "url", "play_url"):
        if isinstance(d.get(k), str) and d[k].startswith("http"):
            return d[k]
    return None


def _safe(s, n=24):
    s = re.sub(r"[\\/:*?\"<>|\n\r\t#]", " ", s or "").strip()
    return re.sub(r"\s+", " ", s)[:n] or "无标题"


def write_md(c: dict, author: dict | None, cues: list, no_voice: bool = False) -> Path:
    plat = PLATFORMS.get(c["platform"], c["platform"])
    who = _safe((author or {}).get("nickname") or "未知博主", 30)
    day = time.strftime("%Y-%m-%d", time.localtime(c.get("published_at") or time.time()))
    p = db.data_root() / plat / "博主" / who / f"{day}_{_safe(c.get('title'))}_{c['content_id']}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = {"平台": plat, "博主": (author or {}).get("nickname"), "标题": c.get("title"), "链接": c.get("url"),
          "发布时间": time.strftime("%Y-%m-%d %H:%M", time.localtime(c["published_at"])) if c.get("published_at") else None,
          "时长秒": c.get("duration_s"), "点赞": c.get("likes"), "评论": c.get("comments"), "收藏": c.get("saves"),
          "分享": c.get("shares"), "播放": c.get("views"), "内容ID": c["content_id"],
          "采集时间": time.strftime("%Y-%m-%d %H:%M")}
    lines = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, str) else ('' if v is None else v)}"
                       for k, v in fm.items()] + ["---", "", f"# {c.get('title') or '无标题'}", ""]
    if no_voice:
        lines += ["> 可能无口播：转写出来的字很少，多半是纯音乐或画面类视频。", ""]
    if c.get("caption"):
        lines += ["## 文案", "", c["caption"], ""]
    hook = "".join(t for s, t in cues if s < 5)
    if hook:
        lines += ["## 前 5 秒", "", hook, ""]
    lines += ["## 逐字稿", ""]
    buf, start = [], None
    for s, t in cues:
        if start is None:
            start = s
        if s - start >= 60 and buf:
            lines += [f"[{int(start // 60)}:{int(start % 60):02d}] " + "".join(buf), ""]
            buf, start = [], s
        buf.append(t)
    if buf:
        lines += [f"[{int(start // 60)}:{int(start % 60):02d}] " + "".join(buf), ""]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def transcribe_content(pk: int, provider, s: dict, force=False) -> dict:
    c = db.q1("SELECT * FROM contents WHERE id=?", (pk,))
    if not c:
        raise TranscribeError("内容不存在")
    if c["transcript_status"] == "done" and not force:
        return {"skipped": True, "reason": "已有逐字稿，直接复用"}
    if c.get("type") == "image":
        db.x("UPDATE contents SET transcript_status='na' WHERE id=?", (pk,))
        return {"skipped": True, "reason": "图文笔记，没有音频"}
    if c["platform"] == "sph" and not os.environ.get("DEI_WB_DEMO"):
        db.x("UPDATE contents SET transcript_status='failed', transcript_error=? WHERE id=?",
             ("视频号视频文件是加密的，第一期暂不支持转写", pk))
        raise TranscribeError("视频号视频文件是加密的，第一期暂不支持转写")
    db.x("UPDATE contents SET transcript_status='running', transcript_error=NULL WHERE id=?", (pk,))
    author = db.q1("SELECT * FROM authors WHERE id=?", (c["author_pk"],)) if c.get("author_pk") else None
    try:
        if os.environ.get("DEI_WB_DEMO"):
            time.sleep(1.5)
            cues = [[0.0, "大家好，今天教你一个方法，"], [2.4, "三分钟让 AI 帮你把周报写完。"], [6.0, "第一步，打开你常用的 AI 工具，"],
                    [12.0, "把这周做过的事情用一句话一句话列出来。"], [20.0, "第二步，让它按老板最关心的结果来排序。"],
                    [65.0, "最后记得自己读一遍再交。关注我，下期讲怎么做汇报 PPT。"]]
            dur = 72
        else:
            errs = []
            urls = [c.get("media_url")]
            cues = dur = None
            for attempt in range(3):
                u = urls[-1]
                if u:
                    try:
                        cues, dur = paraformer(u, s)
                        break
                    except KeyError_:
                        raise
                    except Exception as e:  # noqa
                        errs.append(str(e)[:160])
                if attempt == 0:  # 直链没有或过期：重新取一次详情
                    try:
                        fresh = provider.video(c["platform"], store.content_ref(c))
                        urls.append(fresh.get("media_url"))
                        if fresh.get("content_id") == c["content_id"]:
                            # 顺手把详情写回：补全评论/收藏/分享、博主 sec_uid 等
                            store.upsert_content(fresh, provider.name, "refresh", label="转写前取直链")
                    except ProviderError as e:
                        errs.append(f"刷新直链失败：{e}")
                        urls.append(None)
                elif attempt == 1:  # 再试大圣去水印
                    try:
                        urls.append(dasheng(c.get("url"), s))
                    except Exception as e:  # noqa
                        errs.append(f"大圣失败：{e}")
                        urls.append(None)
            if cues is None:
                raise TranscribeError("拿不到可转写的音频：" + "；".join(errs or ["没有媒体直链"]))
        c = db.q1("SELECT * FROM contents WHERE id=?", (pk,))
        if c.get("author_pk"):
            author = db.q1("SELECT * FROM authors WHERE id=?", (c["author_pk"],))
        chars = len(re.sub(r"[\s\W]", "", "".join(t for _, t in cues)))
        no_voice = chars < max(8, (dur or c.get("duration_s") or 0) * 0.6)
        ex = json.loads(c.get("extra") or "{}")
        ex["no_voice"] = no_voice
        db.x("UPDATE contents SET extra=? WHERE id=?", (json.dumps(ex, ensure_ascii=False), pk))
        path = write_md(c, author, cues, no_voice)
        cost = round((dur or c.get("duration_s") or 0) * PARAFORMER_CNY_PER_SEC, 4)
        db.x("""UPDATE contents SET transcript_status='done', transcript_text=?, transcript_path=?, transcript_error=NULL,
                transcript_cost=?, duration_s=COALESCE(duration_s, ?) WHERE id=?""",
             (json.dumps(cues, ensure_ascii=False), str(path), cost, dur, pk))
        return {"ok": True, "path": str(path), "cost_cny": cost}
    except Exception as e:
        db.x("UPDATE contents SET transcript_status='failed', transcript_error=? WHERE id=?", (str(e)[:500], pk))
        raise
