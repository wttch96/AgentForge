# daily-digest — 每日热门 AI Agent / Skill 仓库日报

每天 **北京时间 08:30** 自动执行：
1. 通过 GitHub Search API 搜索最近 7 天活跃、热度高的 **agent / skill** 相关仓库（Top 10）
2. 用 **DeepSeek API** 汇总生成**中文 HTML 日报**（提示词在 [prompts/](prompts/) 中，从文件加载）
3. **与历史数据去重**：剔除已关注过的仓库，用 DeepSeek 与 `data/daily-digest/` 下的历史记录比对，避免重复推送
4. 发送前把日报与仓库列表写入 `data/daily-digest/`（作为下次去重依据），再通过 **SMTP** 发送

## 目录结构

```
daily-digest/
├── main.py               # 主脚本
├── prompts/
│   ├── system.md         # DeepSeek 系统提示词（角色设定 + 输出格式）
│   ├── user.md           # 用户提示词模板（{repos_json} 占位符）
│   ├── dedupe.md         # 去重提示词（今日日报 vs 历史邮件比对）
│   └── dedupe-system.md  # 去重系统提示词（角色 + 输出 JSON 约束）
└── README.md             # 本文件

仓库 data/daily-digest/   # 运行数据（自动生成，Markdown）
    └── 2026-08/          # 按月分目录
        ├── 07-mail.md        # 当日原始邮件（HTML + 纯文本）
        └── 07-resp-list.md   # 当日关注仓库列表（地址/star/简介）
```

## 部署步骤

### 1. 推送本仓库到 GitHub

将整个 AgentForge 仓库 push 到你的 GitHub 账号（Public 或 Private 均可）。

### 2. 添加 GitHub Secrets

在 GitHub 仓库 **Settings → Secrets and variables → Actions → New repository secret** 中依次添加：

| Secret | 必需 | 说明 | 获取方法 |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API 密钥 | 登录 [platform.deepseek.com](https://platform.deepseek.com) → API Keys → 创建 |
| `SMTP_HOST` | ✅ | SMTP 服务器地址 | QQ 邮箱：`smtp.qq.com`；163 邮箱：`smtp.163.com`；Gmail：`smtp.gmail.com`；Outlook：`smtp-mail.outlook.com` |
| `SMTP_PORT` | ✅ | SMTP 端口 | **465**（SSL）或 **587**（STARTTLS），两者均支持 |
| `SMTP_USER` | ✅ | 发件邮箱地址 | 如 `yourname@qq.com` |
| `SMTP_PASSWORD` | ✅ | **邮箱授权码**（不是登录密码） | QQ/163：邮箱设置 → 开启 SMTP 服务 → 生成授权码；Gmail：需开启两步验证后用"应用专用密码" |
| `SMTP_TO` | ✅ | 收件邮箱 | 可多个，用英文逗号分隔，如 `a@qq.com,b@163.com` |

> `GITHUB_TOKEN` **无需手动配置** —— GitHub Actions 会自动注入 `secrets.GITHUB_TOKEN`，仅用于 GitHub 搜索 API 认证以提高频率限制。

### 3. 运行数据（自动持久化）

本 agent 每次运行会把日报与关注仓库列表写入仓库的 `data/daily-digest/YYYY-MM/`（`DD-mail.md` 与 `DD-resp-list.md`，Markdown 格式），用于后续去重。workflow 已包含"自动提交变更回仓库"的步骤（`git add -A`），**无需额外配置**。

> 注意：该提交步骤要求 workflow 具备 `contents: write` 权限（workflow 文件里已声明）。

### 4. 手动触发验证

推送后，到 **Actions → Daily Agent Digest → Run workflow** 点击手动触发（`workflow_dispatch`），检查运行日志，确认邮件收到。

### 5. 自动定时运行

workflow 中 cron 设为 `30 0 * * *`（UTC）= 北京时间 08:30。之后每天自动执行。

> **注意**：GitHub Actions 的 `schedule` 触发可能有数分钟延迟，且极少数情况下会跳过某次运行（如仓库长期不活跃）。若发现漏发，可用 `workflow_dispatch` 手动补跑。

## 去重机制

每天运行时分两层去重，避免同一仓库反复推送：

1. **确定性去重**（发信前）：读取 `data/daily-digest/` 下历史 `*-resp-list.md`，从搜索候选中剔除已出现过的仓库（按 `owner/repo` 与 URL 匹配）。
2. **LLM 语义去重**（生成日报后）：把今日日报与最近历史 `*-mail.md` 一起交给 DeepSeek（提示词 `prompts/dedupe.md` + `prompts/dedupe-system.md`），识别"已报道过、仅有重复"的内容并提示。

若搜索结果全部与历史重复，会跳过本次生成与发送（不会发空邮件）。

## 本地测试（dry-run 与测试发信）

在本地先安装依赖并复制 `.env.example` 为 `.env`，填写配置：

```bash
pip install -r requirements.txt

# 复制配置模板（Linux / macOS / Git Bash）：
cp .env.example .env
# PowerShell：
Copy-Item .env.example .env
```

填写 `.env` 后，无需再手动导出环境变量（main.py 会自动加载仓库根目录的 `.env`）：

```bash
# ① 测试 SMTP 配置（只发一封测试邮件，验证发信可用）：
python agents/daily-digest/main.py --send-test-email

# ② 完整 dry-run（真实搜索 + DeepSeek 生成，但不发送）：
python agents/daily-digest/main.py --dry-run
```

> - `--send-test-email` 会向 `SMTP_TO` 发送一封测试邮件。**建议先跑这个**，确认 SMTP 配置无误后再跑完整流程。
> - `--dry-run` 执行真实的 GitHub 搜索 + DeepSeek 生成，但**不发送邮件**，把日报打印到终端，方便调试提示词与搜索结果。
> - `.env` 已在 `.gitignore` 中排除，不会提交到仓库；`SMTP_PASSWORD` 填写的是**邮箱授权码**，不是登录密码。

## 常用配置调整

修改 [main.py](main.py) 顶部的常量即可：

| 常量 | 默认 | 说明 |
|---|---|---|
| `SEARCH_QUERIES` | agent / ai agent / claude skills 等 8 个 | GitHub 搜索关键词 |
| `DAYS_BACK` | 7 | 只看最近 N 天活跃的仓库 |
| `PER_QUERY` | 20 | 每个关键词取前 N 条 |
| `TOP_N` | 10 | 日报最终展示的仓库数 |
| `MODEL` | `deepseek-chat` | DeepSeek 模型（可换 `deepseek-reasoner`） |

提示词的调整直接编辑 `prompts/system.md` 与 `prompts/user.md` 即可，无需改代码。
