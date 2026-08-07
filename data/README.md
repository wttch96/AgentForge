# data/ — Agent 数据目录

每个 agent 一个数据目录（目录名即 agent 名），存放该 agent 运行产生的数据，按月份分目录。**所有数据文件一律使用 Markdown（`.md`）格式**。

```
data/
├── README.md                     # 本文件
└── daily-digest/                 # daily-digest agent 的数据
    └── 2026-08/                  # 按月分目录（YYYY-MM）
        ├── 07-mail.md            # 当日原始邮件内容（Markdown：HTML + 纯文本）
        └── 07-resp-list.md       # 当日关注的 GitHub 仓库列表（地址/star/简介）
```

## 文件命名

- 目录：`data/<agent>/YYYY-MM/`（agent 名 / 年-月）
- 文件：`<dd>-<kind>.md`（当日日期 + 类型后缀 + `.md` 扩展名）
  - `<dd>-mail.md`：当日**原始邮件**（HTML + 纯文本正文）
  - `<dd>-resp-list.md`：当日**关注的 GitHub 仓库**，每行一个，格式：`owner/repo | URL | star=N | 简介`
  - 同一天同类型多份时追加序号：`07-mail.md`、`07-mail-2.md` ...

## 作用

1. **存档**：每一封发送过的邮件、每个关注过的仓库都有记录，可追溯。
2. **去重依据**：下次运行时，agent 读取历史 `*-resp-list.md` 剔除已关注过的仓库（确定性去重），再读取历史 `*-mail.md` 用 DeepSeek 做语义比对（见 `agents/daily-digest/prompts/dedupe.md`）。

## 接入方式（新增 agent 时）

复用 `agents/_shared/history.py` 的 API，无需额外配置：

```python
from agents._shared import history

# 写入：data/<agent>/YYYY-MM/DD-<kind>.md（自动补 .md 扩展名）
history.save_data(agent, "mail", today, content)       # kind: 'mail' | 'resp-list'

# 读取（默认最新在前，可限条数）
records = history.load_data(agent, "resp-list", limit=10)
for name, content in records:
    ...

# 从文本中提取仓库引用（去重用）
refs = history.find_repo_refs(content)
```

workflow 需包含"提交 data/ 回仓库"步骤（`git add -A` + commit + push，需 `permissions: contents: write`），否则历史数据不会跨运行持久化。更多开发规范见 `.claude/skills/agentforge-dev/SKILL.md`。

## 注意

- 不要手动编辑这些文件（排查问题除外），它们由 agent 自动生成。
- 误发想重推某内容时，删除对应记录文件并提交即可。
