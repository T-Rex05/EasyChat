"""记忆信号 worker：认领 memory.signal job，幂等应用后完成/重试。"""
from __future__ import annotations

import asyncio
import logging

from backend.modules.memory.api import MemoryService
from backend.platform.jobs import JobQueue

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 0.2
MAX_PER_TICK = 50


class MemoryWorker:
    def __init__(
        self, service: MemoryService, queue: JobQueue, *, poll_interval: float = DEFAULT_POLL_INTERVAL
    ) -> None:
        self.service = service
        self.queue = queue
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self.queue.recover_expired_leases()
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

    def tick(self) -> int:
        count = 0
        while count < MAX_PER_TICK:
            lease = self.queue.claim("memory-worker", kinds=("memory.signal",))
            if lease is None:
                break
            payload = lease.payload_json()
            signal_id = str(payload.get("signal_id") or "")
            try:
                receipt = self.service.apply_signal(signal_id)
            except Exception as exc:  # noqa: BLE001  依赖/存储失败可重试
                logger.exception("记忆信号处理失败 signal=%s", signal_id)
                self.queue.fail(lease, str(exc), retryable=True, retry_delay_seconds=60)
            else:
                # rejected 也是确定性结果（来源缺失/已遗忘），不反复重试
                self.queue.complete(lease)
                logger.info("记忆信号 %s -> %s", signal_id, receipt.state)
            count += 1
        return count

    async def _run(self) -> None:
        while not self._stopping:
            try:
                self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("记忆 worker tick 失败")
            await asyncio.sleep(self.poll_interval)
