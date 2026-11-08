"""GitHub REST 客户端（T2/T4）：Draft PR 创建、按 head/base 查询复用。

- 仓库地址解析复用 credentials.parse_repo_url（保存/prepare/publish 同一 parser）；
- 查询先于创建：push/PR 边界中断后按 repo/head/base 对账复用已知远端结果；
- 创建一律 draft=true（方案：合并交由维护者）；
- 所有错误文本经 credentials.sanitize_text 脱敏。
测试注入 Fake 实现 PRClient；真实实现用 httpx.AsyncClient。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from backend.modules.superagent.credentials import RepoRef, sanitize_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PullRequest:
    number: int
    api_url: str
    html_url: str
    state: str = ""
    draft: bool = False
    head_ref: str = ""
    merged: bool = False


class PRClient(Protocol):
    async def find_pr_for_head(self, *, ref: RepoRef, head_branch: str, base_branch: str) -> PullRequest | None: ...
    async def create_draft_pr(self, *, ref: RepoRef, title: str, head: str, base: str, body: str) -> PullRequest: ...


class HttpxPRClient:
    """POST/GET /repos/{owner}/{repo}/pulls；token 只进 Authorization 头。"""

    def __init__(self, *, token: str, timeout: float = 30.0) -> None:
        self._token = token
        self._timeout = timeout

    async def find_pr_for_head(
        self, *, ref: RepoRef, head_branch: str, base_branch: str
    ) -> PullRequest | None:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # open + closed 都查：重试时若 PR 已被关闭也复用，不重复创建
            response = await client.get(
                f"https://api.github.com/repos/{ref.full_name}/pulls",
                headers=_headers(self._token),
                params={"head": f"{ref.owner}:{head_branch}", "base": base_branch,
                        "state": "all", "per_page": "20"},
            )
            if response.status_code >= 400:
                detail = sanitize_text(response.text[:300], tokens=(self._token,))
                logger.warning("查询 PR 失败 status=%s detail=%s", response.status_code, detail)
                raise RuntimeError(f"查询已有 PR 失败（HTTP {response.status_code}）：{detail}")
            for item in response.json() or []:
                head_ref = str((item.get("head") or {}).get("ref") or "")
                if head_ref == head_branch:
                    return PullRequest(
                        number=int(item.get("number") or 0),
                        api_url=str(item.get("url") or ""),
                        html_url=str(item.get("html_url") or ""),
                        state=str(item.get("state") or ""),
                        draft=bool(item.get("draft")),
                        head_ref=head_ref,
                        merged=bool(item.get("merged")),
                    )
        return None

    async def create_draft_pr(
        self, *, ref: RepoRef, title: str, head: str, base: str, body: str,
    ) -> PullRequest:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"https://api.github.com/repos/{ref.full_name}/pulls",
                headers=_headers(self._token),
                json={"title": title, "head": head, "base": base, "body": body, "draft": True},
            )
            if response.status_code >= 400:
                detail = sanitize_text(response.text[:300], tokens=(self._token,))
                logger.warning("创建 PR 失败 status=%s detail=%s", response.status_code, detail)
                raise RuntimeError(f"创建 PR 失败（HTTP {response.status_code}）：{detail}")
            data = response.json()
        return PullRequest(
            number=int(data.get("number") or 0),
            api_url=str(data.get("url") or ""),
            html_url=str(data.get("html_url") or ""),
            state=str(data.get("state") or ""),
            draft=bool(data.get("draft")),
            head_ref=str((data.get("head") or {}).get("ref") or head),
        )


def _headers(token: str) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers
