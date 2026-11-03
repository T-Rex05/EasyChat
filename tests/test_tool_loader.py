"""用户工具加载器单元测试：可用性隔离 / 编译 / 运行时安全"""
import json

import pytest

# 注：`backend.service.tool_loader` 已在重构提交 2b3d44f「重构工具管理、内容池审核、权限缓存」
# 中被移除，但本测试文件遗留至今。模块级 import 会让 `pytest tests` 整体报收集错误
# （ERROR collecting tests/test_tool_loader.py），一个过期测试拖垮整个套件。
# 这里改为显式 skip（会打印原因，不是静默通过）；若该模块回归，删掉 importorskip 即可。
tool_loader = pytest.importorskip(
    "backend.service.tool_loader",
    reason="backend.service.tool_loader 已在重构 2b3d44f 中移除，本测试已过期",
)


SAMPLE_CODE = (
    "from langchain_core.tools import tool\n"
    "from pydantic import BaseModel, Field\n"
    "\n"
    "class EchoInput(BaseModel):\n"
    "    text: str = Field(description='要复述的文本')\n"
    "\n"
    "@tool(args_schema=EchoInput)\n"
    "def my_echo(text: str) -> str:\n"
    "    \"\"\"复述文本。\"\"\"\n"
    "    return f\"echo: {text}\"\n"
)


def _write_tool(tmp_path, name, status="approved", owner=1, enabled=True, code=None, **extra):
    rec = {
        "name": name,
        "description": "desc",
        "status": status,
        "owner_id": owner,
        "code": code or SAMPLE_CODE.replace("my_echo", name),
        "enabled": enabled,
        "requirements": [],
    }
    rec.update(extra)
    (tmp_path / f"{name}.json").write_text(json.dumps(rec), encoding="utf-8")


class TestToolRecords:
    def test_own_approved_included(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tool_loader, "TOOLS_DIR", tmp_path)
        monkeypatch.setattr(tool_loader, "_pool_installed_names", lambda uid: set())
        _write_tool(tmp_path, "t1", owner=1)
        records = tool_loader.get_user_tool_records(1)
        assert [r["name"] for r in records] == ["t1"]

    def test_pending_and_rejected_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tool_loader, "TOOLS_DIR", tmp_path)
        monkeypatch.setattr(tool_loader, "_pool_installed_names", lambda uid: set())
        _write_tool(tmp_path, "t1", status="pending", owner=1)
        _write_tool(tmp_path, "t2", status="rejected", owner=1)
        _write_tool(tmp_path, "t3", status="approved", owner=1)
        records = tool_loader.get_user_tool_records(1)
        assert [r["name"] for r in records] == ["t3"]

    def test_other_users_tool_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tool_loader, "TOOLS_DIR", tmp_path)
        monkeypatch.setattr(tool_loader, "_pool_installed_names", lambda uid: set())
        _write_tool(tmp_path, "t1", owner=2)
        assert tool_loader.get_user_tool_records(1) == []

    def test_pool_installed_included(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tool_loader, "TOOLS_DIR", tmp_path)
        monkeypatch.setattr(tool_loader, "_pool_installed_names", lambda uid: {"pool_tool"})
        _write_tool(tmp_path, "pool_tool", owner=2)
        records = tool_loader.get_user_tool_records(1)
        assert [r["name"] for r in records] == ["pool_tool"]

    def test_disabled_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tool_loader, "TOOLS_DIR", tmp_path)
        monkeypatch.setattr(tool_loader, "_pool_installed_names", lambda uid: set())
        _write_tool(tmp_path, "t1", owner=1, enabled=False)
        assert tool_loader.get_user_tool_records(1) == []


class TestExecToolCode:
    def test_compile_and_extract(self):
        code = SAMPLE_CODE.replace("my_echo", "my_echo")
        tool = tool_loader.exec_tool_code(code, "my_echo")
        assert tool is not None
        assert tool.name == "my_echo"
        result = tool.invoke({"text": "hi"})
        assert result == "echo: hi"

    def test_syntax_error_raises(self):
        with pytest.raises(SyntaxError):
            tool_loader.exec_tool_code("def broken(:", "bad")

    def test_no_tool_returns_none(self):
        assert tool_loader.exec_tool_code("x = 1", "nothing") is None


class TestSafeHandler:
    def test_normal_execution(self):
        tool = tool_loader.exec_tool_code(SAMPLE_CODE, "my_echo")
        handler = tool_loader._safe_handler(tool, "my_echo")
        assert handler({"text": "你好"}) == "echo: 你好"

    def test_exception_returns_error_string(self):
        code = (
            "from langchain_core.tools import tool\n"
            "\n"
            "@tool\n"
            "def my_bad() -> str:\n"
            "    \"\"\"会抛异常的工具。\"\"\"\n"
            "    raise RuntimeError(\"boom\")\n"
        )
        tool = tool_loader.exec_tool_code(code, "my_bad")
        handler = tool_loader._safe_handler(tool, "my_bad")
        result = handler({})
        assert "[工具执行异常]" in result

    def test_timeout(self, monkeypatch):
        monkeypatch.setattr(tool_loader, "EXEC_TIMEOUT_SECONDS", 0.2)
        code = (
            "from langchain_core.tools import tool\n"
            "import time\n"
            "\n"
            "@tool\n"
            "def my_slow() -> str:\n"
            "    \"\"\"慢工具。\"\"\"\n"
            "    time.sleep(5)\n"
            "    return \"done\"\n"
        )
        tool = tool_loader.exec_tool_code(code, "my_slow")
        handler = tool_loader._safe_handler(tool, "my_slow")
        result = handler({})
        assert "[工具执行超时]" in result

    def test_output_truncated(self, monkeypatch):
        monkeypatch.setattr(tool_loader, "MAX_OUTPUT_CHARS", 20)
        tool = tool_loader.exec_tool_code(SAMPLE_CODE, "my_echo")
        handler = tool_loader._safe_handler(tool, "my_echo")
        result = handler({"text": "x" * 200})
        assert "截断" in result
        assert len(result) < 80