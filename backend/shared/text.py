"""共享文本切分：渠道发送与投递分块使用同一规则。

按空行分段、尽量保持代码块/段落完整；单块超过上限时在换行处硬切。
"""
from __future__ import annotations

DEFAULT_CHUNK_CHARS = 1800


def split_text(text: str, limit: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(block) > limit:
            cut = block.rfind("\n", 0, limit)
            cut = cut if cut > 0 else limit
            chunks.append(block[:cut])
            block = block[cut:].lstrip("\n")
        current = block
    if current:
        chunks.append(current)
    return chunks
