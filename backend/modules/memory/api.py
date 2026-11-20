"""memory 模块公开接口：recall / remember / revise / forget / feedback。

所有写入要求来源、owner 与版本；遗忘清除正文和历史版本，只保留哈希墓碑。
"""
from __future__ import annotations

import logging
import re
from typing import Any

from backend.modules.memory import retrieval
from backend.modules.memory.contracts import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_TOKEN_BUDGET,
    DEFAULT_TOP_K,
    SIGNAL_CORRECT,
    SIGNAL_FEEDBACK,
    SIGNAL_FORGET,
    SIGNAL_REMEMBER,
    SIGNAL_STAGE_COMPLETE,
    MemoryCandidate,
    MemoryRecord,
    RecallResult,
    SignalReceipt,
    ForgetResult,
    SourceRef,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
)
from backend.modules.memory.extractor import (
    ExtractionError,
    MAX_CONTENT_CHARS,
    candidate_from_payload,
    validate_candidate,
)
from backend.modules.memory.repository import MemoryRepository
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import AppError, InvalidInputError

logger = logging.getLogger(__name__)
_MEMORY_ID_PREFIX = re.compile(r"mem_[0-9a-f]{4,32}")


def _memory_id_prefix(value: str) -> str:
    if not _MEMORY_ID_PREFIX.fullmatch(value):
        raise InvalidInputError("请提供以 mem_ 开头且至少含 4 位十六进制字符的记忆 ID")
    return value


def _revision_content(content: str) -> str:
    content = content.strip()
    if not content:
        raise InvalidInputError("修改后的记忆内容不能为空")
    if len(content) > MAX_CONTENT_CHARS:
        raise InvalidInputError(f"修改后的记忆内容不能超过 {MAX_CONTENT_CHARS} 字")
    return content


class MemoryService:
    def __init__(
        self,
        db: Database,
        *,
        access: Any,
        queue: Any = None,
        clock=None,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> None:
        self.db = db
        self.repo = MemoryRepository(db)
        self.access = access
        self.queue = queue
        self.clock = clock
        self.token_budget = token_budget

    # ---- 权限 ------------------------------------------------------------------

    def _principal(self, actor: Principal) -> Principal:
        return self.access.validate_principal(actor)

    def _require(self, principal: Principal, permission: str) -> None:
        self.access.require_permission(principal, permission)

    def require_view(self, actor: Principal) -> None:
        self._require(self._principal(actor), "memory.view")

    # ---- 写入 ------------------------------------------------------------------

    def remember(
        self, actor: Principal, candidate: MemoryCandidate, *,
        persona_id: str | None = None, is_shared: bool = False,
    ) -> MemoryRecord:
        principal = self._principal(actor)
        self._require(principal, "memory.edit")
        validate_candidate(candidate)
        return self.repo.create_memory(
            owner_id=principal.user_id, candidate=candidate, persona_id=persona_id,
            is_shared=is_shared, deduplicate=True,
        )

    def require_active_persona(self, actor: Principal, persona_id: str) -> None:
        principal = self._principal(actor)
        conn = self.db.connect()
        try:
            self.repo.require_active_persona(conn, principal.user_id, persona_id)
        finally:
            conn.close()

    def remember_explicit(
        self, actor: Principal, candidate: MemoryCandidate, *, persona_id: str | None = None,
    ) -> MemoryRecord:
        """用户明确要求记住：来源由服务端强制 user_confirmed，不信任模型字段。"""
        from dataclasses import replace

        from backend.modules.memory.contracts import SOURCE_USER_CONFIRMED

        confirmed = replace(
            candidate,
            source_type=SOURCE_USER_CONFIRMED,
            confidence=1.0,
            scope="user",
        )
        return self.remember(actor, confirmed, persona_id=persona_id)

    def revise(
        self,
        actor: Principal,
        memory_id: str,
        expected_version: int,
        *,
        content: str,
        reason: str = "",
        source_refs: tuple[SourceRef, ...] = (),
    ) -> MemoryRecord:
        principal = self._principal(actor)
        self._require(principal, "memory.edit")
        return self.repo.revise(
            memory_id=memory_id, owner_id=principal.user_id,
            expected_version=expected_version, content=_revision_content(content),
            source_refs=source_refs, reason=reason or "user revised",
        )

    def revise_from_channel(
        self, actor: Principal, memory_id: str, expected_version: int, *,
        content: str, event_id: str, persona_id: str | None = None,
    ) -> tuple[str, int]:
        principal = self._principal(actor)
        self._require(principal, "memory.view")
        self._require(principal, "memory.edit")
        if not event_id:
            raise InvalidInputError("缺少微信事件标识")
        return self.repo.revise_from_channel(
            owner_id=principal.user_id, memory_id=_memory_id_prefix(memory_id), persona_id=persona_id,
            expected_version=expected_version, content=_revision_content(content), event_id=event_id,
        )

    def channel_revision_receipt(
        self, actor: Principal, event_id: str, *, persona_id: str | None = None,
    ) -> tuple[str, int] | None:
        principal = self._principal(actor)
        self._require(principal, "memory.view")
        self._require(principal, "memory.edit")
        return self.repo.channel_revision_receipt(
            owner_id=principal.user_id, event_id=event_id, persona_id=persona_id,
        )

    def set_sharing(self, actor: Principal, memory_id: str, *, is_shared: bool) -> MemoryRecord:
        principal = self._principal(actor)
        self._require(principal, "memory.view")
        self._require(principal, "memory.edit")
        return self.repo.set_sharing(
            owner_id=principal.user_id, memory_id=_memory_id_prefix(memory_id), is_shared=is_shared,
        )

    def record_feedback(
        self, actor: Principal, memory_id: str, source_event_id: str, signal: str, note: str = ""
    ) -> bool:
        principal = self._principal(actor)
        self._require(principal, "memory.edit")
        return self.repo.add_feedback(
            owner_id=principal.user_id, memory_id=memory_id,
            source_event_id=source_event_id, signal=signal, note=note,
        )

    # ---- 召回 ------------------------------------------------------------------

    def recall(
        self, actor: Principal, query: str, *, top_k: int = DEFAULT_TOP_K,
        token_budget: int | None = None, persona_id: str | None = None,
    ) -> RecallResult:
        principal = self._principal(actor)
        self._require(principal, "memory.view")
        include_archived = retrieval.wants_old_memories(query)
        candidates = self.repo.candidates(
            principal.user_id, include_archived=include_archived,
            limit=DEFAULT_CANDIDATE_LIMIT, persona_id=persona_id,
        )
        return retrieval.recall(
            candidates, query, top_k=top_k,
            token_budget=token_budget or self.token_budget,
            include_archived=include_archived,
        )

    def list(
        self, actor: Principal, *, include_archived: bool = False, limit: int = 50,
        persona_id: str | None = None, all_personas: bool = True, shared_only: bool = False,
        query: str = "", exact_scope: bool = False,
    ) -> list[MemoryRecord]:
        principal = self._principal(actor)
        self._require(principal, "memory.view")
        statuses = (STATUS_ACTIVE, STATUS_ARCHIVED) if include_archived else (STATUS_ACTIVE,)
        return self.repo.list_for_owner(
            principal.user_id, statuses=statuses, limit=limit, persona_id=persona_id,
            all_personas=all_personas, shared_only=shared_only, query=query.strip(), exact_scope=exact_scope,
        )

    def get(
        self, actor: Principal, memory_id: str, *,
        persona_id: str | None = None, all_personas: bool = True,
    ) -> MemoryRecord:
        principal = self._principal(actor)
        self._require(principal, "memory.view")
        return self.repo.get_visible(
            principal.user_id, _memory_id_prefix(memory_id),
            persona_id=persona_id, all_personas=all_personas,
        )

    def revisions(
        self, actor: Principal, memory_id: str, *, limit: int = 50, offset: int = 0,
        persona_id: str | None = None, all_personas: bool = True,
    ) -> list[dict[str, Any]]:
        principal = self._principal(actor)
        self._require(principal, "memory.view")
        return self.repo.visible_revisions(
            principal.user_id, _memory_id_prefix(memory_id),
            persona_id=persona_id, all_personas=all_personas, limit=limit, offset=offset,
        )

    # ---- 遗忘 ------------------------------------------------------------------

    def forget(
        self,
        actor: Principal,
        *,
        memory_id: str = "",
        source_ref: str = "",
        query: str = "",
        reason: str = "",
        persona_id: str | None = None,
        all_personas: bool = True,
    ) -> ForgetResult:
        principal = self._principal(actor)
        self._require(principal, "memory.edit")
        if sum(bool(v) for v in (memory_id, source_ref, query)) != 1:
            raise InvalidInputError("必须且只能指定 memory_id / source_ref / query 之一")
        if query and not query.strip():
            raise InvalidInputError("遗忘查询不能为空")
        affected = self.repo.forget_memories(
            owner_id=principal.user_id, memory_id=_memory_id_prefix(memory_id) if memory_id else "",
            source_ref=source_ref, query=query.strip().lower(), persona_id=persona_id, all_personas=all_personas,
        )
        return ForgetResult(forgotten=len(affected), rule_recorded=True, affected_ids=affected)

    # ---- 信号（幂等 job） --------------------------------------------------------

    def enqueue_signal(
        self,
        actor: Principal,
        *,
        signal: str,
        source_event_id: str,
        payload: dict[str, Any],
    ) -> SignalReceipt:
        principal = self._principal(actor)
        self._require(principal, "memory.edit")
        if not source_event_id:
            raise InvalidInputError("缺少 source_event_id")
        signal_id, inserted, state = self.repo.insert_signal(
            owner_id=principal.user_id, source_event_id=source_event_id,
            signal=signal, payload=payload,
        )
        if inserted and state == "pending" and self.queue is not None:
            self.queue.enqueue(
                kind="memory.signal",
                dedup_key=f"memory:{principal.user_id}:{source_event_id}",
                payload={"signal_id": signal_id, "signal": signal},
                owner_id=principal.user_id,
            )
        return SignalReceipt(
            signal_id=signal_id, state=state, duplicate=not inserted,
            memory_id=str(payload.get("memory_id") or ""),
        )

    def apply_signal(self, signal_id: str) -> SignalReceipt:
        row = self.repo.get_signal(signal_id)
        if str(row["state"]) in ("processed", "rejected"):
            return SignalReceipt(
                signal_id=signal_id, state=str(row["state"]), duplicate=True,
                memory_id="",
            )
        import json

        payload = json.loads(str(row["payload"] or "{}"))
        signal = str(row["signal"])
        try:
            principal = self.access.snapshot_principal(int(row["owner_id"]))
            memory_id = ""
            if signal in (SIGNAL_REMEMBER, SIGNAL_STAGE_COMPLETE):
                candidate = candidate_from_payload(payload)
                memory_id = self.remember(principal, candidate).memory_id
            elif signal == SIGNAL_CORRECT:
                record = self.revise(
                    principal, str(payload.get("memory_id") or ""),
                    int(payload.get("expected_version") or 0),
                    content=str(payload.get("content") or ""),
                    reason=str(payload.get("reason") or "signal correction"),
                )
                memory_id = record.memory_id
            elif signal == SIGNAL_FORGET:
                self.forget(
                    principal,
                    memory_id=str(payload.get("memory_id") or ""),
                    source_ref=str(payload.get("source_ref") or ""),
                    query=str(payload.get("query") or ""),
                    reason=str(payload.get("reason") or "signal forget"),
                )
            elif signal == SIGNAL_FEEDBACK:
                self.record_feedback(
                    principal, str(payload.get("memory_id") or ""),
                    str(payload.get("source_event_id") or row["source_event_id"]),
                    str(payload.get("signal") or "used"),
                    note=str(payload.get("note") or ""),
                )
                memory_id = str(payload.get("memory_id") or "")
            else:
                raise InvalidInputError(f"未知记忆信号: {signal}")
        except (ExtractionError, AppError) as exc:
            self.repo.mark_signal(signal_id, state="rejected", error=str(exc))
            return SignalReceipt(signal_id=signal_id, state="rejected", duplicate=False)
        self.repo.mark_signal(signal_id, state="processed")
        return SignalReceipt(
            signal_id=signal_id, state="processed", duplicate=False, memory_id=memory_id,
        )
