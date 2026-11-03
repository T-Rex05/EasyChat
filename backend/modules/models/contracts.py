"""models 模块公开契约：模型配置与选择（架构 §6）。

chat/auxiliary/可选fallback；不带 embedding/rerank 管理。
SYSTEM_USER_ID 常量：系统任务显式主体，不猜测 user_id=1。
"""
from __future__ import annotations

from dataclasses import dataclass

SYSTEM_USER_ID = 0


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """模型配置快照。api_key 永不出现在对外表示中（仅密文引用/掩码）。"""

    config_id: int
    name: str
    provider: str
    model: str
    base_url: str
    api_key_masked: str
    has_api_key: bool
    is_active: bool
    is_multimodal: bool
    reasoning_effort: str
    config_version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ModelSelection:
    """一次 run 的模型选择结果。"""

    chat: ModelProfile
    auxiliary: ModelProfile | None
    fallback: tuple[ModelProfile, ...]
