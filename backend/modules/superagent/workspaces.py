"""superagent 工作区（T3，方案 §6 执行与恢复）。

- 路径由服务生成：{root}/{host}/{repo_hash}/{task_id}，repo_hash 为
  owner/repo 的 sha256 前 10 位（改仓库设置不影响既有任务目录，且路径
  不含用户可控的原始字符）；
- 目录名只由服务生成；resolve 后校验仍在配置根目录内（防符号链接/相对路径逃逸）；
- 同一任务的多个 attempt 复用工作区，恢复前读取 Git 与数据库检查点。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from backend.modules.superagent.credentials import RepoRef

_TASK_ID_RE = re.compile(r"^sag_[0-9a-f]{32}$")


class WorkspaceError(ValueError):
    pass


def workspace_key(ref: RepoRef, task_id: str) -> str:
    """host/repo_hash/task_id 的规范键（持久化在 attempts.workspace_key）。"""
    if not _TASK_ID_RE.match(task_id or ""):
        raise WorkspaceError(f"非法任务 ID: {task_id}")
    repo_hash = hashlib.sha256(ref.full_name.encode()).hexdigest()[:10]
    return f"{ref.host}/{repo_hash}/{task_id}"


def workspace_path(root: Path, key: str) -> Path:
    """把 workspace_key 解析为根目录内的绝对路径，并做逃逸校验。"""
    parts = key.split("/")
    if len(parts) != 3 or not all(parts) or any(p in (".", "..") for p in parts):
        raise WorkspaceError(f"非法 workspace key: {key}")
    resolved = (Path(root).resolve() / parts[0] / parts[1] / parts[2]).resolve()
    root_resolved = Path(root).resolve()
    if root_resolved != resolved and root_resolved not in resolved.parents:
        raise WorkspaceError(f"workspace 逃逸出根目录: {key}")
    return resolved


def repo_workspace_key_for_repo(root: Path, ref: RepoRef) -> str:
    """兼容旧布局的查询：给定 repo 的目录前缀（host/repo_hash）。"""
    repo_hash = hashlib.sha256(ref.full_name.encode()).hexdigest()[:10]
    return f"{ref.host}/{repo_hash}"
