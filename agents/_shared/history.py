"""Agent 数据目录模块：管理 data/<agent>/YYYY-MM/ 下的每日数据文件。

每个 agent 一个数据目录（目录名即 agent 名，如 daily-digest）。数据按月份
分目录，文件名以当月日期开头，统一使用 **Markdown（.md）扩展名**：

    data/daily-digest/
    └── 2026-08/
        ├── 07-mail.md        # 当日原始邮件内容（Markdown）
        └── 07-resp-list.md   # 当日关注的 GitHub 仓库列表（地址/star/简介）

用途：
- 存档：每次运行把生成的邮件与仓库列表写入 data/，供追溯
- 去重：后续运行时读取历史 resp-list，剔除已关注过的仓库；读取 mail 做语义比对

写入路径计算：
    data_path(agent, kind)   -> data/<agent>/YYYY-MM/DD-<kind>.md
其中 kind 为 'mail' 或 'resp-list'。
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]   # AgentForge/
DATA_ROOT = REPO_ROOT / "data"


class HistoryError(RuntimeError):
    """数据读写失败。"""


# 识别文本中的仓库引用（owner/name 或 github.com URL）
_REPO_PATTERN = re.compile(
    r"(?:github\.com/)?([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)",
    re.IGNORECASE,
)


def find_repo_refs(text: str) -> set[str]:
    """从文本中提取仓库引用，返回 {owner/repo, github.com/owner/repo, ...}。

    历史记录中仓库可能以 `owner/repo` 或 `https://github.com/owner/repo` 出现，
    因此两种形式都会加入集合，供过滤时精确匹配。
    """
    found: set[str] = set()
    for m in _REPO_PATTERN.finditer(text):
        full = m.group(0)
        last_two = "/".join(full.split("/")[-2:])
        found.add(last_two.lower())
        found.add(full.lower())
    return found


def agent_dir(agent: str, create: bool = False) -> Path:
    """返回 agent 的数据根目录（data/<agent>/）。

    参数:
        agent:  agent 名（目录名，须匹配 [A-Za-z0-9._-]+）
        create: 目录不存在时是否创建

    异常:
        HistoryError: agent 名非法
    """
    if not re.fullmatch(r"[A-Za-z0-9._-]+", agent):
        raise HistoryError(f"非法的 agent 名称: {agent!r}")
    d = DATA_ROOT / agent
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def month_dir(agent: str, ym: str, create: bool = False) -> Path:
    """返回某月份目录（data/<agent>/YYYY-MM/）。

    参数:
        agent:  agent 名
        ym:     年月，格式 YYYY-MM
        create: 目录不存在时是否创建

    异常:
        HistoryError: 年月格式非法
    """
    if not re.fullmatch(r"\d{4}-\d{2}", ym):
        raise HistoryError(f"非法的年月: {ym!r}")
    d = agent_dir(agent, create=create) / ym
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def data_path(agent: str, kind: str, date_str: str, create: bool = True) -> Path:
    """返回某条数据的写入路径：data/<agent>/YYYY-MM/DD-<kind>.md。

    参数:
        agent:     agent 名（目录名）
        kind:      'mail' 或 'resp-list'
        date_str:  YYYY-MM-DD
    同日同 kind 已存在时追加序号（-2、-3 ...），避免覆盖。
    """
    if kind not in ("mail", "resp-list"):
        raise HistoryError(f"非法的 kind: {kind!r}")
    y, m, d = date_str.split("-")
    md = month_dir(agent, f"{y}-{m}", create=create)
    base = md / f"{d}-{kind}.md"
    if not base.exists():
        return base
    idx = 2
    while (md / f"{d}-{kind}-{idx}.md").exists():
        idx += 1
    return md / f"{d}-{kind}-{idx}.md"


def save_data(agent: str, kind: str, date_str: str, content: str) -> Path:
    """把内容写入 data/<agent>/YYYY-MM/DD-<kind>.md，返回文件路径。"""
    path = data_path(agent, kind, date_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def list_data(agent: str, kind: str, newest_first: bool = True) -> list[Path]:
    """列出 agent 数据目录下所有 <dd>-<kind>.md 文件（跨月份，默认最新在前）。

    匹配形如 `07-mail.md`、`07-mail-2.md` 的文件名（同日同 kind 追加序号的情况）。
    """
    d = agent_dir(agent)
    if not d.exists():
        return []
    pat = re.compile(rf"\d{{2}}-{kind}(?:-\d+)??\.md$")
    # 排序键 = (月份, 文件名)，保证跨月份时按时间正确排序
    files = sorted(
        (
            p
            for month in d.iterdir()
            if month.is_dir() and re.fullmatch(r"\d{4}-\d{2}", month.name)
            for p in month.iterdir()
            if p.is_file() and pat.fullmatch(p.name)
        ),
        key=lambda p: (p.parent.name, p.name),
    )
    if newest_first:
        files.reverse()
    return files


def load_data(agent: str, kind: str, limit: int | None = None) -> list[tuple[str, str]]:
    """加载历史数据文件，返回 [(文件名, 内容), ...]（默认最新在前）。

    参数:
        agent: agent 名
        kind:  数据种类（'mail' / 'resp-list'）
        limit: 只加载最近 N 条（None 表示全部）
    """
    files = list_data(agent, kind, newest_first=True)
    if limit is not None:
        files = files[:limit]
    return [(p.name, p.read_text(encoding="utf-8")) for p in files]


def load_recent(agent: str, kind: str, limit: int = 5) -> str:
    """把最近 limit 条某类数据拼接为一段文本，供 DeepSeek 比对去重。

    参数:
        agent: agent 名
        kind:  数据种类（'mail' → 历史邮件，'resp-list' → 历史仓库列表）
        limit: 拼接最近多少条

    返回:
        拼接后的文本；没有历史数据时返回空字符串
    """
    records = load_data(agent, kind, limit=limit)
    if not records:
        return ""
    label = "历史邮件" if kind == "mail" else "历史仓库列表"
    parts = [f"【{label}】"]
    for name, content in records:
        parts.append(f"--- 文件: {name} ---")
        parts.append(content)
    return "\n\n".join(parts)
