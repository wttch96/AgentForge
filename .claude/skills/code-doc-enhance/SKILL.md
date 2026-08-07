---
name: code-doc-enhance
description: AgentForge 代码注释与文档增强。为 Python 代码补充详尽中文注释（模块/函数 docstring + 关键逻辑行注释），并同步完善项目与各 agent 的文档（README、CLAUDE.md、data 说明）。触发关键词："完善注释"、"补充注释"、"注释增强"、"完善文档"、"增强文档"、"更新文档"
---

# AgentForge 代码注释与文档增强 Skill

本 skill 规定 AgentForge 仓库内代码注释与文档的标准，以及执行"注释/文档增强"时的具体操作步骤。

## 1. 中文详尽注释标准

所有 Python 文件（`agents/_shared/*.py`、`agents/<name>/main.py`）遵循：

- **模块头部 docstring**：说明模块用途、核心流程、依赖的环境变量、使用方式示例。
- **函数 docstring**（三引号）：说明功能、参数（参数名+含义）、返回值、抛出的异常、注意事项。
- **关键逻辑行注释**：对非显而易见的逻辑（正则、边界处理、分支原因、顺序依赖）加行注释，全中文。
- 注释密度"匹配周边代码"——不是每行都加，而是讲清楚"为什么这样做"。
- 类与常量：类上方加说明；魔术常量（如端口、超时、阈值）注释其含义与单位。

## 2. 文档完善标准

本仓库文档与代码保持同步，改动代码后必须检查并更新：

| 文档 | 内容 |
|---|---|
| `README.md`（根） | 仓库总览、目录结构、Agent 列表、快速开始、如何新增 agent、本地开发 |
| `.claude/CLAUDE.md` | 结构说明、关键约定、本地测试命令、现有 agent |
| `data/README.md` | data/ 数据结构、文件命名规则、接入方式 |
| `agents/<name>/README.md` | 每个 agent 的功能、目录结构、部署步骤（Secrets）、去重机制、本地测试、配置调整 |

## 3. 执行"注释/文档增强"的操作步骤

当用户要求完善注释或文档时，按以下顺序执行：

1. **盘点**：列出 `agents/_shared/` 与 `agents/<name>/` 下所有 Python 文件，以及所有 README 文档。
2. **注释增强**：逐文件检查注释是否达到第 1 节标准；对缺失/不足的补全。优先补 docstring，再补关键行注释。
3. **文档同步**：检查代码改动是否已反映到第 2 节表格中的文档；补齐遗漏、修正过时描述（如路径、文件名、常量默认值）。
4. **一致性检查**：文档中提到的路径/文件名/命令与实际代码一致（grep 验证）；提示词文件列表与实际 `prompts/` 目录一致。
5. **验证**：`python -m py_compile` 全部改动文件；有 `--dry-run` 的 agent 跑一次确认无回归。

## 4. 常用检查命令（RTK 前缀）

```bash
# 列出所有 Python / 文档文件
rtk find . -name "*.py" -o -name "*.md"

# 检查是否有残留的旧路径引用（示例）
rtk grep "mail/" .   # 应无命中（旧结构已迁移到 data/）

# 编译验证
python -m py_compile agents/_shared/*.py agents/daily-digest/main.py
```
