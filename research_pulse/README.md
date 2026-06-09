# Research Pulse

Research Pulse 是一个本地优先的科研信息推送网站，用来把 arXiv daily、近两年高影响力论文、论文考古、AI for Science 和学术人物关系网整理成可收藏、可追问、可沉淀笔记的工作台。

当前版本是轻量本地服务：Python 标准库 + SQLite + 原生前端，不需要单独开数据库。DeepSeek、飞书、PDF figure 截图都是可选增强。

## 核心功能

- 管理员/用户两种角色：用户注册后需要管理员审批。
- 每个用户有自己的兴趣关键词、排除关键词、模块开关、每日数量、本地仓库路径。
- 每日推送模块：
  - 最新 arXiv：按兴趣筛选，每篇保留 0-10 相关度。
  - 近两年高影响力 paper：顶会、技术报告、大厂/高影响项目。
  - 论文考古：经典理论、早年好论文和科学思维。
  - AI for Science：Nature 系列、大字刊和 AI for 民生/科学方向。
  - 学术人物关系网：title、机构、师承学生、合作关系和国内学术生态。
- 论文详情页：
  - arXiv Page / PDF / Google Scholar / Project / GitHub 入口。
  - 英文摘要和忠实中文摘要。
  - 核心贡献、主要框架、为什么值得读。
  - PDF Figure 1 / Figure 2 截图和 caption。
  - DeepSeek 即时问答，或复制上下文到 GPT。
  - Markdown 笔记草稿、保存、相关笔记检索、飞书消息提醒。
- 收藏流：只滚动收藏条目，快速回顾近期看过的 paper。
- 大牛 follow：按机构展板关注学者，每月排一次 Agent 更新 Google Scholar / 主页 / publications；红点提示本月新 paper，年均引用量大于 100 的论文用星标标出。
- 本地知识源：读取 `wiki/`、`papers/`、`notes/` 路径，配合 QMem 聊天记录做相关笔记。

## 目录结构

```text
research_pulse/
  main.py                  # 本地网站后端
  update_arxiv_daily.py    # arXiv 拉取、DeepSeek 分析、PDF Figure 1/2 提取
  agent_daily.py           # 导入定时 Agent JSON，并发送飞书提醒
  static/                  # 前端页面、样式、交互
  scripts/                 # 手动启动 / 安装 launchd
  launchd/                 # macOS 登录自动启动配置
  docs/                    # 更新策略和资料来源说明
```

以下目录是本地运行态，默认不提交 GitHub：

```text
data/                  # SQLite 数据库
logs/                  # 服务日志
config/*.txt           # DeepSeek key / 飞书 webhook
notes/                 # 用户 Markdown 笔记
agent_outputs/         # 定时 Agent 输出
tmp_pdfs/              # PDF 缓存
tmp_affiliations/      # 单位解析缓存
static/generated_figures/
.deps/                 # 本地安装的 PyMuPDF 等依赖
.arxivreader/          # 可选虚拟环境
```

## 快速启动

在项目根目录运行：

```bash
python3 main.py
```

打开：

```text
http://127.0.0.1:8766
```

首次运行会创建管理员账号：

```text
用户名：admin
```

首次运行前建议设置管理员初始密码：

```bash
RESEARCH_PULSE_ADMIN_PASSWORD='your-strong-password' python3 main.py
```

## 使用 `.arxivreader` 虚拟环境

如果你在项目根目录放了虚拟环境 `.arxivreader`，启动脚本会自动执行：

```bash
source .arxivreader/bin/activate
```

然后用虚拟环境里的 `python` 启动网站。

推荐配置：

```bash
python3 -m venv .arxivreader
source .arxivreader/bin/activate
python -m pip install --upgrade pip
python -m pip install pymupdf
```

如果不想建虚拟环境，也可以把 PyMuPDF 安装到项目本地 `.deps/`：

```bash
python3 -m pip install --target .deps pymupdf
```

`update_arxiv_daily.py` 会优先加载 `.deps/`，用于从 PDF 截取 Figure 1 / Figure 2。没有 PyMuPDF 时，系统仍可运行，只是 figure 提取会退化。

## macOS 开机自动运行

安装 launchd 启动项：

```bash
./scripts/install_launch_agent.sh
```

它会把启动脚本复制到：

```text
~/.research_pulse/run_server.sh
```

每次登录 macOS 后自动运行：

```text
http://127.0.0.1:8766
```

卸载：

```bash
./scripts/uninstall_launch_agent.sh
```

## DeepSeek 配置

DeepSeek key 只在 Python 后端读取，不会写入 `static/`，普通网页用户无法从页面源码或 Network 里看到真实 key。

方式一：环境变量。

```bash
export DEEPSEEK_API_KEY='your-key'
./scripts/run_server.sh
```

方式二：本地私密文件。

```text
config/deepseek_api_key.txt
```

文件里只放 key，建议：

```bash
chmod 600 config/deepseek_api_key.txt
```

## 飞书配置

普通飞书机器人 webhook 可以发消息提醒，但不能直接创建飞书文档。配置方式：

```bash
export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/xxx'
```

或写入：

```text
config/feishu_webhook.txt
```

支持：

- 每日更新提醒。
- 从论文详情页把当前 Markdown 笔记发送到飞书消息。

如果要自动创建飞书文档，需要后续接飞书开放平台文档 API，并配置 `app_id`、`app_secret`、文档空间权限和用户授权。

## 手动更新今日内容

拉取最新 arXiv，最多 10 篇，并替换当天 demo/fallback 条目：

```bash
source .arxivreader/bin/activate  # 如果使用虚拟环境
python update_arxiv_daily.py --limit 10 --replace-demo
```

导入定时 Agent 输出并发送飞书提醒：

```bash
python agent_daily.py --input agent_outputs/YYYY-MM-DD.json --notify
```

没有真实 Agent 输出时，不建议用 fallback 生成假卡片；fallback 只用于验证流程：

```bash
python agent_daily.py --fallback --notify
```

## 大牛 follow

页面入口在左侧导航的“大牛 follow”。默认关注了：

- Fei-Fei Li：Stanford，Google Scholar 已配置。
- Jiajun Wu：Stanford，Google Scholar 已配置。
- Bernt Schiele：MPI / Saarland，Google Scholar 已配置。
- Dima Damen：Bristol / Google DeepMind，主页与 publications 已配置；Google Scholar ID 暂未硬写，避免误连到错误 profile。

使用方式：

- 展板按机构分组显示作者。
- 红点表示本月有新 paper 或需要重点关注。
- 点击作者进入抽屉，按时间从新到旧看近期论文、科研生平和近期兴趣。
- 高引论文使用 `★ 年均引用 > 100` 标记。
- “提交月度更新”会写入一个 `bigshot_monthly_update` Agent 任务；同一个月份重复点击会复用已有任务，不会堆重复队列。

月度 Agent 更新时建议补充这些字段：

- Google Scholar 总引用量。
- 本月是否有新 paper。
- 最近论文列表，按年份从新到旧。
- 高引论文是否满足平均年引用量大于 100。
- 作者早期方向、代表性 title、近期 focus。

## Agent 输出 JSON 约定

`agent_daily.py` 接收如下结构：

```json
{
  "date": "2026-06-08",
  "summary": "今日更新摘要",
  "items": [
    {
      "id": "2026-06-08-recent-example",
      "kind": "recent",
      "title": "Paper title",
      "subtitle": "ICML / Google DeepMind",
      "summary": "中文导读",
      "score": 8,
      "tags": ["世界模型", "机器人", "长程任务"],
      "authors": "Author A, Author B",
      "venue": "ICML",
      "org": "Google DeepMind",
      "why": "为什么值得读",
      "thinking": "科学思维或方法线索",
      "links": {
        "paper": "https://arxiv.org/abs/xxxx.xxxxx",
        "pdf": "https://arxiv.org/pdf/xxxx.xxxxx",
        "project": "https://project-page.example"
      },
      "payload": {
        "original_abstract": "English abstract",
        "zh_abstract": "忠实中文摘要",
        "contributions": ["**贡献一**：具体解释。"],
        "framework": ["**模块一**：具体解释。"]
      }
    }
  ]
}
```

分数统一使用 0-10。导入器会自动去重：优先按链接，其次按标题和作者。

## GitHub 同步

本目录默认可作为独立 Git 仓库提交。不要提交以下内容：

- `config/deepseek_api_key.txt`
- `config/feishu_webhook.txt`
- `data/`
- `logs/`
- `.arxivreader/`
- `.deps/`
- PDF 缓存和生成图片

初始化并推送到你自己的 GitHub repo：

```bash
git init
git add .
git commit -m "Initial Research Pulse app"
git branch -M main
git remote add origin https://github.com/<owner>/<repo>.git
git push -u origin main
```

如果 repo 已经存在，把上面的 remote URL 换成你的目标仓库即可。

## 当前限制

- 飞书 webhook 只能发消息，不能新建飞书文档。
- 学术人物关系网需要继续接可靠来源，并为师承/学生/合作关系补引用。
- PaperCopilot、GitHub stars、Nature/Science 系列抓取还需要稳定数据源和去重策略。
- 多用户目前共享同一 SQLite 服务；每个用户的兴趣、收藏、笔记是隔离的。
