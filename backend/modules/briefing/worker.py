"""简报 worker：认领 briefing.build，生成后按安静时段延迟投递。

重复任务用 dedup_key 防重；生成失败可重试，但空内容/情绪样本不足
是确定性跳过，不无限重试。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.modules.briefing.api import BriefingService
from backend.modules.delivery.contracts import DeliveryTarget
from backend.platform.jobs import JobQueue
from backend.shared.errors import ForbiddenError, NotFoundError

logger = logging.getLogger(__name__)

BRIEFING_JOB_KIND = "briefing.build"
DEFAULT_POLL_INTERVAL = 0.2
MAX_PER_TICK = 10


class BriefingWorker:
    def __init__(
        self,
        service: BriefingService,
        queue: JobQueue,
        delivery,
        *,
        access,
        channels,
        profiles,
        clock=time.time,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        worker_id: str = "briefing-worker",
    ) -> None:
        self.service = service
        self.queue = queue
        self.delivery = delivery
        self.access = access
        self.channels = channels
        self.profiles = profiles
        self.clock = clock
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
            lease = self.queue.claim(self.worker_id, kinds=(BRIEFING_JOB_KIND,))
            if lease is None:
                break
            payload = lease.payload_json()
            owner_id = int(payload.get("owner_id") or 0)
            kind = str(payload.get("kind") or "")
            local_date = str(payload.get("date") or "")
            schedule_id = str(payload.get("schedule_id") or "")
            target = None
            if payload.get("target_kind") and payload.get("target_ref"):
                target = DeliveryTarget(
                    kind=str(payload["target_kind"]),
                    ref=str(payload["target_ref"]),
                    channel_account_id=str(
                        payload.get("channel_account_id") or ""
                    ),
                )
            try:
                result = await self.service.build(
                    owner_id, kind, local_date=local_date
                )
                await self._deliver(
                    result,
                    schedule_id=schedule_id,
                    local_date=local_date,
                    target=target,
                )
            except (ForbiddenError, NotFoundError) as exc:
                # 用户被禁用/删除是确定性失败，重试只会刷日志。
                logger.warning("简报任务终止 owner=%s kind=%s: %s", owner_id, kind, exc)
                self.queue.fail(lease, str(exc), retryable=False)
            except Exception as exc:  # noqa: BLE001  可重试
                logger.exception("简报任务失败 owner=%s kind=%s", owner_id, kind)
                self.queue.fail(lease, str(exc), retryable=True, retry_delay_seconds=60)
            else:
                self.queue.complete(lease)
            count += 1
        return count

    async def _deliver(
        self, result, *, schedule_id: str, local_date: str,
        target: DeliveryTarget | None = None,
    ) -> None:
        if not result.text:
            return
        if target is None:
            if self.channels is None:
                logger.warning(
                    "简报跳过：未装配渠道且任务没有显式目标 owner=%s kind=%s",
                    result.owner_id, result.kind,
                )
                return
            resolved = self.channels.delivery_target_for_owner(result.owner_id)
            if not resolved:
                logger.warning(
                    "简报跳过：用户未绑定可用渠道 owner=%s kind=%s",
                    result.owner_id, result.kind,
                )
                return
            from backend.modules.delivery.contracts import target_from_channel

            target = target_from_channel(resolved)
        quiet = self.profiles.quiet_window(result.owner_id, now=self.clock())
        delay = max(0.0, quiet.end_epoch - self.clock()) if quiet.active else 0.0
        if delay > 0 and result.kind in ("morning", "evening"):
            # 安静时段跨日时，昨晚生成的“今天/明天”文案会过期；按实际发送日重建。
            tz = self.profiles.timezone_for(result.owner_id)
            try:
                send_date = datetime.fromtimestamp(
                    self.clock() + delay, ZoneInfo(tz)
                ).date().isoformat()
            except (ZoneInfoNotFoundError, ValueError):
                send_date = local_date
            if send_date != local_date:
                result = await self.service.build(
                    result.owner_id, result.kind, local_date=send_date
                )
                if not result.text:
                    return
        dedup = f"briefing:{result.owner_id}:{result.kind}:{local_date}:{schedule_id}"
        self.delivery.enqueue_text(
            owner_id=result.owner_id,
            target=target,
            text=result.text,
            dedup_key=dedup,
            source="schedule",
            delay_seconds=delay,
        )

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("简报 worker tick 失败")
            await asyncio.sleep(self.poll_interval)
