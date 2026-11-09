"""辅助文本生成（OpenAI 兼容 /chat/completions）。

只用于简报/收件箱富化等短文本；失败返回空串，由调用方回退确定性模板。
每次真实请求单独走 usage 计量，不记录 api_key。
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from backend.modules.usage.contracts import NormalizedUsage

logger = logging.getLogger(__name__)


class TextGenerator(Protocol):
    async def generate(
        self, system: str, user: str, *, owner_id: int = 0, max_chars: int = 300
    ) -> str: ...


class OpenAICompatibleTextGenerator:
    def __init__(
        self,
        *,
        models: Any,
        usage: Any = None,
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.models = models
        self.usage = usage
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def generate(
        self, system: str, user: str, *, owner_id: int = 0, max_chars: int = 300
    ) -> str:
        try:
            selection = self.models.select_for_run(auxiliary=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("辅助模型选择失败: %s", exc)
            return ""
        profile = selection.chat
        if profile.provider.lower() not in ("openai", "openai-compatible", "deepseek", "custom"):
            return ""
        try:
            api_key = self.models.resolve_api_key(profile.config_id)
        except Exception:  # noqa: BLE001
            return ""
        if not api_key or not profile.base_url:
            return ""
        call_id = ""
        if self.usage is not None:
            try:
                call_id = self.usage.begin_call(
                    owner_id=owner_id, source="schedule",
                    provider=profile.provider, model=profile.model,
                )
            except Exception:  # noqa: BLE001  计量失败不阻断生成
                call_id = ""
        url = profile.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": profile.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.4,
            # 上限须容纳推理型模型的思考 token：800 的旧上限会让 reasoning
            # 耗尽预算、content 为空（finish_reason=length）。
            "max_tokens": max(256, min(4000, max_chars * 4)),
        }
        text = ""
        error = ""
        usage_value = None
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(
                    url, json=payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
            text = str(
                ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            ).strip()
            raw_usage = data.get("usage") or {}
            if raw_usage:
                usage_value = NormalizedUsage(
                    input_tokens=raw_usage.get("prompt_tokens"),
                    output_tokens=raw_usage.get("completion_tokens"),
                    total_tokens=raw_usage.get("total_tokens"),
                    usage_complete=True,
                )
        except Exception as exc:  # noqa: BLE001  网络/上游失败回退模板
            error = str(exc)
            # httpx 超时类异常的 str() 为空，必须带上类型名才可诊断。
            logger.warning("辅助文本生成失败: %s: %s", type(exc).__name__, exc)
        finally:
            if call_id and self.usage is not None:
                try:
                    self.usage.complete_call(call_id, usage_value, error=error or None)
                except Exception:  # noqa: BLE001
                    logger.exception("辅助生成计量结账失败")
        if error:
            return ""
        return text[:max_chars]
