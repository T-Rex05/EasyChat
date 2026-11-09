"""微信纯文本渲染：微信不支持 Markdown，发送前做保守降级。

不改变语义、不截断内容（分块由 delivery 负责）；只去掉排版标记，
避免用户看到 ``**``、代码围栏和 ATX 标题。
"""
from __future__ import annotations

import re

_FENCE_RE = re.compile(r"^\s*```[^\n]*$", re.MULTILINE)
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_HR_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)


def to_wechat_text(text: str) -> str:
    value = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = _FENCE_RE.sub("", value)
    value = _HEADER_RE.sub("", value)
    value = _HR_RE.sub("", value)
    value = _BOLD_RE.sub(r"\2", value)
    value = _INLINE_CODE_RE.sub(r"\1", value)
    value = _LINK_RE.sub(r"\1（\2）", value)
    value = _BULLET_RE.sub("• ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()
