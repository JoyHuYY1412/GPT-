#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import urllib.request
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo


APP_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = APP_ROOT.parent
STATIC_ROOT = APP_ROOT / "static"
DATA_ROOT = APP_ROOT / "data"
CONFIG_ROOT = APP_ROOT / "config"
NOTES_ROOT = APP_ROOT / "notes"
DB_PATH = DATA_ROOT / "research_pulse.db"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
SESSION_COOKIE = "rp_session"
SENSITIVE_NAME_MARKERS = ("api_key", "apikey", "secret", "token", "password", "webhook", ".env")


def now_iso() -> str:
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(LOCAL_TZ).date().isoformat()


def current_month() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m")


def json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def parse_json(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def is_inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def sensitive_roots() -> list[Path]:
    return [
        CONFIG_ROOT.resolve(),
        DATA_ROOT.resolve(),
        (APP_ROOT / "logs").resolve(),
        (APP_ROOT / "__pycache__").resolve(),
    ]


def is_sensitive_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    name = path.name.lower()
    if any(marker in name for marker in SENSITIVE_NAME_MARKERS):
        return True
    return any(is_inside(resolved, root) for root in sensitive_roots())


def safe_filename(value: str, fallback: str = "note") -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", value.strip(), flags=re.UNICODE)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip(".-")
    return (cleaned or fallback)[:96]


def user_notes_root(user: sqlite3.Row, settings: dict | None = None) -> Path:
    configured = (settings or {}).get("notes_path") or ""
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            root = (WORKSPACE_ROOT / root).resolve()
        root = root / safe_filename(user["username"], f"user-{user['id']}")
        if is_sensitive_path(root):
            root = NOTES_ROOT / safe_filename(user["username"], f"user-{user['id']}")
    else:
        root = NOTES_ROOT / safe_filename(user["username"], f"user-{user['id']}")
    root.mkdir(parents=True, exist_ok=True)
    return root


def note_markdown_path(user: sqlite3.Row, item: sqlite3.Row, title: str, settings: dict | None = None) -> Path:
    filename = f"{safe_filename(item['title'], item['id'])}.md"
    return user_notes_root(user, settings) / filename


def write_note_markdown(user: sqlite3.Row, item: sqlite3.Row, title: str, content: str, settings: dict | None = None) -> Path:
    path = note_markdown_path(user, item, title, settings)
    body = "\n".join(
        [
            "---",
            f"item_id: {item['id']}",
            f"item_title: {item['title']}",
            f"note_title: {title}",
            f"updated_at: {now_iso()}",
            "---",
            "",
            content.strip(),
            "",
        ]
    )
    path.write_text(body, encoding="utf-8")
    return path


def split_terms(value: str) -> list[str]:
    raw = value.replace("，", ",").replace("；", ",").replace(";", ",").replace("\n", ",")
    terms = []
    seen = set()
    for part in raw.split(","):
        term = part.strip()
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            terms.append(term)
    return terms


def tokenize_interest_text(value: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", value)
    stop = {"README", "index", "draft", "notes", "paper", "papers", "wiki", "raw", "json", "yaml", "txt", "pdf"}
    stop_lower = {
        "and", "are", "the", "for", "with", "from", "that", "this", "you", "your", "our", "can", "not",
        "but", "into", "about", "blog", "cache", "content", "message", "assistant", "user", "chatgpt",
        "action", "actions", "application", "applications", "answer", "question", "because", "there",
    }
    result = []
    seen = set()
    for token in tokens:
        normalized = token.strip("_-")
        key = normalized.lower()
        if re.fullmatch(r"[a-f0-9][a-f0-9\-]{7,}", key):
            continue
        if len(normalized) > 32 and "-" in normalized:
            continue
        if key in stop_lower:
            continue
        if re.fullmatch(r"[a-z]{2,3}", key) and key not in {"vae", "vla", "rag", "llm", "vlm"}:
            continue
        if normalized and key not in seen and normalized not in stop:
            seen.add(key)
            result.append(normalized)
    return result


def connect() -> sqlite3.Connection:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    rounds = 220_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), rounds)
    return f"pbkdf2_sha256${rounds}${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(rounds)
        ).hex()
        return secrets.compare_digest(digest, expected)
    except Exception:
        return False


def default_settings() -> dict:
    return {
        "modules": {"arxiv": True, "recent": True, "archaeology": True, "scholar": True, "science": True},
        "counts": {"arxiv": 10, "recent": 5, "archaeology": 6, "scholar": 1, "science": 3},
        "positive_keywords": "video generation, world model, multimodal agent, embodied intelligence, VLA, long video reasoning, controllable generation",
        "negative_keywords": "weather forecasting, remote sensing only, pure meteorology, medical-only application",
        "interest_prompt": "从我的 wiki 聊天记录、收藏论文和 papers 文件夹里抽取长期兴趣，优先推荐能启发新问题定义和方法迁移的工作。",
        "wiki_path": str(WORKSPACE_ROOT / "wiki"),
        "papers_path": str(WORKSPACE_ROOT / "papers"),
        "notes_path": str(APP_ROOT / "notes"),
    }


def row_to_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                modules_json TEXT NOT NULL,
                counts_json TEXT NOT NULL,
                positive_keywords TEXT NOT NULL,
                negative_keywords TEXT NOT NULL,
                interest_prompt TEXT NOT NULL,
                wiki_path TEXT NOT NULL,
                papers_path TEXT NOT NULL,
                notes_path TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                subtitle TEXT NOT NULL,
                summary TEXT NOT NULL,
                item_date TEXT NOT NULL,
                score INTEGER NOT NULL,
                rating REAL NOT NULL,
                tags_json TEXT NOT NULL,
                authors TEXT NOT NULL,
                venue TEXT NOT NULL,
                org TEXT NOT NULL,
                why TEXT NOT NULL,
                thinking TEXT NOT NULL,
                links_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(user_id, item_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(item_id) REFERENCES items(id)
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, item_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(item_id) REFERENCES items(id)
            );
            CREATE TABLE IF NOT EXISTS inbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'unread',
                created_at TEXT NOT NULL,
                FOREIGN KEY(sender_id) REFERENCES users(id),
                FOREIGN KEY(receiver_id) REFERENCES users(id),
                FOREIGN KEY(item_id) REFERENCES items(id)
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(item_id) REFERENCES items(id)
            );
            CREATE TABLE IF NOT EXISTS agent_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id TEXT,
                task_type TEXT NOT NULL,
                prompt TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                result TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS scholar_follows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                institution TEXT NOT NULL,
                institution_group TEXT NOT NULL,
                role_title TEXT NOT NULL,
                scholar_url TEXT NOT NULL,
                homepage_url TEXT NOT NULL,
                citations INTEGER NOT NULL DEFAULT 0,
                has_new_this_month INTEGER NOT NULL DEFAULT 0,
                last_checked_month TEXT NOT NULL,
                bio TEXT NOT NULL,
                early_focus TEXT NOT NULL,
                recent_focus TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        user_settings_columns = {row["name"] for row in conn.execute("PRAGMA table_info(user_settings)").fetchall()}
        if "notes_path" not in user_settings_columns:
            conn.execute("ALTER TABLE user_settings ADD COLUMN notes_path TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "UPDATE user_settings SET notes_path = ? WHERE notes_path = ''",
            (default_settings()["notes_path"],),
        )
        admin = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        if not admin:
            password = os.environ.get("RESEARCH_PULSE_ADMIN_PASSWORD", "Admin@2026!")
            conn.execute(
                """
                INSERT INTO users(username, email, password_hash, role, status, created_at)
                VALUES (?, ?, ?, 'admin', 'approved', ?)
                """,
                ("admin", "admin@local", hash_password(password), now_iso()),
            )
        for user in conn.execute("SELECT id FROM users").fetchall():
            ensure_settings(conn, user["id"])
        seed_items(conn)
        seed_science_items(conn)
        seed_scholar_follows(conn)


def ensure_settings(conn: sqlite3.Connection, user_id: int) -> dict:
    row = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return settings_from_row(row)
    settings = default_settings()
    conn.execute(
        """
        INSERT INTO user_settings(
            user_id, modules_json, counts_json, positive_keywords, negative_keywords,
            interest_prompt, wiki_path, papers_path, notes_path, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            json_dumps(settings["modules"]),
            json_dumps(settings["counts"]),
            settings["positive_keywords"],
            settings["negative_keywords"],
            settings["interest_prompt"],
            settings["wiki_path"],
            settings["papers_path"],
            settings["notes_path"],
            now_iso(),
        ),
    )
    return settings


def settings_from_row(row: sqlite3.Row) -> dict:
    defaults = default_settings()
    modules = defaults["modules"] | parse_json(row["modules_json"], {})
    counts = defaults["counts"] | parse_json(row["counts_json"], {})
    return {
        "modules": modules,
        "counts": counts,
        "positive_keywords": row["positive_keywords"],
        "negative_keywords": row["negative_keywords"],
        "interest_prompt": row["interest_prompt"],
        "wiki_path": row["wiki_path"],
        "papers_path": row["papers_path"],
        "notes_path": row["notes_path"] or defaults["notes_path"],
        "updated_at": row["updated_at"],
    }


def item_payload(item_id: str, kind: str, date: str, title: str, subtitle: str, summary: str,
                 score: int, rating: float, tags: list[str], authors: str, venue: str, org: str,
                 why: str, thinking: str, links: dict, payload: dict) -> tuple:
    return (
        item_id,
        kind,
        title,
        subtitle,
        summary,
        date,
        score,
        rating,
        json_dumps(tags),
        authors,
        venue,
        org,
        why,
        thinking,
        json_dumps(links),
        json_dumps(payload),
        now_iso(),
    )


def seed_items(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
    if count:
        return
    base_date = today()
    yesterday = (datetime.now(LOCAL_TZ).date() - timedelta(days=1)).isoformat()
    records = [
        item_payload(
            f"{base_date}-recent-moviegen",
            "recent",
            base_date,
            "Movie Gen: A Cast of Media Foundation Models",
            "Meta · 技术报告",
            "Meta 提出的 2024 视频/音频生成基础模型系统，覆盖 text-to-video、个性化视频、指令式视频编辑、video-to-audio 和 text-to-audio。",
            9,
            4.6,
            ["视频生成", "视频编辑", "音频生成", "个性化", "评估"],
            "Adam Polyak, Amit Zohar, Andrew Brown, Andros Tjandra, Animesh Sinha, Ann Lee, Apoorv Vyas, Bowen Shi, Chih-Yao Ma, Ching-Yao Chuang, David Yan, Dhruv Choudhary, Dingkang Wang, Geet Sethi, Guan Pang, Haoyu Ma, Ishan Misra, Ji Hou, Jialiang Wang, Kiran Jagadeesh, Kunpeng Li, Luxin Zhang, Mannat Singh, Mary Williamson, Matt Le, Matthew Yu, Mitesh Kumar Singh, Peizhao Zhang, Peter Vajda, Quentin Duval, Rohit Girdhar, Roshan Sumbaly, Sai Saketh Rambhatla, Sam Tsai, Samaneh Azadi, Samyak Datta, Sanyuan Chen, Sean Bell, Sharadh Ramaswamy, Shelly Sheynin, Siddharth Bhattacharya, Simran Motwani, Tao Xu, Tianhe Li, Tingbo Hou, Wei-Ning Hsu, Xi Yin, Xiaoliang Dai, Yaniv Taigman, Yaqiao Luo, Yen-Cheng Liu, Yi-Chiao Wu, Yue Zhao, Yuval Kirstain, Zecheng He, Zijian He, Albert Pumarola, Ali Thabet, Artsiom Sanakoyeu, Arun Mallya, Baishan Guo, Boris Araya, Breena Kerr, Carleigh Wood, Ce Liu, Cen Peng, Dimitry Vengertsev, Edgar Schonfeld, Elliot Blanchard, Felix Juefei-Xu, Fraylie Nord, Jeff Liang, John Hoffman, Jonas Kohler, Kaolin Fire, Karthik Sivakumar, Lawrence Chen, Licheng Yu, Luya Gao, Markos Georgopoulos, Rashel Moritz, Sara K. Sampson, Shikai Li, Simone Parmeggiani, Steve Fine, Tara Fowler, Vladan Petrovic, Yuming Du",
            "arXiv 2024 技术报告",
            "Meta AI",
            "这类大公司系统论文能直接暴露下一阶段视频生成的工程瓶颈：数据清洗、长视频一致性、可控编辑、身份保持、音频同步和评估标准。",
            "读 Movie Gen 不要只问模型结构，而要拆出系统级问题：多任务模型族如何协同，编辑和生成是否共用表示，音频同步怎样被评估。",
            {"paper": "https://arxiv.org/abs/2410.13720", "pdf": "https://arxiv.org/pdf/2410.13720", "project": "https://ai.meta.com/research/movie-gen/"},
            {
                "source": "arxiv-curated",
                "abstract": "Movie Gen 是 Meta 提出的媒体生成基础模型族，目标是在 1080p 高清视频、不同画幅、同步音频、指令式视频编辑、个性化视频生成等任务上形成统一系统。",
                "contributions": [
                    "提出覆盖视频生成、编辑、个性化和音频生成的一组媒体基础模型，而不是单一 text-to-video 模型。",
                    "把 instruction-based video editing 和 personalized video generation 放进同一系统能力谱系。",
                    "强调 synchronized audio 与多任务评估，使视频生成从“画面好看”走向“可编辑、可控、可听”。",
                ],
                "framework": [
                    "视频生成模型负责从文本生成高分辨率视频，并支持不同 aspect ratio。",
                    "编辑与个性化模块把用户图像、文本指令和已有视频作为条件，形成可控修改能力。",
                    "音频生成模块从视频或文本条件生成同步音效/音频，整体通过多任务 benchmark 和人工偏好评估。",
                ],
                "figures": [
                    {
                        "url": "/generated_figures/2410_13720/figure-1.jpg",
                        "caption": "Movie Gen · Figure 1",
                        "explanation": "Figure 1 主要用来看 Movie Gen 的整体能力版图：它不是单一 text-to-video，而是把视频生成、编辑、个性化和音频生成放进同一个媒体生成系统。",
                    },
                    {
                        "url": "/generated_figures/2410_13720/figure-2.png",
                        "caption": "Movie Gen · Figure 2",
                        "explanation": "Figure 2 主要用来看系统框架和模型族之间的关系：重点看文本/图像/视频条件如何进入不同模块，以及生成、编辑、音频同步如何被组织起来。",
                    },
                ],
                "source_badges": ["Meta", "技术报告"],
                "badges": ["视频生成", "视频编辑", "音频生成", "个性化", "评估"],
            },
        ),
        item_payload(
            f"{base_date}-recent-cvpr-transport",
            "recent",
            base_date,
            "Genie: Generative Interactive Environments",
            "Google DeepMind · ICML 2024 / arXiv",
            "Google DeepMind 提出的生成式交互环境模型，从无标注互联网视频中学习可动作控制的虚拟世界。",
            9,
            4.7,
            ["世界模型", "交互环境", "潜动作", "视频学习"],
            "Jake Bruce, Michael Dennis, Ashley Edwards, Jack Parker-Holder, Yuge Shi, Edward Hughes, Matthew Lai, Aditi Mavalankar, Richie Steigerwald, Chris Apps, Yusuf Aytar, Sarah Bechtle, Feryal Behbahani, Stephanie Chan, Nicolas Heess, Lucy Gonzalez, Simon Osindero, Sherjil Ozair, Scott Reed, Jingwei Zhang, Konrad Zolna, Jeff Clune, Nando de Freitas, Satinder Singh, Tim Rocktäschel",
            "ICML 2024 / arXiv 2024",
            "Google DeepMind",
            "Genie 的价值在于把“看视频学世界”推进到“生成可交互环境”：模型不只预测下一帧，还学习一个 latent action space，让用户可以控制生成世界。",
            "如果真实 action 标注很贵，能不能从无标注视频里诱导出可控制的 latent action？这相当于把 paired action-video 数据假设放松成 video-only 学习。",
            {"paper": "https://arxiv.org/abs/2402.15391", "pdf": "https://arxiv.org/pdf/2402.15391", "project": "https://deepmind.google/discover/blog/genie-generative-interactive-environments/"},
            {
                "source": "arxiv-curated",
                "abstract": "Genie 是一个从无标注互联网视频中训练出来的生成式交互环境模型。它可以由文本、合成图像、照片或草图提示，生成可持续交互的虚拟世界。",
                "contributions": [
                    "提出从 unlabelled Internet videos 学习生成式交互环境，把视频生成推进到 action-controllable world generation。",
                    "用 spatiotemporal video tokenizer、autoregressive dynamics model 和 latent action model 组成 foundation world model。",
                    "将 latent action learning 作为绕过真实动作标注稀缺的一种方案。",
                ],
                "framework": [
                    "先把视频压缩成时空离散表示，降低长视频建模难度。",
                    "latent action model 从相邻帧变化中诱导动作空间，使模型可以被用户动作控制。",
                    "自回归 dynamics model 在 latent state/action 条件下滚动生成后续环境。",
                ],
                "figures": [],
                "source_badges": ["Google DeepMind", "ICML"],
                "badges": ["世界模型", "交互环境", "潜动作", "视频学习"],
            },
        ),
        item_payload(
            f"{base_date}-archaeology-neural-ode",
            "archaeology",
            base_date,
            "Neural Ordinary Differential Equations",
            "Paper archaeology · 连续深度模型",
            "Neural ODE 把残差网络从离散层堆叠改写成连续时间动力系统，用黑盒 ODE solver 计算隐藏状态演化。",
            8,
            4.3,
            ["动力系统", "连续深度", "ODE solver", "归一化流", "扩散前史"],
            "Ricky T. Q. Chen, Yulia Rubanova, Jesse Bettencourt, David Duvenaud",
            "NeurIPS 2018",
            "University of Toronto / Vector Institute",
            "这篇适合考古，是因为它提供了一种“重新表述深度学习对象”的范式：把网络层数看成时间，把表示变化看成动力系统。",
            "核心启发是把一个工程结构换成数学对象：离散层变连续轨迹以后，ODE 求解、自适应步长、伴随法、动力系统稳定性都能重新进入深度学习。",
            {"paper": "https://arxiv.org/abs/1806.07366", "pdf": "https://arxiv.org/pdf/1806.07366"},
            {
                "source": "arxiv-curated",
                "abstract": "Neural Ordinary Differential Equations 提出用神经网络参数化隐藏状态的导数，再通过黑盒微分方程求解器得到输出。这样模型深度从固定层数变成连续时间演化，可以自适应计算、常数记忆反向传播，并自然连接 continuous normalizing flows。",
                "contributions": [
                    "把 ResNet 式离散层更新推广为连续时间 ODE 表示，形成 continuous-depth neural network。",
                    "使用 adjoint sensitivity method 进行常数记忆反向传播，解决连续模型训练的内存问题。",
                    "把 ODE 视角用于 continuous normalizing flow，使概率密度变化可以通过瞬时变量公式计算。",
                ],
                "framework": [
                    "定义 dh/dt = f(h,t,theta)，把神经网络作为动力系统的速度场。",
                    "前向计算由 ODE solver 从初始状态积分到终止时间。",
                    "反向传播通过伴随系统求梯度，使模型训练不需要存下所有中间状态。",
                ],
                "figures": [
                    {
                        "url": "/generated_figures/1806_07366/figure-1.png",
                        "caption": "Neural ODE · Figure 1",
                        "explanation": "Figure 1 主要用来看 Neural ODE 的核心表述转换：离散网络层被改写为连续时间隐藏状态轨迹。",
                    },
                    {
                        "url": "/generated_figures/1806_07366/figure-2.png",
                        "caption": "Neural ODE · Figure 2",
                        "explanation": "Figure 2 主要用来看训练/计算机制：ODE solver、伴随法和连续深度模型如何一起工作。",
                    },
                ],
                "source_badges": ["NeurIPS 2018"],
                "badges": ["动力系统", "连续深度", "ODE solver", "归一化流", "扩散前史"],
            },
        ),
        item_payload(
            f"{base_date}-archaeology-saycan",
            "archaeology",
            base_date,
            "Do As I Can, Not As I Say: Grounding Language in Robotic Affordances",
            "Paper archaeology · 语言模型与机器人可供性",
            "SayCan 把语言模型的高层任务分解能力和机器人 affordance value 结合起来，让机器人选择“语言上合理且现实中可执行”的动作。",
            9,
            4.5,
            ["机器人", "可供性", "语言规划", "LLM", "VLA 前身"],
            "Michael Ahn, Anthony Brohan, Noah Brown, Yevgen Chebotar, Omar Cortes, Byron David, Chelsea Finn, Chuyuan Fu, Keerthana Gopalakrishnan, Karol Hausman, Alex Herzog, Daniel Ho, Jasmine Hsu, Julian Ibarz, Brian Ichter, Alex Irpan, Eric Jang, Rosario Jauregui Ruano, Kyle Jeffrey, Sally Jesmonth, Nikhil J Joshi, Ryan Julian, Dmitry Kalashnikov, Yuheng Kuang, Kuang-Huei Lee, Sergey Levine, Yao Lu, Linda Luu, Carolina Parada, Peter Pastor, Jornell Quiambao, Kanishka Rao, Jarek Rettinghouse, Diego Reyes, Pierre Sermanet, Nicolas Sievers, Clayton Tan, Alexander Toshev, Vincent Vanhoucke, Fei Xia, Ted Xiao, Peng Xu, Sichun Xu, Mengyuan Yan, Andy Zeng",
            "arXiv 2022 / Robotics",
            "Robotics at Google / Everyday Robots / Google Research / UC Berkeley",
            "SayCan 的启发是：语言模型知道“应该做什么”，但不知道“当前机器人能不能做”。把语言概率和 affordance 可执行性相乘，是一个非常清楚的问题分解方式。",
            "科学思维线索是把一个开放式语言问题裁剪成 grounded decision making：高层 semantic prior 负责提出候选，低层 affordance prior 负责现实约束。",
            {"paper": "https://arxiv.org/abs/2204.01691", "pdf": "https://arxiv.org/pdf/2204.01691", "project": "https://say-can.github.io/"},
            {
                "source": "arxiv-curated",
                "abstract": "Do As I Can, Not As I Say 关注语言模型用于机器人决策时的核心问题：LLM 有丰富语义知识，但缺乏真实 embodiment 经验，容易提出当前机器人做不到的动作。SayCan 将 LLM 对候选技能的语言评分与机器人 affordance/value function 结合，从而选择既符合任务语义又可执行的技能。",
                "contributions": [
                    "提出 SayCan 框架，把 LLM 作为高层技能选择器，把 affordance value 作为现实可执行性约束。",
                    "将长程自然语言任务分解成一系列预训练技能，使机器人能在真实环境中完成多步骤任务。",
                    "明确指出语言模型缺少 embodiment grounding，并给出语义先验 + 可供性先验的组合范式。",
                ],
                "framework": [
                    "LLM 根据任务上下文对候选技能给出语义相关概率。",
                    "机器人 value/affordance function 评估每个技能在当前状态下是否可执行。",
                    "系统选择语言概率和 affordance 分数共同较高的技能，执行后更新状态并循环规划。",
                ],
                "figures": [
                    {
                        "url": "/generated_figures/2204_01691/figure-1.png",
                        "caption": "SayCan · Figure 1",
                        "explanation": "Figure 1 主要用来看 SayCan 的任务设定：语言模型提出高层候选动作，但最终必须落到机器人当前能执行的技能上。",
                    },
                    {
                        "url": "/generated_figures/2204_01691/figure-2.png",
                        "caption": "SayCan · Figure 2",
                        "explanation": "Figure 2 主要用来看方法框架：LLM 的语义评分和 affordance/value 分数如何组合，如何在每一步选择“既合理又能做”的技能。",
                    },
                ],
                "source_badges": ["arXiv 2022", "Robotics"],
                "badges": ["机器人", "可供性", "语言规划", "LLM", "VLA 前身"],
            },
        ),
        item_payload(
            f"{base_date}-scholar-pan-card",
            "scholar",
            base_date,
            "潘云鹤",
            "中国工程院院士 · 智能系统 / 人工智能",
            "潘云鹤，中国工程院院士，长期从事计算机图形学、人工智能、智能 CAD、智能系统等方向研究，并参与国内人工智能战略与学术平台建设。",
            8,
            4.1,
            ["中国工程院院士", "浙江大学", "人工智能", "智能系统", "学术组织"],
            "潘云鹤",
            "中国工程院院士馆 / 浙江大学公开资料",
            "中国工程院信息与电子工程学部；浙江大学",
            "看潘云鹤这类人物，不只是看个人成果，而是看国内人工智能方向的平台、学术组织、人才 title 和机构流动如何形成网络。",
            "人物关系网必须区分“已核验事实”和“待核验关系”。身份、学部、机构可以先落库；师承、学生、合作、杰青/长江等 title 需要逐条接公开来源。",
            {"profile": "https://ysg.ckcest.cn/html/details/662/index.html"},
            {
                "source": "中国工程院院士馆等公开来源；关系网络待继续核验",
                "sections": ["已核验身份", "机构脉络", "研究方向", "学术组织", "待核验关系"],
                "titles": ["中国工程院院士", "信息与电子工程学部", "人工智能 / 智能系统", "浙江大学相关学术生态"],
                "relations": [
                    {"name": "浙江大学", "note": "已核验机构线索：长期关联浙江大学计算机、人工智能与智能系统方向。"},
                    {"name": "中国工程院信息与电子工程学部", "note": "已核验身份线索：院士馆公开资料可查。"},
                    {"name": "国内人工智能学术组织与平台", "note": "待继续核验：学会任职、平台建设、学生/合作者和高层次人才 title 关系。"},
                ],
                "badges": ["院士", "浙江大学", "人工智能", "智能系统"],
            },
        ),
        item_payload(
            f"{yesterday}-archaeology-paired-data",
            "archaeology",
            yesterday,
            "From Paired Supervision to Weakly Coupled Learning",
            "昨日考古 · 科学问题迁移",
            "从早期依赖 paired data 的视觉任务出发，反推如何在无配对、弱配对或伪配对条件下重新定义学习信号。",
            78,
            4.0,
            ["unpaired learning", "scientific thinking", "data assumption"],
            "整理卡片",
            "Idea archaeology",
            "本地知识库",
            "它不是单篇论文，而是一条读 paper 的问题线：当训练和测试条件不一致时，怎样去掉强假设？",
            "把旧论文中的数据假设圈出来，然后逐个问：这个假设在现实中是否成立？如果不成立，替代信号是什么？",
            {"note": ""},
            {"source": "demo", "freshness": "archive"},
        ),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO items(
            id, kind, title, subtitle, summary, item_date, score, rating, tags_json,
            authors, venue, org, why, thinking, links_json, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        records,
    )


def seed_science_items(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM items WHERE kind = 'science' LIMIT 1").fetchone():
        return
    row = conn.execute("SELECT MAX(item_date) AS latest_date FROM items").fetchone()
    base_date = row["latest_date"] or today()
    records = [
        item_payload(
            f"{base_date}-science-trajcast",
            "science",
            base_date,
            "Force-free molecular dynamics through autoregressive equivariant networks",
            "Nature Machine Intelligence · AI for Science",
            "TrajCast 用自回归等变网络直接预测原子位置和速度轨迹，绕开传统分子动力学里每一步显式力计算和小步长积分的瓶颈。",
            8,
            4.4,
            ["分子动力学", "等变网络", "材料模拟", "AI for Science"],
            "Fabian L. Thiemann, Thiago Reschützegger, Massimiliano Esposito, Tseden Taddese, Juan D. Olarte-Plata, Fausto Martelli",
            "Nature Machine Intelligence 2026",
            "IBM Research / University of Cambridge 等",
            "它很适合青椒关注：不是只把 AI 用来拟合一个性质，而是重写科学模拟管线，把昂贵的数值积分环节替换为可学习的长步长动力学预测。",
            "科学思维上，它把“计算物理瓶颈”转成“可学习的状态转移问题”：如果模型能保持物理约束和统计性质，就可以用更大时间步探索慢过程。",
            {"paper": "https://www.nature.com/articles/s42256-026-01227-7", "pdf": "https://www.nature.com/articles/s42256-026-01227-7.pdf"},
            {
                "source": "Nature Machine Intelligence",
                "abstract": "TrajCast 关注分子动力学模拟中的时间尺度瓶颈，用 autoregressive equivariant MPNN 直接从当前原子状态预测较大时间间隔后的新位置和速度，在多个分子与材料体系中复现结构、动力学和能量分布。",
                "contributions": [
                    "提出 force-free molecular dynamics，用等变消息传递网络直接预测原子轨迹，而不是先预测力再积分。",
                    "在小分子、晶体和液态水等体系中验证，能使用比传统 MD 更大的时间步并保持物理统计量。",
                    "展示对训练分布外慢过程的泛化潜力，为长时间尺度材料/化学模拟提供新路线。",
                ],
                "framework": [
                    "输入当前原子位置、速度和元素类型，通过等变 MPNN 编码局部原子环境。",
                    "模型自回归预测下一时间点的位置和速度，并在 roll-out 中持续推进轨迹。",
                    "通过温控和物理约束降低漂移，使生成轨迹能对齐实验常用 ensemble。",
                ],
                "figures": [],
                "source_badges": ["Nature Machine Intelligence", "AI for Science"],
                "badges": ["分子动力学", "等变网络", "材料模拟"],
            },
        ),
        item_payload(
            f"{base_date}-science-matterchat",
            "science",
            base_date,
            "A multimodal large language model for materials science",
            "Nature Machine Intelligence · 材料科学",
            "MatterChat 把材料结构 encoder 和大语言模型连接起来，让模型既能读文本，也能处理原子结构，用于材料性质预测、合成推理和人机交互。",
            8,
            4.2,
            ["材料科学", "多模态 LLM", "结构理解", "科学推理"],
            "Yingheng Tang, Wenbin Xu, Jie Cao, Weilu Gao, Steven Farrell, Benjamin Erichson, Michael W. Mahoney, Andy Nonaka, Zhi Jackie Yao 等",
            "Nature Machine Intelligence 2026",
            "Lawrence Berkeley National Laboratory / UC Berkeley 等",
            "这类工作有纵向课题价值：它不是通用聊天机器人，而是把材料结构、语言和科学任务放进同一个交互界面，能启发专科领域的科研助手设计。",
            "关键问题是如何把领域对象接入 LLM：材料结构不能被粗暴文本化，需要先用材料 foundation encoder 表示，再通过桥接模块和语言模型对齐。",
            {"paper": "https://www.nature.com/articles/s42256-026-01214-y", "pdf": "https://www.nature.com/articles/s42256-026-01214-y.pdf"},
            {
                "source": "Nature Machine Intelligence",
                "abstract": "MatterChat 是面向材料科学的结构感知多模态大语言模型，将预训练材料基础模型和 LLM 对齐，使模型能够同时利用材料结构和文本信息完成性质预测、科学问答和合成推理。",
                "contributions": [
                    "提出面向材料结构的多模态 LLM，把原子结构表示与文本推理统一起来。",
                    "用 bridging module 对齐材料 foundation encoder 和预训练 LLM，降低领域模型训练成本。",
                    "展示材料性质预测、科学推理和 step-by-step synthesis 等应用。",
                ],
                "framework": [
                    "材料结构先进入预训练材料 encoder，得到结构感知表示。",
                    "桥接模块把结构表示映射到 LLM 可使用的语义空间。",
                    "LLM 结合文本提示和结构 token 输出预测、解释或合成建议。",
                ],
                "figures": [],
                "source_badges": ["Nature Machine Intelligence", "材料科学"],
                "badges": ["材料科学", "多模态 LLM", "科学推理"],
            },
        ),
        item_payload(
            f"{base_date}-science-medicine-access",
            "science",
            base_date,
            "Improving access to essential medicines via decision-aware machine learning",
            "Nature · AI for 民生",
            "这篇 Nature 工作把机器学习用于低中收入国家基本药物供应，把预测模型和实际分配决策联动，目标是提升稀缺医疗资源的公平与效率。",
            7,
            4.1,
            ["AI for 民生", "医疗资源", "决策感知学习", "供应链"],
            "Angel Tsai-Hsuan Chung, Jatu Abdulai, Patrick Bayoh, Lawrence Sandi, Francis Smart, Hamsa Bastani, Osbert Bastani 等",
            "Nature 2026",
            "University of Pennsylvania 等",
            "它代表 AI for Science/民生里很关键的一类：不是追求单点预测分数，而是把模型嵌入真实资源分配流程，让优化目标贴近社会结果。",
            "科学问题不是“预测准不准”这么简单，而是预测误差如何影响下游决策、公平性和可执行性。这对纵向课题设计很重要。",
            {"paper": "https://www.nature.com/articles/s41586-026-10433-7"},
            {
                "source": "Nature",
                "abstract": "论文面向低中收入国家基本药物获取问题，使用 decision-aware machine learning 将预测和资源分配目标连接起来，在数据有限和资源稀缺条件下改善药物供应决策。",
                "contributions": [
                    "把机器学习模型与基本药物供应的实际决策目标绑定，而不是只优化预测误差。",
                    "关注低资源医疗系统中的公平性、可执行性和稀缺资源配置。",
                    "提供 AI for 民生/公共卫生方向可参考的问题定义：模型必须服务于真实决策流程。",
                ],
                "framework": [
                    "从有限的医疗系统数据中学习需求和短缺风险。",
                    "将预测输出接入库存、补货或分配决策，使训练目标感知下游决策后果。",
                    "用实际服务可达性和公平性指标评价模型价值。",
                ],
                "figures": [],
                "source_badges": ["Nature", "AI for 民生"],
                "badges": ["医疗资源", "决策感知学习", "供应链"],
            },
        ),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO items(
            id, kind, title, subtitle, summary, item_date, score, rating, tags_json,
            authors, venue, org, why, thinking, links_json, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        records,
    )


def scholar_follow_payload(
    follow_id: str,
    name: str,
    display_name: str,
    institution: str,
    institution_group: str,
    role_title: str,
    scholar_url: str,
    homepage_url: str,
    citations: int,
    has_new: bool,
    bio: str,
    early_focus: str,
    recent_focus: str,
    papers: list[dict],
    interests: list[str],
    links: dict | None = None,
) -> tuple:
    now = now_iso()
    payload = {
        "papers": papers,
        "interests": interests,
        "links": links or {},
        "monthly_update_prompt": (
            "每月检查 Google Scholar profile，按时间从新到旧同步新论文；"
            "对 average yearly citations > 100 的论文标 star；"
            "补充本月是否有新论文、总引用量、近期兴趣变化。"
        ),
    }
    return (
        follow_id,
        name,
        display_name,
        institution,
        institution_group,
        role_title,
        scholar_url,
        homepage_url,
        citations,
        1 if has_new else 0,
        current_month(),
        bio,
        early_focus,
        recent_focus,
        json_dumps(payload),
        now,
        now,
    )


def seed_scholar_follows(conn: sqlite3.Connection) -> None:
    records = [
        scholar_follow_payload(
            "fei-fei-li",
            "Fei-Fei Li",
            "Fei-Fei Li",
            "Stanford University",
            "Stanford University",
            "Professor · Human-Centered AI / Computer Vision",
            "https://scholar.google.com/citations?user=rDfyQnIAAAAJ&hl=en",
            "https://profiles.stanford.edu/fei-fei-li",
            0,
            True,
            "Fei-Fei Li 是视觉识别、ImageNet、AI4ALL 和 human-centered AI 的代表性学者之一，长期推动大规模视觉数据、视觉理解和以人为中心的人工智能。",
            "早期围绕 object recognition、scene understanding 和大规模视觉数据集展开，ImageNet 是其最有标志性的学术基础设施工作。",
            "近年重点转向 human-centered AI、具身智能、医疗/社会场景中的 AI，以及如何让视觉模型服务真实人类任务。",
            [
                {"year": 2024, "title": "Holistic embodied AI and human-centered intelligence", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "用于跟踪近期兴趣，不代表单篇 Scholar 精确条目。"},
                {"year": 2015, "title": "ImageNet Large Scale Visual Recognition Challenge", "venue": "IJCV", "citations": 0, "citations_per_year": 100, "star": True, "note": "大规模视觉识别基础设施级论文，高年均引用。"},
                {"year": 2014, "title": "Microsoft COCO: Common Objects in Context", "venue": "ECCV", "citations": 0, "citations_per_year": 100, "star": True, "note": "场景理解和检测数据集基础工作，高年均引用。"},
                {"year": 2009, "title": "ImageNet: A large-scale hierarchical image database", "venue": "CVPR", "citations": 0, "citations_per_year": 100, "star": True, "note": "现代视觉预训练与大规模数据路线的核心节点。"},
            ],
            ["ImageNet", "视觉识别", "human-centered AI", "具身智能", "医疗 AI"],
            {"lab": "https://hai.stanford.edu/people/fei-fei-li"},
        ),
        scholar_follow_payload(
            "jiajun-wu",
            "Jiajun Wu",
            "Jiajun Wu",
            "Stanford University",
            "Stanford University",
            "Assistant Professor · 3D Vision / Physical Reasoning",
            "https://scholar.google.com/citations?user=2efgcS0AAAAJ&hl=en",
            "https://jiajunwu.com/",
            0,
            True,
            "Jiajun Wu 关注 3D perception、物理推理、机器人和可组合世界模型，很多工作把视觉理解和可交互/可预测的物理世界连接起来。",
            "早期代表性工作围绕 3D ShapeNets、场景/形状理解和 visual dynamics，强调从视觉中恢复结构化世界表示。",
            "近年更关注 embodied AI、robot learning、3D/4D world modeling，以及可用于长程任务的物理和结构先验。",
            [
                {"year": 2025, "title": "Recent work on 3D world modeling and robot learning", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 占位，后续由 Agent 按 Scholar 更新。"},
                {"year": 2015, "title": "3D ShapeNets: A Deep Representation for Volumetric Shapes", "venue": "CVPR", "citations": 0, "citations_per_year": 100, "star": True, "note": "3D shape representation 早期高影响工作。"},
                {"year": 2017, "title": "Learning to See Physics via Visual De-animation", "venue": "NeurIPS", "citations": 0, "citations_per_year": 0, "star": False, "note": "从视觉中恢复物理场景和因果结构的代表性路线。"},
                {"year": 2017, "title": "Visual Dynamics: Probabilistic Future Frame Synthesis via Cross Convolutional Networks", "venue": "NeurIPS", "citations": 0, "citations_per_year": 0, "star": False, "note": "把视觉预测、动作和动态建模联系起来。"},
            ],
            ["3D world model", "物理推理", "机器人", "结构化视觉", "embodied AI"],
            {"lab": "https://svl.stanford.edu/"},
        ),
        scholar_follow_payload(
            "bernt-schiele",
            "Bernt Schiele",
            "Bernt Schiele",
            "Max Planck Institute for Informatics",
            "Max Planck Institute / Saarland University",
            "Director · Computer Vision / Embodied Perception",
            "https://scholar.google.com/citations?user=z76PBfYAAAAJ&hl=en",
            "https://people.mpi-inf.mpg.de/~schiele/",
            0,
            False,
            "Bernt Schiele 是欧洲计算机视觉和具身感知的重要学者，长期关注人体理解、视觉识别、场景理解、机器人感知和 benchmark。",
            "早期围绕 object recognition、人体姿态、行人/动作理解和视觉检测展开，是传统视觉到深度视觉过渡期的重要节点。",
            "近年兴趣延伸到 embodied perception、robust vision、human-object interaction、视觉语言和开放世界理解。",
            [
                {"year": 2024, "title": "Recent work on embodied perception and open-world visual understanding", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 占位，后续由 Agent 按 Scholar 更新。"},
                {"year": 2014, "title": "The PASCAL Visual Object Classes Challenge: A Retrospective", "venue": "IJCV", "citations": 0, "citations_per_year": 100, "star": True, "note": "视觉检测与分类 benchmark 的基础设施级工作。"},
                {"year": 2014, "title": "Rich feature hierarchies for accurate object detection and semantic segmentation", "venue": "CVPR", "citations": 0, "citations_per_year": 100, "star": True, "note": "R-CNN 代表性高引视觉检测工作之一。"},
                {"year": 2012, "title": "A database for fine grained activity detection of cooking activities", "venue": "CVPR Workshops", "citations": 0, "citations_per_year": 0, "star": False, "note": "长时动作和日常活动理解相关线索。"},
            ],
            ["人体理解", "视觉识别", "embodied perception", "HOI", "benchmark"],
            {"lab": "https://www.mpi-inf.mpg.de/departments/computer-vision-and-machine-learning"},
        ),
        scholar_follow_payload(
            "dima-damen",
            "Dima Damen",
            "Dima Damen",
            "University of Bristol",
            "University of Bristol",
            "Professor · Egocentric Vision / Video Understanding · Google DeepMind",
            "",
            "https://dimadamen.github.io/",
            0,
            True,
            "Dima Damen 主要关注 egocentric vision、视频理解、动作识别和长时活动建模，是 EPIC-KITCHENS 等第一人称视频数据集和评测的重要推动者；公开主页显示她同时任职 University of Bristol 和 Google DeepMind。",
            "早期工作覆盖动作识别、物体交互、视频中人的行为理解，逐步聚焦到第一人称视角和厨房/日常活动场景。",
            "近年重点是 egocentric video、long-horizon activity understanding、hands/objects interaction，以及可用于具身智能的日常行为数据。",
            [
                {"year": 2025, "title": "Recent work on egocentric video and long-horizon activities", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 占位，后续由 Agent 按 Scholar 更新。"},
                {"year": 2018, "title": "Scaling Egocentric Vision: The EPIC-KITCHENS Dataset", "venue": "ECCV", "citations": 0, "citations_per_year": 100, "star": True, "note": "第一人称视频理解核心数据集，高年均引用候选。"},
                {"year": 2021, "title": "Rescaling Egocentric Vision: Collection, Pipeline and Challenges for EPIC-KITCHENS-100", "venue": "IJCV", "citations": 0, "citations_per_year": 100, "star": True, "note": "EPIC-KITCHENS 扩展版，长时日常活动理解重要 benchmark。"},
                {"year": 2022, "title": "Ego4D: Around the World in 3,000 Hours of Egocentric Video", "venue": "CVPR", "citations": 0, "citations_per_year": 100, "star": True, "note": "大规模第一人称视频数据基础设施。"},
            ],
            ["egocentric video", "视频理解", "长时活动", "hands-object interaction", "EPIC-KITCHENS"],
            {"publications": "https://dimadamen.github.io/publications.html"},
        ),
        scholar_follow_payload(
            "chelsea-finn",
            "Chelsea Finn",
            "Chelsea Finn",
            "Stanford University",
            "Stanford University",
            "Assistant Professor · Robot Learning / Meta-Learning",
            "https://scholar.google.com/citations?user=vfPE6hgAAAAJ&hl=en",
            "https://ai.stanford.edu/~cbfinn/",
            0,
            False,
            "Chelsea Finn 是 robot learning、meta-learning 和 embodied AI 方向非常值得长期 follow 的学者，工作常常围绕少样本适应、真实机器人数据和可泛化策略学习展开。",
            "早期代表性路线包括 Model-Agnostic Meta-Learning、机器人模仿学习和视觉运动控制，核心问题是如何让模型用少量交互快速适应新任务。",
            "近年重点关注 foundation models for robotics、可扩展机器人数据、长程任务学习和从多模态反馈中学习可执行行为。",
            [
                {"year": 2017, "title": "Model-Agnostic Meta-Learning for Fast Adaptation of Deep Networks", "venue": "ICML", "citations": 0, "citations_per_year": 100, "star": True, "note": "少样本适应和元学习的基础论文之一。"},
                {"year": 2018, "title": "One-Shot Visual Imitation Learning via Meta-Learning", "venue": "CoRL", "citations": 0, "citations_per_year": 0, "star": False, "note": "机器人从少量示范中学习的代表性工作。"},
                {"year": 2024, "title": "Recent work on scalable robot learning", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时重点看是否有机器人 foundation model 和数据集新工作。"},
            ],
            ["机器人学习", "元学习", "模仿学习", "具身智能", "长程任务"],
            {"lab": "https://irislab.stanford.edu/"},
        ),
        scholar_follow_payload(
            "percy-liang",
            "Percy Liang",
            "Percy Liang",
            "Stanford University",
            "Stanford University",
            "Professor · Foundation Models / NLP / Agents",
            "",
            "https://cs.stanford.edu/~pliang/",
            0,
            False,
            "Percy Liang 适合放在 LLM、agent、评测和基础模型基础设施这一条线上 follow，很多工作不是单点模型，而是围绕模型行为、数据、评测和系统化理解展开。",
            "早期覆盖语义解析、弱监督、语言与结构化知识，长期关注模型如何从语言中学习可操作的表示。",
            "近年重点转向 foundation model evaluation、HELM、agent benchmark、数据治理和模型透明度，对判断一个新 agent 工作是否真的可靠很有参考价值。",
            [
                {"year": 2022, "title": "Holistic Evaluation of Language Models", "venue": "HELM", "citations": 0, "citations_per_year": 100, "star": True, "note": "基础模型系统评测的重要节点。"},
                {"year": 2024, "title": "Recent work on foundation model evaluation and agents", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注 agent/eval/data governance。"},
            ],
            ["LLM 评测", "Agent", "基础模型", "数据治理", "语义解析"],
            {"lab": "https://crfm.stanford.edu/"},
        ),
        scholar_follow_payload(
            "sergey-levine",
            "Sergey Levine",
            "Sergey Levine",
            "University of California, Berkeley",
            "University of California, Berkeley",
            "Professor · Robot Learning / Reinforcement Learning",
            "",
            "https://people.eecs.berkeley.edu/~svlevine/",
            0,
            False,
            "Sergey Levine 是 robot learning、deep RL 和 embodied intelligence 方向必须 follow 的作者之一，特别适合看从强化学习、离线数据到真实机器人泛化这条路线。",
            "早期工作围绕 guided policy search、深度强化学习和视觉运动控制，推动了 end-to-end robot learning 的重要转向。",
            "近年重点在离线 RL、机器人数据、通用机器人策略、world model 和可扩展 embodied learning。",
            [
                {"year": 2016, "title": "End-to-End Training of Deep Visuomotor Policies", "venue": "JMLR", "citations": 0, "citations_per_year": 100, "star": True, "note": "视觉运动策略学习的代表性早期工作。"},
                {"year": 2020, "title": "Offline Reinforcement Learning: Tutorial, Review, and Perspectives", "venue": "Review", "citations": 0, "citations_per_year": 100, "star": True, "note": "离线 RL 路线的重要综述。"},
                {"year": 2024, "title": "Recent work on scalable robot data and policies", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注机器人 foundation policy 和数据闭环。"},
            ],
            ["机器人学习", "离线 RL", "world model", "视觉运动控制", "通用策略"],
            {"lab": "https://rail.eecs.berkeley.edu/"},
        ),
        scholar_follow_payload(
            "pieter-abbeel",
            "Pieter Abbeel",
            "Pieter Abbeel",
            "University of California, Berkeley",
            "University of California, Berkeley",
            "Professor · Robotics / Reinforcement Learning",
            "https://scholar.google.com/citations?user=vtwH6GkAAAAJ&hl=en",
            "https://people.eecs.berkeley.edu/~pabbeel/",
            0,
            False,
            "Pieter Abbeel 适合从机器人、RL、模仿学习和产业化机器人系统这条线长期 follow，他的工作常常把算法、真实机器人平台和可扩展训练连接起来。",
            "早期围绕 apprenticeship learning、直升机自主控制、机器人操作和强化学习展开。",
            "近年与大规模机器人学习、扩散策略、生成模型和机器人系统创业生态关系密切。",
            [
                {"year": 2004, "title": "Apprenticeship Learning via Inverse Reinforcement Learning", "venue": "ICML", "citations": 0, "citations_per_year": 100, "star": True, "note": "模仿学习和逆强化学习基础工作。"},
                {"year": 2023, "title": "Diffusion Policy: Visuomotor Policy Learning via Action Diffusion", "venue": "RSS", "citations": 0, "citations_per_year": 100, "star": True, "note": "近年来机器人动作生成的重要路线。"},
                {"year": 2024, "title": "Recent work on large-scale robot learning", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注机器人策略和系统落地。"},
            ],
            ["机器人", "强化学习", "模仿学习", "扩散策略", "产业化机器人"],
            {"lab": "https://bair.berkeley.edu/"},
        ),
        scholar_follow_payload(
            "jitendra-malik",
            "Jitendra Malik",
            "Jitendra Malik",
            "University of California, Berkeley",
            "University of California, Berkeley",
            "Professor · Computer Vision / Embodied Perception",
            "",
            "https://people.eecs.berkeley.edu/~malik/",
            0,
            False,
            "Jitendra Malik 是计算机视觉领域的基础性人物，适合从视觉表示、分割、三维/具身感知和科学品味上长期 follow。",
            "早期代表性贡献覆盖图像分割、物体识别、视觉 grouping 和场景理解，是传统视觉理论和现代视觉学习之间的重要桥梁。",
            "近年团队持续影响 embodied perception、robot learning、视觉语言和数据驱动视觉理解。",
            [
                {"year": 2001, "title": "Normalized Cuts and Image Segmentation", "venue": "PAMI", "citations": 0, "citations_per_year": 100, "star": True, "note": "图像分割和图划分思想的经典论文。"},
                {"year": 2014, "title": "Rich feature hierarchies for accurate object detection and semantic segmentation", "venue": "CVPR", "citations": 0, "citations_per_year": 100, "star": True, "note": "深度检测时代的核心节点。"},
                {"year": 2024, "title": "Recent work on embodied perception", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注视觉基础问题如何迁移到具身智能。"},
            ],
            ["视觉基础", "图像分割", "embodied perception", "检测", "科学品味"],
            {"lab": "https://bair.berkeley.edu/"},
        ),
        scholar_follow_payload(
            "josh-tenenbaum",
            "Josh Tenenbaum",
            "Josh Tenenbaum",
            "Massachusetts Institute of Technology",
            "Massachusetts Institute of Technology",
            "Professor · Cognitive Science / Probabilistic Models",
            "",
            "https://web.mit.edu/cocosci/josh.html",
            0,
            False,
            "Josh Tenenbaum 适合放在“经典理论与科学思维”的 follow 池里，他的工作把认知科学、概率程序、物理直觉和人类概念学习连接得很深。",
            "早期围绕 Bayesian concept learning、概率图模型和认知建模展开，强调用结构化先验解释人类学习。",
            "近年持续影响 intuitive physics、program induction、neuro-symbolic AI 和世界模型的理论底座。",
            [
                {"year": 2011, "title": "How to Grow a Mind: Statistics, Structure, and Abstraction", "venue": "Science", "citations": 0, "citations_per_year": 100, "star": True, "note": "认知科学和结构化学习的经典综述/观点论文。"},
                {"year": 2016, "title": "Building Machines That Learn and Think Like People", "venue": "Behavioral and Brain Sciences", "citations": 0, "citations_per_year": 100, "star": True, "note": "连接认知、组合泛化和机器智能的重要论文。"},
                {"year": 2024, "title": "Recent work on cognitive world models", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注经典认知理论与现代 world model 的连接。"},
            ],
            ["认知科学", "概率程序", "直觉物理", "组合泛化", "世界模型理论"],
            {"lab": "https://cocosci.mit.edu/"},
        ),
        scholar_follow_payload(
            "phillip-isola",
            "Phillip Isola",
            "Phillip Isola",
            "Massachusetts Institute of Technology",
            "Massachusetts Institute of Technology",
            "Associate Professor · Vision / Generative Models",
            "",
            "https://web.mit.edu/phillipi/",
            0,
            False,
            "Phillip Isola 值得放在视觉生成、表征学习和视觉系统设计这一条线上 follow，很多工作兼具方法简洁性和启发性。",
            "早期代表性工作包括 image-to-image translation、视觉表征和感知相似性，强调简单 formulation 带来的方法迁移。",
            "近年关注视觉生成、可组合表示、视觉语言和具身/交互式视觉系统。",
            [
                {"year": 2017, "title": "Image-to-Image Translation with Conditional Adversarial Networks", "venue": "CVPR", "citations": 0, "citations_per_year": 100, "star": True, "note": "Pix2Pix，paired image translation 的经典工作。"},
                {"year": 2018, "title": "The Unreasonable Effectiveness of Deep Features as a Perceptual Metric", "venue": "CVPR", "citations": 0, "citations_per_year": 100, "star": True, "note": "LPIPS，视觉生成评估和感知距离的重要工具。"},
                {"year": 2024, "title": "Recent work on generative vision and representations", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注视觉生成和世界表示。"},
            ],
            ["视觉生成", "图像翻译", "表征学习", "感知评价", "视觉语言"],
            {"lab": "https://isola-group.mit.edu/"},
        ),
        scholar_follow_payload(
            "katerina-fragkiadaki",
            "Katerina Fragkiadaki",
            "Katerina Fragkiadaki",
            "Carnegie Mellon University",
            "Carnegie Mellon University",
            "Associate Professor · Vision / Robotics / Dynamics",
            "",
            "https://www.cs.cmu.edu/~katef/",
            0,
            False,
            "Katerina Fragkiadaki 适合 follow 视觉动力学、机器人操作、3D/4D world model 和物理交互建模这条线，和你的 world model / VLA 兴趣贴得很近。",
            "早期工作覆盖动作理解、视频中的对象和人类行为建模，强调从视觉序列中恢复动态结构。",
            "近年重点转向机器人、神经场景表示、物理可预测模型和可交互世界建模。",
            [
                {"year": 2015, "title": "Learning Visual Predictive Models of Physics for Playing Billiards", "venue": "ICLR Workshop", "citations": 0, "citations_per_year": 0, "star": False, "note": "视觉预测和物理建模早期线索。"},
                {"year": 2024, "title": "Recent work on 3D dynamics and robot learning", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注动态世界模型、机器人操作和视频预测。"},
            ],
            ["视觉动力学", "机器人操作", "3D world model", "物理预测", "视频理解"],
            {"lab": "https://www.cs.cmu.edu/~katef/projects.html"},
        ),
        scholar_follow_payload(
            "dieter-fox",
            "Dieter Fox",
            "Dieter Fox",
            "University of Washington / NVIDIA",
            "University of Washington / NVIDIA",
            "Professor · Robotics / Embodied AI",
            "https://scholar.google.com/citations?user=DqXsbPAAAAAJ&hl=en",
            "https://dieterfox.github.io/",
            0,
            False,
            "Dieter Fox 适合 follow 机器人感知、SLAM、具身 AI 和大厂机器人研究之间的连接，尤其适合看机器人系统如何从经典概率机器人走向 foundation model。",
            "早期围绕概率机器人、定位、SLAM 和移动机器人感知展开，是机器人基础方法的重要作者。",
            "近年关注 embodied AI、机器人操作、视觉语言机器人和 NVIDIA 机器人研究生态。",
            [
                {"year": 1999, "title": "Monte Carlo Localization: Efficient Position Estimation for Mobile Robots", "venue": "AAAI", "citations": 0, "citations_per_year": 100, "star": True, "note": "概率机器人和定位的经典工作。"},
                {"year": 2024, "title": "Recent work on embodied AI and robot manipulation", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注 NVIDIA / UW 机器人方向。"},
            ],
            ["概率机器人", "SLAM", "embodied AI", "机器人操作", "视觉语言机器人"],
            {"lab": "https://research.nvidia.com/labs/gear/"},
        ),
        scholar_follow_payload(
            "regina-barzilay",
            "Regina Barzilay",
            "Regina Barzilay",
            "Massachusetts Institute of Technology",
            "Massachusetts Institute of Technology",
            "Professor · NLP / AI for Health / AI for Science",
            "",
            "https://people.csail.mit.edu/regina/",
            0,
            False,
            "Regina Barzilay 适合放在 AI for Science / AI for Health 的 follow 池里，尤其适合看 NLP、机器学习和真实医疗/药物发现问题如何结合。",
            "早期工作覆盖文本生成、语义建模和信息抽取，后来把机器学习用于临床文本、影像和药物发现。",
            "近年重点是 AI for drug discovery、医疗 AI、分子建模和真实世界医学决策支持。",
            [
                {"year": 2020, "title": "A deep learning model to predict a diagnosis of Alzheimer disease by using 18F-FDG PET of the brain", "venue": "Radiology", "citations": 0, "citations_per_year": 0, "star": False, "note": "医疗 AI 代表方向之一，具体引用月度同步再核验。"},
                {"year": 2020, "title": "A Deep Learning Approach to Antibiotic Discovery", "venue": "Cell", "citations": 0, "citations_per_year": 100, "star": True, "note": "AI 药物发现方向的高影响工作。"},
                {"year": 2024, "title": "Recent work on AI for medicine and molecules", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注 AI for Health 和 drug discovery。"},
            ],
            ["AI for Health", "药物发现", "医疗 AI", "分子建模", "NLP"],
            {"lab": "https://www.jclinic.mit.edu/"},
        ),
        scholar_follow_payload(
            "david-baker",
            "David Baker",
            "David Baker",
            "University of Washington",
            "University of Washington",
            "Professor · Protein Design / AI for Science",
            "https://scholar.google.com/citations?user=UKqIqRsAAAAJ&hl=en",
            "https://www.ipd.uw.edu/people/david-baker/",
            0,
            False,
            "David Baker 是 AI for Science 和蛋白质设计方向必须 follow 的作者之一，适合看生成模型、结构预测和真实科学发现之间如何形成闭环。",
            "早期长期推动 Rosetta、蛋白质结构建模和 de novo protein design，是计算蛋白质设计的核心人物。",
            "近年重点是深度学习辅助蛋白质设计、功能蛋白生成、结构生成和科学实验闭环。",
            [
                {"year": 2021, "title": "Accurate prediction of protein structures and interactions using a three-track neural network", "venue": "Science", "citations": 0, "citations_per_year": 100, "star": True, "note": "RoseTTAFold，高影响蛋白质结构预测工作。"},
                {"year": 2023, "title": "De novo design of protein structure and function with RFdiffusion", "venue": "Nature", "citations": 0, "citations_per_year": 100, "star": True, "note": "扩散模型用于蛋白质设计的重要工作。"},
                {"year": 2024, "title": "Recent work on generative protein design", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注 Nature/Science 级 AI for Science 更新。"},
            ],
            ["蛋白质设计", "AI for Science", "扩散模型", "结构预测", "实验闭环"],
            {"lab": "https://www.ipd.uw.edu/"},
        ),
        scholar_follow_payload(
            "anima-anandkumar",
            "Anima Anandkumar",
            "Anima Anandkumar",
            "California Institute of Technology",
            "California Institute of Technology",
            "Professor · AI for Science / Scientific Machine Learning",
            "https://scholar.google.com/citations?user=bEcLezcAAAAJ&hl=en",
            "https://tensorlab.cms.caltech.edu/users/anima/",
            0,
            False,
            "Anima Anandkumar 适合 follow 科学机器学习、神经算子、张量方法和 AI for Science 工具链，是把深度学习用于 PDE、天气、分子和物理系统的重要作者。",
            "早期工作覆盖张量分解、无监督学习理论和高维统计，强调有理论结构的方法。",
            "近年重点在 neural operators、Fourier Neural Operator、科学仿真、气候/流体/材料等 AI for Science 场景。",
            [
                {"year": 2021, "title": "Fourier Neural Operator for Parametric Partial Differential Equations", "venue": "ICLR", "citations": 0, "citations_per_year": 100, "star": True, "note": "神经算子和科学机器学习的重要工作。"},
                {"year": 2024, "title": "Recent work on scientific machine learning", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注 AI for Science、neural operator 和模拟。"},
            ],
            ["科学机器学习", "neural operator", "PDE", "AI for Science", "张量方法"],
            {"lab": "https://tensorlab.cms.caltech.edu/"},
        ),
        scholar_follow_payload(
            "demis-hassabis",
            "Demis Hassabis",
            "Demis Hassabis",
            "Google DeepMind",
            "Google DeepMind",
            "CEO · AI for Science / General AI",
            "",
            "https://deepmind.google/about/leadership/demis-hassabis/",
            0,
            False,
            "Demis Hassabis 适合从 Google DeepMind 的研究战略、AI for Science 和通用智能路线去 follow，不只是看单篇论文，更适合看方向布局。",
            "早期背景横跨认知神经科学、游戏 AI 和强化学习，DeepMind 早期路线把深度学习、RL 和 neuroscience 连接起来。",
            "近年重点是 Gemini、AlphaFold、AI for Science、世界模型和能够跨任务泛化的智能系统。",
            [
                {"year": 2021, "title": "Highly accurate protein structure prediction with AlphaFold", "venue": "Nature", "citations": 0, "citations_per_year": 100, "star": True, "note": "AI for Science 标志性工作。"},
                {"year": 2015, "title": "Human-level control through deep reinforcement learning", "venue": "Nature", "citations": 0, "citations_per_year": 100, "star": True, "note": "深度强化学习时代的标志性节点。"},
            ],
            ["Google DeepMind", "AI for Science", "强化学习", "通用智能", "世界模型"],
            {"lab": "https://deepmind.google/research/"},
        ),
        scholar_follow_payload(
            "john-jumper",
            "John Jumper",
            "John Jumper",
            "Google DeepMind",
            "Google DeepMind",
            "Director · Protein Structure / AI for Science",
            "",
            "https://deepmind.google/research/people/johnjumper/",
            0,
            False,
            "John Jumper 是 AlphaFold 路线的核心作者之一，适合 follow 蛋白质结构、分子系统和 AI for Science 从 benchmark 到真实科学影响的变化。",
            "早期围绕物理、化学和蛋白质建模展开，强调把结构先验、几何和学习系统结合起来。",
            "近年重点是 AlphaFold 系列、多分子结构、蛋白质相互作用和科学发现工作流。",
            [
                {"year": 2021, "title": "Highly accurate protein structure prediction with AlphaFold", "venue": "Nature", "citations": 0, "citations_per_year": 100, "star": True, "note": "蛋白质结构预测里程碑。"},
                {"year": 2024, "title": "Accurate structure prediction of biomolecular interactions with AlphaFold 3", "venue": "Nature", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注 AlphaFold 系列后续。"},
            ],
            ["蛋白质结构", "AlphaFold", "分子相互作用", "AI for Science", "几何学习"],
            {"lab": "https://deepmind.google/research/"},
        ),
        scholar_follow_payload(
            "cordelia-schmid",
            "Cordelia Schmid",
            "Cordelia Schmid",
            "Google DeepMind / Inria",
            "Google DeepMind / Inria",
            "Research Scientist · Video Understanding / Computer Vision",
            "",
            "https://www.di.ens.fr/~schmid/",
            0,
            False,
            "Cordelia Schmid 是视频理解、动作识别和视觉表示学习方向的重要作者，适合从经典视觉到现代视频 foundation model 的演化去 follow。",
            "早期贡献覆盖局部特征、视觉检索、动作识别和视频表示，是计算机视觉基础路线的重要人物。",
            "近年重点在视频理解、视觉语言、长视频建模和大规模视觉表示。",
            [
                {"year": 2015, "title": "Action Recognition with Improved Trajectories", "venue": "ICCV", "citations": 0, "citations_per_year": 100, "star": True, "note": "深度视频之前的强基线和经典动作识别路线。"},
                {"year": 2024, "title": "Recent work on video understanding", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注视频 foundation model。"},
            ],
            ["视频理解", "动作识别", "视觉表示", "视觉语言", "长视频"],
            {"lab": "https://deepmind.google/research/"},
        ),
        scholar_follow_payload(
            "kristen-grauman",
            "Kristen Grauman",
            "Kristen Grauman",
            "University of Texas at Austin / Meta",
            "University of Texas at Austin / Meta",
            "Professor · Egocentric Vision / Active Perception",
            "",
            "https://www.cs.utexas.edu/~grauman/",
            0,
            False,
            "Kristen Grauman 适合 follow egocentric vision、active perception 和视频理解，尤其是从第一人称数据到具身智能 benchmark 的连接。",
            "早期覆盖视觉识别、主动学习、图像检索和视频理解。",
            "近年重点是 Ego4D、第一人称视频、具身感知、可交互视觉和长时活动理解。",
            [
                {"year": 2022, "title": "Ego4D: Around the World in 3,000 Hours of Egocentric Video", "venue": "CVPR", "citations": 0, "citations_per_year": 100, "star": True, "note": "第一人称视频基础设施级工作。"},
                {"year": 2024, "title": "Recent work on egocentric video and active perception", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注 Ego4D 后续和长程任务。"},
            ],
            ["egocentric video", "主动感知", "Ego4D", "长时活动", "具身视觉"],
            {"lab": "https://vision.cs.utexas.edu/"},
        ),
        scholar_follow_payload(
            "sanja-fidler",
            "Sanja Fidler",
            "Sanja Fidler",
            "University of Toronto / NVIDIA",
            "University of Toronto / NVIDIA",
            "Professor · 3D Vision / Generative AI",
            "",
            "https://www.cs.toronto.edu/~fidler/",
            0,
            False,
            "Sanja Fidler 适合 follow 3D vision、自动驾驶场景理解、生成式世界建模和 NVIDIA 视觉研究生态。",
            "早期覆盖场景理解、检测、3D 表示和视觉语言。",
            "近年重点在 3D/4D 生成、自动驾驶仿真、视觉语言模型和可编辑场景生成。",
            [
                {"year": 2016, "title": "SYNTHIA: A Large Collection of Synthetic Images for Semantic Segmentation of Urban Scenes", "venue": "CVPR", "citations": 0, "citations_per_year": 100, "star": True, "note": "合成数据和自动驾驶视觉的重要早期工作。"},
                {"year": 2024, "title": "Recent work on 3D generative AI and simulation", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注 3D 场景生成和仿真。"},
            ],
            ["3D vision", "场景生成", "自动驾驶", "仿真", "视觉语言"],
            {"lab": "https://research.nvidia.com/labs/toronto-ai/"},
        ),
        scholar_follow_payload(
            "antonio-torralba",
            "Antonio Torralba",
            "Antonio Torralba",
            "Massachusetts Institute of Technology",
            "Massachusetts Institute of Technology",
            "Professor · Scene Understanding / Computer Vision",
            "",
            "https://groups.csail.mit.edu/vision/torralbalab/",
            0,
            False,
            "Antonio Torralba 适合 follow 场景理解、视觉数据集、视觉常识和从图像到世界结构的建模路线。",
            "早期代表性工作覆盖场景统计、context、物体和场景之间的关系，以及大规模视觉数据。",
            "近年持续影响视觉表征、视觉数据、生成模型评估和世界理解。",
            [
                {"year": 2008, "title": "80 Million Tiny Images: A Large Data Set for Nonparametric Object and Scene Recognition", "venue": "PAMI", "citations": 0, "citations_per_year": 100, "star": True, "note": "大规模视觉数据思想的重要节点。"},
                {"year": 2014, "title": "Microsoft COCO: Common Objects in Context", "venue": "ECCV", "citations": 0, "citations_per_year": 100, "star": True, "note": "视觉场景理解数据集核心工作。"},
            ],
            ["场景理解", "视觉数据集", "视觉常识", "context", "世界理解"],
            {"lab": "https://groups.csail.mit.edu/vision/torralbalab/"},
        ),
        scholar_follow_payload(
            "andrew-zisserman",
            "Andrew Zisserman",
            "Andrew Zisserman",
            "University of Oxford",
            "University of Oxford",
            "Professor · Computer Vision / Video / Self-Supervision",
            "",
            "https://www.robots.ox.ac.uk/~az/",
            0,
            False,
            "Andrew Zisserman 适合 follow 视觉识别、视频理解、自监督学习和 Oxford VGG 系列工作。",
            "早期贡献覆盖几何视觉、多视图几何、视觉识别和大规模视觉表示。",
            "近年重点在视频理解、音视频学习、自监督视觉语言和大规模视觉模型。",
            [
                {"year": 2014, "title": "Very Deep Convolutional Networks for Large-Scale Image Recognition", "venue": "ICLR", "citations": 0, "citations_per_year": 100, "star": True, "note": "VGG，深度视觉架构经典工作。"},
                {"year": 2020, "title": "Self-Supervised Learning from Video", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注视频自监督和视觉语言。"},
            ],
            ["视频理解", "自监督学习", "VGG", "视觉识别", "音视频"],
            {"lab": "https://www.robots.ox.ac.uk/~vgg/"},
        ),
        scholar_follow_payload(
            "joelle-pineau",
            "Joelle Pineau",
            "Joelle Pineau",
            "McGill University / Meta",
            "McGill University / Meta",
            "Professor · Reinforcement Learning / Responsible AI",
            "",
            "https://www.cs.mcgill.ca/~jpineau/",
            0,
            False,
            "Joelle Pineau 适合 follow 强化学习、医疗 AI、可复现性和负责任 AI，能帮助判断 agent/RL 工作是否有扎实评估。",
            "早期覆盖 POMDP、机器人辅助、医疗决策和强化学习。",
            "近年重点在 RL、开源评测、reproducibility、responsible AI 和 Meta AI 研究生态。",
            [
                {"year": 2003, "title": "Point-based value iteration: An anytime algorithm for POMDPs", "venue": "IJCAI", "citations": 0, "citations_per_year": 100, "star": True, "note": "POMDP 经典算法之一。"},
                {"year": 2024, "title": "Recent work on RL, evaluation, and responsible AI", "venue": "Research direction", "citations": 0, "citations_per_year": 0, "star": False, "note": "月度 follow 时关注 RL 评测和负责任 AI。"},
            ],
            ["强化学习", "POMDP", "医疗 AI", "评测", "负责任 AI"],
            {"lab": "https://mila.quebec/en/person/joelle-pineau/"},
        ),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO scholar_follows(
            id, name, display_name, institution, institution_group, role_title,
            scholar_url, homepage_url, citations, has_new_this_month, last_checked_month,
            bio, early_focus, recent_focus, payload_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        records,
    )


def scholar_follow_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "display_name": row["display_name"],
        "institution": row["institution"],
        "institution_group": row["institution_group"],
        "role_title": row["role_title"],
        "scholar_url": row["scholar_url"],
        "homepage_url": row["homepage_url"],
        "citations": row["citations"],
        "has_new_this_month": bool(row["has_new_this_month"]),
        "last_checked_month": row["last_checked_month"],
        "bio": row["bio"],
        "early_focus": row["early_focus"],
        "recent_focus": row["recent_focus"],
        "payload": parse_json(row["payload_json"], {}),
        "updated_at": row["updated_at"],
    }


def item_from_row(row: sqlite3.Row, favorite: bool = False, note: sqlite3.Row | None = None) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["title"],
        "subtitle": row["subtitle"],
        "summary": row["summary"],
        "date": row["item_date"],
        "score": row["score"],
        "rating": row["rating"],
        "tags": parse_json(row["tags_json"], []),
        "authors": row["authors"],
        "venue": row["venue"],
        "org": row["org"],
        "why": row["why"],
        "thinking": row["thinking"],
        "links": parse_json(row["links_json"], {}),
        "payload": parse_json(row["payload_json"], {}),
        "favorite": favorite,
        "note": dict(note) if note else None,
    }


def read_secret(paths: list[Path]) -> str:
    for path in paths:
        try:
            if path.exists():
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    return value
        except OSError:
            continue
    return ""


def deepseek_api_key() -> str:
    env_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("RESEARCH_PULSE_DEEPSEEK_API_KEY") or ""
    if env_key.strip():
        return env_key.strip()
    return read_secret([CONFIG_ROOT / "deepseek_api_key.txt", Path.home() / ".research_pulse_deepseek_api_key"])


def deepseek_messages(item: sqlite3.Row, question: str, history: list[sqlite3.Row]) -> list[dict]:
    tags = " / ".join(parse_json(item["tags_json"], []))
    payload = parse_json(item["payload_json"], {})
    contributions = payload.get("contributions") if isinstance(payload.get("contributions"), list) else []
    framework = payload.get("framework") if isinstance(payload.get("framework"), list) else []
    figures = payload.get("figures") if isinstance(payload.get("figures"), list) else []
    figure_context = "\n".join(
        f"- {figure.get('caption') or f'Figure {index + 1}'}"
        + (f"：{figure.get('pdf_caption')}" if figure.get("pdf_caption") else "")
        for index, figure in enumerate(figures[:2])
        if isinstance(figure, dict)
    )
    recent_history = "\n".join(
        f"{row['role']}: {row['content'][:500]}" for row in history[-6:] if row["content"].strip()
    )
    context = "\n".join(
        part
        for part in [
            f"标题：{item['title']}",
            f"类型：{item['kind']}",
            f"作者：{item['authors']}" if item["authors"] else "",
            f"机构：{item['org']}" if item["org"] else "",
            f"来源：{item['venue']}" if item["venue"] else "",
            f"标签：{tags}" if tags else "",
            "",
            "文章导读：",
            item["summary"],
            "",
            "英文摘要：",
            payload.get("original_abstract") or "",
            "",
            "中文摘要：",
            payload.get("zh_abstract") or payload.get("abstract") or "",
            "",
            "为什么值得读：",
            item["why"],
            "",
            "核心贡献：",
            "\n".join(f"- {value}" for value in contributions) if contributions else "",
            "",
            "主要框架：",
            "\n".join(f"- {value}" for value in framework) if framework else "",
            "",
            "方法/思想线索补充：",
            item["thinking"],
            "",
            "PDF Figure 1/2 caption：",
            figure_context,
            "",
            "近期对话：",
            recent_history or "暂无。",
        ]
        if part
    )
    return [
        {
            "role": "system",
            "content": (
                "你是 Research Pulse 的科研阅读助手。用中文回答，像 GPT 阅读论文一样自然、具体、可追问。"
                "如果是论文，优先围绕问题定义、核心假设、方法框架、实验/结论、可迁移启发展开；"
                "如果是学术人物，优先围绕身份 title、师承学生、合作关系、机构脉络和待核验来源展开。"
                "允许使用 Markdown 加粗、列表和公式，但不要输出空泛套话。不要虚构未给出的结果；"
                "没有来源支持的信息必须明确标注待核验。"
            ),
        },
        {
            "role": "user",
            "content": f"{context}\n\n用户问题：{question}",
        },
    ]


def deepseek_chat(messages: list[dict]) -> str:
    key = deepseek_api_key()
    if not key:
        return ""
    endpoint = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "stream": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str(data.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()


def feishu_webhook() -> str:
    candidates = [
        os.environ.get("FEISHU_WEBHOOK", ""),
        os.environ.get("RESEARCH_PULSE_FEISHU_WEBHOOK", ""),
    ]
    for path in [CONFIG_ROOT / "feishu_webhook.txt", Path.home() / ".research_pulse_feishu_webhook"]:
        if path.exists():
            candidates.append(path.read_text(encoding="utf-8").strip())
    return next((value for value in candidates if value.startswith("http")), "")


def send_feishu_text(text: str) -> bool:
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


class ResearchPulseHandler(BaseHTTPRequestHandler):
    server_version = "ResearchPulse/0.1"

    def log_message(self, fmt, *args):
        print(f"[{now_iso()}] {self.address_string()} {fmt % args}")

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def route(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path.startswith("/api/"):
            try:
                self.handle_api(method, path, qs)
            except Exception as exc:
                self.send_json({"error": "server_error", "detail": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self.serve_static(path)

    def read_json(self) -> dict:
        size = int(self.headers.get("Content-Length", "0") or "0")
        if size == 0:
            return {}
        raw = self.rfile.read(size).decode("utf-8")
        return json.loads(raw or "{}")

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK, headers: dict | None = None):
        body = json_dumps(payload).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def get_cookie_token(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def current_user(self, conn: sqlite3.Connection) -> sqlite3.Row | None:
        token = self.get_cookie_token()
        if not token:
            return None
        row = conn.execute(
            """
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ?
            """,
            (token, now_iso()),
        ).fetchone()
        return row

    def require_user(self, conn: sqlite3.Connection) -> sqlite3.Row | None:
        user = self.current_user(conn)
        if not user:
            self.send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return None
        return user

    def require_admin(self, conn: sqlite3.Connection) -> sqlite3.Row | None:
        user = self.require_user(conn)
        if not user:
            return None
        if user["role"] != "admin":
            self.send_json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
            return None
        return user

    def handle_api(self, method: str, path: str, qs: dict):
        with connect() as conn:
            if method == "POST" and path == "/api/register":
                return self.api_register(conn)
            if method == "POST" and path == "/api/login":
                return self.api_login(conn)
            if method == "POST" and path == "/api/logout":
                return self.api_logout(conn)
            if method == "GET" and path == "/api/me":
                return self.api_me(conn)

            user = self.require_user(conn)
            if not user:
                return

            if method == "GET" and path == "/api/feed":
                return self.api_feed(conn, user, qs)
            if method == "GET" and path == "/api/dates":
                return self.api_dates(conn)
            if method == "GET" and path == "/api/interest_profile":
                return self.api_interest_profile(conn, user)
            if method == "GET" and path == "/api/settings":
                return self.send_json({"settings": ensure_settings(conn, user["id"])})
            if method == "POST" and path == "/api/settings":
                return self.api_update_settings(conn, user)
            if method == "POST" and path == "/api/favorite":
                return self.api_favorite(conn, user)
            if method == "GET" and path == "/api/notes":
                return self.api_notes(conn, user, qs)
            if method == "POST" and path == "/api/notes":
                return self.api_save_note(conn, user)
            if method == "GET" and path == "/api/chat":
                return self.api_chat(conn, user, qs)
            if method == "POST" and path == "/api/chat":
                return self.api_save_chat(conn, user)
            if method == "GET" and path == "/api/qmem":
                return self.api_qmem_context(conn, user, qs)
            if method == "GET" and path == "/api/related_notes":
                return self.api_related_notes(conn, user, qs)
            if method == "POST" and path == "/api/feishu/note":
                return self.api_send_note_to_feishu(conn, user)
            if method == "POST" and path == "/api/agent/feishu-note":
                return self.api_queue_feishu_note_agent(conn, user)
            if method == "GET" and path == "/api/users":
                return self.api_share_users(conn, user)
            if method == "POST" and path == "/api/share":
                return self.api_share(conn, user)
            if method == "GET" and path == "/api/inbox":
                return self.api_inbox(conn, user)
            if method == "POST" and path == "/api/inbox/save":
                return self.api_inbox_save(conn, user)
            if method == "GET" and path == "/api/repository":
                return self.api_repository(conn, user, qs)
            if method == "GET" and path == "/api/bigshots":
                return self.api_bigshots(conn, user)
            if method == "POST" and path == "/api/bigshots":
                return self.api_add_bigshot(conn, user)
            if method == "POST" and path == "/api/bigshots/update":
                return self.api_queue_bigshot_update(conn, user)
            if path == "/api/admin/users":
                if not self.require_admin(conn):
                    return
                if method == "GET":
                    return self.api_admin_users(conn)
                if method == "POST":
                    return self.api_admin_update_user(conn, user)
        self.send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def api_register(self, conn: sqlite3.Connection):
        data = self.read_json()
        username = (data.get("username") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        if not email:
            email = f"{username.lower()}@local"
        if len(username) < 2 or ("@" not in email) or len(password) < 8:
            return self.send_json({"error": "invalid_input"}, HTTPStatus.BAD_REQUEST)
        try:
            cur = conn.execute(
                """
                INSERT INTO users(username, email, password_hash, role, status, created_at)
                VALUES (?, ?, ?, 'user', 'pending', ?)
                """,
                (username, email, hash_password(password), now_iso()),
            )
            ensure_settings(conn, cur.lastrowid)
        except sqlite3.IntegrityError:
            return self.send_json({"error": "user_exists"}, HTTPStatus.CONFLICT)
        return self.send_json({"ok": True, "message": "注册已提交，等待管理员审批。"})

    def api_login(self, conn: sqlite3.Connection):
        data = self.read_json()
        identity = (data.get("identity") or "").strip()
        password = data.get("password") or ""
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (identity, identity.lower()),
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return self.send_json({"error": "bad_credentials"}, HTTPStatus.UNAUTHORIZED)
        if row["status"] != "approved":
            return self.send_json({"error": "not_approved", "status": row["status"]}, HTTPStatus.FORBIDDEN)
        token = secrets.token_urlsafe(32)
        expires = datetime.now(LOCAL_TZ) + timedelta(days=14)
        conn.execute(
            "INSERT INTO sessions(token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token, row["id"], expires.isoformat(timespec="seconds"), now_iso()),
        )
        cookie = f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={14 * 24 * 3600}"
        settings = ensure_settings(conn, row["id"])
        return self.send_json({"user": row_to_user(row), "settings": settings}, headers={"Set-Cookie": cookie})

    def api_logout(self, conn: sqlite3.Connection):
        token = self.get_cookie_token()
        if token:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        cookie = f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
        return self.send_json({"ok": True}, headers={"Set-Cookie": cookie})

    def api_me(self, conn: sqlite3.Connection):
        user = self.current_user(conn)
        if not user:
            return self.send_json({"user": None})
        return self.send_json({"user": row_to_user(user), "settings": ensure_settings(conn, user["id"])})

    def api_feed(self, conn: sqlite3.Connection, user: sqlite3.Row, qs: dict):
        settings = ensure_settings(conn, user["id"])
        modules = settings["modules"]
        counts = settings["counts"]
        scope = qs.get("scope", ["today"])[0]
        kind = qs.get("kind", [""])[0]
        requested_date = qs.get("date", [""])[0]
        params = []
        where = []
        latest_by_kind = {}
        if scope != "all" and not requested_date:
            latest_by_kind = {
                row["kind"]: row["latest_date"]
                for row in conn.execute("SELECT kind, MAX(item_date) AS latest_date FROM items GROUP BY kind").fetchall()
            }
        if scope != "all" and requested_date:
            where.append("item_date = ?")
            params.append(requested_date)
        if kind:
            where.append("kind = ?")
            params.append(kind)
        sql = "SELECT * FROM items"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY item_date DESC, score DESC, rating DESC"
        rows = conn.execute(sql, params).fetchall()
        favorites = {
            row["item_id"]
            for row in conn.execute("SELECT item_id FROM favorites WHERE user_id = ?", (user["id"],)).fetchall()
        }
        notes = {
            row["item_id"]: row
            for row in conn.execute("SELECT * FROM notes WHERE user_id = ?", (user["id"],)).fetchall()
        }
        buckets: dict[str, int] = {}
        items = []
        for row in rows:
            if latest_by_kind and row["item_date"] != latest_by_kind.get(row["kind"]):
                continue
            if not modules.get(row["kind"], True):
                continue
            buckets[row["kind"]] = buckets.get(row["kind"], 0) + 1
            if scope != "all" and buckets[row["kind"]] > int(counts.get(row["kind"], 99)):
                continue
            items.append(item_from_row(row, row["id"] in favorites, notes.get(row["id"])))
        return self.send_json({"items": items, "date": requested_date or today(), "settings": settings})

    def api_dates(self, conn: sqlite3.Connection):
        rows = conn.execute("SELECT DISTINCT item_date FROM items ORDER BY item_date DESC").fetchall()
        return self.send_json({"dates": [row["item_date"] for row in rows]})

    def api_interest_profile(self, conn: sqlite3.Connection, user: sqlite3.Row):
        settings = ensure_settings(conn, user["id"])
        manual_terms = split_terms(settings["positive_keywords"])
        excluded_terms = split_terms(settings["negative_keywords"])
        suggestions: dict[str, set[str]] = {}
        suggestion_labels: dict[str, str] = {}
        manual_keys = {term.lower() for term in manual_terms}
        excluded_keys = {term.lower() for term in excluded_terms}

        def add(term: str, source: str):
            clean = term.strip()
            if not clean or len(clean) < 2:
                return
            key = clean.lower()
            if key in manual_keys:
                return
            if key in excluded_keys:
                return
            suggestions.setdefault(key, set()).add(source)
            suggestion_labels.setdefault(key, clean)

        rows = conn.execute(
            """
            SELECT items.* FROM favorites
            JOIN items ON items.id = favorites.item_id
            WHERE favorites.user_id = ?
            ORDER BY favorites.created_at DESC
            """,
            (user["id"],),
        ).fetchall()
        for row in rows:
            for tag in parse_json(row["tags_json"], []):
                add(tag, "收藏")
            for value in [row["venue"], row["org"]]:
                for token in tokenize_interest_text(value):
                    add(token, "收藏来源")

        note_rows = conn.execute(
            "SELECT title, content FROM notes WHERE user_id = ? ORDER BY updated_at DESC LIMIT 20",
            (user["id"],),
        ).fetchall()
        for row in note_rows:
            for token in tokenize_interest_text(f"{row['title']} {row['content']}")[:12]:
                add(token, "笔记")

        local_sources = []
        for repo_name, root_value in [
            ("wiki", settings["wiki_path"]),
            ("papers", settings["papers_path"]),
            ("notes", settings["notes_path"]),
        ]:
            root = Path(root_value).expanduser()
            if not root.is_absolute():
                root = (WORKSPACE_ROOT / root).resolve()
            root = root.resolve()
            if is_sensitive_path(root):
                continue
            if not root.exists():
                continue
            count = 0
            for path in sorted(root.rglob("*")):
                if count >= 30:
                    break
                if path.is_file() and not path.name.startswith(".") and not is_sensitive_path(path):
                    rel = str(path.relative_to(root))
                    local_sources.append({"repo": repo_name, "path": rel})
                    for token in tokenize_interest_text(path.stem)[:5]:
                        add(token, repo_name)
                    if path.suffix.lower() in {".json", ".md", ".txt"}:
                        try:
                            text = path.read_text(encoding="utf-8", errors="replace")[:12000]
                            if path.suffix.lower() == ".json":
                                data = json.loads(text)
                                parts = [str(data.get("title", ""))]
                                for message in data.get("messages", [])[:8]:
                                    parts.append(str(message.get("content", ""))[:1000])
                                text = "\n".join(parts)
                            for token in tokenize_interest_text(text)[:20]:
                                add(token, f"{repo_name}内容")
                        except Exception:
                            pass
                    count += 1

        suggested_terms = [
            {"term": suggestion_labels[key], "sources": sorted(sources)}
            for key, sources in sorted(suggestions.items(), key=lambda item: (-len(item[1]), item[0]))[:40]
        ]
        return self.send_json(
            {
                "manual_terms": manual_terms,
                "excluded_terms": excluded_terms,
                "suggested_terms": suggested_terms,
                "local_sources": local_sources[:40],
            }
        )

    def api_update_settings(self, conn: sqlite3.Connection, user: sqlite3.Row):
        data = self.read_json()
        current = ensure_settings(conn, user["id"])
        settings = {
            "modules": data.get("modules", current["modules"]),
            "counts": data.get("counts", current["counts"]),
            "positive_keywords": data.get("positive_keywords", current["positive_keywords"]),
            "negative_keywords": data.get("negative_keywords", current["negative_keywords"]),
            "interest_prompt": data.get("interest_prompt", current["interest_prompt"]),
            "wiki_path": data.get("wiki_path", current["wiki_path"]),
            "papers_path": data.get("papers_path", current["papers_path"]),
            "notes_path": data.get("notes_path", current["notes_path"]),
        }
        conn.execute(
            """
            UPDATE user_settings SET modules_json = ?, counts_json = ?, positive_keywords = ?,
                negative_keywords = ?, interest_prompt = ?, wiki_path = ?, papers_path = ?, notes_path = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (
                json_dumps(settings["modules"]),
                json_dumps(settings["counts"]),
                settings["positive_keywords"],
                settings["negative_keywords"],
                settings["interest_prompt"],
                settings["wiki_path"],
                settings["papers_path"],
                settings["notes_path"],
                now_iso(),
                user["id"],
            ),
        )
        return self.send_json({"settings": ensure_settings(conn, user["id"])})

    def api_favorite(self, conn: sqlite3.Connection, user: sqlite3.Row):
        data = self.read_json()
        item_id = data.get("item_id")
        favorite = bool(data.get("favorite"))
        if not conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone():
            return self.send_json({"error": "item_not_found"}, HTTPStatus.NOT_FOUND)
        if favorite:
            conn.execute(
                "INSERT OR IGNORE INTO favorites(user_id, item_id, created_at) VALUES (?, ?, ?)",
                (user["id"], item_id, now_iso()),
            )
        else:
            conn.execute("DELETE FROM favorites WHERE user_id = ? AND item_id = ?", (user["id"], item_id))
        return self.send_json({"ok": True})

    def api_notes(self, conn: sqlite3.Connection, user: sqlite3.Row, qs: dict):
        item_id = qs.get("item_id", [""])[0]
        if item_id:
            row = conn.execute("SELECT * FROM notes WHERE user_id = ? AND item_id = ?", (user["id"], item_id)).fetchone()
            return self.send_json({"note": dict(row) if row else None})
        rows = conn.execute(
            """
            SELECT notes.*, items.title AS item_title, items.kind AS item_kind
            FROM notes JOIN items ON items.id = notes.item_id
            WHERE notes.user_id = ? ORDER BY notes.updated_at DESC
            """,
            (user["id"],),
        ).fetchall()
        return self.send_json({"notes": [dict(row) for row in rows]})

    def api_save_note(self, conn: sqlite3.Connection, user: sqlite3.Row):
        data = self.read_json()
        item_id = data.get("item_id")
        title = (data.get("title") or "未命名笔记").strip()
        content = (data.get("content") or "").strip()
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item_id or not content:
            return self.send_json({"error": "invalid_note"}, HTTPStatus.BAD_REQUEST)
        if not item:
            return self.send_json({"error": "item_not_found"}, HTTPStatus.NOT_FOUND)
        conn.execute(
            """
            INSERT INTO notes(user_id, item_id, title, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, item_id) DO UPDATE SET
                title = excluded.title, content = excluded.content, updated_at = excluded.updated_at
            """,
            (user["id"], item_id, title, content, now_iso(), now_iso()),
        )
        settings = ensure_settings(conn, user["id"])
        note_path = write_note_markdown(user, item, title, content, settings)
        try:
            display_path = str(note_path.relative_to(APP_ROOT))
        except ValueError:
            display_path = str(note_path)
        return self.send_json({"ok": True, "note_path": display_path})

    def api_related_notes(self, conn: sqlite3.Connection, user: sqlite3.Row, qs: dict):
        item_id = qs.get("item_id", [""])[0]
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return self.send_json({"notes": []})
        tags = parse_json(item["tags_json"], [])
        terms = [item["id"].lower(), item["title"].lower(), *[str(tag).lower() for tag in tags]]
        settings = ensure_settings(conn, user["id"])
        root = user_notes_root(user, settings)
        notes = []
        for path in sorted(root.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            if is_sensitive_path(path):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            haystack = f"{path.stem}\n{content}".lower()
            if not any(term and term in haystack for term in terms):
                continue
            title = path.stem
            for line in content.splitlines():
                if line.startswith("note_title:"):
                    title = line.split(":", 1)[1].strip() or title
                    break
            notes.append(
                {
                    "title": title,
                    "path": str(path.relative_to(root)),
                    "content": content[:80_000],
                    "updated_at": datetime.fromtimestamp(path.stat().st_mtime, LOCAL_TZ).isoformat(timespec="seconds"),
                }
            )
            if len(notes) >= 12:
                break
        return self.send_json({"notes": notes})

    def api_chat(self, conn: sqlite3.Connection, user: sqlite3.Row, qs: dict):
        item_id = qs.get("item_id", [""])[0]
        if not item_id:
            return self.send_json({"messages": []})
        rows = conn.execute(
            """
            SELECT id, role, content, created_at FROM chat_messages
            WHERE user_id = ? AND item_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (user["id"], item_id),
        ).fetchall()
        return self.send_json({"messages": [dict(row) for row in rows]})

    def api_qmem_context(self, conn: sqlite3.Connection, user: sqlite3.Row, qs: dict):
        item_id = qs.get("item_id", [""])[0]
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return self.send_json({"records": []})
        settings = ensure_settings(conn, user["id"])
        wiki_root = Path(settings["wiki_path"]).expanduser()
        if not wiki_root.is_absolute():
            wiki_root = (WORKSPACE_ROOT / wiki_root).resolve()
        if not wiki_root.exists():
            return self.send_json({"records": []})

        title_terms = [token.lower() for token in tokenize_interest_text(item["title"]) if len(token) > 3]
        tag_terms = [str(tag).lower() for tag in parse_json(item["tags_json"], []) if len(str(tag)) > 2]
        query_terms = title_terms[:6] + tag_terms[:6]
        records = []
        for path in sorted(wiki_root.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            if len(records) >= 8:
                break
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace")[:300_000])
            except Exception:
                continue
            title = str(data.get("title", ""))
            messages = data.get("messages", [])
            text_parts = [title]
            for message in messages[:20]:
                text_parts.append(str(message.get("content", ""))[:1200])
            haystack = "\n".join(text_parts).lower()
            hits = [term for term in query_terms if term and term in haystack]
            if not hits:
                continue
            excerpt = ""
            for message in messages:
                content = str(message.get("content", "")).strip()
                if any(term in content.lower() for term in hits):
                    excerpt = content[:260]
                    break
            records.append(
                {
                    "title": title or path.stem,
                    "path": str(path.relative_to(wiki_root)),
                    "updated_at": data.get("update_time") or data.get("create_time") or "",
                    "matched_terms": hits[:6],
                    "excerpt": excerpt,
                }
            )
        return self.send_json({"records": records})

    def api_save_chat(self, conn: sqlite3.Connection, user: sqlite3.Row):
        data = self.read_json()
        item_id = data.get("item_id")
        content = (data.get("content") or "").strip()
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item or not content:
            return self.send_json({"error": "invalid_chat"}, HTTPStatus.BAD_REQUEST)
        conn.execute(
            "INSERT INTO chat_messages(user_id, item_id, role, content, created_at) VALUES (?, ?, 'user', ?, ?)",
            (user["id"], item_id, content, now_iso()),
        )
        conn.commit()
        history = conn.execute(
            """
            SELECT role, content FROM chat_messages
            WHERE user_id = ? AND item_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (user["id"], item_id),
        ).fetchall()
        reply = ""
        if deepseek_api_key():
            try:
                answer = deepseek_chat(deepseek_messages(item, content, history))
                if answer:
                    reply = answer
            except Exception:
                reply = ""
        if not reply:
            task_prompt = (
                f"用户对条目《{item['title']}》提出问题：{content}\n"
                "请在下一次 Research Pulse Agent 更新时结合论文/人物卡片、用户 wiki 和 papers 上下文回答。"
            )
            cur = conn.execute(
                "INSERT INTO agent_tasks(user_id, item_id, task_type, prompt, status, created_at) VALUES (?, ?, 'qa', ?, 'pending', ?)",
                (user["id"], item_id, task_prompt, now_iso()),
            )
            reply = (
                f"这次没有拿到即时回答，已转入后台整理（任务 #{cur.lastrowid}）。"
                "需要马上继续问的话，可以复制上下文到 GPT。"
            )
        conn.execute(
            "INSERT INTO chat_messages(user_id, item_id, role, content, created_at) VALUES (?, ?, 'assistant', ?, ?)",
            (user["id"], item_id, reply, now_iso()),
        )
        return self.api_chat(conn, user, {"item_id": [item_id]})

    def api_send_note_to_feishu(self, conn: sqlite3.Connection, user: sqlite3.Row):
        data = self.read_json()
        item_id = data.get("item_id")
        title = (data.get("title") or "Research Pulse 笔记").strip()
        content = (data.get("content") or "").strip()
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item or not content:
            return self.send_json({"error": "invalid_note"}, HTTPStatus.BAD_REQUEST)
        text = "\n".join(
            [
                f"Research Pulse 笔记｜{title}",
                f"条目：{item['title']}",
                f"类型：{item['kind']}｜日期：{item['item_date']}",
                f"作者/机构：{item['authors']}｜{item['org']}",
                "",
                content,
            ]
        )
        draft_dir = APP_ROOT / "agent_outputs"
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path = draft_dir / f"feishu_note_{datetime.now(LOCAL_TZ).strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            sent = send_feishu_text(text)
        except Exception as exc:
            draft_path.write_text(text, encoding="utf-8")
            return self.send_json(
                {"ok": False, "sent": False, "draft_path": str(draft_path), "detail": str(exc)},
            )
        if not sent:
            draft_path.write_text(text, encoding="utf-8")
            return self.send_json({"ok": True, "sent": False, "draft_path": str(draft_path)})
        return self.send_json({"ok": True, "sent": True})

    def api_queue_feishu_note_agent(self, conn: sqlite3.Connection, user: sqlite3.Row):
        data = self.read_json()
        item_id = data.get("item_id")
        current_note = (data.get("content") or "").strip()
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return self.send_json({"error": "item_not_found"}, HTTPStatus.NOT_FOUND)
        payload = parse_json(item["payload_json"], {})
        contributions = payload.get("contributions") if isinstance(payload.get("contributions"), list) else []
        framework = payload.get("framework") if isinstance(payload.get("framework"), list) else []
        figures = payload.get("figures") if isinstance(payload.get("figures"), list) else []
        figure_context = "\n".join(
            f"- {figure.get('caption') or f'Figure {index + 1}'}"
            + (f"：{figure.get('pdf_caption')}" if figure.get("pdf_caption") else "")
            for index, figure in enumerate(figures[:2])
            if isinstance(figure, dict)
        )
        prompt = "\n".join(
            [
                f"请把 Research Pulse 条目整理成一篇可保存为 Markdown、并可通过飞书 webhook 发送摘要提醒的科研笔记：{item['title']}",
                f"类型：{item['kind']}",
                f"来源：{item['venue']} / {item['org']}",
                f"作者：{item['authors']}",
                "",
                "文章导读：",
                item["summary"],
                "",
                "英文摘要：",
                payload.get("original_abstract") or "",
                "",
                "中文摘要：",
                payload.get("zh_abstract") or payload.get("abstract") or "",
                "",
                "核心贡献：",
                "\n".join(f"- {value}" for value in contributions) if contributions else "待从正文核验。",
                "",
                "主要框架：",
                "\n".join(f"- {value}" for value in framework) if framework else "待从正文核验。",
                "",
                "PDF Figure 1/2 caption：",
                figure_context or "暂未提取。",
                "",
                "推荐理由/分析线索：",
                item["why"],
                item["thinking"],
                "",
                "用户当前草稿：",
                current_note or "用户尚未写草稿。",
                "",
                "输出要求：",
                "1. 用中文整理成结构清晰的 Markdown，允许保留必要英文术语和公式。",
                "2. 包含：问题定义、英文摘要忠实中文化、核心方法、Figure 1/2 图文解释、关键假设、影响/后续工作、对我当前方向的启发、可继续追问的问题。",
                "3. 重点内容用 Markdown 加粗；不要只列标题，每个要点都要解释几句。",
                "4. 不要虚构论文结果；不确定处标注待核验。",
                "5. 完成后把结果写回 notes 表。当前 webhook 只能发飞书消息提醒，不能声称已自动创建飞书文档。",
            ]
        )
        cur = conn.execute(
            """
            INSERT INTO agent_tasks(user_id, item_id, task_type, prompt, status, created_at)
            VALUES (?, ?, 'feishu_note', ?, 'pending', ?)
            """,
            (user["id"], item_id, prompt, now_iso()),
        )
        return self.send_json({"ok": True, "task_id": cur.lastrowid})

    def api_share_users(self, conn: sqlite3.Connection, user: sqlite3.Row):
        rows = conn.execute(
            "SELECT * FROM users WHERE status = 'approved' AND id != ? ORDER BY role, username",
            (user["id"],),
        ).fetchall()
        return self.send_json({"users": [row_to_user(row) for row in rows]})

    def api_share(self, conn: sqlite3.Connection, user: sqlite3.Row):
        data = self.read_json()
        receiver_id = int(data.get("receiver_id") or 0)
        item_id = data.get("item_id")
        message = (data.get("message") or "").strip()
        receiver = conn.execute("SELECT id FROM users WHERE id = ? AND status = 'approved'", (receiver_id,)).fetchone()
        item = conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone()
        if not receiver or not item:
            return self.send_json({"error": "invalid_share"}, HTTPStatus.BAD_REQUEST)
        conn.execute(
            "INSERT INTO inbox(sender_id, receiver_id, item_id, message, status, created_at) VALUES (?, ?, ?, ?, 'unread', ?)",
            (user["id"], receiver_id, item_id, message, now_iso()),
        )
        return self.send_json({"ok": True})

    def api_inbox(self, conn: sqlite3.Connection, user: sqlite3.Row):
        incoming = conn.execute(
            """
            SELECT inbox.*, sender.username AS sender_name, items.title, items.kind, items.summary
            FROM inbox
            JOIN users sender ON sender.id = inbox.sender_id
            JOIN items ON items.id = inbox.item_id
            WHERE inbox.receiver_id = ?
            ORDER BY inbox.created_at DESC
            """,
            (user["id"],),
        ).fetchall()
        outgoing = conn.execute(
            """
            SELECT inbox.*, receiver.username AS receiver_name, items.title, items.kind, items.summary
            FROM inbox
            JOIN users receiver ON receiver.id = inbox.receiver_id
            JOIN items ON items.id = inbox.item_id
            WHERE inbox.sender_id = ?
            ORDER BY inbox.created_at DESC
            """,
            (user["id"],),
        ).fetchall()
        return self.send_json({"incoming": [dict(row) for row in incoming], "outgoing": [dict(row) for row in outgoing]})

    def api_inbox_save(self, conn: sqlite3.Connection, user: sqlite3.Row):
        data = self.read_json()
        inbox_id = int(data.get("inbox_id") or 0)
        row = conn.execute("SELECT * FROM inbox WHERE id = ? AND receiver_id = ?", (inbox_id, user["id"])).fetchone()
        if not row:
            return self.send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
        conn.execute(
            "INSERT OR IGNORE INTO favorites(user_id, item_id, created_at) VALUES (?, ?, ?)",
            (user["id"], row["item_id"], now_iso()),
        )
        conn.execute("UPDATE inbox SET status = 'saved' WHERE id = ?", (inbox_id,))
        return self.send_json({"ok": True})

    def api_repository(self, conn: sqlite3.Connection, user: sqlite3.Row, qs: dict):
        settings = ensure_settings(conn, user["id"])
        repo_name = qs.get("repo", ["wiki"])[0]
        rel = unquote(qs.get("path", [""])[0]).lstrip("/")
        if repo_name == "papers":
            root_value = settings["papers_path"]
        elif repo_name == "notes":
            root_value = str(user_notes_root(user, settings))
        else:
            repo_name = "wiki"
            root_value = settings["wiki_path"]
        root = Path(root_value).expanduser()
        if not root.is_absolute():
            root = (WORKSPACE_ROOT / root).resolve()
        root = root.resolve()
        if is_sensitive_path(root):
            return self.send_json({"error": "forbidden_repo_root"}, HTTPStatus.FORBIDDEN)
        if not root.exists():
            return self.send_json({"repo": repo_name, "exists": False, "root": str(root), "entries": [], "path": rel})
        target = (root / rel).resolve()
        if root != target and root not in target.parents:
            return self.send_json({"error": "path_outside_repo"}, HTTPStatus.BAD_REQUEST)
        if is_sensitive_path(target):
            return self.send_json({"error": "forbidden_file"}, HTTPStatus.FORBIDDEN)
        if target.is_dir():
            entries = []
            for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if child.name.startswith("."):
                    continue
                stat = child.stat()
                entries.append(
                    {
                        "name": child.name,
                        "path": str(child.relative_to(root)),
                        "type": "dir" if child.is_dir() else "file",
                        "size": stat.st_size,
                        "mtime": datetime.fromtimestamp(stat.st_mtime, LOCAL_TZ).isoformat(timespec="seconds"),
                        "ext": child.suffix.lower(),
                    }
                )
            return self.send_json({"repo": repo_name, "exists": True, "root": str(root), "path": rel, "entries": entries})
        ext = target.suffix.lower()
        readable = ext in {".md", ".txt", ".json", ".yaml", ".yml", ".csv"}
        content = ""
        if readable:
            content = target.read_text(encoding="utf-8", errors="replace")[:200_000]
        return self.send_json(
            {
                "repo": repo_name,
                "exists": True,
                "root": str(root),
                "path": rel,
                "file": {
                    "name": target.name,
                    "type": "file",
                    "ext": ext,
                    "size": target.stat().st_size,
                    "readable": readable,
                    "content": content,
                },
            }
        )

    def api_bigshots(self, conn: sqlite3.Connection, user: sqlite3.Row):
        rows = conn.execute(
            """
            SELECT * FROM scholar_follows
            ORDER BY institution_group COLLATE NOCASE, citations DESC, display_name COLLATE NOCASE
            """
        ).fetchall()
        return self.send_json(
            {
                "people": [scholar_follow_from_row(row) for row in rows],
                "month": current_month(),
                "update_policy": "monthly",
            }
        )

    def api_add_bigshot(self, conn: sqlite3.Connection, user: sqlite3.Row):
        data = self.read_json()
        name = (data.get("name") or "").strip()
        scholar_url = (data.get("scholar_url") or "").strip()
        institution = (data.get("institution") or "").strip() or "待分组机构"
        homepage_url = (data.get("homepage_url") or "").strip()
        if len(name) < 2:
            return self.send_json({"error": "invalid_bigshot"}, HTTPStatus.BAD_REQUEST)
        follow_id = safe_filename(name, "scholar").lower()
        record = scholar_follow_payload(
            follow_id,
            name,
            name,
            institution,
            institution,
            "待定时 Agent 补充 title",
            scholar_url,
            homepage_url,
            0,
            False,
            "待定时 Agent 从 Google Scholar、主页和公开资料补充科研生平简介。",
            "待补充早期研究方向。",
            "待补充近期 focus。",
            [],
            [],
            {},
        )
        conn.execute(
            """
            INSERT INTO scholar_follows(
                id, name, display_name, institution, institution_group, role_title,
                scholar_url, homepage_url, citations, has_new_this_month, last_checked_month,
                bio, early_focus, recent_focus, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                scholar_url = excluded.scholar_url,
                homepage_url = excluded.homepage_url,
                institution = excluded.institution,
                institution_group = excluded.institution_group,
                updated_at = excluded.updated_at
            """,
            record,
        )
        return self.api_bigshots(conn, user)

    def api_queue_bigshot_update(self, conn: sqlite3.Connection, user: sqlite3.Row):
        rows = conn.execute("SELECT * FROM scholar_follows ORDER BY institution_group, display_name").fetchall()
        people = [scholar_follow_from_row(row) for row in rows]
        month = current_month()
        existing = conn.execute(
            """
            SELECT id FROM agent_tasks
            WHERE user_id = ?
              AND task_type = 'bigshot_monthly_update'
              AND prompt LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user["id"], f"%月份：{month}%"),
        ).fetchone()
        if existing:
            return self.send_json({"ok": True, "task_id": existing["id"], "existing": True})
        prompt = "\n".join(
            [
                "请执行 Research Pulse 的“大牛 follow”月度更新。",
                f"月份：{month}",
                "",
                "任务：",
                "1. 逐个打开 Google Scholar / homepage / publications 页面，更新总引用量和本月是否有新 paper。",
                "2. 每个人从 Google Scholar 按时间从新到旧整理最近 5 篇论文；每篇给 title、year、venue、一句话介绍、Scholar/论文链接。",
                "3. 每个人再整理 5 篇平均年引用量 > 100 的代表作，写入 star 标记；如果不足 5 篇就只列可核验条目。",
                "4. 标题链接优先用单篇 Google Scholar 详情页；没有详情页时用 Google Scholar title 搜索页，不要虚构 URL。",
                "5. 补一段科研生平：早期做什么、代表性 title、最近 focus 是什么。",
                "6. 按机构分组输出，可用于网页展板。",
                "7. 不确定信息标注待核验，不要虚构引用量。",
                "",
                "当前关注名单：",
                json.dumps(
                    [
                        {
                            "name": person["display_name"],
                            "institution": person["institution"],
                            "scholar_url": person["scholar_url"],
                            "homepage_url": person["homepage_url"],
                        }
                        for person in people
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )
        cur = conn.execute(
            """
            INSERT INTO agent_tasks(user_id, item_id, task_type, prompt, status, created_at)
            VALUES (?, NULL, 'bigshot_monthly_update', ?, 'pending', ?)
            """,
            (user["id"], prompt, now_iso()),
        )
        return self.send_json({"ok": True, "task_id": cur.lastrowid})

    def api_admin_users(self, conn: sqlite3.Connection):
        rows = conn.execute("SELECT * FROM users ORDER BY status, role, created_at DESC").fetchall()
        return self.send_json({"users": [row_to_user(row) for row in rows]})

    def api_admin_update_user(self, conn: sqlite3.Connection, admin_user: sqlite3.Row):
        data = self.read_json()
        user_id = int(data.get("user_id") or 0)
        action = data.get("action")
        if user_id == admin_user["id"] and action in {"reject", "suspend", "remove", "make_user"}:
            return self.send_json({"error": "cannot_modify_self"}, HTTPStatus.BAD_REQUEST)
        if action == "approve":
            conn.execute("UPDATE users SET status = 'approved' WHERE id = ? AND role != 'admin'", (user_id,))
        elif action == "reject":
            conn.execute("UPDATE users SET status = 'rejected' WHERE id = ? AND role != 'admin'", (user_id,))
        elif action == "suspend":
            conn.execute("UPDATE users SET status = 'suspended' WHERE id = ? AND role != 'admin'", (user_id,))
        elif action == "make_admin":
            conn.execute("UPDATE users SET role = 'admin', status = 'approved' WHERE id = ?", (user_id,))
        elif action == "make_user":
            conn.execute("UPDATE users SET role = 'user', status = 'approved' WHERE id = ?", (user_id,))
        elif action == "remove":
            conn.execute("UPDATE users SET status = 'removed' WHERE id = ? AND role != 'admin'", (user_id,))
        else:
            return self.send_json({"error": "invalid_action"}, HTTPStatus.BAD_REQUEST)
        return self.api_admin_users(conn)

    def serve_static(self, path: str):
        if path in {"", "/"}:
            target = STATIC_ROOT / "index.html"
        else:
            clean = unquote(path).lstrip("/")
            target = (STATIC_ROOT / clean).resolve()
            if STATIC_ROOT.resolve() != target and STATIC_ROOT.resolve() not in target.parents:
                self.send_error(HTTPStatus.FORBIDDEN.value)
                return
            if not target.exists():
                target = STATIC_ROOT / "index.html"
        if not target.exists():
            self.send_error(HTTPStatus.NOT_FOUND.value)
            return
        content = target.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main():
    init_db()
    host = os.environ.get("RESEARCH_PULSE_HOST", "127.0.0.1")
    port = int(os.environ.get("RESEARCH_PULSE_PORT", "8766"))
    print(f"Research Pulse running at http://{host}:{port}")
    print("Admin account is initialized on first run. Use RESEARCH_PULSE_ADMIN_PASSWORD before first run to override the initial password.")
    ThreadingHTTPServer((host, port), ResearchPulseHandler).serve_forever()


if __name__ == "__main__":
    main()
