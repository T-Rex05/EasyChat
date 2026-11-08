"""T5 superagent 工具：服务端操作键幂等、来源固定回执、身份与权限。"""
from __future__ import annotations

import uuid

from backend.modules.superagent.api import SuperagentService
from backend.shared.tool_context import ToolContext, config_with
from backend.tools.business.superagent_tools import build_superagent_tools
from tests.support.rig import TEST_ENCRYPTION_SECRET, make_rig

REPO_URL = "https://github.com/foo/bar.git"


def _service(rig):
    ready = rig if rig.access is not None else make_rig(rig.tmp_path, seed_access=True)
    rig.db, rig.access = ready.db, ready.access
    service = SuperagentService(ready.db, access=ready.access)
    service.set_encryption_secret(TEST_ENCRYPTION_SECRET)
    service.runner_ready = True
    admin = ready.seed_user(role="super_admin", username=f"adm_{uuid.uuid4().hex[:6]}")
    user = ready.seed_user(role="user", grants=("superagent.view", "superagent.create"))
    service.update_settings(admin, enabled=True, repo_url=REPO_URL, base_branch="main",
                            github_token="ghp_t_1234567890")
    return service, admin, user


def _ctx(principal, *, source="wechat", source_ref="wx_1", channel_account_id="chn_1",
         session_id="sess_abc"):
    return ToolContext(
        principal=principal, run_id="run_x", session_id=session_id,
        source=source, channel_account_id=channel_account_id,
        source_ref=source_ref, source_chat_id="chat_1",
    )


async def test_tool_creates_task_with_source_target(rig) -> None:
    service, admin, user = _service(rig)
    (tool,) = build_superagent_tools(superagent=service)
    context = _ctx(user)
    result = await tool.ainvoke(
        {"title": "修复 bug", "requirement": "修复登录页 500"},
        config=config_with(context),
    )
    assert "error" not in result
    task = service.get_task(user, result["task_id"])
    assert task.source == "tool"
    assert task.source_ref == "wx_1"
    assert task.source_kind == "wechat"
    assert task.session_id == "sess_abc"


async def test_tool_same_session_same_requirement_is_idempotent(rig) -> None:
    """LLM 工具的服务端操作键：同会话同需求只受理一次。"""
    service, admin, user = _service(rig)
    (tool,) = build_superagent_tools(superagent=service)
    context = _ctx(user)
    first = await tool.ainvoke(
        {"title": "t", "requirement": "完全相同的需求"}, config=config_with(context),
    )
    second = await tool.ainvoke(
        {"title": "t（换个标题也没用）", "requirement": "完全相同的需求"},
        config=config_with(context),
    )
    assert first["task_id"] == second["task_id"]
    assert len(service.list_tasks(user, limit=10)) == 1
    # 不同会话：同一需求是不同任务
    other = await tool.ainvoke(
        {"title": "t", "requirement": "完全相同的需求"},
        config=config_with(_ctx(user, session_id="sess_other")),
    )
    assert other["task_id"] != first["task_id"]


async def test_tool_rejects_missing_identity_and_web_source_has_no_target(rig) -> None:
    service, admin, user = _service(rig)
    (tool,) = build_superagent_tools(superagent=service)
    # 无身份
    result = await tool.ainvoke({"title": "t", "requirement": "r"}, config=None)
    assert result["error_code"] == "unauthenticated"
    # web 来源：无回执目标快照（走面板即可）
    context = _ctx(user, source="web", source_ref="")
    result = await tool.ainvoke(
        {"title": "t", "requirement": "web 需求"}, config=config_with(context),
    )
    task = service.get_task(user, result["task_id"])
    assert task.source_ref == "" and task.source_kind == ""


async def test_tool_gate_error_is_stable_message(rig) -> None:
    service, admin, user = _service(rig)
    service.update_settings(admin, enabled=False)
    (tool,) = build_superagent_tools(superagent=service)
    result = await tool.ainvoke(
        {"title": "t", "requirement": "r"},
        config=config_with(_ctx(user)),
    )
    assert "error" in result
    assert "未启用" in result["error"]
