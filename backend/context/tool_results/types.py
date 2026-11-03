"""Trusted identity for stored tool results; physical sessions are audit data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResultScope:
    user_id: str
    thread_id: str
    agent_id: str = "root"
    session_id: str = ""
    run_id: str = ""
    tool_call_id: str = ""
    attempt_id: str = "1"

    def __post_init__(self):
        for name, value in vars(self).items():
            if not isinstance(value, str) or len(value.encode("utf-8")) > 512:
                raise ValueError(f"{name} must be a string of at most 512 bytes")
        if not self.user_id or not self.thread_id or not self.agent_id:
            raise ValueError("user_id, thread_id and agent_id are required")
