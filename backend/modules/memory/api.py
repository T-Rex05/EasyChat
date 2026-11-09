"""memory 模块公开接口：recall / remember / revise / forget / feedback。

所有写入要求来源、owner 与版本；遗忘清除正文和历史版本，只保留哈希墓碑。
"""
from __future__ import annotations

import logging
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
    candidate_from_payload,
    validate_candidate,
)
from backend.modules.memory.repository import (
    MemoryRepository,
    content_hash,
    source_hash,
)
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import AppError, ForbiddenError, InvalidInputError, NotFoundError

logger = logging.getLogger(__name__)


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

    # ---- 写入 ------------------------------------------------------------------

    def remember(self, actor: Principal, candidate: MemoryCandidate) -> MemoryRecord:
        principal = self._principal(actor)
        self._require(principal, "memory.edit")
        validate_candidate(candidate)
        self._assert_not_forgotten(principal.user_id, candidate)
        existing = self.repo.find_active_content(
            principal.user_id, candidate.kind, candidate.content
        )
        if existing is not None:
            return existing
        if candidate.supersedes:
            old = self.repo.get(candidate.supersedes)
            if old.owner_id != principal.user_id:
                raise NotFoundError("被取代的记忆不存在")
            self.repo.set_status(old.memory_id, STATUS_ARCHIVED)
        return self.repo.create_memory(owner_id=principal.user_id, candidate=candidate)

    def remember_explicit(self, actor: Principal, candidate: MemoryCandidate) -> MemoryRecord:
        """用户明确要求记住：来源由服务端强制 user_confirmed，不信任模型字段。"""
        from dataclasses import replace

        from backend.modules.memory.contracts import SOURCE_USER_CONFIRMED

        confirmed = replace(
            candidate,
            source_type=SOURCE_USER_CONFIRMED,
            confidence=1.0,
            scope="user",
        )
        return self.remember(actor, confirmed)

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
        record = self.repo.get(memory_id)
        if record.owner_id != principal.user_id:
            if not self.access.has_permission(principal, "system.manage"):
                raise NotFoundError("记忆不存在")
        if not content.strip():
            raise InvalidInputError("修改后的记忆内容不能为空")
        refs = source_refs or record.source_refs
        return self.repo.revise(
            memory_id=memory_id, owner_id=record.owner_id,
            expected_version=expected_version, content=content.strip(),
            source_refs=refs, reason=reason or "user revised",
        )

    def record_feedback(
        self, actor: Principal, memory_id: str, source_event_id: str, signal: str, note: str = ""
    ) -> bool:
        principal = self._principal(actor)
        self._require(principal, "memory.edit")
        record = self.repo.get(memory_id)
        if record.owner_id != principal.user_id:
            raise NotFoundError("记忆不存在")
        return self.repo.add_feedback(
            owner_id=principal.user_id, memory_id=memory_id,
            source_event_id=source_event_id, signal=signal, note=note,
        )

    # ---- 召回 ------------------------------------------------------------------

    def recall(
        self, actor: Principal, query: str, *, top_k: int = DEFAULT_TOP_K,
        token_budget: int | None = None,
    ) -> RecallResult:
        principal = self._principal(actor)
        self._require(principal, "memory.view")
        include_archived = retrieval.wants_old_memories(query)
        candidates = self.repo.candidates(
            principal.user_id, include_archived=include_archived,
            limit=DEFAULT_CANDIDATE_LIMIT,
        )
        return retrieval.recall(
            candidates, query, top_k=top_k,
            token_budget=token_budget or self.token_budget,
            include_archived=include_archived,
        )

    def list(
        self, actor: Principal, *, include_archived: bool = False, limit: int = 50
    ) -> list[MemoryRecord]:
        principal = self._principal(actor)
        self._require(principal, "memory.view")
        statuses = (STATUS_ACTIVE, STATUS_ARCHIVED) if include_archived else (STATUS_ACTIVE,)
        return self.repo.list_for_owner(principal.user_id, statuses=statuses, limit=limit)

    # ---- 遗忘 ------------------------------------------------------------------

    def forget(
        self,
        actor: Principal,
        *,
        memory_id: str = "",
        source_ref: str = "",
        query: str = "",
        reason: str = "",
    ) -> ForgetResult:
        principal = self._principal(actor)
        self._require(principal, "memory.edit")
        owner = principal.user_id
        if sum(bool(v) for v in (memory_id, source_ref, query)) != 1:
            raise InvalidInputError("必须且只能指定 memory_id / source_ref / query 之一")

        targets: list[MemoryRecord] = []
        extra_rules: list[tuple[str, str]] = []
        if memory_id:
            record = self.repo.get(memory_id)
            if record.owner_id != owner:
                raise NotFoundError("记忆不存在")
            targets = [record]
            target_kind, target_hash = "memory", source_hash(memory_id)
            # 同时按正文/来源登记墓碑，阻止同一内容被旧消息重新提取
            extra_rules.append(("content", content_hash(record.content)))
            extra_rules.extend(("source_ref", source_hash(ref.ref)) for ref in record.source_refs)
        elif source_ref:
            for record in self.repo.list_for_owner(
                owner, statuses=(STATUS_ACTIVE, STATUS_ARCHIVED), limit=2000
            ):
                if any(ref.ref == source_ref for ref in record.source_refs):
                    targets.append(record)
            target_kind, target_hash = "source_ref", source_hash(source_ref)
        else:
            needle = query.strip().lower()
            if not needle:
                raise InvalidInputError("遗忘查询不能为空")
            for record in self.repo.list_for_owner(
                owner, statuses=(STATUS_ACTIVE, STATUS_ARCHIVED), limit=2000
            ):
                if needle in record.content.lower():
                    targets.append(record)
            target_kind, target_hash = "content", content_hash(query)

        affected = [t.memory_id for t in targets]
        forgotten = self.repo.forget_memories(
            owner_id=owner, memory_ids=affected,
            target_kind=target_kind, target_hash=target_hash, reason=reason,
        )
        for rule_kind, rule_hash in extra_rules:
            self.repo.forget_memories(
                owner_id=owner, memory_ids=[], target_kind=rule_kind,
                target_hash=rule_hash, reason=reason,
            )
        # 按内容遗忘时，同时登记每条被删正文的哈希，阻止旧消息重提取
        if query:
            for record in targets:
                self.repo.forget_memories(
                    owner_id=owner, memory_ids=[], target_kind="content",
                    target_hash=content_hash(record.content), reason=reason,
                )
        return ForgetResult(
            forgotten=forgotten, rule_recorded=True, affected_ids=tuple(affected),
        )

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
        if inserted and self.queue is not None:
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

    # ---- 内部 ------------------------------------------------------------------

    def _assert_not_forgotten(self, owner_id: int, candidate: MemoryCandidate) -> None:
        if self.repo.find_forget_rule(owner_id, "content", content_hash(candidate.content)):
            raise ForbiddenError("该内容已被用户遗忘，不能重新写入")
        for ref in candidate.source_refs:
            if self.repo.find_forget_rule(owner_id, "source_ref", source_hash(ref.ref)):
                raise ForbiddenError("该来源已被用户遗忘，不能重新提取")
