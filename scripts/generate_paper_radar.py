#!/usr/bin/env python3
"""Generate the daily arXiv paper radar with recent-title de-duplication.

Output:
- daily-briefs/paper-radar/YYYY-MM-DD.md

This script avoids recommending titles that appeared in the recent 7 days and
targets about 8 items per day. The generated note uses Chinese explanations by
default, while preserving English technical terms, paper titles, and links.
"""

from __future__ import annotations

import datetime as dt
import html
import re
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

TOPIC_RULES = [
    (["world model", "world models", "world simulation", "simulator"], "world model / 世界模拟", "这篇工作主要围绕世界状态建模、环境动态预测或可交互模拟展开，重点不只是生成单个结果，而是让模型维持可持续演化的世界表示。"),
    (["video generation", "text-to-video", "video diffusion", "image-to-video"], "视频生成", "这篇工作主要关注视频生成质量、时序一致性、条件控制或生成效率，适合观察当前 video generation 从画质优化走向结构化控制的趋势。"),
    (["multimodal", "vision-language", "vlm", "lmm", "large multimodal"], "多模态理解/生成", "这篇工作围绕视觉、语言或其他模态之间的对齐与推理展开，适合作为多模态大模型能力扩展或评估设计的候选。"),
    (["agent", "tool", "assistant", "planning"], "Agent / 工具使用 / 规划", "这篇工作与 agentic workflow、工具调用、多步骤规划或任务完成能力相关，重点可以看它如何定义状态、动作、反馈和评估。"),
    (["robot", "embodied", "manipulation", "vision-language-action", "vla"], "具身智能 / VLA", "这篇工作关注模型如何从感知和语言走向可执行动作，适合放入 embodied AI、VLA 或机器人基础模型脉络中理解。"),
    (["benchmark", "dataset", "evaluation", "eval"], "Benchmark / Evaluation", "这篇工作更偏数据集、评测协议或诊断框架，适合用来观察社区正在如何重新定义模型能力边界和失败模式。"),
    (["token", "tokenization", "autoregressive", "codec"], "视觉 tokenization / AR 生成", "这篇工作与视觉 token 表示、autoregressive generation 或 codec representation 相关，适合用于梳理视觉生成从 continuous diffusion 到 discrete token modeling 的路线。"),
    (["4d", "3d", "geometry", "reconstruction", "scene"], "3D/4D 几何与场景建模", "这篇工作强调几何、场景结构、相机或 3D/4D 一致性，适合关注生成模型如何从 2D 外观走向空间一致的世界表示。"),
    (["personalized", "identity", "subject", "human video"], "个性化与主体一致性", "这篇工作关注个性化生成、身份保持或主体一致性，适合连接 personalized generation、视频编辑和可控内容生产。"),
    (["reasoning", "chain", "logic", "knowledge"], "推理增强生成/理解", "这篇工作强调推理、知识约束或逻辑一致性，适合观察生成与理解模型如何从表面匹配走向显式决策过程。"),
]


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


def infer_topic(title: str, summary: str) -> tuple[str, str]:
    text = f"{title} {summary}".lower()
    for keywords, topic, description in TOPIC_RULES:
        if any(k in text for k in keywords):
            return topic, description
    return "综合 AI 研究", "这篇工作与近期 AI 研究中的模型能力扩展、任务定义或系统构建有关，适合作为当天快速扫读候选。"


def chinese_description(item: dict) -> str:
    topic, desc = infer_topic(item.get("title", ""), item.get("summary", ""))
    return (
        f"从题目和摘要关键词看，这篇论文属于 **{topic}** 方向。{desc}"
        "阅读时可以重点关注它提出了什么新的任务设定、数据构造、模型接口、训练策略或评估维度。"
    )


def chinese_value(item: dict) -> str:
    topic, _ = infer_topic(item.get("title", ""), item.get("summary", ""))
    return (
        f"它值得扫读的原因在于：它可能为 **{topic}** 提供新的系统设计或问题表述。"
        "如果方法本身不一定直接可用，也可以从其中抽取 benchmark 设计、中间表示、数据组织或失败分析的启发。"
    )


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
        topic, _ = infer_topic(title, summary)
        entries.append({"title": title, "authors": authors, "summary": summary, "link": link, "published": published, "score": score, "topic": topic})
    entries.sort(key=lambda x: (x["score"], x["published"]), reverse=True)
    return entries[:TARGET_COUNT]


def render(entries: list[dict]) -> str:
    lines = [
        f"# 每日 arXiv 论文雷达｜{TODAY_STR}", "",
        "> 自动生成说明：本栏目目标是每天推送约 8 篇近期值得扫读的论文/项目，并尽量避开近 7 天已经推荐过的标题。正文尽量使用中文描述，必要的模型名、任务名和技术术语保留英文。", "",
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
            f"- **方向判断**: {item.get('topic') or '待判断'}",
            f"- **相关度分数**: {item.get('score', 0)}", "",
            "### 它在做什么", "", chinese_description(item), "",
            "### 为什么值得扫读", "", chinese_value(item), "",
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
