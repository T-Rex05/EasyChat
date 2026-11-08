"""superagent worker：以 attempt 为单位执行任务（T1–T4）。

执行链（方案 §6 Git 发布）：
  claim（一次一个，真实并发=1）→ preparing（无凭证 remote + credential helper
  clone/fetch、记录 base_sha）→ coding（CodingRunner 独立会话，必须观察到
  completed）→ verifying（控制端执行验证命令，证据落工件）→ publishing
  （工作树与 base_sha...HEAD 双比较、控制端提交、publish intent 先落库、
  credential helper push、PR 查询复用/创建 Draft）→ 终态+报告+回执同事务。

边界与恢复：
- 取消：cancel_requested 在每个 phase 边界生效；push 已发出后到达的取消
  记录 cancelled_after_publication 并完成对账（已发布动作以远端结果为准）；
- 发布检查点按 prepared/coded/verified/push_intent/pushed/pr_intent/pr_created
  推进；push 成功后崩溃 → 重试新 attempt 时按 remote 分支与已有 PR 对账复用；
- 凭证：git 远端无凭证 URL；token 只进 git 子进程环境（credential helper），
  不进 URL、.git/config、argv；所有错误文本出口脱敏；
- 超时：git 子进程、验证命令、编码会话分别限时，超时回收进程树；
- 权限：执行前与发布前重新检查 owner 的 superagent.create（撤销即 blocked）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess as sp
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from backend.modules.delivery.contracts import DeliveryTarget, target_from_channel
from backend.modules.superagent import credentials as cred
from backend.modules.superagent import github as gh
from backend.modules.superagent.contracts import (
    CK_CODED,
    CK_PREPARED,
    CK_PR_CREATED,
    CK_PR_INTENT,
    CK_PUSH_INTENT,
    CK_PUSHED,
    CK_VERIFIED,
    EVENT_CANCELLED_AFTER_PUBLICATION,
    PHASE_CODING,
    PHASE_PREPARING,
    PHASE_PUBLISHING,
    PHASE_VERIFYING,
    REPORT_BLOCKED,
    REPORT_FAILED,
    REPORT_NO_CHANGES,
    REPORT_QUESTION,
    REPORT_READY,
    SUMMARY_MAX_CHARS,
    TASK_AWAITING_REVIEW,
    TASK_BLOCKED,
    TASK_CANCELLED,
    TASK_CANCEL_REQUESTED,
    TASK_FAILED,
    TASK_RUNNING,
    TASK_SUCCEEDED,
    TASK_WAITING_INPUT,
    SuperagentTask,
    TaskAttempt,
)
from backend.modules.superagent.credentials import (
    credential_helper_gitconfig,
    credential_helper_source,
    git_auth_env,
    parse_repo_url,
    sanitize_text,
)
from backend.modules.superagent.verification import load_verify_commands, run_verification
from backend.modules.superagent.workspaces import workspace_key, workspace_path
from backend.platform.sqlite import utc_now_iso

logger = logging.getLogger(__name__)

# ---- 超时预算（T3） -----------------------------------------------------------

GIT_CLONE_TIMEOUT = 600.0
GIT_FETCH_TIMEOUT = 600.0
GIT_PUSH_TIMEOUT = 300.0
GIT_DEFAULT_TIMEOUT = 120.0
POLL_SECONDS = 5.0
GIT_AUTHOR_NAME = "EasyChat Superagent"
GIT_AUTHOR_EMAIL = "superagent@easychat.local"

# 注入式 git runner 的签名：(cwd, git_args, env_extra, timeout, *args) -> (code, out, err)
GitRunner = Callable[..., Awaitable[tuple[int, str, str]]]


class TaskCancelledError(RuntimeError):
    """phase 边界检测到取消请求。"""


class _TaskBlockedError(RuntimeError):
    """缺少凭证/权限等受阻条件（转 blocked 而非 failed）。"""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(slots=True)
class _PublishContext:
    """发布边界需要的解析结果（一次解析，处处使用）。"""

    ref: Any
    workspace: Path
    branch: str
    base_branch: str
    token: str
    git_args: tuple[str, str]
    env_extra: dict[str, str]


class SuperagentWorker:
    """单 worker 顺序执行；真实并发固定 1（方案 §6：并行开放前必须完成隔离）。"""

    def __init__(
        self,
        service: Any,
        *,
        runner: Any,
        delivery: Any | None,
        channels_provider: Callable[[], Any],
        workspace_root: Path,
        artifacts_root: Path,
        pr_client_factory: Callable[[str], gh.PRClient] | None = None,
        git_runner: GitRunner | None = None,
        poll_seconds: float = POLL_SECONDS,
        timezone: str = "Asia/Shanghai",
    ) -> None:
        self.service = service
        self.runner = runner
        self.delivery = delivery
        self._channels_provider = channels_provider
        self.workspace_root = Path(workspace_root)
        self.artifacts_root = Path(artifacts_root)
        self._pr_client_factory = pr_client_factory
        self._git_runner = git_runner
        self._poll_seconds = poll_seconds
        self._timezone = timezone
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()
        self._helper_dir: tempfile.TemporaryDirectory | None = None

    # ---- 生命周期 ----------------------------------------------------------------

    async def start(self) -> None:
        recovered = self.service.recover_interrupted()
        if recovered:
            logger.warning("superagent 启动恢复：中断任务 %s 个已标 interrupted", recovered)
        self._sanitize_legacy_remotes()
        self._helper_dir = tempfile.TemporaryDirectory(prefix="easychat-gitcred-")
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
        if self._helper_dir is not None:
            self._helper_dir.cleanup()
            self._helper_dir = None

    def _helper_path(self) -> str:
        assert self._helper_dir is not None, "worker 未启动"
        path = Path(self._helper_dir.name) / "cred_helper.py"
        if not path.exists():
            path.write_text(credential_helper_source(), encoding="utf-8")
        return str(path)

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
        claimed = self.service.repo.claim_next_task()
        if claimed is None:
            return 0
        task, attempt = claimed
        await self._execute(task, attempt)
        return 1

    async def _execute(self, task: SuperagentTask, attempt: TaskAttempt) -> None:
        logger.info("superagent 开始执行 task_id=%s attempt=%s", task.task_id, attempt.attempt_no)
        token = ""
        try:
            self._check_owner_permission(task, "superagent.create", "执行")
            ref = parse_repo_url(task.repo_url_snapshot)  # 快照；损坏视为 blocked
            workspace = workspace_path(self.workspace_root, workspace_key(ref, task.task_id))
            self.service.repo.update_attempt(
                attempt.attempt_id, workspace_key=workspace_key(ref, task.task_id),
            )
            token = self.service.decrypted_github_token()
            git_args = credential_helper_gitconfig(self._helper_path())
            env_extra = git_auth_env(token)
            await self._run_phases(task, attempt, ref, workspace, token, git_args, env_extra)
        except TaskCancelledError:
            await self._on_cancelled(task, attempt)
        except _TaskBlockedError as blocked:
            await self._block(task, attempt, blocked.code, blocked.reason)
        except cred.RepoUrlError as exc:
            await self._block(task, attempt, "invalid_repo_snapshot", f"任务仓库快照不可用：{exc}")
        except Exception as exc:  # noqa: BLE001  任何失败都落到任务终态
            logger.exception("superagent 任务失败 task_id=%s", task.task_id)
            await self._on_failed(task, attempt, sanitize_text(str(exc)[:1500], tokens=(token,)))
        finally:
            release = getattr(self.runner, "release_session_workspace", None)
            if release is not None:
                try:
                    release(attempt.session_id)
                except Exception:  # noqa: BLE001
                    logger.exception("释放会话工作区失败 session=%s", attempt.session_id)

    # ---- 阶段编排 ------------------------------------------------------------------

    async def _run_phases(
        self, task: SuperagentTask, attempt: TaskAttempt, ref: Any, workspace: Path,
        token: str, git_args: tuple[str, str], env_extra: dict[str, str],
    ) -> None:
        settings = self.service.repo.get_settings()
        verify_commands = load_verify_commands(settings.verify_profile)

        # ---- preparing ----
        self._enter_phase(task, attempt, PHASE_PREPARING)
        base_sha = await self._prepare_workspace(task, workspace, git_args, env_extra)
        self.service.repo.update_task_fields(task.task_id, base_sha=base_sha)
        self.service.repo.update_attempt(attempt.attempt_id, checkpoint=CK_PREPARED, head_sha=base_sha)
        self.service.append_event(task.task_id, "progress", f"工作区就绪；base {base_sha[:10]}")

        # 缺凭证：公开 clone 已完成，push 需要凭证 → blocked（方案 §6 预检语义）
        if not token:
            raise _TaskBlockedError(
                "missing_credentials",
                "未配置 GitHub 凭证，无法推送分支；请在配置中保存 token 后重试",
            )

        # ---- coding ----
        self._enter_phase(task, attempt, PHASE_CODING)
        request = self._runner_request(task, attempt, ref, workspace)
        self.service.repo.update_attempt(attempt.attempt_id, run_id=request.run_id)
        self.service.repo.update_task_fields(task.task_id, run_id=request.run_id)
        await self.runner.prepare(request)
        run_timeout = float(getattr(self.runner, "run_timeout_seconds", 4 * 3600) or 4 * 3600)
        try:
            outcome = await asyncio.wait_for(self.runner.execute(request), timeout=run_timeout)
        except asyncio.TimeoutError:
            await self._interrupt_runner(attempt)
            raise RuntimeError(f"编码会话超时（>{int(run_timeout)}s），已中断") from None
        self._assert_live(task.task_id, attempt)
        if not outcome.completed:
            # P0 门禁：流意外结束不是完成
            raise RuntimeError(f"编码会话未正常完成：{outcome.error or '执行流提前结束'}")
        self.service.repo.update_attempt(attempt.attempt_id, checkpoint=CK_CODED)
        for item in outcome.progress_events[-5:]:
            self.service.append_event(
                task.task_id, "progress",
                f"第 {item.get('iteration', '?')} 步：{', '.join(item.get('tools') or []) or '(内部步骤)'}",
            )

        # 追问协议：需要补充信息 → waiting_input（微信回执带问题）
        question = outcome.question()
        if question:
            if not self._transition_terminal(
                task, attempt, to_status=TASK_WAITING_INPUT,
                task_fields={"result_summary": outcome.final_response[:SUMMARY_MAX_CHARS]},
                report_kind=REPORT_QUESTION, report_summary=outcome.final_response[:SUMMARY_MAX_CHARS],
                question=question, notify=False,
                event_kind="question", event_detail=question[:300],
            ):
                return
            self.service.repo.finish_attempt(attempt.attempt_id, state="succeeded", error_code="waiting_input")
            await self._notify_outside_tx(
                task, attempt, "question",
                f"❓ 任务需要补充信息：{question}\n\n回复「/补充 {task.task_id} 你的回答」继续。",
            )
            return

        # ---- verifying ----
        self._enter_phase(task, attempt, PHASE_VERIFYING)
        coded_head = (await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra,
                                      "rev-parse", "HEAD"))[1].strip()
        verify_result = await run_verification(
            commands=verify_commands, workspace=workspace,
            artifacts_dir=self._verify_artifacts_dir(task, attempt),
            head_sha=coded_head, git_runner=self._git_runner, token=token,
        )
        self._assert_live(task.task_id, attempt)
        head_after_verify = (await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra,
                                             "rev-parse", "HEAD"))[1].strip()
        if head_after_verify != coded_head:
            raise RuntimeError("验证阶段改变了 HEAD（验证命令不得提交代码），拒绝发布")
        if verify_result.configured:
            self.service.repo.update_attempt(attempt.attempt_id, checkpoint=CK_VERIFIED)
            self.service.append_event(
                task.task_id, "progress",
                "验证通过" if verify_result.passed else f"验证未通过：{verify_result.failure_reason}",
            )
        else:
            self.service.append_event(task.task_id, "progress", "未配置验证命令")
        if (verify_result.configured and not verify_result.passed
                and not settings.allow_unverified_draft):
            await self._block(
                task, attempt, "verification_failed",
                f"验证门禁未通过：{verify_result.failure_reason}",
                head_sha=coded_head, verification_ref=verify_result.artifacts_dir,
            )
            return

        # ---- publishing ----
        self._enter_phase(task, attempt, PHASE_PUBLISHING)
        self._assert_live(task.task_id, attempt, published_checkpoints=frozenset({CK_PUSHED}))
        self._check_owner_permission(task, "superagent.create", "发布")
        plan = _PublishContext(
            ref=ref, workspace=workspace, branch=task.branch,
            base_branch=task.base_branch_snapshot, token=token,
            git_args=git_args, env_extra=env_extra,
        )
        await self._publish(task, attempt, plan, outcome, verify_result)

    # ---- preparing：无凭证 remote + credential helper ------------------------------

    async def _prepare_workspace(
        self, task: SuperagentTask, workspace: Path,
        git_args: tuple[str, str], env_extra: dict[str, str],
    ) -> str:
        ref = parse_repo_url(task.repo_url_snapshot)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        if not (workspace / ".git").exists():
            workspace.parent.mkdir(parents=True, exist_ok=True)
            await self._git(None, GIT_CLONE_TIMEOUT, git_args, env_extra,
                            "clone", ref.origin_url, str(workspace))
            await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra,
                            "config", "user.name", GIT_AUTHOR_NAME)
            await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra,
                            "config", "user.email", GIT_AUTHOR_EMAIL)
        # remote 一律无凭证 URL（顺带清理历史泄漏的 userinfo）
        await self._git(workspace, GIT_DEFAULT_TIMEOUT, (), env_extra,
                        "remote", "set-url", "origin", ref.origin_url)
        await self._git(workspace, GIT_FETCH_TIMEOUT, git_args, env_extra,
                        "fetch", "origin", "+refs/heads/*:refs/remotes/origin/*", "--prune", "--force")
        await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra,
                        "checkout", "-f", "-B", task.branch, f"origin/{task.base_branch_snapshot}")
        await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra, "clean", "-fd")
        base_sha = await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra,
                                   "rev-parse", "HEAD")
        return base_sha[1].strip()

    # ---- publishing：checkpoint + 对账复用 + Draft PR -------------------------------

    async def _publish(
        self, task: SuperagentTask, attempt: TaskAttempt, plan: _PublishContext,
        outcome: Any, verify_result: Any,
    ) -> None:
        workspace = plan.workspace
        git_args, env_extra = plan.git_args, plan.env_extra
        # 1) 变更识别：工作树 + base...HEAD 双比较（覆盖代理自行 commit）
        status_out = await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra,
                                     "status", "--porcelain")
        working_changes = bool(status_out[1].strip())
        base_sha = str(task.base_sha or "")
        diff_out = await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra,
                                   "diff", "--stat", f"{base_sha}...HEAD")
        committed_changes = bool(diff_out[1].strip())
        if not working_changes and not committed_changes:
            summary = (outcome.final_response or "").strip()[:SUMMARY_MAX_CHARS]
            self._transition_terminal(
                task, attempt, to_status=TASK_SUCCEEDED,
                task_fields={"result_summary": summary},
                report_kind=REPORT_NO_CHANGES, report_summary=summary,
                notify=True,
                notify_text=f"✅ 编码任务完成（无代码变更）：{task.title}\n\n{summary or '代理没有发现需要改动的地方。'}",
                event_kind="no_changes", event_detail="代理未产生代码变更",
            )
            self.service.repo.finish_attempt(attempt.attempt_id, state="succeeded", error_code="no_changes")
            return
        # 2) 控制端统一提交（工作树残余 + 未跟踪文件）
        if working_changes:
            await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra, "add", "-A")
            commit_message = (
                f"{task.title}\n\n"
                f"由 EasyChat 超级代理提交（任务 {task.task_id} attempt #{attempt.attempt_no}）"
            )
            await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra,
                            "commit", "-m", commit_message)
        head_sha = (await self._git(workspace, GIT_DEFAULT_TIMEOUT, git_args, env_extra,
                                    "rev-parse", "HEAD"))[1].strip()
        self.service.repo.update_attempt(attempt.attempt_id, head_sha=head_sha)

        # 3) publish intent 先落库（崩溃后恢复方知道 push 可能已发生）
        self.service.repo.update_attempt(attempt.attempt_id, checkpoint=CK_PUSH_INTENT)
        # 4) push（无凭证 remote + credential helper）
        await self._git(workspace, GIT_PUSH_TIMEOUT, git_args, env_extra,
                        "push", "origin", f"refs/heads/{plan.branch}:refs/heads/{plan.branch}")
        self.service.repo.update_attempt(
            attempt.attempt_id, checkpoint=CK_PUSHED, remote_head_sha=head_sha,
        )
        self.service.append_event(task.task_id, "progress", f"分支已推送（{head_sha[:10]}）")
        # push 已发出：此后到达的取消不再撤销，记录竞态并完成对账
        self._assert_live(task.task_id, attempt, published_checkpoints=frozenset({CK_PUSHED}))

        # 5) PR：先查后建（复用远端已知结果；重试/崩溃恢复安全）
        self.service.repo.update_attempt(attempt.attempt_id, checkpoint=CK_PR_INTENT)
        client = self._pr_client(plan.token)
        existing = None
        try:
            existing = await client.find_pr_for_head(
                ref=plan.ref, head_branch=plan.branch, base_branch=plan.base_branch,
            )
        except Exception as exc:  # noqa: BLE001  查询失败继续尝试创建（创建端同样可对账）
            logger.warning("查询已有 PR 失败：%s", sanitize_text(str(exc), tokens=(plan.token,)))
        if existing is not None:
            pr = existing
            pr_state = "merged" if pr.merged else (pr.state or "open")
            self.service.append_event(task.task_id, "reconciled", f"复用已有 PR #{pr.number}")
        else:
            pr = await client.create_draft_pr(
                ref=plan.ref, title=task.title, head=plan.branch,
                base=plan.base_branch, body=self._pr_body(task, attempt, outcome, verify_result, head_sha),
            )
            pr_state = "draft"
        self.service.repo.update_attempt(
            attempt.attempt_id, checkpoint=CK_PR_CREATED,
            pr_number=pr.number, pr_url=pr.html_url,
        )
        summary = (outcome.final_response or "").strip()[:SUMMARY_MAX_CHARS]
        verify_note = (verify_result.summary_text() if verify_result.configured
                       else "⚠️ 未配置验证命令（未经控制端验证）")
        notify_text = (
            f"✅ 编码任务完成：{task.title}\n"
            f"分支：{plan.branch}\nDraft PR：{pr.html_url}\n"
            f"验证：{verify_note}\n\n{summary}"
        )
        if self._task_cancel_requested(task.task_id):
            self.service.append_event(
                task.task_id, EVENT_CANCELLED_AFTER_PUBLICATION,
                "取消请求晚于 push 到达：已按远端实际结果完成发布",
            )
            notify_text = "⚠️ 你的取消请求到达时分支已推送，任务已按远端实际结果完成。\n\n" + notify_text
        self._transition_terminal(
            task, attempt, to_status=TASK_SUCCEEDED,
            task_fields={"pr_url": pr.html_url, "pr_number": pr.number,
                         "pr_state": pr_state, "result_summary": summary},
            report_kind=REPORT_READY,
            report_summary=f"{summary}\n\n验证：{verify_note}",
            head_sha=head_sha, verification_ref=verify_result.artifacts_dir,
            notify=True, notify_text=notify_text,
            event_kind="pr_created", event_detail=pr.html_url,
        )
        self.service.repo.finish_attempt(
            attempt.attempt_id, state="succeeded", head_sha=head_sha,
            pr_number=pr.number, pr_url=pr.html_url,
        )

    # ---- 终态（同事务：CAS + 报告 + 回执） -------------------------------------------

    def _transition_terminal(
        self, task: SuperagentTask, attempt: TaskAttempt, *, to_status: str,
        task_fields: dict[str, Any], report_kind: str | None,
        report_summary: str = "", question: str = "", head_sha: str = "",
        verification_ref: str = "", notify: bool = False, notify_text: str = "",
        event_kind: str = "", event_detail: str = "",
    ) -> bool:
        """终态/等待态迁移 + 报告 + 回执入队，同一事务；迟到 attempt 直接放弃。"""
        db = self.service.repo.db
        allowed_from = (TASK_RUNNING, TASK_CANCEL_REQUESTED)
        sets = ["status=?", "phase=''", "version=version+1", "updated_at=?"]
        params: list[Any] = [to_status, utc_now_iso()]
        for name, value in task_fields.items():
            sets.append(f"{name}=?")
            params.append(value)
        if to_status in (TASK_SUCCEEDED, TASK_FAILED, TASK_CANCELLED, TASK_AWAITING_REVIEW):
            sets.append("finished_at=?")
            params.append(utc_now_iso())
        sql = (
            f"UPDATE superagent_tasks SET {', '.join(sets)} WHERE id=? "
            f"AND status IN ({','.join('?' * len(allowed_from))}) AND active_attempt_id=?"
        )
        params.extend([task.task_id, *allowed_from, attempt.attempt_id])
        delivery_id = ""
        target: DeliveryTarget | None = None
        with db.transaction() as conn:
            cur = conn.execute(sql, params)
            if cur.rowcount != 1:
                logger.warning("迟到 attempt 放弃写终态 task=%s attempt=%s",
                               task.task_id, attempt.attempt_no)
                return False
            if report_kind:
                from backend.shared.identifiers import new_superagent_report_id

                conn.execute(
                    "INSERT INTO superagent_reports(id, task_id, attempt_id, kind, summary, "
                    "question, head_sha, verification_ref, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (new_superagent_report_id(), task.task_id, attempt.attempt_id, report_kind,
                     report_summary[:SUMMARY_MAX_CHARS], question[:1000],
                     head_sha[:40], verification_ref, utc_now_iso()),
                )
            if event_kind:
                conn.execute(
                    "INSERT INTO superagent_events(task_id, kind, detail, created_at) VALUES(?,?,?,?)",
                    (task.task_id, event_kind, (event_detail or "")[:2000], utc_now_iso()),
                )
            if notify:
                target = self._notify_target(task)
                if target is not None and self.delivery is not None:
                    dedup = (
                        f"superagent:{task.task_id}:a{attempt.attempt_no}"
                        f":{report_kind or to_status}:{target.kind}:{target.ref}"
                    )
                    delivery_id = self.delivery.enqueue_in_transaction(
                        conn, owner_id=task.owner_id, target=target, text=notify_text,
                        dedup_key=dedup, source="superagent",
                    )
        if delivery_id:
            self.service.append_event(
                task.task_id, "notified", f"回执已入队（{target.kind}:{target.ref}）",
            )
        return True

    async def _notify_outside_tx(self, task: SuperagentTask, attempt: TaskAttempt,
                                 kind: str, text: str) -> None:
        """非终态通知（question 等）：尽力而为，不阻塞主流程。"""
        if self.delivery is None:
            return
        target = self._notify_target(task)
        if target is None:
            return
        try:
            self.delivery.enqueue_text(
                owner_id=task.owner_id, target=target, text=text,
                dedup_key=(f"superagent:{task.task_id}:a{attempt.attempt_no}"
                           f":{kind}:{target.kind}:{target.ref}"),
                source="superagent",
            )
            self.service.append_event(task.task_id, "notified", f"通知已入队（{kind}）")
        except Exception:  # noqa: BLE001
            logger.exception("superagent 通知入队失败 task_id=%s", task.task_id)

    # ---- 取消 / 失败 / 受阻路径 -------------------------------------------------------

    async def _on_cancelled(self, task: SuperagentTask, attempt: TaskAttempt) -> None:
        await self._interrupt_runner(attempt)
        if not self._transition_terminal(
            task, attempt, to_status=TASK_CANCELLED,
            task_fields={"error": "已取消"},
            report_kind=REPORT_FAILED, report_summary="任务已取消",
            notify=True, notify_text=f"⛔ 编码任务已取消：{task.title}",
            event_kind="cancelled", event_detail="执行已停止",
        ):
            return
        self.service.repo.finish_attempt(attempt.attempt_id, state="interrupted", error_code="cancelled")

    async def _on_failed(self, task: SuperagentTask, attempt: TaskAttempt, error: str) -> None:
        await self._interrupt_runner(attempt)
        # cancel_requested 期间失败 → 按用户意图落到 cancelled
        was_cancel_requested = self._task_cancel_requested(task.task_id)
        to_status = TASK_CANCELLED if was_cancel_requested else TASK_FAILED
        notify_text = (f"⛔ 编码任务已取消：{task.title}" if was_cancel_requested
                       else f"❌ 编码任务失败：{task.title}\n\n{error[:400]}\n\n"
                            f"可在 Web 面板或回复「/重试 {task.task_id}」重试。")
        if not self._transition_terminal(
            task, attempt, to_status=to_status,
            task_fields={"error": error[:1500]},
            report_kind=REPORT_FAILED, report_summary=error[:SUMMARY_MAX_CHARS],
            notify=True, notify_text=notify_text,
            event_kind=("cancelled" if was_cancel_requested else "failed"),
            event_detail=error[:500],
        ):
            return
        self.service.repo.finish_attempt(attempt.attempt_id, state="failed", error_summary=error)

    async def _block(self, task: SuperagentTask, attempt: TaskAttempt, code: str, reason: str,
                     head_sha: str = "", verification_ref: str = "") -> None:
        logger.warning("superagent 任务受阻 task=%s code=%s", task.task_id, code)
        await self._interrupt_runner(attempt)
        if not self._transition_terminal(
            task, attempt, to_status=TASK_BLOCKED,
            task_fields={"error": reason[:1500]},
            report_kind=REPORT_BLOCKED, report_summary=reason,
            head_sha=head_sha, verification_ref=verification_ref,
            notify=True, notify_text=f"⛔ 编码任务受阻：{task.title}\n\n{reason[:400]}",
            event_kind="blocked", event_detail=reason[:300],
        ):
            return
        self.service.repo.finish_attempt(attempt.attempt_id, state="failed", error_code=code, error_summary=reason)

    # ---- 取消/存活检测 -----------------------------------------------------------

    def _task_cancel_requested(self, task_id: str) -> bool:
        task = self.service.task(task_id)
        return task is not None and task.status == TASK_CANCEL_REQUESTED

    def _assert_live(self, task_id: str, attempt: TaskAttempt,
                     published_checkpoints: frozenset[str] = frozenset()) -> None:
        """取消/迟到检测。published_checkpoints：已发布后取消不抛错（由调用方记录竞态）。"""
        task = self.service.task(task_id)
        if task is None:
            raise TaskCancelledError("任务不存在")
        live_attempt = self.service.repo.get_attempt(attempt.attempt_id)
        current_checkpoint = live_attempt.checkpoint if live_attempt is not None else attempt.checkpoint
        if task.status == TASK_CANCEL_REQUESTED and current_checkpoint not in published_checkpoints:
            raise TaskCancelledError()
        if task.active_attempt_id != attempt.attempt_id:
            raise TaskCancelledError("活跃 attempt 已切换")

    def _enter_phase(self, task: SuperagentTask, attempt: TaskAttempt, phase: str) -> None:
        self.service.repo.update_task_fields(task.task_id, phase=phase)
        self.service.repo.update_attempt(attempt.attempt_id, heartbeat_at=utc_now_iso())
        self._assert_live(task.task_id, attempt)

    async def _interrupt_runner(self, attempt: TaskAttempt) -> None:
        try:
            await self.runner.interrupt(attempt.run_id or attempt.session_id)
        except Exception:  # noqa: BLE001
            logger.exception("runner 中断失败 attempt=%s", attempt.attempt_no)

    def _check_owner_permission(self, task: SuperagentTask, permission: str, action: str) -> None:
        """撤销权限后执行/发布前重新检查（方案 T1）。"""
        try:
            principal = self.service.access.snapshot_principal(task.owner_id)
            self.service.access.require_permission(principal, permission)
        except Exception as exc:  # noqa: BLE001  权限缺失 → blocked（不是 failed）
            raise _TaskBlockedError(
                "permission_revoked",
                f"任务发起者已无 {action} 权限（{permission}），任务挂起",
            ) from exc

    # ---- git / PR / 通知工具 -----------------------------------------------------------

    async def _git(
        self, cwd: Path | None, timeout: float, git_args: tuple[str, str],
        env_extra: dict[str, str], *args: str, tokens: tuple[str, ...] = (),
    ) -> tuple[int, str]:
        if self._git_runner is not None:
            code, out, err = await self._git_runner(cwd, git_args, env_extra, timeout, *args)
        else:
            code, out, err = await _run_git(cwd, timeout, git_args, env_extra, *args)
        if code != 0:
            message = sanitize_text((err or out).strip()[:500], tokens=tokens)
            raise RuntimeError(f"git {' '.join(args[:2])} 失败：{message}")
        return code, out

    def _pr_client(self, token: str) -> gh.PRClient:
        if self._pr_client_factory is not None:
            return self._pr_client_factory(token)
        return gh.HttpxPRClient(token=token)

    def _notify_target(self, task: SuperagentTask) -> DeliveryTarget | None:
        """回执目标：优先受理时的微信来源地址（多账号不回错），回落默认绑定。"""
        if task.source_kind and task.source_ref:
            return DeliveryTarget(
                kind=task.source_kind, ref=task.source_ref,
                channel_account_id=task.source_channel_account_id,
            )
        channels = self._channels_provider()
        resolved = channels.delivery_target_for_owner(task.owner_id) if channels else None
        if resolved is None:
            return None
        return resolved if isinstance(resolved, DeliveryTarget) else target_from_channel(resolved)

    def _verify_artifacts_dir(self, task: SuperagentTask, attempt: TaskAttempt) -> Path:
        return self.artifacts_root / task.task_id / str(attempt.attempt_no)

    def _runner_request(self, task: SuperagentTask, attempt: TaskAttempt,
                        ref: Any, workspace: Path):
        from backend.modules.superagent.runner import RunnerRequest

        principal = self.service.access.snapshot_principal(task.owner_id)
        inputs = self.service.repo.unconsumed_inputs(task.task_id)
        consumed = self.service.repo.mark_inputs_consumed(task.task_id, attempt.attempt_id)
        if consumed:
            self.service.append_event(task.task_id, "progress", f"已纳入 {consumed} 条补充输入")
        return RunnerRequest(
            task_id=task.task_id,
            run_id=f"run_{attempt.attempt_id.split('_', 1)[-1]}",  # attempt 唯一派生
            session_id=attempt.session_id,
            principal=principal,
            workspace=workspace,
            repo_url=task.repo_url_snapshot,
            branch=task.branch,
            base_branch=task.base_branch_snapshot,
            requirement=task.requirement,
            extra_inputs=tuple(i.text for i in inputs),
            context_extra=task.context_extra,
            timezone=self._timezone,
        )

    def _pr_body(self, task: SuperagentTask, attempt: TaskAttempt, outcome: Any,
                 verify_result: Any, head_sha: str) -> str:
        parts = ["## 需求", "", task.requirement[:4000], ""]
        parts += ["## 代理摘要", "", (outcome.final_response or "").strip()[:2000] or "（无）", ""]
        parts += ["## 验证", "", (verify_result.summary_text() if verify_result.configured
                                 else "⚠️ 仓库未配置验证命令，本次 Draft PR 未经控制端验证"), ""]
        parts += ["## 执行信息", "",
                  f"- 任务：{task.task_id}",
                  f"- attempt：#{attempt.attempt_no}",
                  f"- 分支：`{task.branch}`（基于 `{task.base_branch_snapshot}`）",
                  f"- head：`{head_sha[:12]}`",
                  "", "---",
                  f"EasyChat-Superagent-Task: {task.task_id}",
                  "由 EasyChat 超级代理自动创建（Draft，合并由维护者决定）"]
        return "\n".join(parts)

    # ---- 旧工作区 remote 清理（T2：清历史泄漏的 userinfo） -----------------------------

    def _sanitize_legacy_remotes(self) -> None:
        """扫描工作区根下所有 git 仓库；origin URL 携带 userinfo 的改为无凭证并记录。"""
        if not self.workspace_root.exists():
            return
        cleaned: list[str] = []
        for git_dir in self.workspace_root.glob("**/.git"):
            repo_dir = git_dir.parent
            try:
                result = sp.run(["git", "remote", "get-url", "origin"], cwd=str(repo_dir),
                                capture_output=True, text=True, timeout=15, shell=False)
                url = result.stdout.strip() if result.returncode == 0 else ""
                if url and "@" in url.split("://", 1)[-1].split("/", 1)[0]:
                    clean = re.sub(r"(https?://)([^/@]+)@", r"\1", url)
                    sp.run(["git", "remote", "set-url", "origin", clean], cwd=str(repo_dir),
                           capture_output=True, text=True, timeout=15, shell=False, check=False)
                    cleaned.append(clean)
            except Exception:  # noqa: BLE001  清理是尽力而为
                logger.exception("清理旧 remote 失败 dir=%s", repo_dir)
        if cleaned:
            logger.warning(
                "发现 %s 个历史工作区 remote 携带凭证，已改为无凭证 URL；"
                "曾经暴露的 token 请在 GitHub 侧轮换",
                len(cleaned),
            )


async def _run_git(
    cwd: Path | None, timeout: float, git_args: tuple[str, str],
    env_extra: dict[str, str], *args: str,
) -> tuple[int, str, str]:
    """真实 git subprocess：无凭证 URL + credential helper 参数 + 受控环境。"""
    git_exe = shutil.which("git")
    if git_exe is None:
        raise RuntimeError("运行环境缺少 git（runner 镜像需要内置 git）")
    env = dict(os.environ)
    env.update(env_extra)
    argv = [git_exe, *git_args, *args]
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd) if cwd is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise RuntimeError(f"无法启动 git：{exc}") from exc
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        await _terminate_tree(process)
        raise RuntimeError(f"git {' '.join(args[:2])} 超时（>{int(timeout)}s），已终止") from None
    return (
        int(process.returncode or 0),
        stdout.decode("utf-8", "replace"),
        stderr.decode("utf-8", "replace"),
    )


async def _terminate_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        if sys.platform == "win32":
            kill = await asyncio.create_subprocess_exec(
                "taskkill", "/T", "/F", "/PID", str(process.pid),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(kill.wait(), timeout=15)
        else:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            process.kill()
    except Exception:  # noqa: BLE001
        logger.exception("git 进程树回收失败 pid=%s", process.pid)
