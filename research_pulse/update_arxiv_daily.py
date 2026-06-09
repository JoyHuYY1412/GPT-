#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tarfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import main


DEPS_ROOT = Path(__file__).resolve().parent / ".deps"
if DEPS_ROOT.exists() and str(DEPS_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPS_ROOT))

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_EPRINT = "https://export.arxiv.org/e-print"
ARXIV_PDF = "https://arxiv.org/pdf"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
FIGURE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
DEFAULT_QUERY = (
    'all:"world model" OR all:"vision language action" OR all:"VLA" OR '
    'all:"video generation" OR all:"embodied agent" OR all:"long horizon agent"'
)
AFFILIATION_ALIASES = {
    "SJTU": "Shanghai Jiao Tong University",
    "SII": "Shanghai Innovation Institute",
    "HUST": "Huazhong University of Science and Technology",
    "SCUT": "South China University of Technology",
    "ECUST": "East China University of Science and Technology",
    "SHU": "Shanghai University",
    "NJUPT": "Nanjing University of Posts and Telecommunications",
    "RUC": "Renmin University of China",
    "FDU": "Fudan University",
    "UNC": "University of North Carolina at Chapel Hill",
}
BANNED_TAGS = {"arxiv", "daily", "agent generated", "context", "科学推理", "高影响力"}


def normalize_key(value: str) -> str:
    text = re.sub(r"https?://\S+", "", value or "")
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def arxiv_dedupe_keys(paper: dict) -> set[str]:
    keys = {f"arxiv:{paper['arxiv_id'].lower()}"}
    for value in (paper.get("links") or {}).values():
        if value:
            keys.add(f"link:{str(value).strip().lower().rstrip('/')}")
    title_key = normalize_key(paper.get("title", ""))
    authors_key = normalize_key(paper.get("authors", ""))[:80]
    if title_key:
        digest = hashlib.sha1(f"{title_key}|{authors_key}".encode("utf-8")).hexdigest()[:12]
        keys.add(f"title:{digest}")
    return keys


def existing_item_keys(conn) -> set[str]:
    keys = set()
    for row in conn.execute("SELECT title, authors, links_json, payload_json FROM items").fetchall():
        links = main.parse_json(row["links_json"], {})
        payload = main.parse_json(row["payload_json"], {})
        arxiv_id = str(payload.get("arxiv_id") or "").lower()
        if arxiv_id:
            keys.add(f"arxiv:{arxiv_id}")
        for value in links.values():
            if value:
                keys.add(f"link:{str(value).strip().lower().rstrip('/')}")
        title_key = normalize_key(row["title"])
        authors_key = normalize_key(row["authors"])[:80]
        if title_key:
            digest = hashlib.sha1(f"{title_key}|{authors_key}".encode("utf-8")).hexdigest()[:12]
            keys.add(f"title:{digest}")
    return keys


def text_of(node: ET.Element, path: str) -> str:
    value = node.findtext(path, default="", namespaces=NS)
    return re.sub(r"\s+", " ", value).strip()


def arxiv_id_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1].split("v")[0]


def fetch_arxiv(query: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max(limit * 3, limit),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    request = urllib.request.Request(
        f"{ARXIV_API}?{params}",
        headers={"User-Agent": "ResearchPulse/0.1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())
    papers = []
    for entry in root.findall("atom:entry", NS):
        abs_url = text_of(entry, "atom:id")
        arxiv_id = arxiv_id_from_url(abs_url)
        links = {"paper": abs_url, "pdf": f"https://arxiv.org/pdf/{arxiv_id}"}
        authors = ", ".join(text_of(author, "atom:name") for author in entry.findall("atom:author", NS))
        categories = [cat.attrib.get("term", "") for cat in entry.findall("atom:category", NS) if cat.attrib.get("term")]
        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title": text_of(entry, "atom:title"),
                "abstract": text_of(entry, "atom:summary"),
                "authors": authors,
                "published": text_of(entry, "atom:published")[:10],
                "updated": text_of(entry, "atom:updated")[:10],
                "primary_category": entry.find("arxiv:primary_category", NS).attrib.get("term", "") if entry.find("arxiv:primary_category", NS) is not None else "",
                "categories": categories,
                "links": links,
            }
        )
    return papers[:limit]


def parse_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def fallback_analysis(paper: dict) -> dict:
    abstract = paper["abstract"]
    first_sentence = re.split(r"(?<=[.!?。！？])\s+", abstract)[0][:220]
    tags = [paper["primary_category"] or "arXiv"]
    return {
        "score": 6,
        "summary": first_sentence or abstract[:220],
        "why": "这篇文章命中当前兴趣关键词，适合进一步判断是否和你的长期方向相关。",
        "tags": tags[:4],
        "contributions": [
            "围绕摘要中的核心问题提出新的方法或系统。",
            "需要结合正文进一步核验实验设置、数据假设和适用边界。",
            "可作为今日 arXiv 初筛候选进入精读队列。",
        ],
        "framework": [
            "从摘要抽取问题定义、方法模块和实验目标。",
            "后续需要查看 Figure 1/2 与方法章节确认具体 pipeline。",
        ],
    }


def clean_latex_text(value: str) -> str:
    text = re.sub(r"%.*", "", value)
    text = re.sub(r"\\texttt\{[^{}]*\}", "", text)
    text = re.sub(r"\\url\{[^{}]*\}", "", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", text)
    text = re.sub(r"[{}$^*_†‡\\\\]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.;")
    return text


def expand_affiliation(value: str) -> str:
    text = clean_latex_text(value)
    return AFFILIATION_ALIASES.get(text, text)


def source_texts(arxiv_id: str) -> list[str]:
    url = f"{ARXIV_EPRINT}/{arxiv_id}"
    request = urllib.request.Request(url, headers={"User-Agent": "ResearchPulse/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        blob = response.read(30_000_000)
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tar:
            return [
                tar.extractfile(m).read().decode("utf-8", "replace")
                for m in tar.getmembers()
                if m.isfile() and m.name.lower().endswith(".tex") and tar.extractfile(m)
            ]
    except tarfile.ReadError:
        try:
            return [blob.decode("utf-8", "replace")]
        except UnicodeDecodeError:
            return []


def extract_affiliations(arxiv_id: str) -> list[str]:
    try:
        texts = source_texts(arxiv_id)
    except Exception:
        return []
    affiliations: list[str] = []

    def add(value: str):
        clean = expand_affiliation(value)
        lowered = clean.lower()
        if not clean or "email" in lowered or "author" in lowered:
            return
        if any(noise in lowered for noise in ["fairmeta", "rgb", "colback", "colframe", "tblgroup", "ignore it", "metadata"]):
            return
        if len(clean) > 220:
            return
        if len(clean) < 3 or clean in affiliations:
            return
        affiliations.append(clean)

    for text in texts:
        for match in re.finditer(r"\\affiliation(?:\[[^\]]+\])?\{([^{}]+)\}", text):
            add(match.group(1))
        for match in re.finditer(r"\\institute\{(.{0,1600}?)\}", text, flags=re.S):
            chunk = match.group(1)
            for part in re.split(r"\\and|\\\\|;", chunk):
                if re.search(r"University|Institute|Laboratory|\bLab\b|School|College|Google|Meta|Microsoft|Alibaba|Tencent|GigaAI|Knowin|Tsinghua|Peking|Hong Kong|Fudan|Beihang", part, re.I):
                    add(part)
        for line in text.splitlines():
            if re.search(r"(University|Institute|Laboratory|\bLab\b|School|College|Group|Microsoft|Google|Meta|Alibaba|Tencent|GigaAI|Knowin|Tsinghua|Peking|Shanghai|Hong Kong|Fudan|Beihang|BNRist)", line, re.I):
                if "\\author" in line and "{" not in line:
                    continue
                if "@" in line:
                    continue
                line = re.sub(r"^\s*(?:\$?\^?\{?\d+\}?\$?|[0-9]+)\s*", "", line)
                for part in re.split(r"\\\\|;|,\\s*(?=(?:[0-9]+)?[A-Z][A-Za-z .&()]+(?:University|Institute|Laboratory|Lab|School|College|Group|Microsoft|Google|Meta|Alibaba|Tencent|GigaAI|Knowin))", line):
                    if re.search(r"University|Institute|Laboratory|\bLab\b|School|College|Group|Microsoft|Google|Meta|Alibaba|Tencent|GigaAI|Knowin|BNRist", part, re.I):
                        add(part)
        if affiliations:
            break
    return affiliations[:8]


def analyze_paper(paper: dict, interests: str) -> dict:
    prompt = f"""
你是 Research Pulse 的科研论文筛选助手。请只返回 JSON，不要 Markdown。

用户兴趣：
{interests}

论文：
标题：{paper['title']}
作者：{paper['authors']}
arXiv 分类：{paper['primary_category']} / {', '.join(paper['categories'][:6])}
摘要：{paper['abstract']}

请输出字段：
score: 0-10 的整数相关度，只用于 arXiv daily；10 表示非常贴合用户兴趣，0 表示基本无关
summary: 中文 2-3 句导读，讲清楚文章在解决什么问题、用了什么核心方法、得到什么关键结果
zh_abstract: 对英文摘要的忠实中文翻译，逐句覆盖原摘要的信息顺序；中文句数尽量不少于英文句数；不要压缩成短评，不要添加原摘要没有的信息；VLA、LLM、DiT、MPC、RL、3D 等常用缩写保留
why: 中文 2-3 句，具体说明为什么值得读；优先写清楚方法启发、数据/评估假设、可能迁移方向，不要写空泛评价
tags: 3-5 个中文短标签，必须是信息量高的主题/方法/任务标签；不能包含 arXiv、daily、agent generated、context，也不要包含“科学推理”“高影响力”这类空泛词；VLA、LLM、ODE、ICML 这类常用缩写可以保留
contributions: 3-5 条核心贡献，每条先用一个加粗短语概括，再用一句话解释具体做了什么
framework: 3-5 条主要框架/方法流程，每条讲清楚一个模块、数据流、训练目标或推理流程
"""
    try:
        response = main.deepseek_chat(
            [
                {"role": "system", "content": "你只输出合法 JSON。不要输出解释、代码块或前后缀。"},
                {"role": "user", "content": prompt},
            ]
        )
        data = parse_json_object(response)
    except Exception:
        data = {}
    fallback = fallback_analysis(paper)
    score = data.get("score", fallback["score"])
    try:
        score = int(round(float(score)))
    except Exception:
        score = fallback["score"]
    tags = [str(tag).strip() for tag in data.get("tags", fallback["tags"]) if str(tag).strip()]
    tags = [tag for tag in tags if tag.lower() not in BANNED_TAGS]
    return {
        "score": max(0, min(10, score)),
        "summary": str(data.get("summary") or fallback["summary"]).strip(),
        "zh_abstract": str(data.get("zh_abstract") or data.get("summary") or fallback["summary"]).strip(),
        "why": str(data.get("why") or fallback["why"]).strip(),
        "tags": tags[:5] or fallback["tags"],
        "contributions": [str(x).strip() for x in data.get("contributions", fallback["contributions"]) if str(x).strip()][:5],
        "framework": [str(x).strip() for x in data.get("framework", fallback["framework"]) if str(x).strip()][:5],
    }


def figure_sort_key(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    if re.search(r"(fig|figure)[_-]?0?1\b", name):
        return (0, name)
    if re.search(r"(fig|figure)[_-]?0?2\b", name):
        return (1, name)
    if "overview" in name or "pipeline" in name or "method" in name:
        return (2, name)
    if "fig" in name or "figure" in name:
        return (3, name)
    return (9, name)


def is_primary_figure(path: Path) -> bool:
    name = path.stem.lower()
    return bool(re.search(r"(fig|figure)[_-]?0?[12]\b", name))


def figure_explanation(index: int) -> str:
    return (
        "Figure 1 通常用来交代任务设定、系统目标或整体问题：先看输入/输出是什么，再看它把哪些能力放到同一个任务里。"
        if index == 1
        else "Figure 2 通常用来展开主要框架或关键模块：重点看数据流、模型模块、训练/推理阶段，以及每个模块解决哪个子问题。"
    )


def download_pdf(arxiv_id: str) -> bytes:
    pdf_dir = main.APP_ROOT / "tmp_pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    cache_path = pdf_dir / f"{arxiv_id.replace('.', '_')}.pdf"
    if cache_path.exists() and cache_path.stat().st_size > 10_000:
        return cache_path.read_bytes()
    request = urllib.request.Request(
        f"{ARXIV_PDF}/{arxiv_id}",
        headers={"User-Agent": "ResearchPulse/0.1"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        blob = response.read(60_000_000)
    cache_path.write_bytes(blob)
    return blob


def block_text(block: dict) -> str:
    lines = []
    for line in block.get("lines", []):
        spans = [span.get("text", "") for span in line.get("spans", [])]
        text = "".join(spans).strip()
        if text:
            lines.append(text)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def caption_pattern(index: int) -> re.Pattern:
    return re.compile(rf"^\s*(?:fig(?:ure)?\.?)\s*{index}\s*[:.\-– ]", re.I)


def text_blocks(page) -> list[dict]:
    return [
        block
        for block in page.get_text("dict").get("blocks", [])
        if block.get("type") == 0 and block_text(block)
    ]


def find_figure_caption(page, index: int):
    pattern = caption_pattern(index)
    for block in sorted(text_blocks(page), key=lambda b: (b["bbox"][1], b["bbox"][0])):
        text = block_text(block)
        if pattern.search(text):
            return block, text
    return None, ""


def horizontal_overlap(a, b) -> float:
    left = max(a[0], b[0])
    right = min(a[2], b[2])
    return max(0.0, right - left)


def choose_figure_clip(page, caption_block: dict):
    import fitz

    page_rect = page.rect
    caption = fitz.Rect(caption_block["bbox"])
    caption_box = tuple(caption)
    image_blocks = [
        fitz.Rect(block["bbox"])
        for block in page.get_text("dict").get("blocks", [])
        if block.get("type") == 1 and block.get("bbox") and block["bbox"][3] <= caption.y0 + 8
    ]
    nearby_images = [
        rect
        for rect in image_blocks
        if rect.y1 > caption.y0 - page_rect.height * 0.55
        and horizontal_overlap(tuple(rect), caption_box) > min(caption.width, rect.width) * 0.2
    ]
    if nearby_images:
        union = nearby_images[0]
        for rect in nearby_images[1:]:
            union |= rect
        x0 = max(page_rect.x0 + 18, min(union.x0, caption.x0) - 12)
        x1 = min(page_rect.x1 - 18, max(union.x1, caption.x1) + 12)
        y0 = max(page_rect.y0 + 18, union.y0 - 12)
        y1 = min(page_rect.y1 - 18, caption.y1 + 10)
        return fitz.Rect(x0, y0, x1, y1)

    full_width_caption = caption.width > page_rect.width * 0.48 or (
        caption.x0 < page_rect.width * 0.28 and caption.x1 > page_rect.width * 0.72
    )
    if full_width_caption:
        x0, x1 = page_rect.x0 + 28, page_rect.x1 - 28
    elif caption.x0 + caption.width / 2 < page_rect.width / 2:
        x0, x1 = page_rect.x0 + 28, page_rect.x0 + page_rect.width / 2 - 8
    else:
        x0, x1 = page_rect.x0 + page_rect.width / 2 + 8, page_rect.x1 - 28
    y0 = max(page_rect.y0 + 24, caption.y0 - min(360, page_rect.height * 0.48))
    y1 = min(page_rect.y1 - 18, caption.y1 + 10)
    return fitz.Rect(x0, y0, x1, y1)


def extract_pdf_figures(arxiv_id: str, title: str, limit: int = 2) -> list[dict]:
    try:
        import fitz
    except Exception:
        return []

    out_dir = main.STATIC_ROOT / "generated_figures" / arxiv_id.replace(".", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        pdf = download_pdf(arxiv_id)
        document = fitz.open(stream=pdf, filetype="pdf")
        figures = []
        for index in range(1, limit + 1):
            found = None
            caption = ""
            page_index = 0
            for page_number in range(min(len(document), 8)):
                page = document[page_number]
                caption_block, caption_text = find_figure_caption(page, index)
                if caption_block:
                    found = (page, caption_block)
                    caption = caption_text
                    page_index = page_number
                    break
            if not found:
                continue
            page, caption_block = found
            clip = choose_figure_clip(page, caption_block)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
            target = out_dir / f"figure-{index}.png"
            pix.save(target)
            figures.append(
                {
                    "url": f"/generated_figures/{arxiv_id.replace('.', '_')}/{target.name}",
                    "caption": f"PDF Figure {index}",
                    "source": "pdf",
                    "page": page_index + 1,
                    "pdf_caption": caption[:600],
                    "explanation": figure_explanation(index),
                }
            )
        document.close()
        return figures
    except Exception:
        return []


def extract_source_figures(arxiv_id: str, title: str, limit: int = 2) -> list[dict]:
    out_dir = main.STATIC_ROOT / "generated_figures" / arxiv_id.replace(".", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    url = f"{ARXIV_EPRINT}/{arxiv_id}"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "ResearchPulse/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            blob = response.read(30_000_000)
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tar:
            members = [
                m for m in tar.getmembers()
                if m.isfile() and Path(m.name).suffix.lower() in FIGURE_EXTS and not Path(m.name).name.startswith(".")
            ]
            primary_members = [member for member in members if is_primary_figure(Path(member.name))]
            chosen_pool = primary_members or members
            chosen = sorted(chosen_pool, key=lambda m: figure_sort_key(Path(m.name)))[:limit]
            figures = []
            for index, member in enumerate(chosen, 1):
                src = tar.extractfile(member)
                if not src:
                    continue
                suffix = Path(member.name).suffix.lower()
                target = out_dir / f"figure-{index}{suffix}"
                target.write_bytes(src.read())
                figures.append(
                    {
                        "url": f"/generated_figures/{arxiv_id.replace('.', '_')}/{target.name}",
                        "caption": f"{title} · Figure {index}",
                        "source": "arxiv-source",
                        "explanation": figure_explanation(index),
                    }
                )
            return figures
    except Exception:
        return []


def extract_figures(arxiv_id: str, title: str, limit: int = 2) -> list[dict]:
    pdf_figures = extract_pdf_figures(arxiv_id, title, limit)
    if pdf_figures:
        return pdf_figures[:limit]
    return extract_source_figures(arxiv_id, title, limit)


def import_papers(papers: list[dict], interests: str, replace_demo: bool) -> int:
    main.init_db()
    item_date = main.today()
    records = []
    with main.connect() as conn:
        existing_keys = existing_item_keys(conn)
        seen_keys = set()
        if replace_demo:
            conn.execute(
                """
                DELETE FROM items
                WHERE kind = 'arxiv'
                  AND item_date = ?
                  AND (
                    id LIKE '%agent-arxiv%'
                    OR json_extract(payload_json, '$.source') IN ('demo', 'fallback-local-agent-script')
                    OR json_extract(payload_json, '$.source') IS NULL
                  )
                """,
                (item_date,),
            )
        for paper in papers:
            dedupe_keys = arxiv_dedupe_keys(paper)
            if dedupe_keys & existing_keys or dedupe_keys & seen_keys:
                continue
            seen_keys.update(dedupe_keys)
            analysis = analyze_paper(paper, interests)
            figures = extract_figures(paper["arxiv_id"], paper["title"])
            affiliations = extract_affiliations(paper["arxiv_id"])
            payload = {
                "source": "arxiv-api",
                "arxiv_id": paper["arxiv_id"],
                "published": paper["published"],
                "updated": paper["updated"],
                "primary_category": paper["primary_category"],
                "categories": paper["categories"],
                "abstract": paper["abstract"],
                "original_abstract": paper["abstract"],
                "zh_abstract": analysis["zh_abstract"],
                "affiliations": affiliations,
                "primary_affiliation": affiliations[0] if affiliations else "",
                "source_badges": [affiliations[0]] if affiliations else [],
                "contributions": analysis["contributions"],
                "framework": analysis["framework"],
                "figures": figures,
                "imported_at": datetime.now(main.LOCAL_TZ).isoformat(timespec="seconds"),
            }
            item_id = f"{item_date}-arxiv-{paper['arxiv_id'].replace('.', '-')}"
            records.append(
                main.item_payload(
                    item_id,
                    "arxiv",
                    item_date,
                    paper["title"],
                    f"Submitted {paper['published']} · {paper['primary_category']}",
                    analysis["summary"],
                    analysis["score"],
                    float(analysis["score"]) / 2,
                    analysis["tags"],
                    paper["authors"],
                    "arXiv",
                    "; ".join(affiliations),
                    analysis["why"],
                    " / ".join(analysis["framework"]),
                    paper["links"],
                    payload,
                )
            )
        if records:
            conn.executemany(
                """
                INSERT INTO items(
                    id, kind, title, subtitle, summary, item_date, score, rating, tags_json,
                    authors, venue, org, why, thinking, links_json, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    subtitle = excluded.subtitle,
                    summary = excluded.summary,
                    item_date = excluded.item_date,
                    score = excluded.score,
                    rating = excluded.rating,
                    tags_json = excluded.tags_json,
                    authors = excluded.authors,
                    venue = excluded.venue,
                    org = excluded.org,
                    why = excluded.why,
                    thinking = excluded.thinking,
                    links_json = excluded.links_json,
                    payload_json = excluded.payload_json
                """,
                records,
            )
    return len(records)


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Fetch real arXiv Daily papers and enrich them for Research Pulse.")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--replace-demo", action="store_true")
    parser.add_argument("--interests", default="")
    args = parser.parse_args()
    interests = args.interests or main.default_settings()["positive_keywords"]
    papers = fetch_arxiv(args.query, args.limit)
    count = import_papers(papers, interests, args.replace_demo)
    print(json.dumps({"imported": count, "query": args.query}, ensure_ascii=False))


if __name__ == "__main__":
    main_cli()
