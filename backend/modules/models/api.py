"""models 模块公开接口：模型配置管理与 run 模型选择。

- chat：当前激活配置；auxiliary：辅助任务（记忆提取/评估）首选后备；
- fallback：辅助选择的回退链；本地有界状态，不依赖 Redis 熔断同步；
- 所有对外表示只含掩码密钥；系统主体显式使用 contracts.SYSTEM_USER_ID。
"""
from __future__ import annotations

from dataclasses import asdict
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import httpx

from backend.modules.models.contracts import ModelProfile, ModelSelection
from backend.modules.models.repository import ModelsRepository
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import ForbiddenError, InvalidInputError, NotFoundError
from backend.shared.model_endpoint import model_base_url


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

    async def test_connection(
        self, actor: Principal, config_id: int, *, transport: httpx.AsyncBaseTransport | None = None,
    ) -> dict[str, Any]:
        self._require(actor, "system.config")
        profile = self.repo.get_config(config_id)
        if profile is None:
            raise NotFoundError("模型配置不存在")
        try:
            base = model_base_url(profile.base_url, profile.provider)
            parsed = urlsplit(base)
            endpoint = httpx.URL(base)
        except (httpx.InvalidURL, ValueError) as exc:
            raise InvalidInputError("模型 API 基础地址格式无效") from exc
        if (endpoint.scheme not in ("http", "https") or not endpoint.host
                or parsed.username is not None or parsed.query or parsed.fragment):
            raise InvalidInputError("请填写 HTTP(S) 模型 API 基础地址，密钥请填在 API Key 栏")
        key = self.resolve_api_key(config_id)
        anthropic = "anthropic" in profile.provider.lower() or "anthropic" in base.lower()
        headers = {}
        if anthropic:
            headers["anthropic-version"] = "2023-06-01"
            if key:
                headers["x-api-key"] = key
            url = base.removesuffix("/v1") + "/v1/messages"
        else:
            if key:
                headers["Authorization"] = f"Bearer {key}"
            url = base + "/chat/completions"
        payload = {"model": profile.model, "max_tokens": 512, "messages": [{"role": "user", "content": "Reply OK."}]}
        start = monotonic()
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False, transport=transport) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException:
            return {"ok": False, "message": "模型服务响应超时"}
        except httpx.RequestError:
            return {"ok": False, "message": "无法连接模型服务，请检查基础地址、网络和代理"}
        result = {"status_code": response.status_code, "latency_ms": round((monotonic() - start) * 1000)}
        if not response.is_success:
            hint = {401: "请检查 API Key", 403: "请检查密钥权限和订阅端点", 404: "请检查基础地址和模型名",
                    429: "请检查额度或稍后重试"}.get(response.status_code, "请检查服务状态和模型配置")
            return {**result, "ok": False, "message": f"模型服务返回 HTTP {response.status_code}，{hint}"}
        try:
            data = response.json()
            blocks = data["content"] if anthropic else [data["choices"][0]["message"]]
            field = "text" if anthropic else "content"
            has_text = any(isinstance(b.get(field), str) and b[field].strip() for b in blocks)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            has_text = False
        return {**result, "ok": has_text, "message": "模型已返回文本回复" if has_text else "服务已响应，但未返回文本回复"}

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
                out.append(asdict(profile))
        return out

    def save_fallback_chain(self, actor: Principal, config_ids: list[int]) -> None:
        self._require(actor, "system.config")
        self.repo.save_fallback_chain(config_ids)

    # ---- 选择（run 执行路径；不要求管理权限） ------------------------------------

    def get_chat_profile(self) -> ModelProfile | None:
        return self.repo.get_active_chat()

    def resolve_api_key(self, config_id: int) -> str:
        """runtime Adapter 专用：解密密钥。不得写入日志或任何对外响应。"""
        return self.repo.decrypt_api_key(config_id)

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
