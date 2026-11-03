"""Assistant 统一执行入口的公开契约（架构 §4）。

Web/微信/定时任务都构造 RunCommand 提交；渠道只处理协议与显示/投递。
"""
from dataclasses import dataclass
from typing import Mapping

from backend.shared.context import Principal


@dataclass(frozen=True, slots=True)
class RunCommand:
    principal: Principal
    session_id: str
    source: str  # web / wechat / schedule
    client_message_id: str
    text: str
    attachment_ids: tuple[str, ...] = ()
    channel_account_id: str | None = None


@dataclass(frozen=True, slots=True)
class RunReceipt:
    run_id: str
    session_id: str
    state: str
    duplicate: bool


@dataclass(frozen=True, slots=True)
class RunEvent:
    run_id: str
    seq: int
    kind: str
    payload: Mapping[str, object]
