"""平台网关抽象（借鉴 Eyes platform_gateway）

渠道适配器注册 + 统一生命周期管理。微信为第一适配器（包装 wechat_listener），
飞书/企微等新渠道只需实现 ChannelAdapter 并在 gateway.register() 注册。
main.py lifespan 通过 gateway.start()/stop() 统一启停。
"""
import threading
from abc import ABC, abstractmethod
from typing import Dict

from backend.utils.log_utils import log

logger = log


class ChannelAdapter(ABC):
    """渠道适配器契约：start / stop / is_running。"""
    name: str = ""

    @abstractmethod
    def start(self) -> None:
        """启动渠道（长轮询/长连接等）。"""

    @abstractmethod
    def stop(self) -> None:
        """停止渠道。"""

    @abstractmethod
    def is_running(self) -> bool:
        """渠道是否在运行。"""


class WechatChannelAdapter(ChannelAdapter):
    """微信 iLink 渠道：包装现有 wechat_listener 的启动/停止。"""
    name = "wechat"

    def __init__(self):
        self._running = False

    def start(self) -> None:
        try:
            from backend.controller.wechat_listener import start_wechat_listener as _start
            _start()
            self._running = True
            logger.info("微信渠道已启动（platform_gateway）")
        except Exception as e:
            logger.warning(f"微信渠道启动失败（不影响主服务）: {e}")

    def stop(self) -> None:
        try:
            from backend.controller.wechat.config import _listener_state
            _listener_state["running"] = False
            _task = _listener_state.get("task")
            if _task is not None and not _task.done():
                _task.cancel()
        except Exception:
            pass
        self._running = False
        logger.info("微信渠道已停止")

    def is_running(self) -> bool:
        return self._running


class PlatformGateway:
    """渠道适配器管理器：注册 / 统一启停 / 状态查询。"""

    def __init__(self):
        self._adapters: Dict[str, ChannelAdapter] = {}
        self._lock = threading.Lock()

    def register(self, adapter: ChannelAdapter) -> None:
        with self._lock:
            self._adapters[adapter.name] = adapter
            logger.info(f"注册平台渠道: {adapter.name}")

    def unregister(self, name: str) -> None:
        with self._lock:
            self._adapters.pop(name, None)

    def start(self) -> None:
        with self._lock:
            adapters = list(self._adapters.values())
        for adapter in adapters:
            adapter.start()

    def stop(self) -> None:
        with self._lock:
            adapters = list(self._adapters.values())
        for adapter in adapters:
            adapter.stop()

    def status(self) -> dict:
        with self._lock:
            return {name: a.is_running() for name, a in self._adapters.items()}


# 进程内单例：微信为第一适配器（后续飞书/企微在此 register）
gateway = PlatformGateway()
gateway.register(WechatChannelAdapter())