"""文风 DNA：把一个博主的多条内容（逐字稿优先，没有就用文案）交给 Claude 做证据驱动的文风解析。

流程：选内容 → 程序先算量化底稿（句长、标点、人称、口头禅、高频词）→ 和原文一起发给 Claude
→ 报告存库 + 写 md（和逐字稿同一个博主文件夹）。
"""
from __future__ import annotations

import json
import os
import re
import statistics
import time
from collections import Counter
from pathlib import Path

from .. import db
from ..providers import PLATFORMS
from .transcribe import _safe

# 每百万 token 的美元价（输入, 输出）
MODEL_PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-fable-5-2": (8.0, 40.0),
}
MODEL_LABELS = {"claude-opus-5-5": "Claude Opus 5.5", "claude-sonnet-5-5": "Claude Sonnet 5.5", "claude-fable-5-2": "Claude Fable 5.2"}
MAX_CORPUS_CHARS = 600_000   # 约 60 万字，留足 1M 上下文的余量；超了按发布时间从新到旧截，并在报告里写明
EST_OUTPUT_TOKENS = 30_000   # 报告 + 思考，按 3 万 token 估

SCORE_KEYS = ["真实性", "权力", "情感", "逻辑", "具体", "行动"]


class StyleError(Exception):
    pass


# ---------------- 取材料 ----------------
def _cues_text(raw) -> str:
    try:
        cues = json.loads(raw or "[]")
    except Exception:
        return ""
    return "".join(t for _, t in cues).strip()


def collect(author_pk: int, limit: int) -> list[dict]:
    """按发布时间从新到旧取 limit 条（0 = 全部），每条给出逐字稿和文案。没有任何文字的跳过。"""
    sql = "SELECT * FROM contents WHERE author_pk=? ORDER BY published_at IS NULL, published_at DESC"
    rows = db.q(sql + (" LIMIT ?" if limit else ""), (author_pk, limit) if limit else (author_pk,))
    out = []
    for c in rows:
        ex = json.loads(c.get("extra") or "{}")
        tr = _cues_text(c.get("transcript_text")) if c.get("transcript_status") == "done" and not ex.get("no_voice") else ""
        cap = (c.get("caption") or "").strip()
        title = (c.get("title") or "").strip()
        if not (tr or cap or title):
            continue
        out.append({"pk": c["id"], "title": title, "caption": cap if cap != title else "", "transcript": tr,
                    "published_at": c.get("published_at"), "likes": c.get("likes"), "type": c.get("type")})
    return out


# ---------------- 量化底稿 ----------------
SENT_END = re.compile(r"[。！？!?；;…\n]+")
PUNCTS = {"，": "逗号", "。": "句号", "！": "感叹号", "？": "问号", "、": "顿号", "；": "分号", "：": "冒号",
          "…": "省略号", "—": "破折号", "“": "引号", "《": "书名号", "（": "括号", "~": "波浪号", "!": "感叹号(半角)",
          "?": "问号(半角)"}
MARKERS = {
    "人称": ["我", "我们", "咱们", "你", "你们", "他们", "大家", "老板", "朋友"],
    "确定性": ["一定", "必须", "绝对", "肯定", "永远", "所有", "根本", "本质", "真正", "其实"],
    "不确定性": ["可能", "也许", "大概", "或许", "我觉得", "我认为", "不一定", "好像"],
    "指令": ["记住", "千万", "一定要", "不要", "别", "赶紧", "马上", "去做", "试试", "关注"],
    "口语连接": ["就是", "然后", "所以", "但是", "因为", "而且", "那么", "对吧", "是不是", "你知道"],
    "情绪": ["真的", "太", "特别", "非常", "超级", "简直", "居然", "竟然", "哈哈", "天哪"],
    "身体感官": ["看", "听", "摸", "累", "疼", "饿", "心", "手", "眼", "身体", "呼吸", "感觉"],
}
STOP = set("的了是在我你他她它们这那和与也就都而及或一不有个上下中为以到说要会能没很还对把被让给从")


def _per_k(n: int, chars: int) -> float:
    return round(n * 1000 / chars, 2) if chars else 0.0


def _sentences(text: str) -> list[str]:
    return [s.strip(" ，,") for s in SENT_END.split(text) if len(s.strip(" ，,")) >= 2]


def _cjk(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text))


def _ngrams(texts: list[str], n: int, top: int) -> list[tuple[str, int]]:
    cnt: Counter = Counter()
    for t in texts:
        for run in re.findall(r"[一-鿿]{%d,}" % n, t):
            for i in range(len(run) - n + 1):
                g = run[i:i + n]
                if g[0] in STOP or g[-1] in STOP:
                    continue
                cnt[g] += 1
    return [(g, c) for g, c in cnt.most_common(top) if c >= 3]


def _top_grams(texts: list[str]) -> dict:
    """2/3/4 字高频串。被更长的串几乎完全覆盖的（次数 ≥ 它的 80%）去掉，避免「周报写」「报写完」这种碎片刷屏。"""
    g = {n: _ngrams(texts, n, 300) for n in (2, 3, 4)}
    longer = {n: [(x, c) for m in range(n + 1, 5) for x, c in g[m]] for n in (2, 3, 4)}
    out = {}
    for n, top in ((4, 20), (3, 20), (2, 30)):
        keep = [(x, c) for x, c in g[n] if not any(x in y and cy >= 0.8 * c for y, cy in longer[n])]
        out[f"top{n}"] = keep[:top]
    return out


def stats(items: list[dict]) -> dict:
    spoken = [i["transcript"] for i in items if i["transcript"]]
    written = [i["caption"] or i["title"] for i in items if i["caption"] or i["title"]]
    allt = [i["transcript"] or i["caption"] or i["title"] for i in items]
    body = "\n".join(allt)
    chars = _cjk(body) or len(body)

    sents = [s for t in allt for s in _sentences(t)]
    lens = [_cjk(s) or len(s) for s in sents]
    buckets = [("≤10 字", 0, 10), ("11–20 字", 11, 20), ("21–35 字", 21, 35), ("36–60 字", 36, 60), (">60 字", 61, 10 ** 9)]
    dist = {b: sum(lo <= x <= hi for x in lens) for b, lo, hi in buckets}

    wtext = "\n".join(written)
    wchars = _cjk(wtext) or len(wtext)
    punct = {name: _per_k(wtext.count(ch), wchars) for ch, name in PUNCTS.items() if wtext.count(ch)}

    markers = {grp: {w: _per_k(body.count(w), chars) for w in ws if body.count(w)} for grp, ws in MARKERS.items()}
    q_ratio = sum(1 for t in allt for m in re.finditer(r"[？?]", t))
    return {
        "items": len(items), "with_transcript": len(spoken), "chars": chars,
        "avg_chars_per_item": round(chars / len(items)) if items else 0,
        "sentences": len(lens),
        "sent_len": {"mean": round(statistics.mean(lens), 1) if lens else 0,
                     "median": statistics.median(lens) if lens else 0,
                     "p10": sorted(lens)[len(lens) // 10] if lens else 0,
                     "p90": sorted(lens)[len(lens) * 9 // 10] if lens else 0,
                     "stdev": round(statistics.pstdev(lens), 1) if len(lens) > 1 else 0},
        "sent_dist": dist,
        "question_per_k": _per_k(q_ratio, chars),
        "punct_written_per_k": punct, "written_chars": wchars,
        "markers_per_k": markers,
        **_top_grams(allt),
        "english_words_per_k": _per_k(len(re.findall(r"[A-Za-z]{2,}", body)), chars),
        "digits_per_k": _per_k(len(re.findall(r"\d+", body)), chars),
    }


def stats_md(st: dict) -> str:
    sl = st["sent_len"]
    L = [f"- 材料：{st['items']} 条，其中有逐字稿 {st['with_transcript']} 条；汉字约 {st['chars']}，平均每条 {st['avg_chars_per_item']} 字",
         f"- 句子：{st['sentences']} 句；句长均值 {sl['mean']}、中位数 {sl['median']}、P10 {sl['p10']}、P90 {sl['p90']}、标准差 {sl['stdev']}",
         "- 句长分布：" + "，".join(f"{k} {v} 句（{round(v * 100 / max(1, st['sentences']))}%）" for k, v in st["sent_dist"].items()),
         f"- 问号每千字 {st['question_per_k']}；英文词每千字 {st['english_words_per_k']}；数字每千字 {st['digits_per_k']}",
         f"- 标点（只统计作者亲手写的文案/标题，共 {st['written_chars']} 字，每千字）：" +
         ("，".join(f"{k} {v}" for k, v in st["punct_written_per_k"].items()) or "文案太少，无统计")]
    for grp, d in st["markers_per_k"].items():
        if d:
            label = f"- {grp}词（每千字，按字串计数，「我」含「我们」）：" if grp == "人称" else f"- {grp}词（每千字）："
            L.append(label + "，".join(f"{w} {v}" for w, v in sorted(d.items(), key=lambda x: -x[1])))
    for k, name in (("top4", "高频四字串"), ("top3", "高频三字串"), ("top2", "高频二字串")):
        if st[k]:
            L.append(f"- {name}：" + "，".join(f"{g}×{c}" for g, c in st[k]))
    return "\n".join(L)


# ---------------- 拼材料 ----------------
def corpus(items: list[dict]) -> tuple[str, int, int]:
    """返回（材料文本，实际用了几条，被截掉几条）。按从新到旧装，超过 MAX_CORPUS_CHARS 就停。"""
    parts, used = [], 0
    for n, it in enumerate(items, 1):
        day = time.strftime("%Y-%m-%d", time.localtime(it["published_at"])) if it.get("published_at") else "未知"
        seg = [f"【#{n}】标题：{it['title'] or '无'}｜发布 {day}｜点赞 {it['likes'] if it['likes'] is not None else '—'}"]
        if it["caption"]:
            seg.append(f"文案：{it['caption']}")
        if it["transcript"]:
            seg.append(f"逐字稿：{it['transcript']}")
        s = "\n".join(seg)
        if used + len(s) > MAX_CORPUS_CHARS and parts:
            return "\n\n".join(parts), len(parts), len(items) - len(parts)
        parts.append(s)
        used += len(s)
    return "\n\n".join(parts), len(parts), 0


SYSTEM = """你是一位精通哲学、语言学、修辞学与意识形态批评的文风分析专家。你要对同一位作者的一批内容（短视频口播逐字稿、笔记文案）做证据驱动的「文风 DNA」解析。

关于材料：
- 每条材料以【#编号】开头。引用原文一律写成「原文」(#编号)，引文必须逐字出自材料，不改写、不拼接、不编造。
- 「逐字稿」由语音识别生成：标点是机器加的，偶有同音错字。分析标点习惯只能以「文案」和标题为准，逐字稿里的标点不能当作者习惯的证据；遇到明显的识别错字按原意理解即可。
- 「量化底稿」由程序统计，数字以它为准。你可以解读、对照、质疑它（例如某个高频串其实是识别错误），但不要另编统计数字；需要底稿里没有的数字时，写明是估计。

分析原则：
- 每个判断都要有原文引用作证据，量化与质化并重。
- 不简单贴标签：不要只写「成功学」「消费主义」「焦虑营销」这类词就收工，要写清作者相信什么、反对什么、默认了什么，以及这些从哪些句子看出来。
- 重点找文本内部的自相矛盾：作者说的和做的、不同条目之间、主张和语气之间的张力。
- 写给内容创作者看：结论要能被拿去用，少写学术套话。

输出格式（Markdown，严格按以下标题和顺序）：

## 0. 一句话文风
一句话概括核心文风（不超过 40 字），下面用 2–3 句说明这句话怎么来的。

## 1. 哲学底层
### 1.1 本体论：作者怎样构建「真实」
### 1.2 认识论：知识从哪里来
（亲身经历、权威、数据、案例、直觉、常识、他人故事……各占多大分量，作者如何让听众相信）
### 1.3 语言哲学：符号与言语行为
（断言、指令、承诺、表态、宣告各自的用法和大致占比；作者如何使用命名、比喻、术语）

## 2. 意识形态与权力
### 2.1 意识形态倾向
### 2.2 说话姿态里的权力高低
（人称使用、指令句、对听众的称呼、谁被赋予说话资格、作者把自己放在什么位置）

## 3. 修辞与论证
### 3.1 论证方式
### 3.2 修辞策略
### 3.3 句长、高频词、标点
（对照量化底稿：数字说明了什么，和这类内容的常见写法比有什么不同）

## 4. 身体、情感与美学
### 4.1 身体感受
### 4.2 情感浓度
### 4.3 美学节奏
### 4.4 风格谱系
（这种写法承接自哪些文体、传统或作者）

## 5. 内部矛盾
至少 3 处。每处写成：表面主张 → 实际做法 → 这个矛盾说明什么。两边都要有原文。

## 6. 六维评分
表格：维度 ｜ 分数（1–10）｜ 10 分代表什么 ｜ 解读（含一句引文）。
维度依次是：真实性、权力、情感、逻辑、具体、行动。

## 7. 与三位作者对比
选三位可比的作者或内容创作者（至少一位不在同一领域），各写：相同点、关键差异、这位博主可以向他借什么。

## 8. 仿写风格提示词
一段可以直接贴给 AI 的提示词（放在代码块里），包含：身份与姿态、句式规则（带具体数字）、常用词与禁用词、段落结构模板、开头和结尾套路、3 句示范（新写的，不抄原文）。

## 9. DNA 指纹
一个 yaml 代码块，用紧凑的键值列出可机读的风格参数（句长、人称比例、指令密度、情感强度、论证类型、标志性词句、禁忌等）。

报告最后附一个 json 代码块（全文只此一个 json 块），格式：
{"summary": "一句话文风", "scores": {"真实性": 0, "权力": 0, "情感": 0, "逻辑": 0, "具体": 0, "行动": 0}, "authors": ["对比作者1", "对比作者2", "对比作者3"]}"""


def build_user(author: dict, st: dict, text: str, used: int, cut: int) -> str:
    who = author.get("nickname") or author.get("author_id")
    head = f"作者：{who}（{PLATFORMS.get(author['platform'], author['platform'])}）\n简介：{(author.get('bio') or '无').strip()}\n"
    note = f"\n注意：材料过长，只装入了最新的 {used} 条，另有 {cut} 条较早的未装入。\n" if cut else ""
    return f"{head}{note}\n# 量化底稿\n{stats_md(st)}\n\n# 材料（共 {used} 条，从新到旧）\n\n{text}"


def estimate(author_pk: int, limit: int, model: str) -> dict:
    items = collect(author_pk, limit)
    text, used, cut = corpus(items)
    in_tok = int(len(text) * 1.1) + 6000  # 中文约 1 字 ≈ 1 token，再加系统提示和底稿
    pi, po = MODEL_PRICES.get(model, MODEL_PRICES["claude-opus-5-5"])
    usd = round(in_tok * pi / 1e6 + EST_OUTPUT_TOKENS * po / 1e6, 3)
    return {"items": used, "cut": cut, "chars": len(text), "in_tokens": in_tok, "usd": usd,
            "with_transcript": sum(1 for i in items[:used] if i["transcript"])}


# ---------------- 调 Claude ----------------
def analyze(author: dict, items: list[dict], s: dict, log) -> dict:
    import anthropic

    key = (s.get("anthropic_api_key") or "").strip() or None
    model = s.get("style_model") or "claude-opus-5-5"
    effort = s.get("style_effort") or "high"
    st = stats(items)
    text, used, cut = corpus(items)
    if cut:
        log(f"材料超过 {MAX_CORPUS_CHARS // 10000} 万字，只装入最新 {used} 条，另有 {cut} 条未装入", "warn")
    user = build_user(author, st, text, used, cut)
    if not (key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise StyleError("没有 Anthropic API Key：去设置页「AI 分析」填写")
    client = anthropic.Anthropic(api_key=key, timeout=1800)
    log(f"发给 {MODEL_LABELS.get(model, model)} 分析 {used} 条（约 {len(text)} 字），通常要 2–6 分钟")
    t0 = time.time()
    try:
        with client.beta.messages.stream(
            model=model,
            max_tokens=64000,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise StyleError("Anthropic API Key 无效：去设置页重新填写") from e
    except anthropic.RateLimitError as e:
        raise StyleError("Anthropic 接口限流，稍后重试") from e
    except anthropic.APIStatusError as e:
        raise StyleError(f"Anthropic 接口报错 {e.status_code}：{str(e.message)[:200]}") from e
    except anthropic.APIConnectionError as e:
        raise StyleError(f"连不上 Anthropic 接口：{e}") from e

    if msg.stop_reason == "refusal":
        raise StyleError("模型拒绝了这次分析（refusal），可以换一批内容再试")
    report = "".join(b.text for b in msg.content if b.type == "text").strip()
    if not report:
        raise StyleError(f"模型没有返回内容（stop_reason={msg.stop_reason}）")
    if msg.stop_reason == "max_tokens":
        log("报告到达长度上限，结尾可能不完整", "warn")

    u = msg.usage
    in_tok = (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0)
    pi, po = MODEL_PRICES.get(msg.model, MODEL_PRICES.get(model, (4.0, 20.0)))
    cost = round(in_tok * pi / 1e6 + (u.output_tokens or 0) * po / 1e6, 4)
    log(f"分析完成：{round(time.time() - t0)} 秒，输入 {in_tok} / 输出 {u.output_tokens} token，约 ${cost}")

    meta = {}
    m = re.findall(r"```json\s*(\{.*?\})\s*```", report, re.S)
    if m:
        try:
            meta = json.loads(m[-1])
        except Exception:
            log("报告末尾的评分 json 解析失败，评分条不显示", "warn")
    return {"report": report, "stats": st, "meta": meta, "model": msg.model, "used": used, "cut": cut,
            "in_tokens": in_tok, "out_tokens": u.output_tokens, "cost_usd": cost}


def write_md(author: dict, r: dict) -> Path:
    plat = PLATFORMS.get(author["platform"], author["platform"])
    who = _safe(author.get("nickname") or "未知博主", 30)
    p = db.data_root() / plat / "博主" / who / f"_文风DNA_{time.strftime('%Y-%m-%d_%H%M')}_{r['used']}条.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = ["---", f"博主: {json.dumps(author.get('nickname'), ensure_ascii=False)}", f"平台: {plat}",
          f"分析条数: {r['used']}", f"模型: {r['model']}", f"生成时间: {time.strftime('%Y-%m-%d %H:%M')}",
          f"花费美元: {r['cost_usd']}", "---", "", f"# {author.get('nickname')} · 文风 DNA", ""]
    tail = ["", "---", "", "## 附：量化底稿（程序统计）", "", stats_md(r["stats"]), ""]
    p.write_text("\n".join(fm) + "\n" + r["report"] + "\n".join(tail), encoding="utf-8")
    return p
