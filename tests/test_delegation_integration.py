"""委派上下文富化 -- 集成测试

覆盖：
  - enrich_context + _build_child_system_prompt 的端到端模拟
  - 回调机制的正确性
  - 异常降级行为

注意：delegate_tool.py 依赖 Hermes 内部模块路径，
因此本测试通过模拟 _build_child_agent 中的富化逻辑来验证集成。

运行：
  pytest tests/test_delegation_integration.py -v
"""

import pytest
from unittest.mock import patch, MagicMock

from backend.service.delegation.context_enrichment import enrich_context


class TestEnricherCallbackMechanism:
    """回调机制测试（模拟 delegate_tool 中的逻辑）"""

    def test_enricher_applied_to_context(self):
        """模拟 _build_child_agent 中的富化流程"""
        with patch("backend.service.delegation.context_enrichment._load_task_state") as mock_ts, \
             patch("backend.service.delegation.context_enrichment._load_memory_refs") as mock_refs:

            mock_ts.return_value = {
                "current_goal": {"v": "处理订单", "u": 1},
            }
            mock_refs.return_value = {
                "M1": {"category": "fact", "content": "使用顺丰"},
            }

            # 模拟 _build_child_agent 中的逻辑
            original_context = "请用中文回复"
            goal = "查询物流"

            # 这是 delegate_tool.py 中的代码逻辑
            _child_context = original_context
            # _context_enricher 就是 enrich_context
            _child_context = enrich_context(original_context, goal)

            # 验证富化结果包含所有信息
            assert "<inherited_task_state>" in _child_context
            assert "当前目标: 处理订单" in _child_context
            assert "<inherited_memories>" in _child_context
            assert "<supervisor_notes>" in _child_context
            assert "请用中文回复" in _child_context

    def test_enricher_exception_fallback(self):
        """enricher 异常时回退到原始 context（模拟 _build_child_agent 中的 try/except）"""
        def bad_enricher(context, goal):
            raise RuntimeError("enricher failed")

        # 模拟 _build_child_agent 中的异常处理
        original_context = "原始内容"
        goal = "测试"

        _child_context = original_context
        _context_enricher = bad_enricher  # 模拟回调
        if _context_enricher:
            try:
                _child_context = _context_enricher(original_context, goal)
            except Exception:
                _child_context = original_context  # degrade gracefully

        assert _child_context == "原始内容"

    def test_no_enricher_passthrough(self):
        """未注册回调时 context 原样传递"""
        _context_enricher = None  # 模拟未注册

        original_context = "原始内容"
        goal = "测试"

        _child_context = original_context
        if _context_enricher:
            try:
                _child_context = _context_enricher(original_context, goal)
            except Exception:
                _child_context = original_context

        assert _child_context == "原始内容"


class TestSystemPromptSimulation:
    """模拟 _build_child_system_prompt 的行为"""

    @staticmethod
    def _simulate_build_child_prompt(goal, context=None, workspace_path=None):
        """模拟 _build_child_system_prompt 的拼接逻辑"""
        parts = [
            "You are a focused subagent working on a specific delegated task.",
            "",
            f"YOUR TASK:\n{goal}",
        ]
        if context and context.strip():
            parts.append(f"\nCONTEXT:\n{context}")
        if workspace_path:
            parts.append(f"\nWORKSPACE PATH:\n{workspace_path}")
        parts.append(
            "\nComplete this task using the tools available to you."
        )
        return "\n".join(parts)

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_full_pipeline(self, mock_ts, mock_refs):
        """完整流程：LLM context -> enricher -> 系统提示词"""
        mock_ts.return_value = {
            "current_goal": {"v": "处理订单A123", "u": 1},
            "completed_steps": {"v": ["已下单", "已付款"], "u": 12},
            "key_params": {"v": {"订单号": "A123"}, "u": 3},
        }
        mock_refs.return_value = {
            "M1": {"category": "preference", "content": "用户偏好顺丰"},
            "M2": {"category": "fact", "content": "使用MySQL 8.0"},
        }

        # LLM 填的原始 context
        original_context = "请用中文回复，返回物流公司和当前状态"

        # 经过 enricher
        enriched = enrich_context(original_context, "查询物流")

        # 传入模拟的 _build_child_system_prompt
        prompt = self._simulate_build_child_prompt(
            goal="查询订单A123的物流状态",
            context=enriched,
        )

        # 验证
        assert "YOUR TASK:\n查询订单A123的物流状态" in prompt
        assert "CONTEXT:" in prompt
        assert "<inherited_task_state>" in prompt
        assert "当前目标: 处理订单A123" in prompt
        assert "<inherited_memories>" in prompt
        assert "[M1] [preference] 用户偏好顺丰" in prompt
        assert "<supervisor_notes>" in prompt
        assert "请用中文回复" in prompt

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_empty_enrichment_clean_prompt(self, mock_ts, mock_refs):
        """富化结果为空时：无 inherited_* 冗余块，仅保留输出契约与原始备注"""
        mock_ts.return_value = None
        mock_refs.return_value = None

        enriched = enrich_context("原始备注", "目标")

        prompt = self._simulate_build_child_prompt(
            goal="测试任务",
            context=enriched,
        )

        assert "YOUR TASK:\n测试任务" in prompt
        assert "原始备注" in prompt
        assert "<inherited_task_state>" not in prompt
        assert "<inherited_memories>" not in prompt
        assert "<output_contract>" in prompt
        assert "<supervisor_notes>" in prompt

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_batch_delegation_same_snapshot(self, mock_ts, mock_refs):
        """批量委派时每个子 Agent 拿到相同快照"""
        mock_ts.return_value = {
            "current_goal": {"v": "共享目标", "u": 1},
        }
        mock_refs.return_value = {
            "M1": {"category": "fact", "content": "共享记忆"},
        }

        # 模拟 3 个子 Agent 的委派
        results = []
        for i in range(3):
            enriched = enrich_context(f"子任务{i}的备注", f"目标{i}")
            results.append(enriched)

        # 所有子 Agent 的 TaskState 和记忆部分相同
        for r in results:
            assert "<inherited_task_state>" in r
            assert "共享目标" in r
            assert "<inherited_memories>" in r
            assert "共享记忆" in r

        # supervisor_notes 各自不同
        assert "子任务0的备注" in results[0]
        assert "子任务1的备注" in results[1]
        assert "子任务2的备注" in results[2]


class TestEdgeCases:
    """边界情况"""

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_unicode_content(self, mock_ts, mock_refs):
        """中文/特殊字符正确处理"""
        mock_ts.return_value = {
            "current_goal": {"v": "处理中文订单🎉", "u": 1},
        }
        mock_refs.return_value = {
            "M1": {"category": "fact", "content": "特殊字符：@#$%"},
        }
        result = enrich_context("备注内容\n换行测试")
        assert "处理中文订单🎉" in result
        assert "特殊字符：@#$%" in result
        assert "备注内容\n换行测试" in result

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_large_memory_set(self, mock_ts, mock_refs):
        """大量记忆条目"""
        mock_ts.return_value = None
        mock_refs.return_value = {
            f"M{i}": {"category": "fact", "content": f"记忆内容{i}"}
            for i in range(50)
        }
        result = enrich_context("备注")
        assert "<inherited_memories>" in result
        assert result.count("[M") == 50

    @patch("backend.service.delegation.context_enrichment._load_memory_refs")
    @patch("backend.service.delegation.context_enrichment._load_task_state")
    def test_task_state_with_complex_values(self, mock_ts, mock_refs):
        """TaskState 含复杂嵌套值"""
        mock_ts.return_value = {
            "key_params": {"v": {"nested": {"deep": "value"}}, "u": 1},
        }
        mock_refs.return_value = None
        result = enrich_context(None)
        assert "<inherited_task_state>" in result
        assert "关键参数" in result
