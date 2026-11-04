"""ledger HTTP 路由：薄适配层，规则/权限/计算全部在 LedgerService。

- 不在这里拼 SQL、不在这里做金额/去重/退款判断；
- 模型不会经由这些路由执行任意查询：/analyze 只接受结构化 QueryPlan；
- 图片识别候选只接收视觉 Adapter 的结构化结果，不接收任意文件路径。
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel

from backend.modules.ledger.api import LedgerService
from backend.modules.ledger.contracts import AnalysisResult, ImportView, TransactionView
from backend.shared.errors import UnauthenticatedError


class AccountBody(BaseModel):
    provider: str = "wechat"
    account_alias: str = ""
    currency: str = "CNY"


class ImportBody(BaseModel):
    file_id: str
    account_id: str = ""
    account_alias: str = ""
    mapping: dict[str, str] | None = None


class CommitBody(BaseModel):
    request_id: str = ""
    confirm_mismatch: bool = False


class TransactionPatch(BaseModel):
    category_id: str | None = None
    merchant: str | None = None
    product: str | None = None
    note: str | None = None
    reason: str = ""


class CategoryBody(BaseModel):
    name: str
    kind: str = "expense"


class RenameBody(BaseModel):
    name: str


class RuleBody(BaseModel):
    category_id: str
    match_value: str
    match_field: str = "merchant"
    match_op: str = "contains"
    priority: int = 100


class RefundLinkBody(BaseModel):
    refund_transaction_id: str
    original_transaction_id: str
    amount_minor: int | None = None
    confirmation: str = "confirmed"


class AnalyzeBody(BaseModel):
    plan: dict[str, Any]
    request_id: str = ""


class CandidateConfirmBody(BaseModel):
    corrections: dict[str, str] | None = None


class ReportBody(BaseModel):
    plan: dict[str, Any]
    format: str = "markdown"


def _import_payload(view: ImportView) -> dict[str, Any]:
    return asdict(view)


def _transaction_payload(view: TransactionView) -> dict[str, Any]:
    return asdict(view)


def _analysis_payload(result: AnalysisResult) -> dict[str, Any]:
    return {
        "analysis_id": result.analysis_id,
        "basis": result.basis,
        "currency": result.currency,
        "metrics": [asdict(m) for m in result.metrics],
        "coverage": asdict(result.coverage),
        "groups": list(result.groups),
        "transactions": [_transaction_payload(t) for t in result.transactions],
        "warnings": list(result.warnings),
        "data_cutoff": result.data_cutoff,
        "snapshot_revision": result.snapshot_revision,
        "evidence": list(result.evidence),
        "plan": {
            "version": result.plan.version, "basis": result.plan.basis,
            "metrics": list(result.plan.metrics), "scope": result.plan.scope,
            "period": asdict(result.plan.period),
            "group_by": list(result.plan.group_by),
            "output": result.plan.output, "top_n": result.plan.top_n,
        },
    }


def build_ledger_router(service: LedgerService, authenticate: Any) -> APIRouter:
    def _principal(authorization: str | None):
        token = (authorization or "").replace("Bearer ", "").strip()
        if not token:
            raise UnauthenticatedError("请先登录")
        return authenticate(token)

    router = APIRouter(prefix="/api/ledger", tags=["ledger"])

    # ---- 账户 ----------------------------------------------------------------

    @router.get("/accounts")
    async def list_accounts(
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return {"accounts": service.list_accounts(principal)}

    @router.post("/accounts")
    async def create_account(
        body: AccountBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.create_account(
            principal, provider=body.provider, account_alias=body.account_alias,
            currency=body.currency,
        )

    # ---- 导入 ----------------------------------------------------------------

    @router.post("/imports")
    async def register_import(
        body: ImportBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        view = await service.register_import(
            principal, body.file_id, account_id=body.account_id,
            account_alias=body.account_alias, mapping=body.mapping,
        )
        return {"import": _import_payload(view)}

    @router.get("/imports")
    async def list_imports(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        state: str | None = Query(default=None),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        views = service.list_imports(principal, limit=limit, offset=offset, state=state)
        return {"imports": [_import_payload(v) for v in views]}

    @router.get("/imports/{import_id}")
    async def get_import(
        import_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return {"import": _import_payload(service.get_import(principal, import_id))}

    @router.get("/imports/{import_id}/summary")
    async def import_summary(
        import_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        summary = service.import_summary(principal, import_id)
        summary["import"] = _import_payload(summary["import"])
        return summary

    @router.get("/imports/{import_id}/rows")
    async def import_rows(
        import_id: str,
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        parse_state: str | None = Query(default=None),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        rows = service.list_source_rows(
            principal, import_id, limit=limit, offset=offset, parse_state=parse_state,
        )
        return {"rows": rows}

    @router.post("/imports/{import_id}/parse")
    async def parse_import(
        import_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        service.get_import(principal, import_id)
        return {"import": _import_payload(await service.parse_import(import_id))}

    @router.post("/imports/{import_id}/commit")
    async def commit_import(
        import_id: str,
        body: CommitBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        result = service.commit_import(
            principal, import_id, request_id=body.request_id,
            confirm_mismatch=body.confirm_mismatch,
        )
        return asdict(result)

    @router.delete("/imports/{import_id}")
    async def delete_import(
        import_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.delete_import(principal, import_id)

    # ---- 交易 ----------------------------------------------------------------

    @router.get("/transactions")
    async def list_transactions(
        start: str | None = Query(default=None),
        end: str | None = Query(default=None),
        category_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        views = service.list_transactions(
            principal, start=start, end=end, category_id=category_id,
            limit=limit, offset=offset,
        )
        return {"transactions": [_transaction_payload(v) for v in views]}

    @router.get("/transactions/{transaction_id}")
    async def get_transaction(
        transaction_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        detail = service.get_transaction(principal, transaction_id)
        detail["transaction"] = _transaction_payload(detail["transaction"])
        return detail

    @router.patch("/transactions/{transaction_id}")
    async def patch_transaction(
        transaction_id: str,
        body: TransactionPatch,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        detail = service.update_transaction(
            principal, transaction_id, category_id=body.category_id,
            merchant=body.merchant, product=body.product, note=body.note,
            reason=body.reason,
        )
        detail["transaction"] = _transaction_payload(detail["transaction"])
        return detail

    @router.delete("/transactions/{transaction_id}")
    async def delete_transaction(
        transaction_id: str,
        reason: str = Query(default=""),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.delete_transaction(principal, transaction_id, reason=reason)

    # ---- 分类与规则 ------------------------------------------------------------

    @router.get("/categories")
    async def list_categories(
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return {"categories": service.list_categories(principal)}

    @router.post("/categories")
    async def create_category(
        body: CategoryBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.create_category(principal, name=body.name, kind=body.kind)

    @router.patch("/categories/{category_id}")
    async def rename_category(
        category_id: str,
        body: RenameBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.rename_category(principal, category_id, name=body.name)

    @router.delete("/categories/{category_id}")
    async def delete_category(
        category_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.delete_category(principal, category_id)

    @router.get("/rules")
    async def list_rules(
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return {"rules": service.list_rules(principal)}

    @router.post("/rules")
    async def create_rule(
        body: RuleBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.create_rule(
            principal, category_id=body.category_id, match_value=body.match_value,
            match_field=body.match_field, match_op=body.match_op, priority=body.priority,
        )

    @router.delete("/rules/{rule_id}")
    async def delete_rule(
        rule_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.delete_rule(principal, rule_id)

    @router.post("/rules/apply")
    async def apply_rules(
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.apply_rules(principal)

    # ---- 退款 ----------------------------------------------------------------

    @router.get("/refunds")
    async def list_refunds(
        limit: int = Query(default=100, ge=1, le=500),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        result = service.list_refunds(principal, limit=limit)
        result["links"] = [
            {
                "link": item["link"],
                "refund": _transaction_payload(item["refund"]),
                "original": _transaction_payload(item["original"]),
                "remaining_minor": item["remaining_minor"],
            }
            for item in result["links"]
        ]
        return result

    @router.get("/refunds/suggestions")
    async def refund_suggestions(
        import_id: str = Query(default=""),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return {"suggestions": service.suggest_refunds(principal, import_id=import_id)}

    @router.post("/refunds/links")
    async def link_refund(
        body: RefundLinkBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.link_refund(
            principal, refund_transaction_id=body.refund_transaction_id,
            original_transaction_id=body.original_transaction_id,
            amount_minor=body.amount_minor, confirmation=body.confirmation,
        )

    @router.post("/refunds/links/{link_id}/confirm")
    async def confirm_refund(
        link_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.confirm_refund_link(principal, link_id)

    @router.delete("/refunds/links/{link_id}")
    async def unlink_refund(
        link_id: str,
        reason: str = Query(default=""),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.unlink_refund(principal, link_id, reason=reason)

    # ---- 统计 ------------------------------------------------------------------

    @router.post("/analyze")
    async def analyze(
        body: AnalyzeBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        result = service.analyze(principal, body.plan, request_id=body.request_id)
        return _analysis_payload(result)

    @router.post("/reports")
    async def create_report(
        body: ReportBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return await service.create_report(principal, body.plan, fmt=body.format)

    @router.get("/analyses")
    async def list_analyses(
        limit: int = Query(default=50, ge=1, le=200),
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return {"analyses": service.list_analyses(principal, limit=limit)}

    @router.get("/analyses/{analysis_id}")
    async def get_analysis(
        analysis_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        return service.get_analysis(principal, analysis_id)

    # ---- 图片候选 ---------------------------------------------------------------

    @router.post("/images/{file_id}/candidates")
    async def create_candidate(
        file_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ):
        """服务端识别：客户端只给 file_id，不能自报金额/置信度。"""
        principal = _principal(authorization)
        return await service.extract_image_candidate(principal, file_id)

    @router.post("/candidates/{extraction_id}/confirm")
    async def confirm_candidate(
        extraction_id: str,
        body: CandidateConfirmBody,
        authorization: Annotated[str | None, Header()] = None,
    ):
        principal = _principal(authorization)
        detail = service.confirm_image_candidate(
            principal, extraction_id, corrections=body.corrections,
        )
        detail["transaction"] = _transaction_payload(detail["transaction"])
        return detail

    return router
