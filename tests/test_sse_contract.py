"""SSE 帧契约守卫测试：生产端与消费端的 type 集合必须 ⊆ 契约声明

覆盖三处生产源：
  1. backend/controller/chat/stream.py 的 `'type': 'x'` 字面量
  2. backend/service/delegation/sse_bridge.py 的子 Agent 事件→帧类型映射
  3. 前端 agent_frontend/src/api/chat.ts 的 switch case
"""
import re
from pathlib import Path

from backend.service.sse_frame_contract import ALL_FRAME_TYPES

ROOT = Path(__file__).resolve().parent.parent
STREAM_PY = ROOT / "backend" / "controller" / "chat" / "stream.py"
CHAT_TS = ROOT / "agent_frontend" / "src" / "api" / "chat.ts"


def _produced_types():
    text = STREAM_PY.read_text(encoding="utf-8")
    return set(re.findall(r"'type':\s*'([a-z_]+)'", text))


def _consumed_types():
    text = CHAT_TS.read_text(encoding="utf-8")
    return set(re.findall(r"case\s+'([a-z_]+)':", text))


class TestSseContract:
    def test_produced_types_declared(self):
        produced = _produced_types()
        assert produced, "未解析到生产端帧 type，检查正则"
        undeclared = produced - ALL_FRAME_TYPES
        assert not undeclared, f"生产端使用了未声明契约的帧 type: {undeclared}"

    def test_consumed_types_declared(self):
        consumed = _consumed_types()
        assert consumed, "未解析到消费端帧 type，检查正则"
        undeclared = consumed - ALL_FRAME_TYPES
        assert not undeclared, f"前端消费了未声明契约的帧 type: {undeclared}"

    def test_contract_covers_common_types(self):
        for t in ("start", "token", "stream_reset", "tool_call", "tool_output", "chat_complete", "error"):
            assert t in ALL_FRAME_TYPES

    def test_subagent_frame_mapping_declared(self):
        """子 Agent 帧的生产源：事件→帧类型映射的每个值都必须在契约里。

        历史上这里的守卫只扫 stream.py，子 Agent 帧由 delegate_tool 自己拼字符串，
        完全在守卫视野之外（契约漂移无人发现）。现在生产源收敛到 sse_bridge 的映射表，
        这里把它纳入守卫。
        """
        from backend.service.delegation.sse_bridge import SUBAGENT_EVENT_TO_FRAME

        assert SUBAGENT_EVENT_TO_FRAME, "子 Agent 事件映射丢失"
        undeclared = set(SUBAGENT_EVENT_TO_FRAME.values()) - ALL_FRAME_TYPES
        assert not undeclared, f"子 Agent 帧未声明契约: {undeclared}"
        # 前端确实消费了这 4 个帧（防止只改后端不改前端）
        consumed = _consumed_types()
        assert set(SUBAGENT_EVENT_TO_FRAME.values()) <= consumed, (
            f"前端未消费子 Agent 帧: {set(SUBAGENT_EVENT_TO_FRAME.values()) - consumed}"
        )
