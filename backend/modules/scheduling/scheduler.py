"""唯一提醒调度器：周期 tick，把到期计划变成实例+投递请求。

不生成 Agent 内容、不直接发送；重启后从 scheduled_jobs.next_run_at 恢复，
occurrence 唯一键保证同一计划时刻不重复。
"""
from __future__ import annotations

import asyncio
import logging

from backend.modules.scheduling.api import SchedulingService

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 1.0


class Scheduler:
    def __init__(self, service: SchedulingService, *, poll_interval: float = DEFAULT_POLL_INTERVAL) -> None:
        self.service = service
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
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

    def tick(self) -> list[str]:
        return self.service.tick()

    async def _run(self) -> None:
        while not self._stopping:
            try:
                self.service.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001  单个计划失败不终止调度
                logger.exception("提醒调度 tick 失败")
            await asyncio.sleep(self.poll_interval)
