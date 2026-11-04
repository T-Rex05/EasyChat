"""ledger 数据访问：只被 LedgerService 使用，不对外暴露。

规则：
- 所有 SQL 参数化；表名/列名只来自本文件常量；
- 金额整数；时间统一 ISO 字符串（带时区）；
- 跨 owner 的读取一律显式要求 owner_id（Err on missing），防止越权；
- 导入批次提交使用单事务，事务内不做文件 IO。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Mapping, Sequence

from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import NotFoundError
from backend.shared.identifiers import (
    new_analysis_id,
    new_category_id,
    new_category_rule_id,
    new_ledger_account_id,
    new_ledger_change_id,
    new_ledger_import_id,
    new_refund_link_id,
    new_source_row_id,
    new_transaction_id,
    new_transaction_source_id,
)

_IMPORT_COLUMNS = (
    "parser", "parser_version", "state", "declared_from", "declared_to",
    "coverage_kind", "currency", "control_totals", "row_counts", "quality",
    "error", "commit_request_id", "revision",
)
_TRANSACTION_UPDATE_COLUMNS = (
    "status", "status_key", "verification", "category_id", "merchant", "product",
    "tx_type", "note",
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return fallback


class LedgerRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @contextmanager
    def _tx(self, conn: sqlite3.Connection | None = None) -> Iterator[sqlite3.Connection]:
        """复用调用方事务（导入提交要跨多行原子），否则自开短事务。"""
        if conn is not None:
            yield conn
            return
        with self.db.transaction() as own:
            yield own

    # ---- 账户 ------------------------------------------------------------------

    def create_account(
        self, *, owner_id: int, provider: str, account_alias: str = "",
        currency: str = "CNY", timezone: str = "Asia/Shanghai",
    ) -> dict[str, Any]:
        account_id = new_ledger_account_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO ledger_accounts(id, owner_id, provider, account_alias, currency, "
                "timezone, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (account_id, owner_id, provider, account_alias[:60], currency, timezone, now, now),
            )
        return self.get_account(account_id, owner_id=owner_id)

    def get_account(self, account_id: str, *, owner_id: int | None = None) -> dict[str, Any]:
        sql = "SELECT * FROM ledger_accounts WHERE id=?"
        params: list[Any] = [account_id]
        if owner_id is not None:
            sql += " AND owner_id=?"
            params.append(owner_id)
        conn = self.db.connect()
        try:
            row = conn.execute(sql, tuple(params)).fetchone()
            if row is None:
                raise NotFoundError(f"账本账户不存在: {account_id}")
            return dict(row)
        finally:
            conn.close()

    def list_accounts(self, owner_id: int) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM ledger_accounts WHERE owner_id=? ORDER BY created_at, id",
                (owner_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def find_account(
        self, *, owner_id: int, provider: str, account_alias: str
    ) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM ledger_accounts WHERE owner_id=? AND provider=? AND account_alias=?",
                (owner_id, provider, account_alias),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def ensure_account(
        self, *, owner_id: int, provider: str, account_alias: str = "",
        currency: str = "CNY", timezone: str = "Asia/Shanghai",
    ) -> dict[str, Any]:
        existing = self.find_account(
            owner_id=owner_id, provider=provider, account_alias=account_alias,
        )
        if existing:
            return existing
        try:
            return self.create_account(
                owner_id=owner_id, provider=provider, account_alias=account_alias,
                currency=currency, timezone=timezone,
            )
        except Exception:
            # 并发下唯一约束：回读已有行
            again = self.find_account(
                owner_id=owner_id, provider=provider, account_alias=account_alias,
            )
            if again:
                return again
            raise

    # ---- 导入批次 ----------------------------------------------------------------

    def create_import(
        self, *, owner_id: int, account_id: str, file_id: str, parser: str,
        parser_version: str, state: str, declared_from: str | None = None,
        declared_to: str | None = None, coverage_kind: str = "unknown",
        currency: str = "CNY", control_totals: Mapping[str, Any] | None = None,
        row_counts: Mapping[str, Any] | None = None, quality: Mapping[str, Any] | None = None,
    ) -> tuple[str, bool]:
        """返回 (import_id, created)。同一 (owner, file, parser, version) 幂等复用。"""
        import_id = new_ledger_import_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO ledger_imports(id, owner_id, account_id, file_id, parser, "
                "parser_version, state, declared_from, declared_to, coverage_kind, currency, "
                "control_totals, row_counts, quality, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (import_id, owner_id, account_id, file_id, parser, parser_version, state,
                 declared_from, declared_to, coverage_kind, currency, _json(control_totals or {}),
                 _json(row_counts or {}), _json(quality or {}), now, now),
            )
            created = cursor.rowcount == 1
            if not created:
                row = conn.execute(
                    "SELECT id FROM ledger_imports WHERE owner_id=? AND file_id=? AND parser=? "
                    "AND parser_version=?",
                    (owner_id, file_id, parser, parser_version),
                ).fetchone()
                if row is None:  # pragma: no cover - 只在极端并发下出现
                    raise NotFoundError("导入批次创建并发冲突")
                import_id = str(row[0])
        return import_id, created

    def get_import(self, import_id: str, *, owner_id: int | None = None) -> dict[str, Any]:
        sql = "SELECT * FROM ledger_imports WHERE id=?"
        params: list[Any] = [import_id]
        if owner_id is not None:
            sql += " AND owner_id=?"
            params.append(owner_id)
        conn = self.db.connect()
        try:
            row = conn.execute(sql, tuple(params)).fetchone()
            if row is None:
                raise NotFoundError(f"导入批次不存在: {import_id}")
            return self._import_row(dict(row))
        finally:
            conn.close()

    def find_import_by_file(
        self, *, owner_id: int, file_id: str, parser: str, parser_version: str
    ) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM ledger_imports WHERE owner_id=? AND file_id=? AND parser=? "
                "AND parser_version=?",
                (owner_id, file_id, parser, parser_version),
            ).fetchone()
            return self._import_row(dict(row)) if row else None
        finally:
            conn.close()

    def list_imports(
        self, owner_id: int, *, limit: int = 50, offset: int = 0, state: str | None = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ledger_imports WHERE owner_id=?"
        params: list[Any] = [owner_id]
        if state:
            sql += " AND state=?"
            params.append(state)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        conn = self.db.connect()
        try:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._import_row(dict(r)) for r in rows]
        finally:
            conn.close()

    def overlapping_imports(
        self, *, owner_id: int, start: str | None, end: str | None,
        exclude_import_id: str = "",
    ) -> list[dict[str, Any]]:
        """返回时间范围有交集的已提交/已验证批次（用于覆盖提示）。"""
        sql = (
            "SELECT * FROM ledger_imports WHERE owner_id=? AND state IN ('committed','validated')"
        )
        params: list[Any] = [owner_id]
        if exclude_import_id:
            sql += " AND id<>?"
            params.append(exclude_import_id)
        if start:
            sql += " AND (declared_to IS NULL OR declared_to >= ?)"
            params.append(start)
        if end:
            sql += " AND (declared_from IS NULL OR declared_from < ?)"
            params.append(end)
        sql += " ORDER BY declared_from"
        conn = self.db.connect()
        try:
            return [self._import_row(dict(r)) for r in conn.execute(sql, tuple(params)).fetchall()]
        finally:
            conn.close()

    def update_import(self, import_id: str, **fields: Any) -> None:
        updates = {k: v for k, v in fields.items() if k in _IMPORT_COLUMNS}
        if not updates:
            return
        for key in ("control_totals", "row_counts", "quality"):
            if key in updates and not isinstance(updates[key], str):
                updates[key] = _json(updates[key])
        if "revision" in updates:
            updates["revision"] = int(updates["revision"])
        sets = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [utc_now_iso(), import_id]
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE ledger_imports SET {sets}, updated_at=? WHERE id=?",  # noqa: S608
                tuple(values),
            )

    def bump_import_revision(self, import_id: str) -> int:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE ledger_imports SET revision=revision+1, updated_at=? WHERE id=?",
                (utc_now_iso(), import_id),
            )
            row = conn.execute(
                "SELECT revision FROM ledger_imports WHERE id=?", (import_id,),
            ).fetchone()
            return int(row[0]) if row else 0

    @staticmethod
    def _import_row(row: dict[str, Any]) -> dict[str, Any]:
        row["control_totals"] = _loads(row.get("control_totals"), {})
        row["row_counts"] = _loads(row.get("row_counts"), {})
        row["quality"] = _loads(row.get("quality"), {})
        return row

    # ---- 原始行 ------------------------------------------------------------------

    def add_source_rows(
        self, *, import_id: str, owner_id: int, rows: Sequence[Mapping[str, Any]]
    ) -> list[str]:
        """批量写入原始行（含标准化投影）；每个 row 需含 locator/raw_fields。"""
        now = utc_now_iso()
        ids: list[str] = []
        payload: list[tuple[Any, ...]] = []
        for row in rows:
            row_id = new_source_row_id()
            ids.append(row_id)
            payload.append((
                row_id, import_id, owner_id, str(row.get("sheet") or ""),
                int(row.get("row_number") or 0), str(row.get("locator") or ""),
                _json(dict(row.get("raw_fields") or {})), str(row.get("raw_hash") or ""),
                str(row.get("parse_state") or "ok"),
                _json(list(row.get("errors") or [])),
                row.get("occurred_at"), row.get("amount_minor"),
                str(row.get("currency") or "CNY"), str(row.get("direction") or "unknown"),
                str(row.get("event_role") or "payment"), str(row.get("tx_type") or ""),
                str(row.get("merchant") or ""), str(row.get("product") or ""),
                str(row.get("status") or ""), str(row.get("external_id") or ""),
                str(row.get("merchant_id") or ""), str(row.get("note") or ""),
                str(row.get("pay_method") or ""), 1 if row.get("id_reliable") else 0, now,
            ))
        with self.db.transaction() as conn:
            conn.executemany(
                "INSERT INTO ledger_source_rows(id, import_id, owner_id, sheet, row_number, "
                "locator, raw_fields, raw_hash, parse_state, errors, occurred_at, amount_minor, "
                "currency, direction, event_role, tx_type, merchant, product, status, external_id, "
                "merchant_id, note, pay_method, id_reliable, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                payload,
            )
        return ids

    def delete_source_rows(self, import_id: str) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM ledger_source_rows WHERE import_id=?", (import_id,),
            )
            return cursor.rowcount

    def count_source_rows(self, import_id: str, *, parse_state: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM ledger_source_rows WHERE import_id=?"
        params: list[Any] = [import_id]
        if parse_state:
            sql += " AND parse_state=?"
            params.append(parse_state)
        conn = self.db.connect()
        try:
            return int(conn.execute(sql, tuple(params)).fetchone()[0])
        finally:
            conn.close()

    def list_source_rows(
        self, import_id: str, *, limit: int = 500, offset: int = 0,
        parse_state: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ledger_source_rows WHERE import_id=?"
        params: list[Any] = [import_id]
        if parse_state:
            sql += " AND parse_state=?"
            params.append(parse_state)
        sql += " ORDER BY sheet, row_number LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        conn = self.db.connect()
        try:
            return [_source_row(dict(r)) for r in conn.execute(sql, tuple(params)).fetchall()]
        finally:
            conn.close()

    def get_source_row(self, row_id: str, *, owner_id: int) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM ledger_source_rows WHERE id=? AND owner_id=?", (row_id, owner_id),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"原始行不存在: {row_id}")
            return _source_row(dict(row))
        finally:
            conn.close()

    # ---- 交易 ------------------------------------------------------------------

    def find_transaction(
        self, *, owner_id: int, identity_key: str,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        if conn is not None:
            row = conn.execute(
                "SELECT * FROM ledger_transactions WHERE owner_id=? AND identity_key=?",
                (owner_id, identity_key),
            ).fetchone()
            return dict(row) if row else None
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM ledger_transactions WHERE owner_id=? AND identity_key=?",
                (owner_id, identity_key),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_transaction(self, transaction_id: str, *, owner_id: int | None = None) -> dict[str, Any]:
        sql = "SELECT * FROM ledger_transactions WHERE id=?"
        params: list[Any] = [transaction_id]
        if owner_id is not None:
            sql += " AND owner_id=?"
            params.append(owner_id)
        conn = self.db.connect()
        try:
            row = conn.execute(sql, tuple(params)).fetchone()
            if row is None:
                raise NotFoundError(f"交易不存在: {transaction_id}")
            return dict(row)
        finally:
            conn.close()

    def insert_transaction(
        self, *, owner_id: int, account_id: str, transaction: Mapping[str, Any],
        conn: sqlite3.Connection | None = None,
    ) -> str:
        transaction_id = new_transaction_id()
        now = utc_now_iso()
        with self._tx(conn) as active:
            active.execute(
                "INSERT INTO ledger_transactions(id, owner_id, account_id, provider, external_id, "
                "event_role, identity_key, amount_minor, currency, direction, tx_type, merchant, "
                "product, note, occurred_at, status, status_key, category_id, verification, revision, "
                "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    transaction_id, owner_id, account_id,
                    str(transaction.get("provider") or "wechat"),
                    str(transaction.get("external_id") or ""),
                    str(transaction.get("event_role") or "payment"),
                    str(transaction["identity_key"]),
                    int(transaction["amount_minor"]),
                    str(transaction.get("currency") or "CNY"),
                    str(transaction.get("direction") or "unknown"),
                    str(transaction.get("tx_type") or ""),
                    str(transaction.get("merchant") or ""),
                    str(transaction.get("product") or ""),
                    str(transaction.get("note") or ""),
                    str(transaction["occurred_at"]),
                    str(transaction.get("status") or ""),
                    str(transaction.get("status_key") or "unknown"),
                    transaction.get("category_id"),
                    str(transaction.get("verification") or "parsed"),
                    1, now, now,
                ),
            )
        return transaction_id

    def update_transaction(
        self, transaction_id: str, *, conn: sqlite3.Connection | None = None, **fields: Any
    ) -> int:
        updates = {k: v for k, v in fields.items() if k in _TRANSACTION_UPDATE_COLUMNS}
        if not updates:
            return 0
        sets = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [utc_now_iso(), transaction_id]
        with self._tx(conn) as active:
            cursor = active.execute(
                f"UPDATE ledger_transactions SET {sets}, revision=revision+1, updated_at=? "
                "WHERE id=?",  # noqa: S608
                tuple(values),
            )
            return cursor.rowcount

    def soft_delete_transaction(self, transaction_id: str, *, owner_id: int) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE ledger_transactions SET deleted_at=?, updated_at=?, revision=revision+1 "
                "WHERE id=? AND owner_id=? AND deleted_at IS NULL",
                (utc_now_iso(), utc_now_iso(), transaction_id, owner_id),
            )
            return cursor.rowcount

    def list_transactions(
        self, owner_id: int, *, start: str | None = None, end: str | None = None,
        limit: int = 200, offset: int = 0, category_id: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ledger_transactions WHERE owner_id=? AND deleted_at IS NULL"
        params: list[Any] = [owner_id]
        if start:
            sql += " AND occurred_at>=?"
            params.append(start)
        if end:
            sql += " AND occurred_at<?"
            params.append(end)
        if category_id:
            sql += " AND category_id=?"
            params.append(category_id)
        sql += " ORDER BY occurred_at DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        conn = self.db.connect()
        try:
            return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
        finally:
            conn.close()

    def payment_candidates(
        self, owner_id: int, *, occurred_from: str, occurred_to: str, limit: int = 2000
    ) -> list[dict[str, Any]]:
        """退款匹配候选：支出方向的非退款交易。"""
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM ledger_transactions WHERE owner_id=? AND deleted_at IS NULL "
                "AND event_role='payment' AND direction='expense' AND occurred_at>=? "
                "AND occurred_at<=? ORDER BY occurred_at DESC LIMIT ?",
                (owner_id, occurred_from, occurred_to, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def find_by_external_ids(
        self, owner_id: int, external_ids: Sequence[str]
    ) -> list[dict[str, Any]]:
        if not external_ids:
            return []
        placeholders = ",".join("?" for _ in external_ids)
        conn = self.db.connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM ledger_transactions WHERE owner_id=? AND deleted_at IS NULL "
                f"AND external_id IN ({placeholders})",  # noqa: S608
                (owner_id, *external_ids),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def count_transactions(self, owner_id: int, *, import_id: str = "") -> int:
        if import_id:
            sql = (
                "SELECT COUNT(DISTINCT t.id) FROM ledger_transactions t "
                "JOIN ledger_transaction_sources s ON s.transaction_id=t.id "
                "WHERE t.owner_id=? AND s.import_id=?"
            )
            params: tuple[Any, ...] = (owner_id, import_id)
        else:
            sql = "SELECT COUNT(*) FROM ledger_transactions WHERE owner_id=? AND deleted_at IS NULL"
            params = (owner_id,)
        conn = self.db.connect()
        try:
            return int(conn.execute(sql, params).fetchone()[0])
        finally:
            conn.close()

    # ---- 交易来源 ----------------------------------------------------------------

    def link_source(
        self, *, owner_id: int, transaction_id: str, source_row_id: str, import_id: str,
        status_observed: str = "", conn: sqlite3.Connection | None = None,
    ) -> bool:
        now = utc_now_iso()
        with self._tx(conn) as active:
            cursor = active.execute(
                "INSERT OR IGNORE INTO ledger_transaction_sources(id, owner_id, transaction_id, "
                "source_row_id, import_id, observed_at, status_observed, created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    new_transaction_source_id(), owner_id, transaction_id,
                    source_row_id, import_id, now, status_observed, now,
                ),
            )
            return cursor.rowcount == 1

    def sources_for_transaction(self, transaction_id: str, *, owner_id: int) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT s.*, r.locator, r.sheet, r.row_number FROM ledger_transaction_sources s "
                "JOIN ledger_source_rows r ON r.id=s.source_row_id "
                "WHERE s.transaction_id=? AND s.owner_id=? ORDER BY s.created_at",
                (transaction_id, owner_id),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def transactions_for_import(self, import_id: str, *, owner_id: int) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT DISTINCT t.* FROM ledger_transactions t "
                "JOIN ledger_transaction_sources s ON s.transaction_id=t.id "
                "WHERE s.import_id=? AND t.owner_id=? AND t.deleted_at IS NULL",
                (import_id, owner_id),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- 退款关联 ----------------------------------------------------------------

    def create_refund_link(
        self, *, owner_id: int, refund_transaction_id: str, original_transaction_id: str,
        amount_minor: int, match_method: str, confirmation: str,
    ) -> tuple[str, bool]:
        link_id = new_refund_link_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO ledger_refund_links(id, owner_id, refund_transaction_id, "
                "original_transaction_id, amount_minor, match_method, confirmation, revision, "
                "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (link_id, owner_id, refund_transaction_id, original_transaction_id,
                 int(amount_minor), match_method, confirmation, 1, now, now),
            )
            created = cursor.rowcount == 1
            if not created:
                row = conn.execute(
                    "SELECT id FROM ledger_refund_links WHERE refund_transaction_id=? AND "
                    "original_transaction_id=?",
                    (refund_transaction_id, original_transaction_id),
                ).fetchone()
                if row is None:  # pragma: no cover
                    raise NotFoundError("退款关联创建并发冲突")
                link_id = str(row[0])
        return link_id, created

    def get_refund_link(self, link_id: str, *, owner_id: int) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM ledger_refund_links WHERE id=? AND owner_id=?", (link_id, owner_id),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"退款关联不存在: {link_id}")
            return dict(row)
        finally:
            conn.close()

    def links_for_original(
        self, original_transaction_id: str, *, owner_id: int
    ) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM ledger_refund_links WHERE original_transaction_id=? AND owner_id=? "
                "ORDER BY created_at",
                (original_transaction_id, owner_id),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def links_for_refund(self, refund_transaction_id: str, *, owner_id: int) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM ledger_refund_links WHERE refund_transaction_id=? AND owner_id=?",
                (refund_transaction_id, owner_id),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_refund_link(self, link_id: str, **fields: Any) -> int:
        allowed = {"amount_minor", "match_method", "confirmation"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return 0
        sets = ", ".join(f"{k}=?" for k in updates)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                f"UPDATE ledger_refund_links SET {sets}, revision=revision+1, updated_at=? "
                "WHERE id=?",  # noqa: S608
                (*updates.values(), utc_now_iso(), link_id),
            )
            return cursor.rowcount

    def delete_refund_link(self, link_id: str, *, owner_id: int) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM ledger_refund_links WHERE id=? AND owner_id=?", (link_id, owner_id),
            )
            return cursor.rowcount

    def list_refund_links(
        self, owner_id: int, *, limit: int = 200, offset: int = 0,
        confirmation: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ledger_refund_links WHERE owner_id=?"
        params: list[Any] = [owner_id]
        if confirmation:
            sql += " AND confirmation=?"
            params.append(confirmation)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        conn = self.db.connect()
        try:
            return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
        finally:
            conn.close()

    # ---- 分类 ------------------------------------------------------------------

    def create_category(
        self, *, owner_id: int, name: str, kind: str = "expense"
    ) -> dict[str, Any]:
        category_id = new_category_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO ledger_categories(id, owner_id, name, kind, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (category_id, owner_id, name[:40], kind, now, now),
            )
        return self.get_category(category_id, owner_id=owner_id)

    def get_category(self, category_id: str, *, owner_id: int) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM ledger_categories WHERE id=? AND owner_id=?", (category_id, owner_id),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"分类不存在: {category_id}")
            return dict(row)
        finally:
            conn.close()

    def find_category_by_name(self, *, owner_id: int, name: str) -> dict[str, Any] | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM ledger_categories WHERE owner_id=? AND name=?", (owner_id, name),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_categories(self, owner_id: int) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM ledger_categories WHERE owner_id=? ORDER BY name", (owner_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def rename_category(self, category_id: str, *, owner_id: int, name: str) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE ledger_categories SET name=?, updated_at=? WHERE id=? AND owner_id=?",
                (name[:40], utc_now_iso(), category_id, owner_id),
            )
            return cursor.rowcount

    def delete_category(self, category_id: str, *, owner_id: int) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM ledger_categories WHERE id=? AND owner_id=?",
                (category_id, owner_id),
            )
            return cursor.rowcount

    def count_transactions_in_category(self, category_id: str, *, owner_id: int) -> int:
        conn = self.db.connect()
        try:
            return int(conn.execute(
                "SELECT COUNT(*) FROM ledger_transactions WHERE owner_id=? AND category_id=? "
                "AND deleted_at IS NULL",
                (owner_id, category_id),
            ).fetchone()[0])
        finally:
            conn.close()

    # ---- 分类规则 ----------------------------------------------------------------

    def create_rule(
        self, *, owner_id: int, category_id: str, match_field: str, match_op: str,
        match_value: str, priority: int = 100, origin: str = "user",
    ) -> dict[str, Any]:
        rule_id = new_category_rule_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO ledger_category_rules(id, owner_id, category_id, match_field, match_op, "
                "match_value, priority, origin, enabled, version, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,1,1,?,?)",
                (rule_id, owner_id, category_id, match_field, match_op, match_value[:120],
                 int(priority), origin, now, now),
            )
        return self.get_rule(rule_id, owner_id=owner_id)

    def get_rule(self, rule_id: str, *, owner_id: int) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM ledger_category_rules WHERE id=? AND owner_id=?",
                (rule_id, owner_id),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"分类规则不存在: {rule_id}")
            return dict(row)
        finally:
            conn.close()

    def list_rules(self, owner_id: int, *, enabled: bool | None = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ledger_category_rules WHERE owner_id=?"
        params: list[Any] = [owner_id]
        if enabled is not None:
            sql += " AND enabled=?"
            params.append(1 if enabled else 0)
        sql += " ORDER BY priority, created_at"
        conn = self.db.connect()
        try:
            return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
        finally:
            conn.close()

    def update_rule(self, rule_id: str, *, owner_id: int, **fields: Any) -> int:
        allowed = {"category_id", "match_field", "match_op", "match_value", "priority", "enabled"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if "enabled" in updates:
            updates["enabled"] = 1 if updates["enabled"] else 0
        if not updates:
            return 0
        sets = ", ".join(f"{k}=?" for k in updates)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                f"UPDATE ledger_category_rules SET {sets}, version=version+1, updated_at=? "
                "WHERE id=? AND owner_id=?",  # noqa: S608
                (*updates.values(), utc_now_iso(), rule_id, owner_id),
            )
            return cursor.rowcount

    def delete_rule(self, rule_id: str, *, owner_id: int) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM ledger_category_rules WHERE id=? AND owner_id=?",
                (rule_id, owner_id),
            )
            return cursor.rowcount

    # ---- 变更记录 ----------------------------------------------------------------

    def record_change(
        self, *, owner_id: int, actor_id: int, entity: str, entity_id: str,
        revision: int, change: Mapping[str, Any], reason: str = "",
        run_id: str = "", request_id: str = "",
    ) -> str:
        change_id = new_ledger_change_id()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO ledger_changes(id, owner_id, actor_id, run_id, request_id, entity, "
                "entity_id, revision, change, reason, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (change_id, owner_id, actor_id, run_id, request_id, entity, entity_id,
                 int(revision), _json(change), reason[:200], utc_now_iso()),
            )
        return change_id

    def list_changes(
        self, *, owner_id: int, entity: str = "", entity_id: str = "", limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ledger_changes WHERE owner_id=?"
        params: list[Any] = [owner_id]
        if entity:
            sql += " AND entity=?"
            params.append(entity)
        if entity_id:
            sql += " AND entity_id=?"
            params.append(entity_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        conn = self.db.connect()
        try:
            rows = [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
            for row in rows:
                row["change"] = _loads(row.get("change"), {})
            return rows
        finally:
            conn.close()

    # ---- 分析快照 ----------------------------------------------------------------

    def create_analysis(
        self, *, owner_id: int, import_ids: Sequence[str], query_plan: Mapping[str, Any],
        plan_version: int, snapshot_revision: int, data_cutoff: str,
        coverage: Mapping[str, Any], result: Mapping[str, Any], state: str = "succeeded",
        report_file_id: str | None = None,
    ) -> str:
        analysis_id = new_analysis_id()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO ledger_analyses(id, owner_id, import_ids, query_plan, plan_version, "
                "snapshot_revision, data_cutoff, coverage, result, state, report_file_id, "
                "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (analysis_id, owner_id, _json(list(import_ids)), _json(dict(query_plan)),
                 int(plan_version), int(snapshot_revision), data_cutoff, _json(dict(coverage)),
                 _json(dict(result)), state, report_file_id, now, now),
            )
        return analysis_id

    def get_analysis(self, analysis_id: str, *, owner_id: int) -> dict[str, Any]:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM ledger_analyses WHERE id=? AND owner_id=?", (analysis_id, owner_id),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"分析结果不存在: {analysis_id}")
            return _analysis_row(dict(row))
        finally:
            conn.close()

    def list_analyses(self, owner_id: int, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM ledger_analyses WHERE owner_id=? ORDER BY created_at DESC "
                "LIMIT ? OFFSET ?",
                (owner_id, limit, offset),
            ).fetchall()
            return [_analysis_row(dict(r)) for r in rows]
        finally:
            conn.close()

    def set_analysis_report(self, analysis_id: str, *, owner_id: int, file_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE ledger_analyses SET report_file_id=?, updated_at=? WHERE id=? AND owner_id=?",
                (file_id, utc_now_iso(), analysis_id, owner_id),
            )


def _source_row(row: dict[str, Any]) -> dict[str, Any]:
    row["raw_fields"] = _loads(row.get("raw_fields"), {})
    row["errors"] = _loads(row.get("errors"), [])
    return row


def _analysis_row(row: dict[str, Any]) -> dict[str, Any]:
    row["import_ids"] = _loads(row.get("import_ids"), [])
    row["query_plan"] = _loads(row.get("query_plan"), {})
    row["coverage"] = _loads(row.get("coverage"), {})
    row["result"] = _loads(row.get("result"), {})
    return row


def _iter_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
