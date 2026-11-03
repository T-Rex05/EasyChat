"""真实 Hermes AIAgent 构建工厂。

仅在 HermesRuntimeAdapter.startup 之后经 _default_agent_factory 调用；
测试不经过此模块。密钥解密只发生在本层（runtime 受信任边界内）。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_agent(request: Any, profile: dict[str, Any], *, hermes_home: Any, models: Any = None) -> Any:
    """按 RuntimeRequest + 模型 profile 构造 AIAgent（同步，秒级，调用方缓存）。"""
    from pathlib import Path

    from backend.runtime.hermes.paths import ensure_hermes_environment

    ensure_hermes_environment(Path(hermes_home))

    from hermes_state import SessionDB  # noqa: PLC0415  (Hermes 顶层模块)
    from run_agent import AIAgent  # noqa: PLC0415

    ctx = request.context
    api_key = _resolve_api_key(profile, models)
    enabled_toolsets = sorted(frozenset(request.allowed_tools)) if request.allowed_tools else []

    kwargs: dict[str, Any] = {
        "session_id": ctx.session_id,
        "thread_id": ctx.run_id,
        "user_id": ctx.principal.user_id,
        "session_db": SessionDB(),  # 不传等于静默关闭持久化
        "skip_memory": True,  # 记忆走 EasyChat memory 模块（Task 9 桥接）
        "enabled_toolsets": enabled_toolsets,
        "compression_enabled": True,  # 会话压缩保留（原始工具结果证据在 state.db）
    }
    if profile.get("base_url"):
        kwargs["base_url"] = _normalize_base_url(str(profile["base_url"]), str(profile.get("provider", "")))
    if api_key:
        kwargs["api_key"] = api_key
    if profile.get("model"):
        kwargs["model"] = _strip_model_suffix(str(profile["model"]))
    if profile.get("provider"):
        kwargs["provider"] = str(profile["provider"])

    effort = _reasoning_effort(profile)
    if effort is not None:
        kwargs["reasoning_config"] = effort

    fallback = _fallback_profile(models)
    if fallback:
        fb_key = _resolve_api_key(fallback, models)
        kwargs["fallback_model"] = {
            "base_url": _normalize_base_url(str(fallback.get("base_url", "")), str(fallback.get("provider", ""))),
            "api_key": fb_key,
            "model": _strip_model_suffix(str(fallback.get("model", ""))),
            "provider": str(fallback.get("provider", "")),
        }

    agent = AIAgent(**kwargs)
    # 关闭 Hermes 原生后台审查（记忆/技能整理统一走 EasyChat evolution，Task 11）
    for attr in ("_skill_nudge_interval", "_memory_nudge_interval"):
        try:
            setattr(agent, attr, 0)
        except Exception:  # noqa: BLE001
            logger.warning("无法关闭 %s（旧版内核）", attr)
    return agent


def _normalize_base_url(base_url: str, provider: str) -> str:
    if not base_url:
        return base_url
    if "anthropic" in provider.lower() or "anthropic" in base_url.lower():
        return base_url
    if "/v1" in base_url or base_url.rstrip("/").endswith("/v1"):
        return base_url
    if "ollama" in provider.lower():
        return base_url.rstrip("/") + "/v1"
    return base_url.rstrip("/") + "/v1"


def _strip_model_suffix(model: str) -> str:
    for suffix in ("[1m]", "[128k]"):
        if model.endswith(suffix):
            return model[: -len(suffix)]
    return model


def _reasoning_effort(profile: dict[str, Any]) -> Any:
    effort = str(profile.get("reasoning_effort", "") or "")
    if not effort:
        return None
    try:
        from hermes_constants import parse_reasoning_effort  # noqa: PLC0415

        return parse_reasoning_effort(effort)
    except Exception:  # noqa: BLE001
        return None


def _resolve_api_key(profile: dict[str, Any], models: Any) -> str:
    if profile.get("api_key"):
        return str(profile["api_key"])
    if models is not None and profile.get("profile_id") is not None:
        try:
            return models.resolve_api_key(int(profile["profile_id"]))
        except Exception:  # noqa: BLE001
            logger.warning("模型密钥解析失败 profile_id=%s", profile.get("profile_id"))
    return ""


def _fallback_profile(models: Any) -> dict[str, Any] | None:
    if models is None:
        return None
    try:
        selection = models.select_for_run(auxiliary=False)
    except Exception:  # noqa: BLE001
        return None
    for profile in selection.fallback:
        return {
            "base_url": profile.base_url,
            "model": profile.model,
            "provider": profile.provider,
            "profile_id": profile.config_id,
        }
    return None
