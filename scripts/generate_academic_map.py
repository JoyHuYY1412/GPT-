#!/usr/bin/env python3
"""Generate a richer Chinese academic-circle intelligence map.

Output:
- daily-briefs/academic-map/YYYY-MM-DD.md

This stream is not a normal biography. It is a structured map of a person's
position in China's AI and interdisciplinary academic circle: lineage, platform,
student/collaborator network, societies, committees, and social-scene decoding.

Important: this script is a curated-profile generator. It does not browse the
web at runtime, so uncertain relationships must be marked as 待核实.
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
RECENT_DAYS = 30

PROFILES = [
    {
        "name": "王飞跃",
        "identity": "中国科学院自动化研究所复杂系统与智能科学方向的重要学者，长期推动平行系统、ACP 理论、智能交通和社会计算等系统工程路线。",
        "type": "方法论 + 国家级研究平台 + 系统工程路线",
        "sources": [
            "中国科学院自动化研究所相关主页（建议后续人工核验具体任职）：http://www.ia.cas.cn/",
            "IEEE Xplore / Google Scholar 中 ACP、Parallel Intelligence、Intelligent Transportation Systems 相关论文",
            "中国自动化学会及智能交通相关学会/会议公开信息（具体职务以官网为准）",
        ],
        "influence_ranked": [
            ("方法论定义权", "提出并长期推动 Artificial societies, Computational experiments, Parallel execution，即 ACP / 平行系统框架，在智能交通、城市计算、社会计算等领域形成统一叙事。"),
            ("国家级研究平台", "长期依托中科院自动化所和复杂系统相关平台，影响力更偏系统工程与国家项目体系，而不是单一论文社区。"),
            ("跨领域整合", "将 AI、控制、交通、城市系统、社会系统放在一个复杂系统框架中处理，形成区别于纯模型派的路线。"),
            ("学会与期刊网络", "在自动化、智能系统、智能交通等工程和系统科学圈层中持续出现，具体职务以官方信息为准。"),
        ],
        "lineage": [
            "博士训练与海外控制/系统科学体系有关，公开资料显示其学术背景与系统工程、控制和智能系统紧密相关；具体导师关系需要逐项核验。",
            "长期任职与主要学术平台集中在中国科学院自动化所。",
            "这条线不是 AI 子领域细分，而是把 AI 作为复杂系统运行的一部分来组织。",
        ],
        "people": [
            ("李德毅", "同属自动化/智能系统顶层网络的重要人物，非学生关系，属于相邻体系参照。"),
            ("王京", "平行交通/智能交通方向强关联人物，具体师承关系待核实。"),
            ("自动化所复杂系统团队多名 PI", "项目型共同体扩散节点，适合后续按课题组和项目进一步拆。"),
            ("智能交通/智慧城市项目负责人群体", "跨机构项目网络，很多关系来自项目合作而非传统导师-学生。"),
            ("社会计算与群体智能方向合作者", "强关联共同体，具体名单需结合论文和项目进一步核验。"),
        ],
        "orgs": [
            "中国科学院自动化研究所",
            "复杂系统管理与控制相关平台/实验室（具体名称和沿革待核实）",
            "中国自动化学会及其相关分支",
            "智能交通、智慧城市、社会计算相关国家项目体系",
            "自动化、控制、智能系统相关期刊与会议网络",
        ],
        "reality": [
            "靠近这条线通常意味着更接近国家级大型系统工程项目，而不是只靠单点论文驱动。",
            "研究问题往往是交通、城市、群体行为和复杂决策系统，而不是单个模型 benchmark。",
            "论文影响力未必总以 CVPR/NeurIPS 等会场显性体现，但系统工程和平台资源影响较大。",
            "在中文学术场合提到“平行系统/ACP”时，通常是在标识复杂系统方法论圈，而不是纯 AI 模型圈。",
        ],
        "scenes": [
            ("他做平行系统/ACP 那套", "通常意味着属于复杂系统方法论圈，关注系统级智能，而非单纯模型性能。"),
            ("自动化所那边的系统团队", "多半指参与国家级工程项目、复杂系统和智能控制相关课题的研究群体。"),
            ("偏交通/城市/社会计算", "实际是在说研究对象是复杂系统和基础设施层面的智能应用。"),
            ("论文不一定多但项目很多", "在这条线里常是正面评价，代表资源、平台和工程落地能力。"),
        ],
        "summary": {
            "one_line": "王飞跃这条线的核心不是做更强的模型，而是让 AI 成为复杂系统运行的一部分。",
            "names": ["李德毅", "王京（待核实）", "中科院自动化所复杂系统团队"],
            "orgs": ["中科院自动化所", "中国自动化学会", "智能交通/智慧城市项目体系"],
            "mnemonic": "平行系统、自动化所、智能交通。",
            "when_to_know": "当你参加自动化、智能交通、智慧城市、复杂系统、社会计算相关中文会议或项目讨论时，应该知道这条线。",
        },
        "scores": {
            "论文影响力": (3.5, "论文影响力更多体现在系统科学和智能交通等圈层，不完全按 AI 顶会引用来衡量。"),
            "学生网络扩散力": (3.5, "公开导师-学生链条不如传统学院派清晰，更像项目型团队和系统工程共同体扩散。"),
            "学会组织控制力": (4.5, "在自动化、智能系统、智能交通相关学会和期刊网络中具有持续存在感，具体职位需以官网核验。"),
            "平台资源掌控力": (5, "依托中科院自动化所和国家级系统工程平台，平台资源是其核心影响力来源之一。"),
            "跨圈层连接能力": (4.5, "能连接 AI、控制、交通、城市治理、社会系统和工程项目。"),
        },
        "new_map": "这次补上的是“方法论 + 国家级平台 + 系统工程”路线，区别于论文圈、视觉圈或公司扩散型路线。",
    },
    {
        "name": "胡事民",
        "identity": "清华大学计算机图形学与几何处理方向的重要学者，是国内图形学、CAD/几何建模、视觉计算与数字内容方向的关键人物之一。",
        "type": "图形学平台型 + 学术谱系扩散型",
        "sources": [
            "清华大学计算机系/图形学相关实验室主页（建议核验）：https://www.cs.tsinghua.edu.cn/",
            "清华大学学者主页和 Google Scholar / DBLP 论文记录",
            "中国图象图形学学会、CAD/CG、SIGGRAPH/TOG 相关公开信息",
        ],
        "influence_ranked": [
            ("学术成果", "长期在 geometry processing、CAD、图形建模、数字几何处理等方向有代表性成果。"),
            ("清华平台", "清华计算机和图形学平台提供稳定的学生来源、项目资源和国内外合作可见度。"),
            ("学生网络", "图形学方向学生和合作者在高校、研究院、产业界有扩散，具体名单需逐项核验。"),
            ("国际会议/期刊连接", "与 SIGGRAPH、TOG、CAD/CG、图形学和图像图形相关会议期刊有长期连接。"),
        ],
        "lineage": [
            "属于清华计算机图形学/几何处理谱系，是国内图形学体系的重要节点。",
            "上游更接近计算机图形学、CAD、几何建模和视觉计算传统。",
            "下游延伸到图形学高校团队、数字内容生成、三维建模、几何学习和产业图形系统。",
        ],
        "people": [
            ("清华图形学方向多名博士/青年教师", "明确学生名单需结合主页核验，但这条线的扩散主要通过清华图形学训练体系。"),
            ("国内 CAD/CG 与图形学社区中生代 PI", "强关联共同体，关系类型需逐项核验。"),
            ("数字内容与三维视觉产业界技术负责人", "可能存在学生或合作者扩散，具体关系待核实。"),
            ("图像图形学会相关组织成员", "组织共同体强关联，非必然师生。"),
            ("清华计算机图形学实验室合作者", "长期合作线，具体论文作者关系可后续展开。"),
        ],
        "orgs": [
            "清华大学计算机系",
            "中国图象图形学学会相关分支",
            "CAD/CG、SIGGRAPH Asia、TOG、计算机辅助设计与图形学相关期刊会议",
            "三维建模、数字内容、工业软件相关项目网络",
        ],
        "reality": [
            "靠近这条线通常意味着进入国内图形学和几何处理的核心训练体系。",
            "这条线在 AI 大模型语境下的价值正在重新显现，因为 3D generation、NeRF/Gaussian、几何一致性都需要图形学底层能力。",
            "对青年老师来说，图形学线的组织资源常体现在会议、期刊、学会和产业项目，而不只在 AI 顶会。",
        ],
        "scenes": [
            ("他是清华图形学那边出来的", "通常意味着有较强几何、图形系统和建模训练背景。"),
            ("这个工作更像图形学而不是 CV", "通常暗示评价标准偏几何正确性、渲染质量和系统完整性，而不是只看 benchmark 分数。"),
            ("他们在 CAD/CG 那个圈子很熟", "说明其组织网络可能在图形学中文会议和期刊体系内更强。"),
            ("做 3D 生成还是得懂图形学", "这类话通常是在强调图形学谱系在生成式 AI 时代的重新价值。"),
        ],
        "summary": {
            "one_line": "胡事民代表的是国内图形学/几何处理的清华平台型谱系。",
            "names": ["清华图形学团队", "CAD/CG 社区", "图像图形学会相关成员"],
            "orgs": ["清华大学计算机系", "中国图象图形学学会", "CAD/CG/SIGGRAPH/TOG 圈层"],
            "mnemonic": "清华图形学、几何处理、三维内容。",
            "when_to_know": "当你做 3D generation、几何一致性、图形学交叉项目或参加图像图形类会议时，应该知道这条线。",
        },
        "scores": {
            "论文影响力": (4.5, "在图形学和几何处理方向长期有代表性成果。"),
            "学生网络扩散力": (4, "清华图形学训练体系具备较强扩散，但具体学生链条需逐项核验。"),
            "学会组织控制力": (4, "与国内图形学和图像图形组织网络高度相关。"),
            "平台资源掌控力": (4.5, "清华平台和图形学方向积累带来强资源优势。"),
            "跨圈层连接能力": (4, "能连接图形学、视觉计算、工业软件、3D 内容和生成式 AI。"),
        },
        "new_map": "这次补上的是清华图形学/几何处理路线，区别于视觉识别或自动化系统工程路线。",
    },
    {
        "name": "刘成林",
        "identity": "中国科学院自动化研究所模式识别与文档分析方向的重要学者，长期深耕手写识别、模式识别、文档智能和 OCR 相关方向。",
        "type": "模式识别传统 + 中科院平台 + 任务型技术积累",
        "sources": [
            "中科院自动化所模式识别相关主页：http://www.ia.cas.cn/",
            "中国科学院大学/自动化所公开简介（具体头衔以官网为准）",
            "IAPR、ICDAR、模式识别和文档分析相关会议期刊公开信息",
        ],
        "influence_ranked": [
            ("长期任务深耕", "在手写识别、文档分析、模式识别等方向长期积累，属于任务型技术路线。"),
            ("中科院自动化所平台", "依托自动化所模式识别传统和研究生培养体系。"),
            ("国际文档分析社区", "与 ICDAR、IAPR、Pattern Recognition 等模式识别/文档分析圈层关系紧密。"),
            ("学生与工程扩散", "OCR、文档智能和模式识别人才可向高校和产业界扩散，具体学生关系需核验。"),
        ],
        "lineage": [
            "属于中科院自动化所模式识别传统，是中国模式识别和文档分析方向的重要节点。",
            "这条线与 CV 主流目标检测/分割不同，更强调字符、文档、手写体、结构化识别等任务。",
            "在大模型时代，该线可连接 OCR、document AI、视觉语言文档理解和多模态信息抽取。",
        ],
        "people": [
            ("自动化所模式识别团队学生", "明确学生关系需逐项核验。"),
            ("ICDAR/OCR 方向国内研究者", "强任务共同体，可能是合作者或同领域人员。"),
            ("文档智能产业界技术负责人", "可能由 OCR/文档分析方向扩散，具体关系待核实。"),
            ("中科院模式识别国家重点方向相关成员", "同平台/同体系人物，非必然师生。"),
            ("中文手写识别与场景文字识别研究群体", "任务方向强关联。"),
        ],
        "orgs": [
            "中科院自动化所",
            "模式识别相关国家级/院级平台",
            "IAPR、ICDAR、Pattern Recognition、DAS 等文档分析会议期刊",
            "中文 OCR、文档智能、票据识别、信息抽取产业生态",
        ],
        "reality": [
            "这条线的现实意义在于任务长期性和工程落地，而不是短期热点。",
            "在中文语境里，OCR/文档智能方向的人脉常跨越高校、研究所和产业应用。",
            "对多模态大模型来说，文档理解和 OCR 是非常基础但经常被低估的能力入口。",
        ],
        "scenes": [
            ("他是自动化所模式识别那边的", "通常意味着偏传统 pattern recognition 和长期任务积累，而不是新兴大模型流量路线。"),
            ("做 OCR/文档这个方向国内都认识", "说明这个圈子小而稳定，会议和评审网络比较集中。"),
            ("ICDAR 那条线", "通常指文档分析、手写识别、OCR 的国际共同体。"),
            ("这个方向论文不一定最热但很能落地", "通常是对文档智能和 OCR 工程价值的评价。"),
        ],
        "summary": {
            "one_line": "刘成林代表的是中科院自动化所模式识别和文档智能的长期任务型路线。",
            "names": ["自动化所模式识别团队", "ICDAR/OCR 社区", "文档智能产业界"],
            "orgs": ["中科院自动化所", "IAPR/ICDAR", "Pattern Recognition / 文档分析会议期刊"],
            "mnemonic": "自动化所、模式识别、文档 OCR。",
            "when_to_know": "当你接触 OCR、文档智能、多模态文档理解或传统模式识别圈时，应该知道这条线。",
        },
        "scores": {
            "论文影响力": (4, "在文档分析和模式识别方向有长期积累。"),
            "学生网络扩散力": (3.5, "学生和任务共同体扩散存在，但具体链条需核验。"),
            "学会组织控制力": (3.5, "与模式识别和文档分析社区关联较强。"),
            "平台资源掌控力": (4, "自动化所模式识别平台带来稳定资源。"),
            "跨圈层连接能力": (3.5, "连接学术 OCR、文档智能和产业落地。"),
        },
        "new_map": "这次补上的是中科院模式识别/文档智能路线，区别于图形学、视觉大模型和系统工程路线。",
    },
]


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name.strip())


def recent_names() -> set[str]:
    names: set[str] = set()
    folder = ROOT / "daily-briefs" / "academic-map"
    for offset in range(1, RECENT_DAYS + 1):
        path = folder / f"{(TODAY - dt.timedelta(days=offset)).isoformat()}.md"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pat in [r"今日人物[:：]\s*([^\n]+)", r"# 学术圈地图.*?\n\n.*?\*\*([^*]+)\*\*"]:
            m = re.search(pat, text, flags=re.S)
            if m:
                names.add(normalize_name(m.group(1)))
    return names


def pick_profile() -> dict:
    banned = recent_names()
    candidates = [p for p in PROFILES if normalize_name(p["name"]) not in banned]
    pool = candidates or PROFILES
    return pool[(TODAY.toordinal() * 7) % len(pool)]


def render_profile(p: dict) -> str:
    lines = [
        f"# 学术圈情报地图｜{TODAY_STR}",
        "",
        f"## 今日人物：{p['name']}",
        "",
        "## 1. 他是谁",
        "",
        p["identity"],
        "",
        f"**一句话定位：**{p['name']}代表的是：**{p['type']}**。",
        "",
        "### 参考来源线索",
        "",
    ]
    for s in p["sources"]:
        lines.append(f"- {s}")

    lines += ["", "## 2. 影响力来源（按结构重要性排序）", ""]
    for idx, (k, v) in enumerate(p["influence_ranked"], 1):
        lines += [f"### {idx}. {k}", "", v, ""]

    lines += ["## 3. 学术谱系与合作线", ""]
    for item in p["lineage"]:
        lines.append(f"- {item}")

    lines += ["", "## 4. 关键学生 / 强关联成员 / 圈内接班人", "", "以下区分明确学生、长期合作者、同体系人物和项目共同体成员；不确定处标注为待核实。", ""]
    for name, desc in p["people"]:
        lines.append(f"- **{name}**：{desc}")

    lines += ["", "## 5. 这条线在哪些组织里最强", ""]
    for org in p["orgs"]:
        lines.append(f"- {org}")

    lines += ["", "## 6. 现实中的圈子含义", ""]
    for item in p["reality"]:
        lines.append(f"- {item}")

    lines += ["", "## 7. 社交场景解码", ""]
    for quote, meaning in p["scenes"]:
        lines += [f"### 场景：{quote}", "", f"👉 {meaning}", ""]

    s = p["summary"]
    lines += [
        "## 8. 超短总结", "",
        f"- **一句话定位**：{s['one_line']}",
        f"- **三个关联名字**：{', '.join(s['names'])}",
        f"- **三个关联组织**：{', '.join(s['orgs'])}",
        f"- **记忆口诀**：{s['mnemonic']}",
        f"- **最该知道他的场合**：{s['when_to_know']}",
        "",
        "## 9. 影响力拆分", "",
    ]
    for key, (score, desc) in p["scores"].items():
        lines.append(f"- **{key}：{score}/5**。{desc}")

    lines += ["", "## 和前几次相比，这次新增的圈子地图信息", "", p["new_map"], ""]
    return "\n".join(lines)


def main() -> None:
    out = ROOT / "daily-briefs" / "academic-map" / f"{TODAY_STR}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_profile(pick_profile()).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
