#!/usr/bin/env python3
"""Generate the daily arXiv paper radar with recent-title de-duplication.

Output:
- daily-briefs/paper-radar/YYYY-MM-DD.md

This script avoids recommending titles that appeared in the recent 7 days and
targets about 8 items per day.
"""

from __future__ import annotations

import datetime as dt
import html
import re
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")
TODAY = dt.datetime.now(TZ).date()
TODAY_STR = TODAY.isoformat()
TARGET_COUNT = 8
RECENT_DAYS = 7

QUERY_TERMS = [
    "video generation", "world model", "interactive video", "long-horizon video",
    "multimodal agent", "embodied intelligence", "video understanding",
    "multimodal reasoning", "visual generation", "video benchmark",
    "agent benchmark", "controllable generation", "personalized generation",
    "visual tokenization", "4D generation", "world simulation", "vision language action",
]

KEYWORD_WEIGHTS = {
    "video": 4, "world model": 6, "interactive": 3, "long-horizon": 4,
    "long horizon": 4, "multimodal": 4, "agent": 5, "memory": 4,
    "embodied": 4, "robot": 3, "benchmark": 3, "evaluation": 3,
    "controllable": 3, "personalized": 3, "token": 2, "4d": 3,
    "geometry": 3, "reasoning": 3, "generation": 2,
}


def normalize_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip().lower()
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", "", title)
    return title


def extract_titles_from_md(text: str) -> set[str]:
    titles: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^##\s+\d+\.\s+(.+)$", line)
        if m:
            raw = re.sub(r"\s+\([^)]*\)\s*$", "", m.group(1)).strip()
            titles.add(normalize_title(raw))
    return titles


def recent_titles() -> set[str]:
    titles: set[str] = set()
    folder = ROOT / "daily-briefs" / "paper-radar"
    for offset in range(1, RECENT_DAYS + 1):
        path = folder / f"{(TODAY - dt.timedelta(days=offset)).isoformat()}.md"
        if path.exists():
            titles |= extract_titles_from_md(path.read_text(encoding="utf-8", errors="ignore"))
    return titles


def score_text(text: str) -> int:
    lower = text.lower()
    return sum(weight for kw, weight in KEYWORD_WEIGHTS.items() if kw in lower)


def fetch_arxiv(max_results: int = 100) -> list[dict]:
    query = " OR ".join(f'all:"{term}"' for term in QUERY_TERMS)
    query = f"({query}) AND (cat:cs.CV OR cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:cs.RO OR cat:cs.MM)"
    params = urllib.parse.urlencode({
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"https://export.arxiv.org/api/query?{params}"
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            data = response.read()
    except Exception as exc:
        return [{"title": "arXiv fetch failed", "authors": "N/A", "summary": f"Failed to fetch arXiv feed: {exc}", "link": "https://arxiv.org/", "published": TODAY_STR, "score": 0}]

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(data)
    entries = []
    seen = set()
    banned = recent_titles()
    for entry in root.findall("atom:entry", ns):
        title = html.unescape(entry.findtext("atom:title", default="", namespaces=ns)).replace("\n", " ").strip()
        norm = normalize_title(title)
        if not norm or norm in seen or norm in banned:
            continue
        seen.add(norm)
        summary = html.unescape(entry.findtext("atom:summary", default="", namespaces=ns)).replace("\n", " ").strip()
        link = entry.findtext("atom:id", default="", namespaces=ns).strip()
        published = entry.findtext("atom:published", default="", namespaces=ns)[:10]
        authors = ", ".join(html.unescape(a.findtext("atom:name", default="", namespaces=ns)) for a in entry.findall("atom:author", ns)[:8])
        score = score_text(f"{title} {summary}")
        entries.append({"title": title, "authors": authors, "summary": summary, "link": link, "published": published, "score": score})
    entries.sort(key=lambda x: (x["score"], x["published"]), reverse=True)
    return entries[:TARGET_COUNT]


def wrap(text: str, width: int = 88) -> str:
    return "\n".join(textwrap.wrap(" ".join(text.split()), width=width))


def render(entries: list[dict]) -> str:
    lines = [
        f"# 每日 arXiv 论文雷达｜{TODAY_STR}", "",
        "> 自动生成说明：本栏目目标是每天推送约 8 篇近期值得扫读的论文/项目，并尽量避开近 7 天已经推荐过的标题。", "",
        "## 今日筛选规则", "",
        f"- 目标数量：约 {TARGET_COUNT} 篇",
        f"- 去重窗口：近 {RECENT_DAYS} 天 `daily-briefs/paper-radar/` 中已经出现过的标题会被跳过",
        "- 优先级：近期 arXiv + 高相关关键词 + 有明确任务/系统/benchmark 价值", "",
        "## 今日推荐", "",
    ]
    for idx, item in enumerate(entries, 1):
        lines.extend([
            f"## {idx}. {item['title']}", "",
            f"- **链接**: {item.get('link') or '链接待补'}",
            f"- **日期**: {item.get('published') or '日期待补'}",
            f"- **作者**: {item.get('authors') or '作者待补'}",
            f"- **相关度分数**: {item.get('score', 0)}", "",
            "### 它在做什么", "", wrap(item.get("summary", "")[:900]) or "摘要待补。", "",
            "### 为什么值得扫读", "",
            "这篇工作与近期多模态、视频、world model、agent、具身智能或评估方向有明显关联，适合作为当天快速浏览候选。", "",
            "### 可进一步追问", "",
            "- 它是否提供了新的任务定义、数据构造、评估维度或中间表示？",
            "- 它能否作为 related work、baseline、benchmark 或新 project seed？", "", "---", "",
        ])
    lines.extend(["## 今日趋势总结", "", "今天的 paper-radar 会主动扩大覆盖面，并跳过近期重复标题。建议从 8 篇里挑 1–2 篇深入阅读，其余作为趋势扫描和选题雷达。"])
    return "\n".join(lines)


def main() -> None:
    out = ROOT / "daily-briefs" / "paper-radar" / f"{TODAY_STR}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(fetch_arxiv()).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
