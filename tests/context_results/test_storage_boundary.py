import pytest

from backend.context.tool_results.runtime import default_store_root
from backend.tools import code_executor


def test_default_store_lives_outside_source_workspace(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENTFORGE_CONTEXT_RESULTS_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "private-appdata"))
    assert default_store_root().is_relative_to(tmp_path / "private-appdata")


def test_configured_store_is_not_readable_through_code_mode_files(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    store = root / "custom-private-store"
    store.mkdir(parents=True)
    secret = store / "ar_example.txt"
    secret.write_text("other-tenant-evidence", encoding="utf-8")
    monkeypatch.setattr(code_executor, "_PROJECT_ROOT", str(root))
    monkeypatch.setenv("AGENTFORGE_CONTEXT_RESULTS_DIR", str(store))
    with pytest.raises(code_executor.FileOperationError):
        code_executor.code_mode_read_file(str(secret))
    assert "other-tenant-evidence" not in code_executor.code_mode_search_files(
        "other-tenant", target="content", path=".")
    assert "ar_example.txt" not in code_executor.code_mode_search_files("*.txt", target="files", path=".")


def test_legacy_workspace_store_remains_blocked(monkeypatch, tmp_path):
    store = tmp_path / "data" / "tool_results"
    store.mkdir(parents=True)
    secret = store / "old.txt"
    secret.write_text("old-tenant-evidence", encoding="utf-8")
    monkeypatch.setattr(code_executor, "_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(code_executor.FileOperationError):
        code_executor.code_mode_read_file(str(secret))


def test_sibling_prefix_is_not_a_workspace_child(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    sibling = tmp_path / "workspace-private"
    root.mkdir()
    sibling.mkdir()
    file = sibling / "secret.txt"
    file.write_text("private", encoding="utf-8")
    monkeypatch.setattr(code_executor, "_PROJECT_ROOT", str(root))
    with pytest.raises(code_executor.FileOperationError):
        code_executor.code_mode_read_file(str(file))
