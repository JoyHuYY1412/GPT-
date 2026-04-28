#!/usr/bin/env python3
"""Generate daily paper archaeology notes.

This stream is intentionally independent from the user's current research
interests. It highlights 2018-2026 top-conference/top-journal papers that have
novel, unusual, or under-discussed ideas, for example importing a mathematical,
cognitive, planning, social-science, physics, or programmatic concept into a new
AI/CV/ML/NLP/robotics task.

Output:
- daily-briefs/paper-archaeology/YYYY-MM-DD.md
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Taipei")
TODAY = dt.datetime.now(TZ).date()
TODAY_STR = TODAY.isoformat()

PAPER_POOL = [
    {
        "title": "Learning to Optimize Neural Nets",
        "year": "2016/idea precursor",
        "venue": "ICML 2016",
        "link": "https://arxiv.org/abs/1606.01885",
        "project": "链接待补",
        "idea": "把优化器本身视作可学习对象，用 RNN 学习 optimization algorithm。",
        "why_novel": "虽然早于 2018，但它是许多 meta-optimizer、learned optimizer、自动训练策略工作的思想前史。",
        "why_overlooked": "现在谈 AutoML 或 test-time adaptation 时常直接讨论 scaling 或 RL，反而较少回到 learned optimizer 这一早期问题表述。",
        "angle": "适合考古“把算法过程本身作为模型学习对象”的范式。",
        "tags": ["learned optimizer", "meta-learning", "algorithm learning"],
    },
    {
        "title": "Neural Ordinary Differential Equations",
        "year": "2018",
        "venue": "NeurIPS 2018 Best Paper",
        "link": "https://arxiv.org/abs/1806.07366",
        "project": "https://github.com/rtqichen/torchdiffeq",
        "idea": "把连续时间动力系统和 ODE solver 引入深度网络结构设计。",
        "why_novel": "它不是简单加一层网络，而是把 hidden state evolution 看成可由微分方程定义的连续过程。",
        "why_overlooked": "后来 diffusion/flow matching 爆火后，很多人忘了 neural ODE 是连续建模进入深度学习主流的重要节点。",
        "angle": "适合连接 flow matching、continuous-depth network、world model dynamics。",
        "tags": ["ODE", "continuous dynamics", "flow", "world model"],
    },
    {
        "title": "Learning Latent Dynamics for Planning from Pixels",
        "year": "2019",
        "venue": "ICML 2019",
        "link": "https://arxiv.org/abs/1811.04551",
        "project": "https://planetrl.github.io/",
        "idea": "把 planning 引入 latent space，用 learned dynamics model 从像素中规划。",
        "why_novel": "它把高维视觉输入压缩为可规划的 latent dynamics，而不是直接从图像到动作。",
        "why_overlooked": "在今天 world model 讨论里经常提 Dreamer，却较少细看 PlaNet 如何奠定 latent planning 的问题结构。",
        "angle": "适合考古 world model + planning 的早期技术分叉。",
        "tags": ["planning", "world model", "latent dynamics", "RL"],
    },
    {
        "title": "Learning to Simulate Complex Physics with Graph Networks",
        "year": "2020",
        "venue": "ICML 2020",
        "link": "https://arxiv.org/abs/2002.09405",
        "project": "https://sites.google.com/view/learning-to-simulate/",
        "idea": "把物理系统中的粒子交互建模为图网络 message passing。",
        "why_novel": "它将物理仿真问题转化为可学习的 relational dynamics，并让 GNN 成为模拟器。",
        "why_overlooked": "现在很多 world model 讨论偏视频生成，这类物理结构先验路线常被低估。",
        "angle": "适合比较 neural simulator、world model、3D/robotics dynamics。",
        "tags": ["physics", "graph network", "simulation", "dynamics"],
    },
    {
        "title": "Learning to Defer to an Expert",
        "year": "2018",
        "venue": "ICML 2018",
        "link": "https://arxiv.org/abs/1805.07836",
        "project": "链接待补",
        "idea": "把“何时不回答、何时交给专家”形式化为可学习决策。",
        "why_novel": "它把医学/高风险决策中的拒答与转交专家机制引入机器学习分类系统。",
        "why_overlooked": "当前 LLM safety 里常讲 abstention，但很多讨论没有回到 defer-to-expert 的学习框架。",
        "angle": "适合连接可信 AI、medical AI、human-AI collaboration。",
        "tags": ["human-AI", "defer", "trustworthy", "medical"],
    },
    {
        "title": "Counterfactual Generative Networks",
        "year": "2018",
        "venue": "ICLR 2018",
        "link": "https://arxiv.org/abs/1701.07530",
        "project": "链接待补",
        "idea": "把 counterfactual reasoning 引入生成建模，用来分离可解释因素和反事实变化。",
        "why_novel": "早期尝试将因果/反事实思想与深度生成模型结合。",
        "why_overlooked": "后续生成模型快速转向 GAN、diffusion、LLM scaling，因果生成这条线反而显得分散。",
        "angle": "适合考古 trustworthy generation、causal editing、counterfactual explanation。",
        "tags": ["counterfactual", "causal", "generative model"],
    },
    {
        "title": "Learning to Shape Rewards using a Game of Two Partners",
        "year": "2020",
        "venue": "ICLR 2020",
        "link": "https://arxiv.org/abs/1908.09817",
        "project": "链接待补",
        "idea": "把 reward shaping 看成两个 agent 之间的协作博弈。",
        "why_novel": "将多智能体协作与 reward design 结合，提供了不同于手工 reward 的视角。",
        "why_overlooked": "现在 RLHF/RLAIF 讨论很多，但早期 reward shaping 的多智能体视角常被跳过。",
        "angle": "适合连接 agentic RL、reward design、自动反馈生成。",
        "tags": ["reward shaping", "multi-agent", "RL", "planning"],
    },
    {
        "title": "The Consciousness Prior",
        "year": "2017/idea precursor",
        "venue": "arXiv / cognitive prior",
        "link": "https://arxiv.org/abs/1709.08568",
        "project": "链接待补",
        "idea": "把认知科学中的 conscious attention / low-dimensional conscious state 作为 representation learning prior。",
        "why_novel": "它尝试从认知结构出发，约束高维表示中哪些变量进入可推理的“意识状态”。",
        "why_overlooked": "论文较早且偏概念，但与今天 sparse feature、SAE、interpretable representation 有潜在呼应。",
        "angle": "适合考古认知理论如何影响 representation learning。",
        "tags": ["cognition", "representation", "attention", "interpretability"],
    },
    {
        "title": "A Simple Neural Attentive Meta-Learner",
        "year": "2018",
        "venue": "ICLR 2018",
        "link": "https://arxiv.org/abs/1707.03141",
        "project": "链接待补",
        "idea": "把 memory-augmented attention 用于 meta-learning，让模型通过 attention 检索支持集。",
        "why_novel": "它在 few-shot learning 中引入了显式记忆检索结构，而不是只靠梯度快速适应。",
        "why_overlooked": "今天大家常讲 in-context learning，却较少回看早期 attention memory meta-learner。",
        "angle": "适合连接 ICL、memory、retrieval、meta-learning 的思想谱系。",
        "tags": ["meta-learning", "memory", "attention", "in-context learning"],
    },
    {
        "title": "Learning to Compose Task-Specific Tree Structures",
        "year": "2019",
        "venue": "AAAI 2019",
        "link": "https://arxiv.org/abs/1707.02786",
        "project": "链接待补",
        "idea": "把可学习树结构引入任务特定组合推理。",
        "why_novel": "它不是固定句法树，而是让模型学习对任务有用的组合结构。",
        "why_overlooked": "Transformer 统一 attention 后，很多结构化归纳偏置工作被边缘化，但这类思想仍适合复杂推理。",
        "angle": "适合考古结构化推理、neural-symbolic、compositionality。",
        "tags": ["tree", "compositionality", "reasoning", "structure"],
    },
    {
        "title": "Object-Oriented Dynamics Predictor",
        "year": "2019",
        "venue": "NeurIPS 2019",
        "link": "https://arxiv.org/abs/1906.06066",
        "project": "https://github.com/haozhiqiang/OODP",
        "idea": "把 object-oriented programming 的思想引入物体级动力学预测。",
        "why_novel": "它把场景表示为对象及其交互，而不是整体图像 latent。",
        "why_overlooked": "后续大模型更偏端到端，但 object-centric dynamics 对可解释 world model 仍然有价值。",
        "angle": "适合连接 object-centric learning、planning、video prediction。",
        "tags": ["object-centric", "dynamics", "planning", "world model"],
    },
    {
        "title": "Causal Confusion in Imitation Learning",
        "year": "2019",
        "venue": "NeurIPS 2019",
        "link": "https://arxiv.org/abs/1905.11979",
        "project": "链接待补",
        "idea": "把因果混淆概念引入 imitation learning，解释模型为何学习错误因果特征。",
        "why_novel": "它指出模仿学习中的 failure 并非只是分布偏移，也可能是因果方向和观测变量混淆。",
        "why_overlooked": "今天 VLA/robot policy 很热，但因果混淆作为失败模式没有被充分纳入评估。",
        "angle": "适合连接 robot policy、causal evaluation、spurious correlation。",
        "tags": ["causal", "imitation learning", "robot", "evaluation"],
    },
    {
        "title": "A Bayesian Perspective on Generalization and Stochastic Gradient Descent",
        "year": "2018",
        "venue": "ICLR 2018",
        "link": "https://arxiv.org/abs/1710.06451",
        "project": "链接待补",
        "idea": "用 Bayesian / PAC-Bayes 视角解释 SGD 泛化。",
        "why_novel": "将优化轨迹、后验分布和泛化误差联系起来，为理解训练动态提供理论镜头。",
        "why_overlooked": "今天很多 scaling 讨论偏经验规律，理论视角常被放到附属位置。",
        "angle": "适合考古训练稳定性、泛化、后训练中的理论解释。",
        "tags": ["Bayesian", "SGD", "generalization", "theory"],
    },
    {
        "title": "Disentangling by Factorising",
        "year": "2018",
        "venue": "ICML 2018",
        "link": "https://arxiv.org/abs/1802.05983",
        "project": "链接待补",
        "idea": "用 total correlation 分解约束 disentangled representation。",
        "why_novel": "把信息分解与生成表示学习结合，显式惩罚变量依赖。",
        "why_overlooked": "disentanglement 一度很热，后来被大模型路线淹没，但对可控生成和解释性仍有启发。",
        "angle": "适合连接 controllable generation、concept editing、interpretable latent space。",
        "tags": ["disentanglement", "information theory", "generation", "control"],
    },
    {
        "title": "Invariant Risk Minimization",
        "year": "2020",
        "venue": "arXiv / influential causal generalization line",
        "link": "https://arxiv.org/abs/1907.02893",
        "project": "https://github.com/facebookresearch/InvariantRiskMinimization",
        "idea": "把跨环境不变因果机制引入 domain generalization。",
        "why_novel": "它要求学习出的表示在不同环境下支持同一个最优分类器，从而逼近不变机制。",
        "why_overlooked": "引用不低，但很多使用者只把它当 DG baseline，忽略其理论动机和争议。",
        "angle": "适合考古 causal generalization、domain shift、robust AI。",
        "tags": ["causal", "domain generalization", "invariance", "robustness"],
    },
]


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def pick_items(count: int = 4) -> list[dict]:
    # Deterministic daily rotation, independent from user interest profile.
    start = (TODAY.toordinal() * 3) % len(PAPER_POOL)
    items = []
    for i in range(len(PAPER_POOL)):
        item = PAPER_POOL[(start + i) % len(PAPER_POOL)]
        if item not in items:
            items.append(item)
        if len(items) >= count:
            break
    return items


def render() -> str:
    items = pick_items(4)
    lines = [
        f"# 考古论文雷达｜{TODAY_STR}",
        "",
        "> 目标：每天从 2018–2026 年顶会顶刊或重要技术脉络中，挖几篇想法新奇、跨理论迁移明显、但未必已经成为高引用常识的论文。这个栏目不受当前研究兴趣限制。",
        "",
        "## 筛选偏好",
        "",
        "- 第一次或较早把某种数学、认知、规划、物理、因果、博弈、信息论、程序化思想引入新任务。",
        "- 强组或强作者的论文，但不一定是大众最熟知的爆款论文。",
        "- 引用量不一定低，但希望关注被主流叙事遮住的技术角度。",
        "- 优先给出论文链接、项目页或代码链接。",
        "",
        "## 今日考古条目",
        "",
    ]
    for idx, item in enumerate(items, 1):
        lines.extend(
            [
                f"## {idx}. {item['title']} ({item['year']})",
                "",
                f"- **Venue/类型**: {item['venue']}",
                f"- **论文链接**: {item['link']}",
                f"- **项目/代码**: {item['project']}",
                f"- **关键词**: {', '.join(item['tags'])}",
                "",
                "### 新奇点",
                "",
                item["idea"],
                "",
                "### 为什么值得考古",
                "",
                item["why_novel"],
                "",
                "### 为什么可能没被充分关注",
                "",
                item["why_overlooked"],
                "",
                "### 可延展角度",
                "",
                item["angle"],
                "",
                "---",
                "",
            ]
        )
    lines.extend(
        [
            "## 今日小结",
            "",
            "这个栏目更像是 idea mining，而不是热点追踪。建议重点看每篇论文背后的“理论迁移方式”：它把什么外部概念引入了什么 AI 任务，以及这种引入是否还能迁移到今天的大模型、多模态、生成、agent 或科学智能问题中。",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    write(ROOT / "daily-briefs" / "paper-archaeology" / f"{TODAY_STR}.md", render())
