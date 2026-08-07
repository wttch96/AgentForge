# AgentForge

寄托于 GitHub 的 **Agent 工厂**：每个 agent 是「一个 Python 脚本 + 一个 GitHub Actions workflow」，挂载在 GitHub Actions 上定时执行，无需自建服务器。

## 目录结构

```
AgentForge/
├── README.md                     # 本文件
├── requirements.txt              # Python 依赖
├── .github/workflows/            # 所有 agent 的 GitHub Actions workflow
│   └── daily-agent-digest.yml    # Agent 1：每日热门 Agent 仓库日报
├── data/                         # 每个 agent 一个数据目录（自动生成）
│   ├── README.md                 #   数据结构说明
│   └── daily-digest/2026-08/     #   YYYY-MM 分月：<dd>-mail.md / <dd>-resp-list.md
├── agents/
│   ├── _shared/                  # 公共工具库（所有 agent 复用）
│   │   ├── deepseek.py           #   DeepSeek 客户端封装
│   │   ├── github_search.py      #   GitHub Search API 封装
│   │   ├── emailer.py            #   SMTP 邮件发送封装
│   │   └── history.py            #   Agent 数据读写（data/<agent>/YYYY-MM/，Markdown）
│   └── daily-digest/             # Agent 1
│       ├── main.py               #   主脚本（搜索→生成→去重→存档→发送）
│       ├── prompts/              #   提示词文件（system/user/dedupe/dedupe-system）
│       ├── README.md             #   部署说明（GitHub Secrets 配置）
└── .claude/                      # Claude Code 配置
    ├── CLAUDE.md
    ├── settings.json
    └── skills/                   # 项目级 Skill
        ├── agentforge-dev/       #   仓库开发规范（Markdown 数据/不硬编码/自动提交）
        └── code-doc-enhance/     #   中文注释与文档增强
```

## Agent 列表

| Agent | 触发时间（北京时间） | 功能 | 部署文档 |
|---|---|---|---|
| daily-digest | 每天 08:30 | 搜索 GitHub 热门 agent/skill 仓库，DeepSeek 汇总中文日报，与历史数据去重后发送 | [agents/daily-digest/README.md](agents/daily-digest/README.md) |

> 每个 agent 的运行数据都会存档到 `data/<agent>/YYYY-MM/`（邮件与关注仓库列表），下次运行会与历史比对去重，避免重复推送。

## 开发规范

本仓库内置两个**项目级 Claude Code Skill**（`.claude/skills/`），开发时按需触发：

| Skill | 用途 | 触发词 |
|---|---|---|
| `agentforge-dev` | 仓库开发规范：数据文件用 Markdown、提示词文件化不硬编码、新增 agent 流程、workflow 自动提交 | "新增agent"、"数据规范"、"提示词文件" |
| `code-doc-enhance` | 中文详尽注释增强 + 项目/agent 文档自动完善 | "完善注释"、"完善文档"、"增强文档" |

核心约定（详见 skill 正文）：
- **数据文件一律用 Markdown**：`data/<agent>/YYYY-MM/DD-<kind>.md`
- **提示词一律文件化**：放 `agents/<name>/prompts/*.md`，禁止在代码里硬编码提示词
- **workflow 自动提交**：运行后 `git add -A && commit && push` 回仓库

## 快速开始

1. **Fork / 克隆本仓库**到你的 GitHub 账号下
2. 按每个 agent 的部署文档在 **Settings → Secrets and variables → Actions** 中添加所需 Secrets
3. 首次部署可用 `workflow_dispatch` 手动触发验证，之后按 schedule 自动运行

## 如何新增一个 Agent

1. 在 `agents/` 下新建目录 `<agent-name>/`
   - `main.py`：主脚本（入口，读取环境变量）
   - `prompts/`：提示词全部写成文件，从文件加载
   - `README.md`：部署说明（需要的 Secrets 及获取方法）
2. 需要调用 DeepSeek / GitHub 搜索 / 发邮件时，复用 `agents/_shared/` 中的公共模块
3. 在 `.github/workflows/` 下新建 `<agent-name>.yml`
   - `on.schedule` 使用 **UTC** 时间（北京时间 = UTC+8）
   - 用 `workflow_dispatch` 允许手动触发，便于验证
4. 在本 `README.md` 的 Agent 列表中加入一行

## 时区换算速查

| 北京时间 | UTC | Cron（UTC） |
|---|---|---|
| 08:30 | 00:30 | `30 0 * * *` |
| 09:00 | 01:00 | `0 1 * * *` |
| 12:00 | 04:00 | `0 4 * * *` |

> 注意：GitHub Actions 的 `schedule` 仅支持 UTC，且实际触发时间可能有几分钟延迟。

## 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 复制本地配置模板并填写真实值
cp .env.example .env          # Linux / macOS / Git Bash
Copy-Item .env.example .env   # PowerShell
```

`.env` 会被自动加载（已 gitignore，不会提交）。常用命令：

```bash
# 测试 SMTP 发信配置（先跑这个验证发信）
python agents/daily-digest/main.py --send-test-email

# 本地 dry-run（真实搜索 + 生成，不发邮件）
python agents/daily-digest/main.py --dry-run
```

> 已存在的环境变量优先级高于 `.env`，不会被覆盖（本地 shell 已导出的变量优先）。
