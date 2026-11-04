"""账本服务：导入状态机、去重提交、退款核对、受控统计与图片候选。

边界（设计 §4/§10）：
- 只有本模块写 ledger_* 表；routes/LLM 工具只调用本服务；
- 统计/去重/退款/对账全部由确定性代码计算，模型只负责意图与解释；
- 模型永远不生成 SQL/Python：查询走 QueryPlan 验证 + 参数化编译；
- 原件与解析产物归 files 模块，账本只存业务引用。
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from backend.modules.access.api import AccessService
from backend.modules.files.api import FileService
from backend.modules.files.contracts import KIND_IMAGE
from backend.modules.ledger.contracts import (
    BASIS_CONSUMPTION_NET,
    BASIS_PERIOD_CASH_OUTFLOW,
    BASIS_STATEMENT_FLOW,
    COVERAGE_COMPLETE,
    COVERAGE_OVERLAPPING,
    COVERAGE_PARTIAL,
    DIRECTION_EXPENSE,
    DIRECTION_INCOME,
    DIRECTION_NEUTRAL,
    EVENT_ROLE_PAYMENT,
    EVENT_ROLE_REFUND,
    GROUP_BY_CATEGORY,
    IMPORT_COMMITTED,
    IMPORT_FAILED,
    IMPORT_NEEDS_REVIEW,
    IMPORT_PARSING,
    IMPORT_SAVED,
    IMPORT_VALIDATED,
    METRIC_EXPENSE,
    METRIC_INCOME,
    METRIC_NET,
    METRIC_NEUTRAL,
    METRIC_REFUND_RECEIVED,
    AnalysisResult,
    CommitResult,
    Coverage,
    ImageCandidate,
    ImportView,
    MetricResult,
    ParsedRow,
    Period,
    QueryPlan,
    RefundSuggestion,
    TransactionView,
)
from backend.modules.ledger import identity as identity_rules
from backend.modules.ledger import refunds as refund_rules
from backend.modules.ledger.extraction import (
    apply_corrections,
    candidate_from_vision,
    candidate_payload,
    is_ready_for_confirmation,
)
from backend.modules.ledger.normalization import (
    classify_event_role,
    clean_text,
    fingerprint,
    format_money,
    normalize_external_id,
    parse_control_totals,
    parse_money,
    parse_occurred_at,
    status_key,
)
from backend.modules.ledger.parsers import ParseOptions, detect_format, parse_saved_file
from backend.modules.ledger.query import CompiledQuery, compile_plan, validate_plan
from backend.modules.ledger.repository import LedgerRepository
from backend.platform.jobs import JobQueue
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.context import Principal
from backend.shared.errors import InvalidInputError, NotFoundError
from backend.shared.identifiers import new_extraction_id

logger = logging.getLogger(__name__)

PARSER_VERSION = "1"
PARSE_JOB_KIND = "ledger.parse"
DEFAULT_TIMEZONE = "Asia/Shanghai"
MAX_COMMIT_ROWS = 100_000
IMAGE_EXTRACTOR = "vision.candidate"
IMAGE_EXTRACTOR_VERSION = "1"


@dataclass(frozen=True, slots=True)
class _Control:
    ok: bool
    checked: bool
    mismatches: tuple[str, ...]
    detail: Mapping[str, Any]


def _import_view(row: Mapping[str, Any]) -> ImportView:
    return ImportView(
        import_id=str(row["id"]),
        owner_id=int(row["owner_id"]),
        account_id=str(row["account_id"]),
        file_id=str(row["file_id"]),
        parser=str(row.get("parser") or ""),
        parser_version=str(row.get("parser_version") or ""),
        state=str(row.get("state") or ""),
        declared_from=row.get("declared_from"),
        declared_to=row.get("declared_to"),
        coverage_kind=str(row.get("coverage_kind") or "unknown"),
        currency=str(row.get("currency") or "CNY"),
        revision=int(row.get("revision") or 1),
        row_counts=row.get("row_counts") or {},
        control_totals=row.get("control_totals") or {},
        quality=row.get("quality") or {},
        error=row.get("error"),
    )


def _transaction_view(row: Mapping[str, Any]) -> TransactionView:
    return TransactionView(
        transaction_id=str(row["id"]),
        owner_id=int(row["owner_id"]),
        account_id=str(row["account_id"]),
        external_id=str(row.get("external_id") or ""),
        event_role=str(row.get("event_role") or EVENT_ROLE_PAYMENT),
        amount_minor=int(row.get("amount_minor") or 0),
        currency=str(row.get("currency") or "CNY"),
        direction=str(row.get("direction") or "unknown"),
        tx_type=str(row.get("tx_type") or ""),
        merchant=str(row.get("merchant") or ""),
        product=str(row.get("product") or ""),
        occurred_at=str(row.get("occurred_at") or ""),
        status=str(row.get("status") or ""),
        status_key=str(row.get("status_key") or "unknown"),
        category_id=row.get("category_id"),
        verification=str(row.get("verification") or "parsed"),
        revision=int(row.get("revision") or 1),
    )


def _parsed_from_row(row: Mapping[str, Any]) -> ParsedRow:
    return ParsedRow(
        sheet=str(row.get("sheet") or ""),
        row_number=int(row.get("row_number") or 0),
        locator=str(row.get("locator") or ""),
        raw=row.get("raw_fields") or {},
        occurred_at=row.get("occurred_at"),
        amount_minor=row.get("amount_minor"),
        direction=str(row.get("direction") or "unknown"),
        currency=str(row.get("currency") or "CNY"),
        tx_type=str(row.get("tx_type") or ""),
        counterparty=str(row.get("merchant") or ""),
        product=str(row.get("product") or ""),
        status=str(row.get("status") or ""),
        external_id=str(row.get("external_id") or ""),
        merchant_id=str(row.get("merchant_id") or ""),
        note=str(row.get("note") or ""),
        pay_method=str(row.get("pay_method") or ""),
        event_role=str(row.get("event_role") or EVENT_ROLE_PAYMENT),
        id_reliable=bool(row.get("id_reliable")),
        errors=tuple(row.get("errors") or ()),
    )


class LedgerService:
    def __init__(
        self,
        db: Database,
        *,
        access: AccessService,
        files: FileService,
        queue: JobQueue | None = None,
        timezone: str = DEFAULT_TIMEZONE,
        max_rows: int = MAX_COMMIT_ROWS,
        clock=None,
    ) -> None:
        self.db = db
        self.repo = LedgerRepository(db)
        self.access = access
        self.files = files
        self.queue = queue
        self.timezone = timezone
        self.max_rows = max_rows
        self.clock = clock or (lambda: None)

    # ---- 权限与取数 ----------------------------------------------------------------

    def _principal(self, principal: Principal, permission: str) -> Principal:
        principal = self.access.validate_principal(principal)
        self.access.require_permission(principal, permission)
        return principal

    def _owner_account(self, principal: Principal, account_id: str) -> dict[str, Any]:
        return self.repo.get_account(account_id, owner_id=principal.user_id)

    def _owner_import(self, principal: Principal, import_id: str) -> dict[str, Any]:
        return self.repo.get_import(import_id, owner_id=principal.user_id)

    def _record(
        self, principal: Principal, *, entity: str, entity_id: str, revision: int,
        change: Mapping[str, Any], reason: str = "",
    ) -> None:
        self.repo.record_change(
            owner_id=principal.user_id, actor_id=principal.user_id, entity=entity,
            entity_id=entity_id, revision=revision, change=change, reason=reason,
        )

    # ---- 账户 ------------------------------------------------------------------

    def create_account(
        self, principal: Principal, *, provider: str = "wechat", account_alias: str = "",
        currency: str = "CNY",
    ) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.manage")
        if not provider or len(provider) > 40:
            raise InvalidInputError("账户来源不合法")
        row = self.repo.ensure_account(
            owner_id=principal.user_id, provider=provider,
            account_alias=clean_text(account_alias, limit=60), currency=currency,
            timezone=self.timezone,
        )
        return row

    def list_accounts(self, principal: Principal) -> list[dict[str, Any]]:
        principal = self._principal(principal, "ledger.view")
        return self.repo.list_accounts(principal.user_id)

    # ---- 导入：登记 ------------------------------------------------------------------

    async def register_import(
        self,
        principal: Principal,
        file_id: str,
        *,
        account_id: str = "",
        account_alias: str = "",
        mapping: Mapping[str, str] | None = None,
        parse_now: bool | None = None,
    ) -> ImportView:
        principal = self._principal(principal, "ledger.import")
        record = self.files.get(principal, file_id)
        if record.kind == KIND_IMAGE:
            raise InvalidInputError("图片请走截图识别候选流程，不能作为账单文件导入")
        if record.status != "ready":
            raise InvalidInputError("文件尚未就绪，稍后再试")
        if account_id:
            account = self._owner_account(principal, account_id)
        else:
            account = self.repo.ensure_account(
                owner_id=principal.user_id, provider=_provider_of(record.original_name),
                account_alias=clean_text(account_alias, limit=60) or "默认账户",
                currency="CNY", timezone=self.timezone,
            )
        import_id, created = self.repo.create_import(
            owner_id=principal.user_id, account_id=str(account["id"]), file_id=file_id,
            parser="auto", parser_version=PARSER_VERSION, state=IMPORT_SAVED,
            currency="CNY",
        )
        row = self.repo.get_import(import_id, owner_id=principal.user_id)
        if created and mapping:
            self.repo.update_import(import_id, quality={"mapping": dict(mapping)})
        state = str(row["state"])
        pending = state in (IMPORT_SAVED, IMPORT_PARSING, IMPORT_FAILED)
        should_parse = parse_now if parse_now is not None else self.queue is None
        if should_parse and (created or pending):
            await self.parse_import(import_id)
        elif created:
            self._enqueue_parse(import_id)
        return _import_view(self.repo.get_import(import_id, owner_id=principal.user_id))

    def _enqueue_parse(self, import_id: str) -> None:
        if self.queue is None:
            return
        self.queue.enqueue(
            kind=PARSE_JOB_KIND,
            dedup_key=f"{PARSE_JOB_KIND}:{import_id}",
            payload={"import_id": import_id},
            owner_id=None,
            max_attempts=3,
        )

    async def parse_import(self, import_id: str) -> ImportView:
        """解析已登记文件：状态机 parsing → needs_review/validated/failed。

        可重入：重复解析会替换本批次的标准化行，不影响其他批次。
        """
        row = self.repo.get_import(import_id)
        owner_id = int(row["owner_id"])
        principal = self.access.snapshot_principal(owner_id)
        if not self.access.has_permission(principal, "ledger.import"):
            self.repo.update_import(import_id, state=IMPORT_FAILED, error="权限已撤销，无法导入")
            raise InvalidInputError("权限已撤销，无法导入")
        self.repo.update_import(import_id, state=IMPORT_PARSING, error=None)
        try:
            file_record = self.files.get(principal, str(row["file_id"]))
            path = self.files.internal_path(principal, file_record.file_id)
            head = self.files.read_head(principal, file_record.file_id, 65536)
            sample_text = _decode_head(head)
            match = detect_format(
                file_name=file_record.original_name, mime=file_record.verified_mime,
                head=head, sample_text=sample_text,
            )
            mapping = _mapping_from_quality(row.get("quality"))
            options = ParseOptions(
                timezone=self.timezone, default_currency=str(row.get("currency") or "CNY"),
                max_rows=self.max_rows, mapping=mapping,
            )
            statement = parse_saved_file(
                path, file_name=file_record.original_name,
                mime=file_record.verified_mime, options=options,
            )
        except Exception as exc:  # noqa: BLE001  解析失败必须落状态，不能静默
            logger.warning("账单解析失败 import=%s: %s", import_id, exc)
            self.repo.update_import(
                import_id, state=IMPORT_FAILED, error=str(exc)[:500],
                row_counts={"rows": 0},
            )
            return _import_view(self.repo.get_import(import_id, owner_id=owner_id))

        self.repo.delete_source_rows(import_id)
        source_rows = [_row_payload(parsed) for parsed in statement.rows]
        if source_rows:
            self.repo.add_source_rows(
                import_id=import_id, owner_id=owner_id, rows=source_rows,
            )
        control = _check_control(statement)
        overlapping = self.repo.overlapping_imports(
            owner_id=owner_id, start=statement.declared_from, end=statement.declared_to,
            exclude_import_id=import_id,
        )
        coverage = _coverage_kind(statement, control, overlapping)
        errors = sum(1 for parsed in statement.rows if parsed.errors)
        quality = {
            "control": {"ok": control.ok, "checked": control.checked,
                        "mismatches": list(control.mismatches),
                        "detail": dict(control.detail)},
            "warnings": list(statement.warnings),
            "truncated": statement.truncated,
            "error_rows": errors,
            "overlapping_imports": [str(item["id"]) for item in overlapping],
        }
        mapping_now = mapping or match.mapping
        if mapping_now is not None:
            quality["mapping"] = mapping_now.as_dict()
        state = IMPORT_VALIDATED
        if errors or not control.ok or statement.truncated:
            state = IMPORT_NEEDS_REVIEW
        self.repo.update_import(
            import_id,
            parser=match.format, parser_version=match.version, state=state,
            declared_from=statement.declared_from, declared_to=statement.declared_to,
            coverage_kind=coverage, currency=statement.currency,
            control_totals={
                "count": statement.control_totals.count,
                "income_minor": statement.control_totals.income_minor,
                "expense_minor": statement.control_totals.expense_minor,
                "neutral_minor": statement.control_totals.neutral_minor,
                "checked": control.checked,
            },
            row_counts={
                "rows": len(statement.rows), "errors": errors,
                "expense_minor": sum(
                    r.amount_minor or 0 for r in statement.rows
                    if r.direction == DIRECTION_EXPENSE and not r.errors
                ),
                "income_minor": sum(
                    r.amount_minor or 0 for r in statement.rows
                    if r.direction == DIRECTION_INCOME and not r.errors
                ),
            },
            quality=quality,
        )
        return _import_view(self.repo.get_import(import_id, owner_id=owner_id))

    def get_import(self, principal: Principal, import_id: str) -> ImportView:
        principal = self._principal(principal, "ledger.view")
        return _import_view(self._owner_import(principal, import_id))

    def list_source_rows(
        self, principal: Principal, import_id: str, *, limit: int = 200, offset: int = 0,
        parse_state: str | None = None,
    ) -> list[dict[str, Any]]:
        principal = self._principal(principal, "ledger.view")
        self._owner_import(principal, import_id)
        return self.repo.list_source_rows(
            import_id, limit=min(max(1, limit), 1000), offset=max(0, offset),
            parse_state=parse_state,
        )

    def list_imports(
        self, principal: Principal, *, limit: int = 50, offset: int = 0, state: str | None = None
    ) -> list[ImportView]:
        principal = self._principal(principal, "ledger.view")
        rows = self.repo.list_imports(principal.user_id, limit=limit, offset=offset, state=state)
        return [_import_view(row) for row in rows]

    def delete_import(self, principal: Principal, import_id: str) -> dict[str, Any]:
        """删除批次：清除来源行与未提交交易，已提交交易保留（由用户逐笔删除）。"""
        principal = self._principal(principal, "ledger.import")
        row = self._owner_import(principal, import_id)
        if row["state"] == IMPORT_COMMITTED:
            raise InvalidInputError("已提交批次不能直接删除；请逐笔撤回交易或删除附件")
        removed = self.repo.delete_source_rows(import_id)
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM ledger_imports WHERE id=? AND owner_id=?",
                (import_id, principal.user_id),
            )
        self.files.unlink(principal, str(row["file_id"]), "import", import_id)
        return {"import_id": import_id, "removed_rows": removed}

    def import_summary(self, principal: Principal, import_id: str) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.view")
        row = self._owner_import(principal, import_id)
        rows = self.repo.list_source_rows(import_id, limit=100_000)
        error_rows = [r for r in rows if r["parse_state"] != "ok"]
        duplicates = 0
        for source in rows:
            if source["parse_state"] != "ok":
                continue
            parsed = _parsed_from_row(source)
            key = identity_rules.identity_key(parsed, account_id=str(row["account_id"]))
            if self.repo.find_transaction(owner_id=principal.user_id, identity_key=key):
                duplicates += 1
        coverage = dict(row.get("quality") or {}).get("control") or {}
        return {
            "import": _import_view(row),
            "rows": len(rows),
            "error_rows": len(error_rows),
            "duplicate_rows": duplicates,
            "totals": {
                "expense_minor": sum(
                    int(r["amount_minor"] or 0) for r in rows
                    if r["parse_state"] == "ok" and r["direction"] == DIRECTION_EXPENSE
                ),
                "income_minor": sum(
                    int(r["amount_minor"] or 0) for r in rows
                    if r["parse_state"] == "ok" and r["direction"] == DIRECTION_INCOME
                ),
                "neutral_minor": sum(
                    int(r["amount_minor"] or 0) for r in rows
                    if r["parse_state"] == "ok"
                    and r["direction"] in (DIRECTION_NEUTRAL, "unknown")
                ),
                "refund_minor": sum(
                    int(r["amount_minor"] or 0) for r in rows
                    if r["parse_state"] == "ok" and r["event_role"] == EVENT_ROLE_REFUND
                ),
            },
            "control": coverage,
            "errors": [
                {"locator": r["locator"], "errors": r["errors"]} for r in error_rows[:50]
            ],
            "warnings": list((row.get("quality") or {}).get("warnings") or []),
        }

    # ---- 导入：提交 ------------------------------------------------------------------

    def commit_import(
        self,
        principal: Principal,
        import_id: str,
        *,
        request_id: str = "",
        confirm_mismatch: bool = False,
    ) -> CommitResult:
        principal = self._principal(principal, "ledger.import")
        row = self._owner_import(principal, import_id)
        state = str(row["state"])
        previous = (row.get("quality") or {}).get("commit") or {}
        if state == IMPORT_COMMITTED:
            if request_id and str(row.get("commit_request_id") or "") == request_id:
                return _commit_result(import_id, previous, duplicate=True)
            raise InvalidInputError("该批次已提交，如需重新导入请使用新文件")
        if state not in (IMPORT_VALIDATED, IMPORT_NEEDS_REVIEW):
            raise InvalidInputError(f"当前状态不能提交: {state}")
        control = (row.get("quality") or {}).get("control") or {}
        if control.get("checked") and not control.get("ok") and not confirm_mismatch:
            raise InvalidInputError(
                "账单控制总额与明细不一致，确认无误后才能提交"
                f"（{'; '.join(control.get('mismatches') or [])}）"
            )
        rows = self.repo.list_source_rows(import_id, limit=self.max_rows + 1)
        if len(rows) > self.max_rows:
            raise InvalidInputError("批次行数超过单次提交上限")
        account_id = str(row["account_id"])
        inserted = updated = unchanged = conflicts = skipped = 0
        refund_pairs: list[tuple[ParsedRow, str]] = []
        with self.db.transaction() as conn:
            for source in rows:
                if source["parse_state"] != "ok":
                    skipped += 1
                    continue
                parsed = _parsed_from_row(source)
                key = identity_rules.identity_key(parsed, account_id=account_id)
                existing = self.repo.find_transaction(
                    owner_id=principal.user_id, identity_key=key, conn=conn,
                )
                if existing is None:
                    verification = identity_rules.choose_identity(parsed, account_id=account_id)[1]
                    transaction_id = self.repo.insert_transaction(
                        owner_id=principal.user_id, account_id=account_id,
                        conn=conn,
                        transaction={
                            "identity_key": key,
                            "external_id": parsed.external_id,
                            "event_role": parsed.event_role,
                            "amount_minor": parsed.amount_minor,
                            "currency": parsed.currency,
                            "direction": parsed.direction,
                            "tx_type": parsed.tx_type,
                            "merchant": parsed.counterparty,
                            "product": parsed.product,
                            "occurred_at": parsed.occurred_at,
                            "status": parsed.status,
                            "status_key": status_key(parsed.status),
                            "verification": verification,
                        },
                    )
                    inserted += 1
                else:
                    transaction_id = str(existing["id"])
                    merged = identity_rules.merge_transaction(existing, parsed)
                    if merged:
                        self.repo.update_transaction(transaction_id, conn=conn, **merged)
                        updated += 1
                    else:
                        unchanged += 1
                    if identity_rules.status_transition(
                        str(existing.get("status_key") or ""), status_key(parsed.status),
                    ) == "conflict":
                        conflicts += 1
                self.repo.link_source(
                    owner_id=principal.user_id, transaction_id=transaction_id,
                    source_row_id=str(source["id"]), import_id=import_id,
                    status_observed=parsed.status, conn=conn,
                )
                if parsed.event_role == EVENT_ROLE_REFUND:
                    refund_pairs.append((parsed, transaction_id))
        suggestions = self._match_refunds(
            principal, account_id=account_id, refund_pairs=refund_pairs,
        )
        confirmed_links = sum(1 for item in suggestions if item.confirmation == "confirmed")
        summary = {
            "inserted": inserted, "updated": updated, "unchanged": unchanged,
            "conflicts": conflicts, "skipped": skipped,
            "refund_links": confirmed_links,
            "refund_suggestions": len(suggestions) - confirmed_links,
            "warnings": [],
        }
        quality = dict(row.get("quality") or {})
        quality["commit"] = summary
        self.repo.update_import(
            import_id, state=IMPORT_COMMITTED, commit_request_id=request_id,
            quality=quality, error=None,
            row_counts={
                **dict(row.get("row_counts") or {}),
                "imported": inserted + updated, "skipped": skipped,
            },
        )
        revision = self.repo.bump_import_revision(import_id)
        self._record(
            principal, entity="import", entity_id=import_id, revision=revision,
            change={"type": "commit", **summary}, reason="提交账单导入",
        )
        self.files.link(principal, str(row["file_id"]), "import", import_id)
        return _commit_result(import_id, summary)

    def _match_refunds(
        self, principal: Principal, *, account_id: str,
        refund_pairs: Sequence[tuple[ParsedRow, str]],
    ) -> list[RefundSuggestion]:
        """为本次提交的退款行匹配原支付；额度不足/多候选一律不落库。"""
        if not refund_pairs:
            return []
        start, end = _refund_candidate_window([row for row, _ in refund_pairs])
        candidates = self.repo.payment_candidates(
            principal.user_id, occurred_from=start, occurred_to=end,
        )
        suggestions = refund_rules.suggest_refund_links(
            [row for row, _ in refund_pairs], candidates,
        )
        reference_to_id = {
            refund_rules.refund_row_reference(row): transaction_id
            for row, transaction_id in refund_pairs
        }
        applied: list[RefundSuggestion] = []
        for suggestion in suggestions:
            refund_tx_id = reference_to_id.get(suggestion.refund_transaction_id)
            original = next(
                (c for c in candidates
                 if str(c["id"]) == suggestion.original_transaction_id), None,
            )
            if not refund_tx_id or original is None:
                continue
            existing = self.repo.links_for_original(
                str(original["id"]), owner_id=principal.user_id,
            )
            ok, _reason = refund_rules.validate_link(
                refund_amount_minor=suggestion.amount_minor,
                original_amount_minor=int(original["amount_minor"]),
                existing_amounts=[
                    int(link["amount_minor"]) for link in existing
                    if link["confirmation"] == "confirmed"
                    and str(link["refund_transaction_id"]) != refund_tx_id
                ],
            )
            if not ok:
                continue
            _link_id, created = self.repo.create_refund_link(
                owner_id=principal.user_id,
                refund_transaction_id=refund_tx_id,
                original_transaction_id=str(original["id"]),
                amount_minor=suggestion.amount_minor,
                match_method=suggestion.match_method,
                confirmation=suggestion.confirmation,
            )
            if created:
                applied.append(suggestion)
        return applied

    # ---- 交易 ------------------------------------------------------------------

    def list_transactions(
        self, principal: Principal, *, start: str | None = None, end: str | None = None,
        limit: int = 200, offset: int = 0, category_id: str | None = None,
    ) -> list[TransactionView]:
        principal = self._principal(principal, "ledger.view")
        rows = self.repo.list_transactions(
            principal.user_id, start=start, end=end, limit=limit, offset=offset,
            category_id=category_id,
        )
        return [_transaction_view(row) for row in rows]

    def get_transaction(self, principal: Principal, transaction_id: str) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.view")
        row = self.repo.get_transaction(transaction_id, owner_id=principal.user_id)
        sources = self.repo.sources_for_transaction(transaction_id, owner_id=principal.user_id)
        links = self.repo.links_for_refund(transaction_id, owner_id=principal.user_id)
        originals = self.repo.links_for_original(transaction_id, owner_id=principal.user_id)
        category = None
        if row.get("category_id"):
            try:
                category = self.repo.get_category(str(row["category_id"]), owner_id=principal.user_id)
            except NotFoundError:
                category = None
        return {
            "transaction": _transaction_view(row),
            "sources": sources,
            "refund_links": links,
            "original_links": originals,
            "category": category,
            "amount_text": format_money(int(row["amount_minor"]), str(row["currency"])),
        }

    def update_transaction(
        self, principal: Principal, transaction_id: str, *, category_id: str | None = None,
        merchant: str | None = None, product: str | None = None, note: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.edit")
        row = self.repo.get_transaction(transaction_id, owner_id=principal.user_id)
        updates: dict[str, Any] = {}
        if category_id is not None:
            if category_id:
                self.repo.get_category(category_id, owner_id=principal.user_id)
            updates["category_id"] = category_id or None
        if merchant is not None:
            updates["merchant"] = clean_text(merchant, limit=120)
        if product is not None:
            updates["product"] = clean_text(product, limit=200)
        if note is not None:
            updates["note"] = clean_text(note, limit=200)
        if not updates:
            raise InvalidInputError("没有需要修改的字段")
        self.repo.update_transaction(transaction_id, **updates)
        revision = int(row.get("revision") or 1) + 1
        self._record(
            principal, entity="transaction", entity_id=transaction_id, revision=revision,
            change={"before": {k: row.get(k) for k in updates}, "after": updates},
            reason=reason or "手工修正交易",
        )
        return self.get_transaction(principal, transaction_id)

    def delete_transaction(self, principal: Principal, transaction_id: str, *, reason: str = "") -> dict[str, Any]:
        principal = self._principal(principal, "ledger.edit")
        row = self.repo.get_transaction(transaction_id, owner_id=principal.user_id)
        removed = self.repo.soft_delete_transaction(transaction_id, owner_id=principal.user_id)
        if not removed:
            raise InvalidInputError("交易已删除")
        self._record(
            principal, entity="transaction", entity_id=transaction_id,
            revision=int(row.get("revision") or 1) + 1,
            change={"type": "delete", "amount_minor": row.get("amount_minor")},
            reason=reason or "撤回交易",
        )
        return {"transaction_id": transaction_id, "deleted": True}

    # ---- 分类与规则 ----------------------------------------------------------------

    def create_category(
        self, principal: Principal, *, name: str, kind: str = "expense"
    ) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.manage")
        name = clean_text(name, limit=40)
        if not name:
            raise InvalidInputError("分类名称不能为空")
        if self.repo.find_category_by_name(owner_id=principal.user_id, name=name):
            raise InvalidInputError("分类已存在")
        return self.repo.create_category(owner_id=principal.user_id, name=name, kind=kind)

    def list_categories(self, principal: Principal) -> list[dict[str, Any]]:
        principal = self._principal(principal, "ledger.view")
        return self.repo.list_categories(principal.user_id)

    def rename_category(self, principal: Principal, category_id: str, *, name: str) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.manage")
        name = clean_text(name, limit=40)
        if not name:
            raise InvalidInputError("分类名称不能为空")
        if self.repo.find_category_by_name(owner_id=principal.user_id, name=name):
            raise InvalidInputError("分类已存在")
        if not self.repo.rename_category(category_id, owner_id=principal.user_id, name=name):
            raise NotFoundError(f"分类不存在: {category_id}")
        return self.repo.get_category(category_id, owner_id=principal.user_id)

    def delete_category(self, principal: Principal, category_id: str) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.manage")
        used = self.repo.count_transactions_in_category(category_id, owner_id=principal.user_id)
        if used:
            raise InvalidInputError(f"分类仍被 {used} 笔交易使用，先改分类再删除")
        if not self.repo.delete_category(category_id, owner_id=principal.user_id):
            raise NotFoundError(f"分类不存在: {category_id}")
        return {"category_id": category_id, "deleted": True}

    def create_rule(
        self, principal: Principal, *, category_id: str, match_value: str,
        match_field: str = "merchant", match_op: str = "contains", priority: int = 100,
    ) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.manage")
        self.repo.get_category(category_id, owner_id=principal.user_id)
        if match_field not in ("merchant", "product", "tx_type", "note"):
            raise InvalidInputError("规则匹配字段不合法")
        if match_op not in ("contains", "equals", "startswith"):
            raise InvalidInputError("规则匹配方式不合法")
        value = clean_text(match_value, limit=120)
        if not value:
            raise InvalidInputError("规则匹配内容不能为空")
        return self.repo.create_rule(
            owner_id=principal.user_id, category_id=category_id, match_field=match_field,
            match_op=match_op, match_value=value, priority=int(priority),
        )

    def list_rules(self, principal: Principal) -> list[dict[str, Any]]:
        principal = self._principal(principal, "ledger.view")
        return self.repo.list_rules(principal.user_id, enabled=None)

    def delete_rule(self, principal: Principal, rule_id: str) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.manage")
        if not self.repo.delete_rule(rule_id, owner_id=principal.user_id):
            raise NotFoundError(f"分类规则不存在: {rule_id}")
        return {"rule_id": rule_id, "deleted": True}

    def apply_rules(self, principal: Principal, *, limit: int = 5000) -> dict[str, Any]:
        """把启用规则套用到尚未分类的交易；只改 category_id。"""
        principal = self._principal(principal, "ledger.edit")
        rules = self.repo.list_rules(principal.user_id, enabled=True)
        if not rules:
            return {"matched": 0, "rules": 0}
        rows = self.repo.list_transactions(principal.user_id, limit=limit)
        matched = 0
        for row in rows:
            if row.get("category_id"):
                continue
            for rule in rules:
                value = str(row.get(rule["match_field"]) or "")
                needle = str(rule["match_value"])
                hit = (
                    needle in value if rule["match_op"] == "contains"
                    else value == needle if rule["match_op"] == "equals"
                    else value.startswith(needle)
                )
                if hit:
                    self.repo.update_transaction(str(row["id"]), category_id=rule["category_id"])
                    matched += 1
                    break
        return {"matched": matched, "rules": len(rules)}

    # ---- 退款 ------------------------------------------------------------------

    def list_refunds(self, principal: Principal, *, limit: int = 100) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.view")
        links = self.repo.list_refund_links(principal.user_id, limit=limit)
        rows = []
        for link in links:
            try:
                refund = self.repo.get_transaction(
                    str(link["refund_transaction_id"]), owner_id=principal.user_id,
                )
                original = self.repo.get_transaction(
                    str(link["original_transaction_id"]), owner_id=principal.user_id,
                )
            except NotFoundError:
                continue
            rows.append({
                "link": link,
                "refund": _transaction_view(refund),
                "original": _transaction_view(original),
                "remaining_minor": refund_rules.refund_balance(
                    int(original["amount_minor"]),
                    self.repo.links_for_original(str(original["id"]), owner_id=principal.user_id),
                ),
            })
        return {"links": rows, "confirmed": sum(1 for r in rows if r["link"]["confirmation"] == "confirmed")}

    def suggest_refunds(self, principal: Principal, *, import_id: str = "") -> list[dict[str, Any]]:
        principal = self._principal(principal, "ledger.view")
        if import_id:
            self._owner_import(principal, import_id)
            transactions = self.repo.transactions_for_import(
                import_id, owner_id=principal.user_id,
            )
        else:
            transactions = self.repo.list_transactions(principal.user_id, limit=5000)
        refund_pairs = [
            (_parsed_from_row_of_tx(tx), str(tx["id"])) for tx in transactions
            if tx.get("event_role") == EVENT_ROLE_REFUND
        ]
        candidates = self.repo.payment_candidates(
            principal.user_id, occurred_from="0000", occurred_to="9999",
        )
        suggestions = refund_rules.suggest_refund_links(
            [row for row, _ in refund_pairs], candidates,
        )
        reference_to_id = {
            refund_rules.refund_row_reference(row): transaction_id
            for row, transaction_id in refund_pairs
        }
        return [
            {
                "refund_transaction_id": reference_to_id.get(
                    item.refund_transaction_id, item.refund_transaction_id
                ),
                "original_transaction_id": item.original_transaction_id,
                "amount_minor": item.amount_minor,
                "match_method": item.match_method,
                "confirmation": item.confirmation,
                "reason": item.reason,
            }
            for item in suggestions
        ]

    def link_refund(
        self, principal: Principal, *, refund_transaction_id: str,
        original_transaction_id: str, amount_minor: int | None = None,
        confirmation: str = "confirmed",
    ) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.edit")
        refund = self.repo.get_transaction(refund_transaction_id, owner_id=principal.user_id)
        original = self.repo.get_transaction(original_transaction_id, owner_id=principal.user_id)
        if refund.get("event_role") != EVENT_ROLE_REFUND:
            raise InvalidInputError("该交易不是退款，不能关联原支付")
        if original.get("event_role") == EVENT_ROLE_REFUND:
            raise InvalidInputError("原支付不能是退款交易")
        amount = int(amount_minor if amount_minor is not None else refund["amount_minor"])
        if amount <= 0:
            raise InvalidInputError("退款金额必须大于 0")
        existing = self.repo.links_for_original(
            original_transaction_id, owner_id=principal.user_id,
        )
        ok, reason = refund_rules.validate_link(
            refund_amount_minor=amount,
            original_amount_minor=int(original["amount_minor"]),
            existing_amounts=[
                int(link["amount_minor"]) for link in existing
                if link["confirmation"] == "confirmed"
                and str(link["refund_transaction_id"]) != refund_transaction_id
            ],
        )
        if not ok:
            raise InvalidInputError(reason)
        link_id, _created = self.repo.create_refund_link(
            owner_id=principal.user_id, refund_transaction_id=refund_transaction_id,
            original_transaction_id=original_transaction_id, amount_minor=amount,
            match_method="manual", confirmation=confirmation,
        )
        if _created is False:
            self.repo.update_refund_link(
                link_id, amount_minor=amount, confirmation=confirmation,
            )
        self._record(
            principal, entity="refund_link", entity_id=link_id, revision=1,
            change={"refund": refund_transaction_id, "original": original_transaction_id,
                    "amount_minor": amount},
            reason="关联退款",
        )
        return self.repo.get_refund_link(link_id, owner_id=principal.user_id)

    def unlink_refund(self, principal: Principal, link_id: str, *, reason: str = "") -> dict[str, Any]:
        principal = self._principal(principal, "ledger.edit")
        link = self.repo.get_refund_link(link_id, owner_id=principal.user_id)
        self.repo.delete_refund_link(link_id, owner_id=principal.user_id)
        self._record(
            principal, entity="refund_link", entity_id=link_id, revision=1,
            change={"type": "unlink", "refund": link["refund_transaction_id"]},
            reason=reason or "取消退款关联",
        )
        return {"link_id": link_id, "deleted": True}

    def confirm_refund_link(self, principal: Principal, link_id: str) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.edit")
        link = self.repo.get_refund_link(link_id, owner_id=principal.user_id)
        if link["confirmation"] == "confirmed":
            return link
        original = self.repo.get_transaction(
            str(link["original_transaction_id"]), owner_id=principal.user_id,
        )
        siblings = self.repo.links_for_original(
            str(link["original_transaction_id"]), owner_id=principal.user_id,
        )
        ok, reason = refund_rules.validate_link(
            refund_amount_minor=int(link["amount_minor"]),
            original_amount_minor=int(original["amount_minor"]),
            existing_amounts=[
                int(item["amount_minor"]) for item in siblings
                if item["confirmation"] == "confirmed" and item["id"] != link_id
            ],
        )
        if not ok:
            raise InvalidInputError(reason)
        self.repo.update_refund_link(link_id, confirmation="confirmed")
        return self.repo.get_refund_link(link_id, owner_id=principal.user_id)

    # ---- 受控统计 ------------------------------------------------------------------

    def analyze(
        self, principal: Principal, raw_plan: Mapping[str, Any], *, request_id: str = "",
    ) -> AnalysisResult:
        principal = self._principal(principal, "ledger.view")
        accounts = self.repo.list_accounts(principal.user_id)
        imports = self.repo.list_imports(principal.user_id, limit=200)
        plan = validate_plan(
            raw_plan, now_iso=utc_now_iso(), default_timezone=self.timezone,
            allowed_account_ids=frozenset(str(a["id"]) for a in accounts),
            allowed_import_ids=frozenset(str(i["id"]) for i in imports),
        )
        compiled = compile_plan(plan, owner_id=principal.user_id)
        aggregate = self._fetch_one(compiled.aggregate_sql, compiled.aggregate_params)
        metrics = _metrics_for(plan, aggregate)
        groups: list[dict[str, Any]] = []
        if compiled.group_sql:
            groups = self._fetch_all(compiled.group_sql, compiled.group_params)
            groups = _label_groups(groups, plan, self.repo, principal)
        detail = self._fetch_all(compiled.detail_sql, compiled.detail_params)
        coverage = self._coverage(principal, plan, coverage_hint=imports)
        warnings = list(compiled.notes)
        if not plan.filters.include_unconfirmed_refunds:
            warnings.append("未确认的退款关联不计入净额")
        analysis_id = self.repo.create_analysis(
            owner_id=principal.user_id, import_ids=plan.import_ids, query_plan=_plan_payload(plan),
            plan_version=plan.version, snapshot_revision=0, data_cutoff=utc_now_iso(),
            coverage=_coverage_payload(coverage),
            result={
                "metrics": [
                    {"name": m.name, "amount_minor": m.amount_minor,
                     "transaction_count": m.transaction_count, "note": m.note}
                    for m in metrics
                ],
                "groups": groups,
                "warnings": warnings,
            },
        )
        evidence = tuple(
            {"kind": "transaction", "ref_id": str(row["id"])} for row in detail[:20]
        )
        return AnalysisResult(
            analysis_id=analysis_id, plan=plan, basis=plan.basis, currency=plan.currency,
            metrics=metrics, coverage=coverage,
            groups=tuple(groups), transactions=tuple(_transaction_view(r) for r in detail),
            warnings=tuple(warnings), data_cutoff=utc_now_iso(), snapshot_revision=0,
            evidence=evidence,
        )

    def get_analysis(self, principal: Principal, analysis_id: str) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.view")
        return self.repo.get_analysis(analysis_id, owner_id=principal.user_id)

    def list_analyses(self, principal: Principal, *, limit: int = 50) -> list[dict[str, Any]]:
        principal = self._principal(principal, "ledger.view")
        return self.repo.list_analyses(principal.user_id, limit=limit)

    def _fetch_one(self, sql: str, params: Sequence[Any]) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def _fetch_all(self, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
        finally:
            conn.close()

    def _coverage(
        self, principal: Principal, plan: QueryPlan, *, coverage_hint: Sequence[Mapping[str, Any]],
    ) -> Coverage:
        period = plan.period
        start = period.start or ""
        end = period.end_exclusive or ""
        overlapping = self.repo.overlapping_imports(
            owner_id=principal.user_id, start=start or None, end=end or None,
        )
        committed = [i for i in overlapping if i["state"] == IMPORT_COMMITTED]
        kinds = {str(i.get("coverage_kind") or "unknown") for i in committed}
        if not committed:
            kind = "unknown"
        elif len(committed) > 1 or COVERAGE_OVERLAPPING in kinds:
            kind = COVERAGE_OVERLAPPING
        elif kinds == {COVERAGE_COMPLETE}:
            kind = COVERAGE_COMPLETE
        else:
            kind = COVERAGE_PARTIAL
        category_ids = set(plan.filters.category_ids)
        names: list[str] = []
        for category_id in category_ids:
            try:
                names.append(str(
                    self.repo.get_category(category_id, owner_id=principal.user_id)["name"]
                ))
            except NotFoundError:
                continue
        notes = []
        if kind == COVERAGE_OVERLAPPING:
            notes.append("该时间段存在多个账单批次，已按去重后交易统计")
        if kind in ("unknown", COVERAGE_PARTIAL):
            notes.append("该时间段账单覆盖不完整，结果可能偏低")
        return Coverage(
            start=start or None, end_exclusive=end or None,
            imports=tuple(str(i["id"]) for i in committed),
            accounts=tuple(plan.account_ids), category_names=tuple(names),
            coverage_kind=kind, data_cutoff=utc_now_iso(),
            confidence="high" if kind == COVERAGE_COMPLETE else "medium",
            notes=tuple(notes),
        )

    # ---- 图片候选 ------------------------------------------------------------------

    async def save_image_candidate(
        self, principal: Principal, image_file_id: str, payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.import")
        record = self.files.get(principal, image_file_id)
        if record.kind != KIND_IMAGE:
            raise InvalidInputError("只有图片文件可以生成识别候选")
        candidate_id = new_extraction_id()
        candidate = candidate_from_vision(
            candidate_id=candidate_id, image_file_id=image_file_id, payload=payload,
            timezone=self.timezone, default_currency=record.currency if hasattr(record, "currency") else "CNY",
        )
        extraction_id = self.files.record_extraction(
            principal, image_file_id, extractor=IMAGE_EXTRACTOR,
            extractor_version=IMAGE_EXTRACTOR_VERSION,
            input_hash=hashlib.sha256(
                str(payload.get("text") or "").encode("utf-8")
            ).hexdigest()[:32],
            state="candidate",
            quality={"candidate": candidate_payload(candidate)},
        )
        data = candidate_payload(candidate)
        data["extraction_id"] = extraction_id
        return data

    def confirm_image_candidate(
        self, principal: Principal, extraction_id: str, *,
        corrections: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        principal = self._principal(principal, "ledger.edit")
        extraction = self.files.get_extraction(principal, extraction_id)
        stored = (extraction.get("quality_summary") or {}).get("candidate") or {}
        if not stored:
            raise InvalidInputError("该提取结果没有候选数据")
        candidate = _candidate_from_payload(stored)
        if corrections:
            candidate = apply_corrections(candidate, corrections, reviewer_id=principal.user_id)
        if not is_ready_for_confirmation(candidate):
            raise InvalidInputError(
                "识别结果仍有缺失/低置信字段，请先修正: "
                + ", ".join(extraction.get("missing_fields") or candidate.missing_fields or ("amount",))
            )
        account = self.repo.ensure_account(
            owner_id=principal.user_id, provider="wechat", account_alias="截图识别",
            currency=candidate.currency, timezone=self.timezone,
        )
        parsed = ParsedRow(
            sheet="image", row_number=0, locator=f"image:{extraction_id}",
            raw={"text": candidate.raw_text},
            occurred_at=candidate.occurred_at, amount_minor=candidate.amount_minor,
            direction=candidate.direction, currency=candidate.currency,
            tx_type="图片识别", counterparty=candidate.merchant, product="",
            status="", external_id="", merchant_id="", note="",
            event_role=classify_event_role("图片识别", candidate.direction),
            id_reliable=False, errors=(),
        )
        account_id = str(account["id"])
        key = f"image|{account_id}|{fingerprint(candidate.occurred_at, candidate.amount_minor, candidate.merchant, extraction_id)}"
        existing = self.repo.find_transaction(owner_id=principal.user_id, identity_key=key)
        if existing:
            transaction_id = str(existing["id"])
        else:
            transaction_id = self.repo.insert_transaction(
                owner_id=principal.user_id, account_id=account_id,
                transaction={
                    "identity_key": key, "external_id": "",
                    "event_role": parsed.event_role, "amount_minor": candidate.amount_minor,
                    "currency": candidate.currency, "direction": candidate.direction,
                    "tx_type": parsed.tx_type, "merchant": candidate.merchant, "product": "",
                    "occurred_at": candidate.occurred_at, "status": "图片确认",
                    "status_key": "paid", "verification": "confirmed",
                },
            )
        self.files.record_extraction(
            principal, candidate.image_file_id, extractor=IMAGE_EXTRACTOR,
            extractor_version=IMAGE_EXTRACTOR_VERSION,
            input_hash=str(extraction.get("input_hash") or ""), state="confirmed",
            quality={"candidate": candidate_payload(candidate),
                     "transaction_id": transaction_id},
        )
        return self.get_transaction(principal, transaction_id)


# ---- 内部辅助 ------------------------------------------------------------------


def _refund_candidate_window(rows: Sequence[ParsedRow]) -> tuple[str, str]:
    """退款匹配候选窗口：退款发生时间前后各 400 天（覆盖跨期退款）。"""
    moments: list[datetime] = []
    for row in rows:
        if not row.occurred_at:
            continue
        try:
            moments.append(datetime.fromisoformat(row.occurred_at))
        except ValueError:
            continue
    if not moments:
        return "0000", "9999"
    window = timedelta(days=400)
    return (
        (min(moments) - window).isoformat(timespec="seconds"),
        (max(moments) + window).isoformat(timespec="seconds"),
    )


def _provider_of(file_name: str) -> str:
    lowered = (file_name or "").lower()
    if "微信" in file_name or "wechat" in lowered or "wx" in lowered:
        return "wechat"
    if "支付宝" in file_name or "alipay" in lowered:
        return "alipay"
    return "generic"


def _decode_head(head: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "latin-1"):
        try:
            return head.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""


def _mapping_from_quality(quality: Any) -> Any:
    from backend.modules.ledger.contracts import ColumnMapping

    mapping = (quality or {}).get("mapping") or {}
    if not mapping:
        return None
    try:
        return ColumnMapping(**{k: str(v) for k, v in mapping.items()})
    except TypeError:
        return None


def _row_payload(parsed: ParsedRow) -> dict[str, Any]:
    return {
        "sheet": parsed.sheet, "row_number": parsed.row_number, "locator": parsed.locator,
        "raw_fields": dict(parsed.raw), "raw_hash": fingerprint(*parsed.raw.values()),
        "parse_state": "ok" if not parsed.errors else "error",
        "errors": list(parsed.errors), "occurred_at": parsed.occurred_at,
        "amount_minor": parsed.amount_minor, "currency": parsed.currency,
        "direction": parsed.direction, "event_role": parsed.event_role,
        "tx_type": parsed.tx_type, "merchant": parsed.counterparty,
        "product": parsed.product, "status": parsed.status,
        "external_id": parsed.external_id, "merchant_id": parsed.merchant_id,
        "note": parsed.note, "pay_method": parsed.pay_method,
        "id_reliable": parsed.id_reliable,
    }


def _check_control(statement) -> _Control:
    totals = statement.control_totals
    if totals.count is None and totals.expense_minor is None and totals.income_minor is None:
        return _Control(ok=True, checked=False, mismatches=(), detail={})
    rows = statement.rows
    expense = sum(r.amount_minor or 0 for r in rows
                  if r.direction == DIRECTION_EXPENSE and not r.errors)
    income = sum(r.amount_minor or 0 for r in rows
                 if r.direction == DIRECTION_INCOME and not r.errors)
    neutral = sum(r.amount_minor or 0 for r in rows
                  if r.direction in (DIRECTION_NEUTRAL, "unknown") and not r.errors)
    mismatches: list[str] = []
    if totals.count is not None and len(rows) != totals.count:
        mismatches.append(f"笔数不符: 账单写 {totals.count}，明细 {len(rows)}")
    if totals.expense_minor is not None and expense != totals.expense_minor:
        mismatches.append(
            f"支出不符: 账单写 {format_money(totals.expense_minor)}，明细 {format_money(expense)}"
        )
    if totals.income_minor is not None and income != totals.income_minor:
        mismatches.append(
            f"收入不符: 账单写 {format_money(totals.income_minor)}，明细 {format_money(income)}"
        )
    if totals.neutral_minor is not None and neutral != totals.neutral_minor:
        mismatches.append(
            f"中性交易不符: 账单写 {format_money(totals.neutral_minor)}，明细 "
            f"{format_money(neutral)}"
        )
    return _Control(
        ok=not mismatches, checked=True, mismatches=tuple(mismatches),
        detail={"count": len(rows), "expense_minor": expense,
                "income_minor": income, "neutral_minor": neutral},
    )


def _coverage_kind(statement, control: _Control, overlapping: Sequence[Mapping[str, Any]]) -> str:
    if overlapping:
        return COVERAGE_OVERLAPPING
    if not control.ok:
        return COVERAGE_PARTIAL
    if statement.declared_from and statement.declared_to:
        return COVERAGE_COMPLETE
    return COVERAGE_PARTIAL


def _metrics_for(plan: QueryPlan, aggregate: Mapping[str, Any]) -> tuple[MetricResult, ...]:
    expense = int(aggregate.get("expense_minor") or 0)
    income = int(aggregate.get("income_minor") or 0)
    neutral = int(aggregate.get("neutral_minor") or 0)
    refund_received = int(aggregate.get("refund_received_minor") or 0)
    refund_applied = int(aggregate.get("refund_applied_minor") or 0)
    count = int(aggregate.get("tx_count") or 0)

    if plan.basis == BASIS_STATEMENT_FLOW:
        basis_expense = expense
        basis_net = income + refund_received - expense
        note = "账单流水口径：支出不扣退款，退款单列为收入"
    elif plan.basis == BASIS_CONSUMPTION_NET:
        basis_expense = expense - refund_applied
        basis_net = income - basis_expense
        note = "消费净额口径：关联到本期消费的已确认退款（含跨期）已扣除"
    elif plan.basis == BASIS_PERIOD_CASH_OUTFLOW:
        basis_expense = expense - refund_received
        basis_net = income - basis_expense
        note = "本期实际现金口径：本期收到的退款（含跨期）从流出中扣除"
    else:  # pragma: no cover - validate_plan 已拦截
        basis_expense = expense
        basis_net = income - expense
        note = ""

    values = {
        METRIC_EXPENSE: MetricResult(METRIC_EXPENSE, basis_expense, count, note),
        METRIC_INCOME: MetricResult(METRIC_INCOME, income, count, ""),
        METRIC_NEUTRAL: MetricResult(METRIC_NEUTRAL, neutral, count, "中性交易不计收支"),
        METRIC_REFUND_RECEIVED: MetricResult(
            METRIC_REFUND_RECEIVED, refund_received, count, "本期退款到账合计"
        ),
        METRIC_NET: MetricResult(METRIC_NET, basis_net, count, note),
    }
    return tuple(values[name] for name in plan.metrics)


def _label_groups(
    groups: Sequence[Mapping[str, Any]], plan: QueryPlan, repo: LedgerRepository,
    principal: Principal,
) -> list[dict[str, Any]]:
    names: dict[str, str] = {}
    if GROUP_BY_CATEGORY in plan.group_by:
        for category in repo.list_categories(principal.user_id):
            names[str(category["id"])] = str(category["name"])
    labelled: list[dict[str, Any]] = []
    for row in groups:
        item = dict(row)
        if GROUP_BY_CATEGORY in plan.group_by:
            bucket = str(item.get("bucket1") or item.get("bucket2") or "")
            item["bucket_label"] = names.get(bucket, "未分类" if not bucket else bucket)
        labelled.append(item)
    return labelled


def _plan_payload(plan: QueryPlan) -> dict[str, Any]:
    return {
        "version": plan.version, "basis": plan.basis, "metrics": list(plan.metrics),
        "scope": plan.scope, "account_ids": list(plan.account_ids),
        "import_ids": list(plan.import_ids),
        "period": {
            "start": plan.period.start, "end_exclusive": plan.period.end_exclusive,
            "timezone": plan.period.timezone,
        },
        "group_by": list(plan.group_by),
        "filters": {
            "directions": list(plan.filters.directions),
            "category_ids": list(plan.filters.category_ids),
            "merchants": list(plan.filters.merchants),
            "min_amount_minor": plan.filters.min_amount_minor,
            "max_amount_minor": plan.filters.max_amount_minor,
            "include_unconfirmed_refunds": plan.filters.include_unconfirmed_refunds,
        },
        "top_n": plan.top_n, "output": plan.output, "currency": plan.currency,
    }


def _coverage_payload(coverage: Coverage) -> dict[str, Any]:
    return {
        "start": coverage.start, "end_exclusive": coverage.end_exclusive,
        "imports": list(coverage.imports), "accounts": list(coverage.accounts),
        "category_names": list(coverage.category_names),
        "coverage_kind": coverage.coverage_kind, "data_cutoff": coverage.data_cutoff,
        "confidence": coverage.confidence, "notes": list(coverage.notes),
    }


def _commit_result(
    import_id: str, summary: Mapping[str, Any], *, duplicate: bool = False
) -> CommitResult:
    return CommitResult(
        import_id=import_id, state=IMPORT_COMMITTED,
        inserted=int(summary.get("inserted") or 0),
        updated=int(summary.get("updated") or 0),
        unchanged=int(summary.get("unchanged") or 0),
        conflicts=int(summary.get("conflicts") or 0),
        skipped=int(summary.get("skipped") or 0),
        refund_links=int(summary.get("refund_links") or 0),
        refund_suggestions=int(summary.get("refund_suggestions") or 0),
        duplicate=duplicate, warnings=tuple(summary.get("warnings") or ()),
    )


def _parsed_from_row_of_tx(tx: Mapping[str, Any]) -> ParsedRow:
    return ParsedRow(
        sheet="", row_number=0, locator=str(tx["id"]), raw={},
        occurred_at=str(tx.get("occurred_at") or ""),
        amount_minor=int(tx.get("amount_minor") or 0),
        direction=str(tx.get("direction") or DIRECTION_EXPENSE),
        currency=str(tx.get("currency") or "CNY"),
        tx_type=str(tx.get("tx_type") or ""),
        counterparty=str(tx.get("merchant") or ""),
        product=str(tx.get("product") or ""),
        status=str(tx.get("status") or ""),
        external_id=str(tx.get("external_id") or ""),
        event_role=str(tx.get("event_role") or EVENT_ROLE_REFUND),
        id_reliable=normalize_external_id(tx.get("external_id"))[1],
    )


def _candidate_from_payload(payload: Mapping[str, Any]) -> ImageCandidate:
    from backend.modules.ledger.contracts import ExtractedField

    fields: dict[str, ExtractedField] = {}
    for name, field_value in (payload.get("fields") or {}).items():
        fields[name] = ExtractedField(
            value=str(field_value.get("value") or ""),
            confidence=float(field_value.get("confidence") or 0.0),
            source_text=str(field_value.get("source_text") or ""),
            needs_review=bool(field_value.get("needs_review")),
        )
    return ImageCandidate(
        candidate_id=str(payload.get("candidate_id") or ""),
        image_file_id=str(payload.get("image_file_id") or ""),
        fields=fields, missing_fields=tuple(payload.get("missing_fields") or ()),
        confidence=float(payload.get("confidence") or 0.0),
        raw_text=str(payload.get("raw_text") or ""),
        merchant=str(payload.get("merchant") or ""),
        amount_minor=payload.get("amount_minor"),
        direction=str(payload.get("direction") or "unknown"),
        occurred_at=payload.get("occurred_at"),
        currency=str(payload.get("currency") or "CNY"),
        needs_review=bool(payload.get("needs_review")),
        notes=tuple(payload.get("notes") or ()),
    )


__all__ = ["LedgerService", "PARSER_VERSION", "PARSE_JOB_KIND"]

_ = (Period, CompiledQuery, parse_money, parse_occurred_at, parse_control_totals)
