"""task_state 单元测试

覆盖：
  - backend.context.task_state: TaskStateMaintainer
      * 单例机制
      * GC：字段级淘汰（FIELD_STALE_TURNS）
      * GC：整体重置（STATE_DEAD_TURNS）
      * format_for_injection 输出格式
      * update：LLM 失败降级（保留旧状态）
      * update：空对话跳过
      * update：轮次单调递增保护
      * update：合并 + u 设为 current_turn
      * update：LLM 返回 {} → 整体清空（话题切换）
      * clear：清理指定 thread
      * _parse_json：多种回退策略

运行：
  pytest tests/test_task_state.py -v
"""

import threading
from unittest.mock import patch, MagicMock

import pytest

from backend.context.task_state import (
    FIELD_STALE_TURNS,
    STATE_DEAD_TURNS,
    TaskStateMaintainer,
    get_task_state_maintainer,
)


# ═══════════════════════════════════════════════════════════
# 全局 fixture：禁用持久化，避免测试之间通过 state.db 互相污染
# ═══════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _disable_task_state_persistence():
    """让本模块所有 TaskStateMaintainer 实例跳过 state.db 读写。

    原因：`_ensure_db_init()` 会从 state.db 恢复数据到内存，
    导致上一个测试写入的数据在下一个测试被恢复，破坏隔离性。
    """
    with patch.object(
        TaskStateMaintainer, "_get_db_path", return_value=None
    ):
        yield


# ═══════════════════════════════════════════════════════════
# 常量 + 单例
# ═══════════════════════════════════════════════════════════

class TestTaskStateConfig:
    def test_field_stale_turns_positive(self):
        assert FIELD_STALE_TURNS > 0

    def test_state_dead_turns_positive(self):
        assert STATE_DEAD_TURNS > 0

    def test_state_dead_ge_field_stale(self):
        # 整体重置阈值应该 >= 字段淘汰阈值（否则字段还没被淘汰整体就先重置了）
        assert STATE_DEAD_TURNS >= FIELD_STALE_TURNS

    def test_singleton_returns_same_instance(self):
        m1 = get_task_state_maintainer()
        m2 = get_task_state_maintainer()
        assert m1 is m2

    def test_singleton_thread_safe(self):
        results = []

        def worker():
            results.append(get_task_state_maintainer())

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(m is results[0] for m in results)


# ═══════════════════════════════════════════════════════════
# GC 逻辑（不需要 LLM）
# ═══════════════════════════════════════════════════════════

class TestTaskStateGC:
    def test_field_eviction_after_stale_turns(self):
        """字段 u 过期（current_turn - u > FIELD_STALE_TURNS）→ 删除"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 50,
            "_state_started_turn": 1,
            "recent": {"v": "新", "u": 45},   # 50-45=5 < 20 → 保留
            "stale": {"v": "旧", "u": 10},    # 50-10=40 > 20 → 淘汰
        }
        m._gc_locked("t1", 50)
        assert "recent" in m._states["t1"]
        assert "stale" not in m._states["t1"]

    def test_field_at_exact_boundary_kept(self):
        """current_turn - u == FIELD_STALE_TURNS 应该保留（严格大于才淘汰）"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 30,
            "_state_started_turn": 1,
            "boundary": {"v": "x", "u": 10},  # 30-10=20 == FIELD_STALE_TURNS → 保留
        }
        m._gc_locked("t1", 30)
        assert "boundary" in m._states["t1"]

    def test_field_one_over_boundary_evicted(self):
        """current_turn - u == FIELD_STALE_TURNS + 1 → 淘汰"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 31,
            "_state_started_turn": 1,
            "over": {"v": "x", "u": 10},  # 31-10=21 > 20 → 淘汰
        }
        m._gc_locked("t1", 31)
        assert "over" not in m._states["t1"]

    def test_all_fields_dead_triggers_full_reset(self):
        """所有字段都 > STATE_DEAD_TURNS 没动 → 整体重置"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 100,
            "_state_started_turn": 1,
            "a": {"v": "x", "u": 50},  # 100-50=50 > 30
            "b": {"v": "y", "u": 60},  # 100-60=40 > 30
        }
        m._gc_locked("t1", 100)
        # 只剩元数据
        remaining = {k: v for k, v in m._states["t1"].items() if not k.startswith("_")}
        assert remaining == {}
        # 元数据重置
        assert m._states["t1"]["_state_started_turn"] == 100

    def test_one_field_alive_prevents_full_reset(self):
        """只要还有一个字段活着，整体不重置"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 100,
            "_state_started_turn": 1,
            "alive": {"v": "x", "u": 95},  # 100-95=5 < 30 → 活着
            "dead": {"v": "y", "u": 50},   # 100-50=50 > 30 → 淘汰
        }
        m._gc_locked("t1", 100)
        assert "alive" in m._states["t1"]
        assert "dead" not in m._states["t1"]

    def test_empty_state_resets_metadata(self):
        """没有字段时，_state_started_turn 重置为 current_turn"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 10,
            "_state_started_turn": 1,
        }
        m._gc_locked("t1", 10)
        assert m._states["t1"]["_state_started_turn"] == 10

    def test_metadata_fields_not_evicted(self):
        """'_' 前缀的元数据字段不参与淘汰逻辑"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 1000,  # 1000-1000=0
            "_state_started_turn": 1,
            "_future_meta": {"v": "x", "u": 1},  # 1000-1=999 > 20 但它是元数据
        }
        m._gc_locked("t1", 1000)
        assert "_future_meta" in m._states["t1"]  # 元数据保留


# ═══════════════════════════════════════════════════════════
# format_for_injection
# ═══════════════════════════════════════════════════════════

class TestTaskStateFormat:
    def test_empty_state_returns_empty(self):
        m = TaskStateMaintainer()
        assert m.format_for_injection("nonexist") == ""

    def test_state_no_visible_fields_returns_empty(self):
        m = TaskStateMaintainer()
        m._states["t1"] = {"_current_turn": 5, "_state_started_turn": 1}
        assert m.format_for_injection("t1") == ""

    def test_normal_state_has_task_state_tag(self):
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 5,
            "current_goal": {"v": "处理订单", "u": 5},
        }
        out = m.format_for_injection("t1")
        assert "<task_state>" in out
        assert "</task_state>" in out
        assert "处理订单" in out

    def test_metadata_not_in_output(self):
        """元数据字段（_ 前缀）不应该出现在注入文本里"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 5,
            "_state_started_turn": 1,
            "current_goal": {"v": "任务", "u": 5},
        }
        out = m.format_for_injection("t1")
        assert "_current_turn" not in out
        assert "_state_started_turn" not in out
        assert "任务" in out

    def test_invalid_field_shape_skipped(self):
        """字段格式不对（没有 v 键）应该跳过而不是崩"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 5,
            "bad_field": "not a dict",           # 跳过
            "bad_field_2": {"no_v": "x"},        # 跳过
            "good_field": {"v": "好", "u": 5},  # 保留
        }
        out = m.format_for_injection("t1")
        assert "好" in out
        assert "not a dict" not in out
        assert "no_v" not in out

    def test_cross_session_signals_excluded_from_injection(self):
        """cross_session_signals 不应出现在注入文本里（仅供记忆提取管线消费）"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 5,
            "current_goal": {"v": "处理订单", "u": 5},
            "cross_session_signals": {"v": ["用户偏好 Python", "数据库用 MySQL 8"], "u": 3},
        }
        out = m.format_for_injection("t1")
        assert "处理订单" in out
        assert "cross_session_signals" not in out
        assert "用户偏好 Python" not in out
        assert "MySQL" not in out


# ═══════════════════════════════════════════════════════════
# update 主流程（mock LLM）
# ═══════════════════════════════════════════════════════════

class TestTaskStateUpdate:
    def test_empty_messages_no_llm_call(self):
        """空消息不触发 LLM"""
        m = TaskStateMaintainer()
        with patch.object(m, "_extract_state_update") as mock_llm:
            m.update("t1", "", "", 1)
            mock_llm.assert_not_called()

    def test_turn_backwards_is_raised_not_dropped(self):
        """T3.7：轮次回退**不能丢弃更新**，应抬到单调值后继续处理。

        背景：`current_turn` 来自 `agent._user_turn_count`，agent 重建时会由**压缩后的**
        历史重算 → 比内存里已存的值小。若据此 return，该 thread 的状态会**永久静默冻结**
        （DB/内存里还有值，但再也不会更新）。
        改动前本用例断言"同轮次/倒退都跳过"，正是那个缺陷的行为。
        """
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 10,
            "_state_started_turn": 1,
            "current_goal": {"v": "旧目标", "u": 1},
        }

        with patch.object(
            m, "_extract_state_update",
            return_value={"current_goal": {"v": "新目标"}},
        ) as mock_llm:
            # 同轮次 → 抬到 11 后继续处理（改动前：跳过）
            m.update("t1", "c", "d", 10)
            assert mock_llm.call_count == 1, "同轮次不应跳过"
            assert m._states["t1"]["_current_turn"] == 11, "轮次应抬到 last_turn + 1"

            # 倒退 → 抬到 12 后继续处理（改动前：跳过 → 状态永久冻结）
            m.update("t1", "e", "f", 3)
            assert mock_llm.call_count == 2, "轮次回退不应跳过"
            assert m._states["t1"]["_current_turn"] == 12, "轮次应继续单调递增"

        # 新字段确实被写入了（不是被 return 掉）
        assert m._states["t1"]["current_goal"]["v"] == "新目标"

    def test_turn_zero_is_ignored(self):
        """T3.7 未变：current_turn <= 0 仍直接忽略（不是合法轮次）。"""
        m = TaskStateMaintainer()
        with patch.object(m, "_extract_state_update") as mock_llm:
            m.update("t1", "c", "d", 0)
            mock_llm.assert_not_called()

    def test_llm_failure_keeps_old_state(self):
        """LLM 失败 → 保留旧状态，_current_turn 仍然前进"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 1,
            "_state_started_turn": 1,
            "current_goal": {"v": "旧目标", "u": 1},
        }
        with patch.object(m, "_extract_state_update", return_value=None):
            m.update("t1", "新消息", "新回复", 2)
        # 旧状态保留
        assert m._states["t1"]["current_goal"]["v"] == "旧目标"
        # _current_turn 前进
        assert m._states["t1"]["_current_turn"] == 2

    def test_llm_returns_empty_dict_clears_state(self):
        """LLM 返回 {} → 整体清空（话题切换信号）"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 1,
            "current_goal": {"v": "旧目标", "u": 1},
            "key_params": {"v": {"x": 1}, "u": 1},
        }
        with patch.object(m, "_extract_state_update", return_value={}):
            m.update("t1", "换个话题", "好的", 2)
        # 整体清空
        assert "current_goal" not in m._states["t1"]
        assert "key_params" not in m._states["t1"]
        # 元数据重置
        assert m._states["t1"]["_state_started_turn"] == 2

    def test_llm_returns_new_fields_merged_with_u_set(self):
        """新协议：LLM 只输出 {"v": 值}，框架强制设置 u = current_turn"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 1,
            "_state_started_turn": 1,
            "current_goal": {"v": "旧目标", "u": 1},
        }
        # 新协议下 LLM 只输出 v，不输出 u
        new_fields = {
            "current_goal": {"v": "新目标"},  # 框架会设 u=5
            "next_action": {"v": "下一步"},   # 新字段，框架设 u=5
        }
        with patch.object(m, "_extract_state_update", return_value=new_fields):
            m.update("t1", "msg", "resp", 5)
        # 新值
        assert m._states["t1"]["current_goal"]["v"] == "新目标"
        assert m._states["t1"]["next_action"]["v"] == "下一步"
        # u 由框架强制设为 5（无论 LLM 是否输出 u）
        assert m._states["t1"]["current_goal"]["u"] == 5
        assert m._states["t1"]["next_action"]["u"] == 5

    def test_llm_returns_old_style_with_u_is_overridden(self):
        """向后兼容：LLM 如果还输出 u，框架会强制覆盖为 current_turn"""
        m = TaskStateMaintainer()
        m._states["t1"] = {"_current_turn": 1, "_state_started_turn": 1}
        # 旧协议：LLM 错误地输出 u（比如伪造一个过去的轮次）
        old_style = {"goal": {"v": "目标", "u": 9999}}  # u 应被框架覆盖
        with patch.object(m, "_extract_state_update", return_value=old_style):
            m.update("t1", "m", "r", 5)
        # 框架强制 u=5，LLM 伪造的 u=9999 被忽略
        assert m._states["t1"]["goal"]["u"] == 5

    def test_llm_returns_malformed_field_skipped(self):
        """LLM 返回的字段格式不对（没 v 键）→ 跳过该字段，不崩"""
        m = TaskStateMaintainer()
        m._states["t1"] = {"_current_turn": 1, "_state_started_turn": 1}
        bad = {
            "good": {"v": "ok"},
            "bad1": "not a dict",
            "bad2": {"no_v_here": "x"},
        }
        with patch.object(m, "_extract_state_update", return_value=bad):
            m.update("t1", "m", "r", 2)
        assert m._states["t1"]["good"]["v"] == "ok"
        assert m._states["t1"]["good"]["u"] == 2  # 框架设 u
        assert "bad1" not in m._states["t1"]
        assert "bad2" not in m._states["t1"]

    def test_llm_metadata_fields_ignored(self):
        """LLM 不能覆盖元数据（'_' 前缀）"""
        m = TaskStateMaintainer()
        m._states["t1"] = {"_current_turn": 1, "_state_started_turn": 1}
        malicious = {
            "_current_turn": {"v": 9999},  # 应被忽略
            "_state_started_turn": {"v": 0},  # 应被忽略
            "real_field": {"v": "ok"},
        }
        with patch.object(m, "_extract_state_update", return_value=malicious):
            m.update("t1", "m", "r", 5)
        # 元数据没被污染
        assert m._states["t1"]["_current_turn"] == 5
        assert m._states["t1"]["_state_started_turn"] == 1
        # 真实字段合并了，u 由框架设
        assert m._states["t1"]["real_field"]["v"] == "ok"
        assert m._states["t1"]["real_field"]["u"] == 5


# ═══════════════════════════════════════════════════════════
# clear
# ═══════════════════════════════════════════════════════════

class TestTaskStateClear:
    def test_clear_removes_thread(self):
        m = TaskStateMaintainer()
        m._states["t1"] = {"_current_turn": 1, "x": {"v": 1, "u": 1}}
        m.clear("t1")
        assert "t1" not in m._states

    def test_clear_nonexistent_no_error(self):
        m = TaskStateMaintainer()
        m.clear("never_existed")  # 不抛异常


# ═══════════════════════════════════════════════════════════
# _parse_json
# ═══════════════════════════════════════════════════════════

class TestParseJson:
    def test_direct_json(self):
        assert TaskStateMaintainer._parse_json('{"a": 1}') == {"a": 1}

    def test_json_in_code_fence(self):
        content = '```json\n{"a": 1}\n```'
        assert TaskStateMaintainer._parse_json(content) == {"a": 1}

    def test_json_with_surrounding_text(self):
        content = '解释...\n{"a": 1}\n后续...'
        assert TaskStateMaintainer._parse_json(content) == {"a": 1}

    def test_invalid_returns_none(self):
        assert TaskStateMaintainer._parse_json("") is None
        assert TaskStateMaintainer._parse_json("not json") is None
        assert TaskStateMaintainer._parse_json("{bad") is None

    def test_non_dict_json_returns_as_is(self):
        # 返回 list / int 等也 OK（调用方做 isinstance 检查）
        assert TaskStateMaintainer._parse_json("[1,2,3]") == [1, 2, 3]
        assert TaskStateMaintainer._parse_json("42") == 42


# ═══════════════════════════════════════════════════════════
# get_cross_session_signals
# ═══════════════════════════════════════════════════════════

class TestCrossSessionSignals:
    def test_empty_state_returns_empty_list(self):
        m = TaskStateMaintainer()
        assert m.get_cross_session_signals("nonexist") == []

    def test_no_signals_field_returns_empty(self):
        m = TaskStateMaintainer()
        m._states["t1"] = {"_current_turn": 5, "current_goal": {"v": "任务", "u": 5}}
        assert m.get_cross_session_signals("t1") == []

    def test_signals_list_returned(self):
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 5,
            "cross_session_signals": {"v": ["用户偏好 Python", "数据库用 MySQL 8"], "u": 3},
        }
        result = m.get_cross_session_signals("t1")
        assert result == ["用户偏好 Python", "数据库用 MySQL 8"]

    def test_signals_string_wrapped_in_list(self):
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 5,
            "cross_session_signals": {"v": "单条信号", "u": 3},
        }
        result = m.get_cross_session_signals("t1")
        assert result == ["单条信号"]

    def test_signals_null_value_returns_empty(self):
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 5,
            "cross_session_signals": {"v": None, "u": 3},
        }
        assert m.get_cross_session_signals("t1") == []

    def test_signals_empty_list_returns_empty(self):
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 5,
            "cross_session_signals": {"v": [], "u": 3},
        }
        assert m.get_cross_session_signals("t1") == []


# ═══════════════════════════════════════════════════════════
# clear_cross_session_signals
# ═══════════════════════════════════════════════════════════

class TestClearCrossSessionSignals:
    def test_clear_removes_signals_field(self):
        """清空后 signals 字段应该被删除，其他字段不受影响"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 5,
            "current_goal": {"v": "任务", "u": 5},
            "cross_session_signals": {"v": ["用户偏好 Python"], "u": 3},
        }
        m.clear_cross_session_signals("t1")
        assert "cross_session_signals" not in m._states["t1"]
        assert m._states["t1"]["current_goal"]["v"] == "任务"  # 其他字段不变

    def test_clear_then_get_returns_empty(self):
        """清空后 get_cross_session_signals 应返回空列表"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 5,
            "cross_session_signals": {"v": ["信号1", "信号2"], "u": 3},
        }
        m.clear_cross_session_signals("t1")
        assert m.get_cross_session_signals("t1") == []

    def test_clear_nonexistent_thread_no_error(self):
        """清空不存在的 thread 不应该报错"""
        m = TaskStateMaintainer()
        m.clear_cross_session_signals("nonexist")  # 不抛异常

    def test_clear_thread_without_signals_no_error(self):
        """清空没有 signals 字段的 thread 不应该报错"""
        m = TaskStateMaintainer()
        m._states["t1"] = {"_current_turn": 5, "current_goal": {"v": "任务", "u": 5}}
        m.clear_cross_session_signals("t1")  # 不抛异常
        assert "current_goal" in m._states["t1"]  # 其他字段不变

    def test_clear_does_not_affect_injection(self):
        """清空 signals 后，format_for_injection 应该正常返回（有可见字段时）"""
        m = TaskStateMaintainer()
        m._states["t1"] = {
            "_current_turn": 5,
            "current_goal": {"v": "任务", "u": 5},
            "cross_session_signals": {"v": ["用户偏好 Python"], "u": 3},
        }
        # 清空前：注入文本有任务，无 signals
        out_before = m.format_for_injection("t1")
        assert "任务" in out_before
        assert "用户偏好 Python" not in out_before

        m.clear_cross_session_signals("t1")

        # 清空后：注入文本仍有任务（不受影响）
        out_after = m.format_for_injection("t1")
        assert "任务" in out_after
        assert "用户偏好 Python" not in out_after
