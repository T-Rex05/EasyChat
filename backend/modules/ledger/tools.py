"""账本工具面（给运行时/LLM 调用的受控入口）。

原则：
- 工具参数只接受“结构化 ID / QueryPlan”，不接受 SQL、脚本或任意路径；
- 金额、去重、退款匹配全部由 `LedgerService` 用受控代码计算，工具只做转发；
- 提交账单必须由用户显式确认，**不**作为模型可调用的工具暴露。
"""
from __future__ import annotations

from typing import Any, Mapping

from backend.modules.ledger.api import LedgerService
from backend.modules.ledger.intent import (
    INTENT_IMPORT,
    IntentDecision,
    plan_from_text,
    route,
)
from backend.shared.errors import InvalidInputError

TOOL_IMPORT_PREVIEW = "ledger_import_preview"
TOOL_ANALYZE = "ledger_analyze"
TOOL_CORRECT = "ledger_correct_transaction"
TOOL_REPORT = "ledger_make_report"
TOOL_REFUND_SUGGEST = "ledger_refund_suggestions"

TOOL_NAMES = (
    TOOL_IMPORT_PREVIEW, TOOL_ANALYZE, TOOL_CORRECT, TOOL_REPORT, TOOL_REFUND_SUGGEST,
)

_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "受控查询计划；不接受 SQL/脚本字段",
    "required": ["version", "basis", "metrics", "period"],
    "properties": {
        "version": {"type": "integer", "enum": [1]},
        "basis": {
            "type": "string",
            "enum": ["statement_flow", "consumption_net", "period_cash_outflow"],
        },
        "metrics": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["expense", "income", "neutral", "refund_received", "net"],
            },
        },
        "period": {
            "type": "object",
            "required": ["start", "end_exclusive"],
            "properties": {
                "start": {"type": "string"},
                "end_exclusive": {"type": "string"},
            },
        },
        "group_by": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["month", "day", "category", "merchant", "account"],
            },
        },
        "top_n": {"type": "integer", "minimum": 1, "maximum": 200},
        "output": {"type": "string", "enum": ["summary", "table", "chart", "pdf"]},
    },
}

TOOL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": TOOL_IMPORT_PREVIEW,
        "description": "解析已上传的账单文件并返回预览与差异（不做提交）",
        "parameters": {
            "type": "object",
            "required": ["file_id"],
            "properties": {
                "file_id": {"type": "string"},
                "account_id": {"type": "string"},
                "mapping": {"type": "object"},
            },
        },
    },
    {
        "name": TOOL_ANALYZE,
        "description": "按 QueryPlan 统计账单（金额由服务端计算）",
        "parameters": {
            "type": "object",
            "required": ["plan"],
            "properties": {"plan": _PLAN_SCHEMA, "request_id": {"type": "string"}},
        },
    },
    {
        "name": TOOL_CORRECT,
        "description": "修正单笔交易的分类/商户/备注（写审计）",
        "parameters": {
            "type": "object",
            "required": ["transaction_id"],
            "properties": {
                "transaction_id": {"type": "string"},
                "category_id": {"type": "string"},
                "merchant": {"type": "string"},
                "note": {"type": "string"},
                "reason": {"type": "string"},
            },
        },
    },
    {
        "name": TOOL_REPORT,
        "description": "生成账单报告文件（markdown/csv），返回可下载 file_id",
        "parameters": {
            "type": "object",
            "required": ["plan"],
            "properties": {
                "plan": _PLAN_SCHEMA,
                "format": {"type": "string", "enum": ["markdown", "csv"]},
            },
        },
    },
    {
        "name": TOOL_REFUND_SUGGEST,
        "description": "列出待核对的退款候选（只建议，不自动改账）",
        "parameters": {
            "type": "object",
            "properties": {"import_id": {"type": "string"}},
        },
    },
)


class LedgerToolbox:
    def __init__(self, service: LedgerService) -> None:
        self.service = service

    def specs(self) -> list[dict[str, Any]]:
        return [dict(spec) for spec in TOOL_SPECS]

    async def call(
        self, principal, name: str, arguments: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if name not in TOOL_NAMES:
            raise InvalidInputError(f"未知工具: {name}")
        args = dict(arguments or {})
        if name == TOOL_IMPORT_PREVIEW:
            return await self._import_preview(principal, args)
        if name == TOOL_ANALYZE:
            return self._analyze(principal, args)
        if name == TOOL_CORRECT:
            return self._correct(principal, args)
        if name == TOOL_REPORT:
            return await self._report(principal, args)
        return self._refund_suggestions(principal, args)

    async def _import_preview(self, principal, args: Mapping[str, Any]) -> dict[str, Any]:
        file_id = str(args.get("file_id") or "").strip()
        if not file_id:
            raise InvalidInputError("缺少 file_id")
        mapping = args.get("mapping")
        if mapping is not None and not isinstance(mapping, Mapping):
            raise InvalidInputError("mapping 必须是对象")
        view = await self.service.register_import(
            principal, file_id, account_id=str(args.get("account_id") or ""),
            mapping=dict(mapping) if mapping else None, parse_now=True,
        )
        summary = self.service.import_summary(principal, view.import_id)
        summary["import"] = {
            "import_id": view.import_id, "state": view.state,
            "coverage_kind": view.coverage_kind, "quality": view.quality,
        }
        summary["requires_user_confirmation"] = True
        summary["next_step"] = "confirm_commit"
        return summary

    def _analyze(self, principal, args: Mapping[str, Any]) -> dict[str, Any]:
        plan = args.get("plan")
        if not isinstance(plan, Mapping):
            raise InvalidInputError("plan 必须是对象")
        result = self.service.analyze(
            principal, plan, request_id=str(args.get("request_id") or ""),
        )
        return {
            "analysis_id": result.analysis_id,
            "basis": result.basis,
            "currency": result.currency,
            "metrics": [
                {"name": m.name, "amount_minor": m.amount_minor} for m in result.metrics
            ],
            "groups": list(result.groups),
            "coverage": {
                "coverage_kind": result.coverage.coverage_kind,
                "start": result.coverage.start,
                "end_exclusive": result.coverage.end_exclusive,
                "notes": list(result.coverage.notes),
            },
            "warnings": list(result.warnings),
            "evidence": list(result.evidence),
        }

    def _correct(self, principal, args: Mapping[str, Any]) -> dict[str, Any]:
        transaction_id = str(args.get("transaction_id") or "").strip()
        if not transaction_id:
            raise InvalidInputError("缺少 transaction_id")
        detail = self.service.update_transaction(
            principal, transaction_id,
            category_id=args.get("category_id"),
            merchant=args.get("merchant"),
            note=args.get("note"),
            reason=str(args.get("reason") or "对话修正"),
        )
        return {
            "transaction": {
                "transaction_id": detail["transaction"].transaction_id,
                "amount_minor": detail["transaction"].amount_minor,
                "category_id": detail["transaction"].category_id,
                "merchant": detail["transaction"].merchant,
                "revision": detail["transaction"].revision,
            },
        }

    async def _report(self, principal, args: Mapping[str, Any]) -> dict[str, Any]:
        plan = args.get("plan")
        if not isinstance(plan, Mapping):
            raise InvalidInputError("plan 必须是对象")
        return await self.service.create_report(
            principal, plan, fmt=str(args.get("format") or "markdown"),
        )

    def _refund_suggestions(self, principal, args: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "suggestions": self.service.suggest_refunds(
                principal, import_id=str(args.get("import_id") or ""),
            ),
        }


async def handle_message(
    service: LedgerService,
    principal,
    text: str,
    *,
    file_ids: tuple[str, ...] = (),
    planner=None,
    transaction_id: str = "",
    corrections: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """意图路由 + 执行：返回可直接给用户/模型的结果（金额均来自服务端计算）。"""
    decision: IntentDecision = await route(
        service, principal, text, file_ids=file_ids, planner=planner,
    )
    toolbox = LedgerToolbox(service)
    if decision.intent == INTENT_IMPORT:
        if not file_ids:
            return {
                "intent": decision.intent, "needs_input": "file",
                "message": "请先上传要导入的微信账单文件（xlsx/csv/截图）。",
            }
        previews = [
            await toolbox.call(principal, TOOL_IMPORT_PREVIEW, {"file_id": file_id})
            for file_id in file_ids
        ]
        return {
            "intent": decision.intent, "previews": previews,
            "message": "账单已解析，请核对控制总额后再确认提交。",
        }
    if decision.intent == "review_refund":
        return {
            "intent": decision.intent,
            "suggestions": service.suggest_refunds(principal),
            "message": "以下退款候选需要你确认后才会影响净额。",
        }
    if decision.intent == "correct":
        if not transaction_id or not corrections:
            return {
                "intent": decision.intent, "needs_input": "transaction",
                "message": "请指定要修正的交易与目标字段（分类/商户/备注）。",
            }
        return {
            "intent": decision.intent,
            "result": await toolbox.call(
                principal, TOOL_CORRECT,
                {"transaction_id": transaction_id, **dict(corrections)},
            ),
        }
    if decision.intent == "report":
        plan = decision.plan or plan_from_text(
            text, now=service.now(), timezone=service.timezone,
        )
        return {
            "intent": decision.intent,
            "report": await toolbox.call(principal, TOOL_REPORT, {"plan": plan}),
        }
    if decision.intent == "analyze":
        return {
            "intent": decision.intent,
            "result": toolbox._analyze(principal, {"plan": decision.plan}),  # noqa: SLF001
        }
    return {
        "intent": decision.intent, "needs_clarification": True,
        "message": decision.question,
    }
