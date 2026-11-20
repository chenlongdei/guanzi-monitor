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


def _base(s: dict) -> str:
    return (s.get("dashscope_base_url") or "https://dashscope.aliyuncs.com").rstrip("/")


def test_key(s: dict) -> dict:
    """提交一段官方示例音频（几秒，费用可忽略）验证 Key 能不能用 Paraformer。"""
    key = (s.get("dashscope_api_key") or "").strip()
    if not key:
        return {"ok": False, "msg": "没有填百炼 Key"}
    try:
        _post(_base(s) + "/api/v1/services/audio/asr/transcription", key,
              {"model": s.get("dashscope_model") or "paraformer-v2",
               "input": {"file_urls": ["https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/hello_world_female2.wav"]},
               "parameters": {"channel_id": [0]}}, {"X-DashScope-Async": "enable"})
        return {"ok": True, "msg": "可以调用 Paraformer"}
    except TranscribeError as e:
        return {"ok": False, "msg": str(e)}


def paraformer(media_url: str, s: dict, max_wait=1800, log=None):
    log = log or (lambda *a, **k: None)
    key = (s.get("dashscope_api_key") or "").strip()
    if not key:
        raise TranscribeError("没有填阿里云百炼 Key（设置页，sk- 开头）")
    base = _base(s)
    resp = _post(base + "/api/v1/services/audio/asr/transcription", key,
                 {"model": s.get("dashscope_model") or "paraformer-v2", "input": {"file_urls": [media_url]},
                  "parameters": {"channel_id": [0], "language_hints": ["zh", "en"]}},
                 {"X-DashScope-Async": "enable"})
    task = (resp.get("output") or {}).get("task_id")
    if not task:
        raise TranscribeError(f"提交转写失败：{json.dumps(resp, ensure_ascii=False)[:200]}")
    log(f"已提交阿里云转写（任务 {task[:8]}…），等待结果")
    t0 = last_log = time.time()
    while time.time() - t0 < max_wait:
        resp = _post(f"{base}/api/v1/tasks/{task}", key)
        out = resp.get("output")
        if not isinstance(out, dict) or not out.get("task_status"):
            # 没有 output / 没有状态：不是「还在跑」，继续等只会空转到超时
            raise TranscribeError(f"查询转写进度返回异常：{json.dumps(resp, ensure_ascii=False)[:200]}")
        st = out["task_status"]
        if time.time() - last_log >= 60:
            last_log = time.time()
            log(f"阿里云转写进行中（{st}），已等 {int(time.time() - t0)} 秒")
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
    raise TranscribeError(f"转写超时：等了 {max_wait // 60} 分钟阿里云还没出结果")


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


def _fresh_media_url(c: dict, provider, errs: list, log) -> str | None:
    """重新取直链：provider.media_url()（只在转写时调，如小红书走 TikHub 视频详情）→ provider.video() 刷新。
    取到就写回 contents.media_url；每条路线为什么没取到都记进 errs，不再静默。"""
    ref = store.content_ref(c)
    try:
        u = provider.media_url(c["platform"], ref)
        if u:
            log("已取到视频直链")
            db.x("UPDATE contents SET media_url=? WHERE id=?", (u, c["id"]))
            return u
    except ProviderError as e:
        if e.fatal:
            raise
        errs.append(f"取直链失败：{e}")
    try:
        log("重新取一次详情找直链")
        fresh = provider.video(c["platform"], ref)
        if fresh.get("content_id") == c["content_id"]:
            # 顺手把详情写回：补全评论/收藏/分享、博主 sec_uid 等
            store.upsert_content(fresh, provider.name, "refresh", label="转写前取直链")
        if fresh.get("media_url"):
            return fresh["media_url"]
        errs.append(f"{provider.name} 的详情里没有视频直链")
    except ProviderError as e:
        if e.fatal:
            raise
        errs.append(f"刷新直链失败：{e}")
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


def transcribe_content(pk: int, provider, s: dict, force=False, log=None) -> dict:
    """log(msg, level)：每一步写进任务日志，卡住时能看出卡在哪。"""
    _log = log or (lambda *a, **k: None)
    log = lambda msg, level="info": _log(f"#{pk} {msg}", level)  # noqa: E731
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
            if not urls[0]:
                log("库里没有视频直链，去渠道取")
            cues = dur = None
            for attempt in range(3):
                u = urls[-1]
                if u:
                    try:
                        cues, dur = paraformer(u, s, log=log)
                        break
                    except KeyError_:
                        raise
                    except Exception as e:  # noqa
                        errs.append(str(e)[:160])
                        log(f"转写失败，换一个直链再试：{str(e)[:120]}", "warn")
                if attempt == 0:  # 直链没有或过期：先用渠道专门取直链的接口，没有再重新取一次详情
                    urls.append(_fresh_media_url(c, provider, errs, log))
                elif attempt == 1:  # 再试大圣去水印
                    if not (s.get("dasheng_uid") and s.get("dasheng_key")):
                        errs.append("大圣去水印没配置，跳过")
                        urls.append(None)
                        continue
                    try:
                        log("改用大圣去水印取直链")
                        v = dasheng(c.get("url"), s)
                        if not v:
                            errs.append("大圣没返回视频地址")
                        urls.append(v)
                    except Exception as e:  # noqa
                        errs.append(f"大圣失败：{e}")
                        urls.append(None)
            if cues is None:
                raise TranscribeError("拿不到可转写的音频：" + "；".join(errs or ["渠道没有返回可用的视频直链"]))
        c = db.q1("SELECT * FROM contents WHERE id=?", (pk,))
        if c.get("author_pk"):
            author = db.q1("SELECT * FROM authors WHERE id=?", (c["author_pk"],))
        chars = len(re.sub(r"[\s\W]", "", "".join(t for _, t in cues)))
        no_voice = chars < max(8, (dur or c.get("duration_s") or 0) * 0.6)
        ex = json.loads(c.get("extra") or "{}")
        ex["no_voice"] = no_voice
        db.x("UPDATE contents SET extra=? WHERE id=?", (json.dumps(ex, ensure_ascii=False), pk))
        path = write_md(c, author, cues, no_voice)
        log(f"转写完成，{len(cues)} 句")
        cost = round((dur or c.get("duration_s") or 0) * PARAFORMER_CNY_PER_SEC, 4)
        db.x("""UPDATE contents SET transcript_status='done', transcript_text=?, transcript_path=?, transcript_error=NULL,
                transcript_cost=?, duration_s=COALESCE(duration_s, ?) WHERE id=?""",
             (json.dumps(cues, ensure_ascii=False), str(path), cost, dur, pk))
        return {"ok": True, "path": str(path), "cost_cny": cost}
    except Exception as e:
        db.x("UPDATE contents SET transcript_status='failed', transcript_error=? WHERE id=?", (str(e)[:500], pk))
        raise
