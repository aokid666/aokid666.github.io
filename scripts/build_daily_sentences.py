#!/usr/bin/env python3
"""Generate the public sentence archive from the canonical Markdown ledger."""

from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass
class Record:
    key: str
    title: str
    prompt: str = ""
    status: str = ""
    answer: str = ""
    feedback: list[tuple[str, str]] = field(default_factory=list)


def clean(text: str) -> str:
    return re.sub(r"\*\*(.*?)\*\*", r"\1", text).strip()


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def parse_ledger(path: Path) -> tuple[dict[str, list[Record]], list[tuple[str, str, str]]]:
    days: dict[str, list[Record]] = {}
    history: list[tuple[str, str, str]] = []
    current_day: str | None = None
    current: Record | None = None
    mode = ""

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        day_match = re.match(r"^## (\d{4}-\d{2}-\d{2})(?:$|：)", line)
        if day_match:
            current_day = day_match.group(1)
            current = None
            mode = ""
            days.setdefault(current_day, [])
            continue

        item = re.match(r"^### (\d{4}-\d{2}-\d{2}-\d{2})｜(.+)$", line)
        if item and current_day:
            current = Record(item.group(1), clean(item.group(2)).strip("【】"))
            days.setdefault(current_day, []).append(current)
            mode = "prompt"
            continue
        if not current:
            continue
        if line.startswith("**题目：**"):
            prompt = clean(line.removeprefix("**题目：**"))
            current.prompt += ("\n" if current.prompt and prompt else "") + prompt
            mode = "prompt"
        elif line.startswith("**共同情境：**"):
            context = clean(line.removeprefix("**共同情境：**"))
            current.prompt += ("\n" if current.prompt and context else "") + context
            mode = "prompt"
        elif line.startswith("**状态：**"):
            current.status = clean(line.removeprefix("**状态：**"))
            mode = ""
        elif line.startswith("**用户原答／"):
            mode = ""
        elif line.startswith("**用户原答"):
            mode = "answer"
        elif line.startswith("|"):
            cells = [clean(x) for x in line.strip("|").split("|")]
            if len(cells) == 2 and cells[0] not in {"---", "项目"} and not set(cells[0]) <= {"-", ":"}:
                current.feedback.append((cells[0], cells[1]))
            mode = ""
        elif line.startswith(">"):
            quote = clean(line[1:].strip())
            if quote and mode in {"answer", "prompt"}:
                previous = current.answer if mode == "answer" else current.prompt
                setattr(current, mode, previous + ("\n" if previous else "") + quote)
        elif line and not line.startswith(("##", "**")) and mode == "prompt":
            current.prompt += ("\n" if current.prompt else "") + clean(line)
    return days, history


def kind(record: Record) -> str:
    if "已讲评" in record.status or "已评" in record.status:
        return "reviewed"
    if "明确不会" in record.status:
        return "blocked"
    if record.answer:
        return "submitted"
    return "pending"


def genre(record: Record) -> str:
    if "小作文" in record.title:
        return "small"
    if "大作文" in record.title:
        return "large"
    return "other"


def mode(record: Record) -> str:
    title = record.title
    index = int(record.key[-2:])
    if "中文转英文" in title:
        return "translate"
    if "情境造句" in title:
        return "compose"
    if "纠错" in title:
        return "correct"
    if "表达升级" in title:
        return "upgrade"
    if "衔接" in title or index in (7, 8):
        return "connect"
    if "复现" in title or index == 9:
        return "recall"
    if "迁移" in title or index == 10:
        return "transfer"
    # Older questions do not always label their form; use the set's known 1–10 structure.
    return {1: "translate", 2: "translate", 3: "compose", 4: "compose", 5: "correct", 6: "upgrade"}[index]


def scene(record: Record) -> str:
    title = record.title
    if genre(record) == "large":
        if "图表" in title or "数据" in title or "材料联系" in title:
            return "chart"
        if "图画" in title or "从描述" in title:
            return "picture"
        return "argument"
    if any(x in title for x in ("通知", "招募", "活动安排")):
        return "notice"
    if any(x in title for x in ("申请", "志愿者")):
        return "application"
    if any(x in title for x in ("建议", "推荐", "回复")):
        return "advice"
    if any(x in title for x in ("请求", "询问", "投诉")):
        return "request"
    return "correspondence"


MODE_LABELS = {
    "translate": "中文转英文", "compose": "情境造句", "correct": "纠错",
    "upgrade": "表达升级", "connect": "两句衔接", "recall": "复现", "transfer": "迁移",
}
SCENE_LABELS = {
    "chart": "图表 / 数据", "picture": "图画", "argument": "论证 / 解释",
    "notice": "通知 / 活动", "application": "申请 / 招募",
    "advice": "建议 / 推荐", "request": "询问 / 请求", "correspondence": "书信往来",
}
STATE_LABELS = {"reviewed": "已讲评", "submitted": "待讲评", "blocked": "待补写", "pending": "待作答"}


def preview(record: Record) -> str:
    """Return a compact, useful prompt preview for the collapsed list row."""
    text = " ".join(record.prompt.split())
    quoted = re.search(r"“([^”]{6,100})”", text)
    if quoted:
        text = quoted.group(1)
    else:
        text = re.sub(
            r"^(共同情境：|承接第\d题，|用一句(?:英文)?话(?:准确)?(?:概括|表达|说明|提出|解释|推荐|写出)?[:：]?)",
            "",
            text,
        )
    text = re.sub(r"^(请)?用一个完整英文句子", "", text).lstrip("表达：: ")
    return text if len(text) <= 52 else text[:51].rstrip("，；、 ") + "…"


def render_record(record: Record) -> str:
    state = kind(record)
    form = mode(record)
    context = scene(record)
    searchable = " ".join([record.key, record.title, record.prompt, record.answer, *[v for _, v in record.feedback]])
    answer = (
        f'<div class="answer-block"><span class="content-label">你的原答</span>'
        f'<p class="english">{esc(record.answer)}</p></div>'
        if record.answer else ""
    )
    feedback = ""
    if record.feedback:
        feedback = '<div class="feedback-block"><span class="content-label">讲评与修改</span><dl class="feedback-list">' + "".join(
            f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>'
            for k, v in record.feedback
        ) + "</dl></div>"
    if not answer and state != "blocked":
        answer = '<p class="waiting">尚未找到作答记录。可以在聊天中报出日期和题号继续作答。</p>'
    return f"""
      <details class="question" id="q-{record.key}" data-date="{record.key[:10]}" data-state="{state}" data-genre="{genre(record)}" data-mode="{form}" data-scene="{context}" data-search="{esc(searchable.lower())}">
        <summary>
          <span class="question-index">{record.key[-2:]}</span>
          <span class="question-main"><strong>{esc(record.title)}</strong><span class="question-preview">{esc(preview(record))}</span><small>{esc(MODE_LABELS[form])} · {esc(SCENE_LABELS[context])}</small></span>
          <span class="state-pill {state}">{STATE_LABELS[state]}</span>
          <span class="open-icon" aria-hidden="true">＋</span>
        </summary>
        <div class="question-detail">
          <div class="prompt-block"><span class="content-label">题目 · {record.key}</span><p>{esc(record.prompt)}</p></div>
          {answer}{feedback}
        </div>
      </details>"""


def options(items: list[tuple[str, str]]) -> str:
    return "".join(f'<option value="{esc(value)}">{esc(label)}</option>' for value, label in items)


def render(days: dict[str, list[Record]], history: list[tuple[str, str, str]]) -> str:
    records = [r for day in days.values() for r in day]
    if not records or len({r.key for r in records}) != len(records):
        raise ValueError("台账没有可用题目，或题号重复")
    dates = sorted(days, reverse=True)
    reviewed = sum(kind(r) == "reviewed" for r in records)
    blocked = sum(kind(r) == "blocked" for r in records)
    waiting = len(records) - reviewed - blocked
    updated = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    date_options = options([("", "全部日期")] + [(d, d) for d in dates])
    status_options = options([("", "全部状态"), ("pending", "待作答"), ("submitted", "待讲评"), ("blocked", "待补写"), ("reviewed", "已讲评")])
    genre_options = options([("", "全部类型"), ("small", "小作文"), ("large", "大作文")])
    mode_options = options([("", "全部方式")] + list(MODE_LABELS.items()))
    scene_options = options([("", "全部场景")] + list(SCENE_LABELS.items()))
    date_sections = "".join(
        f'<section class="day-section" data-day="{d}"><div class="date-heading"><div><span class="overline">SESSION / {len(dates) - i:02}</span><h2>{d}<small> / {len(days[d])} 句</small></h2></div><span>{sum(kind(r) == "reviewed" for r in days[d])} 题已讲评</span></div><div class="question-list">{"".join(render_record(r) for r in days[d])}</div></section>'
        for i, d in enumerate(dates)
    )
    history_rows = "".join(f'<li><span>{esc(k[-2:])}</span><strong>{esc(topic)}</strong></li>' for k, topic, _ in history)
    history_panel = (
        f'<section class="history-panel"><div class="date-heading"><div><span class="overline">ARCHIVE NOTE</span><h2>2026-09-10 <small>/ 历史摘要</small></h2></div><span>{len(history)} 条待补档</span></div>'
        f'<p>这一天现存记录只有主题摘要，原题、原答与讲评全文仍待补档。</p><ol>{history_rows}</ol></section>'
        if history else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="theme-color" content="#f6f4ef">
  <title>每日句子｜我的考研资料库</title>
  <meta name="description" content="考研英语一每日句子训练：按日期、题型、方式、场景筛选题目、作答与讲评。">
  <link rel="stylesheet" href="/assets/site.css">
  <link rel="stylesheet" href="/daily-sentences/daily.css">
  <script src="/daily-sentences/app.js" defer></script>
</head>
<body>
<div class="site-shell">
  <nav class="site-nav" aria-label="主导航">
    <a class="wordmark" href="/"><span class="mark">A<span>·</span></span><span>我的考研资料库</span></a>
    <div class="nav-links"><a href="/">资料首页</a><a href="/daily-sentences/" aria-current="page">每日句子</a></div>
  </nav>
  <main>
    <header class="archive-hero">
      <div class="archive-heading"><span class="overline"><span class="signal"></span> ENGLISH I · SENTENCE JOURNAL</span><h1>每日句子<span class="title-dot">.</span></h1><p>每一道题都有自己的位置。从题目到原答，再到讲评和下一次复现，沿着日期慢慢积累。</p></div>
      <div class="archive-hero-note"><span>最新收录</span><strong>{dates[0]}</strong><span>可随时回看与补交</span></div>
    </header>
    <section class="progress-strip" aria-label="训练概览">
      <div><strong>{len(records)}</strong><span>完整题目</span></div>
      <div><strong>{reviewed}</strong><span>已讲评</span></div>
      <div><strong>{waiting}</strong><span>待作答 / 待评</span></div>
      <div><strong>{blocked}</strong><span>待补写</span></div>
    </section>
    <div class="archive-layout">
      <aside class="filter-panel" aria-label="题目分类筛选">
        <details class="filter-drawer" open>
          <summary><span>筛选题目</span><span aria-hidden="true">⌄</span></summary>
          <div class="filter-fields">
            <label>日期<select id="date-filter">{date_options}</select></label>
            <label>作答状态<select id="state-filter">{status_options}</select></label>
            <label>作文类型<select id="genre-filter">{genre_options}</select></label>
            <label>训练方式<select id="mode-filter">{mode_options}</select></label>
            <label>表达场景<select id="scene-filter">{scene_options}</select></label>
            <button class="clear-button" id="reset-filters" type="button">清除所有筛选 <span aria-hidden="true">↺</span></button>
          </div>
        </details>
        <div class="filter-tip"><span aria-hidden="true">✳</span><p>筛选可以叠加。例如选“小作文”＋“待作答”，就能找到尚未完成的应用文句子。</p></div>
      </aside>
      <div class="archive-content">
        <div class="content-toolbar"><div><span class="overline">THE SENTENCE ARCHIVE</span><h2>训练档案</h2></div><div class="search-wrap"><label class="sr-only" for="search">搜索题目、原答与讲评</label><input id="search" type="search" placeholder="搜索题目、原答、讲评…" autocomplete="off"></div></div>
        <div class="results-row"><span id="result-count" role="status" aria-live="polite">显示 {len(records)} 道题</span><span>点击题目查看完整记录</span></div>
        <div id="archive">{date_sections}</div>
        <div class="empty-state" id="empty-state" hidden><strong>没有找到符合条件的题目</strong><p>试试调整分类，或清除筛选重新浏览。</p><button type="button" id="empty-reset">清除筛选</button></div>
{history_panel}
      </div>
    </div>
  </main>
  <footer class="site-footer"><span>更新于 {updated} · 题目与讲评依据可核对台账整理</span><span>未找到作答记录的题目不会补写答案。</span></footer>
</div>
</body>
</html>"""


def update_home(path: Path, total: int, reviewed: int) -> None:
    content = path.read_text(encoding="utf-8")
    changes = {
        r'(<div class="hero-aside-number">)\d+(<span>句</span>)': rf'\g<1>{total}\g<2>',
        r'(<div class="hero-aside-foot"><span>)\d+( 题已有原答和讲评)': rf'\g<1>{reviewed}\g<2>',
        r'(<div class="tag-row"><span>)\d+( 道题</span><span>)\d+( 题已讲评)': rf'\g<1>{total}\g<2>{reviewed}\g<3>',
        r'(个人学习资料 · 最后更新 )\d{4}-\d{2}-\d{2}': rf'\g<1>{datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")}',
    }
    for pattern, replacement in changes.items():
        content, count = re.subn(pattern, replacement, content)
        if count != 1:
            raise ValueError(f"首页统计标记无法唯一匹配：{pattern}")
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--home", type=Path, help="同步更新首页统计与日期")
    args = parser.parse_args()
    days, history = parse_ledger(args.ledger)
    result = render(days, history)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding="utf-8")
    if args.home:
        records = [r for group in days.values() for r in group]
        update_home(args.home, len(records), sum(kind(r) == "reviewed" for r in records))


if __name__ == "__main__":
    main()
