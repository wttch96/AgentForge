"""GitHub Search API 封装。

基于 GitHub REST API 的仓库搜索：
  GET https://api.github.com/search/repositories?q=...&sort=stars&order=desc&per_page=20

带 GITHUB_TOKEN（Bearer）认证时搜索 rate limit 为 30 次/分钟，可满足多关键词查询。

使用方式：
    from agents._shared.github_search import search_repos
    repos = search_repos(
        queries=["agent", "claude skills"],
        days=7,
        per_query=20,
        top_n=10,
    )
    # 返回 [{"full_name", "html_url", "description", "stargazers_count",
    #         "forks_count", "pushed_at", "language", "topics", ...}]
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


class GitHubSearchError(RuntimeError):
    """GitHub 搜索失败。"""


def _gh_request(url: str, token: str) -> dict[str, Any]:
    """发送带认证的 GitHub API 请求，处理 rate limit 与限流重试。

    参数:
        url:   完整 API 地址（含 query string）
        token: GitHub Token，非空时带 Bearer 认证（提升 rate limit 到 30 次/分）

    返回:
        JSON 解析后的字典

    异常:
        GitHubSearchError: 请求失败（HTTP 错误或多次重试后仍网络失败）

    重试策略：
        - 403 且 rate limit 耗尽：按 Retry-After 头等待后重试（最多 120 秒）
        - 502/503/504 网关错误：指数退避重试
        - URLError 网络错误：指数退避，最多 4 次
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "AgentForge/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return _json(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and exc.headers.get("X-RateLimit-Remaining") == "0":
                # rate limit 耗尽：优先按服务器提示的 Retry-After 等待
                delay = float(exc.headers.get("Retry-After", "60"))
                time.sleep(min(delay, 120))
                continue
            if exc.code in (502, 503, 504):
                # 网关类错误：指数退避（2^attempt 秒）
                time.sleep(2 ** attempt)
                continue
            raise GitHubSearchError(
                f"GitHub API 请求失败: HTTP {exc.code} {exc.reason} - {url}"
            ) from exc
        except urllib.error.URLError as exc:
            if attempt == 3:
                raise GitHubSearchError(f"GitHub API 网络错误: {exc}") from exc
            time.sleep(2 ** attempt)
    raise GitHubSearchError(f"GitHub API 请求多次重试后仍失败: {url}")


def _json(resp: Any) -> dict[str, Any]:
    """把 HTTP 响应体解析为 JSON 字典。"""
    return json.loads(resp.read().decode("utf-8"))


def _search_repo(query: str, token: str, sort: str, order: str, per_page: int) -> list[dict[str, Any]]:
    """执行单次仓库搜索请求，返回 items 列表。"""
    params = urllib.parse.urlencode(
        {"q": query, "sort": sort, "order": order, "per_page": per_page}
    )
    data = _gh_request(f"{GITHUB_SEARCH_URL}?{params}", token)
    return data.get("items", [])


def _pick_fields(item: dict[str, Any]) -> dict[str, Any]:
    """从 GitHub 仓库对象中挑选日报需要的字段。"""
    return {
        "full_name": item.get("full_name", ""),
        "html_url": item.get("html_url", ""),
        "description": item.get("description"),
        "stargazers_count": item.get("stargazers_count", 0),
        "forks_count": item.get("forks_count", 0),
        "open_issues_count": item.get("open_issues_count", 0),
        "language": item.get("language"),
        "pushed_at": item.get("pushed_at", ""),
        "created_at": item.get("created_at", ""),
        "topics": item.get("topics", []) or [],
        "license": (item.get("license") or {}).get("spdx_id"),
    }


def _days_ago(days: int) -> str:
    """返回 N 天前的 ISO 日期字符串（UTC），用于 pushed:>= 过滤。"""
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")


def search_repos(
    queries: list[str],
    days: int = 7,
    per_query: int = 20,
    top_n: int = 10,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """对每个关键词执行仓库搜索，合并去重后返回 star 数最高的 top_n 个仓库。

    参数:
        queries:    GitHub 搜索关键词列表
        days:       只看最近 N 天有更新的仓库（pushed:>=）
        per_query:  每个关键词取前多少条
        top_n:      合并后最终返回的仓库数
        token:      GitHub Token（默认读 GITHUB_TOKEN 环境变量）
    """
    token = token or os.environ.get("GITHUB_TOKEN", "")
    since = _days_ago(days)

    merged: dict[str, dict[str, Any]] = {}
    for query in queries:
        q = f"{query} pushed:>={since}"
        try:
            items = _search_repo(q, token, sort="stars", order="desc", per_page=per_query)
        except GitHubSearchError as exc:
            # 单关键词失败不中断整体流程
            print(f"[warn] 关键词 '{query}' 搜索失败: {exc}")
            continue

        for item in items:
            full_name = item.get("full_name")
            if not full_name:
                continue
            # 同名仓库只保留一次，star 多的优先（后续按 star 排序时自然覆盖）
            merged.setdefault(full_name, _pick_fields(item))

    ranked = sorted(merged.values(), key=lambda r: r["stargazers_count"], reverse=True)
    return ranked[:top_n]
