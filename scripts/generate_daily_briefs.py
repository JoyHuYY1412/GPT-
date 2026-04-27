#!/usr/bin/env python3
"""Generate daily Markdown briefings for GPT-learning notes.

This script is intentionally dependency-free so it can run inside GitHub Actions
without extra setup. It writes three daily files:

- daily-briefs/paper-radar/YYYY-MM-DD.md
- daily-briefs/academic-map/YYYY-MM-DD.md
- daily-briefs/related_paper-radar/YYYY-MM-DD.md

The arXiv radar fetches recent papers from arXiv. The academic-map and related
paper radar use curated seed pools that rotate daily. You can edit the seed pools
below to better match your current interests.
"""

from __future__ import annotations

import datetime as dt
import html
import os
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

INTERESTS = [
    "multimodal perception and generation",
    "video understanding and video generation",
    "long-video reasoning",
    "world models and memory mechanisms",
    "multimodal agents and embodied intelligence",
    "controllable and personalized generation",
    "trustworthy evaluation and diagnostic benchmarks",
    "retrieval-augmented generation",
    "AI4Science and medical multimodal modeling",
]

ARXIV_QUERY_TERMS = [
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

KEYWORD_WEIGHTS = {
    "video": 4,
    "world model": 5,
    "multimodal": 4,
    "agent": 4,
    "memory": 4,
    "embodied": 4,
    "robot": 3,
    "controllable": 3,
    "personalized": 3,
    "long": 2,
    "generation": 2,
    "benchmark": 2,
    "evaluation": 2,
    "retrieval": 2,
    "medical": 2,
}

RELATED_PAPER_POOL = [
    {
        "title": "World Models",
        "year": "2018",
        "venue": "arXiv / later influential world-model line",
        "link": "https://arxiv.org/abs/1803.10122",
        "project": "https://worldmodels.github.io/",
        "why": "把环境动态压缩为可预测 latent dynamics，是后续 video/world model 和 agent memory 讨论的重要起点。",
        "angle": "可以作为你梳理 world model memory 机制时的历史根节点。",
    },
    {
        "title": "VideoGPT: Video Generation using VQ-VAE and Transformers",
        "year": "2021",
        "venue": "arXiv / influential autoregressive video generation",
        "link": "https://arxiv.org/abs/2104.10157",
        "project": "https://wilson1yan.github.io/videogpt/index.html",
        "why": "早期把离散视觉 token 与 transformer 视频生成结合起来，对后来的 visual tokenizer 和 AR video generation 有启发。",
        "angle": "适合和 JPEG-LM、xAR、UniTok、FlexTok 等视觉 tokenization 工作放在一起比较。",
    },
    {
        "title": "Perceiver IO: A General Architecture for Structured Inputs & Outputs",
        "year": "2021",
        "venue": "ICLR 2022",
        "link": "https://arxiv.org/abs/2107.14795",
        "project": "https://deepmind.google/discover/blog/building-architectures-that-can-handle-the-worlds-data/",
        "why": "通过 latent bottleneck 处理多模态长输入，是多模态压缩、统一输入输出和高效感知模型的经典结构参考。",
        "angle": "可连接你关注的多模态压缩、long-context perception 和 efficient multimodal learning。",
    },
    {
        "title": "Flamingo: a Visual Language Model for Few-Shot Learning",
        "year": "2022",
        "venue": "NeurIPS 2022",
        "link": "https://arxiv.org/abs/2204.14198",
        "project": "https://www.deepmind.com/blog/tackling-multiple-tasks-with-a-single-visual-language-model",
        "why": "将 frozen language model、visual resampler 和 cross-attention 结合，是多模态 in-context learning 的代表性系统。",
        "angle": "可作为 LIVE/MimIC 一类轻量 context learning 方法的背景参照。",
    },
    {
        "title": "Segment Anything",
        "year": "2023",
        "venue": "ICCV 2023",
        "link": "https://arxiv.org/abs/2304.02643",
        "project": "https://segment-anything.com/",
        "why": "promptable segmentation 和大规模数据引擎极大改变了视觉基础模型和标注范式。",
        "angle": "可与 MTA-CLIP、mask-text alignment、text-enhanced segmentation 等方向连接。",
    },
    {
        "title": "LLaVA: Large Language and Vision Assistant",
        "year": "2023",
        "venue": "NeurIPS 2023 Workshop / widely influential LMM project",
        "link": "https://arxiv.org/abs/2304.08485",
        "project": "https://llava-vl.github.io/",
        "why": "用 instruction tuning 把视觉编码器接入 LLM，推动了 open-source LMM 生态。",
        "angle": "适合作为多模态 agent、evaluation、visual instruction tuning 的基线脉络。",
    },
    {
        "title": "VideoPoet: A Large Language Model for Zero-Shot Video Generation",
        "year": "2023",
        "venue": "ICML 2024",
        "link": "https://arxiv.org/abs/2312.14125",
        "project": "https://sites.research.google/videopoet/",
        "why": "把视频生成表述为语言模型式 token prediction，连接了 AR modeling、多模态 tokenization 和视频生成。",
        "angle": "适合和 VideoFlexTok、JPEG-LM、visual codec representation 方向一起讨论。",
    },
    {
        "title": "Sora: Creating video from text",
        "year": "2024",
        "venue": "OpenAI technical report",
        "link": "https://openai.com/research/video-generation-models-as-world-simulators",
        "project": "https://openai.com/sora",
        "why": "强化了 video generation as world simulator 的叙事，推动视频生成从短片合成走向世界建模讨论。",
        "angle": "可用于你 workshop 中关于 video generation 与 video evaluation 并行发展的 framing。",
    },
    {
        "title": "Movie Gen: A Cast of Media Foundation Models",
        "year": "2024",
        "venue": "arXiv / Meta AI technical report",
        "link": "https://arxiv.org/abs/2410.13720",
        "project": "https://ai.meta.com/research/movie-gen/",
        "why": "系统展示 text-to-video、personalized video、audio generation 和 editing 的统一媒体生成能力。",
        "angle": "非常贴近你关注的 personalized generation、video editing 和商业短视频创作 agent。",
    },
    {
        "title": "Genie: Generative Interactive Environments",
        "year": "2024",
        "venue": "ICML 2024",
        "link": "https://arxiv.org/abs/2402.15391",
        "project": "https://sites.google.com/view/genie-2024/",
        "why": "从无标注视频中学习可交互环境，连接视频生成、world model 和 action-conditioned simulation。",
        "angle": "可与 Matrix-Game、AIM、VAG 等 video-action/world-action model 工作串联。",
    },
    {
        "title": "GAIA: a Benchmark for General AI Assistants",
        "year": "2023",
        "venue": "ICLR 2024",
        "link": "https://arxiv.org/abs/2311.12983",
        "project": "https://huggingface.co/gaia-benchmark",
        "why": "关注通用 AI assistant 在工具使用、搜索、推理和多步骤任务中的能力。",
        "angle": "可作为你做多模态 agent、记忆迁移平台和工具调用系统时的评估参考。",
    },
    {
        "title": "Visual Program Distillation: Distilling Tools and Programmatic Reasoning into Vision-Language Models",
        "year": "2023",
        "venue": "CVPR 2023",
        "link": "https://arxiv.org/abs/2212.03052",
        "project": "https://prior.allenai.org/projects/visprog",
        "why": "把视觉任务拆成可解释程序和工具调用，是 agentic visual reasoning 的早期重要路线。",
        "angle": "可连接你关注的验证反馈、多工具视频创作 agent 和显式中间结构。",
    },
]

ACADEMIC_MAP_POOL = [
    {
        "node": "何恺明线：从表征学习到视觉基础模型的国际影响力节点",
        "sources": [
            "ResNet: https://arxiv.org/abs/1512.03385",
            "Mask R-CNN: https://arxiv.org/abs/1703.06870",
            "MAE: https://arxiv.org/abs/2111.06377",
        ],
        "lineage": "微软亚洲研究院、Facebook AI Research/Meta AI、MIT 等节点共同构成了这一视觉表征学习路线的核心扩散网络。",
        "people": "Ross Girshick、Kaiming He、Piotr Dollar、Xiaolong Wang、Saining Xie、Xinlei Chen 等相关合作网络。",
        "institutions": "MSRA、Meta AI、MIT、CVPR/ICCV/ECCV/NeurIPS 等。",
        "meaning": "接近这条线通常意味着接近视觉基础架构、表征学习范式和顶会方法论标准。",
    },
    {
        "node": "李飞飞线：ImageNet、视觉数据集、具身与以人为中心 AI",
        "sources": [
            "ImageNet: https://www.image-net.org/",
            "Stanford HAI: https://hai.stanford.edu/",
        ],
        "lineage": "从大规模视觉数据集建设到以人为中心 AI，再扩展到具身智能和医疗等应用。",
        "people": "Fei-Fei Li、Olga Russakovsky、Justin Johnson、Andrej Karpathy 等相关学生/合作者网络。",
        "institutions": "Stanford、Princeton、ImageNet community、CVPR/ICCV 等。",
        "meaning": "这条线的资源优势在于数据集定义、领域议程设置和跨学科 AI 影响力。",
    },
    {
        "node": "Sergey Levine / Berkeley Robot Learning：机器人学习、离线 RL 与 foundation agent",
        "sources": [
            "Berkeley Artificial Intelligence Research: https://bair.berkeley.edu/",
            "Robotics at Google / RT series context: https://robotics-transformer.github.io/",
        ],
        "lineage": "Berkeley robot learning、offline RL、language-conditioned policy 和大规模机器人数据路线。",
        "people": "Sergey Levine、Chelsea Finn、Pieter Abbeel、Aviral Kumar、Karl Pertsch 等相关网络。",
        "institutions": "UC Berkeley、BAIR、Google DeepMind/Robotics、CoRL/RSS/NeurIPS/ICLR。",
        "meaning": "这条线强调真实机器人、可扩展策略学习和具身 foundation model。",
    },
    {
        "node": "多模态大模型与开源 LMM 生态：LLaVA 系列及其扩散网络",
        "sources": [
            "LLaVA: https://llava-vl.github.io/",
            "LLaVA-NeXT: https://llava-vl.github.io/blog/2024-01-30-llava-next/",
        ],
        "lineage": "从视觉 instruction tuning 到多图、视频、多模态 agent，推动开源 LMM benchmark 与训练范式。",
        "people": "Liu Haotian、Li Chunyuan、Yong Jae Lee、LLaVA contributors 等。",
        "institutions": "UW-Madison、Microsoft Research、UCSD、开源社区。",
        "meaning": "这条线对新方法扩散、benchmark 复用和开源生态影响很大。",
    },
    {
        "node": "视频生成与世界模拟器路线：从 diffusion video 到 interactive world model",
        "sources": [
            "Sora technical report: https://openai.com/research/video-generation-models-as-world-simulators",
            "Genie: https://sites.google.com/view/genie-2024/",
        ],
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


def fetch_arxiv(max_results: int = 12) -> list[dict]:
    query = " OR ".join(f'all:"{term}"' for term in ARXIV_QUERY_TERMS)
    query = f"({query}) AND (cat:cs.CV OR cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:cs.RO)"
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    url = f"https://export.arxiv.org/api/query?{params}"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            data = response.read()
    except Exception as exc:  # pragma: no cover - GitHub Actions runtime fallback
        return [
            {
                "title": "arXiv fetch failed",
                "authors": "N/A",
                "summary": f"Failed to fetch arXiv feed: {exc}",
                "link": "https://arxiv.org/",
                "published": TODAY_STR,
                "score": 0,
            }
        ]

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(data)
    entries = []
    for entry in root.findall("atom:entry", ns):
        title = html.unescape(entry.findtext("atom:title", default="", namespaces=ns)).replace("\n", " ").strip()
        summary = html.unescape(entry.findtext("atom:summary", default="", namespaces=ns)).replace("\n", " ").strip()
        link = entry.findtext("atom:id", default="", namespaces=ns).strip()
        published = entry.findtext("atom:published", default="", namespaces=ns)[:10]
        authors = ", ".join(
            html.unescape(a.findtext("atom:name", default="", namespaces=ns))
            for a in entry.findall("atom:author", ns)[:6]
        )
        haystack = f"{title} {summary}".lower()
        score = sum(weight for kw, weight in KEYWORD_WEIGHTS.items() if kw in haystack)
        entries.append(
            {
                "title": title,
                "authors": authors,
                "summary": summary,
                "link": link,
                "published": published,
                "score": score,
            }
        )
    entries.sort(key=lambda x: (x["score"], x["published"]), reverse=True)
    return entries[:5]


def render_arxiv_radar(entries: list[dict]) -> str:
    lines = [
        f"# 每日 arXiv 论文雷达｜{TODAY_STR}",
        "",
        "> 自动生成说明：本文件由 GitHub Actions 每日生成。筛选偏向近期新发、与多模态、视频、world model、agent、memory、可控生成、具身智能相关的 arXiv 论文。",
        "",
        "## 今日主题",
        "",
        "今天的筛选重点是：视频生成/理解、多模态 agent、world model、memory、具身智能、可控与个性化生成。自动脚本会优先选择关键词匹配度高且最近提交的条目。",
        "",
    ]
    for idx, item in enumerate(entries, 1):
        lines.extend(
            [
                f"## {idx}. {item['title']}",
                "",
                f"- **链接**: {item['link'] or '链接待补'}",
                f"- **日期**: {item['published'] or '日期待补'}",
                f"- **作者**: {item['authors'] or '作者待补'}",
                f"- **相关度分数**: {item['score']}",
                "",
                "### 它在做什么",
                "",
                wrap(item["summary"][:900]) if item.get("summary") else "摘要待补。",
                "",
                "### 为什么值得关注",
                "",
                "这篇论文与当前兴趣中的视频/多模态/agent/world model/评估或可控生成关键词有较强重合，适合作为当天快速扫读候选。",
                "",
                "### 和我当前研究兴趣的关系",
                "",
                "可以优先从模型结构、数据构造、评估指标、可控性机制、长程一致性或 agentic workflow 角度判断是否值得深入阅读。",
                "",
                "### 可进一步追问",
                "",
                "- 这篇工作的核心技术创新是否能迁移到视频生成、视频评估或多模态 agent？",
                "- 它相比近期同类工作真正解决了什么痛点？",
                "",
                "---",
                "",
            ]
        )
    lines.extend(
        [
            "## 今日趋势总结",
            "",
            "自动筛选结果用于快速发现候选论文。建议每天从标题、摘要和链接中挑 1 到 2 篇进行人工精读，并把值得长期跟踪的论文加入 related_paper-radar 的人工精选池。",
        ]
    )
    return "\n".join(lines)


def pick_rotating(pool: list[dict], count: int, offset: int = 0) -> list[dict]:
    if not pool:
        return []
    day_index = TODAY.toordinal() + offset
    return [pool[(day_index + i) % len(pool)] for i in range(count)]


def render_related_paper_radar() -> str:
    items = pick_rotating(RELATED_PAPER_POOL, 4, offset=3)
    lines = [
        f"# 相关论文项目雷达｜{TODAY_STR}",
        "",
        "> 自动生成说明：本文件基于 repo 内置兴趣画像和精选论文池轮换生成，用于补充 2018–2026 顶会顶刊/重要技术报告中的长期相关工作。",
        "",
        "## 兴趣依据",
        "",
    ]
    for interest in INTERESTS:
        lines.append(f"- {interest}")
    lines.extend(["", "## 今日精选", ""])
    for idx, item in enumerate(items, 1):
        lines.extend(
            [
                f"## {idx}. {item['title']} ({item['year']})",
                "",
                f"- **Venue/类型**: {item['venue']}",
                f"- **论文链接**: {item['link'] or '链接待补'}",
                f"- **项目/代码链接**: {item['project'] or '链接待补'}",
                "",
                "### 为什么和我当前研究相关",
                "",
                item["why"],
                "",
                "### 可以延展成我自己工作的角度",
                "",
                item["angle"],
                "",
                "---",
                "",
            ]
        )
    lines.extend(
        [
            "## 简短趋势总结",
            "",
            "今日条目用于构建长期研究地图。建议每周人工复盘一次，把真正相关的论文归入专题：video/world model、multimodal agent、memory、controllable generation、evaluation、AI4Science。",
        ]
    )
    return "\n".join(lines)


def render_academic_map() -> str:
    item = pick_rotating(ACADEMIC_MAP_POOL, 1, offset=11)[0]
    lines = [
        f"# 学术圈地图｜{TODAY_STR}",
        "",
        "> 自动生成说明：本文件用于长期积累 AI/CV/多模态相关学术网络观察。自动版本偏结构化提示，具体人际关系需要人工核验。",
        "",
        f"## 1. 今日核心人物或节点\n\n{item['node']}",
        "",
        "## 2. 影响力来源",
        "",
    ]
    for source in item["sources"]:
        lines.append(f"- {source}")
    lines.extend(
        [
            "",
            "## 3. 学术谱系与合作线",
            "",
            item["lineage"],
            "",
            "## 4. 关键学生、合作者或强关联人物",
            "",
            item["people"],
            "",
            "## 5. 强关联机构、会议、期刊或平台",
            "",
            item["institutions"],
            "",
            "## 6. 接近这条线在实践中意味着什么",
            "",
            item["meaning"],
            "",
            "## 7. 社交场景解码",
            "",
            "这类节点通常不是只靠单篇论文产生影响，而是通过方法范式、数据集、benchmark、开源生态、学生扩散和会议组织共同形成长期议程设置能力。具体合作关系和师承关系应以公开主页、论文作者列表和机构信息进一步核验。",
            "",
            "## 8. 极简总结",
            "",
            "今天的节点适合作为理解 AI/CV/多模态研究版图中的一个结构性入口。",
            "",
            "## 9. 评分",
            "",
            "- 论文影响力：4/5",
            "- 学生扩散：4/5",
            "- 组织控制：3/5",
            "- 平台资源：4/5",
            "- 跨圈连接：4/5",
            "",
            "## 今日新增地图信息",
            "",
            "本条目补充了一个可用于长期追踪的学术网络节点，建议后续人工加入更具体的学生、合作者、项目和会议组织信息。",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    write(ROOT / "daily-briefs" / "paper-radar" / f"{TODAY_STR}.md", render_arxiv_radar(fetch_arxiv()))
    write(ROOT / "daily-briefs" / "related_paper-radar" / f"{TODAY_STR}.md", render_related_paper_radar())
    write(ROOT / "daily-briefs" / "academic-map" / f"{TODAY_STR}.md", render_academic_map())


if __name__ == "__main__":
    main()
