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
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

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
        profiles: Any = None,
        memory: Any = None,
        poll_interval: float = 0.05,
    ) -> None:
        self.repo = repo
        self.events = events
        self.runtime = runtime
        self.models = models
        self.access = access
        self.on_run_finished = on_run_finished
        # 由 bootstrap 晚绑定，避免 assistant 构造早于 profiles/memory。
        self.profiles = profiles
        self.memory = memory
        self.skills = None  # bootstrap 晚绑定（assistant 先装配、skills 后装配）
        # 由 bootstrap 晚绑定（channels 装配后）：session → 渠道来源标识；
        # ToolContext 携带后业务工具可固定任务回执目标。
        self.source_for_session: Callable[[str], dict[str, str] | None] | None = None
        # bootstrap 晚绑定（P4）：principal → 已启用且对其可见的 MCP 工具组名，
        # 逐 run 并入 allowed_tools；audience 门控在服务层完成。
        self.mcp_grantor: Callable[[Any], tuple[str, ...]] | None = None
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
        """启动对账：上一进程遗留的 running/cancel_requested 标 interrupted。

        缺陷②：中断也必须走终态回调——微信用户此前对遗留 run 永远无回应。
        """
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
            if self.repo.finish_terminal(
                run_id, to_status=RUN_INTERRUPTED,
                error="进程重启，执行中断（已保留检查点，不自动重跑）",
                on_finish=self.on_run_finished,
            ):
                self.events.finish(run_id, "interrupted", {"reason": "process_restart"})
                recovered += 1
        return recovered

    # ---- 取消 ------------------------------------------------------------------

    def _source_extra(self, session_id: str) -> dict[str, str]:
        """服务端来源查询（channels 晚绑定）；查询失败不阻塞 run。"""
        lookup = self.source_for_session
        if lookup is None or not session_id:
            return {}
        try:
            route = lookup(session_id)
            return route if isinstance(route, dict) else {}
        except Exception:  # noqa: BLE001
            logger.exception("来源查询失败 session=%s", session_id)
            return {}

    async def request_cancel(self, run_id: str) -> str:
        status = self.repo.request_cancel(run_id, on_finish=self.on_run_finished)
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
            if self.repo.finish_terminal(
                run_id, to_status=RUN_FAILED, error=error[:500],
                on_finish=self.on_run_finished,
            ):
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

        try:
            request = self._build_request(run)
        except Exception as exc:  # noqa: BLE001  身份失效/配置损坏必须明确失败
            logger.exception("构建 run 请求失败 run_id=%s", run_id)
            if self.repo.finish_terminal(
                run_id, to_status=RUN_FAILED, error=str(exc)[:500],
                on_finish=self.on_run_finished,
            ):
                self.events.finish(run_id, "failed", {"error": str(exc)[:500]})
            return

        from backend.shared.tool_context import ToolContext, reset_current, set_current

        source_extra = self._source_extra(request.context.session_id)
        tool_context = ToolContext(
            principal=request.context.principal,
            run_id=request.context.run_id,
            session_id=request.context.session_id,
            source=request.context.source,
            channel_account_id=request.context.channel_account_id,
            source_ref=str(source_extra.get("external_user_id") or ""),
            source_chat_id=str(source_extra.get("external_chat_id") or ""),
        )
        token = set_current(tool_context)
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
        finally:
            reset_current(token)

        if run_id in self._cancel_flags and final_status in (RUN_COMPLETED, RUN_FAILED):
            final_status = RUN_CANCELLED
        self._cancel_flags.discard(run_id)
        self._cancelled_runtime.discard(run_id)

        # 缺陷②：failed/cancelled 与 completed 对称，状态推进和可读回执
        # 入队同事务（finish_terminal 内条件 UPDATE 保证重复终态不双发）。
        if final_status == RUN_CANCELLED:
            if self.repo.finish_terminal(
                run_id, to_status=RUN_CANCELLED, error=error,
                on_finish=self.on_run_finished,
            ):
                self.events.finish(run_id, "cancelled", {"error": error})
            return
        if final_status == RUN_FAILED:
            if self.repo.finish_terminal(
                run_id, to_status=RUN_FAILED, error=error,
                on_finish=self.on_run_finished,
            ):
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
        from backend.runtime.contracts import ALWAYS_AVAILABLE_TOOLSET, RuntimeRequest
        from backend.shared.context import ExecutionContext

        owner_id = int(run["owner_id"])
        # 唯一可信身份来源：数据库中的当前用户/状态/角色；禁用用户在此拒绝，
        # 不能回落到默认 user 0 或模型传入的 user_id。
        principal = self.access.snapshot_principal(owner_id)
        self.access.require_permission(principal, "chat.use")
        role_toolsets = self.access.hermes_toolsets(owner_id)
        # P4：MCP 工具组逐 run 注入（audience=config_admin 仅系统配置者，
        # audience=all 面向所有登录用户）。判定失败按不授予处理。
        grantor = self.mcp_grantor
        if grantor is not None:
            try:
                granted = tuple(grantor(principal))
            except Exception:  # noqa: BLE001
                logger.exception("MCP 工具组获取失败 run=%s（本轮不授予）", run["id"])
                granted = ()
            if granted:
                role_toolsets = tuple(set(role_toolsets) | set(granted))
        source = str(run["source"])
        text = self._input_text(run)
        persona_context = ""
        timezone_name = "Asia/Shanghai"
        if self.profiles is not None:
            try:
                profile = self.profiles.get_by_owner(owner_id)
                timezone_name = profile.timezone
                persona_context = self.profiles.render_persona(
                    owner_id, "wechat" if source == "wechat" else "web"
                )
            except Exception:  # noqa: BLE001  人格失败不阻塞回答
                logger.exception("人格渲染失败 owner=%s", owner_id)

        attachment_ids = tuple(json.loads(run["attachment_ids"] or "[]"))

        # WP-C: 已激活技能按 owner 快照注入本轮（版本固定，激活/回滚只影响下一轮）。
        skill_context = ""
        skill_versions: tuple[tuple[str, str], ...] = ()
        if self.skills is not None:
            try:
                snaps = self.skills.list_for_runtime(principal)
                parts = []
                budget = 16000
                for snap in snaps:
                    block = "\n".join((f"### {snap.name}", snap.description, snap.content))
                    if len(block) > budget:
                        # 超预算截断注入而非整体跳过：激活内容必须实际进入请求
                        # （来源/许可头在文首，截断后保留）；完整正文可在技能页查看。
                        block = block[:budget] + "\n（内容超出预算已截断；完整版见技能页）"
                    parts.append(block)
                    budget -= len(block)
                    if budget <= 0:
                        break
                if parts:
                    skill_context = "已激活技能（本轮固定版本）：\n\n" + "\n\n".join(parts)
                skill_versions = tuple((s.name, str(s.version_seq)) for s in snaps)
            except Exception:  # noqa: BLE001  技能加载失败不阻塞对话
                logger.exception("技能快照加载失败 owner=%s", owner_id)

        prefix = self._context_prefix(
            owner_id, str(run["id"]), text, attachment_ids, source, timezone_name
        )

        ctx = ExecutionContext(
            run_id=str(run["id"]),
            session_id=str(run["session_id"]),
            principal=principal,
            source=source,
            channel_account_id=run["channel_account_scope"] or None,
            model_profile_id="active",
            policy_revision=self.access.permission_revision,
        )
        return RuntimeRequest(
            context=ctx,
            text=text,
            attachment_ids=attachment_ids,
            system_context=skill_context,
            # 对话 run 显式启用项目工具组（内核无自动包含；权限由 service 层
            # 逐操作校验，__always_available__ 只表示 schema 可见）。
            allowed_tools=frozenset(role_toolsets) | {ALWAYS_AVAILABLE_TOOLSET},
            skill_versions=skill_versions,
            persona_context=persona_context,
            context_prefix=prefix,
            persist_user_message=text,
        )

    def _context_prefix(
        self,
        owner_id: int,
        run_id: str,
        text: str,
        attachment_ids: tuple[str, ...],
        source: str,
        timezone_name: str,
    ) -> str:
        """当前时间 + 附件元数据 + 记忆召回；只放易变上下文。"""
        try:
            now = datetime.now(ZoneInfo(timezone_name))
            weekday = "一二三四五六日"[now.weekday()]
            lines = [f"【当前】{now:%Y-%m-%d %H:%M}，周{weekday}，{timezone_name}"]
        except Exception:  # noqa: BLE001
            lines = [f"【当前】{datetime.now():%Y-%m-%d %H:%M}"]
        if attachment_ids:
            try:
                attachments = self.repo.attachments_by_ids(owner_id, attachment_ids)
                if attachments:
                    lines.append("【附件】")
                    for index, item in enumerate(attachments, 1):
                        name = _safe_attachment_name(str(item.get("file_name") or "附件"))
                        file_id = str(item.get("stored_file_id") or "")
                        suffix = f"，file_id={file_id}" if file_id else ""
                        lines.append(
                            f"{index}. {name} attachment_id={item['id']}{suffix}"
                            f"（{item.get('mime') or '未知类型'}，已保存）"
                        )
            except Exception:  # noqa: BLE001
                logger.exception("附件元数据读取失败 run=%s", run_id)
        if source in ("web", "wechat") and self.memory is not None:
            try:
                principal = self.access.snapshot_principal(owner_id)
                recalled = self.memory.recall(
                    principal, text[:500], top_k=3, token_budget=800
                )
                if recalled.items:
                    lines.append("【可能是相关的记忆，未必准确；自然使用，不要逐条复述】")
                    for index, item in enumerate(recalled.items, 1):
                        memory = item.memory
                        lines.append(f"{index}. [{memory.kind}] {memory.content}")
            except Exception:  # noqa: BLE001  记忆失败只跳过
                logger.warning("记忆召回失败 owner=%s run=%s", owner_id, run_id)
        return "\n".join(lines)

    def _input_text(self, run: dict[str, Any]) -> str:  # noqa: D401
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


def _safe_attachment_name(name: str) -> str:
    """附件名是不可信输入：去控制字符、压平空白、截断 80 字。"""
    cleaned = "".join(ch for ch in name if ch.isprintable() and ch not in "\r\n\t")
    return " ".join(cleaned.split())[:80] or "附件"
