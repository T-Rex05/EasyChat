"""GitHub/Gitee REST 客户端：只做创建 PR 这一件外部事（httpx，无 SDK 依赖）。

host 与 owner/repo 一律从配置的 repo_url 解析；测试注入 Fake 实现 PRClient。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_REPO_URL_RE = re.compile(
    r"https://(?:www\.)?(?P<host>github\.com|gitee\.com)/(?P<full>[^/]+/[^/]+?)(?:\.git)?/?$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class PullRequest:
    number: int
    api_url: str
    html_url: str


class PRClient(Protocol):
    async def create_pull_request(
        self, *, repo_url: str, title: str, head: str, base: str, body: str,
    ) -> PullRequest: ...


def parse_repo_full_name(repo_url: str) -> tuple[str, str]:
    """仓库 URL → (host, owner/repo)；不支持的形式抛 ValueError。"""
    match = _REPO_URL_RE.match(repo_url.strip())
    if not match:
        raise ValueError(f"无法从仓库地址解析 owner/repo: {repo_url}")
    return match.group("host"), match.group("full")


def push_url_with_token(repo_url: str, token: str) -> str:
    """一次性 push URL：凭证只出现在命令行参数，不写进 .git/config。"""
    host, full = parse_repo_full_name(repo_url)
    return f"https://{token}@{host}/{full}.git"


class HttpxPRClient:
    """POST /repos/{owner}/{repo}/pulls；Gitee 字段差异收敛在这里。"""

    def __init__(self, *, token: str, timeout: float = 30.0) -> None:
        self._token = token
        self._timeout = timeout

    async def create_pull_request(
        self, *, repo_url: str, title: str, head: str, base: str, body: str,
    ) -> PullRequest:
        import httpx  # noqa: PLC0415

        host, full_name = parse_repo_full_name(repo_url)
        api_base = "https://gitee.com/api/v5" if host == "gitee.com" else "https://api.github.com"
        headers = {"Accept": "application/vnd.github+json"}
        payload: dict[str, Any] = {"title": title, "head": head, "base": base, "body": body}
        if host == "gitee.com":
            payload["access_token"] = self._token
        else:
            headers["Authorization"] = f"Bearer {self._token}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{api_base}/repos/{full_name}/pulls", headers=headers, json=payload,
            )
            if response.status_code >= 400:
                detail = response.text[:300]
                logger.warning("创建 PR 失败 status=%s detail=%s", response.status_code, detail)
                raise RuntimeError(f"创建 PR 失败（HTTP {response.status_code}）：{detail}")
            data = response.json()
        return PullRequest(
            number=int(data.get("number") or 0),
            api_url=str(data.get("url") or ""),
            html_url=str(data.get("html_url") or ""),
        )
