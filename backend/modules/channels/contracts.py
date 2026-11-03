"""channels 模块公开契约（架构 §3.1、§4、§5.2）。

渠道只负责协议、身份绑定、归一化与生命周期；执行统一走 Assistant.submit，
不在这里选模型、写 run 状态或直接触碰 Hermes。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

PLATFORM_WECHAT = "wechat"

ACCOUNT_ACTIVE = "active"
ACCOUNT_DISABLED = "disabled"

BINDING_ACTIVE = "active"
BINDING_DISABLED = "disabled"

EVENT_RECEIVED = "received"
EVENT_PROCESSED = "processed"
EVENT_REJECTED = "rejected"

# 入站处理结果（拒绝也要落 channel_events，避免同一事件被反复处理）
REASON_OK = "ok"
REASON_DUPLICATE = "duplicate"
REASON_ACCOUNT_DISABLED = "account_disabled"
REASON_ACCOUNT_UNKNOWN = "account_unknown"
REASON_UNBOUND = "unbound"
REASON_USER_DISABLED = "user_disabled"
REASON_FORBIDDEN = "forbidden"
REASON_EMPTY = "empty"
REASON_INVALID = "invalid"
REASON_BUSY = "busy"
REASON_MEDIA_FAILED = "media_failed"
REASON_INTERNAL = "internal"

# 无稳定 message_id 时的近似指纹短窗口（秒）。窗口桶保证相同文本只在窗口内
# 去重，窗口过后可再次处理，不会被永久吞掉（架构 Task 7）。
DEFAULT_FINGERPRINT_WINDOW_SECONDS = 5.0
MAX_MEDIA_REFS_PER_MESSAGE = 10
MAX_MEDIA_BYTES = 50 * 1024 * 1024

# 监听器真实状态：running 只在至少一次成功轮询后成立，不设假 running 标志。
LISTENER_STOPPED = "stopped"
LISTENER_STARTING = "starting"
LISTENER_RUNNING = "running"
LISTENER_BACKOFF = "backoff"
LISTENER_ERROR = "error"

# QR 会话状态
QR_WAIT = "wait"
QR_SCANNED = "scanned"
QR_CONFIRMED = "confirmed"
QR_EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class ChannelAccount:
    """机器人账号（channel_accounts）。credentials 不在值对象里明文出现。"""

    id: str
    platform: str
    account_id: str
    display_name: str = ""
    status: str = ACCOUNT_ACTIVE
    base_url: str = ""
    bot_user_id: str = ""
    sync_cursor: str = ""
    last_poll_at: str | None = None
    last_error: str = ""
    has_credentials: bool = False
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class ChannelBinding:
    id: str
    platform: str
    account_id: str
    external_user_id: str
    user_id: int
    status: str = BINDING_ACTIVE
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class MediaRef:
    """媒体引用：只记录下载/解密所需描述，绝不携带文件字节。

    下载由注入的 MediaFetcher 落盘并登记附件，事件 payload 中只保存本结构，
    因此同一消息重复读取不会把图片/文件累积进进程内存。
    """

    kind: str  # image / voice / file / video
    url: str = ""
    encrypt_query_param: str = ""
    aes_key: str = ""
    file_name: str = ""
    size: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "url": self.url,
            "encrypt_query_param": self.encrypt_query_param,
            "aes_key": self.aes_key,
            "file_name": self.file_name,
            "size": self.size,
        }


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """归一化后的入站消息（平台 → 内部字段的唯一转换结果）。"""

    platform: str
    account_pk: str  # channel_accounts.id（内部主键，不是平台 openid）
    external_account_id: str  # 机器人平台账号
    external_user_id: str
    external_chat_id: str
    external_event_id: str  # msg:<id> 或 fp:<fingerprint>:<窗口桶>
    text: str = ""
    media: tuple[MediaRef, ...] = ()
    context_token: str = ""
    received_at: float = 0.0
    fingerprint: str = ""
    fingerprint_window: float = DEFAULT_FINGERPRINT_WINDOW_SECONDS
    event_kind: str = "message"  # message_id / fingerprint


@dataclass(frozen=True, slots=True)
class InboundOutcome:
    accepted: bool
    reason: str
    run_id: str = ""
    session_id: str = ""
    duplicate: bool = False
    event_id: str = ""
    reply_text: str = ""


@dataclass(frozen=True, slots=True)
class ListenerState:
    account_id: str
    status: str
    since: float
    last_error: str = ""
    polls: int = 0
    last_poll_at: float | None = None


@dataclass(frozen=True, slots=True)
class QrSessionView:
    session_id: str
    status: str
    qr_image: str = ""
    qr_content: str = ""
    expires_at: float = 0.0
    account_id: str = ""
    base_url: str = ""


@dataclass(frozen=True, slots=True)
class ChannelAccountView:
    """对外账号视图：凭证只出掩码/是否存在。"""

    id: str
    platform: str
    account_id: str
    display_name: str
    status: str
    base_url: str
    bot_user_id: str
    last_poll_at: str | None
    last_error: str
    has_credentials: bool


@dataclass(frozen=True, slots=True)
class EncryptedCredentials:
    """持久化前的凭证载荷：token 已加密，其余为连接元数据。"""

    token_ciphertext: str
    base_url: str = ""
    bot_user_id: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)
