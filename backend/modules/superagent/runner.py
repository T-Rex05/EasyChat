"""superagent runner 接缝（T3，方案 §6 工作区和 runner）。

窄接口 CodingRunner：prepare / execute / interrupt。控制端（worker）持有
git、凭证、数据库；runner 只负责"编码会话"（当前实现 = Hermes 独立会话 +
per-session CWD 覆盖；后续可替换为独立进程/容器实现）。

边界约束：
- runner 不接触 GitHub 发布凭证；
- runner 收到的请求携带任务/attempt 快照与已解析的 Principal，不由其读取当前 settings；
- execute 结论以是否观察到 completed 事件为准（runtime 契约），流意外结束 = 失败。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from backend.modules.superagent.contracts import QUESTION_PREFIX
from backend.runtime.contracts import ExecutionContext, RuntimeRequest
from backend.shared.context import Principal

logger = logging.getLogger(__name__)

RUN_TIMEOUT_SECONDS = 4 * 3600  # 单 attempt 总看门狗（覆盖 coding 阶段）

CODING_SYSTEM_PROMPT = """你是 EasyChat 超级代理（superagent）：在一个专用 git 工作区里完成编码任务，控制端会把你的提交推送到远端并自动创建 Draft Pull Request。

工作区与分支（不要质疑、不要改动这些设定）：
- 工作区路径：{workspace}
- 当前分支：{branch}（已基于 {base_branch} 创建）
- 目标仓库：{repo_url}

硬性规则：
1. 只在工作区内改代码；不要 push、不要自己创建 PR、不要改 git 配置、不要切分支。
2. 完成实现后，运行与改动相关的测试/类型检查/构建脚本验证。
3. 不要提交与需求无关的改动；临时文件与日志不要留在工作区。
4. 信息不足或需求不可行时，不要虚构实现：说明缺什么、为什么，并按追问协议输出问题。
5. 全程用中文。

追问协议：需要用户补充信息才能继续时，把你的一句话问题写在最终回复的最后一行，格式：
{question_prefix} 你的问题
（控制端会把问题转给用户；带此行时不要做无关改动。）

完成后用 300 字以内总结：改了什么、为什么这样改、如何验证。"""


@dataclass(frozen=True, slots=True)
class RunnerRequest:
    """一次编码会话请求（数据来自任务与 attempt 快照，不读当前配置）。"""

    task_id: str
    run_id: str
    session_id: str
    principal: Principal
    workspace: Path
    repo_url: str
    branch: str
    base_branch: str
    requirement: str
    extra_inputs: tuple[str, ...] = ()
    context_extra: str = ""
    allowed_tools: frozenset[str] = frozenset({"terminal", "file", "web"})
    timezone: str = "Asia/Shanghai"
    policy_revision: int = 0


@dataclass(slots=True)
class RunnerOutcome:
    """execute 的确定性结论：completed 观察到才算成功。"""

    completed: bool = False
    final_response: str = ""
    error: str = ""
    tool_steps: int = 0
    progress_events: list[dict] = field(default_factory=list)

    def question(self) -> str:
        """按追问协议解析最后一行 QUESTION:；无则空串。"""
        for line in reversed(self.final_response.strip().splitlines()):
            line = line.strip()
            if not line:
                continue
            if line.upper().startswith(QUESTION_PREFIX):
                return line[len(QUESTION_PREFIX):].strip()[:1000]
            return ""  # 最后一行不是 QUESTION: 即无追问
        return ""


class CodingRunner(Protocol):
    async def prepare(self, request: RunnerRequest) -> None: ...
    async def execute(self, request: RunnerRequest) -> RunnerOutcome: ...
    async def interrupt(self, run_id: str) -> None: ...


class HermesCodingRunner:
    """基于既有 ExecutionRuntime 的编码 runner（当前唯一生产实现）。"""

    def __init__(self, runtime, *, run_timeout_seconds: float = RUN_TIMEOUT_SECONDS) -> None:
        self.runtime = runtime
        self.run_timeout_seconds = run_timeout_seconds

    async def prepare(self, request: RunnerRequest) -> None:
        """按 session 注入工作区（业务层 duck-typing，不导入 Hermes 内部）。"""
        prepare = getattr(self.runtime, "prepare_session_workspace", None)
        if prepare is not None:
            prepare(request.session_id, str(request.workspace))

    async def execute(self, request: RunnerRequest) -> RunnerOutcome:
        outcome = RunnerOutcome()
        request_runtime = self._build_request(request)
        try:
            async for event in self.runtime.execute(request_runtime):
                if event.kind == "completed":
                    outcome.completed = True
                    payload = dict(event.payload)
                    result = payload.get("result")
                    if isinstance(result, dict):
                        outcome.final_response = str(result.get("final_response") or "")
                elif event.kind == "failed":
                    outcome.error = str(event.payload.get("error") or "")[:800]
                elif event.kind == "tool_started":
                    outcome.tool_steps += 1
                    outcome.progress_events.append(
                        {"iteration": event.payload.get("iteration"), "tools": list(event.payload.get("tools") or [])}
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001  runtime 抛错 → 确定性失败
            logger.exception("runner execute 异常 run_id=%s", request.run_id)
            outcome.error = outcome.error or str(exc)[:800]
        return outcome

    async def interrupt(self, run_id: str) -> None:
        cancel = getattr(self.runtime, "cancel", None)
        if cancel is None:
            return
        await cancel(run_id)

    # ---- 内部 ------------------------------------------------------------------

    def _build_request(self, request: RunnerRequest) -> RuntimeRequest:
        parts = [request.requirement]
        if request.context_extra:
            parts.append(f"\n补充上下文：\n{request.context_extra}")
        for item in request.extra_inputs:
            parts.append(f"\n用户补充：\n{item}")
        prompt = "\n".join(parts)
        now_local = ""
        try:
            now_local = datetime.now(ZoneInfo(request.timezone)).strftime("%Y-%m-%d %H:%M %Z")
        except Exception:  # noqa: BLE001
            now_local = ""
        system_context = CODING_SYSTEM_PROMPT.format(
            workspace=request.workspace, branch=request.branch,
            base_branch=request.base_branch, repo_url=request.repo_url,
            question_prefix=QUESTION_PREFIX,
        )
        context_prefix = (
            f"当前时间：{now_local}；目标仓库：{request.repo_url}；"
            f"工作分支：{request.branch}（基于 {request.base_branch}）。"
            f"任务编号：{request.task_id}。"
        )
        return RuntimeRequest(
            context=ExecutionContext(
                run_id=request.run_id,
                session_id=request.session_id,
                principal=request.principal,
                source="superagent",
                channel_account_id=None,
                model_profile_id="",
                policy_revision=0,
            ),
            text=prompt,
            attachment_ids=(),
            system_context=system_context,
            allowed_tools=request.allowed_tools,
            skill_versions=(),
            context_prefix=context_prefix,
            persona_context="",
        )
