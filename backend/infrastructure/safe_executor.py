"""
Safe Executor - 后台线程安全执行器

对齐 AGI-saber 的 goSafe 模式：
- 所有异步任务走这里
- 任意异常不会影响主流程
- 支持 timeout 和 fallback

使用场景：
- 记忆提取
- 图索引
- 事件发布
- 记忆合并
"""

import contextvars
import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Optional, Any

logger = logging.getLogger(__name__)

# 全局线程池（限制并发数）
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """获取全局线程池"""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="safe_exec")
        return _executor


def go_safe(
    name: str,
    fn: Callable[[], None],
    timeout: Optional[float] = None
) -> threading.Thread:
    """
    启动带 panic recover 的后台线程（对齐 AGI-saber goSafe）

    所有异步任务应走这里，任意异常不会影响主流程：
    - 记忆提取
    - 图索引
    - 事件发布
    - 记忆合并

    Args:
        name: 任务名称（用于日志和线程名）
        fn: 要执行的函数（无参数）
        timeout: 已废弃，保留参数兼容性但不再使用（Python 线程不支持外部超时）

    Returns:
        Thread 对象

    Example:
        go_safe("memory.graph_index", lambda: graph_memory.add_to_graph(item))

    注意（contextvars 传播）：
        裸 threading.Thread **不继承** ContextVar —— 子线程里 `ctxvar.get()` 会拿到默认值。
        记忆预取等场景依赖 `_MEMORY_REFS_CTX`，若不传播则引用映射静默降级。
        因此在父线程捕获当前 context 的副本，再在子线程中用 `ctx.run(fn)` 执行。
    """
    # ★ 必须在父线程捕获 context 副本（子线程启动后再取就晚了）
    ctx = contextvars.copy_context()

    def _wrapped():
        try:
            ctx.run(fn)
        except Exception as e:
            logger.warning(
                f"⚠️ background thread panic [{name}]: {e}\n"
                f"{traceback.format_exc()}"
            )

    t = threading.Thread(
        target=_wrapped,
        name=f"go_safe:{name}",
        daemon=True
    )
    t.start()
    return t


def safe_submit(
    name: str,
    fn: Callable[[], Any],
    timeout: Optional[float] = None,
    fallback: Optional[Callable[[], Any]] = None
) -> Future:
    """
    提交任务到线程池（带 panic recover）
    
    与 go_safe 的区别：
    - go_safe: 创建新线程，不等待结果
    - safe_submit: 使用线程池，返回 Future 可获取结果
    
    Args:
        name: 任务名称
        fn: 要执行的函数
        timeout: 可选超时（秒）
        fallback: 失败时的降级函数
        
    Returns:
        Future 对象
    """
    def _wrapped():
        try:
            return fn()
        except Exception as e:
            logger.warning(f"safe_submit failed [{name}]: {e}")
            if fallback:
                try:
                    return fallback()
                except Exception as e2:
                    logger.warning(f"fallback also failed [{name}]: {e2}")
            raise
    
    return _get_executor().submit(_wrapped)


def safe_execute(
    fn: Callable[[], Any],
    fallback: Optional[Callable[[], Any]] = None,
    default: Any = None
) -> Any:
    """
    同步安全执行，捕获异常并可选执行降级
    
    Args:
        fn: 主函数
        fallback: 降级函数
        default: 失败时的默认返回值
        
    Returns:
        fn() 的返回值，或 fallback() 的返回值，或 default
    """
    try:
        return fn()
    except Exception as e:
        logger.warning(f"safe_execute failed: {e}")
        if fallback:
            try:
                return fallback()
            except Exception as e2:
                logger.warning(f"fallback also failed: {e2}")
        return default


class SafeTask:
    """
    安全任务包装器
    
    支持重试、超时、降级
    """
    
    def __init__(
        self,
        name: str,
        fn: Callable[[], Any],
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: Optional[float] = None,
        fallback: Optional[Callable[[], Any]] = None
    ):
        self.name = name
        self.fn = fn
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.fallback = fallback
        self._last_error: Optional[str] = None
    
    def execute(self) -> Any:
        """执行任务（带重试）"""
        import time
        
        for attempt in range(self.max_retries):
            try:
                return self.fn()
            except Exception as e:
                self._last_error = str(e)
                if attempt < self.max_retries - 1:
                    logger.debug(f"[{self.name}] attempt {attempt + 1} failed: {e}, retrying...")
                    time.sleep(self.retry_delay)
        
        # 所有重试失败
        logger.warning(f"[{self.name}] all {self.max_retries} attempts failed: {self._last_error}")
        
        if self.fallback:
            try:
                return self.fallback()
            except Exception as e:
                logger.warning(f"[{self.name}] fallback failed: {e}")
        
        return None
    
    def submit(self) -> Future:
        """提交到线程池"""
        return safe_submit(self.name, self.execute)


def publish_event_safe(event_type: str, payload: dict) -> None:
    """
    安全发布事件（用于事件总线）
    
    Args:
        event_type: 事件类型
        payload: 事件负载
    """
    def _publish():
        try:
            from backend.infrastructure.event_bus import publish_event
            publish_event(event_type, payload)
        except ImportError:
            # EventBus 未实现，静默跳过
            pass
        except Exception as e:
            logger.debug(f"event publish failed [{event_type}]: {e}")
    
    go_safe(f"event:{event_type}", _publish)


# 便捷别名
goSafe = go_safe  # 兼容 AGI-saber 命名