#!/usr/bin/env python3
"""Build the public daily sentence archive from the training ledger."""

from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Record:
    key: str
    title: str
    prompt: str = ""
    status: str = ""
    answer: str = ""
    feedback: list[tuple[str, str]] = field(default_factory=list)


def inline(text: str) -> str:
    return re.sub(r"\*\*(.*?)\*\*", r"\1", text).strip()


def parse_ledger(path: Path) -> tuple[dict[str, list[Record]], list[tuple[str, str, str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    days: dict[str, list[Record]] = {}
    history: list[tuple[str, str, str]] = []
    current_day: str | None = None
    current: Record | None = None
    mode = ""

    for raw in lines:
        line = raw.strip()
        day_match = re.match(r"^## (2026-\d{2}-\d{2})(?:$|：)", line)
        if day_match:
            current_day = day_match.group(1)
            current = None
            mode = ""
            if current_day != "2026-09-10":
                days.setdefault(current_day, [])
            continue

        if current_day == "2026-09-10":
            row = re.match(r"^\| (2026-09-10-\d{2}) \| (.*?) \| (.*?) \|$", line)
            if row:
                history.append(tuple(inline(x) for x in row.groups()))
            continue

        item = re.match(r"^### (2026-\d{2}-\d{2}-\d{2})｜(.+)$", line)
        if item and current_day:
            current = Record(item.group(1), inline(item.group(2)).strip("【】"))
            days.setdefault(current_day, []).append(current)
            mode = "prompt"
            continue
        if not current:
            continue

        if line.startswith("**状态：**"):
            current.status = inline(line.removeprefix("**状态：**"))
            mode = ""
            continue
        if line.startswith("**用户原答"):
            mode = "answer"
            continue
        if line.startswith("**用户原答／"):
            mode = ""
            continue
        if line.startswith("|"):
            cells = [inline(x) for x in line.strip("|").split("|")]
            if len(cells) == 2 and cells[0] not in {"---", "项目"} and not set(cells[0]) <= {"-", ":"}:
                current.feedback.append((cells[0], cells[1]))
            mode = ""
            continue
        if line.startswith(">"):
            quote = inline(line[1:].strip())
            if mode == "answer" and quote:
                current.answer += ("\n" if current.answer else "") + quote
            elif mode == "prompt" and quote:
                current.prompt += ("\n" if current.prompt else "") + quote
            continue
        if not line:
            continue
        if line.startswith("##") or line.startswith("**"):
            continue
        if mode == "prompt":
            current.prompt += ("\n" if current.prompt else "") + inline(line)

    return days, history


def status_kind(status: str) -> tuple[str, str]:
    if "已讲评" in status:
        return "reviewed", "已讲评"
    if "明确不会" in status:
        return "blocked", "待补写"
    return "pending", "待作答"


def record_html(record: Record) -> str:
    kind, label = status_kind(record.status)
    answer = ""
    if record.answer:
        answer = f'''<div class="answer"><div class="label">你的原答</div><p>{html.escape(record.answer)}</p></div>'''
    feedback = ""
    if record.feedback:
        rows = "".join(
            f'<div class="feedback-row"><dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd></div>'
            for k, v in record.feedback
        )
        feedback = f'<dl class="feedback">{rows}</dl>'
    empty = '<p class="empty">还没有提交答案，之后可以按日期和题号补交。</p>' if not answer else ""
    return f'''
      <details class="question" data-state="{kind}" data-search="{html.escape((record.key + ' ' + record.title + ' ' + record.prompt + ' ' + record.answer).lower(), quote=True)}">
        <summary><span class="number">{record.key[-2:]}</span><span class="qtitle">{html.escape(record.title)}</span><span class="badge {kind}">{label}</span><span class="chevron">⌄</span></summary>
        <div class="question-body">
          <div class="label">题目</div><p class="prompt">{html.escape(record.prompt)}</p>
          {answer}{feedback}{empty}
        </div>
      </details>'''


def build(days: dict[str, list[Record]], history: list[tuple[str, str, str]]) -> str:
    day_order = sorted(days, reverse=True)
    full = [r for day in days.values() for r in day]
    reviewed = sum(status_kind(r.status)[0] == "reviewed" for r in full)
    pending = len(full) - reviewed
    date_buttons = "".join(f'<button class="date-chip" data-date="{d}">{d[5:].replace("-", ".")}</button>' for d in day_order)
    day_blocks = "".join(
        f'''<section class="day" data-date="{day}">
          <div class="day-head"><div><span class="eyebrow">DAILY PRACTICE</span><h2>{day}</h2></div><span class="day-count">{sum(status_kind(r.status)[0] == "reviewed" for r in records)}/10 已讲评</span></div>
          <div class="questions">{"".join(record_html(r) for r in records)}</div>
        </section>'''
        for day, records in ((d, days[d]) for d in day_order)
    )
    history_rows = "".join(
        f'<div class="history-row"><span>{html.escape(key[-2:])}</span><b>{html.escape(topic)}</b><em>{html.escape(status)}</em></div>'
        for key, topic, status in history
    )
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>每日句子｜我的考研资料库</title><meta name="description" content="考研英语一每日句子训练：题目、作答、讲评和待办记录。">
<style>
:root{{--bg:#eef1f4;--card:#fff;--ink:#0f1720;--sub:#5b6873;--line:#e3e8ec;--accent:#0f766e;--accent2:#7c3aed;--soft:#ecf8f6;--violet:#f4f0ff;--amber:#fff7df;--shadow:0 1px 3px rgba(15,23,32,.07),0 8px 24px rgba(15,23,32,.05)}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0d1117;--card:#161b22;--ink:#e6edf3;--sub:#9aa7b2;--line:#2a313a;--accent:#45c9b7;--accent2:#b59cff;--soft:#102b28;--violet:#241c38;--amber:#352d19;--shadow:0 1px 3px rgba(0,0,0,.4),0 10px 28px rgba(0,0,0,.3)}}}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.72 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;-webkit-text-size-adjust:100%}}button,input{{font:inherit}}.wrap{{max-width:920px;margin:auto;padding:18px 14px 70px}}.topbar{{display:flex;align-items:center;justify-content:space-between;margin:0 4px 14px}}.back{{color:var(--sub);text-decoration:none;font-size:14px}}.updated{{font-size:12px;color:var(--sub)}}header{{position:relative;overflow:hidden;border-radius:24px;padding:30px 26px;color:#fff;background:linear-gradient(135deg,#0f766e 0%,#115e59 48%,#5b21b6 100%);box-shadow:var(--shadow)}}header:after{{content:"";position:absolute;right:-42px;top:-65px;width:230px;height:230px;border-radius:50%;background:rgba(255,255,255,.10)}}.k{{font-size:12px;letter-spacing:.16em;opacity:.8}}h1{{font-size:clamp(28px,6vw,42px);line-height:1.2;margin:8px 0}}header p{{max-width:590px;margin:0;opacity:.91;font-size:14px}}.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0 20px}}.stat{{background:var(--card);border-radius:16px;padding:16px 18px;box-shadow:var(--shadow)}}.stat b{{display:block;font-size:24px;line-height:1.2}}.stat span{{font-size:12px;color:var(--sub)}}.tools{{position:sticky;top:8px;z-index:10;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(12px);border:1px solid var(--line);border-radius:18px;padding:10px;margin-bottom:20px}}.search{{width:100%;border:0;background:var(--card);color:var(--ink);border-radius:11px;padding:10px 12px;outline:none;box-shadow:inset 0 0 0 1px var(--line)}}.filters{{display:flex;gap:7px;overflow:auto;padding-top:9px;scrollbar-width:none}}.filters::-webkit-scrollbar{{display:none}}.filter,.date-chip{{flex:none;border:0;border-radius:99px;padding:6px 11px;background:var(--card);color:var(--sub);font-size:12px;cursor:pointer;box-shadow:inset 0 0 0 1px var(--line)}}.filter.active,.date-chip.active{{background:var(--accent);color:#fff;box-shadow:none}}.day{{margin:28px 0 36px;scroll-margin-top:128px}}.day-head{{display:flex;align-items:end;justify-content:space-between;margin:0 4px 10px}}.eyebrow{{font-size:10px;letter-spacing:.14em;color:var(--accent);font-weight:700}}h2{{font-size:22px;line-height:1.2;margin:2px 0}}.day-count{{font-size:12px;color:var(--sub)}}.questions{{display:grid;gap:9px}}.question{{background:var(--card);border-radius:15px;box-shadow:var(--shadow);overflow:hidden}}.question[hidden],.day[hidden]{{display:none}}summary{{display:grid;grid-template-columns:34px minmax(0,1fr) auto 18px;gap:9px;align-items:center;cursor:pointer;list-style:none;padding:14px}}summary::-webkit-details-marker{{display:none}}.number{{display:grid;place-items:center;width:31px;height:31px;border-radius:9px;background:var(--soft);color:var(--accent);font-size:12px;font-weight:800}}.qtitle{{font-weight:650;font-size:14px;line-height:1.45}}.badge{{font-size:11px;padding:3px 8px;border-radius:99px;white-space:nowrap}}.badge.reviewed{{background:var(--soft);color:var(--accent)}}.badge.pending{{background:var(--violet);color:var(--accent2)}}.badge.blocked{{background:var(--amber);color:#9a6700}}.chevron{{color:var(--sub);transition:.18s}}details[open] .chevron{{transform:rotate(180deg)}}.question-body{{padding:0 16px 17px 57px;border-top:1px solid var(--line)}}.label{{margin-top:14px;font-size:11px;letter-spacing:.08em;color:var(--sub);font-weight:700}}.prompt,.answer p,.empty{{white-space:pre-line;margin:4px 0 0;font-size:14px}}.answer p{{padding:11px 13px;border-left:3px solid var(--accent2);border-radius:0 9px 9px 0;background:var(--violet);font-family:ui-serif,Georgia,serif}}.feedback{{margin:13px 0 0;border-top:1px solid var(--line)}}.feedback-row{{display:grid;grid-template-columns:145px 1fr;gap:14px;padding:10px 0;border-bottom:1px solid var(--line)}}dt{{font-size:12px;color:var(--accent);font-weight:700}}dd{{margin:0;font-size:13px}}.empty{{color:var(--sub);font-style:italic}}.history{{background:var(--card);border-radius:18px;padding:18px;box-shadow:var(--shadow);margin-top:34px}}.history h2{{margin-bottom:3px}}.history>p{{margin:0 0 12px;color:var(--sub);font-size:13px}}.history-row{{display:grid;grid-template-columns:32px minmax(0,1fr) auto;gap:10px;padding:9px 0;border-top:1px solid var(--line);font-size:13px}}.history-row span{{color:var(--accent);font-weight:800}}.history-row b{{font-weight:550}}.history-row em{{color:var(--sub);font-style:normal;font-size:11px;text-align:right}}.no-results{{display:none;text-align:center;color:var(--sub);padding:42px 0}}footer{{text-align:center;color:var(--sub);font-size:12px;margin-top:38px}}
@media(max-width:620px){{.wrap{{padding:12px 10px 52px}}header{{border-radius:20px;padding:24px 20px}}.stats{{gap:7px}}.stat{{padding:13px 12px}}.stat b{{font-size:20px}}.question-body{{padding-left:14px}}.feedback-row{{grid-template-columns:1fr;gap:3px}}.history-row{{grid-template-columns:28px 1fr}}.history-row em{{grid-column:2;text-align:left}}}}
</style></head><body><main class="wrap">
<div class="topbar"><a class="back" href="/">← 返回资料库</a><span class="updated">更新于 2026-09-23</span></div>
<header><div class="k">考研英语一 · 表达训练台账</div><h1>每日句子</h1><p>按日期保存题目、你的原答、逐项讲评与推荐表达。点开任意题目查看详情，也可以筛选待作答内容。</p></header>
<section class="stats"><div class="stat"><b>{len(full)}</b><span>完整题目</span></div><div class="stat"><b>{reviewed}</b><span>已作答讲评</span></div><div class="stat"><b>{pending}</b><span>待继续</span></div></section>
<nav class="tools" aria-label="筛选"><input class="search" id="search" type="search" placeholder="搜索题目、题型或你的答案…"><div class="filters"><button class="filter active" data-state="all">全部</button><button class="filter" data-state="reviewed">已讲评</button><button class="filter" data-state="pending">待作答</button><button class="filter" data-state="blocked">待补写</button>{date_buttons}</div></nav>
<div id="archive">{day_blocks}</div><p class="no-results" id="empty">没有符合条件的记录。</p>
<section class="history"><span class="eyebrow">HISTORICAL SUMMARY</span><h2>2026-09-10 · 待补档摘要</h2><p>当日10题已答已评，但现有记录只有主题摘要。未取得的原文不会被补写或猜测。</p>{history_rows}</section>
<footer>题目、原答与讲评均按可核对记录整理 · 后续训练会继续追加到这里</footer>
</main><script>
const qs=[...document.querySelectorAll('.question')],days=[...document.querySelectorAll('.day')],search=document.querySelector('#search'),empty=document.querySelector('#empty');let state='all',date='all';
function apply(){{const term=search.value.trim().toLowerCase();let shown=0;qs.forEach(q=>{{const okState=state==='all'||q.dataset.state===state;const okDate=date==='all'||q.closest('.day').dataset.date===date;const okText=!term||q.dataset.search.includes(term);q.hidden=!(okState&&okDate&&okText);if(!q.hidden)shown++}});days.forEach(d=>d.hidden=![...d.querySelectorAll('.question')].some(q=>!q.hidden));empty.style.display=shown?'none':'block'}}
search.addEventListener('input',apply);document.querySelectorAll('.filter').forEach(b=>b.addEventListener('click',()=>{{document.querySelectorAll('.filter').forEach(x=>x.classList.remove('active'));b.classList.add('active');state=b.dataset.state;apply()}}));document.querySelectorAll('.date-chip').forEach(b=>b.addEventListener('click',()=>{{const same=b.classList.contains('active');document.querySelectorAll('.date-chip').forEach(x=>x.classList.remove('active'));date=same?'all':b.dataset.date;if(!same)b.classList.add('active');apply()}}));
</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    days, history = parse_ledger(args.ledger)
    if sum(map(len, days.values())) != 70:
        raise SystemExit("Expected 70 complete questions in the ledger")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build(days, history), encoding="utf-8")


if __name__ == "__main__":
    main()
