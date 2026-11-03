"""usage 模块公开接口：唯一计量写入口（架构 §7）。

begin_call / complete_call / report_usage 是所有真实出站 LLM 调用的唯一
计量路径。Hermes 与 traced_llm 等入口产生通知后必须汇入同一 call_id；
迁移期间旧 Trace observer 不得再直接累加 daily_user_stats。
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.modules.usage.contracts import VALID_SOURCES, NormalizedUsage, UsageRecord
from backend.modules.usage.repository import UsageRepository
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import ForbiddenError, InvalidInputError, NotFoundError
from backend.shared.identifiers import new_call_id


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UsageService:
    def __init__(
        self,
        db: Database,
        *,
        clock: Callable[[], datetime] | None = None,
        effective_permissions: Callable[[Principal], frozenset[str]] | None = None,
    ) -> None:
        """effective_permissions 由 bootstrap 注入 access 公开接口，避免模块环。"""
        self.repo = UsageRepository(db)
        self._clock = clock or utc_now
        self._effective_permissions = effective_permissions or (lambda _p: frozenset())

    # ---- 唯一计量入口 ------------------------------------------------------------

    def begin_call(
        self,
        *,
        owner_id: int,
        source: str,
        provider: str,
        model: str,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """真实请求发送前分配 call_id 并落明细。真实重试须再次调用（两次计两次）。"""
        if source not in VALID_SOURCES:
            raise InvalidInputError(f"未知计量来源: {source}")
        call_id = new_call_id()
        self.repo.insert_call(
            call_id=call_id,
            owner_id=owner_id,
            source=source,
            provider=provider,
            model=model,
            run_id=run_id,
            session_id=session_id,
            created_utc=self._clock(),
        )
        return call_id

    def complete_call(
        self,
        call_id: str,
        usage: NormalizedUsage | None,
        *,
        estimated: bool = False,
        error: str | None = None,
    ) -> bool:
        """请求完成：首次生效并累加日汇总；同一 call_id 的重复回调不重复计。"""
        return self.repo.complete_call(
            call_id=call_id,
            usage=usage,
            estimated=estimated,
            completed_utc=self._clock(),
            error=error,
        )

    def mark_error(self, call_id: str, error: str) -> None:
        self.repo.mark_error(call_id=call_id, error=error, completed_utc=self._clock())

    def report_usage(self, call_id: str, usage: NormalizedUsage) -> bool:
        """晚到/修正补全：按新旧差额一次更新明细与日汇总，不重复累计。"""
        return self.repo.report_usage(call_id=call_id, usage=usage, completed_utc=self._clock())

    def record_call(self, record: UsageRecord) -> str:
        """一次性建账（组合入口）：返回 call_id，调用方完成后用 complete_call 结账。"""
        return self.begin_call(
            owner_id=record.owner_id,
            source=record.source,
            provider=record.provider,
            model=record.model,
            run_id=record.run_id,
            session_id=record.session_id,
        )

    # ---- 查询 ------------------------------------------------------------------

    def _permissions(self, actor: Principal) -> frozenset[str]:
        return self._effective_permissions(actor)

    def _can_view_owner(self, actor: Principal, owner_id: int) -> bool:
        if owner_id == actor.user_id:
            return True
        if actor.role == "super_admin":
            return True
        return "trace.manage" in self._permissions(actor)

    def list_calls(
        self,
        actor: Principal,
        *,
        owner_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """明细查看：默认本人；他人/全量需 trace.manage。无权限看不到他人明细。"""
        if owner_id is not None:
            if not self._can_view_owner(actor, owner_id):
                raise ForbiddenError("无权查看他人调用明细")
        else:
            if actor.role != "super_admin" and "trace.manage" not in self._permissions(actor):
                owner_id = actor.user_id
        return self.repo.list_calls(owner_id=owner_id, limit=limit, offset=offset)

    def get_call(self, actor: Principal, call_id: str) -> dict[str, Any]:
        row = self.repo.get_call(call_id)
        if row is None:
            raise NotFoundError(f"调用不存在: {call_id}")
        if not self._can_view_owner(actor, int(row["owner_id"])):
            raise ForbiddenError("无权查看他人调用明细")
        return row

    def ranking(self, actor: Principal, *, days: int = 7, limit: int = 20) -> dict[str, Any]:
        """Token 排行：保留 trace.view 查看排行语义（架构 §6/§7）。"""
        if actor.role != "super_admin" and "trace.view" not in self._permissions(actor):
            raise ForbiddenError("缺少权限: trace.view")
        rows = self.repo.ranking(days=days, limit=limit, today_utc=self._clock())
        return {"ranking": rows, "days": days}

    def my_daily_usage(self, actor: Principal, *, days: int = 30) -> list[dict[str, Any]]:
        return self.repo.daily_totals(owner_id=actor.user_id, days=days, today_utc=self._clock())

    def cleanup_old_calls(self, actor: Principal, *, days: int) -> int:
        """清理排障明细：日汇总不动；明细保留范围必须覆盖重建区间。"""
        if actor.role != "super_admin" and "trace.manage" not in self._permissions(actor):
            raise ForbiddenError("缺少权限: trace.manage")
        cutoff = self._clock() - timedelta(days=days)
        return self.repo.cleanup_calls_before(cutoff)
