"""superagent 业务工具：微信对话里收集需求并受理编码任务。

模型引导约定：用户明确想让代理改代码/提 PR 且需求已足够具体时才调用；
requirement 必须是自包含的完整需求（目标/验收/涉及范围），对话中的
零散上下文由模型整理后写入，绝不依赖后续追问。
身份来自 ToolContext；权限校验在 service.create_task 内。
"""
from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.shared.errors import AppError
from backend.shared.tool_context import resolve

logger = logging.getLogger(__name__)


class SubmitTaskInput(BaseModel):
    title: str = Field(description="任务标题，≤120 字，概括要做什么")
    requirement: str = Field(
        description=(
            "自包含的完整需求：目标、验收标准、涉及文件/模块、约束。"
            "信息不足时先在对话里追问用户，不要用占位描述提交。"
        )
    )
    context_extra: str = Field(default="", description="补充上下文（相关链接、已有结论等），可留空")


def build_superagent_tools(*, superagent: Any) -> list[Any]:
    if superagent is None:
        return []

    @tool(args_schema=SubmitTaskInput)
    async def superagent_submit_task(
        title: str,
        requirement: str,
        context_extra: str = "",
        config: RunnableConfig = None,
    ) -> dict[str, Any]:
        """把一个编码任务提交给后台超级代理：它会在独立工作区实现并自动创建 Pull Request，完成后把结果回信给用户。"""
        context = resolve(config)
        if context is None:
            return {"error": "缺少可信用户身份，拒绝提交任务", "error_code": "unauthenticated"}
        try:
            task = await _create(
                superagent, context.principal,
                title=title, requirement=requirement, context_extra=context_extra,
                session_id=context.session_id or "",
            )
        except AppError as exc:
            # 业务错误本身是给用户看的，但只返回稳定消息，不带内部 details。
            return {"error": exc.message, "error_code": exc.code.value}
        except Exception:  # noqa: BLE001  内部异常不能把 SQL/路径原文交给模型
            logger.exception("superagent 任务提交失败")
            return {"error": "任务提交失败，请稍后再试", "error_code": "internal_error"}
        return {
            "task_id": task.task_id,
            "status": task.status,
            "branch": task.branch,
            "message": (
                "任务已受理，后台代理将开始工作。完成后会把分支和 PR 链接回信给你；"
                "也可以在 Web 面板查看进度。"
            ),
        }

    superagent_submit_task._toolset = "__always_available__"
    return [superagent_submit_task]


async def _create(superagent: Any, principal, *, title: str, requirement: str,
                  context_extra: str, session_id: str):
    from backend.modules.superagent.contracts import SOURCE_TOOL  # noqa: PLC0415

    return superagent.create_task(
        principal, title=title, requirement=requirement,
        context_extra=context_extra, source=SOURCE_TOOL, session_id=session_id,
    )
