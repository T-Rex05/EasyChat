"""
LLM 网关 — 多模型配置故障转移 + 熔断器

面试卖点：不修改 Hermes 内核，通过「配置选择时路由 + TraceObserver 钩子上报」
两个切入点实现 LLM 层的高可用：

  1. CircuitBreaker：closed → open（连续失败达到阈值）→ half_open（冷却期后放行探测请求），
     标准熔断器状态机；按模型名维护，进程内线程安全。
     **Redis 持久化**：状态同步到 Redis，跨进程/重启后可恢复。
  2. ModelGateway.select_config()：is_current 优先，跳过熔断中的配置自动降级到备用配置；
     全部熔断时 fail-open 返回 is_current（避免二次故障：宁可用坏配置也不彻底断流）。
  3. 上报链路：TraceObserver.on_post_api_request → report_success(model)；
     on_api_request_error → report_failure(model)。全程零侵入。

调用方：agent_controller.get_current_model_config（Web/微信/定时任务共用的唯一配置入口）。
"""
import threading
import time
from typing import Any, Dict, List, Optional

from backend.utils.log_utils import log
from backend.infrastructure import get_cache, get_key_builder

logger = log

# 熔断状态常量（与 /metrics 的 circuit_state gauge 对应）
STATE_CLOSED = 0
STATE_OPEN = 1
STATE_HALF_OPEN = 2


class CircuitBreaker:
    """熔断器状态机：

    closed --连续失败>=阈值--> open --冷却超时--> half_open
    half_open：放行一个探测请求；成功→closed，失败→重新 open。

    **Redis 持久化**：状态同步到 Redis Hash，跨进程/重启可恢复。
    """

    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout = recovery_timeout
        self._state = STATE_CLOSED
        self._failures = 0
        self._opened_at = 0.0  # 改用 time.time() 以支持跨进程比较
        self._lock = threading.Lock()
        self._loaded_from_redis = False  # 标记是否已从 Redis 加载（在锁内访问）

    def _redis_key(self) -> str:
        """获取 Redis key。"""
        kb = get_key_builder()
        return kb.breaker_state(self.name)

    def _sync_to_redis_unlocked(self):
        """同步状态到 Redis（非阻塞，失败静默）。注意：必须在持有锁时调用。"""
        try:
            cache = get_cache()
            key = self._redis_key()
            cache.set(key, {
                "state": self._state,
                "failures": self._failures,
                "opened_at": self._opened_at,
            }, ttl=int(self.recovery_timeout * 2))  # TTL 为冷却期的 2 倍
        except Exception:
            pass  # Redis 不可用时静默降级

    def _load_from_redis_unlocked(self):
        """从 Redis 恢复状态（首次访问时调用）。注意：必须在持有锁时调用。"""
        if self._loaded_from_redis:
            return
        self._loaded_from_redis = True
        try:
            cache = get_cache()
            key = self._redis_key()
            data = cache.get(key)
            if data and isinstance(data, dict):
                self._state = int(data.get("state", STATE_CLOSED))
                self._failures = int(data.get("failures", 0))
                self._opened_at = float(data.get("opened_at", 0.0))
                logger.debug(f"[CircuitBreaker] 从 Redis 恢复状态: {self.name}, state={self._state}")
        except Exception:
            pass  # Redis 不可用时使用默认状态

    @property
    def state(self) -> int:
        with self._lock:
            self._load_from_redis_unlocked()
            return self._current_state_unlocked()

    def _current_state_unlocked(self) -> int:
        """计算当前状态（含 OPEN → HALF_OPEN 的时间转换）。注意：必须在持有锁时调用。"""
        if self._state == STATE_OPEN and self._opened_at > 0:
            elapsed = time.time() - self._opened_at
            if elapsed >= self.recovery_timeout:
                self._state = STATE_HALF_OPEN
                logger.info(f"熔断器进入半开状态: {self.name}（冷却 {elapsed:.1f}s）")
                self._sync_to_redis_unlocked()
        return self._state

    def allow_request(self) -> bool:
        """请求是否放行。closed/half_open 放行，open 拒绝。"""
        with self._lock:
            self._load_from_redis_unlocked()
            return self._current_state_unlocked() in (STATE_CLOSED, STATE_HALF_OPEN)

    def record_success(self):
        with self._lock:
            self._load_from_redis_unlocked()
            if self._current_state_unlocked() == STATE_HALF_OPEN:
                logger.info(f"熔断器恢复: {self.name}")
            self._state = STATE_CLOSED
            self._failures = 0
            self._sync_to_redis_unlocked()

    def record_failure(self):
        with self._lock:
            self._load_from_redis_unlocked()
            st = self._current_state_unlocked()
            if st == STATE_OPEN:
                self._opened_at = time.time()  # 冷却期内的失败重置计时
                self._sync_to_redis_unlocked()
                return
            self._failures += 1
            if st == STATE_HALF_OPEN or self._failures >= self.failure_threshold:
                self._state = STATE_OPEN
                self._opened_at = time.time()
                logger.warning(f"熔断器打开: {self.name}（连续失败 {self._failures} 次，冷却 {self.recovery_timeout}s）")
                self._sync_to_redis_unlocked()


class ModelGateway:
    """LLM 网关：维护每模型的熔断器，负责配置选择。"""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

    def _breaker(self, model: str) -> CircuitBreaker:
        with self._lock:
            b = self._breakers.get(model)
            if b is None:
                b = CircuitBreaker(model, self.failure_threshold, self.recovery_timeout)
                self._breakers[model] = b
            return b

    def select_config(self, configs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """从候选配置中选出一个可用配置。

        优先级：is_current 在前 → 熔断中的配置跳过 → 全部熔断时 fail-open 返回 is_current。
        返回 None 表示候选列表为空。
        """
        if not configs:
            return None
        ordered = sorted(configs, key=lambda c: (0 if c.get("is_current") else 1, c.get("id", 0)))
        for cfg in ordered:
            model = cfg.get("model_name") or ""
            b = self._breaker(model)
            if b.allow_request():
                return cfg
            logger.info(f"[熔断] 跳过模型 {model}（熔断器状态: {b.state}）")
        # fail-open：全部熔断时仍返回 is_current 配置，避免彻底断流
        logger.warning(f"全部模型配置处于熔断状态，fail-open 使用 is_current 配置")
        return ordered[0]

    def report_success(self, model: str):
        self._breaker(model).record_success()

    def report_failure(self, model: str):
        self._breaker(model).record_failure()

    def breaker_state(self, model: str) -> int:
        return self._breaker(model).state

    def report_is_available(self, model: str) -> bool:
        """检查模型是否可用（熔断器未打开）。"""
        if not model:
            return True  # 无模型名时不做拦截
        return self._breaker(model).allow_request()

    def breaker_states(self) -> Dict[str, int]:
        with self._lock:
            return {m: b.state for m, b in self._breakers.items()}


# 进程内单例
gateway = ModelGateway(
    failure_threshold=int(__import__("os").environ.get("LLM_GATEWAY_FAILURE_THRESHOLD", "3")),
    recovery_timeout=float(__import__("os").environ.get("LLM_GATEWAY_RECOVERY_SECONDS", "60")),
)