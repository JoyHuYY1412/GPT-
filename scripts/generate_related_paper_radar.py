#!/usr/bin/env python3
"""Generate related-paper radar with recent-title de-duplication.

Output:
- daily-briefs/related_paper-radar/YYYY-MM-DD.md

This stream is for 2018-2026 top-conference/top-journal or influential project
papers related to the user's evolving research context. It targets about 8 items
and avoids titles that appeared in the recent 7 days.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")
TODAY = dt.datetime.now(TZ).date()
TODAY_STR = TODAY.isoformat()
TARGET_COUNT = 8
RECENT_DAYS = 7
CONTEXT_DIRS = ["context", "topics", "notes", "reading"]
CONTEXT_EXTS = {".md", ".txt", ".yaml", ".yml"}

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

PAPER_POOL = [
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
    {
        "title": "DreamerV3: Mastering Diverse Domains through World Models",
        "year": "2023",
        "venue": "arXiv / influential world model RL",
        "link": "https://arxiv.org/abs/2301.04104",
        "project": "https://danijar.com/project/dreamerv3/",
        "tags": ["world model", "RL", "planning", "agent"],
        "why": "展示了 world model 在多域 RL 中的通用性，是理解模型式 RL 与 agent 规划的重要节点。",
        "angle": "可用于连接 video/world model 与可执行 agent policy。",
    },
    {
        "title": "RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control",
        "year": "2023",
        "venue": "CoRL 2023 / robotics foundation model",
        "link": "https://arxiv.org/abs/2307.15818",
        "project": "https://robotics-transformer2.github.io/",
        "tags": ["VLA", "robot", "embodied", "vision language action"],
        "why": "把视觉语言模型扩展为 action-generating model，是 VLA 路线的代表工作。",
        "angle": "可作为 embodied multimodal agent 和 action grounding 的 related work。",
    },
    {
        "title": "Ego4D: Around the World in 3,000 Hours of Egocentric Video",
        "year": "2022",
        "venue": "CVPR 2022",
        "link": "https://arxiv.org/abs/2110.07058",
        "project": "https://ego4d-data.org/",
        "tags": ["egocentric video", "long video", "benchmark", "video understanding"],
        "why": "大规模第一人称视频数据集，推动长视频、记忆、交互和日常行为理解。",
        "angle": "适合作为 long-video agent perception 和 embodied understanding 的数据基础。",
    },
    {
        "title": "Video-LLaMA: An Instruction-tuned Audio-Visual Language Model for Video Understanding",
        "year": "2023",
        "venue": "EMNLP 2023 Demo / video LMM",
        "link": "https://arxiv.org/abs/2306.02858",
        "project": "https://github.com/DAMO-NLP-SG/Video-LLaMA",
        "tags": ["video understanding", "multimodal", "LMM", "instruction tuning"],
        "why": "早期 video instruction-tuned LMM 之一，连接 LLaVA 风格图像 LMM 与视频理解。",
        "angle": "可用于梳理 video-LMM 从短视频问答到长视频推理的发展线。",
    },
    {
        "title": "RoboCat: A Self-Improving Robotic Agent",
        "year": "2023",
        "venue": "technical report / robotics agent",
        "link": "https://arxiv.org/abs/2306.11706",
        "project": "https://www.deepmind.com/blog/robocat-a-self-improving-robotic-agent",
        "tags": ["robot", "agent", "self-improving", "embodied"],
        "why": "强调机器人 agent 通过数据闭环和自我改进扩展任务能力。",
        "angle": "可连接 agentic RL、反馈闭环和具身数据生成。",
    },
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
    folder = ROOT / "daily-briefs" / "related_paper-radar"
    for offset in range(1, RECENT_DAYS + 1):
        path = folder / f"{(TODAY - dt.timedelta(days=offset)).isoformat()}.md"
        if path.exists():
            titles |= extract_titles_from_md(path.read_text(encoding="utf-8", errors="ignore"))
    return titles


def read_context_terms() -> list[str]:
    text_parts = []
    for dirname in CONTEXT_DIRS:
        root = ROOT / dirname
        if root.exists():
            files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in CONTEXT_EXTS]
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for p in files[:10]:
                text_parts.append(p.read_text(encoding="utf-8", errors="ignore")[:4000])
    lower = "\n".join(text_parts).lower()
    terms = [t for t in WATCH_TERMS if t.lower() in lower]
    return terms[:20]


def select_items() -> tuple[list[dict], list[str]]:
    terms = read_context_terms()
    banned = recent_titles()
    scored = []
    for i, item in enumerate(PAPER_POOL):
        norm = normalize_title(item["title"])
        if norm in banned:
            continue
        haystack = " ".join([item["title"], item["why"], item["angle"], " ".join(item.get("tags", []))]).lower()
        score = sum(2 for t in terms if t.lower() in haystack) + sum(1 for tag in item.get("tags", []) if tag.lower() in haystack)
        # deterministic rotation tie-breaker
        rotate = -((TODAY.toordinal() + i) % len(PAPER_POOL))
        scored.append((score, rotate, item))
    scored.sort(reverse=True, key=lambda x: (x[0], x[1]))
    picked = [item for _, _, item in scored[:TARGET_COUNT]]
    if len(picked) < TARGET_COUNT:
        for item in PAPER_POOL:
            if normalize_title(item["title"]) not in banned and item not in picked:
                picked.append(item)
            if len(picked) >= TARGET_COUNT:
                break
    return picked[:TARGET_COUNT], terms


def render() -> str:
    items, terms = select_items()
    lines = [
        f"# 相关论文项目雷达｜{TODAY_STR}", "",
        "> 自动生成说明：本栏目每天读取 repo 当前研究上下文，推荐约 8 篇 2018–2026 顶会顶刊/重要项目相关工作，并尽量避开近 7 天已经推荐过的标题。", "",
        "## 今日研究 topic 信号", "",
    ]
    lines.extend([f"- {t}" for t in terms[:15]] or ["- 暂无动态上下文，使用默认长期兴趣画像。"])
    lines.extend(["", "## 今日精选", ""])
    for idx, item in enumerate(items, 1):
        lines.extend([
            f"## {idx}. {item['title']} ({item['year']})", "",
            f"- **Venue/类型**: {item['venue']}",
            f"- **论文链接**: {item['link'] or '链接待补'}",
            f"- **项目/代码链接**: {item['project'] or '链接待补'}",
            f"- **匹配标签**: {', '.join(item.get('tags', []))}", "",
            "### 为什么和我当前研究相关", "", item["why"], "",
            "### 可以延展成我自己工作的角度", "", item["angle"], "", "---", "",
        ])
    lines.extend(["## 简短趋势总结", "", "这份 related-paper radar 现在会主动扩大到约 8 篇，并跳过近 7 天重复标题。若当天同步了 GPT Project 兴趣，后续推荐会进一步贴近最新 topic。"])
    return "\n".join(lines)


def main() -> None:
    out = ROOT / "daily-briefs" / "related_paper-radar" / f"{TODAY_STR}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render().rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
