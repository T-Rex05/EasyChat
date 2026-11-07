"""bootstrap 注入的业务工具集合。

工具只做参数校验/权限调用，状态转换全部在模块 service 内；每轮工具
身份来自 ToolContext，绝不接受模型传入的 user_id。
"""
from __future__ import annotations

from typing import Any


def extra_tools(registry: Any) -> list[Any]:
    """按已装配模块返回 LangChain 工具；后续阶段逐步追加。"""
    tools: list[Any] = []
    if getattr(registry, "scheduling", None) is not None:
        from backend.tools.business.reminder_tools import build_reminder_tools

        tools.extend(
            build_reminder_tools(
                scheduling=registry.scheduling,
                channels=getattr(registry, "channels", None),
                profiles=getattr(registry, "profiles", None),
            )
        )
    if getattr(registry, "ledger", None) is not None:
        from backend.tools.business.ledger_tools import build_ledger_tools

        tools.extend(build_ledger_tools(ledger=registry.ledger))
    if getattr(registry, "inbox", None) is not None:
        from backend.tools.business.inbox_tools import build_inbox_tools

        tools.extend(
            build_inbox_tools(
                inbox=registry.inbox,
                assistant=getattr(registry, "assistant", None),
            )
        )
    if (
        getattr(registry, "superagent", None) is not None
        and getattr(registry, "runtime", None) is not None
    ):
        from backend.tools.business.superagent_tools import build_superagent_tools

        tools.extend(build_superagent_tools(superagent=registry.superagent))
    return tools
