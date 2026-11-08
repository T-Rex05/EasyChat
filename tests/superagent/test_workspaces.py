"""T3 工作区隔离回归：路径由服务生成、包含 host/repo/task、拒绝逃逸。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.modules.superagent.credentials import parse_repo_url
from backend.modules.superagent.workspaces import WorkspaceError, workspace_key, workspace_path


def test_workspace_key_is_hosted_per_repo_and_task() -> None:
    ref = parse_repo_url("https://github.com/foo/bar.git")
    ref_other = parse_repo_url("https://github.com/foo/baz.git")
    task_id = "sag_" + "a" * 32
    key = workspace_key(ref, task_id)
    assert key == f"github.com/{hashlib.sha256(b'foo/bar').hexdigest()[:10]}/{task_id}"
    # 不同任务不同目录
    other_task = workspace_key(ref, "sag_" + "b" * 32)
    assert other_task != key
    # 不同仓库不同目录（同名 task id 也不冲突）
    assert workspace_key(ref_other, task_id) != key


def test_workspace_key_rejects_bad_task_id() -> None:
    ref = parse_repo_url("https://github.com/foo/bar.git")
    with pytest.raises(WorkspaceError):
        workspace_key(ref, "not-a-task-id")
    with pytest.raises(WorkspaceError):
        workspace_key(ref, "sess_abc")


def test_workspace_path_resolves_inside_root(tmp_path: Path) -> None:
    ref = parse_repo_url("https://github.com/foo/bar.git")
    key = workspace_key(ref, "sag_" + "a" * 32)
    path = workspace_path(tmp_path, key)
    assert path.is_absolute()
    assert tmp_path.resolve() in path.resolve().parents or path.resolve().parent.parent.parent == tmp_path.resolve()
    # 深度固定：root/host/hash/task
    assert len(path.relative_to(tmp_path.resolve()).parts) == 3


@pytest.mark.parametrize("key", [
    "../../etc/passwd",
    "github.com/../../..",
    "github.com/hash/../../../evil",
    "",
    "a/b",
    "a/b/c/d",
    "github.com//task",
])
def test_workspace_path_rejects_escape(tmp_path: Path, key: str) -> None:
    with pytest.raises(WorkspaceError):
        workspace_path(tmp_path, key)
