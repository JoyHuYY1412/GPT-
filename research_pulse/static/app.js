const app = document.querySelector("#app");

const state = {
  user: null,
  settings: null,
  view: "today",
  authMode: "login",
  feed: [],
  selected: null,
  shareUsers: [],
  dates: [],
  archiveDate: "",
  notes: [],
  inbox: { incoming: [], outgoing: [] },
  chatMessages: [],
  qmemRecords: [],
  relatedNotes: [],
  favoriteTag: "",
  archiveTag: "",
  returnContext: null,
  interestProfile: null,
  adminUsers: [],
  repo: { name: "wiki", path: "", data: null },
  drawerWidth: 860,
  message: "",
  error: "",
  lightbox: null,
  collapsedSections: {},
  settingsSection: "interest",
  settingsSaveStatus: "",
};

const kindMeta = {
  arxiv: { label: "arXiv 每日", short: "AX", title: "最新 arXiv", hint: "", icon: "spark" },
  recent: { label: "高影响力", short: "HI", title: "近两年高影响力paper", hint: "", icon: "trend" },
  archaeology: { label: "论文考古", short: "PA", title: "论文考古：经典理论&科学思维", hint: "", icon: "book" },
  scholar: { label: "人物图谱", short: "SG", title: "学术人物关系网", hint: "", icon: "network" },
  science: { label: "AI for Science", short: "AS", title: "AI for Science", hint: "", icon: "spark" },
};

const navItems = [
  ["today", "今日推送", "home"],
  ["archive", "往日记录", "calendar"],
  ["favorites", "收藏流", "star"],
  ["notes", "论文笔记", "pen"],
  ["resources", "资料库", "book"],
  ["people", "人物卡片", "network"],
  ["inbox", "收件箱", "inbox"],
  ["settings", "设置", "settings"],
];

let settingsSaveTimer = null;

const researchResources = [
  {
    group: "论文发现",
    items: [
      ["Hugging Face Daily Papers", "每日/每周/每月 paper 社区热度，适合补 arXiv daily 的人工热度信号。", "https://huggingface.co/papers"],
      ["CodeSOTA Trending", "Papers with Code 趋势页替代之一，保留 benchmark / code / score 线索。", "https://www.codesota.com/papers-with-code/trending"],
      ["Papers with Code 2", "按 paper、code、benchmark 找实现和复现线索。", "https://paperswithcode2.com/"],
    ],
  },
  {
    group: "阅读与问答",
    items: [
      ["paper-qa", "面向文档问答和引用的开源思路，可借鉴到 PDF/RAG 问答。", "https://github.com/whitead/paper-qa"],
      ["Zotero Better Notes", "Zotero 里做 paper annotation、Markdown 导出、AI 辅助笔记的完整工作流参考。", "https://github.com/windingwind/zotero-better-notes"],
      ["Zotero Better BibTeX", "Zotero + Markdown/LaTeX 写作的 citation key 和 bib 管理参考。", "https://github.com/retorquere/zotero-better-bibtex"],
    ],
  },
  {
    group: "笔记格式",
    items: [
      ["Markdown 预览", "当前网站已支持标题、加粗、列表、代码、链接、公式样式和图片。", ""],
      ["图文笔记模板", "生成草稿会自动预留 Figure 1 / Figure 2 的图文解释位置。", ""],
      ["飞书联动", "Webhook 能发消息；真正创建飞书文档需要额外配置飞书开放平台 app_id/app_secret 与文档权限。", "https://open.feishu.cn/document/server-docs/docs/drive-v1/import_task/create"],
    ],
  },
];

function h(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function displayEmail(email) {
  if (!email) return "未填邮箱";
  return email.endsWith("@local") ? "未填邮箱" : email;
}

function renderScorePill(item) {
  if (item.kind !== "arxiv") return "";
  return `<span class="score">${arxivScoreText(item)}</span>`;
}

function arxivScoreText(item) {
  const raw = Number(item.score || 0);
  const score = raw > 10 ? Math.round(raw / 10) : Math.round(raw);
  return `相关 ${Math.max(0, Math.min(10, score))}/10`;
}

function normalizeTagList(values) {
  const raw = [
    ...(Array.isArray(values) ? values : []),
  ];
  const seen = new Set();
  const hasNamedLab = raw.some((value) => /meta|openai|deepmind|google|microsoft|anthropic/i.test(String(value || "")));
  const generic = new Set([
    "high impact",
    "paper",
    "papers",
    "大公司系统论文",
    "technical report 2024",
    "近两年高影响力",
    "近两年高影响力paper",
    "daily candidate",
    "daily",
    "arxiv",
    "arxiv daily",
    "agent generated",
    "context",
    "daily archaeology",
    "daily scholar card",
    "local workspace",
    "本地知识库",
    "科学推理",
    "ai for science",
    "paper archaeology",
    "high impact",
  ]);
  const result = [];

  for (const value of raw) {
    const text = normalizeTagText(value);
    if (!text || text.includes("示例") || text === "arXiv 2026") continue;
    const key = text.toLowerCase().replace(/\s+/g, " ");
    if (generic.has(key)) continue;
    if (hasNamedLab && /大公司/.test(text)) continue;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(text);
  }
  return result.slice(0, 6);
}

function sourceTags(item) {
  if (item.kind === "scholar") return [];
  const explicit = Array.isArray(item.payload?.source_badges) ? item.payload.source_badges : [];
  if (explicit.length) return normalizeTagList(explicit).slice(0, 4);
  const fallback = item.kind === "arxiv" ? [item.payload?.primary_affiliation] : [item.org, item.venue];
  return normalizeTagList(fallback).slice(0, 4);
}

function topicTags(item) {
  return normalizeTagList([
    ...(Array.isArray(item.payload?.badges) ? item.payload.badges : []),
    ...(Array.isArray(item.tags) ? item.tags : []),
  ]).filter((tag) => !sourceTags(item).some((source) => source.toLowerCase() === tag.toLowerCase())).slice(0, 6);
}

function normalizedTags(item) {
  return normalizeTagList([...sourceTags(item), ...topicTags(item)]);
}

function normalizeTagText(value) {
  const text = String(value || "").trim();
  const map = {
    "technical report": "技术报告",
    "technical report 2024": "技术报告",
    "video generation": "视频生成",
    "video editing": "视频编辑",
    "audio generation": "音频生成",
    "personalization": "个性化",
    "editing": "编辑",
    "evaluation": "评估",
    "world model": "世界模型",
    "interactive environment": "交互环境",
    "latent action": "潜动作",
    "training-free acceleration": "免训练加速",
    "diffusion transformer": "Diffusion Transformer",
    "denoising scheduling": "去噪调度",
    "temporal coherence": "时序一致性",
    "autonomous driving": "自动驾驶",
    "controllable generation": "可控生成",
    "latent representation": "潜在表示",
    "planning": "规划",
    "robotics": "机器人",
    "affordance": "可供性",
    "language planning": "语言规划",
    "embodied intelligence": "具身智能",
    "robotic manipulation": "机器人操作",
    "cvpr/iccv 趋势": "CVPR/ICCV",
    "paper archaeology": "论文考古",
    "scientific thinking": "科学思维",
    "scholar graph": "学术关系",
    "title": "学术 Title",
    "lineage": "师承关系",
  };
  return map[text.toLowerCase()] || text;
}

function renderTags(item) {
  const topics = topicTags(item);
  if (!topics.length) return "";
  const row = (tags, className) => tags.length ? `<div class="tag-row ${className}">${tags.map((tag) => `
    <button class="pill tag-chip" data-action="archive-tag" data-tag="${h(tag)}" data-source-id="${h(item.id)}">${h(tag)}</button>
  `).join("")}</div>` : "";
  return `<div class="tag-stack">${row(topics, "topic-tags")}</div>`;
}

function renderSourceBadges(item) {
  const sources = sourceTags(item);
  if (!sources.length) return "";
  return sources.map((tag) => `
    <button class="pill tag-chip source-chip" data-action="archive-tag" data-tag="${h(tag)}" data-source-id="${h(item.id)}">${h(tag)}</button>
  `).join("");
}

function tagText(item) {
  return normalizedTags(item).join(" / ");
}

function cleanMeta(value) {
  const text = String(value || "").trim();
  if (!text || text.includes("示例") || text === "arXiv 2026") return "";
  return text;
}

function sourceLine(item) {
  return [cleanMeta(item.authors), cleanMeta(item.org), cleanMeta(item.venue)].filter(Boolean).join(" · ");
}

function renderAuthorInfo(item) {
  const affiliationText = Array.isArray(item.payload?.affiliations) && item.payload.affiliations.length
    ? item.payload.affiliations.join("; ")
    : cleanMeta(item.org);
  const rows = [
    ["作者", cleanMeta(item.authors)],
    ["单位", affiliationText],
    ["来源", cleanMeta(item.venue)],
  ].filter(([, value]) => value);
  if (!rows.length) {
    return `<div class="paper-source-grid"><div><strong>作者 / 单位</strong><span>待补充</span></div></div>`;
  }
  return `<div class="paper-source-grid">${rows.map(([label, value]) => `
    <div><strong>${h(label)}</strong><span>${h(value)}</span></div>
  `).join("")}</div>`;
}

function linkEntries(item) {
  const links = item.links || {};
  const entries = [];
  if (links.paper) {
    const isArxiv = /arxiv\.org\/abs/i.test(links.paper);
    entries.push({ key: "paper", label: isArxiv ? "arXiv Page" : "Paper Page", url: links.paper, group: "primary" });
  }
  if (links.pdf) entries.push({ key: "pdf", label: "PDF", url: links.pdf, group: "primary" });
  if (item.kind !== "scholar") {
    entries.push({
      key: "scholar",
      label: "Google Scholar",
      url: `https://scholar.google.com/scholar?q=${encodeURIComponent(item.title || "")}`,
      group: "lookup",
    });
  }
  const githubUrl = links.github || (String(links.code || "").includes("github.com") ? links.code : "");
  if (githubUrl) entries.push({ key: "github", label: "GitHub", url: githubUrl, group: "lookup" });
  if (links.project && !String(links.project).includes("github.com")) {
    entries.push({ key: "project", label: "Project", url: links.project, group: "lookup" });
  }
  if (links.profile) entries.push({ key: "profile", label: "Profile", url: links.profile, group: "primary" });
  return entries;
}

function figureExplanation(figure, index) {
  const explicit = figure.explanation || figure.note || "";
  if (explicit) return explicit;
  if (index === 0) {
    return "通常 Figure 1 用来交代任务设定、系统目标或整体问题：先看输入/输出是什么，再看它把哪些能力放到同一个任务里。";
  }
  if (index === 1) {
    return "通常 Figure 2 用来展开主要框架或关键模块：重点看数据流、模型模块、训练/推理阶段，以及每个模块解决哪个子问题。";
  }
  return "这张图适合用来补充实验设置、消融或更多实现细节。";
}

function renderAbstractContent(item) {
  const zh = item.payload?.zh_abstract || (item.payload?.source !== "arxiv-api" ? item.payload?.abstract : "") || item.summary || "";
  const original = item.payload?.original_abstract || (item.payload?.source === "arxiv-api" ? item.payload?.abstract : "");
  const same = original && zh && original.trim() === zh.trim();
  const paired = Boolean(original && !same && zh);
  return `
    <div class="abstract-stack ${paired ? "paired" : ""}">
      ${original && !same ? `<div class="abstract-card original"><strong>英文摘要</strong><p>${h(original)}</p></div>` : ""}
      ${zh ? `<div class="abstract-card"><strong>中文摘要</strong><p>${h(zh)}</p></div>` : ""}
    </div>
  `;
}

function renderRichText(value) {
  return renderMarkdown(value);
}

function isSafeMediaUrl(url) {
  const text = String(url || "").trim();
  return text.startsWith("/") || /^https?:\/\//i.test(text);
}

function renderInlineMarkdown(value) {
  return h(value || "")
    .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, url) => {
      return isSafeMediaUrl(url) ? `<img class="md-inline-image" src="${h(url)}" alt="${h(alt)}">` : h(match);
    })
    .replace(/\[([^\]]+)\]((?:\(|%28)(https?:\/\/[^)%]+)(?:\)|%29))/g, '<a href="$3" target="_blank" rel="noopener">$1</a>')
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\$([^$]+)\$/g, '<span class="math">$1</span>');
}

function flushParagraph(buffer, out) {
  if (!buffer.length) return;
  out.push(`<p>${renderInlineMarkdown(buffer.join(" "))}</p>`);
  buffer.length = 0;
}

function flushList(buffer, out) {
  if (!buffer.length) return;
  out.push(`<ul>${buffer.map((line) => `<li>${renderInlineMarkdown(line)}</li>`).join("")}</ul>`);
  buffer.length = 0;
}

function renderMarkdown(value) {
  const lines = String(value || "").replace(/\r\n/g, "\n").split("\n");
  const out = [];
  const para = [];
  const list = [];
  let code = false;
  let codeLines = [];
  lines.forEach((raw) => {
    const line = raw.trimEnd();
    if (line.trim().startsWith("```")) {
      if (code) {
        out.push(`<pre><code>${h(codeLines.join("\n"))}</code></pre>`);
        codeLines = [];
        code = false;
      } else {
        flushParagraph(para, out);
        flushList(list, out);
        code = true;
      }
      return;
    }
    if (code) {
      codeLines.push(raw);
      return;
    }
    if (!line.trim()) {
      flushParagraph(para, out);
      flushList(list, out);
      return;
    }
    const imageMatch = line.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (imageMatch && isSafeMediaUrl(imageMatch[2])) {
      flushParagraph(para, out);
      flushList(list, out);
      out.push(`<figure><img src="${h(imageMatch[2])}" alt="${h(imageMatch[1])}"><figcaption>${h(imageMatch[1])}</figcaption></figure>`);
      return;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph(para, out);
      flushList(list, out);
      const level = Math.min(heading[1].length + 2, 6);
      out.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      return;
    }
    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      flushParagraph(para, out);
      list.push(bullet[1]);
      return;
    }
    if (line.startsWith(">")) {
      flushParagraph(para, out);
      flushList(list, out);
      out.push(`<blockquote>${renderInlineMarkdown(line.replace(/^>\s?/, ""))}</blockquote>`);
      return;
    }
    flushList(list, out);
    para.push(line.trim());
  });
  flushParagraph(para, out);
  flushList(list, out);
  if (codeLines.length) out.push(`<pre><code>${h(codeLines.join("\n"))}</code></pre>`);
  return out.join("") || "<p></p>";
}

function icon(name) {
  const paths = {
    home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
    calendar: '<path d="M8 2v4M16 2v4M3 9h18"/><rect x="3" y="5" width="18" height="18" rx="2"/>',
    star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.2 6.5 20.2l1-6.2L3 9.6l6.2-.9Z"/>',
    pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    network: '<circle cx="6" cy="7" r="3"/><circle cx="18" cy="7" r="3"/><circle cx="12" cy="18" r="3"/><path d="M8.7 9.3 10.7 15M15.3 9.3 13.3 15M9 7h6"/>',
    folder: '<path d="M3 6h7l2 2h9v13H3Z"/><path d="M3 10h18"/>',
    inbox: '<path d="M4 4h16l2 12v4H2v-4Z"/><path d="M2 16h6l2 3h4l2-3h6"/>',
    settings: '<path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.2a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 0 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.2a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 0 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.2a1.7 1.7 0 0 0 1 1.5h.1a1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 0 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.2a1.7 1.7 0 0 0-1.5 1Z"/>',
    user: '<path d="M20 21a8 8 0 0 0-16 0"/><circle cx="12" cy="7" r="4"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
    spark: '<path d="M12 2v5M12 17v5M4.2 4.2l3.5 3.5M16.3 16.3l3.5 3.5M2 12h5M17 12h5M4.2 19.8l3.5-3.5M16.3 7.7l3.5-3.5"/>',
    trend: '<path d="M3 17 9 11l4 4 8-9"/><path d="M14 6h7v7"/>',
    book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H21"/><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H21v20H6.5A2.5 2.5 0 0 1 4 19.5Z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    close: '<path d="M18 6 6 18M6 6l12 12"/>',
    check: '<path d="m20 6-11 11-5-5"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>',
    lock: '<rect x="4" y="11" width="16" height="11" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  };
  return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.file}</svg>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || "request_failed");
    error.payload = data;
    throw error;
  }
  return data;
}

function setMessage(text = "", isError = false) {
  state.message = text;
  state.error = isError ? text : "";
}

async function init() {
  try {
    const data = await api("/api/me");
    state.user = data.user;
    state.settings = data.settings;
    if (state.user) {
      await Promise.all([loadFeed(), loadShareUsers()]);
      if (state.user.role === "admin") {
        const usersData = await api("/api/admin/users");
        state.adminUsers = usersData.users;
      }
    }
  } catch (error) {
    state.user = null;
  }
  render();
}

async function loadFeed({ scope = "today", date = "" } = {}) {
  const params = new URLSearchParams();
  params.set("scope", scope);
  if (date) params.set("date", date);
  const data = await api(`/api/feed?${params.toString()}`);
  state.feed = data.items;
  state.settings = data.settings;
}

async function loadShareUsers() {
  const data = await api("/api/users");
  state.shareUsers = data.users;
}

async function navigate(view) {
  state.view = view;
  state.selected = null;
  setMessage("");
  try {
    if (view === "today") await loadFeed();
    if (view === "archive") {
      const dates = await api("/api/dates");
      state.dates = dates.dates;
      state.archiveDate = state.archiveDate || state.dates[0] || "";
      if (state.archiveTag) await loadFeed({ scope: "all" });
      else await loadFeed({ date: state.archiveDate });
    }
    if (view === "favorites") await loadFeed({ scope: "all" });
    if (view === "notes") {
      const data = await api("/api/notes");
      state.notes = data.notes;
    }
    if (view === "people") await loadFeed({ scope: "all" });
    if (view === "inbox") {
      state.inbox = await api("/api/inbox");
    }
    if (view === "settings") {
      const [settingsData, profileData] = await Promise.all([api("/api/settings"), api("/api/interest_profile")]);
      state.settings = settingsData.settings;
      state.interestProfile = profileData;
      if (!state.repo.data) await loadRepo();
    }
    if (view === "admin") {
      const data = await api("/api/admin/users");
      state.adminUsers = data.users;
    }
  } catch (error) {
    setMessage(error.payload?.detail || error.message, true);
  }
  render();
}

function render() {
  if (!state.user) {
    renderAuth();
    return;
  }
  app.innerHTML = `
    <div class="shell">
      ${renderSidebar()}
      <main class="main">
        ${renderTopbar()}
        ${state.message ? `<div class="message ${state.error ? "error" : ""}">${h(state.message)}</div>` : ""}
        ${renderMain()}
      </main>
      ${renderDrawer()}
      ${renderLightbox()}
    </div>
  `;
}

function renderLightbox() {
  if (!state.lightbox) return "";
  return `
    <div class="lightbox" data-action="close-figure">
      <div class="lightbox-panel">
        <button class="icon-btn lightbox-close" data-action="close-figure" title="关闭">${icon("close")}</button>
        <img src="${h(state.lightbox.src)}" alt="${h(state.lightbox.caption)}">
        <div class="lightbox-caption">
          <strong>${h(state.lightbox.caption)}</strong>
          <span>${h(state.lightbox.explanation)}</span>
        </div>
      </div>
    </div>
  `;
}

function renderAuth() {
  const login = state.authMode === "login";
  app.innerHTML = `
    <div class="auth-page">
      <section class="auth-panel">
        <div class="brand-row">
          <div class="brand-mark">RP</div>
          <div>
            <h1>Research Pulse</h1>
            <p>科研推送、论文考古、学术人物图谱</p>
          </div>
        </div>
        <div class="auth-tabs">
          <button class="${login ? "active" : ""}" data-action="auth-mode" data-mode="login">${icon("lock")}登录</button>
          <button class="${!login ? "active" : ""}" data-action="auth-mode" data-mode="register">${icon("user")}注册</button>
        </div>
        <form class="form" data-form="${login ? "login" : "register"}">
          ${login ? renderLoginFields() : renderRegisterFields()}
          <button class="primary" type="submit">${icon(login ? "lock" : "send")}${login ? "进入工作台" : "提交注册"}</button>
          <div class="message ${state.error ? "error" : ""}">${h(state.message || (login ? "请输入账号信息登录。" : "注册后需要管理员审批才能访问。"))}</div>
        </form>
      </section>
      <section class="auth-context">
        <div>
          <h2>面向课题组的科研情报工作台</h2>
          <p class="muted">每个用户维护自己的兴趣、收藏、笔记、本地 wiki 与 papers 路径；管理员可以审批用户，并把 paper 或人物卡片转发到成员收件箱。</p>
        </div>
        <div class="auth-grid">
          ${["arXiv daily", "近两年高影响力paper", "论文考古：经典理论&科学思维", "学术人物关系网"].map((title, index) => `
            <div class="auth-card">
              <div class="cover ${Object.keys(kindMeta)[index]}"><span>${Object.values(kindMeta)[index].short}</span></div>
              <h3>${title}</h3>
              <p>${["每日相关论文雷达", "近两年高影响力paper", "经典理论&科学思维", "院士、杰青、师承和关系网"][index]}</p>
            </div>
          `).join("")}
        </div>
      </section>
    </div>
  `;
}

function renderLoginFields() {
  return `
    <div class="field">
      <label>用户名或邮箱</label>
      <input name="identity" autocomplete="username" required>
    </div>
    <div class="field">
      <label>密码</label>
      <input name="password" type="password" autocomplete="current-password" required>
    </div>
  `;
}

function renderRegisterFields() {
  return `
    <div class="field">
      <label>用户名</label>
      <input name="username" autocomplete="username" required minlength="2">
    </div>
    <div class="field">
      <label>邮箱（可选）</label>
      <input name="email" type="email" autocomplete="email" placeholder="后续接收提醒时再补也可以">
    </div>
    <div class="field">
      <label>密码</label>
      <input name="password" type="password" autocomplete="new-password" required minlength="8">
    </div>
  `;
}

function renderSidebar() {
  const adminNav = state.user.role === "admin" ? [["admin", "用户管理", "user"]] : [];
  const pendingCount = state.adminUsers.filter((user) => user.status === "pending").length;
  return `
    <aside class="sidebar">
      <div class="brand-row">
        <div class="brand-mark">RP</div>
        <div>
          <h1>Research Pulse</h1>
          <p>科研推送系统</p>
        </div>
      </div>
      <nav class="nav">
        ${[...navItems, ...adminNav].map(([view, label, ico]) => `
          <button class="${state.view === view ? "active" : ""}" data-action="nav" data-view="${view}">
            ${icon(ico)}<span>${label}</span>${view === "admin" && pendingCount ? `<b class="nav-dot">${pendingCount}</b>` : ""}
          </button>
        `).join("")}
      </nav>
      <div class="sidebar-footer">
        <div class="user-chip">
          <div class="avatar">${h(state.user.username.slice(0, 1).toUpperCase())}</div>
          <div class="truncate">
            <strong>${h(state.user.username)}</strong>
            <div class="muted">${h(state.user.role)} · ${h(state.user.status)}</div>
          </div>
        </div>
        <button class="secondary" data-action="logout">${icon("logout")}退出</button>
      </div>
    </aside>
  `;
}

function renderTopbar() {
  const titles = {
    today: ["今日推送", "按你的兴趣、负面筛选和模块开关聚合当天内容"],
    archive: ["往日记录", "每天推送都会留档，可以回看和补收藏"],
    favorites: ["收藏流", "你保存的 paper、考古卡片和人物卡片"],
    notes: ["论文笔记", "每篇 paper 都可以沉淀自己的追问和总结"],
    resources: ["资料库", "论文发现、PDF 阅读、Markdown 笔记和飞书联动的参考源"],
    people: ["学术人物关系网", "学术圈、title、师承与机构关系的每日卡片"],
    inbox: ["收件箱", "管理员和成员之间互相分享值得看的内容"],
    settings: ["设置", "兴趣画像、推送模块和本地仓库路径"],
    admin: ["用户管理", "审批注册用户，管理访问状态和角色"],
  };
  const [title, subtitle] = titles[state.view] || titles.today;
  const showSettingsButton = !["settings", "admin"].includes(state.view);
  return `
    <div class="topbar">
      <div>
        <h2>${title}</h2>
        <p>${subtitle}</p>
      </div>
      <div class="top-actions">
        <button class="secondary" data-action="refresh">${icon("spark")}刷新</button>
        ${showSettingsButton ? `<button class="primary" data-action="nav" data-view="settings">${icon("settings")}设置</button>` : ""}
      </div>
    </div>
  `;
}

function renderMain() {
  if (state.view === "archive") return renderArchive();
  if (state.view === "favorites") return renderFavorites();
  if (state.view === "notes") return renderNotes();
  if (state.view === "resources") return renderResources();
  if (state.view === "people") return renderPeople();
  if (state.view === "inbox") return renderInbox();
  if (state.view === "settings") return renderSettings();
  if (state.view === "admin") return renderAdmin();
  return renderToday();
}

function grouped() {
  return Object.keys(kindMeta).reduce((acc, kind) => {
    acc[kind] = state.feed.filter((item) => item.kind === kind);
    return acc;
  }, {});
}

function itemHasTag(item, tag) {
  const needle = String(tag || "").toLowerCase();
  return normalizedTags(item).some((entry) => entry.toLowerCase() === needle);
}

function byNewestThenScore(a, b) {
  return String(b.date || "").localeCompare(String(a.date || "")) || Number(b.score || 0) - Number(a.score || 0);
}

function favoriteSeriesKey(item) {
  const tags = normalizedTags(item).map((tag) => tag.toLowerCase());
  const title = String(item.title || "").toLowerCase();
  const text = [...tags, title].join(" ");
  const rules = [
    ["世界模型 / VLA / Agent", ["世界模型", "world model", "vla", "agent", "机器人", "可供性", "embodied"]],
    ["视频生成与可控编辑", ["视频生成", "视频编辑", "video", "diffusion", "生成"]],
    ["AI for Science / 民生", ["ai for science", "材料", "分子", "医疗", "民生", "science", "medicine"]],
    ["经典理论与科学思维", ["动力系统", "ode", "连续深度", "科学思维", "考古", "paired"]],
    ["学术人物关系网", ["院士", "杰青", "长江", "学术", "师承", "关系"]],
  ];
  const matched = rules.find(([, needles]) => needles.some((needle) => text.includes(needle)));
  return matched ? matched[0] : "其他收藏";
}

function groupFavorites(items) {
  return items.reduce((acc, item) => {
    const key = favoriteSeriesKey(item);
    if (!acc[key]) acc[key] = [];
    acc[key].push(item);
    return acc;
  }, {});
}

function renderStats(items = state.feed) {
  const g = Object.keys(kindMeta).map((kind) => [kind, items.filter((item) => item.kind === kind).length]);
  return `
    <div class="stats">
      ${g.map(([kind, count]) => `
        <div class="stat">
          <span>${kindMeta[kind].title}</span>
          <strong>${count}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function renderToday() {
  const groups = grouped();
  const favorites = state.feed.filter((item) => item.favorite);
  return `
    ${renderStats()}
    ${renderRail(favorites, "收藏流", "")}
    ${Object.keys(kindMeta).map((kind) => renderSection(kindMeta[kind].title, kindMeta[kind].hint, groups[kind], kind)).join("")}
  `;
}

function renderRail(items, title, hint) {
  const shouldScroll = items.length >= 4;
  const railItems = shouldScroll ? [...items, ...items] : items;
  return `
    <section class="rail-panel">
      <div class="panel-head">
        <div>
          <h3>${h(title)}</h3>
          ${hint ? `<div class="muted">${h(hint)}</div>` : ""}
        </div>
        <button class="secondary" data-action="nav" data-view="favorites">${icon("star")}收藏夹</button>
      </div>
      <div class="rail">
        <div class="rail-track ${shouldScroll ? "scrolling" : "static"}">
          ${railItems.length ? railItems.map(renderMiniCard).join("") : `<div class="empty">还没有可以滚动展示的内容。</div>`}
        </div>
      </div>
    </section>
  `;
}

function renderMiniCard(item) {
  const meta = kindMeta[item.kind] || { label: item.kind || "条目" };
  return `
    <article class="mini-card" role="button" tabindex="0" data-action="select" data-id="${h(item.id)}">
      <div class="mini-meta">
        <span class="kind-badge ${h(item.kind)}">${h(meta.label)}</span>
        <span class="pill">${h(item.date || "")}</span>
      </div>
      <h4>${h(item.title)}</h4>
      <p>${h(item.summary)}</p>
    </article>
  `;
}

function renderSection(title, hint, items, sectionId = title) {
  const collapsed = Boolean(state.collapsedSections[sectionId]);
  return `
    <section class="section ${collapsed ? "collapsed" : ""}">
      <div class="panel-head">
        <div>
          <h3>${h(title)}</h3>
          ${hint ? `<div class="muted">${h(hint)}</div>` : ""}
        </div>
        <div class="inline-row">
          <span class="pill">${items.length}</span>
          <button class="secondary compact-btn" data-action="toggle-section" data-section="${h(sectionId)}">${collapsed ? "展开" : "收起"}</button>
        </div>
      </div>
      ${collapsed ? "" : (items.length ? `<div class="section-grid">${items.map(renderItemCard).join("")}</div>` : `<div class="empty">这个模块今天没有推送，或已在设置里关闭。</div>`)}
    </section>
  `;
}

function renderItemCard(item) {
  const meta = kindMeta[item.kind] || { label: item.kind || "条目", short: "RP" };
  return `
    <article class="item-card" data-action="select" data-id="${h(item.id)}">
      <div class="cover ${h(item.kind)}"><span>${meta.short}</span></div>
      <div class="item-main">
        <div class="meta-row">
          <span class="kind-badge ${h(item.kind)}">${meta.label}</span>
          ${renderScorePill(item)}
          ${renderSourceBadges(item)}
        </div>
        ${renderTags(item)}
        <h4>${h(item.title)}</h4>
        <p class="summary">${h(item.summary)}</p>
        <div class="card-actions">
          <button class="secondary" data-action="favorite" data-id="${h(item.id)}" data-favorite="${item.favorite ? "0" : "1"}">
            ${icon("star")}${item.favorite ? "已收藏" : "收藏"}
          </button>
          <button class="ghost" data-action="select" data-id="${h(item.id)}">${icon("pen")}笔记</button>
        </div>
      </div>
    </article>
  `;
}

function renderArchive() {
  if (state.archiveTag) {
    const items = state.feed.filter((item) => itemHasTag(item, state.archiveTag)).sort(byNewestThenScore);
    return `
      <div class="filter-bar">
        <span>往日记录标签：<strong>${h(state.archiveTag)}</strong></span>
        <div class="inline-row">
          ${state.returnContext ? `<button class="secondary" data-action="return-context">${icon("close")}返回刚才文章</button>` : ""}
          <button class="secondary" data-action="clear-archive-tag">${icon("close")}显示全部往日记录</button>
        </div>
      </div>
      ${renderStats(items)}
      ${items.length ? `<section class="section"><div class="section-grid">${items.map(renderItemCard).join("")}</div></section>` : `<div class="section"><div class="empty">还没有匹配这个标签的历史内容。</div></div>`}
    `;
  }
  return `
    <div class="inline-row" style="margin-bottom: 14px;">
      ${state.dates.map((date) => `<button class="${state.archiveDate === date ? "primary" : "secondary"}" data-action="archive-date" data-date="${h(date)}">${h(date)}</button>`).join("")}
    </div>
    ${renderStats()}
    ${Object.keys(kindMeta).map((kind) => renderSection(kindMeta[kind].title, `${state.archiveDate || "往日"} 的留档`, grouped()[kind])).join("")}
  `;
}

function renderFavorites() {
  const items = state.feed.filter((item) => item.favorite && (!state.favoriteTag || normalizedTags(item).some((tag) => tag.toLowerCase() === state.favoriteTag.toLowerCase())));
  const series = groupFavorites(items);
  return `
    ${state.favoriteTag ? `<div class="filter-bar">
      <span>收藏夹标签：<strong>${h(state.favoriteTag)}</strong></span>
      <div class="inline-row">
        ${state.returnContext ? `<button class="secondary" data-action="return-context">${icon("close")}返回刚才文章</button>` : ""}
        <button class="secondary" data-action="clear-favorite-tag">${icon("close")}显示全部收藏</button>
      </div>
    </div>` : ""}
    ${renderStats(items)}
    ${renderRail(items, "收藏流", "所有收藏会自动汇入这个滚动条")}
    ${items.length ? Object.entries(series).map(([name, group]) => `
      <section class="section favorite-series">
        <div class="panel-head">
          <div>
            <h3>${h(name)}</h3>
            <div class="muted">${group.length} 条收藏</div>
          </div>
        </div>
        <div class="section-grid">${group.sort(byNewestThenScore).map(renderItemCard).join("")}</div>
      </section>
    `).join("") : `<div class="section"><div class="empty">还没有收藏。打开任意卡片或点卡片上的收藏按钮即可保存。</div></div>`}
  `;
}

function renderNotes() {
  return `
    <section class="section">
      <div class="panel-head">
        <h3>我的笔记</h3>
        <button class="secondary" data-action="nav" data-view="today">${icon("plus")}从今日推送添加</button>
      </div>
      <div class="list" style="padding: 14px;">
        ${state.notes.length ? state.notes.map((note) => `
          <button class="list-item" data-action="select" data-id="${h(note.item_id)}">
            <div class="meta-row">
              <span class="kind-badge ${h(note.item_kind)}">${kindMeta[note.item_kind]?.label || note.item_kind}</span>
              <span class="pill">${h(note.updated_at)}</span>
            </div>
            <h4>${h(note.title)}</h4>
            <p>${h(note.content).slice(0, 220)}</p>
          </button>
        `).join("") : `<div class="empty">还没有笔记。每篇 paper 的右侧详情里可以直接写。</div>`}
      </div>
    </section>
  `;
}

function renderResources() {
  return `
    <div class="resource-grid">
      ${researchResources.map((group) => `
        <section class="section resource-section">
          <div class="panel-head"><h3>${h(group.group)}</h3></div>
          <div class="list" style="padding: 14px;">
            ${group.items.map(([title, desc, url]) => `
              <article class="list-item resource-card">
                <h4>${h(title)}</h4>
                <p>${h(desc)}</p>
                ${url ? `<a class="paper-link" href="${h(url)}" target="_blank" rel="noopener">打开资料</a>` : ""}
              </article>
            `).join("")}
          </div>
        </section>
      `).join("")}
    </div>
  `;
}

function renderPeople() {
  const people = state.feed.filter((item) => item.kind === "scholar");
  return `
    ${renderRail(people, "人物卡片流", "人物、title、师承、合作和机构关系会汇入这里")}
    ${renderSection("学术人物关系网", "", people)}
  `;
}

function renderRepo() {
  const data = state.repo.data;
  const entries = data?.entries || [];
  const file = data?.file;
  const parent = state.repo.path.split("/").slice(0, -1).join("/");
  const repoLabels = { wiki: "wiki", papers: "papers", notes: "notes" };
  return `
    <section class="repo-panel">
      <aside class="repo-sidebar">
        <div class="repo-toolbar">
          ${Object.keys(repoLabels).map((repo) => `
            <button class="${state.repo.name === repo ? "primary" : "secondary"}" data-action="repo-switch" data-repo="${repo}">
              ${icon(repo === "wiki" ? "book" : "folder")}${repoLabels[repo]}
            </button>
          `).join("")}
        </div>
        <div class="panel-head">
          <div>
            <h3>${h(repoLabels[state.repo.name] || state.repo.name)}</h3>
            <div class="muted">${h(data?.root || "")}</div>
          </div>
        </div>
        <div class="repo-list">
          ${state.repo.path ? `<button class="file-row" data-action="repo-open" data-path="${h(parent)}">${icon("folder")}上一级</button>` : ""}
          ${data && !data.exists ? `<div class="empty">路径不存在，可以在设置里修改 ${h(state.repo.name)} 路径。</div>` : ""}
          ${entries.map((entry) => `
            <button class="file-row" data-action="repo-open" data-path="${h(entry.path)}">
              <span class="truncate">${icon(entry.type === "dir" ? "folder" : "file")}${h(entry.name)}</span>
              <span class="muted">${entry.type === "dir" ? "dir" : h(entry.ext || "file")}</span>
            </button>
          `).join("")}
        </div>
      </aside>
      <div class="repo-viewer">
        ${file ? renderFile(file) : `
          <h3>本地知识源</h3>
          <div class="list" style="margin-top: 16px;">
            <div class="list-item"><h4>wiki</h4><p>QMem/GPT 对话记录、paper 讨论和想法备忘。</p></div>
            <div class="list-item"><h4>papers</h4><p>本地 PDF 与已读论文材料。</p></div>
            <div class="list-item"><h4>notes</h4><p>网页里生成和保存的 markdown 笔记。</p></div>
          </div>
        `}
      </div>
    </section>
  `;
}

function renderFile(file) {
  if (!file.readable) {
    return `
      <h3>${h(file.name)}</h3>
      <p class="muted">这个文件类型暂不在网页里直接预览。大小：${file.size} bytes。</p>
    `;
  }
  return `
    <h3>${h(file.name)}</h3>
    <pre class="repo-content">${h(file.content)}</pre>
  `;
}

function renderInbox() {
  return `
    <div class="split">
      <section class="section">
        <div class="panel-head"><h3>收到的分享</h3></div>
        <div class="list" style="padding: 14px;">
          ${state.inbox.incoming.length ? state.inbox.incoming.map((item) => `
            <div class="list-item">
              <div class="meta-row">
                <span class="kind-badge ${h(item.kind)}">${kindMeta[item.kind]?.label || item.kind}</span>
                <span class="pill">来自 ${h(item.sender_name)}</span>
                <span class="pill">${h(item.status)}</span>
              </div>
              <h4>${h(item.title)}</h4>
              <p>${h(item.message || item.summary)}</p>
              <div class="inline-row">
                <button class="primary" data-action="inbox-save" data-id="${item.id}">${icon("star")}保存到收藏</button>
                <button class="secondary" data-action="select" data-id="${h(item.item_id)}">${icon("pen")}打开</button>
              </div>
            </div>
          `).join("") : `<div class="empty">暂无收到的分享。</div>`}
        </div>
      </section>
      <section class="section">
        <div class="panel-head"><h3>我发出的分享</h3></div>
        <div class="list" style="padding: 14px;">
          ${state.inbox.outgoing.length ? state.inbox.outgoing.map((item) => `
            <div class="list-item">
              <div class="meta-row">
                <span class="pill">发给 ${h(item.receiver_name)}</span>
                <span class="pill">${h(item.status)}</span>
              </div>
              <h4>${h(item.title)}</h4>
              <p>${h(item.message || item.summary)}</p>
            </div>
          `).join("") : `<div class="empty">还没有分享给别人。</div>`}
        </div>
      </section>
    </div>
  `;
}

function renderSettings() {
  const s = state.settings || {};
  const modules = s.modules || {};
  const counts = s.counts || {};
  const profile = state.interestProfile || { manual_terms: [], excluded_terms: [], suggested_terms: [], local_sources: [] };
  const moduleDefaults = { arxiv: 10, recent: 5, archaeology: 6, scholar: 1, science: 3 };
  const settingsNav = [
    ["interest", "兴趣画像"],
    ["modules", "功能开启"],
    ["paths", "仓库路径"],
    ["local", "本地预览"],
  ];
  return `
    <div class="settings-layout">
      <aside class="settings-subnav">
        ${settingsNav.map(([id, label]) => `
          <button type="button" data-action="settings-jump" data-target="${id}">
            <span></span>${h(label)}
          </button>
        `).join("")}
        <div class="save-status">${h(state.settingsSaveStatus || "修改后自动保存")}</div>
      </aside>
      <form class="settings-panel" data-form="settings">
        <section class="settings-section" id="settings-interest">
          <div class="panel-head inline-head">
            <h3>兴趣画像</h3>
            <button class="secondary" type="button" data-action="refresh-interest">${icon("spark")}重新读取</button>
          </div>
          <div class="interest-box wide">
            <h4>人工关键词</h4>
            <textarea name="positive_keywords">${h(s.positive_keywords || "")}</textarea>
          </div>
          <div class="interest-box wide">
            <h4>排除关键词</h4>
            <textarea name="negative_keywords">${h(s.negative_keywords || "")}</textarea>
          </div>
          <div class="interest-box wide">
            <h4>推荐关键词</h4>
            <div class="tag-row suggested-tags">
              ${profile.suggested_terms.length ? profile.suggested_terms.map((entry) => `
                <button class="pill chip-button" type="button" data-action="add-interest-term" data-term="${h(entry.term)}" title="${h(entry.sources.join(" / "))}">
                  ${h(entry.term)}
                </button>
              `).join("") : `<span class="muted">暂无推荐关键词。</span>`}
            </div>
          </div>
          <div class="interest-box wide">
            <h4>兴趣画像 Prompt</h4>
            <textarea name="interest_prompt">${h(s.interest_prompt || "")}</textarea>
          </div>
        </section>
        <section class="settings-section" id="settings-modules">
          <div class="panel-head inline-head"><h3>功能开启</h3></div>
          <div class="module-list">
            ${Object.keys(kindMeta).map((kind) => `
              <div class="toggle-row">
                <div>
                  <strong>${kindMeta[kind].title}</strong>
                </div>
                <div class="inline-row">
                  <label class="switch"><input name="module_${kind}" type="checkbox" ${modules[kind] !== false ? "checked" : ""}><i></i></label>
                  <input name="count_${kind}" type="number" min="1" max="20" value="${h(counts[kind] || moduleDefaults[kind] || 5)}">
                </div>
              </div>
            `).join("")}
          </div>
        </section>
        <section class="settings-section" id="settings-paths">
          <div class="panel-head inline-head"><h3>仓库路径</h3></div>
          <div class="path-list">
            <div class="field">
              <label>wiki 仓库路径</label>
              <input name="wiki_path" value="${h(s.wiki_path || "")}">
            </div>
            <div class="field">
              <label>papers 仓库路径</label>
              <input name="papers_path" value="${h(s.papers_path || "")}">
            </div>
            <div class="field">
              <label>notes 笔记仓库路径</label>
              <input name="notes_path" value="${h(s.notes_path || "")}">
            </div>
          </div>
        </section>
        <section class="settings-section" id="settings-local">
          <div class="panel-head inline-head"><h3>本地预览</h3></div>
          ${renderRepo()}
        </section>
      </form>
    </div>
  `;
}

function renderAdmin() {
  const pending = state.adminUsers.filter((user) => user.status === "pending");
  const existing = state.adminUsers.filter((user) => user.status !== "pending" && user.status !== "removed");
  const userRow = (user) => `
    <tr>
      <td>${h(user.username)}</td>
      <td>${h(displayEmail(user.email))}</td>
      <td>${h(user.role === "admin" ? "管理员" : "用户")}</td>
      <td>${h(user.created_at)}</td>
      <td>
        <div class="inline-row">
          ${user.id === state.user.id ? `<span class="pill">当前管理员</span>` : `
            ${user.role === "admin"
              ? `<button class="secondary" data-action="admin-user" data-user="${user.id}" data-admin-action="make_user">设为用户</button>`
              : `<button class="secondary" data-action="admin-user" data-user="${user.id}" data-admin-action="make_admin">授为管理员</button>`}
            <button class="danger" data-action="admin-user" data-user="${user.id}" data-admin-action="remove">移除</button>
          `}
        </div>
      </td>
    </tr>
  `;
  return `
    <div class="admin-stack">
      <section class="table-panel">
        <div class="panel-head"><h3>正在申请</h3><span class="pill">${pending.length}</span></div>
        <table>
          <thead>
            <tr><th>用户</th><th>邮箱</th><th>注册时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            ${pending.length ? pending.map((user) => `
            <tr>
              <td>${h(user.username)}</td>
              <td>${h(displayEmail(user.email))}</td>
              <td>${h(user.created_at)}</td>
              <td>
                <div class="inline-row">
                  <button class="primary" data-action="admin-user" data-user="${user.id}" data-admin-action="approve">${icon("check")}通过</button>
                  <button class="danger" data-action="admin-user" data-user="${user.id}" data-admin-action="reject">不通过</button>
                </div>
              </td>
            </tr>
          `).join("") : `<tr><td colspan="4"><div class="empty compact">当前没有待审批用户。</div></td></tr>`}
          </tbody>
        </table>
      </section>
      <section class="table-panel">
        <div class="panel-head"><h3>现存用户</h3><span class="pill">${existing.length}</span></div>
        <table>
          <thead>
            <tr><th>用户</th><th>邮箱</th><th>身份</th><th>注册时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            ${existing.length ? existing.map(userRow).join("") : `<tr><td colspan="5"><div class="empty compact">还没有已通过用户。</div></td></tr>`}
          </tbody>
        </table>
      </section>
    </div>
  `;
}

function renderDrawer() {
  const item = state.selected;
  if (!item) return `<aside class="drawer"></aside>`;
  const meta = kindMeta[item.kind] || kindMeta.arxiv;
  const noteContent = item.note?.content || "";
  const noteTitle = item.note?.title || `${item.title} 笔记`;
  const isScholar = item.kind === "scholar";
  return `
    <aside class="drawer open" style="--drawer-width: ${state.drawerWidth}px;">
      <div class="drawer-resize-handle" title="拖拽调整宽度"></div>
      <div class="drawer-head">
        <div>
          <span class="kind-badge ${h(item.kind)}">${meta.label}</span>
          <h3>${h(item.title)}</h3>
        </div>
        <button class="icon-btn" data-action="close-drawer" title="关闭">${icon("close")}</button>
      </div>
      <div class="drawer-body">
        <div class="detail-block">
          <div class="meta-row">
            <span class="kind-badge ${h(item.kind)}">${meta.label}</span>
            ${renderScorePill(item)}
            ${renderSourceBadges(item)}
          </div>
          ${renderTags(item)}
        </div>
        ${isScholar ? renderScholarDetail(item) : renderPaperDetail(item, noteTitle, noteContent)}
        <form class="detail-block" data-form="share" data-id="${h(item.id)}">
          <h4>分享给成员</h4>
          <div class="field">
            <select name="receiver_id" required>
              <option value="">选择用户</option>
              ${state.shareUsers.map((user) => `<option value="${user.id}">${h(user.username)} · ${h(displayEmail(user.email))}</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <textarea name="message" placeholder="写一句为什么推荐给 TA。"></textarea>
          </div>
          <button class="secondary" type="submit">${icon("send")}发送到收件箱</button>
        </form>
      </div>
    </aside>
  `;
}

function renderPaperDetail(item, noteTitle, noteContent) {
  const links = linkEntries(item);
  const contributions = Array.isArray(item.payload?.contributions) ? item.payload.contributions : [];
  const framework = Array.isArray(item.payload?.framework) ? item.payload.framework : [];
  const figures = Array.isArray(item.payload?.figures) ? item.payload.figures : [];
  return `
    <div class="detail-flow">
      <section class="detail-block">
        <h4>论文入口</h4>
        <div class="paper-meta">
          ${links.length ? `<div class="paper-links">${links.map((link) => `
            <a class="paper-link ${h(link.group || "")}" href="${h(link.url)}" target="_blank" rel="noopener">${h(link.label)}</a>
          `).join("")}</div>` : ""}
          ${renderAuthorInfo(item)}
        </div>
      </section>
      <section class="detail-block">
        <h4>文章摘要</h4>
        ${renderAbstractContent(item)}
      </section>
      <section class="detail-block">
        <h4>核心贡献</h4>
        ${contributions.length ? `<ul class="tight-list">${contributions.map((entry) => `<li>${renderInlineMarkdown(entry)}</li>`).join("")}</ul>` : `<div class="markdown-body">${renderMarkdown(item.summary)}</div>`}
      </section>
      <section class="detail-block">
        <h4>主要框架</h4>
        ${framework.length ? `<ul class="tight-list">${framework.map((entry) => `<li>${renderInlineMarkdown(entry)}</li>`).join("")}</ul>` : `<div class="markdown-body">${renderMarkdown(item.thinking)}</div>`}
        ${figures.length ? `<div class="figure-grid">${figures.slice(0, 2).map((figure, index) => `
          <figure class="paper-figure">
            <button class="figure-zoom" type="button" data-action="open-figure" data-src="${h(figure.url)}" data-caption="${h(figure.caption || `Figure ${index + 1}`)}" data-explanation="${h(figureExplanation(figure, index))}">
              <img src="${h(figure.url)}" alt="${h(figure.caption || `Figure ${index + 1}`)}">
            </button>
            <figcaption>
              <strong>${h(figure.caption || `Figure ${index + 1}`)}</strong>
              <span>${h(figureExplanation(figure, index))}</span>
            </figcaption>
          </figure>
        `).join("")}</div>` : ""}
      </section>
      <section class="detail-block">
        <h4>为什么值得读</h4>
        <div class="markdown-body">${renderMarkdown(item.why)}</div>
      </section>
    </div>
    <form class="detail-block" data-form="chat" data-id="${h(item.id)}">
      <h4>关于这篇文章的提问</h4>
      <div class="chat-log">
        ${state.chatMessages.length ? state.chatMessages.map((msg) => `
          <div class="chat-msg ${h(msg.role)}">
            <strong>${msg.role === "user" ? "我" : "DeepSeek / Agent"}</strong>
            <div class="markdown-body chat-content">${renderRichText(msg.content)}</div>
          </div>
        `).join("") : `<div class="empty compact">还没有针对这篇 paper 的提问。</div>`}
      </div>
      <div class="field">
        <textarea name="content" placeholder="这篇文章的核心假设是什么？"></textarea>
      </div>
      <div class="inline-row">
        <button class="primary" type="submit">${icon("send")}回答</button>
        <button class="secondary" type="button" data-action="copy-gpt-prompt">${icon("spark")}复制上下文到 GPT</button>
      </div>
    </form>
    <form class="note-editor detail-block" data-form="note" data-id="${h(item.id)}">
      <h4>生成笔记草稿</h4>
      <input type="hidden" name="title" value="${h(noteTitle)}">
      <textarea name="content" placeholder="可以写：问题定义、核心方法、数据假设、启发、我想继续追问什么。">${h(noteContent)}</textarea>
      ${noteContent ? `
        <details class="markdown-preview" open>
          <summary>Markdown 预览</summary>
          <div class="markdown-body">${renderMarkdown(noteContent)}</div>
        </details>
      ` : ""}
      <div class="inline-row">
        <button class="primary" type="button" data-action="generate-note">${icon("pen")}生成草稿</button>
        <button class="secondary" type="submit">${icon("check")}保存笔记</button>
        <button class="secondary" type="button" data-action="send-feishu-note" data-id="${h(item.id)}">${icon("send")}发送到飞书文档</button>
        <button class="secondary" type="button" data-action="favorite" data-id="${h(item.id)}" data-favorite="${item.favorite ? "0" : "1"}">${icon("star")}${item.favorite ? "取消收藏" : "收藏"}</button>
      </div>
    </form>
    <div class="detail-block">
      <h4>已有相关笔记</h4>
      ${state.relatedNotes.length ? `<div class="related-note-list">${state.relatedNotes.map((note, index) => `
        <details class="related-note" ${index === 0 ? "open" : ""}>
          <summary>
            <strong>${h(note.title)}</strong>
            <span>${h(note.path)}</span>
          </summary>
          <div class="markdown-body related-note-preview">${renderMarkdown(note.content)}</div>
        </details>
      `).join("")}</div>` : `<p>还没有相关笔记。生成草稿并保存后，会写入根目录的 notes 文件夹。</p>`}
    </div>
  `;
}

function renderScholarDetail(item) {
  const sections = item.payload?.sections || [];
  const relations = item.payload?.relations || [];
  const titles = item.payload?.titles || [];
  const scholarTags = (titles.length ? titles : item.tags).filter(Boolean);
  return `
    <div class="detail-flow">
      <section class="detail-block">
        <h4>简介</h4>
        <p>${h(item.summary)}</p>
      </section>
      <section class="detail-block">
        <h4>Title / 身份</h4>
        <div class="tag-row">${scholarTags.map((tag) => `
          <button class="pill tag-chip" data-action="archive-tag" data-tag="${h(tag)}" data-source-id="${h(item.id)}">${h(tag)}</button>
        `).join("")}</div>
      </section>
      <section class="detail-block">
        <h4>师承 / 学生 / 合作关系</h4>
        ${relations.length ? `<div class="list">${relations.map((rel) => `
          <div class="list-item compact">
            <strong>${h(rel.name || rel)}</strong>
            <p>${h(rel.note || "")}</p>
          </div>
        `).join("")}</div>` : `<p>${h(item.thinking || "待定时 Agent 补充师承、合作、学生、机构和来源核验。")}</p>`}
      </section>
      <section class="detail-block">
        <h4>其他关系网</h4>
        <p>${h(item.why || "待定时 Agent 补充国内学术流派、人才 title、机构脉络和潜在合作网络。")}</p>
      </section>
      <section class="detail-block">
        <h4>核验状态</h4>
        <p>${h(item.payload?.source || "待核验来源")} · ${sections.map(h).join(" / ")}</p>
      </section>
    </div>
    <div class="inline-row detail-block">
      <button class="secondary" type="button" data-action="favorite" data-id="${h(item.id)}" data-favorite="${item.favorite ? "0" : "1"}">${icon("star")}${item.favorite ? "取消收藏" : "收藏"}</button>
    </div>
  `;
}

function findItem(id) {
  return state.feed.find((item) => item.id === id) || null;
}

async function selectItem(id) {
  let item = findItem(id);
  if (!item) {
    await loadFeed({ scope: "all" });
    item = findItem(id);
  }
  state.selected = item;
  state.chatMessages = [];
  state.qmemRecords = [];
  state.relatedNotes = [];
  if (item && item.kind !== "scholar") {
    const [chat, qmem, relatedNotes] = await Promise.all([
      api(`/api/chat?item_id=${encodeURIComponent(item.id)}`),
      api(`/api/qmem?item_id=${encodeURIComponent(item.id)}`),
      api(`/api/related_notes?item_id=${encodeURIComponent(item.id)}`),
    ]);
    state.chatMessages = chat.messages || [];
    state.qmemRecords = qmem.records || [];
    state.relatedNotes = relatedNotes.notes || [];
  }
  render();
}

async function loadRepo(path = state.repo.path) {
  const params = new URLSearchParams({ repo: state.repo.name, path: path || "" });
  state.repo.path = path || "";
  state.repo.data = await api(`/api/repository?${params.toString()}`);
}

function setSettingsSaveStatus(text, isError = false) {
  state.settingsSaveStatus = text;
  const el = document.querySelector(".save-status");
  if (el) {
    el.textContent = text;
    el.classList.toggle("error", isError);
  }
}

function collectSettingsPayload(form) {
  const current = state.settings || {};
  const data = new FormData(form);
  const modules = { ...(current.modules || {}) };
  const counts = { ...(current.counts || {}) };
  Object.keys(kindMeta).forEach((kind) => {
    const moduleInput = form.querySelector(`[name="module_${kind}"]`);
    const countInput = form.querySelector(`[name="count_${kind}"]`);
    if (moduleInput) modules[kind] = Boolean(moduleInput.checked);
    if (countInput) counts[kind] = Number(countInput.value || 1);
  });
  return {
    modules,
    counts,
    positive_keywords: data.get("positive_keywords") ?? current.positive_keywords ?? "",
    negative_keywords: data.get("negative_keywords") ?? current.negative_keywords ?? "",
    interest_prompt: data.get("interest_prompt") ?? current.interest_prompt ?? "",
    wiki_path: data.get("wiki_path") ?? current.wiki_path ?? "",
    papers_path: data.get("papers_path") ?? current.papers_path ?? "",
    notes_path: data.get("notes_path") ?? current.notes_path ?? "",
  };
}

async function saveSettings(form) {
  if (!form) return;
  setSettingsSaveStatus("保存中...");
  try {
    const result = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify(collectSettingsPayload(form)),
    });
    state.settings = result.settings;
    setSettingsSaveStatus("已自动保存");
  } catch (error) {
    setSettingsSaveStatus("保存失败", true);
  }
}

function scheduleSettingsSave(form, delay = 500) {
  window.clearTimeout(settingsSaveTimer);
  settingsSaveTimer = window.setTimeout(() => saveSettings(form), delay);
}

document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  if (action === "select" && window.getSelection()?.toString().trim()) {
    event.preventDefault();
    event.stopPropagation();
    return;
  }
  if (action !== "select") event.preventDefault();
  try {
    if (action === "auth-mode") {
      state.authMode = target.dataset.mode;
      setMessage("");
      renderAuth();
    }
    if (action === "open-figure") {
      event.stopPropagation();
      state.lightbox = {
        src: target.dataset.src || "",
        caption: target.dataset.caption || "Figure",
        explanation: target.dataset.explanation || "",
      };
      render();
    }
    if (action === "close-figure") {
      state.lightbox = null;
      render();
    }
    if (action === "nav") await navigate(target.dataset.view);
    if (action === "refresh") await navigate(state.view);
    if (action === "settings-jump") {
      const section = document.querySelector(`#settings-${target.dataset.target}`);
      section?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (action === "toggle-section") {
      const sectionId = target.dataset.section || "";
      state.collapsedSections[sectionId] = !state.collapsedSections[sectionId];
      render();
    }
    if (action === "archive-tag") {
      event.stopPropagation();
      state.archiveTag = target.dataset.tag || "";
      state.returnContext = { view: state.view, itemId: target.dataset.sourceId || state.selected?.id || "" };
      state.selected = null;
      state.view = "archive";
      const dates = await api("/api/dates");
      state.dates = dates.dates;
      state.archiveDate = state.archiveDate || state.dates[0] || "";
      await loadFeed({ scope: "all" });
      render();
    }
    if (action === "clear-archive-tag") {
      state.archiveTag = "";
      state.returnContext = null;
      await navigate("archive");
    }
    if (action === "clear-favorite-tag") {
      state.favoriteTag = "";
      state.returnContext = null;
      render();
    }
    if (action === "return-context") {
      const ctx = state.returnContext;
      state.favoriteTag = "";
      state.archiveTag = "";
      state.returnContext = null;
      if (ctx?.view) state.view = ctx.view;
      if (ctx?.itemId) await selectItem(ctx.itemId);
      else render();
    }
    if (action === "refresh-interest") {
      const profileData = await api("/api/interest_profile");
      state.interestProfile = profileData;
      render();
    }
    if (action === "add-interest-term") {
      const textarea = document.querySelector('textarea[name="positive_keywords"]');
      const term = target.dataset.term || "";
      if (textarea && term) {
        const existing = textarea.value.split(/[,，;；\n]/).map((part) => part.trim().toLowerCase()).filter(Boolean);
        if (!existing.includes(term.toLowerCase())) {
          textarea.value = textarea.value.trim() ? `${textarea.value.trim()}, ${term}` : term;
          scheduleSettingsSave(textarea.closest('form[data-form="settings"]'), 200);
        }
      }
    }
    if (action === "logout") {
      await api("/api/logout", { method: "POST", body: "{}" });
      state.user = null;
      state.settings = null;
      renderAuth();
    }
    if (action === "select") await selectItem(target.dataset.id);
    if (action === "close-drawer") {
      state.selected = null;
      render();
    }
    if (action === "favorite") {
      event.stopPropagation();
      await api("/api/favorite", {
        method: "POST",
        body: JSON.stringify({ item_id: target.dataset.id, favorite: target.dataset.favorite === "1" }),
      });
      state.feed.forEach((item) => {
        if (item.id === target.dataset.id) item.favorite = target.dataset.favorite === "1";
      });
      if (state.selected?.id === target.dataset.id) state.selected.favorite = target.dataset.favorite === "1";
      render();
    }
    if (action === "generate-note") {
      const form = document.querySelector('form[data-form="note"]');
      const textarea = form?.querySelector('textarea[name="content"]');
      const title = form?.querySelector('input[name="title"]');
      if (state.selected && textarea && title) {
        title.value = `${state.selected.title} 阅读笔记`;
        textarea.value = draftNote(state.selected, state.chatMessages);
      }
    }
    if (action === "copy-gpt-prompt") {
      if (!state.selected) return;
      const form = document.querySelector('form[data-form="chat"]');
      const userQuestion = form?.querySelector('textarea[name="content"]')?.value || "";
      const prompt = buildGptPrompt(state.selected, userQuestion, state.qmemRecords);
      await navigator.clipboard.writeText(prompt);
      window.open("https://chatgpt.com/", "_blank", "noopener");
      setMessage("上下文 prompt 已复制，已打开 GPT。");
      render();
    }
    if (action === "send-feishu-note") {
      const form = document.querySelector('form[data-form="note"]');
      const title = form?.querySelector('input[name="title"]')?.value || `${state.selected?.title || ""} 笔记`;
      const content = form?.querySelector('textarea[name="content"]')?.value || "";
      const result = await api("/api/feishu/note", {
        method: "POST",
        body: JSON.stringify({ item_id: target.dataset.id, title, content }),
      });
      setMessage(result.sent ? "已发送到飞书消息。" : `未检测到可用 webhook，已写入草稿：${result.draft_path || ""}`);
      render();
    }
    if (action === "archive-date") {
      state.archiveTag = "";
      state.returnContext = null;
      state.archiveDate = target.dataset.date;
      await loadFeed({ date: state.archiveDate });
      render();
    }
    if (action === "repo-switch") {
      state.repo.name = target.dataset.repo;
      state.repo.path = "";
      await loadRepo("");
      render();
    }
    if (action === "repo-open") {
      await loadRepo(target.dataset.path);
      render();
    }
    if (action === "inbox-save") {
      await api("/api/inbox/save", { method: "POST", body: JSON.stringify({ inbox_id: target.dataset.id }) });
      state.inbox = await api("/api/inbox");
      render();
    }
    if (action === "admin-user") {
      const data = await api("/api/admin/users", {
        method: "POST",
        body: JSON.stringify({ user_id: target.dataset.user, action: target.dataset.adminAction }),
      });
      state.adminUsers = data.users;
      render();
    }
  } catch (error) {
    setMessage(error.payload?.detail || readableError(error.message), true);
    render();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.lightbox) {
    state.lightbox = null;
    render();
    return;
  }
  if (event.key === "Escape" && state.selected) {
    state.selected = null;
    render();
    return;
  }
  const target = event.target.closest('[data-action="select"][role="button"]');
  if (!target || !["Enter", " "].includes(event.key)) return;
  event.preventDefault();
  target.click();
});

document.addEventListener("pointerdown", (event) => {
  const handle = event.target.closest(".drawer-resize-handle");
  if (!handle) return;
  event.preventDefault();
  const minWidth = Math.min(520, window.innerWidth);
  const maxWidth = Math.max(minWidth, window.innerWidth - 92);
  const onMove = (moveEvent) => {
    const width = Math.max(minWidth, Math.min(maxWidth, window.innerWidth - moveEvent.clientX));
    state.drawerWidth = width;
    const drawer = document.querySelector(".drawer.open");
    if (drawer) drawer.style.setProperty("--drawer-width", `${width}px`);
  };
  const onUp = () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
  };
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp);
});

document.addEventListener("input", (event) => {
  const form = event.target.closest('form[data-form="settings"]');
  if (!form) return;
  scheduleSettingsSave(form, event.target.tagName === "TEXTAREA" ? 800 : 300);
});

document.addEventListener("change", (event) => {
  const form = event.target.closest('form[data-form="settings"]');
  if (!form) return;
  scheduleSettingsSave(form, 80);
});

document.addEventListener("submit", async (event) => {
  const form = event.target.closest("form[data-form]");
  if (!form) return;
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form).entries());
  try {
    if (form.dataset.form === "login") {
      const result = await api("/api/login", { method: "POST", body: JSON.stringify(data) });
      state.user = result.user;
      state.settings = result.settings;
      await Promise.all([loadFeed(), loadShareUsers()]);
      if (state.user.role === "admin") {
        const usersData = await api("/api/admin/users");
        state.adminUsers = usersData.users;
      }
      setMessage("");
      render();
    }
    if (form.dataset.form === "register") {
      const result = await api("/api/register", { method: "POST", body: JSON.stringify(data) });
      state.authMode = "login";
      setMessage(result.message);
      renderAuth();
    }
    if (form.dataset.form === "settings") {
      await saveSettings(form);
    }
    if (form.dataset.form === "note") {
      await api("/api/notes", {
        method: "POST",
        body: JSON.stringify({ item_id: form.dataset.id, title: data.title, content: data.content }),
      });
      await loadFeed({ scope: state.view === "today" ? "today" : "all", date: state.archiveDate });
      setMessage("笔记已保存。");
      await selectItem(form.dataset.id);
    }
    if (form.dataset.form === "chat") {
      const result = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ item_id: form.dataset.id, content: data.content }),
      });
      state.chatMessages = result.messages || [];
      form.reset();
      render();
    }
    if (form.dataset.form === "share") {
      await api("/api/share", {
        method: "POST",
        body: JSON.stringify({ item_id: form.dataset.id, receiver_id: data.receiver_id, message: data.message }),
      });
      setMessage("已发送到对方收件箱。");
      render();
    }
  } catch (error) {
    setMessage(error.payload?.detail || readableError(error.message), true);
    render();
  }
});

function readableError(error) {
  const map = {
    bad_credentials: "用户名或密码不正确。",
    not_approved: "账号还没有通过管理员审批。",
    invalid_input: "输入不完整：用户名至少 2 位，密码至少 8 位；邮箱如果填写，需要是有效格式。",
    user_exists: "用户名或邮箱已经存在。",
    unauthorized: "请先登录。",
    forbidden: "当前账号没有权限。",
    invalid_note: "笔记内容不能为空。",
    invalid_share: "分享对象或内容不存在。",
    invalid_chat: "问题不能为空。",
  };
  return map[error] || error || "请求失败。";
}

function draftNote(item, messages = [], qmemRecords = []) {
  const questions = messages
    .filter((msg) => msg.role === "user")
    .map((msg) => `- ${msg.content}`)
    .join("\n");
  const qmem = qmemRecords
    .map((record) => `- ${record.title}: ${record.excerpt || record.path}`)
    .join("\n");
  return [
    `# ${item.title}`,
    "",
    `类型：${kindMeta[item.kind]?.title || item.kind}`,
    item.kind === "arxiv" ? `arXiv ${arxivScoreText(item)}` : "",
    sourceLine(item) ? `来源：${sourceLine(item)}` : "",
    tagText(item) ? `标签：${tagText(item)}` : "",
    "",
    "## 笔记要点",
    "- **问题定义**：待补充。",
    "- **核心方法**：待补充。",
    "- **关键假设**：待补充。",
    "- **可迁移启发**：待补充。",
    "",
    "## 这篇在解决什么问题",
    item.summary,
    "",
    "## 为什么值得读",
    item.why || "待补充。",
    "",
    "## 方法/思想线索",
    item.thinking || "待补充。",
    "",
    "## 图文理解",
    ...(Array.isArray(item.payload?.figures) && item.payload.figures.length
      ? item.payload.figures.slice(0, 2).flatMap((figure, index) => [
          `![${figure.caption || `Figure ${index + 1}`}](${figure.url})`,
          figureExplanation(figure, index),
          "",
        ])
      : ["- 暂未提取到主图；后续可从 PDF Figure 1 / Figure 2 补充。"]),
    "",
    "## 我接下来要追问",
    questions || "- 这篇工作的核心假设是什么？\n- 哪个假设可以被放松，形成新的选题？\n- 和我的 wiki/papers 里已有兴趣有什么连接？",
    "",
    "## 已有相关材料",
    qmem || "- 暂未匹配到相关材料。",
    "",
    "## 可迁移 idea",
    "- **数据假设**：是否依赖 paired / curated / expensive annotation？",
    "- **评估假设**：它的 benchmark 是否真的测到了目标能力？",
    "- **方法迁移**：是否能迁移到 video generation、world model、VLA 或 long video reasoning？",
  ].filter(Boolean).join("\n");
}

function buildGptPrompt(item, question = "", qmemRecords = []) {
  const qmem = qmemRecords
    .map((record) => `- ${record.title}\n  命中：${record.matched_terms.join(", ")}\n  摘要：${record.excerpt || record.path}`)
    .join("\n");
  const contributions = Array.isArray(item.payload?.contributions)
    ? item.payload.contributions.map((entry) => `- ${entry}`).join("\n")
    : "";
  const framework = Array.isArray(item.payload?.framework)
    ? item.payload.framework.map((entry) => `- ${entry}`).join("\n")
    : "";
  const figures = Array.isArray(item.payload?.figures)
    ? item.payload.figures.slice(0, 2).map((figure, index) => (
        `- ${figure.caption || `Figure ${index + 1}`}${figure.pdf_caption ? `：${figure.pdf_caption}` : ""}`
      )).join("\n")
    : "";
  return [
    "你是我的科研论文阅读助手。请结合下面 Research Pulse 的上下文，像 GPT 读论文一样具体分析这篇内容，并给出可以沉淀成 Markdown 笔记的要点。",
    "",
    `标题：${item.title}`,
    `类型：${kindMeta[item.kind]?.title || item.kind}`,
    item.kind === "arxiv" ? `arXiv ${arxivScoreText(item)}` : "",
    sourceLine(item) ? `来源：${sourceLine(item)}` : "",
    tagText(item) ? `标签：${tagText(item)}` : "",
    "",
    "文章导读：",
    item.summary,
    "",
    "英文摘要：",
    item.payload?.original_abstract || "",
    "",
    "中文摘要：",
    item.payload?.zh_abstract || item.payload?.abstract || "",
    "",
    "核心贡献：",
    contributions || "待补充。",
    "",
    "主要框架：",
    framework || "待补充。",
    "",
    "PDF Figure 1/2 caption：",
    figures || "暂未提取。",
    "",
    "已有分析线索：",
    item.why || "",
    item.thinking || "",
    "",
    "已有相关材料：",
    qmem || "暂无匹配记录。",
    "",
    "我的问题：",
    question || "请介绍这篇文章做了什么、核心假设是什么、方法有什么启发、可以怎么整理成我的科研笔记。",
    "",
    "请输出：",
    "1. 文章介绍：问题定义、输入输出、核心假设",
    "2. 英文摘要的忠实中文解读",
    "3. 关键贡献：每点先加粗概括，再解释具体做了什么",
    "4. 方法/理论线索：结合 Figure 1/2 解释框架",
    "5. 关键假设与可能的弱点",
    "6. 对我当前方向的启发",
    "7. 可直接保存到笔记的 Markdown 草稿",
  ].filter(Boolean).join("\n");
}

init();
