"""
工具直接调用控制器

提供直接调用 Hermes 工具的 REST API，用于论文复现等场景。
"""

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import Dict, Any
import json

from backend.utils.log_utils import log

logger = log

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolInvokeResponse(BaseModel):
    """工具调用响应"""
    result: str
    success: bool
    error: str = None


@router.post("/{tool_name}", response_model=ToolInvokeResponse)
async def invoke_tool(tool_name: str, params: Dict[str, Any] = Body(default={})):
    """
    直接调用工具

    Args:
        tool_name: 工具名称（如 parse_paper, extract_claim_rubric）
        params: 工具参数（直接作为 JSON body 传递）

    Returns:
        ToolInvokeResponse: 工具执行结果

    Example:
        POST /api/tools/parse_paper
        Body: {"paper_url": "https://arxiv.org/abs/1706.03762"}
    """
    try:
        # 导入工具
        from backend.tools.tools_decorator import get_project_tools

        # 查找工具
        tools_registry = {tool.name: tool for tool in get_project_tools()}

        if tool_name not in tools_registry:
            raise HTTPException(
                status_code=404,
                detail=f"工具 '{tool_name}' 不存在。可用工具: {list(tools_registry.keys())}"
            )

        tool = tools_registry[tool_name]

        # 调用工具
        logger.info(f"🔧 调用工具: {tool_name}, 参数: {params}")

        result = tool.invoke(params)

        logger.info(f"✅ 工具调用成功: {tool_name}")

        return ToolInvokeResponse(
            result=result,
            success=True
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 工具调用失败: {tool_name}, 错误: {e}", exc_info=True)
        return ToolInvokeResponse(
            result="",
            success=False,
            error=str(e)
        )


@router.get("/")
async def list_tools():
    """
    列出所有可用工具

    Returns:
        list: 工具名称列表
    """
    try:
        from backend.tools.tools_decorator import get_project_tools

        tools = get_project_tools()
        tool_list = [
            {
                "name": tool.name,
                "description": tool.description,
                "args_schema": tool.args_schema.schema() if tool.args_schema else None
            }
            for tool in tools
        ]

        return {
            "tools": tool_list,
            "count": len(tool_list)
        }

    except Exception as e:
        logger.error(f"❌ 列出工具失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def register_tool_routes(app):
    """注册工具路由到 FastAPI 应用"""
    app.include_router(router)
    logger.info("✅ 工具调用 API 已注册: /api/tools")