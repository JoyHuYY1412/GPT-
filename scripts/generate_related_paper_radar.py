#!/usr/bin/env python3
"""Generate related-paper radar with recent-title de-duplication.

Output:
- daily-briefs/related_paper-radar/YYYY-MM-DD.md

Target: about 8 items. Avoid titles already appearing in the recent 7 days.
This is not the hot arXiv stream; it is a related-work stream for building a
research map around multimodal/video/world-model/agent interests.
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
    {"title":"GAIA: a Benchmark for General AI Assistants","year":"2023/2024","venue":"ICLR 2024","link":"https://arxiv.org/abs/2311.12983","project":"https://huggingface.co/gaia-benchmark","tags":["agent","tool use","benchmark","evaluation"],"why":"GAIA 将 agent 能力放到搜索、工具使用、多步骤推理和真实任务完成中评估，比普通 QA 更接近 agentic workflow。","angle":"适合作为多模态 agent、短视频创作 agent、记忆迁移系统的端到端评估参考。"},
    {"title":"Visual Program Distillation: Distilling Tools and Programmatic Reasoning into Vision-Language Models","year":"2023","venue":"CVPR 2023","link":"https://arxiv.org/abs/2212.03052","project":"https://prior.allenai.org/projects/visprog","tags":["visual reasoning","program","tool use","agent"],"why":"它把视觉推理任务拆成程序化工具调用，是 agentic visual reasoning 的重要早期路线。","angle":"可迁移到视频生成 agent 的脚本规划、素材检索、局部生成和验证反馈链路。"},
    {"title":"PaLM-E: An Embodied Multimodal Language Model","year":"2023","venue":"ICML 2023","link":"https://arxiv.org/abs/2303.03378","project":"https://palm-e.github.io/","tags":["embodied","multimodal","robot","language model"],"why":"PaLM-E 把多模态感知、语言模型和具身控制连接起来，是 embodied multimodal model 的代表节点。","angle":"适合对比 LMM、VLA、world model 三条路线如何连接感知、语言和行动。"},
    {"title":"VIMA: General Robot Manipulation with Multimodal Prompts","year":"2022/2023","venue":"ICML 2023","link":"https://arxiv.org/abs/2210.03094","project":"https://vimalabs.github.io/","tags":["robot","multimodal prompt","manipulation","generalist policy"],"why":"VIMA 将多模态 prompt 引入机器人操作任务，强调任务描述、视觉目标和动作执行之间的统一接口。","angle":"可作为 promptable embodied policy 和多模态任务条件化的 related work。"},
    {"title":"RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control","year":"2023","venue":"CoRL 2023 / robotics foundation model","link":"https://arxiv.org/abs/2307.15818","project":"https://robotics-transformer2.github.io/","tags":["VLA","robot","web knowledge","action"],"why":"RT-2 把 web-scale VLM 知识迁移到机器人动作输出，推动了 vision-language-action model 的主流叙事。","angle":"适合和 HY-Embodied、Open X-Embodiment、world-action model 放在一条谱系里。"},
    {"title":"Do As I Can, Not As I Say: Grounding Language in Robotic Affordances","year":"2022","venue":"CoRL 2022","link":"https://arxiv.org/abs/2204.01691","project":"https://say-can.github.io/","tags":["robot","affordance","planning","language grounding"],"why":"SayCan 将语言模型规划与 affordance/value function 结合，解决会说但不能做的具身落地问题。","angle":"可作为 agentic planning 中语言计划和可执行动作约束结合的经典 related work。"},
    {"title":"Ego4D: Around the World in 3,000 Hours of Egocentric Video","year":"2022","venue":"CVPR 2022","link":"https://arxiv.org/abs/2110.07058","project":"https://ego4d-data.org/","tags":["egocentric video","long video","benchmark","dataset"],"why":"Ego4D 提供大规模第一人称长视频数据和任务设置，是长视频理解、具身感知和日常活动建模的重要数据节点。","angle":"适合作为 long-video reasoning、agent perception、memory benchmark 的背景数据工作。"},
    {"title":"DreamerV3: Mastering Diverse Domains through World Models","year":"2023/2025","venue":"Nature 2025 / world model RL line","link":"https://arxiv.org/abs/2301.04104","project":"https://danijar.com/project/dreamerv3/","tags":["world model","RL","planning","latent dynamics"],"why":"DreamerV3 展示了 latent world model 在多任务 RL 中的通用性，是理解 world model 与 policy learning 结合的重要节点。","angle":"适合对比 video world model 与 latent dynamics world model 的差别。"},
    {"title":"RT-1: Robotics Transformer for Real-World Control at Scale","year":"2022","venue":"robotics foundation model line","link":"https://arxiv.org/abs/2212.06817","project":"https://robotics-transformer.github.io/","tags":["robot","transformer","real-world control","scale"],"why":"RT-1 将 transformer policy 和大规模真实机器人数据结合，是 VLA/robot foundation model 的前置节点。","angle":"可用于梳理从 language-conditioned policy 到 web-knowledge VLA 的发展。"},
    {"title":"Flamingo: a Visual Language Model for Few-Shot Learning","year":"2022","venue":"NeurIPS 2022","link":"https://arxiv.org/abs/2204.14198","project":"https://www.deepmind.com/blog/tackling-multiple-tasks-with-a-single-visual-language-model","tags":["multimodal","in-context learning","vision-language"],"why":"Flamingo 是多模态 in-context learning 和 frozen LM + visual resampler 架构的重要代表。","angle":"适合和 LIVE/MimIC 这类轻量多模态 context learning 方法形成背景对照。"},
    {"title":"Perceiver IO: A General Architecture for Structured Inputs & Outputs","year":"2021/2022","venue":"ICLR 2022","link":"https://arxiv.org/abs/2107.14795","project":"https://deepmind.google/discover/blog/building-architectures-that-can-handle-the-worlds-data/","tags":["multimodal","latent bottleneck","long context","architecture"],"why":"Perceiver IO 用 latent bottleneck 统一处理结构化输入输出，是多模态压缩和可扩展感知架构的重要参考。","angle":"适合连接 efficient multimodal learning、long-context perception 和统一输入输出空间。"},
    {"title":"Movie Gen: A Cast of Media Foundation Models","year":"2024","venue":"Meta AI technical report","link":"https://arxiv.org/abs/2410.13720","project":"https://ai.meta.com/research/movie-gen/","tags":["video generation","personalized generation","video editing","media foundation model"],"why":"Movie Gen 系统性展示了视频、音频、个性化和编辑能力的统一媒体生成路线。","angle":"适合连接 personalized video、video editing 和短视频创作 agent。"},
    {"title":"Open X-Embodiment: Robotic Learning Datasets and RT-X Models","year":"2023/2024","venue":"ICRA 2024 / robotics data scaling line","link":"https://arxiv.org/abs/2310.08864","project":"https://robotics-transformer-x.github.io/","tags":["robot","dataset","scaling","cross-embodiment"],"why":"Open X-Embodiment 强调跨机器人、跨任务数据汇聚，是 embodied foundation model 的数据基础设施节点。","angle":"适合比较多模态数据融合、跨域泛化和具身大模型训练范式。"},
]


def normalize_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip().lower()
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", "", title)
    return title


def extract_titles_from_md(text: str) -> set[str]:
    titles: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"^##\s+\d+\.\s+(.+?)(?:\s+\([^)]*\))?$", line.strip())
        if m:
            titles.add(normalize_title(m.group(1)))
    return titles


def recent_titles() -> set[str]:
    titles: set[str] = set()
    folder = ROOT / "daily-briefs" / "related_paper-radar"
    for offset in range(1, RECENT_DAYS + 1):
        path = folder / f"{(TODAY - dt.timedelta(days=offset)).isoformat()}.md"
        if path.exists():
            titles |= extract_titles_from_md(path.read_text(encoding="utf-8", errors="ignore"))
    return titles


def context_terms() -> list[str]:
    texts = []
    for dirname in CONTEXT_DIRS:
        root = ROOT / dirname
        if root.exists():
            files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in CONTEXT_EXTS]
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for p in files[:10]:
                texts.append(p.read_text(encoding="utf-8", errors="ignore")[:4000])
    lower = "\n".join(texts).lower()
    return [t for t in WATCH_TERMS if t.lower() in lower][:20]


def select_items() -> tuple[list[dict], list[str]]:
    terms = context_terms()
    banned = recent_titles()
    scored = []
    for i, item in enumerate(PAPER_POOL):
        if normalize_title(item["title"]) in banned:
            continue
        haystack = " ".join([item["title"], item["why"], item["angle"], " ".join(item.get("tags", []))]).lower()
        score = sum(2 for t in terms if t.lower() in haystack) + len(item.get("tags", []))
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
