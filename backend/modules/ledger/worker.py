"""账本解析 worker：认领 ledger.parse job，幂等解析后完成/重试。

解析是确定性本地计算（无 LLM），失败可重试；重复投递不会产生重复批次
（批次由 (owner, file, parser, version) 唯一约束 + 收据式状态机保证）。
"""
from __future__ import annotations

import asyncio
import logging

from backend.modules.ledger.api import PARSE_JOB_KIND, LedgerService
from backend.platform.jobs import JobQueue

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 0.2
MAX_PER_TICK = 20


class LedgerWorker:
    def __init__(
        self,
        service: LedgerService,
        queue: JobQueue,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        worker_id: str = "ledger-worker",
    ) -> None:
        self.service = service
        self.queue = queue
        self.poll_interval = poll_interval
        self.worker_id = worker_id
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

    async def tick(self) -> int:
        count = 0
        while count < MAX_PER_TICK:
            lease = self.queue.claim(self.worker_id, kinds=(PARSE_JOB_KIND,))
            if lease is None:
                break
            payload = lease.payload_json()
            import_id = str(payload.get("import_id") or "")
            if not import_id:
                self.queue.fail(lease, "缺少 import_id", retryable=False)
                continue
            try:
                view = await self.service.parse_import(import_id)
            except Exception as exc:  # noqa: BLE001  存储/IO 失败可重试
                logger.exception("账单解析任务失败 import=%s", import_id)
                self.queue.fail(lease, str(exc), retryable=True, retry_delay_seconds=30)
            else:
                # failed 是确定性业务结果（格式不支持等），不无限重试
                self.queue.complete(lease)
                logger.info("账单解析 import=%s -> %s", import_id, view.state)
            count += 1
        return count

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("账本 worker tick 失败")
            await asyncio.sleep(self.poll_interval)
