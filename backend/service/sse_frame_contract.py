"""
SSE 帧 type 契约 — 单一权威常量（借鉴 Eyes sse_frame_contract）

chat/stream.py 生产端与前端 chat.ts 消费端的帧 type 必须一致；
tests/test_sse_contract.py 有守卫测试：
  1. 生产端实际 yield 的 type ⊆ 本模块声明；
  2. 前端 switch 消费的 type ⊆ 本模块声明。
新增/改名 type 时先改这里，守卫测试会卡住漂移。
"""
FRAME_START = "start"
# 前端兼容别名（与 start 同义）
FRAME_CHAT_START = "chat_start"
FRAME_TOKEN = "token"
FRAME_STATUS = "status"
FRAME_TOOL_CALL = "tool_call"
FRAME_TOOL_OUTPUT = "tool_output"
FRAME_STREAM_RESET = "stream_reset"
FRAME_THINKING_STEP = "thinking_step"
FRAME_EXEC_APPROVAL_REQUEST = "exec_approval_request"
FRAME_DB_WRITE_APPROVAL_REQUEST = "db_write_approval_request"
FRAME_CHAT_COMPLETE = "chat_complete"
FRAME_ERROR = "error"

# ── 子 Agent 委派事件（P0: 多 Agent 可视化） ──
FRAME_SUBAGENT_START = "subagent_start"        # 子 Agent 开始执行
FRAME_SUBAGENT_TOKEN = "subagent_token"        # 子 Agent 流式 token
FRAME_SUBAGENT_TOOL = "subagent_tool"          # 子 Agent 工具调用
FRAME_SUBAGENT_COMPLETE = "subagent_complete"  # 子 Agent 执行完成


ALL_FRAME_TYPES = frozenset({
    FRAME_START,
    FRAME_CHAT_START,
    FRAME_TOKEN,
    FRAME_STATUS,
    FRAME_TOOL_CALL,
    FRAME_TOOL_OUTPUT,
    FRAME_STREAM_RESET,
    FRAME_THINKING_STEP,
    FRAME_EXEC_APPROVAL_REQUEST,
    FRAME_DB_WRITE_APPROVAL_REQUEST,
    FRAME_CHAT_COMPLETE,
    FRAME_ERROR,
    # 子 Agent 委派事件
    FRAME_SUBAGENT_START,
    FRAME_SUBAGENT_TOKEN,
    FRAME_SUBAGENT_TOOL,
    FRAME_SUBAGENT_COMPLETE,
})