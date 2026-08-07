# AgentForge — Claude Code 维护指南

本仓库是寄托于 GitHub Actions 的 **Agent 工厂**：每个 agent = 一个 Python 脚本 + 一个 GitHub Actions workflow，定时在云端执行，无需自建服务器。

## 仓库结构

```
.
├── .github/workflows/       # 每个 agent 一个 workflow（cron 定时 + workflow_dispatch 手动）
├── data/<agent>/YYYY-MM/    # 每个 agent 一个数据目录（自动生成：<dd>-mail.md / <dd>-resp-list.md）
├── agents/
│   ├── _shared/             # 公共底座，所有 agent 复用
│   │   ├── deepseek.py      #   DeepSeek 客户端（OpenAI 兼容，base_url=https://api.deepseek.com）
│   │   ├── github_search.py #   GitHub Search API（多关键词、按 star 排序、去重取 Top N）
│   │   ├── emailer.py       #   SMTP 发送（SSL 465 / STARTTLS 587，HTML+纯文本）
│   │   └── history.py       #   Agent 数据读写（data/<agent>/YYYY-MM/，Markdown，含 find_repo_refs）
│   └── <agent-name>/        # 每个 agent 自包含
│       ├── main.py          #   入口（读取环境变量/secrets，支持 --dry-run）
│       ├── prompts/         #   ⚠️ 提示词全部文件化，从文件加载，不改代码
│       └── README.md        #   ⚠️ 部署说明：需要的 Secrets 及获取方法
└── .claude/                 # 本目录
    ├── skills/
    │   ├── agentforge-dev/  #   仓库开发规范
    │   └── code-doc-enhance/ #  注释与文档增强
```

## 项目级 Skill

仓库内置两个 skill（`.claude/skills/`），开发相关任务时优先参考：

- **`agentforge-dev`**：仓库开发规范 —— 数据文件用 Markdown（`data/<agent>/YYYY-MM/DD-<kind>.md`）、提示词文件化不硬编码、新增 agent 流程、workflow 自动提交。**涉及本仓库开发/数据/提示词/新 agent 时必须遵守。**
- **`code-doc-enhance`**：为 Python 代码补中文详尽注释（模块/函数 docstring + 关键行注释），并同步完善 README、CLAUDE.md、data 说明等文档。

## 关键约定（维护时务必遵守）

1. **提示词一律放 `prompts/*.md` 文件**，main.py 用 `load_prompt()` 读取并替换 `{...}` 占位符。不要硬编码提示词在代码里（含 system 提示词）。
2. **数据文件一律用 Markdown（`.md`）**，写入 `data/<agent>/YYYY-MM/DD-<kind>.md`，通过 `history.save_data` 操作（自动补扩展名），不要手写路径。
3. **密钥一律来自环境变量**（GitHub Actions 中由 secrets 注入）。本地测试：复制根目录 `.env.example` 为 `.env` 填写（`.env` 已 gitignore），main.py 启动时自动加载；**不要把真实密钥写进代码或提交到仓库**。
4. **每个 agent 必须配套部署 README**，说明需要添加的 GitHub Secrets 及其获取方法。
5. **workflow 必须带 `workflow_dispatch`**，便于手动触发验证；`schedule` cron 使用 **UTC 时间**（北京 = UTC+8，8:30 北京 = `30 0 * * *`）。
6. **新增 agent 复用 `_shared`**：搜索/LLM/邮件/历史记录能力已有封装，不要重复造轮子。
7. **发信类 agent 默认应做历史去重**：发送前把日报存档到 `data/<agent>/YYYY-MM/`（`history.save_data(agent, 'mail', ...)` 与 `'resp-list'`），下次运行时剔除已关注内容（`history.load_data` + `find_repo_refs`），并用 `prompts/dedupe.md` 让 LLM 二次比对。workflow 需含"提交 data/ 回仓库"步骤（`permissions: contents: write`）。

## 如何新增一个 Agent

1. 建目录 `agents/<name>/`，写 `main.py`、`prompts/`、`README.md`
2. 需要时复用 `agents/_shared/`（`sys.path.insert` 已在各 main.py 中处理，或参考 daily-digest/main.py 的模式）
3. 在 `.github/workflows/` 建 `<name>.yml`，模式参考 `daily-agent-digest.yml`
4. 更新根 `README.md` 的 Agent 列表

## 本地测试

```bash
# 语法检查
python -m py_compile agents/daily-digest/main.py

# 测试 SMTP 发信配置（先跑这个验证发信）
python agents/daily-digest/main.py --send-test-email

# dry-run（真实搜索 + 生成，不发送邮件）
python agents/daily-digest/main.py --dry-run

# 本地配置写在仓库根目录 .env（复制自 .env.example），main.py 自动加载
```

> 所有 shell 命令按 RTK 规范加 `rtk` 前缀：`rtk python agents/daily-digest/main.py --send-test-email`

## 现有 Agent

| Agent | 触发（北京时间） | 说明 |
|---|---|---|
| daily-digest | 08:30 | 搜索热门 agent/skill 仓库 → DeepSeek 汇总中文日报 → SMTP 发送 |
