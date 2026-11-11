"""superagent 服务：受理、配置、查询与生命周期控制（T1）。

权限边界：
- view：superagent.view +（owner 本人或 superagent.manage 跨用户）；
- create：superagent.create；微信对话经业务工具进入同一入口；
- cancel/retry：owner 需 superagent.create，跨用户需 superagent.manage；
- manage（配置/跨用户）：superagent.manage。
撤销权限后：执行阶段（认领前）与发布阶段由 worker 重新检查（见 worker）。

Gate：enabled 且 repo_url 可解析才受理新任务；GitHub token 可后补
（执行阶段缺凭证进入 blocked，见 worker/publishing）。

快照：受理时把解析后的仓库 origin URL、基线分支与 settings.updated_at 一起
写入任务；执行只读快照（排队后管理员改配置不影响已受理任务，方案 §5）。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from backend.modules.access.api import AccessService
from backend.modules.delivery.contracts import DeliveryTarget
from backend.modules.superagent.contracts import (
    RETRYABLE_TASK_STATUSES,
    SOURCE_TOOL,
    SOURCE_WEB,
    SOURCE_WECHAT,
    SuperagentSettings,
    SuperagentTask,
    TaskInput,
    TASK_BLOCKED,
    TASK_CANCELLED,
    TASK_CANCEL_REQUESTED,
    TASK_FAILED,
    TASK_QUEUED,
    TASK_RUNNING,
    TASK_WAITING_INPUT,
    TASK_INTERRUPTED,
    TERMINAL_TASK_STATUSES,
)
from backend.modules.superagent.acceptance import AcceptanceRepository
from backend.modules.superagent.credentials import RepoUrlError, parse_repo_url
from backend.modules.superagent.repository import SuperagentRepository
from backend.modules.superagent.contracts import MAX_AUTO_FIX_ROUNDS
from backend.modules.superagent.verification import MAX_VERIFY_COMMANDS, load_verify_commands
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.crypto import decrypt_secret, encrypt_secret
from backend.shared.errors import ForbiddenError, InvalidInputError, NotFoundError

logger = logging.getLogger(__name__)

_SOURCES = frozenset({SOURCE_WECHAT, SOURCE_WEB, SOURCE_TOOL})
REQUIREMENT_LIMIT = 8000
# 重新执行前需要确认目标配置的状态（含缺快照的旧任务）
REACTIVABLE_INPUT_STATUSES = frozenset({TASK_WAITING_INPUT, TASK_BLOCKED, TASK_FAILED})


class SuperagentService:
    def __init__(
        self,
        db: Database,
        *,
        access: AccessService,
        delivery: Any | None = None,
        channels: Any | None = None,
        timezone: str = "Asia/Shanghai",
    ) -> None:
        self.repo = SuperagentRepository(db)
        self.acceptance = AcceptanceRepository(db)
        self.access = access
        self.delivery = delivery
        self.channels = channels
        self._encryption_secret = ""
        # 协作取消回调（bootstrap 注入 async canceller：await runtime.cancel(run_id)）
        self._run_canceller: Any = None
        # runner 是否就绪（capabilities 用；bootstrap 在 runtime 存在时置 True）
        self.runner_ready = False

    # ---- 装配钩子 ------------------------------------------------------------------

    def set_encryption_secret(self, secret: str) -> None:
        self._encryption_secret = str(secret or "")

    def set_run_canceller(self, canceller: Any) -> None:
        """异步回调：await canceller(run_id)；协作中断编码会话。"""
        self._run_canceller = canceller

    # ---- capabilities（T1：普通用户也能获得准确受理状态） ----------------------------

    def capabilities(self, principal: Principal) -> dict[str, Any]:
        self.access.validate_principal(principal)
        settings = self.repo.get_settings()
        can_view = self._has(principal, "superagent.view")
        can_create = self._has(principal, "superagent.create")
        can_manage = self._has(principal, "superagent.manage")
        reasons: list[str] = []
        configured = False
        if settings.enabled and settings.repo_url:
            try:
                parse_repo_url(settings.repo_url)
                configured = True
            except RepoUrlError as exc:
                reasons.append(f"仓库配置不可用：{exc}")
        else:
            reasons.append("超级代理未启用或未配置仓库")
        if not settings.has_github_token:
            reasons.append("未配置 GitHub 凭证（执行阶段将进入 blocked）")
        if not self.runner_ready:
            reasons.append("编码 runner 未就绪（未启用 Hermes 运行时）")
        return {
            "view": can_view,
            "create": can_create,
            "cancel": can_create or can_manage,
            "manage": can_manage,
            "enabled": bool(settings.enabled),
            "configured": configured,
            "credentials_ready": bool(settings.has_github_token),
            "runner_ready": bool(self.runner_ready),
            "reasons": reasons if (not (configured and self.runner_ready)) else [],
            # 敏感值不对普通用户暴露
            "repo_url": settings.repo_url if can_manage else "",
        }

    # ---- 配置 ------------------------------------------------------------------

    def get_settings(self, principal: Principal) -> SuperagentSettings:
        self.access.validate_principal(principal)
        self.access.require_permission(principal, "superagent.manage")
        return self.repo.get_settings()

    def update_settings(
        self, principal: Principal, *,
        enabled: bool | None = None,
        repo_url: str | None = None,
        base_branch: str | None = None,
        github_token: str | None = None,
        pr_labels: str | None = None,
        max_concurrent: int | None = None,
        verify_profile: str | None = None,
        allow_unverified_draft: bool | None = None,
        auto_fix_enabled: bool | None = None,
        auto_fix_max_rounds: int | None = None,
    ) -> SuperagentSettings:
        self.access.validate_principal(principal)
        self.access.require_permission(principal, "superagent.manage")
        if auto_fix_max_rounds is not None and int(auto_fix_max_rounds) > MAX_AUTO_FIX_ROUNDS:
            raise InvalidInputError(f"自动修复轮数最多 {MAX_AUTO_FIX_ROUNDS}")
        encrypted_payload: str | None = None
        if repo_url is not None and repo_url.strip():
            try:
                ref = parse_repo_url(repo_url)  # 保存即严格校验（与执行同一 parser）
            except RepoUrlError as exc:
                raise InvalidInputError(f"仓库地址非法：{exc}") from exc
            repo_url = ref.origin_url  # 规范化存储
        if github_token is not None:
            secret = str(github_token).strip()
            if not self._encryption_secret:
                raise InvalidInputError("未配置 EASYCHAT_ENCRYPTION_SECRET，无法保存 GitHub 凭证")
            encrypted_payload = encrypt_secret(secret, self._encryption_secret) if secret else ""
        if verify_profile is not None:
            commands = load_verify_commands(verify_profile)
            if len(commands) > MAX_VERIFY_COMMANDS:
                raise InvalidInputError(f"验证命令最多 {MAX_VERIFY_COMMANDS} 条")
        self.repo.update_settings(
            enabled=enabled,
            repo_url=repo_url,
            base_branch=base_branch,
            github_token_enc=encrypted_payload,
            pr_labels=pr_labels,
            max_concurrent=max_concurrent,
            verify_profile=verify_profile,
            allow_unverified_draft=allow_unverified_draft,
            auto_fix_enabled=auto_fix_enabled,
            auto_fix_max_rounds=auto_fix_max_rounds,
        )
        return self.repo.get_settings()

    # ---- 任务受理 ----------------------------------------------------------------

    def create_task(
        self, principal: Principal, *, title: str, requirement: str,
        context_extra: str = "", source: str = SOURCE_WEB, session_id: str = "",
        idempotency_key: str = "", source_target: DeliveryTarget | None = None,
    ) -> SuperagentTask:
        self.access.validate_principal(principal)
        self.access.require_permission(principal, "superagent.create")
        if source not in _SOURCES:
            raise InvalidInputError(f"未知任务来源: {source}")
        title = str(title or "").strip()
        requirement = str(requirement or "").strip()
        if not title:
            raise InvalidInputError("任务标题不能为空")
        if len(title) > 120:
            raise InvalidInputError("任务标题过长（≤120 字）")
        if not requirement:
            raise InvalidInputError("任务需求描述不能为空")
        if len(requirement) > REQUIREMENT_LIMIT:
            raise InvalidInputError(f"需求描述过长（≤{REQUIREMENT_LIMIT} 字）")
        # 幂等：同一来源事件 / Idempotency-Key 已受理过 → 返回既有任务
        external_event_id = str(idempotency_key or "").strip()
        if external_event_id:
            existing = self.repo.find_task_by_source_event(source, external_event_id)
            if existing is not None:
                return existing
        settings = self.repo.get_settings()
        if not settings.enabled or not settings.repo_url:
            raise InvalidInputError("超级代理未启用或未配置目标仓库，请联系管理员")
        try:
            ref = parse_repo_url(settings.repo_url)
        except RepoUrlError as exc:
            raise InvalidInputError(f"仓库配置不可用：{exc}") from exc
        task = self.repo.create_task(
            owner_id=principal.user_id, title=title, requirement=requirement,
            context_extra=str(context_extra or "").strip(),
            source=source, session_id=str(session_id or ""),
            branch=f"superagent/sag_{uuid.uuid4().hex}",
            repo_url_snapshot=ref.origin_url,
            base_branch_snapshot=settings.base_branch or "main",
            settings_revision=settings.updated_at or "initial",
            policy_revision=0,
            source_event_id=external_event_id,
            source_channel_account_id=(source_target.channel_account_id if source_target else ""),
            source_chat_id=(source_target.ref if source_target else ""),
            source_ref=(source_target.ref if source_target else ""),
            source_kind=(source_target.kind if source_target else ""),
        )
        self.repo.append_event(task.task_id, "created",
                               f"来源 {source}；分支 {task.branch}；仓库 {ref.full_name}")
        logger.info("superagent 任务已受理 task_id=%s owner=%s repo=%s",
                    task.task_id, principal.user_id, ref.full_name)
        return task

    # ---- 输入（补充/追问回答） -------------------------------------------------------

    def append_task_input(
        self, principal: Principal, task_id: str, *, text: str,
        source: str = SOURCE_WEB, external_event_id: str = "",
        attachment_refs: str = "[]",
    ) -> TaskInput:
        """追加输入并按需把 waiting_input/blocked/failed 任务重新入队（同一任务续跑）。"""
        task = self._task_for(principal, task_id)
        self._require_cancel_like(principal, task)
        text = str(text or "").strip()
        if not text:
            raise InvalidInputError("补充内容不能为空")
        if len(text) > REQUIREMENT_LIMIT:
            raise InvalidInputError(f"补充内容过长（≤{REQUIREMENT_LIMIT} 字）")
        created_input, created = self.repo.append_input(
            task_id=task_id, source=source, external_event_id=external_event_id,
            actor_id=principal.user_id, text=text, attachment_refs=attachment_refs,
        )
        if not created:
            return created_input  # 幂等：同一事件重复提交
        self.repo.append_event(task_id, "input", f"补充输入（{source}）：{text[:120]}")
        if task.status in REACTIVABLE_INPUT_STATUSES:
            self.repo.transition_task(
                task_id,
                from_statuses=REACTIVABLE_INPUT_STATUSES,
                to_status=TASK_QUEUED,
                event_kind="created",
                event_detail="收到补充输入，重新入队",
            )
        return created_input

    # ---- 查询 ------------------------------------------------------------------

    def list_tasks(
        self, principal: Principal, *, limit: int = 50,
        cursor_created_at: str = "", cursor_id: str = "",
        status: str = "",
    ) -> list[SuperagentTask]:
        self.access.validate_principal(principal)
        self.access.require_permission(principal, "superagent.view")
        tasks = (
            self.repo.list_all(limit=limit, cursor_created_at=cursor_created_at, cursor_id=cursor_id)
            if self._can_manage(principal)
            else self.repo.list_for_owner(
                principal.user_id, limit=limit,
                cursor_created_at=cursor_created_at, cursor_id=cursor_id,
            )
        )
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def get_task(self, principal: Principal, task_id: str) -> SuperagentTask:
        return self._task_for(principal, task_id)

    def list_events(self, principal: Principal, task_id: str, after_id: int = 0):
        self._task_for(principal, task_id)
        return self.repo.events_for_task(task_id, after_id=after_id)

    def list_reports(self, principal: Principal, task_id: str):
        self._task_for(principal, task_id)
        return self.repo.reports_for_task(task_id)

    def list_attempts(self, principal: Principal, task_id: str):
        self._task_for(principal, task_id)
        return self.repo.attempts_for_task(task_id)

    # ---- 生命周期 ----------------------------------------------------------------

    async def cancel_task(self, principal: Principal, task_id: str) -> SuperagentTask:
        task = self._task_for(principal, task_id)
        self._require_cancel_like(principal, task)
        if task.status in TERMINAL_TASK_STATUSES or task.status == TASK_CANCEL_REQUESTED:
            return task
        if task.status != TASK_RUNNING:
            # queued/waiting_input/blocked/failed/interrupted：直接取消
            self.repo.transition_task(
                task_id,
                from_statuses=frozenset(
                    {TASK_QUEUED, TASK_WAITING_INPUT, TASK_BLOCKED, TASK_FAILED, TASK_INTERRUPTED}
                ),
                to_status=TASK_CANCELLED,
                event_kind="cancelled",
                event_detail="任务在执行前被取消",
                finished_at=_now(),
            )
            return self.repo.get_task(task_id)  # type: ignore[return-value]
        # 运行中：CAS running → cancel_requested，再 await 协作中断
        if not self.repo.transition_task(
            task_id,
            from_statuses=frozenset({TASK_RUNNING}),
            to_status=TASK_CANCEL_REQUESTED,
            event_kind="cancel_requested",
            event_detail="已请求取消，等待当前步骤结束",
            cancel_requested_at=_now(),
        ):
            # 状态已被并发改变（如迟到终态）；返回当前值
            return self.repo.get_task(task_id)  # type: ignore[return-value]
        current = self.repo.get_task(task_id)
        if current is not None and current.run_id and self._run_canceller is not None:
            try:
                await self._run_canceller(current.run_id)
            except Exception:  # noqa: BLE001  中断失败不改变取消请求状态；worker 兜底
                logger.exception("协作取消失败 task_id=%s run_id=%s", task_id, current.run_id)
        return self.repo.get_task(task_id)  # type: ignore[return-value]

    def retry_task(self, principal: Principal, task_id: str) -> SuperagentTask:
        task = self._task_for(principal, task_id)
        self._require_cancel_like(principal, task)
        self.access.require_permission(principal, "superagent.create")
        if task.legacy_config_unknown:
            raise InvalidInputError("旧任务缺少仓库快照，无法安全重试；请确认目标仓库后重新提交任务")
        if task.status not in RETRYABLE_TASK_STATUSES:
            raise InvalidInputError("只有失败、受阻、中断或已取消的任务可以重试")
        if not self.repo.requeue(task_id):
            raise InvalidInputError("任务状态已变化，刷新后重试")
        return self.repo.get_task(task_id)  # type: ignore[return-value]

    # ---- 运维指标（T8：runner/队列/执行/验证/PR/回执观测面） --------------------------

    def ops_metrics(self, principal: Principal) -> dict[str, Any]:
        self.access.validate_principal(principal)
        self.access.require_permission(principal, "superagent.manage")
        db = self.repo.db
        conn = db.connect()
        try:
            def count(sql: str, params: tuple = ()) -> int:
                row = conn.execute(sql, params).fetchone()
                return int(row["c"]) if row else 0

            tasks_by_status: dict[str, int] = {}
            for row in conn.execute(
                "SELECT status, count(*) AS c FROM superagent_tasks GROUP BY status"
            ):
                tasks_by_status[str(row["status"])] = int(row["c"])
            attempts_total = count("SELECT count(*) AS c FROM superagent_attempts")
            attempts_failed = count(
                "SELECT count(*) AS c FROM superagent_attempts WHERE state='failed'"
            )
            attempts_succeeded = count(
                "SELECT count(*) AS c FROM superagent_attempts WHERE state='succeeded'"
            )
            avg_seconds = conn.execute(
                "SELECT avg(julianday(finished_at) - julianday(started_at)) AS d "
                "FROM superagent_attempts WHERE finished_at IS NOT NULL AND started_at IS NOT NULL"
            ).fetchone()
            duration_seconds = round(float(avg_seconds["d"] or 0) * 86400, 1)
            verify_total = count(
                "SELECT count(*) AS c FROM superagent_reports WHERE kind IN ('ready','blocked')"
            )
            verify_blocked = count(
                "SELECT count(*) AS c FROM superagent_reports WHERE kind='blocked'"
            )
            deliveries: dict[str, int] = {}
            for row in conn.execute(
                "SELECT status, count(*) AS c FROM deliveries WHERE source='superagent' GROUP BY status"
            ):
                deliveries[str(row["status"])] = int(row["c"])
            webhook_pending = count(
                "SELECT count(*) AS c FROM superagent_webhook_events WHERE processed_at IS NULL"
            )
            settings = self.repo.get_settings()
        finally:
            conn.close()
        return {
            "tasks_by_status": tasks_by_status,
            "attempts": {
                "total": attempts_total,
                "succeeded": attempts_succeeded,
                "failed": attempts_failed,
                "avg_duration_seconds": duration_seconds,
            },
            "verification": {
                "total": verify_total,
                "blocked": verify_blocked,
                "allow_unverified_draft": settings.allow_unverified_draft,
                "verify_commands": len(load_verify_commands(settings.verify_profile)),
            },
            "deliveries_by_status": deliveries,
            "webhook_pending": webhook_pending,
            "runner_ready": bool(self.runner_ready),
            "credentials_ready": bool(settings.has_github_token),
            "enabled": bool(settings.enabled),
        }

    # ---- worker 协作入口（内部） ---------------------------------------------------

    def claim_next_task(self) -> tuple[SuperagentTask, Any] | None:
        return self.repo.claim_next_task()

    def task(self, task_id: str) -> SuperagentTask | None:
        return self.repo.get_task(task_id)

    def append_event(self, task_id: str, kind: str, detail: str = "") -> None:
        self.repo.append_event(task_id, kind, detail)

    def recover_interrupted(self) -> int:
        return self.repo.reset_running_to_interrupted()

    # ---- worker 令牌解密 ------------------------------------------------------------

    def decrypted_github_token(self) -> str:
        token_enc = self.repo.get_token_encrypted()
        if not token_enc or not self._encryption_secret:
            return ""
        return decrypt_secret(token_enc, self._encryption_secret)

    # ---- 内部 ------------------------------------------------------------------

    def _has(self, principal: Principal, permission: str) -> bool:
        return permission in self.access.effective_permissions(principal.user_id)

    def _can_manage(self, principal: Principal) -> bool:
        return self._has(principal, "superagent.manage")

    def _task_for(self, principal: Principal, task_id: str) -> SuperagentTask:
        self.access.validate_principal(principal)
        self.access.require_permission(principal, "superagent.view")
        task = self.repo.get_task(task_id)
        if task is None:
            raise NotFoundError("任务不存在")
        if task.owner_id != principal.user_id and not self._can_manage(principal):
            raise ForbiddenError("无权访问该任务")
        return task

    def _require_cancel_like(self, principal: Principal, task: SuperagentTask) -> None:
        """取消/重试授权：owner 需 create；跨用户需 manage。"""
        if task.owner_id == principal.user_id:
            self.access.require_permission(principal, "superagent.create")
        else:
            self.access.require_permission(principal, "superagent.manage")

    # ---- 逐项验收（工作包四） ------------------------------------------------------

    def submit_acceptance_round(
        self, principal: Principal, task_id: str, *, requirement: str,
        checks: list[dict], provenance: dict | None = None, attempt_id: str = "",
    ) -> dict:
        task = self._task_for(principal, task_id)
        self._require_cancel_like(principal, task)
        round_id, round_no, verdict = self.acceptance.create_round(
            task_id=task.task_id, attempt_id=attempt_id, requirement=requirement,
            provenance=provenance or {}, checks=checks, created_by=principal.user_id,
        )
        self.repo.append_event(task_id, "acceptance_round",
                               f"验收第 {round_no} 轮: {verdict}（{len(checks)} 项）")
        return {"round_id": round_id, "round_no": round_no, "verdict": verdict}

    def acceptance_for_task(self, principal: Principal, task_id: str) -> list[dict]:
        self._task_for(principal, task_id)
        return self.acceptance.list_rounds(task_id)

    def decide_acceptance_check(
        self, principal: Principal, check_id: int, *, decision: str, note: str = "",
    ) -> dict:
        row0 = self.acceptance.get_check(check_id)
        if row0 is None:
            raise NotFoundError("验收检查项不存在")
        task = self._task_for(principal, row0["task_id"])
        self._require_cancel_like(principal, task)
        check, first_reject = self.acceptance.set_decision(
            check_id=check_id, decision=decision, note=note, actor_id=principal.user_id,
        )
        requeued = False
        if first_reject:
            # 打回进入原任务：幂等输入(键=check_id)+终态 CAS 回队;旧轮证据保留。
            self.repo.append_input(
                task_id=task.task_id, source="acceptance",
                external_event_id=f"acceptance-reject:{check_id}",
                actor_id=principal.user_id,
                text=f"[验收打回 {check['item_id']}] {check['title']}：{note or '（无说明）'}",
            )
            requeued = self.acceptance.requeue_after_reject(task.task_id)
            self.repo.append_event(task.task_id, "acceptance_rejected",
                                   f"{check['item_id']} 打回返工" + ("（任务已回队）" if requeued else "（任务当前状态无需回队）"))
        elif decision == "accepted":
            self.repo.append_event(task.task_id, "acceptance_accepted", f"{check['item_id']} 验收通过")
        return {"check_id": check_id, "decision": decision, "first_reject": first_reject,
                "requeued": requeued}

    def acceptance_evidence_path(self, principal: Principal, task_id: str, round_id: str,
                                 item_id: str, index: int):
        """受控读取证据文件：owner 校验 + 相对 attempt.verification_ref 的 resolve 防逃逸。"""
        self._task_for(principal, task_id)
        import json as _json
        from pathlib import Path

        rounds = self.acceptance.list_rounds(task_id)
        for r in rounds:
            if r["id"] != round_id:
                continue
            for c in r["checks"]:
                if c["item_id"] != item_id:
                    continue
                entries = _json.loads(c["evidence_json"] or "[]")
                if not (0 <= index < len(entries)):
                    raise NotFoundError("证据序号不存在")
                rel = str(entries[index].get("path") or "")
                # 证据根:该轮 attempt 最新报告的 verification_ref(验证工件目录)
                root = None
                for rep in reversed(self.repo.reports_for_task(task.task_id)):
                    if (not r["attempt_id"] or rep.attempt_id == r["attempt_id"]) and rep.verification_ref:
                        from pathlib import Path as _P
                        root = _P(rep.verification_ref)
                        break
                if not rel or not rel.startswith("assets/") or root is None or not root.is_dir():
                    raise ForbiddenError("证据路径不在受控工件目录内")
                target = (root / rel).resolve()
                if root.resolve() not in target.parents or not target.is_file():
                    raise ForbiddenError("证据路径校验失败")
                return target
        raise NotFoundError("验收轮或检查项不存在")


def _now() -> str:
    from backend.platform.sqlite import utc_now_iso  # noqa: PLC0415

    return utc_now_iso()
