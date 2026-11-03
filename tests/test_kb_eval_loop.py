"""
RAG 评测闭环单元测试

- 六态分类器 classify_result（确定性，纯函数）
- 六态计数聚合 aggregate_classifications
- 建议结算 _metrics_improved（before/after 对比逻辑）
- 建议状态机 settle_verification（需 MySQL，mock 指标函数）
- 负反馈 → 建议生成 generate_from_feedback（需 MySQL）
- 反馈 API 服务层 create_feedback 归属校验 + 检索归因（需 MySQL）
- cron 质量结算 finish_execution.quality_issues 落库（需 MySQL）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


def _mysql_available() -> bool:
    try:
        from backend.db.connection_pool import get_pool_connection
        conn = get_pool_connection()
        conn.close()
        return True
    except Exception:
        return False


requires_mysql = pytest.mark.skipif(
    not _mysql_available(), reason="MySQL 不可用，跳过 DB 集成测试"
)


# ════════════════════════════════════════════════════════════
# 六态分类器（纯函数）
# ════════════════════════════════════════════════════════════

class TestClassifyResult:
    def test_complete(self):
        from backend.service.kb.kb_eval_metrics import classify_result
        assert classify_result(
            {"recall_at_k": 1.0}, {"faithfulness": 0.9, "answer_correctness": 0.9}
        ) == "complete"

    def test_retrieval_miss(self):
        from backend.service.kb.kb_eval_metrics import classify_result
        assert classify_result(
            {"recall_at_k": 0.0}, {"faithfulness": 0.9}
        ) == "retrieval_miss"

    def test_wrong_answer_priority(self):
        """检索命中但 correctness 低 → wrong_answer（优先级高于 insufficient_context）。"""
        from backend.service.kb.kb_eval_metrics import classify_result
        assert classify_result(
            {"recall_at_k": 1.0},
            {"faithfulness": 0.3, "answer_correctness": 0.2},
        ) == "wrong_answer"

    def test_insufficient_context(self):
        from backend.service.kb.kb_eval_metrics import classify_result
        assert classify_result(
            {"recall_at_k": 1.0}, {"faithfulness": 0.4}
        ) == "insufficient_context"

    def test_partial(self):
        """命中 + faithfulness 达标但 relevancy 低 → partial。"""
        from backend.service.kb.kb_eval_metrics import classify_result
        assert classify_result(
            {"recall_at_k": 1.0},
            {"faithfulness": 0.8, "answer_relevancy": 0.5},
        ) == "partial"

    def test_unjudgeable_no_judge(self):
        from backend.service.kb.kb_eval_metrics import classify_result
        assert classify_result({"recall_at_k": 1.0}, {}) == "complete"  # 无裁判只有检索层：命中即 complete
        assert classify_result({"recall_at_k": 0.0}, {}) == "retrieval_miss"

    def test_unjudgeable_error(self):
        from backend.service.kb.kb_eval_metrics import classify_result
        assert classify_result({"error": "boom"}, {}) == "unjudgeable"

    def test_judge_none_tolerated(self):
        """judge 值为 None 时忽略该指标。"""
        from backend.service.kb.kb_eval_metrics import classify_result
        assert classify_result(
            {"recall_at_k": 1.0},
            {"faithfulness": None, "answer_correctness": 0.9},
        ) == "complete"


class TestAggregateClassifications:
    def test_counts(self):
        from backend.service.kb.kb_eval_metrics import aggregate_classifications
        counts = aggregate_classifications(["complete", "complete", "retrieval_miss", "bogus"])
        assert counts["complete"] == 2
        assert counts["retrieval_miss"] == 1
        assert counts["wrong_answer"] == 0
        assert sum(counts.values()) == 3  # 未知分类不计入


# ════════════════════════════════════════════════════════════
# 建议结算：before/after 对比（纯函数）
# ════════════════════════════════════════════════════════════

class TestMetricsImproved:
    def test_improved_recall(self):
        from backend.service.kb.kb_eval_suggestion import _metrics_improved
        improved, delta = _metrics_improved(
            {"recall_at_k": 0.2}, {"recall_at_k": 0.8}
        )
        assert improved is True
        assert delta["gains"]["recall_at_k"] == pytest.approx(0.6, abs=1e-4)

    def test_not_improved_below_threshold(self):
        from backend.service.kb.kb_eval_suggestion import _metrics_improved
        improved, _ = _metrics_improved(
            {"recall_at_k": 0.2}, {"recall_at_k": 0.22}
        )
        assert improved is False

    def test_regression_blocks(self):
        """有显著回退时即使有提升也判失败。"""
        from backend.service.kb.kb_eval_suggestion import _metrics_improved
        improved, delta = _metrics_improved(
            {"recall_at_k": 0.2, "mrr": 0.9},
            {"recall_at_k": 0.8, "mrr": 0.3},
        )
        assert improved is False
        assert "regressions" in delta and delta["regressions"]

    def test_empty_after(self):
        from backend.service.kb.kb_eval_suggestion import _metrics_improved
        improved, _ = _metrics_improved({"recall_at_k": 0.5}, {})
        assert improved is False


# ════════════════════════════════════════════════════════════
# 建议状态机（需 MySQL；mock 指标比较）
# ════════════════════════════════════════════════════════════

@requires_mysql
class TestSuggestionStateMachine:
    def _insert_suggestion(self, status="verifying", attempts=0, linked_run_ids=None):
        import json
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO kb_eval_suggestions "
                "(user_id, eval_set_id, source, kind, summary, status, linked_run_ids, attempts, before_metrics) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (999001, None, "eval", "manual", "test suggestion", status,
                 json.dumps(linked_run_ids or []), attempts,
                 json.dumps({"recall_at_k": 0.2})),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def _cleanup(self, sid):
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            conn.execute("DELETE FROM kb_eval_suggestions WHERE id = ?", (sid,))
            conn.commit()
        finally:
            conn.close()

    def test_verified_transition(self, monkeypatch):
        from backend.service.kb import kb_eval_suggestion as sug
        sid = self._insert_suggestion(status="verifying", linked_run_ids=[900001])
        try:
            monkeypatch.setattr(sug, "_run_metrics", lambda run_id: {"recall_at_k": 0.9, "mrr": 0.7})
            monkeypatch.setattr(sug, "_metrics_improved", lambda b, a: (True, {"gains": {"recall_at_k": 0.7}}))
            sug.settle_verification(900001)
            row = sug._fetch_owned(999001, sid, {"kb.manage"})
            assert row["status"] == "verified"
            assert row["attempts"] == 1
        finally:
            self._cleanup(sid)

    def test_failed_then_dismissed_after_max_attempts(self, monkeypatch):
        from backend.service.kb import kb_eval_suggestion as sug
        sid = self._insert_suggestion(status="verifying", attempts=2, linked_run_ids=[900002])
        try:
            monkeypatch.setattr(sug, "_run_metrics", lambda run_id: {"recall_at_k": 0.2})
            monkeypatch.setattr(sug, "_metrics_improved", lambda b, a: (False, {}))
            sug.settle_verification(900002)
            row = sug._fetch_owned(999001, sid, {"kb.manage"})
            assert row["status"] == "dismissed"  # 第 3 次失败 → 自动忽略
            assert row["attempts"] == 3
        finally:
            self._cleanup(sid)

    def test_settle_ignores_unrelated_run(self, monkeypatch):
        from backend.service.kb import kb_eval_suggestion as sug
        sid = self._insert_suggestion(status="verifying", linked_run_ids=[900003])
        try:
            called = {"n": 0}

            def fake_metrics(run_id):
                called["n"] += 1
                return {}

            monkeypatch.setattr(sug, "_run_metrics", fake_metrics)
            sug.settle_verification(999999)  # 不相关的 run_id
            assert called["n"] == 0
            row = sug._fetch_owned(999001, sid, {"kb.manage"})
            assert row["status"] == "verifying"
        finally:
            self._cleanup(sid)

    def test_duplicate_suggestion_dedup(self):
        from backend.service.kb import kb_eval_suggestion as sug
        first = sug._insert_suggestion(999002, None, "eval", "manual", "dup check", {"a": 1})
        second = sug._insert_suggestion(999002, None, "eval", "manual", "dup check", {"a": 1})
        try:
            assert second is None  # pending 同型去重
            row = sug._fetch_owned(999002, first, {"kb.manage"})
            assert row["status"] == "pending"
        finally:
            self._cleanup(first)


# ════════════════════════════════════════════════════════════
# 负反馈 → 建议生成（需 MySQL）
# ════════════════════════════════════════════════════════════

@requires_mysql
class TestFeedbackSuggestion:
    def test_negative_feedback_generates_suggestion(self):
        import json
        from backend.db.schema import get_conn
        from backend.service.kb import kb_feedback, kb_eval_suggestion

        conn = get_conn()
        try:
            # 造一条检索日志（有 query + chunk_ids）
            cur = conn.execute(
                "INSERT INTO kb_retrieval_logs (user_id, thread_id, query, top_k, retriever, chunk_ids, hit_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (999003, "999003_ts", "如何报销？", 5, "bm25", json.dumps([1, 2]), 2),
            )
            conn.commit()
            # 造一条负反馈
            cur = conn.execute(
                "INSERT INTO kb_feedback (user_id, thread_id, rating, retrieved_chunk_ids, status) "
                "VALUES (?, ?, ?, ?, 'open')",
                (999003, "999003_ts", -1, json.dumps([1, 2])),
            )
            conn.commit()
            fb_id = cur.lastrowid
        finally:
            conn.close()

        try:
            sid = kb_eval_suggestion.generate_from_feedback(fb_id, 999003)
            assert sid is not None
            row = kb_eval_suggestion._fetch_owned(999003, sid, {"kb.manage"})
            assert row["source"] == "feedback"
            assert row["kind"] == "manual"
            assert "如何报销" in row["summary"]
            # 反馈标记 processed，重复生成返回 None
            assert kb_eval_suggestion.generate_from_feedback(fb_id, 999003) is None
        finally:
            conn = get_conn()
            try:
                conn.execute("DELETE FROM kb_eval_suggestions WHERE user_id = 999003")
                conn.execute("DELETE FROM kb_feedback WHERE user_id = 999003")
                conn.execute("DELETE FROM kb_retrieval_logs WHERE user_id = 999003")
                conn.commit()
            finally:
                conn.close()

    def test_positive_feedback_no_suggestion(self):
        from backend.service.kb import kb_eval_suggestion
        assert kb_eval_suggestion.generate_from_feedback(999999, 999003) is None  # 不存在
        # 正反馈路径：直接调用内部逻辑（无检索日志时静默返回 None）
        from backend.service.kb import kb_feedback
        assert kb_feedback._parse_thread_user("999003_12345") == 999003
        assert kb_feedback._parse_thread_user("wx_7_o9cq80") == 7
        assert kb_feedback._parse_thread_user("badformat") is None


# ════════════════════════════════════════════════════════════
# 反馈服务层：归属校验 + 检索归因（需 MySQL）
# ════════════════════════════════════════════════════════════

@requires_mysql
class TestFeedbackService:
    def test_thread_ownership_helpers(self):
        from backend.service.kb.kb_feedback import _thread_belongs_to, FeedbackInvalid
        assert _thread_belongs_to("999004_123", 999004) is True
        assert _thread_belongs_to("999004_123", 999005) is False
        assert _thread_belongs_to("wx_999004_openid", 999004) is True

    def test_create_feedback_with_attribution(self):
        import json
        from backend.db.schema import get_conn
        from backend.service.kb import kb_feedback
        from backend.service.kb.kb_feedback import FeedbackNotFound

        conn = get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO kb_retrieval_logs (user_id, thread_id, query, top_k, retriever, chunk_ids, hit_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (999005, "999005_fbt", "问题", 5, "bm25", json.dumps([11, 22]), 2),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            result = kb_feedback.create_feedback(999005, None, "999005_fbt", -1, "答非所问")
            assert result["id"] > 0
            assert result["chunk_ids"] == [11, 22]

            # 越权：别人的 thread 前缀 → 404
            with pytest.raises(FeedbackNotFound):
                kb_feedback.create_feedback(999005, None, "888888_fbt", -1)

            # 非法 rating → 400
            from backend.service.kb.kb_feedback import FeedbackInvalid
            with pytest.raises(FeedbackInvalid):
                kb_feedback.create_feedback(999005, None, "999005_fbt", 0)
        finally:
            conn = get_conn()
            try:
                conn.execute("DELETE FROM kb_feedback WHERE user_id = 999005")
                conn.execute("DELETE FROM kb_retrieval_logs WHERE user_id = 999005")
                conn.commit()
            finally:
                conn.close()


# ════════════════════════════════════════════════════════════
# cron 质量结算：finish_execution 写 quality_issues（需 MySQL）
# ════════════════════════════════════════════════════════════

@requires_mysql
class TestCronQualitySettlement:
    def test_finish_execution_writes_quality_issues(self):
        from backend.service.cron.data import CronDataMapper
        from backend.service.cron.cron_service import STATUS_QUALITY_ISSUES
        from backend.db.schema import get_conn

        mapper = CronDataMapper()
        execution_id = mapper.create_execution(999999, "999006_quality")
        try:
            mapper.finish_execution(
                execution_id, STATUS_QUALITY_ISSUES, "报告正文", "",
                "email:ok", quality_issues="报告过短（12 字符 < 50）",
            )
            conn = get_conn()
            try:
                cur = conn.execute(
                    "SELECT status, quality_issues FROM cron_executions WHERE id = ?", (execution_id,)
                )
                rows = cur.fetchall() if hasattr(cur, "fetchall") else []
                assert rows and rows[0]["status"] == 3
                assert "报告过短" in (rows[0].get("quality_issues") or "")
            finally:
                conn.close()
        finally:
            conn = get_conn()
            try:
                conn.execute("DELETE FROM cron_executions WHERE id = ?", (execution_id,))
                conn.commit()
            finally:
                conn.close()

    def test_report_quality_pure(self):
        from backend.service.report.report_quality import check_report
        assert check_report("正常报告内容" * 20)["ok"] is True
        bad = check_report("短")
        assert bad["ok"] is False and any("过短" in i for i in bad["issues"])
