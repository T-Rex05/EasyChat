"""run 执行调度器：唯一前台 worker（架构 §10 起始容量：foreground active=1）。

- FIFO 消费 queued run；全局同时执行 1 个前台 run（会话天然串行）。
- 取消语义：cancel_requested → runtime.cancel（协作式）；流结束后按实际
  结果落 cancelled 或 completed，不宣称同步工具被强杀。
- 重启恢复：启动时把遗留 running/cancel_requested 标 interrupted 对账；
  queued 保持排队。禁止自动重跑有副作用的工具。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from backend.modules.assistant.events import EventBus
from backend.modules.assistant.repository import (
    RUN_CANCEL_REQUESTED,
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_INTERRUPTED,
    RUN_QUEUED,
    RUN_RUNNING,
    AssistantRepository,
)

logger = logging.getLogger(__name__)


class RunDispatcher:
    def __init__(
        self,
        *,
        repo: AssistantRepository,
        events: EventBus,
        runtime: Any,
        models: Any,
        access: Any,
        on_run_finished: Callable[[Any, dict[str, Any]], None] | None = None,
        poll_interval: float = 0.05,
    ) -> None:
        self.repo = repo
        self.events = events
        self.runtime = runtime
        self.models = models
        self.access = access
        self.on_run_finished = on_run_finished
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._cancel_flags: set[str] = set()
        self._cancelled_runtime: set[str] = set()

    # ---- 生命周期 ------------------------------------------------------------------

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        await self.recover_interrupted()
        self._task = asyncio.ensure_future(self._worker())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._task = None

    async def recover_interrupted(self) -> int:
        """启动对账：上一进程遗留的 running/cancel_requested 标 interrupted。"""
        recovered = 0
        conn = self.repo.db.connect()
        try:
            rows = conn.execute(
                "SELECT id FROM runs WHERE status IN (?,?)", (RUN_RUNNING, RUN_CANCEL_REQUESTED)
            ).fetchall()
        finally:
            conn.close()
        for row in rows:
            run_id = str(row["id"])
            if self.repo.transition_run(run_id, to_status=RUN_INTERRUPTED,
                                        error="进程重启，执行中断（已保留检查点，不自动重跑）"):
                self.events.finish(run_id, "interrupted", {"reason": "process_restart"})
                recovered += 1
        return recovered

    # ---- 取消 ------------------------------------------------------------------

    async def request_cancel(self, run_id: str) -> str:
        status = self.repo.request_cancel(run_id)
        if status == RUN_CANCEL_REQUESTED:
            self._cancel_flags.add(run_id)
            if run_id not in self._cancelled_runtime:
                self._cancelled_runtime.add(run_id)
                try:
                    await self.runtime.cancel(run_id)
                except Exception:  # noqa: BLE001  cancel 失败不阻塞状态推进
                    logger.exception("runtime.cancel 失败 run_id=%s", run_id)
        return status

    # ---- worker ------------------------------------------------------------------

    async def _worker(self) -> None:
        while not self._stopping:
            run = self._next_queued()
            if run is None:
                await asyncio.sleep(self.poll_interval)
                continue
            try:
                await self._execute_run(run)
            except Exception as exc:  # noqa: BLE001  worker 不因单 run 崩溃，也不热循环重试
                logger.exception("执行 run 失败 run_id=%s", run.get("id"))
                self._fail_stuck_run(str(run.get("id", "")), str(exc))
                await asyncio.sleep(self.poll_interval)
            self.events.sweep()

    def _fail_stuck_run(self, run_id: str, error: str) -> None:
        """执行异常且 run 仍处可迁移状态 → 落 failed，防止同一 run 无限重试。"""
        if not run_id:
            return
        try:
            if self.repo.transition_run(run_id, to_status=RUN_FAILED, error=error[:500]):
                self.events.finish(run_id, "failed", {"error": error[:500]})
        except Exception:  # noqa: BLE001  状态推进也失败时依赖退避避免热循环
            logger.exception("落 failed 失败 run_id=%s", run_id)

    def _next_queued(self) -> dict[str, Any] | None:
        conn = self.repo.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM runs WHERE status=? ORDER BY created_at LIMIT 1", (RUN_QUEUED,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _count_queued(self) -> int:
        conn = self.repo.db.connect()
        try:
            row = conn.execute("SELECT count(*) AS c FROM runs WHERE status=?", (RUN_QUEUED,)).fetchone()
            return int(row["c"])
        finally:
            conn.close()

    async def _execute_run(self, run: dict[str, Any]) -> None:
        run_id = str(run["id"])
        if not self.repo.transition_run(run_id, to_status=RUN_RUNNING):
            return  # 已被取消等并发推进
        self.events.publish(run_id, "started", {"session_id": run["session_id"]})

        request = self._build_request(run)
        final_status = RUN_FAILED
        final_content = ""
        error: str | None = None
        try:
            async for event in self.runtime.execute(request):
                if run_id in self._cancel_flags:
                    await self.request_cancel(run_id)  # 确保runtime已收到取消
                if event.kind == "token":
                    self.events.publish(run_id, "token", dict(event.payload))
                elif event.kind == "thinking":
                    self.events.publish(run_id, "thinking", dict(event.payload))
                elif event.kind == "tool_started":
                    self.events.publish(run_id, "tool_started", dict(event.payload))
                elif event.kind == "tool_finished":
                    self.events.publish(run_id, "tool_finished", dict(event.payload))
                elif event.kind == "completed":
                    final_status = RUN_COMPLETED
                    result = event.payload.get("result", {})
                    final_content = str(result.get("final_response", ""))
                elif event.kind == "failed":
                    final_status = RUN_FAILED
                    error = str(event.payload.get("error", ""))
                if run_id in self._cancel_flags:
                    # 流提前结束（runtime 协作取消后 completed/failed 都视为 cancelled）
                    if event.kind in ("completed", "failed"):
                        final_status = RUN_CANCELLED
                        final_content = final_content or str(
                            event.payload.get("result", {}).get("final_response", "")
                        )
                        break
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            final_status = RUN_FAILED
            error = str(exc)
            logger.exception("run 执行异常 run_id=%s", run_id)

        if run_id in self._cancel_flags and final_status in (RUN_COMPLETED, RUN_FAILED):
            final_status = RUN_CANCELLED
        self._cancel_flags.discard(run_id)
        self._cancelled_runtime.discard(run_id)

        if final_status == RUN_CANCELLED:
            if self.repo.transition_run(run_id, to_status=RUN_CANCELLED, error=error):
                self.events.finish(run_id, "cancelled", {"error": error})
            return
        if final_status == RUN_FAILED:
            if self.repo.transition_run(run_id, to_status=RUN_FAILED, error=error):
                self.events.finish(run_id, "failed", {"error": error})
            return
        # completed：终态 + 投影 + 注入 job 同事务
        try:
            ok = self.repo.finish_run_with_projection(
                run_id, to_status=RUN_COMPLETED, final_content=final_content,
                error=None, on_finish=self.on_run_finished,
            )
        except Exception as exc:  # noqa: BLE001  投影失败：保持running待重启对账
            logger.exception("完成投影失败 run_id=%s（重启将标 interrupted 对账）", run_id)
            self.events.publish(run_id, "failed", {"error": f"投影失败: {exc}"})
            return
        if ok:
            self.events.finish(run_id, "completed", {"final_content": final_content})
        else:
            self.events.finish(run_id, "failed", {"error": "终态推进失败（状态竞争）"})

    def _build_request(self, run: dict[str, Any]) -> Any:
        from backend.runtime.contracts import RuntimeRequest
        from backend.shared.context import ExecutionContext, Principal

        owner_id = int(run["owner_id"])
        principal = Principal(user_id=owner_id, role="user", permission_revision=self.access.permission_revision)
        user = self.access.repo.get_user(owner_id)
        role_toolsets = ()
        if user is not None:
            role = self.access.repo.get_role_by_name(user.role)
            role_toolsets = tuple(role.toolsets) if role is not None else ()
        ctx = ExecutionContext(
            run_id=str(run["id"]),
            session_id=str(run["session_id"]),
            principal=principal,
            source=str(run["source"]),
            channel_account_id=run["channel_account_scope"] or None,
            model_profile_id="active",
            policy_revision=self.access.permission_revision,
        )
        return RuntimeRequest(
            context=ctx,
            text=self._input_text(run),
            attachment_ids=tuple(json.loads(run["attachment_ids"] or "[]")),
            system_context="",
            allowed_tools=frozenset(role_toolsets),
            skill_versions=(),
        )

    def _input_text(self, run: dict[str, Any]) -> str:
        """从 UI 投影取该 run 的用户输入（submit 时已落库）。"""
        conn = self.repo.db.connect()
        try:
            row = conn.execute(
                "SELECT content FROM conversations WHERE run_id=? AND role='user' ORDER BY id LIMIT 1",
                (str(run["id"]),),
            ).fetchone()
            return str(row["content"]) if row else str(run["input_summary"] or "")
        finally:
            conn.close()
