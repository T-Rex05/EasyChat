"""iLink 入站消息 → 统一 InboundMessage。

只做协议归一化：不解密、不下载、不调用模型。媒体只保留下载/解密描述，
因此事件记录和重复读取不会把图片/文件字节留在进程内存。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from backend.modules.channels.contracts import (
    DEFAULT_FINGERPRINT_WINDOW_SECONDS,
    MAX_MEDIA_REFS_PER_MESSAGE,
    ChannelAccount,
    InboundMessage,
    MediaRef,
)

ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5

_MEDIA_KINDS = {
    ITEM_IMAGE: "image",
    ITEM_VOICE: "voice",
    ITEM_FILE: "file",
    ITEM_VIDEO: "video",
}


def _item_url(payload: Mapping[str, Any]) -> str:
    media = payload.get("media") if isinstance(payload.get("media"), Mapping) else {}
    for value in (
        payload.get("url"),
        payload.get("cdn_url"),
        payload.get("full_url"),
        payload.get("cdn_url_full"),
        media.get("full_url") if isinstance(media, Mapping) else "",
    ):
        if value:
            return str(value)
    return ""


def _item_aes_key(payload: Mapping[str, Any]) -> str:
    media = payload.get("media") if isinstance(payload.get("media"), Mapping) else {}
    for value in (
        payload.get("aeskey"),
        payload.get("aes_key"),
        media.get("aes_key") if isinstance(media, Mapping) else "",
        media.get("aeskey") if isinstance(media, Mapping) else "",
    ):
        if value:
            return str(value)
    return ""


def _media_ref(kind: str, payload: Mapping[str, Any]) -> MediaRef | None:
    media = payload.get("media") if isinstance(payload.get("media"), Mapping) else {}
    encrypt_query_param = str(
        (media.get("encrypt_query_param") if isinstance(media, Mapping) else "")
        or payload.get("encrypt_query_param")
        or ""
    )
    url = _item_url(payload)
    if not url and not encrypt_query_param:
        return None  # 无可下载描述：不进入内存/事件
    size = 0
    raw_size = payload.get("len") or payload.get("size") or payload.get("file_size") or 0
    try:
        size = max(0, int(raw_size))
    except (TypeError, ValueError):
        size = 0
    return MediaRef(
        kind=kind,
        url=url,
        encrypt_query_param=encrypt_query_param,
        aes_key=_item_aes_key(payload),
        file_name=str(payload.get("file_name") or payload.get("name") or "")[:255],
        size=size,
    )


def fingerprint_of(
    *,
    external_user_id: str,
    external_chat_id: str,
    text: str,
    media: tuple[MediaRef, ...],
) -> str:
    """近似指纹：稳定字段的规范化摘要；用于没有稳定 message_id 的短窗口去重。"""
    canonical = json.dumps(
        {
            "u": external_user_id,
            "c": external_chat_id,
            "t": text.strip(),
            "m": [
                [m.kind, m.url, m.encrypt_query_param, m.file_name, m.size]
                for m in media
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_inbound(
    account: ChannelAccount,
    msg: Mapping[str, Any],
    *,
    now: float,
    fingerprint_window: float = DEFAULT_FINGERPRINT_WINDOW_SECONDS,
) -> InboundMessage | None:
    """解析一条 getupdates 消息；机器人自身回声、空消息返回 None。"""
    from_user_id = str(msg.get("from_user_id") or "").strip()
    if not from_user_id or from_user_id == account.account_id:
        return None

    text_parts: list[str] = []
    media: list[MediaRef] = []
    seen: set[tuple[str, str, str, str, int]] = set()
    for item in msg.get("item_list") or []:
        if not isinstance(item, Mapping):
            continue
        try:
            item_type = int(item.get("type") or 0)
        except (TypeError, ValueError):
            continue
        if item_type == ITEM_TEXT:
            text_item = item.get("text_item") or {}
            if isinstance(text_item, Mapping):
                text_parts.append(str(text_item.get("text") or ""))
            continue
        kind = _MEDIA_KINDS.get(item_type)
        if kind is None:
            continue
        payload = item.get(f"{kind}_item") or item.get("file_item") or {}
        if not isinstance(payload, Mapping):
            continue
        ref = _media_ref(kind, payload)
        if ref is None:
            continue
        key = (ref.kind, ref.url, ref.encrypt_query_param, ref.file_name, ref.size)
        if key in seen:
            continue
        seen.add(key)
        if len(media) >= MAX_MEDIA_REFS_PER_MESSAGE:
            break  # 单条消息媒体引用有上限，防止异常大消息膨胀
        media.append(ref)

    text = "".join(text_parts).strip()
    if not text and not media:
        return None

    chat_id = str(msg.get("chat_id") or msg.get("room_id") or from_user_id)
    media_tuple = tuple(media)
    fingerprint = fingerprint_of(
        external_user_id=from_user_id, external_chat_id=chat_id, text=text, media=media_tuple,
    )
    raw_message_id = str(msg.get("message_id") or msg.get("msg_id") or "").strip()
    if raw_message_id:
        # 平台消息 ID 的作用域未被文档保证为全局；带上发送者，避免两个用户
        # 恰好同 ID 时后者被静默吞掉。账号维度另由 channel_events 唯一键覆盖。
        external_event_id = f"msg:{from_user_id[:48]}:{raw_message_id[:140]}"
        event_kind = "message_id"
    else:
        window = max(1.0, float(fingerprint_window))
        bucket = int(now // window)
        external_event_id = f"fp:{fingerprint[:32]}:{bucket}"
        event_kind = "fingerprint"

    return InboundMessage(
        platform=account.platform,
        account_pk=account.id,
        external_account_id=account.account_id,
        external_user_id=from_user_id,
        external_chat_id=chat_id,
        external_event_id=external_event_id,
        text=text,
        media=media_tuple,
        context_token=str(msg.get("context_token") or ""),
        received_at=now,
        fingerprint=fingerprint,
        fingerprint_window=fingerprint_window,
        event_kind=event_kind,
    )
