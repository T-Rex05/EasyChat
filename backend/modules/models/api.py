"""models 模块公开接口：模型配置管理与 run 模型选择。

- chat：当前激活配置；auxiliary：辅助任务（记忆提取/评估）首选后备；
- fallback：辅助选择的回退链；本地有界状态，不依赖 Redis 熔断同步；
- 所有对外表示只含掩码密钥；系统主体显式使用 contracts.SYSTEM_USER_ID。
"""
from __future__ import annotations

from typing import Any

from backend.modules.models.contracts import ModelProfile, ModelSelection
from backend.modules.models.repository import ModelsRepository
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import ForbiddenError, InvalidInputError, NotFoundError


class ModelsService:
    def __init__(
        self,
        db: Database,
        *,
        encryption_secret: str,
        permission_check: Any = None,
    ) -> None:
        """permission_check: Callable[[Principal, str], None] 由 bootstrap 注入 access。"""
        self.repo = ModelsRepository(db, encryption_secret=encryption_secret)
        self._permission_check = permission_check
        self._fail_counts: dict[int, int] = {}

    # ---- 管理（system.manage / system.config 权限在调用方执行） -------------------

    def list_configs(self, actor: Principal) -> list[ModelProfile]:
        self._require(actor, "system.config")
        return self.repo.list_configs()

    def create_config(
        self,
        actor: Principal,
        *,
        name: str,
        provider: str,
        model: str,
        api_key: str = "",
        base_url: str = "",
        is_multimodal: bool = False,
        reasoning_effort: str = "",
    ) -> int:
        self._require(actor, "system.config")
        if not name or not provider or not model:
            raise InvalidInputError("name/provider/model 必填")
        return self.repo.create_config(
            name=name, provider=provider, model=model, api_key=api_key,
            base_url=base_url, is_multimodal=is_multimodal, reasoning_effort=reasoning_effort,
        )

    def update_config(self, actor: Principal, config_id: int, **fields: Any) -> None:
        self._require(actor, "system.config")
        self.repo.update_config(config_id, **fields)

    def set_active(self, actor: Principal, config_id: int) -> None:
        self._require(actor, "system.config")
        self.repo.set_active(config_id)

    def delete_config(self, actor: Principal, config_id: int) -> None:
        self._require(actor, "system.config")
        self.repo.delete_config(config_id)

    def get_fallback_chain(self, actor: Principal) -> list[dict[str, Any]]:
        self._require(actor, "system.config")
        chain = self.repo.get_fallback_chain()
        out = []
        for cid in chain:
            profile = self.repo.get_config(cid)
            if profile is not None:
                out.append(profile.__dict__)
        return out

    def save_fallback_chain(self, actor: Principal, config_ids: list[int]) -> None:
        self._require(actor, "system.config")
        self.repo.save_fallback_chain(config_ids)

    # ---- 选择（run 执行路径；不要求管理权限） ------------------------------------

    def get_chat_profile(self) -> ModelProfile | None:
        return self.repo.get_active_chat()

    def select_for_run(self, *, auxiliary: bool = False) -> ModelSelection:
        """run 的模型选择：主配置 + 可选辅助链（无可用配置返回空选择，由调用方报错）。"""
        chat = self.repo.get_active_chat()
        if chat is None:
            raise NotFoundError("未配置可用的聊天模型")
        fallback: list[ModelProfile] = []
        if auxiliary:
            for cid in self.repo.get_fallback_chain():
                profile = self.repo.get_config(cid)
                if profile is not None:
                    fallback.append(profile)
        return ModelSelection(chat=chat, auxiliary=None, fallback=tuple(fallback))

    # ---- 状态（本机有界，无 Redis） ----------------------------------------------

    def report_health(self, config_id: int, ok: bool) -> None:
        """调用成功/失败的本机状态记录（简单连续失败计数，供选择器跳过持续不可用配置）。"""
        if ok:
            self._fail_counts.pop(config_id, None)
        else:
            self._fail_counts[config_id] = self._fail_counts.get(config_id, 0) + 1
        if len(self._fail_counts) > 64:
            oldest = next(iter(self._fail_counts))
            self._fail_counts.pop(oldest, None)

    def is_healthy(self, config_id: int) -> bool:
        return self._fail_counts.get(config_id, 0) < 3

    def _require(self, actor: Principal, permission: str) -> None:
        """管理操作权限检查。检查函数由 bootstrap 注入 access 公开接口。"""
        if self._permission_check is None:
            raise ForbiddenError(f"缺少权限: {permission}")
        self._permission_check(actor, permission)
