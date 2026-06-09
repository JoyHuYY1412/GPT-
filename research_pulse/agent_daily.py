#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import main


APP_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = APP_ROOT / "agent_outputs"
CONFIG_ROOT = APP_ROOT / "config"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def today() -> str:
    return datetime.now(LOCAL_TZ).date().isoformat()


def now_text() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_key(value: str) -> str:
    text = re.sub(r"https?://\S+", "", value or "")
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def item_dedupe_key(raw: dict) -> str:
    links = raw.get("links") or {}
    for key in ["paper", "pdf", "project", "code", "profile"]:
        value = str(links.get(key) or "").strip().lower()
        if value:
            return f"link:{value.rstrip('/')}"
    title_key = normalize_key(str(raw.get("title") or ""))
    authors_key = normalize_key(str(raw.get("authors") or ""))[:80]
    digest = hashlib.sha1(f"{title_key}|{authors_key}".encode("utf-8")).hexdigest()[:12]
    return f"title:{digest}"


def normalize_score(value, fallback: int = 0) -> int:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = float(fallback)
    if score > 10:
        score = score / 10
    return max(0, min(10, int(round(score))))


def normalize_rating(value, score: int) -> float:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        rating = score / 2
    if rating > 5:
        rating = rating / 2
    return max(0.0, min(5.0, rating))


def collect_local_context(limit: int = 16) -> dict:
    settings = main.default_settings()
    wiki = Path(settings["wiki_path"]).expanduser()
    papers = Path(settings["papers_path"]).expanduser()
    wiki_files = []
    paper_files = []
    if wiki.exists():
        for path in sorted(wiki.rglob("*")):
            if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in {".md", ".txt", ".json", ".yaml", ".yml"}:
                wiki_files.append(str(path.relative_to(wiki)))
                if len(wiki_files) >= limit:
                    break
    if papers.exists():
        for path in sorted(papers.rglob("*")):
            if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in {".pdf", ".md", ".txt"}:
                paper_files.append(str(path.relative_to(papers)))
                if len(paper_files) >= limit:
                    break
    return {"wiki_files": wiki_files, "paper_files": paper_files}


def fallback_output() -> dict:
    date = today()
    context = collect_local_context()
    return {
        "date": date,
        "source": "fallback-local-agent-script",
        "summary": "本地 fallback 不再写入占位卡片；没有真实筛选结果时保持当天模块为空。",
        "items": [],
    }


def normalize_item(raw: dict, date: str) -> tuple:
    item_id = raw.get("id") or f"{date}-{raw.get('kind', 'item')}-{abs(hash(raw.get('title', 'untitled')))}"
    kind = raw.get("kind") if raw.get("kind") in main.default_settings()["modules"] else "arxiv"
    score = normalize_score(raw.get("score"), 0)
    rating = normalize_rating(raw.get("rating"), score)
    return main.item_payload(
        item_id,
        kind,
        raw.get("date") or date,
        raw.get("title") or "Untitled Research Pulse item",
        raw.get("subtitle") or "定时更新",
        raw.get("summary") or "",
        score,
        rating,
        list(raw.get("tags") or []),
        raw.get("authors") or "",
        raw.get("venue") or "",
        raw.get("org") or "",
        raw.get("why") or "",
        raw.get("thinking") or "",
        dict(raw.get("links") or {}),
        dict(raw.get("payload") or {}),
    )


def import_output(data: dict) -> int:
    main.init_db()
    date = data.get("date") or today()
    raw_items = list(data.get("items", []))
    if not raw_items:
        return 0
    with main.connect() as conn:
        existing_keys = set()
        for row in conn.execute("SELECT id, title, authors, links_json FROM items").fetchall():
            existing_keys.add(item_dedupe_key({
                "id": row["id"],
                "title": row["title"],
                "authors": row["authors"],
                "links": main.parse_json(row["links_json"], {}),
            }))
        seen_keys = set()
        records = []
        for item in raw_items:
            dedupe_key = item_dedupe_key(item)
            if dedupe_key in seen_keys or dedupe_key in existing_keys:
                continue
            seen_keys.add(dedupe_key)
            records.append(normalize_item(item, date))
        if not records:
            return 0
        conn.executemany(
            """
            INSERT INTO items(
                id, kind, title, subtitle, summary, item_date, score, rating, tags_json,
                authors, venue, org, why, thinking, links_json, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                kind = excluded.kind,
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


def feishu_webhook() -> str:
    candidates = [
        os.environ.get("FEISHU_WEBHOOK", ""),
        os.environ.get("RESEARCH_PULSE_FEISHU_WEBHOOK", ""),
    ]
    for path in [CONFIG_ROOT / "feishu_webhook.txt", Path.home() / ".research_pulse_feishu_webhook"]:
        if path.exists():
            candidates.append(path.read_text(encoding="utf-8").strip())
    return next((value for value in candidates if value.startswith("http")), "")


def notification_text(data: dict, imported: int) -> str:
    date = data.get("date") or today()
    items = data.get("items", [])
    counts = {}
    for item in items:
        counts[item.get("kind", "other")] = counts.get(item.get("kind", "other"), 0) + 1
    lines = [
        f"Research Pulse 已更新｜{date}",
        f"更新时间：{now_text()}",
        f"写入条目：{imported}",
        "",
        "今日分类：",
    ]
    for kind, label in [
        ("arxiv", "arXiv Daily"),
        ("recent", "High Impact"),
        ("archaeology", "Paper Archaeology"),
        ("scholar", "Scholar Graph"),
        ("science", "AI for Science"),
    ]:
        lines.append(f"- {label}: {counts.get(kind, 0)}")
    lines.extend(["", "打开网站查看：http://127.0.0.1:8766"])
    if data.get("summary"):
        lines.extend(["", str(data["summary"])])
    return "\n".join(lines)


def send_feishu(text: str) -> bool:
    webhook = feishu_webhook()
    if not webhook:
        return False
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()
    return True


def main_cli() -> int:
    parser = argparse.ArgumentParser(description="Import daily agent output and optionally notify Feishu.")
    parser.add_argument("--input", type=Path, help="JSON file generated by the scheduled Codex agent.")
    parser.add_argument("--notify", action="store_true", help="Send Feishu notification when webhook is configured.")
    parser.add_argument("--notify-empty", action="store_true", help="Also notify when no new non-duplicate items were imported.")
    parser.add_argument("--fallback", action="store_true", help="Generate a fallback daily output if --input is missing.")
    args = parser.parse_args()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    input_path = args.input or OUTPUT_ROOT / f"{today()}.json"
    if input_path.exists():
        data = load_json(input_path)
    elif args.fallback:
        data = fallback_output()
        write_json(input_path, data)
    else:
        print(f"Missing agent output: {input_path}", file=sys.stderr)
        return 2

    imported = import_output(data)
    text = notification_text(data, imported)
    draft_path = OUTPUT_ROOT / f"{data.get('date') or today()}.feishu.txt"
    draft_path.write_text(text, encoding="utf-8")

    if args.notify and (imported or args.notify_empty):
        try:
            sent = send_feishu(text)
        except Exception as exc:
            print(f"Feishu notification failed: {exc}", file=sys.stderr)
            print(f"Notification draft written to {draft_path}")
            return 3
        if sent:
            print("Feishu notification sent.")
        else:
            print(f"Feishu webhook not configured. Notification draft written to {draft_path}")
    print(f"Imported {imported} Research Pulse items from {input_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
