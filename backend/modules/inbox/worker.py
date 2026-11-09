"""收件箱富化 worker：只抓链接，失败标记 failed，不重试到天荒地老。"""
from __future__ import annotations

import asyncio
import logging

from backend.modules.inbox.api import InboxService
from backend.platform.jobs import JobQueue

logger = logging.getLogger(__name__)

INBOX_JOB_KIND = "inbox.enrich"
DEFAULT_POLL_INTERVAL = 0.2
MAX_PER_TICK = 10


class InboxWorker:
    def __init__(
        self,
        service: InboxService,
        queue: JobQueue,
        enricher,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        worker_id: str = "inbox-worker",
    ) -> None:
        self.service = service
        self.queue = queue
        self.enricher = enricher
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
            lease = self.queue.claim(self.worker_id, kinds=(INBOX_JOB_KIND,))
            if lease is None:
                break
            payload = lease.payload_json()
            item_id = str(payload.get("item_id") or "")
            if not item_id:
                self.queue.fail(lease, "缺少 item_id", retryable=False)
                continue
            try:
                await asyncio.to_thread(self.service.enrich, item_id, self.enricher.fetch)
            except KeyError:
                self.queue.fail(lease, "条目不存在", retryable=False)
            except Exception as exc:  # noqa: BLE001  抓取失败是确定性结果
                logger.warning("收件箱富化失败 item=%s: %s", item_id, exc)
                try:
                    self.service.repo.update(
                        int(payload.get("owner_id") or 0), item_id,
                        enrich_state="failed",
                    )
                except Exception:  # noqa: BLE001
                    pass
                self.queue.fail(lease, str(exc), retryable=False)
            else:
                self.queue.complete(lease)
            count += 1
        return count

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("收件箱 worker tick 失败")
            await asyncio.sleep(self.poll_interval)
