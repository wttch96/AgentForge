#!/usr/bin/env python3
"""每日热门 Agent / Skill 仓库日报（AgentForge 第一个 agent）。

完整流程：
1. 通过 GitHub Search API 搜索最近 7 天活跃的 agent / skill 相关仓库（Top 10）
2. 与历史数据（data/daily-digest/）确定性去重，剔除已关注过的仓库
3. 用 DeepSeek 汇总生成中文 HTML 日报（提示词从 prompts/ 文件加载，不硬编码）
4. 与历史邮件做 LLM 语义去重，避免重复推送
5. 把日报与仓库列表写入 data/daily-digest/YYYY-MM/ 存档
6. 通过 SMTP 发送邮件

用法：
    # 实际运行（GitHub Actions 中使用）
    python agents/daily-digest/main.py

    # 本地测试（不发送邮件，把日报打印到终端）
    python agents/daily-digest/main.py --dry-run

    # 只发一封测试邮件，验证 SMTP 配置是否可用
    python agents/daily-digest/main.py --send-test-email

配置：
    环境变量（secrets）：
        DEEPSEEK_API_KEY, GITHUB_TOKEN, SMTP_HOST, SMTP_PORT,
        SMTP_USER, SMTP_PASSWORD, SMTP_TO
    本地测试可用 .env 文件（见仓库根目录 .env.example），
    main.py 会自动从仓库根目录或当前工作目录加载 .env。
    注意：已存在的环境变量优先级高于 .env，不会被覆盖。
详见本目录 README.md。
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 输出避免中文乱码
for stream in (sys.stdout, sys.stderr):
    if stream and hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001 - 失败不影响主流程
            pass

# 从仓库根目录或当前工作目录加载 .env（不存在则静默跳过）
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv()  # 兜底：也尝试当前工作目录下的 .env

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents._shared.deepseek import DeepSeekClient  # noqa: E402
from agents._shared.emailer import SMTPConfig, send_email  # noqa: E402
from agents._shared.github_search import search_repos  # noqa: E402
from agents._shared import history  # noqa: E402

AGENT_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = AGENT_DIR / "prompts"

# 数据目录：data/<TAG>/
TAG = "daily-digest"

# 生成日报后，最多与最近多少份历史数据比对去重
DEDUPE_HISTORY_LIMIT = 7

# GitHub 搜索关键词：agent / skill 相关的热门话题与仓库
SEARCH_QUERIES = [
    'agent',
    '"ai agent"',
    'topic:ai-agents',
    '"claude skills"',
    'topic:claude-skills',
    '"agent skill"',
    '"ai agents"',
    'langchain agent',
]

DAYS_BACK = 7      # 只看最近 7 天有更新的仓库
PER_QUERY = 20     # 每个关键词取前 20
TOP_N = 10         # 最终日报中的仓库数
MODEL = "deepseek-chat"


def load_prompt(name: str) -> str:
    """从 prompts/ 目录加载提示词文件（不硬编码，全部文件化）。

    参数:
        name: 提示词文件名，如 "system.md"、"user.md"、"dedupe.md"

    返回:
        文件内容字符串

    异常:
        FileNotFoundError: 提示词文件不存在
    """
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"缺少提示词文件: {path}")
    return path.read_text(encoding="utf-8")


def build_daily_report(repos: list[dict]) -> str:
    """调用 DeepSeek，用提示词文件生成中文日报（HTML）。

    参数:
        repos: 去重后的仓库列表（含 full_name/html_url/description/star 等字段）

    返回:
        DeepSeek 生成的中文 HTML 日报
    """
    system = load_prompt("system.md")
    user_template = load_prompt("user.md")
    # 把仓库 JSON 序列化后填入 user.md 的 {repos_json} 占位符
    repos_json = json.dumps(repos, ensure_ascii=False, indent=2)
    user = user_template.replace("{repos_json}", repos_json)

    client = DeepSeekClient(model=MODEL)
    return client.chat(system=system, user=user)


def filter_known_repos(repos: list[dict]) -> list[dict]:
    """确定性去重：剔除历史 resp-list 中已关注过的仓库（按 full_name / html_url）。

    读取 data/<TAG>/ 下最近 DEDUPE_HISTORY_LIMIT 份 resp-list，
    提取其中出现过的仓库引用，从候选列表中剔除匹配项。
    """
    seen = set()
    for name, content in history.load_data(TAG, "resp-list", limit=DEDUPE_HISTORY_LIMIT):
        seen.update(history.find_repo_refs(content))
    if not seen:
        return repos
    kept, dropped = [], []
    for r in repos:
        name = r.get("full_name", "")
        url = r.get("html_url", "")
        # 仓库名（owner/repo）或完整 URL 命中历史即视为已关注
        if name in seen or url in seen:
            dropped.append(name)
        else:
            kept.append(r)
    if dropped:
        print(f"      [去重] 历史已关注，跳过: {', '.join(dropped)}")
    return kept


def dedupe_with_llm(report: str) -> dict:
    """LLM 语义去重：把今日日报与最近历史邮件比对，找出重复内容。

    提示词均从 prompts/ 文件加载（不硬编码）：
        dedupe-system.md  系统提示词（角色 + 输出 JSON 格式约束）
        dedupe.md         用户提示词模板（比对规则）

    参数:
        report: 今日生成的日报 HTML

    返回:
        字典，含 has_duplicate / duplicated_repos / analysis
    """
    history_text = history.load_recent(TAG, kind="mail", limit=DEDUPE_HISTORY_LIMIT)
    if not history_text:
        return {"has_duplicate": False, "duplicated_repos": [], "analysis": "无历史记录"}

    system = load_prompt("dedupe-system.md")
    template = load_prompt("dedupe.md")
    # 把今日日报与历史邮件拼接进用户提示词
    user = (
        template
        + "\n\n【今日日报】\n"
        + report
        + "\n\n【历史邮件】\n"
        + history_text
    )
    client = DeepSeekClient(model=MODEL)
    raw = client.chat(system=system, user=user, temperature=0.1)
    return parse_dedupe_result(raw)


def parse_dedupe_result(raw: str) -> dict:
    """从 DeepSeek 输出中提取 JSON 结果（容错解析）。

    DeepSeek 可能返回带 ```json 代码块或前后有多余文字的内容，
    这里去代码块围栏后截取第一个 `{...}` 块再解析。

    返回:
        dict；解析失败时返回带 has_duplicate=False 的默认结构（不阻断流程）
    """
    import re

    text = raw.strip()
    # 去掉 ```json ... ``` 代码块围栏（行首或行尾）
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return {"has_duplicate": False, "duplicated_repos": [], "analysis": "去重结果解析失败"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"has_duplicate": False, "duplicated_repos": [], "analysis": "去重结果解析失败"}


def save_history_record(html: str, text: str, repos: list[dict]) -> str:
    """把本次日报与仓库列表写入 data/daily-digest/YYYY-MM/，返回日期串。

    写入两个 Markdown 文件（由 history.save_data 补 .md 扩展名）：
        DD-mail.md        原始邮件内容（HTML + 纯文本）
        DD-resp-list.md   当日关注的 GitHub 仓库（地址/star/简介）

    参数:
        html:  日报 HTML 正文
        text:  日报纯文本正文
        repos: 本次报道的仓库列表
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # mail：完整保留 HTML 与纯文本两份正文
    mail_content = (
        f"# 每日日报 {today}\n\n"
        f"## HTML 正文\n\n{html}\n\n"
        f"## 纯文本正文\n\n{text}\n"
    )
    mail_path = history.save_data(TAG, "mail", today, mail_content)

    # resp-list：每行一个仓库，格式 owner/repo | URL | star=N | 简介
    lines = [f"# 关注仓库列表 {today}\n"]
    for r in repos:
        desc = (r.get("description") or "").replace("\n", " ").strip()
        lines.append(
            f"- {r.get('full_name', '')} | {r.get('html_url', '')} | "
            f"star={r.get('stargazers_count', 0)} | {desc}"
        )
    resp_path = history.save_data(TAG, "resp-list", today, "\n".join(lines) + "\n")

    print(f"      [数据] {mail_path.relative_to(history.REPO_ROOT)}")
    print(f"      [数据] {resp_path.relative_to(history.REPO_ROOT)}")
    return today


def send_test_email() -> None:
    """发送一封测试邮件，验证 SMTP 配置可用。

    不搜索、不调用 DeepSeek，只做一次完整的 SMTP 发送验证。
    收件人取 SMTP_TO 环境变量（或 .env 配置）。
    """
    cfg = SMTPConfig.from_env()
    send_email(
        cfg=cfg,
        subject="AgentForge 测试邮件",
        html_body=(
            "<h2>AgentForge 测试邮件</h2>"
            "<p>这封邮件用于验证 SMTP 配置是否正常。</p>"
            "<p>如果你收到这封邮件，说明 SMTP 配置已就绪，"
            "可以运行 <code>python agents/daily-digest/main.py</code> "
            "发送正式日报。</p>"
        ),
        text_body="AgentForge 测试邮件：SMTP 配置验证成功。",
    )
    print(f"✅ 测试邮件已发送到: {', '.join(cfg.to)}")


def main() -> None:
    """主入口：搜索 → 去重 → 生成 → 存档 → 发送。

    命令行参数:
        --dry-run          真实搜索与生成，但不发送、不写数据，日报打印到终端
        --send-test-email  只发一封测试邮件验证 SMTP，不搜索不生成

    数据流:
        1. GitHub 搜索 Top 仓库
        2. 与历史 resp-list 确定性去重
        3. DeepSeek 生成中文日报
        4. 与历史 mail 做 LLM 语义去重
        5. 写 data/<TAG>/YYYY-MM/ 存档
        6. SMTP 发送
    """
    parser = argparse.ArgumentParser(description="每日热门 Agent/Skill 仓库日报")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="本地测试：不发送邮件，把日报打印到终端",
    )
    parser.add_argument(
        "--send-test-email",
        action="store_true",
        help="只发送一封测试邮件，验证 SMTP 配置（不搜索、不调用 DeepSeek）",
    )
    args = parser.parse_args()

    if args.send_test_email:
        send_test_email()
        return

    print("[1/4] 搜索 GitHub 热门 agent/skill 仓库 ...")
    repos = search_repos(
        queries=SEARCH_QUERIES,
        days=DAYS_BACK,
        per_query=PER_QUERY,
        top_n=TOP_N,
    )
    if not repos:
        print("[error] 没有搜索到任何仓库，请检查 GITHUB_TOKEN 与网络。")
        sys.exit(1)
    print(f"      共找到 {len(repos)} 个仓库")

    # 历史去重：剔除历史 resp-list 中已关注过的仓库（data/<TAG>/ 中的记录）
    repos = filter_known_repos(repos)
    if not repos:
        print("[info] 本次搜索结果与历史记录全部重复，跳过生成与发送。")
        return
    print(f"      去重后剩 {len(repos)} 个新仓库")

    print(f"[2/4] 调用 DeepSeek ({MODEL}) 生成日报 ...")
    html_report = build_daily_report(repos)
    print("      日报生成完成")

    # LLM 语义去重：与最近的历史邮件比对，确认没有重复内容
    print("      与历史邮件比对去重 ...")
    dedupe = dedupe_with_llm(html_report)
    if dedupe.get("has_duplicate"):
        dup_list = dedupe.get("duplicated_repos", [])
        print(f"[warn] 与历史邮件存在大量重复: {', '.join(dup_list) or '未知'}")
        print(f"       {dedupe.get('analysis', '')}")
    else:
        print("      未发现与历史邮件重复的内容")

    # 日报正文头部附加搜索元信息（收件人可溯源）
    metadata = (
        f"<p style='color:#888;font-size:12px'>"
        f"数据来源：GitHub Search · 近 {DAYS_BACK} 天活跃仓库 · 共 {len(repos)} 个 · "
        f"生成模型 {MODEL}</p>"
    )
    html_report = metadata + html_report

    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY-RUN：以下为生成的日报（未发送、未保存记录）")
        print("=" * 60)
        print(html_report)
        return

    # 发信前把本次日报与仓库列表写入 data/<TAG>/ 作为历史记录
    print("[3/4] 保存邮件与仓库数据 ...")
    today = save_history_record(html_report, _html_to_text(html_report), repos)

    print("[4/4] 通过 SMTP 发送邮件 ...")
    cfg = SMTPConfig.from_env()
    send_email(
        cfg=cfg,
        subject=f"今日 AI Agent / Skill 热门仓库日报（{today}）",
        html_body=html_report,
        text_body=_html_to_text(html_report),
    )
    print(f"      邮件已发送到: {', '.join(cfg.to)}")


def _html_to_text(html: str) -> str:
    """极简 HTML→纯文本：去掉标签，用于邮件纯文本正文。

    处理规则：
        去掉 <style> 块、把 <br> 转换行、块级标签（</p></div></li></h>）换行、
        剥离其余标签、反转义 HTML 实体、压缩连续空行。
    """
    import html as html_lib
    import re

    # 先移除 <style> 样式块（其中可能含 < 字符干扰后续解析）
    text = re.sub(r"<style.*?</style>", "", html, flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>|</div>|</li>", "\n", text)
    text = re.sub(r"</h[1-6]>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


if __name__ == "__main__":
    from agents._shared.deepseek import DeepSeekError
    from agents._shared.emailer import EmailError

    try:
        main()
    except (EmailError, DeepSeekError, FileNotFoundError) as exc:
        print(f"\n[error] {exc}")
        print("提示：本地测试请复制 .env.example 为 .env 并填写完整配置。")
        sys.exit(1)
