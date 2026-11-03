"""usage 模块公开契约：唯一计量入口的数据结构（架构 §7）。

每个真实出站 LLM 请求分配本地唯一 call_id；重试请求是新的 call_id；
同一请求的 observer 回调重复不产生新计量。run_id 不是 call_id。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NormalizedUsage:
    """供应商无关的规范化用量。

    input_tokens 为未含缓存的输入；prompt_tokens = input + cache_read + cache_write。
    各字段可为 None（未知）；usage_complete=False 表示不完整，等待补全。
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    usage_complete: bool = False

    def prompt_tokens(self) -> int | None:
        if self.input_tokens is None:
            return None
        return self.input_tokens + (self.cache_read_tokens or 0) + (self.cache_write_tokens or 0)


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """一次真实出站调用的计量记录。

    owner_id=0 表示系统主体（记忆提取/评估/回放等），不归属任何真实用户。
    """

    call_id: str
    owner_id: int
    source: str  # chat / memory / evolution / schedule
    provider: str
    model: str
    run_id: str | None = None
    session_id: str | None = None
    usage: NormalizedUsage | None = None
    estimated: bool = False
    error: str | None = None


SYSTEM_OWNER_ID = 0
VALID_SOURCES = frozenset({"chat", "memory", "evolution", "schedule"})
