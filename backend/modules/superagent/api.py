"""superagent 服务：受理任务、配置仓库、查询与生命周期控制。

权限边界：
- 查看：superagent.view（仅本人）；superagent.manage 可跨用户。
- 提交：superagent.create；微信对话经业务工具进入同一入口。
- 配置（仓库/凭证/开关）：superagent.manage。

Gate：enabled 且 repo_url 非空才受理新任务；GitHub token 可后补
（未配置 token 时任务仍可受理，执行阶段报失败并写事件）。
"""
from __future__ import annotations

import logging

from backend.modules.access.api import AccessService
from backend.modules.superagent.contracts import (
    REQUIREMENT_MAX_CHARS,
    SOURCE_TOOL,
    SOURCE_WEB,
    SOURCE_WECHAT,
    SuperagentSettings,
    SuperagentTask,
    TASK_CANCELLED,
    TASK_QUEUED,
    TASK_RUNNING,
    TERMINAL_TASK_STATUSES,
)
from backend.modules.superagent.repository import SuperagentRepository
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.crypto import decrypt_secret, encrypt_secret, mask_secret
from backend.shared.errors import ForbiddenError, InvalidInputError, NotFoundError

logger = logging.getLogger(__name__)

_SOURCES = frozenset({SOURCE_WECHAT, SOURCE_WEB, SOURCE_TOOL})


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
        self.access = access
        self.delivery = delivery
        self.channels = channels
        self._encryption_secret = ""
        self._run_canceller = None

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
    ) -> SuperagentSettings:
        self.access.validate_principal(principal)
        self.access.require_permission(principal, "superagent.manage")
        if repo_url is not None and repo_url.strip():
            _validate_repo_url(repo_url.strip())
        if github_token is not None:
            secret = str(github_token).strip()
            if not self._encryption_secret:
                raise InvalidInputError("未配置 EASYCHAT_ENCRYPTION_SECRET，无法保存 GitHub 凭证")
            encrypted = encrypt_secret(secret, self._encryption_secret) if secret else ""
            self.repo.update_settings(github_token_enc=encrypted)
        self.repo.update_settings(
            enabled=enabled,
            repo_url=repo_url,
            base_branch=base_branch,
            pr_labels=pr_labels,
            max_concurrent=max_concurrent,
        )
        return self.repo.get_settings()

    def set_encryption_secret(self, secret: str) -> None:
        """bootstrap 注入部署密钥（token 加密只存内存引用，不落库）。"""
        self._encryption_secret = str(secret or "")

    def set_run_canceller(self, canceller) -> None:
        """worker 注入协作取消回调（runtime.cancel）。"""
        self._run_canceller = canceller

    # ---- 任务受理 ----------------------------------------------------------------

    def create_task(
        self, principal: Principal, *, title: str, requirement: str,
        context_extra: str = "", source: str = SOURCE_WEB, session_id: str = "",
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
        if len(requirement) > REQUIREMENT_MAX_CHARS:
            raise InvalidInputError(f"需求描述过长（≤{REQUIREMENT_MAX_CHARS} 字）")
        settings = self.repo.get_settings()
        if not settings.enabled or not settings.repo_url:
            raise InvalidInputError("超级代理未启用或未配置目标仓库，请联系管理员")
        task = self.repo.create_task(
            owner_id=principal.user_id, title=title, requirement=requirement,
            context_extra=str(context_extra or "").strip(),
            source=source, session_id=str(session_id or ""),
        )
        self.repo.append_event(task.task_id, "created", f"来源 {source}；分支 {task.branch}")
        logger.info("superagent 任务已受理 task_id=%s owner=%s", task.task_id, principal.user_id)
        return task

    # ---- 查询 ------------------------------------------------------------------

    def list_tasks(self, principal: Principal, *, limit: int = 50) -> list[SuperagentTask]:
        self.access.validate_principal(principal)
        if self._can_manage(principal):
            return self.repo.list_all(limit=limit)
        return self.repo.list_for_owner(principal.user_id, limit=limit)

    def get_task(self, principal: Principal, task_id: str) -> SuperagentTask:
        task = self._task_for(principal, task_id)
        _ = task
        return task

    def list_events(self, principal: Principal, task_id: str):
        self._task_for(principal, task_id)
        return self.repo.events_for_task(task_id)

    # ---- 生命周期 ----------------------------------------------------------------

    def cancel_task(self, principal: Principal, task_id: str) -> SuperagentTask:
        task = self._task_for(principal, task_id)
        if task.status in TERMINAL_TASK_STATUSES:
            return task
        if task.status == TASK_QUEUED:
            self.repo.update_fields(task_id, status=TASK_CANCELLED, finished_at=_now())
            self.repo.append_event(task_id, "cancelled", "任务在执行前被取消")
        elif task.status == TASK_RUNNING:
            # 运行中：先标记取消，worker 完成时发现终态即放弃写结果；
            # 协作中断由 worker 注入的 canceller 处理。
            self.repo.update_fields(task_id, status=TASK_CANCELLED, finished_at=_now())
            self.repo.append_event(task_id, "cancelled", "已请求取消，等待当前步骤结束")
            canceller = getattr(self, "_run_canceller", None)
            if canceller is not None and task.run_id:
                try:
                    canceller(task.run_id)
                except Exception:  # noqa: BLE001
                    logger.exception("协作取消失败 task_id=%s run_id=%s", task_id, task.run_id)
        return self.repo.get_task(task_id)  # type: ignore[return-value]

    def retry_task(self, principal: Principal, task_id: str) -> SuperagentTask:
        self._task_for(principal, task_id)
        self.access.require_permission(principal, "superagent.create")
        if not self.repo.requeue(task_id):
            raise InvalidInputError("只有失败或已取消的任务可以重试")
        self.repo.append_event(task_id, "created", "手动重试，重新入队")
        return self.repo.get_task(task_id)  # type: ignore[return-value]

    # ---- worker 协作入口（内部） ---------------------------------------------------

    def claim_due_tasks(self, limit: int) -> list[SuperagentTask]:
        return self.repo.claim_due_tasks(limit)

    def task(self, task_id: str) -> SuperagentTask | None:
        return self.repo.get_task(task_id)

    def append_event(self, task_id: str, kind: str, detail: str = "") -> None:
        self.repo.append_event(task_id, kind, detail)

    def recover_interrupted(self) -> int:
        return self.repo.reset_running_tasks()

    # ---- 内部 ------------------------------------------------------------------

    def _can_manage(self, principal: Principal) -> bool:
        return "superagent.manage" in self.access.effective_permissions(principal.user_id)

    def _task_for(self, principal: Principal, task_id: str) -> SuperagentTask:
        self.access.validate_principal(principal)
        task = self.repo.get_task(task_id)
        if task is None:
            raise NotFoundError("任务不存在")
        if task.owner_id != principal.user_id and not self._can_manage(principal):
            raise ForbiddenError("无权访问该任务")
        return task


def _now() -> str:
    from backend.platform.sqlite import utc_now_iso  # noqa: PLC0415

    return utc_now_iso()


def _validate_repo_url(repo_url: str) -> None:
    lowered = repo_url.lower()
    ok = (
        lowered.startswith("https://")
        and ("github.com/" in lowered or "gitee.com/" in lowered)
    ) or lowered.startswith("git@")
    if not ok:
        raise InvalidInputError("仓库地址仅支持 https://github.com/...、https://gitee.com/... 或 git@ 形式")


def decrypt_github_token(token_enc: str, encryption_secret: str) -> str:
    """worker 用：解密 GitHub 凭证；明文兼容。"""
    if not token_enc:
        return ""
    return decrypt_secret(token_enc, encryption_secret)


def mask_token_preview(token: str) -> str:
    return mask_secret(token)
