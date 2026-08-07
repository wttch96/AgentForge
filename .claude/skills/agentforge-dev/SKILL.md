---
name: agentforge-dev
description: AgentForge 仓库开发规范。定义本项目所有 agent 的统一约定：数据文件一律用 Markdown、提示词/skill 一律文件化不硬编码、新增 agent 的标准流程、workflow 自动提交。当在本仓库编写/修改 agent、操作 data/ 数据、设计提示词或 workflow 时必须遵守。触发关键词："新增agent"、"agent开发"、"数据规范"、"提示词文件"、"不硬编码"
---

# AgentForge 仓库开发规范 Skill

本 skill 定义 AgentForge 仓库内所有 agent 的统一开发规范。**本仓库任何 agent 开发都必须遵守**。

## 1. 数据文件一律用 Markdown

- agent 的运行数据存放在 `data/<agent>/YYYY-MM/` 下，文件名带 **`.md` 扩展名**：
  - `DD-mail.md`：当日原始邮件内容（Markdown 格式，HTML 正文 + 纯文本正文）
  - `DD-resp-list.md`：当日关注的 GitHub 仓库列表（每行 `owner/repo | URL | star=N | 简介`）
- 操作数据必须通过 `agents/_shared/history.py` 的 API，**不要**直接用 `open()` 手写路径：
  - `history.save_data(agent, kind, date_str, content)` → 写入
  - `history.load_data(agent, kind, limit=...)` → 读取历史
  - `history.find_repo_refs(text)` → 从文本提取仓库引用（去重用）
- `kind` 目前固定为 `'mail'` 与 `'resp-list'`；新增数据种类时需在 `data_path()` 校验列表同步扩展。

## 2. 提示词 / skill 一律文件化，禁止硬编码

- 所有提示词放到 `agents/<agent>/prompts/*.md`，主脚本用 `load_prompt(name)` 从文件加载后拼接占位符。
- **禁止**在 Python 代码里硬编码长提示词字符串（包括 system 提示词）。API 需要的 `"system"`/`"user"` 角色标签属于参数，不算提示词内容。
- 提示词模板中的动态内容用 `{占位符}` 标注，代码里 `.replace("{占位符}", 实际值)`。
- 修改提示词只需改 `.md` 文件，不需要改代码。

## 3. 新增 Agent 的标准流程

1. 建目录 `agents/<name>/`，包含 `main.py`、`prompts/`、`README.md`（部署说明）。
2. 复用 `agents/_shared/` 的公共能力：`deepseek.py`（LLM）、`github_search.py`（搜索）、`emailer.py`（发信）、`history.py`（数据存储）。
3. 在 `.github/workflows/` 建 `<name>.yml`：
   - 必须带 `workflow_dispatch`（便于手动验证）
   - `schedule` 用 **UTC** 时间（北京 = UTC+8，8:30 北京 = `30 0 * * *`）
   - 声明 `permissions: contents: write` 用于自动提交
4. 发信类 agent 默认做历史去重（读历史 resp-list 剔除 + LLM 语义比对）。
5. 更新根 `README.md` 的 Agent 列表。

## 4. workflow 自动提交

- 每个 workflow 运行后应把变更自动提交回仓库：
  - `git add -A && git commit -m "<类型>(<范围>): 描述" && git push`
  - 无变更时跳过（用 `git diff --cached --quiet` 判断）
- 使用 `secrets.GITHUB_TOKEN` 自动注入的凭据提交，**无需**手动配置 token。
- commit 类型参考 conventional commits：`chore(data)` 数据、`feat` 功能、`fix` 修复、`docs` 文档。

## 5. 本地开发与测试

- 本地配置放根目录 `.env`（复制自 `.env.example`），main.py 自动加载；**不要把真实密钥写进代码**。
- 本地测试：`python agents/<name>/main.py --dry-run`（不发送、不写数据）。
- 测试发信：`python agents/<name>/main.py --send-test-email`。
- 命令统一加 `rtk` 前缀（如 `rtk python agents/daily-digest/main.py --dry-run`）。
