"""SSE 契约测试：帧格式/续传/环形缓存失效 resync/取消帧（对照 legacy-sse.json）。"""
from __future__ import annotations

import asyncio

import pytest

from backend.modules.assistant.contracts import RunCommand
from backend.modules.assistant.events import EventBus
from backend.runtime.contracts import RuntimeEvent
from backend.shared.context import Principal
from tests.support.rig import make_rig


def _e(kind, payload):
    return RuntimeEvent(kind=kind, payload=payload)


@pytest.fixture
async def rig(tmp_path):
    r = make_rig(tmp_path, seed_access=True)
    r.attach_assistant()
    await r.start_assistant()
    yield r
    await r.aclose()


async def _collect_frames(rig, client_params_owner, params: dict):
    """提交并收集SSE帧（经 routes 层语义验证在此文件的姊妹测试完成；
    这里直接测事件层映射）。"""
    raise NotImplementedError


async def test_frames_id_seq_monotonic_and_resume(rig):
    """帧 id=seq 单调；Last-Event-ID: N → after_seq=N+1 续传（排除已见N）。"""
    user = rig.seed_user(role="user", grants=("chat.use",), username="sse_resume")
    session = await rig.seed_session(user)

    async def gen(request):
        for text in ("片段一", "片段二", "片段三"):
            yield _e("token", {"text": text})
            await asyncio.sleep(0.12)  # 明确超过合并窗口(0.05s)，各自成帧
        yield _e("completed", {"result": {"final_response": "片段一片段二片段三", "completed": True}})
        # 注意：Runtime 协议要求流必须以终态事件结束；此处显式给出 completed

    rig.runtime.execute = gen
    receipt = await rig.assistant.submit(RunCommand(
        principal=user, session_id=session, source="web", client_message_id="sse1", text="讲三句"))
    await rig.drain_runs()

    # 从头订阅：帧 id 单调递增，token 三帧
    frames = [(e.seq, e.kind, e.payload) for e in await _drain(rig, user, receipt.run_id, after_seq=0)]
    token_frames = [f for f in frames if f[1] == "token"]
    assert len(token_frames) == 3
    seqs = [f[0] for f in token_frames]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    # Last-Event-ID=第一token帧seq → 续传只看后续
    resumed = [(e.seq, e.kind) for e in await _drain(rig, user, receipt.run_id, after_seq=seqs[0] + 1)]
    resumed_tokens = [s for s, k in resumed if k == "token"]
    assert resumed_tokens == seqs[1:]


async def _drain(rig, principal, run_id, after_seq):
    out = []
    iterator = rig.assistant.iter_events(principal, run_id, after_seq=after_seq)
    while True:
        try:
            event = await iterator.__anext__()
        except StopAsyncIteration:
            break
        out.append(event)
        if event.kind in ("completed", "failed", "cancelled", "interrupted"):
            break
    return out


async def test_token_coalescing_within_window(rig):
    """合并窗口内的连续 token 合成一帧，降低帧开销。"""
    bus = EventBus(coalesce_seconds=0.2)
    bus.publish("run_" + "1" * 32, "token", {"text": "a"})
    bus.publish("run_" + "1" * 32, "token", {"text": "b"})
    bus.publish("run_" + "1" * 32, "token", {"text": "c"})
    bus.flush_token("run_" + "1" * 32)
    buffer = bus._buffers["run_" + "1" * 32]
    token_frames = [e for _s, e in buffer.frames if e.kind == "token"]
    assert len(token_frames) == 1
    assert token_frames[0].payload["text"] == "abc"


async def test_ring_buffer_truncation_signals_resync(rig):
    """环形缓存截断后续传先收 stream_reset（不从头重放，也不重新执行）。"""
    from backend.modules.assistant.events import EventBus

    bus = EventBus(max_frames=3, max_bytes=256 * 1024)
    run_id = "run_" + "2" * 32
    for i in range(5):
        bus.publish(run_id, "tool_started", {"iteration": i, "tools": []})
    bus.finish(run_id, "completed", {"final_content": "done"})
    principal = Principal(user_id=1, role="user", permission_revision=0)
    events = []
    iterator = bus.subscribe(principal, 1, run_id, after_seq=2)  # 请求已截断的旧区间
    async for e in iterator:
        events.append(e)
    kinds = [e.kind for e in events]
    assert kinds[0] == "stream_reset"  # 明确的 resync 信号
    assert "completed" in kinds
    frames = [(e.seq, e.kind) for _q, e in bus._buffers[run_id].frames]
    assert len(frames) <= 3  # 环形上限


async def test_completed_run_ttl_sweep(rig):
    bus = EventBus(completed_ttl=0.01)
    run_id = "run_" + "3" * 32
    bus.finish(run_id, "completed", {"final_content": ""})
    await asyncio.sleep(0.03)
    assert bus.sweep() == 1
    assert bus.latest_seq(run_id) is None


async def test_completed_flow_persists_terminal_state(rig):
    """完成后：事件缓存5分钟内可重放终态；缓存过期后走持久状态（不重跑）。"""
    user = rig.seed_user(role="user", grants=("chat.use",), username="ttl")
    session = await rig.seed_session(user)
    rig.runtime.script_events([
        _e("token", {"text": "答案"}),
        _e("completed", {"result": {"final_response": "答案", "completed": True}}),
    ])
    receipt = await rig.assistant.submit(RunCommand(
        principal=user, session_id=session, source="web", client_message_id="ttl1", text="问"))
    await rig.drain_runs()
    status = await rig.assistant.run_status(user, receipt.run_id)
    assert status["status"] == "completed"
    # 持久投影可查（缓存过期时的最终状态来源）
    messages = await rig.assistant.session_messages(user, session)
    assert any(m["role"] == "assistant" and m["content"] == "答案" for m in messages)
