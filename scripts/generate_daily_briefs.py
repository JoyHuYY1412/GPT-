#!/usr/bin/env python3
"""Generate daily Markdown briefings for GPT-learning notes.

The script runs in GitHub Actions and writes three files every day:

- daily-briefs/paper-radar/YYYY-MM-DD.md
- daily-briefs/academic-map/YYYY-MM-DD.md
- daily-briefs/related_paper-radar/YYYY-MM-DD.md

Dynamic part: it scans repo folders `context/`, `topics/`, `notes/`, and
`reading/` each day. Updating files in these folders changes the next day's
recommendations without editing the workflow YAML.
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

CONTEXT_DIRS = ["context", "topics", "notes", "reading"]
CONTEXT_EXTS = {".md", ".txt", ".yaml", ".yml"}
MAX_CONTEXT_FILES = 30
MAX_CONTEXT_CHARS = 60000

BASE_INTERESTS = [
    "multimodal perception and generation",
    "video understanding and video generation",
    "long-video reasoning",
    "video generation evaluation",
    "world models and memory mechanisms",
    "multimodal agents and embodied intelligence",
    "controllable and personalized generation",
    "retrieval-augmented generation",
    "trustworthy reasoning and evaluation",
    "AI4Science and medical multimodal modeling",
    "visual tokenization and autoregressive visual generation",
    "video editing and 3D-aware generation",
]

BASE_ARXIV_TERMS = [
    "video generation",
    "world model",
    "multimodal agent",
    "embodied intelligence",
    "long video",
    "memory",
    "controllable generation",
    "personalized generation",
    "visual reasoning",
    "video understanding",
]

WATCH_TERMS = [
    "video generation", "video understanding", "long video", "world model",
    "memory", "multimodal agent", "embodied", "robot", "vision language action",
    "VLA", "controllable generation", "personalized generation", "visual tokenization",
    "autoregressive", "diffusion", "flow matching", "evaluation", "benchmark",
    "dataset", "retrieval", "RAG", "3D", "video editing", "image editing",
    "medical", "AI4Science", "TCR", "pMHC", "protein", "agent", "workflow",
    "SAE", "sparse autoencoder", "world action", "temporal grounding",
    "foundation model", "multimodal reasoning", "tool use", "computer use",
]

KEYWORD_WEIGHTS = {
    "video": 4,
    "world model": 6,
    "multimodal": 4,
    "agent": 5,
    "memory": 4,
    "embodied": 4,
    "robot": 3,
    "controllable": 3,
    "personalized": 3,
    "long video": 4,
    "generation": 2,
    "benchmark": 3,
    "evaluation": 3,
    "retrieval": 2,
    "medical": 2,
    "visual tokenization": 4,
    "autoregressive": 3,
    "diffusion": 2,
    "3d": 2,
    "temporal grounding": 4,
}

RELATED_PAPER_POOL = [
    {
        "title": "World Models",
        "year": "2018",
        "venue": "influential world-model line",
        "link": "https://arxiv.org/abs/1803.10122",
        "project": "https://worldmodels.github.io/",
        "tags": ["world model", "memory", "agent", "latent dynamics"],
        "why": "把环境动态压缩为可预测 latent dynamics，是后续 video/world model 和 agent memory 讨论的重要起点。",
        "angle": "可作为梳理 world model memory 机制时的历史根节点。",
    },
    {
        "title": "VideoGPT: Video Generation using VQ-VAE and Transformers",
        "year": "2021",
        "venue": "autoregressive video generation",
        "link": "https://arxiv.org/abs/2104.10157",
        "project": "https://wilson1yan.github.io/videogpt/index.html",
        "tags": ["video generation", "visual tokenization", "autoregressive"],
        "why": "早期把离散视觉 token 与 transformer 视频生成结合起来，对视觉 tokenizer 和 AR video generation 有启发。",
        "angle": "适合和 JPEG-LM、xAR、UniTok、FlexTok 等视觉 tokenization 工作放在一起比较。",
    },
    {
        "title": "Perceiver IO: A General Architecture for Structured Inputs & Outputs",
        "year": "2021",
        "venue": "ICLR 2022",
        "link": "https://arxiv.org/abs/2107.14795",
        "project": "https://deepmind.google/discover/blog/building-architectures-that-can-handle-the-worlds-data/",
        "tags": ["multimodal", "long context", "latent bottleneck", "efficient perception"],
        "why": "通过 latent bottleneck 处理多模态长输入，是多模态压缩和统一输入输出架构的经典参考。",
        "angle": "可连接多模态压缩、long-context perception 和 efficient multimodal learning。",
    },
    {
        "title": "Flamingo: a Visual Language Model for Few-Shot Learning",
        "year": "2022",
        "venue": "NeurIPS 2022",
        "link": "https://arxiv.org/abs/2204.14198",
        "project": "https://www.deepmind.com/blog/tackling-multiple-tasks-with-a-single-visual-language-model",
        "tags": ["multimodal", "in-context learning", "vision language model"],
        "why": "将 frozen language model、visual resampler 和 cross-attention 结合，是多模态 in-context learning 的代表性系统。",
        "angle": "可作为 LIVE/MimIC 一类轻量 context learning 方法的背景参照。",
    },
    {
        "title": "Segment Anything",
        "year": "2023",
        "venue": "ICCV 2023",
        "link": "https://arxiv.org/abs/2304.02643",
        "project": "https://segment-anything.com/",
        "tags": ["segmentation", "mask", "foundation model", "promptable perception"],
        "why": "promptable segmentation 和大规模数据引擎改变了视觉基础模型和标注范式。",
        "angle": "可与 MTA-CLIP、mask-text alignment、text-enhanced segmentation 等方向连接。",
    },
    {
        "title": "LLaVA: Large Language and Vision Assistant",
        "year": "2023",
        "venue": "NeurIPS 2023 workshop / influential LMM project",
        "link": "https://arxiv.org/abs/2304.08485",
        "project": "https://llava-vl.github.io/",
        "tags": ["multimodal", "LMM", "instruction tuning", "visual reasoning"],
        "why": "用 instruction tuning 把视觉编码器接入 LLM，推动了 open-source LMM 生态。",
        "angle": "适合作为多模态 agent、evaluation、visual instruction tuning 的基线脉络。",
    },
    {
        "title": "VideoPoet: A Large Language Model for Zero-Shot Video Generation",
        "year": "2023/2024",
        "venue": "ICML 2024",
        "link": "https://arxiv.org/abs/2312.14125",
        "project": "https://sites.research.google/videopoet/",
        "tags": ["video generation", "autoregressive", "visual tokenization", "multimodal generation"],
        "why": "把视频生成表述为语言模型式 token prediction，连接了 AR modeling、多模态 tokenization 和视频生成。",
        "angle": "适合和 VideoFlexTok、JPEG-LM、visual codec representation 方向一起讨论。",
    },
    {
        "title": "Sora: Creating video from text",
        "year": "2024",
        "venue": "technical report",
        "link": "https://openai.com/research/video-generation-models-as-world-simulators",
        "project": "https://openai.com/sora",
        "tags": ["video generation", "world simulator", "evaluation", "long video"],
        "why": "强化了 video generation as world simulator 的叙事，推动视频生成从短片合成走向世界建模讨论。",
        "angle": "可用于 video generation 与 video evaluation 并行发展的 framing。",
    },
    {
        "title": "Movie Gen: A Cast of Media Foundation Models",
        "year": "2024",
        "venue": "technical report",
        "link": "https://arxiv.org/abs/2410.13720",
        "project": "https://ai.meta.com/research/movie-gen/",
        "tags": ["video generation", "personalized generation", "video editing", "media foundation model"],
        "why": "系统展示 text-to-video、personalized video、audio generation 和 editing 的统一媒体生成能力。",
        "angle": "贴近 personalized generation、video editing 和商业短视频创作 agent。",
    },
    {
        "title": "Genie: Generative Interactive Environments",
        "year": "2024",
        "venue": "ICML 2024",
        "link": "https://arxiv.org/abs/2402.15391",
        "project": "https://sites.google.com/view/genie-2024/",
        "tags": ["world model", "interactive environment", "video generation", "agent"],
        "why": "从无标注视频中学习可交互环境，连接视频生成、world model 和 action-conditioned simulation。",
        "angle": "可与 Matrix-Game、AIM、VAG 等 video-action/world-action model 工作串联。",
    },
    {
        "title": "GAIA: a Benchmark for General AI Assistants",
        "year": "2023/2024",
        "venue": "ICLR 2024",
        "link": "https://arxiv.org/abs/2311.12983",
        "project": "https://huggingface.co/gaia-benchmark",
        "tags": ["agent", "tool use", "benchmark", "evaluation"],
        "why": "关注通用 AI assistant 在工具使用、搜索、推理和多步骤任务中的能力。",
        "angle": "可作为多模态 agent、记忆迁移平台和工具调用系统的评估参考。",
    },
    {
        "title": "Visual Program Distillation",
        "year": "2023",
        "venue": "CVPR 2023",
        "link": "https://arxiv.org/abs/2212.03052",
        "project": "https://prior.allenai.org/projects/visprog",
        "tags": ["visual reasoning", "tool use", "program", "agent"],
        "why": "把视觉任务拆成可解释程序和工具调用，是 agentic visual reasoning 的早期重要路线。",
        "angle": "可连接验证反馈、多工具视频创作 agent 和显式中间结构。",
    },
]

ACADEMIC_MAP_POOL = [
    {
        "node": "何恺明线：从表征学习到视觉基础模型的国际影响力节点",
        "sources": ["ResNet: https://arxiv.org/abs/1512.03385", "Mask R-CNN: https://arxiv.org/abs/1703.06870", "MAE: https://arxiv.org/abs/2111.06377"],
        "lineage": "微软亚洲研究院、Facebook AI Research/Meta AI、MIT 等节点共同构成了视觉表征学习路线的核心扩散网络。",
        "people": "Ross Girshick、Kaiming He、Piotr Dollar、Xiaolong Wang、Saining Xie、Xinlei Chen 等相关合作网络。",
        "institutions": "MSRA、Meta AI、MIT、CVPR/ICCV/ECCV/NeurIPS 等。",
        "meaning": "接近这条线通常意味着接近视觉基础架构、表征学习范式和顶会方法论标准。",
    },
    {
        "node": "李飞飞线：ImageNet、视觉数据集、具身与以人为中心 AI",
        "sources": ["ImageNet: https://www.image-net.org/", "Stanford HAI: https://hai.stanford.edu/"],
        "lineage": "从大规模视觉数据集建设到以人为中心 AI，再扩展到具身智能和医疗等应用。",
        "people": "Fei-Fei Li、Olga Russakovsky、Justin Johnson、Andrej Karpathy 等相关学生/合作者网络。",
        "institutions": "Stanford、Princeton、ImageNet community、CVPR/ICCV 等。",
        "meaning": "这条线的资源优势在于数据集定义、领域议程设置和跨学科 AI 影响力。",
    },
    {
        "node": "Sergey Levine / Berkeley Robot Learning：机器人学习、离线 RL 与 embodied foundation model",
        "sources": ["BAIR: https://bair.berkeley.edu/", "RT series context: https://robotics-transformer.github.io/"],
        "lineage": "Berkeley robot learning、offline RL、language-conditioned policy 和大规模机器人数据路线。",
        "people": "Sergey Levine、Chelsea Finn、Pieter Abbeel、Aviral Kumar、Karl Pertsch 等相关网络。",
        "institutions": "UC Berkeley、BAIR、Google DeepMind/Robotics、CoRL/RSS/NeurIPS/ICLR。",
        "meaning": "这条线强调真实机器人、可扩展策略学习和具身 foundation model。",
    },
    {
        "node": "多模态大模型与开源 LMM 生态：LLaVA 系列及其扩散网络",
        "sources": ["LLaVA: https://llava-vl.github.io/", "LLaVA-NeXT: https://llava-vl.github.io/blog/2024-01-30-llava-next/"],
        "lineage": "从视觉 instruction tuning 到多图、视频、多模态 agent，推动开源 LMM benchmark 与训练范式。",
        "people": "Liu Haotian、Li Chunyuan、Yong Jae Lee、LLaVA contributors 等。",
        "institutions": "UW-Madison、Microsoft Research、UCSD、开源社区。",
        "meaning": "这条线对新方法扩散、benchmark 复用和开源生态影响很大。",
    },
    {
        "node": "视频生成与世界模拟器路线：从 diffusion video 到 interactive world model",
        "sources": ["Sora technical report: https://openai.com/research/video-generation-models-as-world-simulators", "Genie: https://sites.google.com/view/genie-2024/"],
        "lineage": "Google DeepMind、OpenAI、Meta、Runway 等机构共同推动视频生成从内容合成走向世界模拟器。",
        "people": "Tim Brooks、Bill Peebles、Google DeepMind Genie team、Meta Movie Gen team 等。",
        "institutions": "OpenAI、Google DeepMind、Meta AI、Runway、SIGGRAPH/CVPR/ICML/NeurIPS。",
        "meaning": "这条线正在重塑视频生成、视频评估和具身模拟的共同议程。",
    },
]


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def wrap(text: str, width: int = 88) -> str:
    return "\n".join(textwrap.wrap(" ".join(text.split()), width=width))


def read_dynamic_context() -> tuple[str, list[str]]:
    files: list[Path] = []
    for dirname in CONTEXT_DIRS:
        root = ROOT / dirname
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in CONTEXT_EXTS)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    chunks = []
    names = []
    total = 0
    for path in files[:MAX_CONTEXT_FILES]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not text.strip():
            continue
        rel = str(path.relative_to(ROOT))
        names.append(rel)
        chunk = f"\n\n# File: {rel}\n" + text[:8000]
        chunks.append(chunk)
        total += len(chunk)
        if total >= MAX_CONTEXT_CHARS:
            break
    return "".join(chunks), names


def extract_context_terms(context_text: str) -> list[str]:
    lower = context_text.lower()
    terms = []
    for term in WATCH_TERMS:
        if term.lower() in lower and term not in terms:
            terms.append(term)

    # Pull short English headings and bullet phrases as lightweight topic hints.
    for line in context_text.splitlines():
        line = line.strip(" #-*\t")
        if 3 <= len(line) <= 80 and re.search(r"[A-Za-z]", line):
            cleaned = re.sub(r"[:：].*$", "", line).strip()
            if 3 <= len(cleaned) <= 60 and cleaned.lower() not in {t.lower() for t in terms}:
                terms.append(cleaned)
        if len(terms) >= 20:
            break
    return terms[:20]


def context_boosted_weights(context_terms: list[str]) -> dict[str, int]:
    weights = dict(KEYWORD_WEIGHTS)
    for term in context_terms:
        key = term.lower()
        if 2 <= len(key) <= 50:
            weights[key] = max(weights.get(key, 0), 5)
    return weights


def score_text(text: str, weights: dict[str, int]) -> int:
    lower = text.lower()
    return sum(weight for kw, weight in weights.items() if kw.lower() in lower)


def fetch_arxiv(query_terms: list[str], weights: dict[str, int], max_results: int = 18) -> list[dict]:
    safe_terms = []
    for term in query_terms:
        term = term.strip()
        if not term or len(term) > 60:
            continue
        # Very long headings are poor arXiv query terms.
        if len(term.split()) > 5:
            continue
        if term.lower() not in {t.lower() for t in safe_terms}:
            safe_terms.append(term)
    safe_terms = safe_terms[:14] or BASE_ARXIV_TERMS

    query = " OR ".join(f'all:"{term}"' for term in safe_terms)
    query = f"({query}) AND (cat:cs.CV OR cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:cs.RO)"
    params = urllib.parse.urlencode({"search_query": query, "start": 0, "max_results": max_results, "sortBy": "submittedDate", "sortOrder": "descending"})
    url = f"https://export.arxiv.org/api/query?{params}"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            data = response.read()
    except Exception as exc:
        return [{"title": "arXiv fetch failed", "authors": "N/A", "summary": f"Failed to fetch arXiv feed: {exc}", "link": "https://arxiv.org/", "published": TODAY_STR, "score": 0}]

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(data)
    entries = []
    for entry in root.findall("atom:entry", ns):
        title = html.unescape(entry.findtext("atom:title", default="", namespaces=ns)).replace("\n", " ").strip()
        summary = html.unescape(entry.findtext("atom:summary", default="", namespaces=ns)).replace("\n", " ").strip()
        link = entry.findtext("atom:id", default="", namespaces=ns).strip()
        published = entry.findtext("atom:published", default="", namespaces=ns)[:10]
        authors = ", ".join(html.unescape(a.findtext("atom:name", default="", namespaces=ns)) for a in entry.findall("atom:author", ns)[:6])
        score = score_text(f"{title} {summary}", weights)
        entries.append({"title": title, "authors": authors, "summary": summary, "link": link, "published": published, "score": score})
    entries.sort(key=lambda x: (x["score"], x["published"]), reverse=True)
    return entries[:5]


def render_arxiv_radar(entries: list[dict], context_terms: list[str], context_files: list[str]) -> str:
    lines = [
        f"# 每日 arXiv 论文雷达｜{TODAY_STR}", "",
        "> 自动生成说明：本文件由 GitHub Actions 每日生成。脚本会读取 `context/`、`topics/`、`notes/`、`reading/` 中的最新内容来调整推荐方向。", "",
        "## 今日动态兴趣信号", "",
    ]
    lines.extend([f"- {t}" for t in context_terms[:10]] or ["- 暂无动态上下文，使用默认长期兴趣画像。"])
    if context_files:
        lines.extend(["", "## 参考的上下文文件", ""] + [f"- `{f}`" for f in context_files[:10]])
    lines.extend(["", "## 今日推荐", ""])
    for idx, item in enumerate(entries, 1):
        lines.extend([f"## {idx}. {item['title']}", "", f"- **链接**: {item['link'] or '链接待补'}", f"- **日期**: {item['published'] or '日期待补'}", f"- **作者**: {item['authors'] or '作者待补'}", f"- **相关度分数**: {item['score']}", "", "### 它在做什么", "", wrap(item.get("summary", "")[:900]) or "摘要待补。", "", "### 为什么值得关注", "", "这篇论文和今天 repo 上下文中的研究主题有关键词或方向重合，适合作为当天快速扫读候选。", "", "### 可进一步追问", "", "- 它和我最近更新的研究 topic 具体对应在哪里？", "- 它能否作为 related work、baseline、benchmark 或新 project seed？", "", "---", ""])
    lines.extend(["## 今日趋势总结", "", "这份雷达会随着 repo 中的研究主题文件变化而改变。若当天兴趣变了，直接更新 `context/` 或 `topics/` 下的文件即可。"])
    return "\n".join(lines)


def pick_rotating(pool: list[dict], count: int, offset: int = 0) -> list[dict]:
    if not pool:
        return []
    day_index = TODAY.toordinal() + offset
    return [pool[(day_index + i) % len(pool)] for i in range(count)]


def pick_related_by_context(context_terms: list[str], count: int = 5) -> list[dict]:
    if not context_terms:
        return pick_rotating(RELATED_PAPER_POOL, count, offset=3)
    terms = [t.lower() for t in context_terms]
    scored = []
    for i, item in enumerate(RELATED_PAPER_POOL):
        haystack = " ".join([item["title"], item["why"], item["angle"], " ".join(item.get("tags", []))]).lower()
        score = sum(1 for term in terms if term and term in haystack)
        scored.append((score, -((TODAY.toordinal() + i) % 7), item))
    scored.sort(reverse=True, key=lambda x: (x[0], x[1]))
    picked = [item for score, _, item in scored if score > 0][:count]
    if len(picked) < count:
        for item in pick_rotating(RELATED_PAPER_POOL, count, offset=7):
            if item not in picked:
                picked.append(item)
            if len(picked) >= count:
                break
    return picked[:count]


def render_related_paper_radar(context_terms: list[str], context_files: list[str]) -> str:
    items = pick_related_by_context(context_terms, 5)
    lines = [
        f"# 相关论文项目雷达｜{TODAY_STR}", "",
        "> 自动生成说明：本文件每天读取 repo 当前研究上下文后生成。重点用于补充 2018–2026 顶会顶刊/重要技术报告中的长期相关工作。", "",
        "## 今日研究 topic 信号", "",
    ]
    lines.extend([f"- {t}" for t in context_terms[:15]] or ["- 暂无动态上下文，使用默认长期兴趣画像。"])
    if context_files:
        lines.extend(["", "## 读取的上下文文件", ""] + [f"- `{f}`" for f in context_files[:15]])
    lines.extend(["", "## 今日精选", ""])
    for idx, item in enumerate(items, 1):
        lines.extend([f"## {idx}. {item['title']} ({item['year']})", "", f"- **Venue/类型**: {item['venue']}", f"- **论文链接**: {item['link'] or '链接待补'}", f"- **项目/代码链接**: {item['project'] or '链接待补'}", f"- **匹配标签**: {', '.join(item.get('tags', []))}", "", "### 为什么和我当前研究相关", "", item["why"], "", "### 可以延展成我自己工作的角度", "", item["angle"], "", "---", ""])
    lines.extend(["## 简短趋势总结", "", "这份 related-paper radar 不需要每天改 YAML。你只要更新 `context/`、`topics/`、`notes/` 或 `reading/` 文件夹，下一次自动任务就会把这些内容作为兴趣依据。"])
    return "\n".join(lines)


def render_academic_map() -> str:
    item = pick_rotating(ACADEMIC_MAP_POOL, 1, offset=11)[0]
    lines = [f"# 学术圈地图｜{TODAY_STR}", "", "> 自动生成说明：本文件用于长期积累 AI/CV/多模态相关学术网络观察。自动版本偏结构化提示，具体关系需要人工核验。", "", f"## 1. 今日核心人物或节点\n\n{item['node']}", "", "## 2. 影响力来源", ""]
    lines.extend([f"- {source}" for source in item["sources"]])
    lines.extend(["", "## 3. 学术谱系与合作线", "", item["lineage"], "", "## 4. 关键学生、合作者或强关联人物", "", item["people"], "", "## 5. 强关联机构、会议、期刊或平台", "", item["institutions"], "", "## 6. 接近这条线在实践中意味着什么", "", item["meaning"], "", "## 7. 社交场景解码", "", "这类节点通常不是只靠单篇论文产生影响，而是通过方法范式、数据集、benchmark、开源生态、学生扩散和会议组织共同形成长期议程设置能力。", "", "## 8. 极简总结", "", "今天的节点适合作为理解 AI/CV/多模态研究版图中的一个结构性入口。", "", "## 9. 评分", "", "- 论文影响力：4/5", "- 学生扩散：4/5", "- 组织控制：3/5", "- 平台资源：4/5", "- 跨圈连接：4/5", "", "## 今日新增地图信息", "", "本条目补充了一个可用于长期追踪的学术网络节点。"])
    return "\n".join(lines)


def main() -> None:
    context_text, context_files = read_dynamic_context()
    context_terms = extract_context_terms(context_text)
    weights = context_boosted_weights(context_terms)
    arxiv_terms = BASE_ARXIV_TERMS + context_terms
    entries = fetch_arxiv(arxiv_terms, weights)

    write(ROOT / "daily-briefs" / "paper-radar" / f"{TODAY_STR}.md", render_arxiv_radar(entries, context_terms, context_files))
    write(ROOT / "daily-briefs" / "related_paper-radar" / f"{TODAY_STR}.md", render_related_paper_radar(context_terms, context_files))
    write(ROOT / "daily-briefs" / "academic-map" / f"{TODAY_STR}.md", render_academic_map())


if __name__ == "__main__":
    main()
