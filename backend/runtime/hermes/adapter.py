"""Hermes Runtime Adapter：ExecutionRuntime 的唯一 Hermes 整合入口（架构 §4.1）。

- 线程/回调转换：run_conversation（同步）在线程池执行，回调经队列桥接为
  RuntimeEvent 异步流；ContextVar 用 copy_context 传播到工作线程。
- Agent 缓存键含 owner/session、模型配置版本、权限/策略版本、技能摘要；
  LRU 有界（默认 8 / 闲置 15 分钟）；正在执行的实例不回收。
- 取消走 Hermes 协作式 interrupt，不用 asyncio task.cancel。
- 业务层不得导入本模块以外的任何 Hermes 内部模块。
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import queue
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from backend.runtime.contracts import ExecutionRuntime, RuntimeEvent, RuntimeRequest
from backend.runtime.hermes.usage_bridge import begin_for_run, complete_for_run, diff, snapshot

logger = logging.getLogger(__name__)

DEFAULT_AGENT_CACHE_SIZE = 8
DEFAULT_IDLE_TTL_SECONDS = 900


@dataclass
class _AgentHandle:
    key: tuple
    agent: Any
    last_used: float = field(default_factory=time.monotonic)
    running: bool = False
    model_provider: str = ""
    model_name: str = ""


class HermesRuntimeAdapter(ExecutionRuntime):
    """唯一 Hermes 整合点。agent_factory 可注入（测试替身/远程实现）。"""

    def __init__(
        self,
        *,
        hermes_home: Path,
        agent_factory: Callable[[RuntimeRequest, dict[str, Any]], Any] | None = None,
        runner: Callable[[Any, RuntimeRequest, Callable, Callable, Callable], dict] | None = None,
        usage: Any | None = None,
        models: Any | None = None,
        cache_size: int = DEFAULT_AGENT_CACHE_SIZE,
        idle_ttl_seconds: int = DEFAULT_IDLE_TTL_SECONDS,
    ) -> None:
        self.hermes_home = Path(hermes_home)
        self._agent_factory = agent_factory  # None → 启动期解析真实 Hermes 工厂
        self._runner = runner  # None → 启动期解析 run_conversation
        self.usage = usage
        self.models = models
        self.cache_size = cache_size
        self.idle_ttl_seconds = idle_ttl_seconds
        self._cache: OrderedDict[tuple, _AgentHandle] = OrderedDict()
        self._by_run: dict[str, _AgentHandle] = {}
        self._closed = False
        self._started = False

    # ---- 生命周期 ----------------------------------------------------------------

    async def startup(self) -> None:
        """显式启动（lifespan 调用）：环境引导、安全工具注册、真实工厂解析。"""
        if self._started:
            return
        from backend.runtime.hermes.paths import ensure_hermes_environment

        ensure_hermes_environment(self.hermes_home)
        from backend.runtime.hermes import tools as hermes_tools

        hermes_tools.register_safe_project_tools(thread_context_provider=self._current_thread_id)
        if self._agent_factory is None:
            self._agent_factory = self._default_agent_factory
        if self._runner is None:
            from agent.conversation_loop import run_conversation  # noqa: PLC0415  (Hermes 顶层模块)

            self._runner = self._default_runner(run_conversation)
        self._started = True

    def _current_thread_id(self) -> str | None:
        return getattr(self, "_current_thread_ctx", None)

    def register_extra_tools(self, tools: Any) -> int:
        """注册 bootstrap 构造的业务工具（提醒/账本/收件箱等）。

        必须在 Assistant worker 与渠道监听启动前调用；重复调用幂等。
        """
        from backend.runtime.hermes import tools as hermes_tools

        hermes_tools._ensure_hermes_loaded()
        return hermes_tools.register_safe_project_tools(
            thread_context_provider=self._current_thread_id,
            extra_tools=list(tools or ()),
        )

    # ---- 会话工作区（superagent 等独立工作区执行方） --------------------------------

    def prepare_session_workspace(self, session_id: str, workspace: str) -> None:
        """把 session 的工具工作目录锚定到 workspace（terminal/file 的 CWD 覆盖）。

        键是 AIAgent 的 session_id（顶层工具调用的 task_id）；CWD-only 覆盖
        共享 default 容器，不触发沙箱隔离。业务层经 duck-typing 调用，
        不导入 Hermes 内部模块。
        """
        from backend.runtime.hermes.paths import ensure_hermes_environment

        ensure_hermes_environment(self.hermes_home)
        from tools.terminal_tool import register_task_env_overrides  # noqa: PLC0415

        register_task_env_overrides(session_id, {"cwd": str(workspace)})

    def release_session_workspace(self, session_id: str) -> None:
        from tools.terminal_tool import clear_task_env_overrides  # noqa: PLC0415

        clear_task_env_overrides(session_id)

    # ---- Agent 缓存 ----------------------------------------------------------------

    def _cache_key(self, request: RuntimeRequest, profile: dict[str, Any] | None = None) -> tuple:
        """缓存键：owner/session、模型配置版本、权限/策略版本、技能摘要。

        同 session 不同 owner、模型/权限/技能版本不同 → 不同 Agent，禁止复用。
        """
        ctx = request.context
        profile = profile if profile is not None else self._resolve_model(request)
        skills_digest = ",".join(f"{name}@{ver}" for name, ver in request.skill_versions)
        return (
            ctx.principal.user_id,
            ctx.session_id,
            ctx.model_profile_id,
            ctx.policy_revision,
            ctx.principal.permission_revision,
            request.allowed_tools and frozenset(request.allowed_tools) or frozenset(),
            skills_digest,
            (profile.get("profile_id"), profile.get("config_version"),
             profile.get("fallback_versions", ())),
        )

    def _acquire(self, request: RuntimeRequest) -> _AgentHandle:
        self._evict_idle()
        profile = self._resolve_model(request)
        key = self._cache_key(request, profile)
        handle = self._cache.get(key)
        if handle is not None:
            self._cache.move_to_end(key)
            handle.last_used = time.monotonic()
            return handle
        agent = self._agent_factory(request, profile)
        handle = _AgentHandle(key=key, agent=agent,
                              model_provider=str(profile.get("provider", "")),
                              model_name=str(profile.get("model", "")))
        self._cache[key] = handle
        while len(self._cache) > self.cache_size:
            self._evict_one()
        return handle

    def _resolve_model(self, request: RuntimeRequest) -> dict[str, Any]:
        if self.models is not None:
            selection = self.models.select_for_run(auxiliary=True)
            profile = selection.chat
            return {
                "config_type": "URL",
                "base_url": profile.base_url,
                "api_key": None,  # 密钥由模型 Adapter 层解密注入（见 _default_agent_factory）
                "model": profile.model,
                "provider": profile.provider,
                "profile_id": profile.config_id,
                "config_version": profile.config_version,
                "fallback_versions": tuple(
                    (fallback.config_id, fallback.config_version)
                    for fallback in selection.fallback
                ),
            }
        return {"config_type": "URL", "base_url": "", "api_key": None, "model": "", "provider": ""}

    def _evict_idle(self) -> None:
        now = time.monotonic()
        stale = [k for k, h in self._cache.items()
                 if not h.running and now - h.last_used > self.idle_ttl_seconds]
        for k in stale:
            self._cache.pop(k, None)

    def _evict_one(self) -> None:
        for k, h in self._cache.items():  # LRU 顺序；跳过运行中的活跃实例
            if not h.running:
                self._cache.pop(k, None)
                return

    # ---- 执行 ----------------------------------------------------------------------

    async def execute(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]:
        if self._closed:
            raise RuntimeError("runtime 已关闭")
        if not self._started:
            await self.startup()
        loop = asyncio.get_running_loop()
        handle = self._acquire(request)
        handle.running = True
        self._by_run[request.context.run_id] = handle
        events: queue.Queue = queue.Queue()

        pre = snapshot(handle.agent)
        call_id = begin_for_run(
            self.usage,
            owner_id=request.context.principal.user_id,
            source=request.context.source if request.context.source in ("chat", "memory", "evolution", "schedule", "superagent") else "chat",
            provider=handle.model_provider,
            model=handle.model_name,
            run_id=request.context.run_id,
            session_id=request.context.session_id,
        )

        def on_delta(text: str) -> None:
            events.put(("token", {"text": text}))

        def on_reasoning(text: str) -> None:
            events.put(("thinking", {"text": text}))

        def on_step(iteration: int, prev_tools: Any) -> None:
            events.put(("tool_started", {"iteration": iteration, "tools": _safe_tools(prev_tools)}))

        def _sync_run() -> None:
            # 审计 #2：服务端 run 无人值守，Hermes 的非交互分支会默认放行全部
            # 需审批命令。这里显式离开该分支（interactive 上下文）并注册自动
            # 拒绝回调——良性命令照常执行，被 tirith/危险命令检测标记的命令
            # 一律拒绝；线程本地状态在 finally 里恢复。
            interactive_token = None
            approval_installed = False
            try:
                from tools import terminal_tool
                from tools.approval import reset_hermes_interactive_context, set_hermes_interactive_context

                def _deny_unattended(command, description, **kwargs) -> str:
                    logger.warning(
                        "命令需人工审批但服务端无审批通道，已拒绝 run_id=%s: %s (%s)",
                        request.context.run_id, str(command)[:160], str(description)[:200],
                    )
                    return "deny"

                # 顺序不可换：回调必须先于 interactive 上下文就位，否则装配
                # 中途失败会留下"交互模式+无回调"，内核会走 input() 兜底挂起。
                terminal_tool.set_approval_callback(_deny_unattended)
                interactive_token = set_hermes_interactive_context(True)
                approval_installed = True
            except Exception:  # noqa: BLE001  审批装配失败时拒绝兜底由调用方保证
                logger.exception("审批通道装配失败 run_id=%s；本轮命令按内核默认处理", request.context.run_id)
            try:
                result = self._runner(handle.agent, request, on_delta, on_reasoning, on_step)
                post = snapshot(handle.agent)
                delta = diff(pre, post)
                complete_for_run(
                    self.usage,
                    call_id,
                    delta=delta,
                    model=handle.model_name,
                    estimated=bool(request.text),
                )
                events.put(("completed", {"result": _safe_result(result), "api_calls": delta.get("session_api_calls", 0)}))
            except BaseException as exc:  # noqa: BLE001  桥接层必须把失败转成事件
                logger.exception("run 执行失败 run_id=%s", request.context.run_id)
                events.put(("failed", {"error": str(exc)}))
            finally:
                if approval_installed:
                    try:
                        from tools import terminal_tool
                        from tools.approval import reset_hermes_interactive_context

                        terminal_tool.set_approval_callback(None)
                        if interactive_token is not None:
                            reset_hermes_interactive_context(interactive_token)
                    except Exception:  # noqa: BLE001  线程本地清理尽力而为
                        logger.exception("审批通道清理失败 run_id=%s", request.context.run_id)
                events.put(None)

        worker_ctx = contextvars.copy_context()
        task = loop.run_in_executor(None, lambda: worker_ctx.run(_sync_run))
        try:
            while True:
                item = await loop.run_in_executor(None, events.get)
                if item is None:
                    break
                kind, payload = item
                yield RuntimeEvent(kind=kind, payload=payload)
                if kind in ("completed", "failed"):
                    break
            await task
        finally:
            handle.running = False
            self._by_run.pop(request.context.run_id, None)

    async def cancel(self, run_id: str) -> None:
        """协作式取消：interrupt 当前请求并中断子 Agent；不宣称同步工具被强杀。"""
        handle = self._by_run.get(run_id)
        if handle is None:
            return
        agent = handle.agent
        try:
            agent.interrupt("用户请求取消")
        except Exception:  # noqa: BLE001
            logger.exception("interrupt 失败 run_id=%s", run_id)
        subagents = list(getattr(agent, "_active_subagents", []) or [])
        if not subagents:
            return  # 没有子 Agent 时不为尽力而为的中断导入 Hermes 内部模块
        try:
            # 陷阱 #3：必须先引导 sys.path/HERMES_HOME 再导入 Hermes 顶层模块
            from backend.runtime.hermes.paths import ensure_hermes_environment

            ensure_hermes_environment(self.hermes_home)
            from tools.delegate_tool import interrupt_subagent  # noqa: PLC0415

            for sid in subagents:
                interrupt_subagent(sid)
        except Exception:  # noqa: BLE001  子Agent中断为尽力而为
            pass

    async def aclose(self) -> None:
        self._closed = True
        self._cache.clear()
        self._by_run.clear()

    # ---- 真实 Hermes 工厂（仅 startup 后存在） -------------------------------------

    def _default_agent_factory(self, request: RuntimeRequest, profile: dict[str, Any]) -> Any:
        from backend.runtime.hermes.agent_factory import build_agent

        return build_agent(request, profile, hermes_home=self.hermes_home, models=self.models)

    def _default_runner(self, run_conversation: Callable) -> Callable:
        def _run(agent, request, on_delta, on_reasoning, on_step) -> dict:
            agent.stream_delta_callback = on_delta
            agent.reasoning_callback = on_reasoning
            agent.step_callback = on_step
            # 人格/记忆/附件是每轮易变的上下文：走 ephemeral_system_prompt 与
            # 合成 user message，绝不写进会持久化的 system_message。
            combined_system = "\n\n".join(
                part.strip() for part in (request.system_context, request.persona_context) if part.strip()
            )
            agent.ephemeral_system_prompt = combined_system or None
            user_message = request.text
            if request.context_prefix.strip():
                user_message = f"{request.context_prefix.strip()}\n\n{request.text}"
            try:
                # 会话连续性由 agent 绑定的 SessionDB（state.db）提供；
                # UI 投影历史不得在此拼接（架构 §5.1：conversations 仅是投影）。
                return run_conversation(
                    agent,
                    user_message,
                    system_message=None,
                    persist_user_message=request.persist_user_message or request.text,
                )
            finally:
                agent.stream_delta_callback = None
                agent.reasoning_callback = None
                agent.step_callback = None

        return _run


def _safe_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"final_response": str(result)}
    return {
        "final_response": str(result.get("final_response", "")),
        "completed": bool(result.get("completed", True)),
    }


def _safe_tools(prev_tools: Any) -> list[str]:
    try:
        names = []
        for t in prev_tools or []:
            name = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
            if name:
                names.append(str(name))
        return names
    except Exception:  # noqa: BLE001
        return []
