"""多 Agent 委派桥接 —— 真·集成测试

与 test_delegation_integration.py 的区别：这里**真的导入 delegate_tool**，
用假的 AIAgent 跑通 `_build_child_agent`，因此覆盖的是生产路径本身，而不是
"把生产逻辑在测试里再抄一遍"（后者永远发现不了字段名/门控条件写错这种问题）。

覆盖：
  A. 富化回调真的被调用，产出真的进了子 Agent 的系统提示
  B. 子 Agent 的 tool_progress_callback（Hermes 自己构造的转发器）真的把
     subagent.* 事件送到宿主的回调 → SSE 帧 + 留痕
  C. 没有展示通道时回调为 None（等于原生 Hermes 行为）
  D. 后台完成事件的所有权判定 / 上限 / 认领
  E. 结果回流：注入一轮、合并产出、确认投递；失败则放回队列
  F. 取消传导、同批重复检测、留痕熔断快速失败

运行：
  pytest tests/test_delegation_bridge.py -v
"""
import asyncio
import contextvars
import json
import queue
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# delegate_tool 依赖 Hermes 内部包路径（toolsets/tools/agent...）
_HERMES_ROOT = str(ROOT / "backend" / "hermes")
if _HERMES_ROOT not in sys.path:
    sys.path.insert(0, _HERMES_ROOT)

_IMPORT_ERROR = None
dt = None
try:
    from tools import delegate_tool as dt  # noqa: E402
except Exception as _e:  # pragma: no cover - 环境缺依赖时整体跳过
    _IMPORT_ERROR = _e

requires_delegate_tool = pytest.mark.skipif(
    dt is None, reason=f"无法导入 delegate_tool: {_IMPORT_ERROR}"
)


# ──────────────────────────────────────────────────────────────
# 测试替身
# ──────────────────────────────────────────────────────────────


class FakeChildAgent:
    """替掉 run_agent.AIAgent：只保留 delegate_tool 构造后会用到的属性。"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.session_id = kwargs.get("session_id") or "child-sid"
        self.model = kwargs.get("model") or "child-model"
        self.valid_tool_names = []
        self._delegate_depth = 1
        self._active_children = []

    def close(self):
        pass


class FakeParentAgent:
    """父 Agent 替身：字段与 delegate_tool 读取的一致。"""

    def __init__(self, **overrides):
        self.model = "parent-model"
        self.provider = "custom"
        self.base_url = "http://localhost:9/v1"
        self.api_key = "k"
        self.session_id = "parent-sid"
        self._delegate_depth = 0
        self.enabled_toolsets = ["web"]
        self.disabled_toolsets = []
        self.valid_tool_names = []
        self._client_kwargs = {}
        self.tool_progress_callback = None
        self.__dict__.update(overrides)


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch):
    """这些用例不该依赖 MySQL。

    连接池在 DB 不可用时单次要重试约 15 秒，会把测试拖到分钟级；这里让连接获取
    立刻失败，既保持 store 的降级路径被真实执行，又让熔断马上生效（后续写入直接跳过）。
    """
    import backend.db.schema as schema
    from backend.service.delegation import store as _store_mod

    def _fail():
        raise RuntimeError("no db in tests")

    _store_mod.reset_breaker()
    monkeypatch.setattr(schema, "get_conn", _fail)
    yield
    _store_mod.reset_breaker()


@pytest.fixture
def fake_aiagent(monkeypatch):
    """把 run_agent.AIAgent 换成 FakeChildAgent（delegate_tool 在函数内 import 它）。"""
    import run_agent

    monkeypatch.setattr(run_agent, "AIAgent", FakeChildAgent, raising=False)
    return FakeChildAgent


@pytest.fixture
def clean_enricher():
    """保证每个用例后卸载富化回调（模块级全局，会串场）。"""
    yield
    if dt is not None:
        dt.set_context_enricher(None)


def _frame_types(q):
    out = []
    while not q.empty():
        raw = q.get_nowait()
        assert raw.startswith("data: "), f"帧格式不对: {raw!r}"
        out.append(json.loads(raw[6:].strip()))
    return out


# ──────────────────────────────────────────────────────────────
# A/B/C：真实 _build_child_agent 路径
# ──────────────────────────────────────────────────────────────


@requires_delegate_tool
class TestRealChildAgentPath:
    def _build(self, monkeypatch, parent, context="ctx-1", goal="查物流"):
        import backend.hermes_adapter as ha

        q = queue.Queue()
        cb = ha.build_subagent_progress_callback(thread_queue=q, thread_id="t-1", user_id=7)
        parent.tool_progress_callback = cb
        child = dt._build_child_agent(
            task_index=0,
            goal=goal,
            context=context,
            toolsets=None,
            model=None,
            max_iterations=5,
            task_count=1,
            parent_agent=parent,
            role="leaf",
        )
        return child, q

    def test_enricher_output_reaches_child_system_prompt(
        self, fake_aiagent, clean_enricher, monkeypatch
    ):
        """富化的产物必须真的出现在子 Agent 的系统提示里（而不是只被调用过）"""
        dt.set_context_enricher(lambda ctx, goal: f"ENRICHED<{ctx}|{goal}>")
        child, _ = self._build(monkeypatch, FakeParentAgent())
        system_prompt = child.kwargs.get("ephemeral_system_prompt") or ""
        assert "ENRICHED<ctx-1|查物流>" in system_prompt
        assert "CONTEXT:" in system_prompt

    def test_enricher_exception_degrades_to_raw_context(
        self, fake_aiagent, clean_enricher, monkeypatch
    ):
        def _boom(ctx, goal):
            raise RuntimeError("enricher down")

        dt.set_context_enricher(_boom)
        child, _ = self._build(monkeypatch, FakeParentAgent(), context="原始备注")
        system_prompt = child.kwargs.get("ephemeral_system_prompt") or ""
        assert "原始备注" in system_prompt
        assert "ENRICHED" not in system_prompt

    def test_hermes_relays_subagent_events_to_host_callback(
        self, fake_aiagent, clean_enricher, monkeypatch
    ):
        """核心回归：宿主挂 tool_progress_callback 后，Hermes 会把子 Agent 事件转发过来。

        这条链路替代了此前"改 delegate_tool 源码埋 4 处 _push_sse"的做法。
        """
        child, q = self._build(monkeypatch, FakeParentAgent())
        relay = child.kwargs.get("tool_progress_callback")
        assert relay is not None, "父 Agent 挂了回调，子 Agent 的转发器不该是 None"

        # Hermes 侧真实会发的事件序列
        relay("subagent.start", preview="查物流")
        relay("tool.started", "web_search", "物流单号 A123")
        relay("subagent.text", preview="正在查询")
        relay("subagent.complete", preview="已查到", status="completed",
              duration_seconds=1.5, tokens={"input": 10, "output": 20}, api_calls=2)

        frames = _frame_types(q)
        assert [f["type"] for f in frames] == [
            "subagent_start", "subagent_tool", "subagent_token", "subagent_complete",
        ]
        start, tool, token, done = frames
        # 身份字段必须带全（前端按 subagent_id 分组、按 depth 缩进）
        assert start["subagent_id"].startswith("sa-0-")
        assert start["goal"] == "查物流"
        assert start["depth"] == 0
        # model 是"有效模型"：未指定 delegation.model 时继承父 Agent 的模型
        assert start["model"] == child.kwargs.get("model")
        assert tool["tool_name"] == "web_search"
        assert tool["preview"] == "物流单号 A123"
        assert token["content"] == "正在查询"
        assert done["status"] == "completed"
        assert done["summary"] == "已查到"
        assert done["tokens"] == {"input": 10, "output": 20}
        assert done["api_calls"] == 2

    def test_host_callback_records_留痕(self, fake_aiagent, clean_enricher, monkeypatch):
        """每个事件都要落留痕（异步提交，这里替换成同步执行以便断言）"""
        import backend.hermes_adapter as ha

        calls = []
        monkeypatch.setattr(ha, "_submit_store_write", lambda name, fn: calls.append((name, fn)))

        child, q = self._build(monkeypatch, FakeParentAgent())
        relay = child.kwargs.get("tool_progress_callback")
        relay("subagent.start", preview="查物流")
        relay("tool.started", "web_search", "x")
        relay("subagent.complete", preview="ok", status="completed",
              tokens={"input": 1, "output": 2}, api_calls=1)

        # 工具调用不逐次写库（每 10 次才落一次），start/complete 必写
        assert [name for name, _ in calls] == ["started", "completed"]
        # 提交的是 partial，参数里必须带 subagent_id / 父子会话
        started_kwargs = calls[0][1].keywords
        assert started_kwargs["subagent_id"].startswith("sa-0-")
        assert started_kwargs["thread_id"] == "t-1"
        assert started_kwargs["user_id"] == 7
        assert started_kwargs["child_session_id"] == "child-sid"
        # complete 事件里的 tool_count 是权威值
        assert calls[1][1].keywords["tool_count"] == 1

    def test_tool_count_flushed_in_batches(self, fake_aiagent, clean_enricher, monkeypatch):
        """工具调用每 10 次落一次库（避免每次写库灌满共享线程池）"""
        import backend.hermes_adapter as ha

        calls = []
        monkeypatch.setattr(ha, "_submit_store_write", lambda name, fn: calls.append((name, fn)))

        child, _ = self._build(monkeypatch, FakeParentAgent())
        relay = child.kwargs.get("tool_progress_callback")
        relay("subagent.start", preview="g")
        for i in range(25):
            relay("tool.started", "web_search", f"q{i}")
        assert [name for name, _ in calls] == ["started", "tool_count", "tool_count"]
        assert calls[1][1].args[1] == 10
        assert calls[2][1].args[1] == 20

    def test_non_subagent_events_are_ignored(self, fake_aiagent, clean_enricher, monkeypatch):
        """父 Agent 自身的工具进度走的是同一个 tool_progress_callback 通道，必须被过滤掉"""
        import backend.hermes_adapter as ha

        q = queue.Queue()
        host_cb = ha.build_subagent_progress_callback(thread_queue=q, thread_id="t-1", user_id=7)
        host_cb("tool.started", "terminal", "ls")          # 父自己的工具
        host_cb("tool.completed", "terminal", "done")
        host_cb("_thinking", "想一想")
        host_cb("reasoning.available", "_thinking", "想")
        assert _frame_types(q) == []

        # 而子 Agent 转发器送来的事件必须被接住（tool.started 经中转后叫 subagent.tool）
        child, q2 = self._build(monkeypatch, FakeParentAgent())
        relay = child.kwargs.get("tool_progress_callback")
        relay("tool.started", "web_search", "查一下")
        relay("_thinking", "子 Agent 的思考")   # 映射为 subagent.thinking，无对应帧 → 忽略
        frames = _frame_types(q2)
        assert [f["type"] for f in frames] == ["subagent_tool"]

    def test_callback_exceptions_never_escape(self, fake_aiagent, clean_enricher, monkeypatch):
        """回调跑在 Agent 主循环里：任何异常都必须被吞掉"""
        import backend.hermes_adapter as ha

        child, q = self._build(monkeypatch, FakeParentAgent())
        relay = child.kwargs.get("tool_progress_callback")
        monkeypatch.setattr(ha, "push_frame", MagicMock(side_effect=RuntimeError("boom")), raising=False)
        # push_frame 是从 sse_bridge 内部 import 的，改成让 store 炸更直接
        monkeypatch.setattr(ha, "_submit_store_write", MagicMock(side_effect=RuntimeError("boom")))
        relay("subagent.start", preview="x")  # 不应抛
        relay("tool.started", "t", "p")
        relay("subagent.complete", preview="s")

    def test_no_display_channel_keeps_upstream_behaviour(self, fake_aiagent, monkeypatch):
        """父 Agent 既无 spinner 也无回调时，Hermes 不构造转发器（= 原生行为）"""
        child, q = self._build(monkeypatch, FakeParentAgent())
        assert child.kwargs.get("tool_progress_callback") is not None  # 有回调时构造

        parent = FakeParentAgent(tool_progress_callback=None)
        child2 = dt._build_child_agent(
            task_index=0, goal="g", context=None, toolsets=None, model=None,
            max_iterations=5, task_count=1, parent_agent=parent, role="leaf",
        )
        assert child2.kwargs.get("tool_progress_callback") is None


# ──────────────────────────────────────────────────────────────
# D：后台完成事件的所有权判定
# ──────────────────────────────────────────────────────────────


class TestDrainOwnedEvents:
    @pytest.fixture
    def fake_registry(self, monkeypatch):
        import tools.process_registry as pr

        reg = types.SimpleNamespace(completion_queue=queue.Queue())
        monkeypatch.setattr(pr, "process_registry", reg, raising=False)
        return reg

    def test_only_owned_events_are_consumed(self, fake_registry, monkeypatch):
        import backend.hermes_adapter as ha
        import tools.async_delegation as ad

        monkeypatch.setattr(ad, "claim_event_delivery", lambda evt, consumer: "claim-1")
        mine = {"type": "async_delegation", "delegation_id": "d-1", "session_key": "parent-sid",
                "results": [{"task_index": 0, "status": "completed", "summary": "ok"}]}
        others = {"type": "async_delegation", "delegation_id": "d-2", "session_key": "someone-else",
                  "results": []}
        fake_registry.completion_queue.put(mine)
        fake_registry.completion_queue.put(others)

        items = ha.drain_owned_delegation_events({"parent-sid"})
        assert len(items) == 1
        evt, text = items[0]
        assert evt["delegation_id"] == "d-1"
        assert evt["_claim_id"] == "claim-1"
        assert text and "d-1" in text      # 事件被格式化成了可注入文本
        # 别人的事件必须还在队列里（多用户同进程的硬要求）
        assert fake_registry.completion_queue.qsize() == 1
        left = fake_registry.completion_queue.get_nowait()
        assert left["delegation_id"] == "d-2"

    def test_real_claim_function_signature(self, fake_registry):
        """回归：必须调用 Hermes 真实存在的 claim_event_delivery(evt, consumer)。

        历史 bug：这里曾误用同名的两参 DB 函数 claim_completion_delivery(delegation_id,
        claim_id)，调用直接抛 TypeError，被 except 吞成 None → 事件被静默丢弃、
        结果永远不回流。这个用例刻意**不 monkeypatch**，直接用真实现（SQLite 支撑），
        所以函数名/签名写错会立刻失败。
        """
        import backend.hermes_adapter as ha

        evt = {
            "type": "async_delegation",
            "delegation_id": "d-not-in-wal",     # 库里没有该行 → 认领按"legacy 事件"放行
            "session_key": "parent-sid",
            "results": [{"task_index": 0, "status": "completed", "summary": "真认领"}],
        }
        fake_registry.completion_queue.put(evt)
        items = ha.drain_owned_delegation_events({"parent-sid"})
        assert len(items) == 1, "真实 claim_event_delivery 未被正确调用（函数名/签名不符）"
        got, text = items[0]
        assert got["_claim_id"]                       # 拿到了认领令牌
        assert "真认领" in (text or "")
        assert fake_registry.completion_queue.qsize() == 0

    def test_claim_failure_requeues_instead_of_dropping(self, fake_registry, monkeypatch):
        """认领失败（别人正在投递 / DB 抖动）时放回队列，绝不静默丢弃"""
        import backend.hermes_adapter as ha
        import tools.async_delegation as ad

        monkeypatch.setattr(ad, "claim_event_delivery", lambda evt, consumer: None)
        fake_registry.completion_queue.put({
            "type": "async_delegation", "delegation_id": "d-busy", "session_key": "parent-sid",
            "results": [],
        })
        assert ha.drain_owned_delegation_events({"parent-sid"}) == []
        assert fake_registry.completion_queue.qsize() == 1, "认领失败的事件必须放回队列"
        assert fake_registry.completion_queue.get_nowait()["delegation_id"] == "d-busy"

    def test_non_delegation_owned_event_needs_no_claim(self, fake_registry):
        """非委派类事件（如后台进程完成）不需要认领，直接投递"""
        import backend.hermes_adapter as ha

        fake_registry.completion_queue.put({
            "type": "completion", "session_id": "proc-1", "session_key": "parent-sid",
            "command": "echo hi", "exit_code": 0, "output": "hi",
        })
        items = ha.drain_owned_delegation_events({"parent-sid"})
        assert len(items) == 1
        assert "echo hi" in (items[0][1] or "")

    def test_parent_and_origin_session_also_match(self, fake_registry, monkeypatch):
        import backend.hermes_adapter as ha
        import tools.async_delegation as ad

        monkeypatch.setattr(ad, "claim_event_delivery", lambda evt, consumer: "c")
        fake_registry.completion_queue.put(
            {"type": "async_delegation", "delegation_id": "d-3", "parent_session_id": "parent-sid",
             "results": []}
        )
        fake_registry.completion_queue.put(
            {"type": "async_delegation", "delegation_id": "d-4", "origin_session_id": "parent-sid",
             "results": []}
        )
        assert len(ha.drain_owned_delegation_events({"parent-sid"})) == 2

    def test_max_events_requeues_overflow(self, fake_registry, monkeypatch):
        import backend.hermes_adapter as ha
        import tools.async_delegation as ad

        monkeypatch.setattr(ad, "claim_event_delivery", lambda evt, consumer: "c")
        for i in range(4):
            fake_registry.completion_queue.put(
                {"type": "async_delegation", "delegation_id": f"d-{i}", "session_key": "parent-sid",
                 "results": []}
            )
        items = ha.drain_owned_delegation_events({"parent-sid"}, max_events=2)
        assert len(items) == 2
        assert fake_registry.completion_queue.qsize() == 2  # 超出的放回

    def test_empty_session_ids_is_noop(self, fake_registry):
        import backend.hermes_adapter as ha

        fake_registry.completion_queue.put(
            {"type": "async_delegation", "delegation_id": "d-y", "results": []}
        )
        assert ha.drain_owned_delegation_events(set()) == []
        assert fake_registry.completion_queue.qsize() == 1


# ──────────────────────────────────────────────────────────────
# E：结果回流（注入一轮 + 合并 + 确认投递 + 失败重排）
# ──────────────────────────────────────────────────────────────


class _FakeRuntime:
    """HermesRuntime 的最小替身（只带 _inject_delegation_followups 用到的字段）。"""

    def __init__(self, session_id="parent-sid"):
        self.thread_id = "t-1"
        self.user_id = 7
        self.system_prompt = "SYS"
        self._agent = types.SimpleNamespace(session_id=session_id)
        self._last_session_id = None

    def _subagent_owner_session_ids(self):
        return {"t-1", self._agent.session_id}

    async def _drain_with_grace(self, session_ids, *, grace_s: float = 5.0):
        """替身直接 drain（不测宽限期，避免测试里多等 5s）。"""
        import backend.hermes_adapter as ha

        return ha.drain_owned_delegation_events(
            self._subagent_owner_session_ids() | set(session_ids or ())
        )

    def _live_subagent_ids(self):
        """替身默认"无法裁剪"（返回 None）→ 等待逻辑只看传入的集合。

        需要测裁剪行为的用例自行覆盖这个属性/方法。
        """
        return None


def _run(coro):
    return asyncio.run(coro)


class TestFollowupInjection:
    @pytest.fixture
    def registry(self, monkeypatch):
        import tools.process_registry as pr

        reg = types.SimpleNamespace(completion_queue=queue.Queue())
        monkeypatch.setattr(pr, "process_registry", reg, raising=False)
        # 注意函数名：模块级认领是 claim_event_delivery(evt, consumer)
        monkeypatch.setattr(
            "tools.async_delegation.claim_event_delivery", lambda evt, consumer: "claim"
        )
        monkeypatch.setattr(
            "tools.async_delegation.mark_completion_delivered", lambda did: True
        )
        return reg

    def _invoke(self, runtime, result, run_conversation, session_ids=None):
        import backend.hermes_adapter as ha

        async def _go():
            loop = asyncio.get_running_loop()
            ctx = contextvars.copy_context()
            await ha.HermesRuntime._inject_delegation_followups(
                runtime,
                loop=loop,
                ctx=ctx,
                run_conversation=run_conversation,
                result=result,
                session_ids=session_ids or {"parent-sid"},
            )

        _run(_go())

    def test_no_events_is_noop(self, registry, monkeypatch):
        import backend.hermes_adapter as ha

        monkeypatch.setattr(ha, "_persist_drained_event", MagicMock())
        called = []
        self._invoke(_FakeRuntime(), {"final_response": "x"}, lambda *a, **k: called.append(1))
        assert called == []

    def test_event_is_injected_and_merged(self, registry, monkeypatch):
        import backend.hermes_adapter as ha

        persisted = []
        monkeypatch.setattr(
            ha, "_persist_drained_event",
            lambda evt, thread_id=None, user_id=0, parent_session_id=None: persisted.append(evt),
        )
        registry.completion_queue.put({
            "type": "async_delegation", "delegation_id": "d-9", "session_key": "parent-sid",
            "goal": "查物流", "goals": ["查物流"],
            "results": [{"task_index": 0, "status": "completed", "summary": "顺丰已签收",
                         "api_calls": 3, "duration_seconds": 2.0,
                         "tokens": {"input": 5, "output": 6}}],
        })

        seen = {}

        def _fake_run_conversation(agent, user_message=None, **kw):
            seen["injected"] = user_message
            return {"final_response": "子任务结果：顺丰已签收", "api_calls": 3}

        result = {"final_response": "已派发子任务", "api_calls": 1}
        self._invoke(_FakeRuntime(), result, _fake_run_conversation)

        # ① 事件被注入成新的一轮，文本来自 Hermes 的官方格式化
        assert "d-9" in seen["injected"]
        assert "顺丰已签收" in seen["injected"]
        # ② 产出被合并进最终答案（前端/落库都用 final_response）
        assert result["final_response"] == "已派发子任务\n\n子任务结果：顺丰已签收"
        assert result["api_calls"] == 4
        # ③ 留痕已写
        assert [e["delegation_id"] for e in persisted] == ["d-9"]
        # ④ 队列已清空
        assert registry.completion_queue.qsize() == 0

    def test_injection_failure_requeues_event(self, registry, monkeypatch):
        import backend.hermes_adapter as ha

        monkeypatch.setattr(ha, "_persist_drained_event", MagicMock())
        registry.completion_queue.put({
            "type": "async_delegation", "delegation_id": "d-err", "session_key": "parent-sid",
            "results": [{"task_index": 0, "status": "completed", "summary": "s"}],
        })

        def _boom(*a, **kw):
            raise RuntimeError("LLM down")

        result = {"final_response": "x"}
        self._invoke(_FakeRuntime(), result, _boom)

        assert result["final_response"] == "x"                     # 本轮回答没被破坏
        assert registry.completion_queue.qsize() == 1              # 放回，等待重试
        assert registry.completion_queue.get_nowait()["delegation_id"] == "d-err"

    def test_disabled_by_env(self, registry, monkeypatch):
        import backend.hermes_adapter as ha

        monkeypatch.setenv("AGENTFORGE_DELEGATION_FOLLOWUP", "0")
        monkeypatch.setattr(ha, "_persist_drained_event", MagicMock())
        registry.completion_queue.put({
            "type": "async_delegation", "delegation_id": "d-off", "session_key": "parent-sid",
            "results": [],
        })
        self._invoke(_FakeRuntime(), {"final_response": "x"}, lambda *a, **k: {"final_response": "y"})
        assert registry.completion_queue.qsize() == 1  # 未消费


# ──────────────────────────────────────────────────────────────
# F：取消传导 / 重复检测 / 留痕熔断
# ──────────────────────────────────────────────────────────────


class TestCancelPropagation:
    def test_interrupts_tracked_subagents(self, monkeypatch):
        import backend.hermes_adapter as ha
        import tools.delegate_tool as _dt

        hit = []
        monkeypatch.setattr(_dt, "interrupt_subagent", lambda sid: hit.append(sid) or True)

        runtime = _FakeRuntime()
        runtime._active_subagent_ids = {"sa-0-aaa", "sa-1-bbb"}
        n = ha.HermesRuntime.interrupt_active_subagents(runtime)
        assert n == 2
        assert set(hit) == {"sa-0-aaa", "sa-1-bbb"}
        assert runtime._active_subagent_ids == set()  # 中断后清理

    def test_no_subagents_is_noop(self, monkeypatch):
        import backend.hermes_adapter as ha

        runtime = _FakeRuntime()
        runtime._active_subagent_ids = set()
        assert ha.HermesRuntime.interrupt_active_subagents(runtime) == 0


class TestOverlapDetection:
    def test_detects_near_duplicate_goals(self):
        import backend.hermes_adapter as ha

        goals = ["查询订单A123的物流状态", "查询订单A123的物流进度", "分析本季度销售报表"]
        hits = ha.find_overlapping_goals(goals)
        assert hits, "高度相似的子任务应被判定为重叠"
        assert hits[0][0] == 0 and hits[0][1] == 1

    def test_distinct_goals_pass(self):
        import backend.hermes_adapter as ha

        assert ha.find_overlapping_goals(["写周报", "抓取竞品价格", "修复登录超时"]) == []

    def test_single_goal_and_empty(self):
        import backend.hermes_adapter as ha

        assert ha.find_overlapping_goals([]) == []
        assert ha.find_overlapping_goals(["只有一个"]) == []


class TestAwaitBackgroundSubagents:
    """父轮内等待后台子 Agent（修复"必须刷新浏览器才看到状态更新"）。

    原理：SSE 消费循环以父轮结束为退出条件；不等就关流，子 Agent 之后的实时事件
    推进无人读取的队列，前端只能靠刷新 + DB 回填看到状态。

    T3.2 后等待只看**本轮**的 turn_ids（不再看跨轮累积的 _active_subagent_ids）；
    T3.3 后"本轮派发过批次"也能触发等待（兜住 subagent.start 事件延迟的竞态）。
    """

    def _run(self, runtime, turn_ids=None, dispatch=None):
        import backend.hermes_adapter as ha

        return _run(
            ha.HermesRuntime._await_background_subagents(runtime, turn_ids, dispatch)
        )

    def test_no_active_subagents_returns_immediately(self, monkeypatch):
        monkeypatch.setenv("AGENTFORGE_DELEGATION_WAIT_SECONDS", "180")
        runtime = _FakeRuntime()
        runtime._active_subagent_ids = set()
        assert self._run(runtime, set()) == 0

    def test_wait_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("AGENTFORGE_DELEGATION_WAIT_SECONDS", "0")
        runtime = _FakeRuntime()
        runtime._active_subagent_ids = {"sa-0-a"}
        assert self._run(runtime, {"sa-0-a"}) == 1  # 不等待，立即返回仍在跑的数量

    def test_waits_until_child_completes(self, monkeypatch):
        """子 Agent 的 complete 事件清空集合后，等待应立即结束"""
        monkeypatch.setenv("AGENTFORGE_DELEGATION_WAIT_SECONDS", "10")
        runtime = _FakeRuntime()
        turn_ids = {"sa-0-a", "sa-1-b"}
        runtime._active_subagent_ids = turn_ids

        import threading
        import time as _t

        def _finish():
            _t.sleep(0.6)
            turn_ids.clear()

        threading.Thread(target=_finish, daemon=True).start()
        started = _t.monotonic()
        assert self._run(runtime, turn_ids) == 0
        assert _t.monotonic() - started < 5  # 是"提前结束"而不是等满 10s

    def test_interrupt_stops_waiting(self, monkeypatch):
        """用户点停止后不能傻等：立即退出等待"""
        monkeypatch.setenv("AGENTFORGE_DELEGATION_WAIT_SECONDS", "30")
        runtime = _FakeRuntime()
        runtime._active_subagent_ids = {"sa-0-a"}
        runtime._agent._interrupt_requested = True

        import time as _t

        started = _t.monotonic()
        assert self._run(runtime, {"sa-0-a"}) == 1  # 提前退出，仍有 1 个在跑
        assert _t.monotonic() - started < 3

    def test_timeout_is_bounded(self, monkeypatch):
        monkeypatch.setenv("AGENTFORGE_DELEGATION_WAIT_SECONDS", "1")
        runtime = _FakeRuntime()
        runtime._active_subagent_ids = {"sa-0-a"}

        import time as _t

        started = _t.monotonic()
        assert self._run(runtime, {"sa-0-a"}) == 1
        elapsed = _t.monotonic() - started
        assert 1 <= elapsed < 4  # 有界，不会无限等

    # ── T3.2：轮次作用域 ──

    def test_stale_id_from_previous_turn_does_not_block(self, monkeypatch):
        """上一轮超时/事件丢失留下的 id 不能拖住本轮（改动前每轮都卡满等待上限）"""
        monkeypatch.setenv("AGENTFORGE_DELEGATION_WAIT_SECONDS", "30")
        runtime = _FakeRuntime()
        # 上一轮的残留（不属于本轮）
        runtime._active_subagent_ids = {"sa-stale-from-last-turn"}

        import time as _t

        started = _t.monotonic()
        # 本轮没有任何 id、也没派发过 → 立即返回，不等 30s
        assert self._run(runtime, set()) == 0
        assert _t.monotonic() - started < 2

    def test_hermes_authoritative_pruning(self, monkeypatch):
        """Hermes 侧已不在跑 → 从等待集合中剔除（防 complete 事件丢失导致永久等待）"""
        monkeypatch.setenv("AGENTFORGE_DELEGATION_WAIT_SECONDS", "30")
        runtime = _FakeRuntime()
        runtime._active_subagent_ids = {"sa-gone", "sa-alive"}

        # Hermes 只报告 sa-alive 还在跑
        runtime._live_subagent_ids = lambda: {"sa-alive"}

        import threading
        import time as _t

        def _finish():
            _t.sleep(0.6)
            runtime._live_subagent_ids = lambda: set()

        threading.Thread(target=_finish, daemon=True).start()

        ids = {"sa-gone", "sa-alive"}
        started = _t.monotonic()
        assert self._run(runtime, ids) == 0
        assert _t.monotonic() - started < 5
        assert "sa-gone" not in ids, "已不在 Hermes 活跃集合里的 id 应被剔除"
        assert "sa-gone" not in runtime._active_subagent_ids

    # ── T3.3：派发信号竞态 ──

    def test_dispatched_batch_waits_for_delayed_start(self, monkeypatch):
        """派发了但 subagent.start 延迟 2 秒 → 必须等到完成事件，而不是立即返回"""
        monkeypatch.setenv("AGENTFORGE_DELEGATION_WAIT_SECONDS", "30")
        runtime = _FakeRuntime()
        runtime._active_subagent_ids = set()

        import threading
        import time as _t

        turn_ids: set = set()
        signal = {"dispatched": 1}
        # 模拟：start 事件 2 秒后才到（daemon 池饱和、worker 未及时启动）
        runtime._live_subagent_ids = lambda: set(turn_ids)

        def _delayed_start_then_complete():
            _t.sleep(2.0)
            turn_ids.add("sa-late")                      # start 事件终于到了
            _t.sleep(0.5)
            turn_ids.clear()                             # complete

        threading.Thread(target=_delayed_start_then_complete, daemon=True).start()

        started = _t.monotonic()
        result = self._run(runtime, turn_ids, signal)
        elapsed = _t.monotonic() - started

        assert result == 0
        # 关键：不是立即返回（改动前集合为空 → 立即返回 ~0s）
        assert elapsed >= 2.0, f"应等到延迟的 start + 完成事件（实际 {elapsed:.2f}s）"
        assert elapsed < 10

    def test_dispatched_but_nothing_running_exits_after_grace(self, monkeypatch):
        """派发过但确实没有子 Agent 在跑 → 宽限期后退出，而不是等满上限"""
        monkeypatch.setenv("AGENTFORGE_DELEGATION_WAIT_SECONDS", "30")
        runtime = _FakeRuntime()
        runtime._active_subagent_ids = set()
        runtime._live_subagent_ids = lambda: set()   # 没有在跑的

        import backend.hermes_adapter as ha
        import time as _t

        started = _t.monotonic()
        result = self._run(runtime, set(), {"dispatched": 1})
        elapsed = _t.monotonic() - started

        assert result == 0
        assert ha._DELEGATION_START_GRACE_S <= elapsed < ha._DELEGATION_START_GRACE_S + 3


class TestStoreResilience:
    def test_write_failure_is_swallowed_and_breaks_circuit(self, monkeypatch):
        """DB 不可用时：不抛异常，且熔断后立刻返回（不再等连接池重试）"""
        from backend.service.delegation import store

        store.reset_breaker()
        calls = {"n": 0}

        def _boom():
            calls["n"] += 1
            raise RuntimeError("db down")

        # 替换最底层的连接获取（store._conn 是带熔断的包装，不能直接换掉）
        import backend.db.schema as schema

        monkeypatch.setattr(schema, "get_conn", _boom)
        store.record_subagent_started(subagent_id="sa-0-zzz", goal="g")   # 不抛
        assert calls["n"] == 1
        store.record_subagent_tool("sa-0-zzz")                            # 熔断期内不再尝试
        store.record_subagent_completed(subagent_id="sa-0-zzz")
        assert calls["n"] == 1
        assert store.list_by_thread("t") == []
        store.reset_breaker()

    def test_parse_task_index(self):
        from backend.service.delegation import store

        assert store._parse_task_index("sa-3-ab12cd34") == 3
        assert store._parse_task_index("child-sid") is None
        assert store._parse_task_index(None) is None


class TestSseBridgeFrames:
    def test_build_frame_roundtrip(self):
        from backend.service.delegation.sse_bridge import build_frame, push_frame

        q = queue.Queue()
        assert push_frame(q, "subagent_start", {"subagent_id": "sa-0-1", "goal": "中文 🎉"}) is True
        raw = q.get_nowait()
        assert raw.startswith("data: ") and raw.endswith("\n\n")
        payload = json.loads(raw[6:].strip())
        assert payload["type"] == "subagent_start"
        assert payload["goal"] == "中文 🎉"
        assert build_frame("x", {}) == 'data: {"type": "x"}\n\n'

    def test_push_frame_never_raises(self):
        from backend.service.delegation.sse_bridge import push_frame

        class Broken:
            def put(self, item):
                raise RuntimeError("nope")

        assert push_frame(Broken(), "subagent_start", {}) is False
        assert push_frame(None, "subagent_start", {}) is False
