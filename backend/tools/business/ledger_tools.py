"""账本 5 个受控 LangChain 工具（不暴露提交能力）。

金额一律由服务端格式化；模型不执行除法/四舍五入。身份来自 ToolContext。
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.modules.ledger.tools import (
    TOOL_ANALYZE,
    TOOL_CORRECT,
    TOOL_IMPORT_PREVIEW,
    TOOL_REFUND_SUGGEST,
    TOOL_REPORT,
    LedgerToolbox,
)
from backend.shared.errors import AppError, UnauthenticatedError
from backend.shared.tool_context import resolve

logger = logging.getLogger(__name__)


class ImportPreviewInput(BaseModel):
    file_id: str = Field(description="context_prefix 中的 file_id")
    account_id: str = Field(default="", description="账本账户 ID，可留空")
    mapping: dict[str, str] | None = Field(default=None, description="可选列映射")


class AnalyzeInput(BaseModel):
    plan: dict[str, Any] = Field(description="受控 QueryPlan，不接受 SQL")
    request_id: str = Field(default="", description="幂等请求 ID，可留空")


class CorrectInput(BaseModel):
    transaction_id: str
    category_id: str = ""
    merchant: str = ""
    note: str = ""
    reason: str = "对话修正"


class ReportInput(BaseModel):
    plan: dict[str, Any]
    format: str = Field(default="markdown", description="markdown/csv")


class RefundInput(BaseModel):
    import_id: str = ""


def format_minor(amount_minor: int | None, currency: str = "CNY") -> str:
    if amount_minor is None:
        return "—"
    sign = "-" if amount_minor < 0 else ""
    yuan, cents = divmod(abs(int(amount_minor)), 100)
    symbol = "¥" if currency.upper() == "CNY" else f"{currency} "
    return f"{sign}{symbol}{yuan:,}.{cents:02d}"


def _decorate_amounts(value: Any, currency: str = "CNY") -> Any:
    """递归给 *_minor 字段补充 amount_text；不改变原数值。"""
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            result[key] = _decorate_amounts(item, currency)
        for key, item in list(result.items()):
            if key.endswith("_minor") and isinstance(item, int):
                result[key.replace("_minor", "_text")] = format_minor(item, currency)
        return result
    if isinstance(value, list):
        return [_decorate_amounts(item, currency) for item in value]
    return value


def _ctx(config: RunnableConfig = None):
    context = resolve(config)
    if context is None:
        raise UnauthenticatedError("缺少可信用户身份，拒绝访问账本")
    return context


def build_ledger_tools(*, ledger: Any) -> list[Any]:
    if ledger is None:
        return []
    toolbox = LedgerToolbox(ledger)

    async def _call(name: str, args: dict[str, Any], config) -> dict[str, Any]:
        try:
            context = _ctx(config)
            result = await toolbox.call(context.principal, name, args)
            return _decorate_amounts(result)
        except AppError as exc:
            # 业务错误本身是给用户看的，但只返回稳定消息，不带内部 details。
            return {"error": exc.message, "error_code": exc.code.value}
        except Exception:  # noqa: BLE001  内部异常不能把 SQL/路径原文交给模型
            logger.exception("账本工具执行失败：%s", name)
            return {"error": "账本操作失败，请稍后再试", "error_code": "internal_error"}

    @tool(args_schema=ImportPreviewInput)
    async def ledger_import_preview(
        file_id: str,
        account_id: str = "",
        mapping: dict[str, str] | None = None,
        config: RunnableConfig = None,
    ) -> dict[str, Any]:
        """解析已上传账单并返回预览/差异/控制总额；绝不提交。"""
        result = await _call(
            TOOL_IMPORT_PREVIEW,
            {"file_id": file_id, "account_id": account_id, "mapping": mapping},
            config,
        )
        if "error" not in result:
            import_data = result.get("import") or {}
            import_id = str(import_data.get("import_id") or "")
            result["message"] = (
                f"预览好了。回复 /账单确认 {import_id} 提交；"
                "有差异时先核对控制总额。"
            )
        return result

    @tool(args_schema=AnalyzeInput)
    async def ledger_analyze(
        plan: dict[str, Any], request_id: str = "", config: RunnableConfig = None
    ) -> dict[str, Any]:
        """按 QueryPlan 统计账单；返回最多 3 组结论，不贴全表。"""
        result = await _call(TOOL_ANALYZE, {"plan": plan, "request_id": request_id}, config)
        if "error" not in result:
            metrics = list(result.get("metrics") or [])
            result["conclusion_lines"] = [
                f"{m['name']}：{m.get('amount_text', '—')}" for m in metrics[:3]
            ]
            result["groups"] = (result.get("groups") or [])[:3]
        return result

    @tool(args_schema=CorrectInput)
    async def ledger_correct_transaction(
        transaction_id: str,
        category_id: str = "",
        merchant: str = "",
        note: str = "",
        reason: str = "对话修正",
        config: RunnableConfig = None,
    ) -> dict[str, Any]:
        """用户明确要求修正时才调用；只改指定字段并写审计。"""
        return await _call(
            TOOL_CORRECT,
            {
                "transaction_id": transaction_id, "category_id": category_id,
                "merchant": merchant, "note": note, "reason": reason,
            },
            config,
        )

    @tool(args_schema=ReportInput)
    async def ledger_make_report(
        plan: dict[str, Any],
        format: str = "markdown",
        config: RunnableConfig = None,
    ) -> dict[str, Any]:
        """生成报告文件，返回 Web 下载入口；微信不承诺发文件。"""
        result = await _call(TOOL_REPORT, {"plan": plan, "format": format}, config)
        if "error" not in result:
            result["message"] = "报告已生成，在 Web 账本页下载。"
        return result

    @tool(args_schema=RefundInput)
    async def ledger_refund_suggestions(
        import_id: str = "", config: RunnableConfig = None
    ) -> dict[str, Any]:
        """列出最多 3 条退款候选；关联/确认只在 Web 完成。"""
        result = await _call(TOOL_REFUND_SUGGEST, {"import_id": import_id}, config)
        if "error" not in result:
            result["suggestions"] = (result.get("suggestions") or [])[:3]
        return result

    tools = [
        ledger_import_preview, ledger_analyze, ledger_correct_transaction,
        ledger_make_report, ledger_refund_suggestions,
    ]
    for item in tools:
        item._toolset = "__always_available__"
    return tools
