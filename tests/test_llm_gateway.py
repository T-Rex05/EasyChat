"""LLM 网关（熔断器 + 故障转移）单元测试"""
import time

from backend.service.llm_gateway import (
    CircuitBreaker, ModelGateway, STATE_CLOSED, STATE_OPEN, STATE_HALF_OPEN,
)


class TestCircuitBreaker:
    def test_initial_closed(self):
        b = CircuitBreaker("m1")
        assert b.state == STATE_CLOSED
        assert b.allow_request() is True

    def test_opens_after_threshold(self):
        b = CircuitBreaker("m1", failure_threshold=3, recovery_timeout=60)
        b.record_failure()
        b.record_failure()
        assert b.state == STATE_CLOSED
        b.record_failure()
        assert b.state == STATE_OPEN
        assert b.allow_request() is False

    def test_half_open_after_recovery(self):
        b = CircuitBreaker("m1", failure_threshold=1, recovery_timeout=0.01)
        b.record_failure()
        assert b.state == STATE_OPEN
        time.sleep(0.02)
        assert b.state == STATE_HALF_OPEN
        assert b.allow_request() is True

    def test_half_open_success_closes(self):
        b = CircuitBreaker("m1", failure_threshold=1, recovery_timeout=0.01)
        b.record_failure()
        time.sleep(0.02)
        assert b.state == STATE_HALF_OPEN
        b.record_success()
        assert b.state == STATE_CLOSED
        assert b.allow_request() is True

    def test_half_open_failure_reopens(self):
        b = CircuitBreaker("m1", failure_threshold=1, recovery_timeout=0.01)
        b.record_failure()
        time.sleep(0.02)
        b.record_failure()  # 半开状态下的探测请求再次失败 → 重新熔断
        assert b.state == STATE_OPEN


class TestModelGateway:
    @staticmethod
    def _cfg(cid, model, current=0):
        return {"id": cid, "model_name": model, "api_url": f"http://u{cid}",
                "api_key": "k", "is_current": current}

    def test_prefers_current(self):
        gw = ModelGateway()
        cfg = gw.select_config([self._cfg(1, "m1"), self._cfg(2, "m2", current=1)])
        assert cfg["id"] == 2

    def test_skip_open_breaker_fails_over(self):
        gw = ModelGateway(failure_threshold=1, recovery_timeout=60)
        gw.report_failure("m2")  # current 模型熔断
        cfg = gw.select_config([self._cfg(1, "m1"), self._cfg(2, "m2", current=1)])
        assert cfg["id"] == 1  # 自动降级到备用配置

    def test_fail_open_when_all_open(self):
        gw = ModelGateway(failure_threshold=1, recovery_timeout=60)
        gw.report_failure("m1")
        gw.report_failure("m2")
        cfg = gw.select_config([self._cfg(1, "m1"), self._cfg(2, "m2", current=1)])
        assert cfg is not None and cfg["id"] == 2  # fail-open：全部熔断仍返回 is_current

    def test_breaker_recovers_after_timeout(self):
        gw = ModelGateway(failure_threshold=1, recovery_timeout=0.01)
        gw.report_failure("m1")
        cfg = gw.select_config([self._cfg(1, "m1", current=1), self._cfg(2, "m2")])
        assert cfg["id"] == 2  # m1 熔断 → 降级到 m2
        time.sleep(0.02)
        cfg = gw.select_config([self._cfg(1, "m1", current=1), self._cfg(2, "m2")])
        assert cfg["id"] == 1  # m1 半开 → 恢复可用

    def test_empty_candidates(self):
        assert ModelGateway().select_config([]) is None

    def test_success_resets_failures(self):
        gw = ModelGateway(failure_threshold=2, recovery_timeout=60)
        gw.report_failure("m1")
        gw.report_success("m1")
        gw.report_failure("m1")
        cfg = gw.select_config([self._cfg(1, "m1", current=1), self._cfg(2, "m2")])
        assert cfg["id"] == 1  # 失败计数被成功重置，未达阈值