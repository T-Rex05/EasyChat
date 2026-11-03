"""投递 worker：唯一后台循环，按账本认领到期记录并调用发送适配器。

发送是外部调用，不持有 SQLite 事务；进程重启时 sending 记录进入 uncertain，
不盲目重发。前台 run 完成只入队，不等待发送。
"""
from __future__ import annotations

import asyncio
import logging

from backend.modules.delivery.api import DeliveryService

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 0.2
MAX_PER_TICK = 100


class DeliveryWorker:
    def __init__(self, service: DeliveryService, *, poll_interval: float = DEFAULT_POLL_INTERVAL) -> None:
        self.service = service
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._stopping = False
        self.processed = 0

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self.service.recover_inflight()
        self._stopping = False
        self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._task = None

    async def tick(self) -> int:
        """处理当前到期记录直到没有更多（有上限，避免测试/故障时热循环）。"""
        count = 0
        while count < MAX_PER_TICK and await self.service.process_next():
            count += 1
        self.processed += count
        return count

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001  单条失败不影响后续投递
                logger.exception("投递 worker 处理失败")
            await asyncio.sleep(self.poll_interval)
