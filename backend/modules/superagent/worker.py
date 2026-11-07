"""superagent worker：任务表即队列，认领 → 独立会话+工作区执行 → PR → 回信。

对齐 dsh-superagent-prototype 的 Executor 语义：
- 每个任务一次独立 Hermes 会话（新 session_id），工作区经 runtime 的
  可选接缝 prepare_session_workspace 注入（CWD 覆盖按 session 隔离）；
- git 操作全部走 subprocess，凭证只出现在一次性 URL 参数，不落 .git/config；
- 终态与微信回信（delivery 入队）尽力而为，通知失败不改变任务终态；
- 长任务不走共享 jobs 表（执行可达数十分钟，超过 lease 语义）。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from backend.modules.delivery.contracts import DeliveryTarget, target_from_channel
from backend.modules.superagent import github as gh
from backend.modules.superagent.contracts import (
    EVENT_FAILED,
    EVENT_NO_CHANGES,
    EVENT_NOTIFIED,
    EVENT_PR_CREATED,
    EVENT_STARTED,
    SUMMARY_MAX_CHARS,
    TASK_CANCELLED,
    TASK_RUNNING,
    TASK_SUCCEEDED,
    TERMINAL_TASK_STATUSES,
    SuperagentSettings,
    SuperagentTask,
)
from backend.platform.sqlite import utc_now_iso
from backend.runtime.contracts import ExecutionContext, RuntimeRequest
from backend.shared.identifiers import new_run_id, new_session_id

logger = logging.getLogger(__name__)

RUN_TIMEOUT_SECONDS = 4 * 3600  # 单次执行看门狗；Hermes 自身还有迭代预算兜底
GIT_AUTHOR_NAME = "EasyChat Superagent"
GIT_AUTHOR_EMAIL = "superagent@easychat.local"

SYSTEM_PROMPT_TEMPLATE = """你是 EasyChat 超级代理（superagent）：在一个专用 git 工作区里完成编码任务，系统会把你的提交推送到远端并自动创建 Pull Request。

工作区与分支（不要质疑、不要改动这些设定）：
- 工作区路径：{workspace}
- 当前分支：{branch}（已基于 {base_branch} 创建）
- 目标仓库：{repo_url}

硬性规则：
1. 只在工作区内改代码；不要 push、不要自己创建 PR、不要改 git 配置。
2. 完成实现后，如果项目有测试/类型检查/构建脚本，运行与改动相关的部分验证。
3. 不要提交与需求无关的改动；临时文件与日志不要留在工作区。
4. 信息不足或需求不可行时，不要虚构实现，直接说明缺什么、为什么。
5. 全程用中文思考与回复。

完成后用 300 字以内总结：改了什么、为什么这样改、如何验证。"""


GitRunner = Callable[..., Awaitable[tuple[int, str, str]]]


class SuperagentWorker:
    """单 worker 顺序执行；max_concurrent 控制每次 tick 认领数。"""

    def __init__(
        self,
        service: Any,
        *,
        runtime: Any,
        delivery: Any | None,
        channels_provider: Callable[[], Any],
        workspace_root: Path,
        encryption_secret: str,
        pr_client: gh.PRClient | None = None,
        git_runner: GitRunner | None = None,
        clock: Callable[[], float] | None = None,
        poll_seconds: float = 5.0,
        timezone: str = "Asia/Shanghai",
    ) -> None:
        self.service = service
        self.runtime = runtime
        self.delivery = delivery
        self._channels_provider = channels_provider
        self.workspace_root = Path(workspace_root)
        self._encryption_secret = encryption_secret
        self._pr_client = pr_client
        self._git_runner = git_runner
        self._poll_seconds = poll_seconds
        self._timezone = timezone
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()
        self._busy = asyncio.Lock()

    # ---- 生命周期 ----------------------------------------------------------------

    async def start(self) -> None:
        recovered = self.service.recover_interrupted()
        if recovered:
            logger.warning("superagent 启动恢复：中断任务 %s 个已标失败", recovered)
        self._stopped.clear()
        self._task = asyncio.ensure_future(self._loop())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.tick()
            except Exception:  # noqa: BLE001  worker 循环永不退出
                logger.exception("superagent worker tick 失败")
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._poll_seconds)
            except asyncio.TimeoutError:
                pass

    # ---- 主流程 ------------------------------------------------------------------

    async def tick(self) -> int:
        settings = self.service.repo.get_settings()
        if not settings.enabled or not settings.repo_url:
            return 0
        tasks = self.service.claim_due_tasks(max(1, int(settings.max_concurrent)))
        for task in tasks:
            async with self._busy:
                await self._execute(settings, task)
        return len(tasks)

    async def _execute(self, settings: SuperagentSettings, task: SuperagentTask) -> None:
        run_id = new_run_id()
        session_id = new_session_id()
        workspace = self._workspace_for(settings.repo_url)
        branch = task.branch
        self.service.repo.update_fields(task.task_id, run_id=run_id)
        self.service.append_event(
            task.task_id, EVENT_STARTED, f"会话 {session_id[:16]}…；分支 {branch}"
        )
        logger.info("superagent 开始执行 task_id=%s run_id=%s", task.task_id, run_id)
        try:
            token = _decrypt_token(self.service, settings, self._encryption_secret)
            await self._prepare_workspace(settings, workspace, branch, token)
            final_response = await self._run_agent(
                settings, task, run_id, session_id, workspace, branch,
            )
            await self._finalize(settings, task.task_id, workspace, branch, token,
                                 final_response, run_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001  任何失败都落到任务终态
            logger.exception("superagent 任务失败 task_id=%s", task.task_id)
            await self._fail(task.task_id, run_id, str(exc)[:1500])
        finally:
            self._release_workspace(session_id)

    # ---- agent 执行 ----------------------------------------------------------------

    async def _run_agent(
        self, settings: SuperagentSettings, task: SuperagentTask, run_id: str,
        session_id: str, workspace: Path, branch: str,
    ) -> str:
        self._prepare_workspace_binding(session_id, workspace)
        request = self._build_request(settings, task, run_id, session_id, workspace, branch)
        final_response = ""
        async for event in self.runtime.execute(request):
            if event.kind == "completed":
                payload = dict(event.payload)
                result = payload.get("result")
                if isinstance(result, dict):
                    final_response = str(result.get("final_response") or "")
            elif event.kind == "failed":
                raise RuntimeError(f"代理执行失败：{event.payload.get('error', '')}"[:800])
            elif event.kind == "tool_started":
                tools = ", ".join(event.payload.get("tools") or []) or "(内部步骤)"
                self.service.append_event(
                    task.task_id, "progress", f"第 {event.payload.get('iteration', '?')} 步：{tools}"
                )
        if not self._is_live(task.task_id, run_id):
            raise _TaskCancelledError()
        return final_response

    def _build_request(
        self, settings: SuperagentSettings, task: SuperagentTask, run_id: str,
        session_id: str, workspace: Path, branch: str,
    ) -> RuntimeRequest:
        principal = self.service.access.snapshot_principal(task.owner_id)
        system_context = SYSTEM_PROMPT_TEMPLATE.format(
            workspace=workspace, branch=branch,
            base_branch=settings.base_branch, repo_url=settings.repo_url,
        )
        context_prefix = (
            f"当前时间：{self._now_local()}；目标仓库：{settings.repo_url}；"
            f"工作分支：{branch}（基于 {settings.base_branch}）。"
            f"任务编号：{task.task_id}。"
        )
        return RuntimeRequest(
            context=ExecutionContext(
                run_id=run_id,
                session_id=session_id,
                principal=principal,
                source="superagent",
                channel_account_id=None,
                model_profile_id="",
                policy_revision=0,
            ),
            text=task.requirement,
            attachment_ids=(),
            system_context=system_context,
            allowed_tools=frozenset({"terminal", "file", "web"}),
            skill_versions=(),
            context_prefix=context_prefix,
            persona_context=(task.context_extra or ""),
        )

    def _prepare_workspace_binding(self, session_id: str, workspace: Path) -> None:
        """经 runtime 可选接缝注入 per-session 工作区（业务层不导入 Hermes 内部）。"""
        prepare = getattr(self.runtime, "prepare_session_workspace", None)
        if prepare is not None:
            prepare(session_id, str(workspace))

    def _release_workspace(self, session_id: str) -> None:
        release = getattr(self.runtime, "release_session_workspace", None)
        if release is not None:
            try:
                release(session_id)
            except Exception:  # noqa: BLE001
                logger.exception("释放会话工作区失败 session=%s", session_id)

    def _is_live(self, task_id: str, run_id: str) -> bool:
        """执行期间用户可能已取消；取消后不再产出结果。"""
        current = self.service.task(task_id)
        return current is not None and current.status == TASK_RUNNING and current.run_id == run_id

    # ---- git / PR / 收尾 --------------------------------------------------------------

    async def _prepare_workspace(
        self, settings: SuperagentSettings, workspace: Path, branch: str, token: str,
    ) -> None:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        if not (workspace / ".git").is_dir():
            clone_url = gh.push_url_with_token(settings.repo_url, token) if token else settings.repo_url
            await self._git(None, "clone", clone_url, str(workspace))
            await self._git(workspace, "config", "user.name", GIT_AUTHOR_NAME)
            await self._git(workspace, "config", "user.email", GIT_AUTHOR_EMAIL)
        fetch_url = gh.push_url_with_token(settings.repo_url, token) if token else "origin"
        await self._git(workspace, "fetch", fetch_url, "+refs/heads/*:refs/remotes/origin/*", "--prune", "--force")
        await self._git(workspace, "checkout", "-f", "-B", branch, f"origin/{settings.base_branch}")
        await self._git(workspace, "clean", "-fd")

    async def _finalize(
        self, settings: SuperagentSettings, task_id: str, workspace: Path, branch: str,
        token: str, final_response: str, run_id: str,
    ) -> None:
        if not self._is_live(task_id, run_id):
            raise _TaskCancelledError()
        status_out = await self._git(workspace, "status", "--porcelain")
        has_changes = bool(status_out[1].strip())
        summary = (final_response or "").strip()[:SUMMARY_MAX_CHARS]
        pr_url = ""
        if has_changes:
            commit_message = f"{self._title_of(task_id)}\n\n由 EasyChat 超级代理提交（任务 {task_id}）"
            await self._git(workspace, "add", "-A")
            await self._git(workspace, "commit", "-m", commit_message)
            if token:
                push_url = gh.push_url_with_token(settings.repo_url, token)
                await self._git(workspace, "push", push_url, f"refs/heads/{branch}:refs/heads/{branch}")
            else:
                raise RuntimeError("未配置 GitHub 凭证，无法推送分支；请在超级代理配置中保存 token 后重试")
            pr = await self._create_pr(settings, task_id, branch, summary, token)
            pr_url = pr.html_url
            self.service.repo.update_fields(
                task_id, status=TASK_SUCCEEDED, pr_url=pr_url, pr_number=pr.number,
                result_summary=summary, finished_at=utc_now_iso(),
            )
            self.service.append_event(task_id, EVENT_PR_CREATED, pr_url)
        else:
            self.service.repo.update_fields(
                task_id, status=TASK_SUCCEEDED, result_summary=summary,
                finished_at=utc_now_iso(),
            )
            self.service.append_event(
                task_id, EVENT_NO_CHANGES, "代理未产生代码变更（见结果摘要）"
            )
        task = self.service.task(task_id)
        if task is not None:
            await self._notify(task, has_changes)

    async def _create_pr(
        self, settings: SuperagentSettings, task_id: str, branch: str, summary: str,
        token: str,
    ) -> gh.PullRequest:
        client = self._pr_client
        if client is None:
            client = gh.HttpxPRClient(token=token)
        title = self._title_of(task_id)
        body_parts = [f"## 需求", ""]
        task = self.service.task(task_id)
        requirement = task.requirement if task else ""
        body_parts += [requirement[:4000], ""]
        if summary:
            body_parts += ["## 代理摘要", "", summary]
        body_parts += ["", "---", f"由 EasyChat 超级代理自动创建（任务 {task_id}）"]
        return await client.create_pull_request(
            repo_url=settings.repo_url, title=title, head=branch,
            base=settings.base_branch, body="\n".join(body_parts),
        )

    async def _notify(self, task: SuperagentTask, has_changes: bool) -> None:
        if self.delivery is None:
            return
        channels = self._channels_provider()
        resolved = channels.delivery_target_for_owner(task.owner_id) if channels else None
        if resolved is None:
            return
        text = self._notify_text(task, has_changes)
        try:
            self.delivery.enqueue_text(
                owner_id=task.owner_id,
                target=target_from_channel(resolved) if not isinstance(resolved, DeliveryTarget) else resolved,
                text=text,
                dedup_key=f"superagent:{task.task_id}:notify",
                source="superagent",
            )
            self.service.append_event(task.task_id, EVENT_NOTIFIED, "回执已进入投递队列")
        except Exception:  # noqa: BLE001  通知失败不影响终态
            logger.exception("superagent 回执入队失败 task_id=%s", task.task_id)

    @staticmethod
    def _notify_text(task: SuperagentTask, has_changes: bool) -> str:
        if task.status == TASK_SUCCEEDED and has_changes and task.pr_url:
            lines = [f"✅ 编码任务完成：{task.title}", f"分支：{task.branch}", f"PR：{task.pr_url}"]
            if task.result_summary:
                lines += ["", task.result_summary[:400]]
            return "\n".join(lines)
        if task.status == TASK_SUCCEEDED:
            lines = [f"✅ 编码任务完成（无代码变更）：{task.title}", ""]
            lines.append(task.result_summary[:600] or "代理没有发现需要改动的地方。")
            return "\n".join(lines)
        return f"❌ 编码任务失败：{task.title}\n\n{(task.error or '未知原因')[:400]}\n\n可在 Web 面板重试。"

    async def _fail(self, task_id: str, run_id: str, error: str) -> None:
        current = self.service.task(task_id)
        if current is not None and current.status in TERMINAL_TASK_STATUSES:
            return  # 已取消/已终态：不覆盖
        self.service.repo.update_fields(
            task_id, status="failed", error=error, finished_at=utc_now_iso(),
        )
        self.service.append_event(task_id, EVENT_FAILED, error[:500])
        task = self.service.task(task_id)
        if task is not None:
            await self._notify(task, False)

    # ---- git subprocess -----------------------------------------------------------

    async def _git(self, cwd: Path | None, *args: str) -> tuple[int, str]:
        runner = self._git_runner
        if runner is not None:
            code, out, err = await runner(cwd, *args)
        else:
            code, out, err = await _run_git(cwd, *args)
        if code != 0:
            raise RuntimeError(f"git {' '.join(args[:2])} 失败：{(err or out).strip()[:500]}")
        return code, out

    def _workspace_for(self, repo_url: str) -> Path:
        _, full_name = gh.parse_repo_full_name(repo_url)
        safe = full_name.replace("/", "__")
        return self.workspace_root / safe

    def _title_of(self, task_id: str) -> str:
        task = self.service.task(task_id)
        return task.title if task else "superagent change"

    def _now_local(self) -> str:
        return datetime.now(ZoneInfo(self._timezone)).strftime("%Y-%m-%d %H:%M %Z")


class _TaskCancelledError(RuntimeError):
    pass


async def _run_git(cwd: Path | None, *args: str) -> tuple[int, str, str]:
    """真实 git subprocess：stdout/stderr 全量捕获，不进 shell。"""
    process = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(cwd) if cwd is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return (
        int(process.returncode or 0),
        stdout.decode("utf-8", "replace"),
        stderr.decode("utf-8", "replace"),
    )


def _decrypt_token(service: Any, settings: SuperagentSettings, encryption_secret: str) -> str:
    """密文只存在 repo；worker 内存中解密，明文不落任何存储。"""
    from backend.modules.superagent.api import decrypt_github_token  # noqa: PLC0415

    if not settings.has_github_token:
        return ""
    token_enc = service.repo.get_token_encrypted()
    if not token_enc:
        return ""
    return decrypt_github_token(token_enc, encryption_secret)
