"""子 Agent 上下文富化 -- 单元测试

覆盖：
  - backend.service.delegation.context_enrichment:
      * _format_task_state: 正常/空/无值/跳过元数据
      * _format_memories: 正常/空/跳过空内容
      * enrich_context: 双有/仅TaskState/仅记忆/双空/无原始context/异常降级

运行：
  pytest tests/test_context_enrichment.py -v
"""

import pytest
from unittest.mock import patch, MagicMock

from backend.service.delegation.context_enrichment import (
    enrich_context,
    _format_task_state,
    _format_memories,
    _OUTPUT_CONTRACT as _CONTRACT_TEXT,
)


class TestFormatTaskState:
    """TaskState 格式化"""

    def test_normal_state(self):
        ts = {
            "current_goal": {"v": "处理订单A123", "u": 1},
            "completed_steps": {"v": ["已下单", "已付款"], "u": 12},
            "next_action": {"v": "查询物流", "u": 12},
        }
        result = _format_task_state(ts)
        assert result is not None
        assert "<inherited_task_state>" in result
        assert "当前目标: 处理订单A123" in result
        assert "已完成步骤" in result
        assert "下一步: 查询物流" in result

    def test_empty_state(self):
        assert _format_task_state({}) is None

    def test_none_state(self):
        assert _format_task_state(None) is None

    def test_state_with_no_values(self):
        ts = {"current_goal": {"v": None, "u": 1}}
        assert _format_task_state(ts) is None

    def test_skips_framework_metadata(self):
        """_ 前缀的字段不应出现在输出中"""
        ts = {
            "_current_turn": 15,
            "_state_started_turn": 1,
            "current_goal": {"v": "测试目标", "u": 1},
        }
        result = _format_task_state(ts)
        assert result is not None
        assert "_current_turn" not in result
        assert "_state_started_turn" not in result
        assert "测试目标" in result

    def test_all_fields_present(self):
        ts = {
            "current_goal": {"v": "目标", "u": 1},
            "completed_steps": {"v": ["步骤1"], "u": 2},
            "next_action": {"v": "下一步", "u": 3},
            "key_params": {"v": {"key": "val"}, "u": 4},
            "constraints": {"v": ["约束1"], "u": 5},
            "decisions": {"v": [{"choice": "A"}], "u": 6},
        }
        result = _format_task_state(ts)
        assert "当前目标" in result
        assert "已完成步骤" in result
        assert "下一步" in result
        assert "关键参数" in result
        assert "约束条件" in result
        assert "已做决策" in result


class TestFormatMemories:
    """记忆格式化"""

    def test_normal_memories(self):
        refs = {
            "M1": {"category": "preference", "content": "用户偏好顺丰"},
            "M2": {"category": "fact", "content": "使用MySQL 8.0"},
        }
        result = _format_memories(refs)
        assert result is not None
        assert "<inherited_memories>" in result
        assert "[M1] [preference] 用户偏好顺丰" in result
        assert "[M2] [fact] 使用MySQL 8.0" in result

    def test_empty_memories(self):
        assert _format_memories({}) is None

    def test_none_memories(self):
        assert _format_memories(None) is None

    def test_skips_empty_content(self):
        refs = {"M1": {"category": "fact", "content": ""}}
        assert _format_memories(refs) is None

    def test_skips_non_dict_entries(self):
        refs = {"M1": "not a dict", "M2": {"category": "fact", "content": "有效内容"}}
        result = _format_memories(refs)
        assert result is not None
        assert "有效内容" in result

    def test_missing_category_defaults_to_unknown(self):
        refs = {"M1": {"content": "没有类别"}}
        result = _format_memories(refs)
        assert "[unknown]" in result

    def test_real_producer_shape_uses_memory_type(self):
        """真实生产形状：agentforge_provider.prefetch 写的是 memory_type（不是 category）。

        历史缺陷：这里读 category，导致真实环境恒输出 [unknown]（测试用 mock 喂了
        category，所以一直是绿的）。
        """
        refs = {
            "M1": {
                "id": 12,
                "content": "用户偏好顺丰快递",
                "memory_type": "preference",
                "created_at": "2026-01-01 00:00:00",
            }
        }
        result = _format_memories(refs)
        assert "[M1] [preference] 用户偏好顺丰快递" in result
        assert "[unknown]" not in result


class TestEnrichContext:
    """enrich_context 整体逻辑"""

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_both_present(self, mock_ts, mock_refs):
        """TaskState + 记忆都有时，三者全部出现"""
        mock_ts.return_value = {
            "current_goal": {"v": "处理订单", "u": 1},
        }
        mock_refs.return_value = {
            "M1": {"category": "fact", "content": "使用顺丰"},
        }
        result = enrich_context("请用中文回复")
        assert "<inherited_task_state>" in result
        assert "当前目标: 处理订单" in result
        assert "<inherited_memories>" in result
        assert "[M1]" in result
        assert "<supervisor_notes>" in result
        assert "请用中文回复" in result

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_only_task_state(self, mock_ts, mock_refs):
        mock_ts.return_value = {
            "current_goal": {"v": "处理订单", "u": 1},
        }
        mock_refs.return_value = None
        result = enrich_context("请用中文回复")
        assert "<inherited_task_state>" in result
        assert "<inherited_memories>" not in result
        assert "<supervisor_notes>" in result

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_only_memories(self, mock_ts, mock_refs):
        mock_ts.return_value = None
        mock_refs.return_value = {
            "M1": {"category": "fact", "content": "使用顺丰"},
        }
        result = enrich_context("请用中文回复")
        assert "<inherited_task_state>" not in result
        assert "<inherited_memories>" in result
        assert "<supervisor_notes>" in result

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_both_empty_still_injects_contract(self, mock_ts, mock_refs):
        """TaskState/记忆都为空时：只追加输出契约 + 原始 context 包成 supervisor_notes"""
        mock_ts.return_value = None
        mock_refs.return_value = None
        result = enrich_context("请用中文回复")
        assert "<inherited_task_state>" not in result
        assert "<inherited_memories>" not in result
        assert "<output_contract>" in result
        assert "<supervisor_notes>" in result
        assert "请用中文回复" in result

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_original_context_none(self, mock_ts, mock_refs):
        mock_ts.return_value = {
            "current_goal": {"v": "测试", "u": 1},
        }
        mock_refs.return_value = None
        result = enrich_context(None)
        assert "<inherited_task_state>" in result
        assert "<supervisor_notes>" not in result

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_original_context_empty_string(self, mock_ts, mock_refs):
        mock_ts.return_value = {
            "current_goal": {"v": "测试", "u": 1},
        }
        mock_refs.return_value = None
        result = enrich_context("  ")
        assert "<supervisor_notes>" not in result

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_all_empty_and_no_original(self, mock_ts, mock_refs):
        """全空且无原始 context：只剩输出契约（保证子 Agent 始终拿到结构约束）"""
        mock_ts.return_value = None
        mock_refs.return_value = None
        result = enrich_context(None)
        assert result == _CONTRACT_TEXT

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_task_state_exception_degrades(self, mock_ts, mock_refs):
        """TaskState 异常时不影响记忆注入"""
        mock_ts.side_effect = Exception("DB error")
        mock_refs.return_value = {
            "M1": {"category": "fact", "content": "使用顺丰"},
        }
        result = enrich_context("请用中文回复")
        assert "<inherited_task_state>" not in result
        assert "<inherited_memories>" in result
        assert "<supervisor_notes>" in result

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_all_exception_still_delivers_contract_and_original(self, mock_ts, mock_refs):
        """读取全部异常时：仍保留原始 context（包成 supervisor_notes）+ 输出契约"""
        mock_ts.side_effect = Exception("DB error")
        mock_refs.side_effect = Exception("Memory error")
        result = enrich_context("原始内容")
        assert "<inherited_task_state>" not in result
        assert "<inherited_memories>" not in result
        assert "<output_contract>" in result
        assert "原始内容" in result

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_ordering(self, mock_ts, mock_refs):
        """验证 XML 块的顺序：task_state -> memories -> output_contract -> supervisor_notes"""
        mock_ts.return_value = {
            "current_goal": {"v": "目标", "u": 1},
        }
        mock_refs.return_value = {
            "M1": {"memory_type": "fact", "content": "记忆"},
        }
        result = enrich_context("备注")
        ts_pos = result.index("<inherited_task_state>")
        mem_pos = result.index("<inherited_memories>")
        contract_pos = result.index("<output_contract>")
        notes_pos = result.index("<supervisor_notes>")
        assert ts_pos < mem_pos < contract_pos < notes_pos


class TestOutputContract:
    """子 Agent 输出契约（B3）"""

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_contract_present_by_default(self, mock_ts, mock_refs):
        mock_ts.return_value = None
        mock_refs.return_value = None
        result = enrich_context("备注")
        assert _CONTRACT_TEXT in result
        # 契约必须真的约束到关键字段，而不是一句空话
        for field in ("status:", "conclusion:", "evidence:", "files:", "errors:"):
            assert field in result

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_contract_can_be_disabled(self, mock_ts, mock_refs, monkeypatch):
        """AGENTFORGE_DELEGATION_CONTRACT=0 → 回到"两者都为空时不追加任何内容"的原生行为"""
        monkeypatch.setenv("AGENTFORGE_DELEGATION_CONTRACT", "0")
        mock_ts.return_value = None
        mock_refs.return_value = None
        assert enrich_context("请用中文回复") == "请用中文回复"
        assert enrich_context(None) == ""
