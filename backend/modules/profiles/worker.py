"""情绪采样 worker：只有用户显式 opt-in 后才落库；同一 run 幂等。"""
from __future__ import annotations

import asyncio
import logging

from backend.modules.profiles.api import ProfilesService
from backend.platform.jobs import JobQueue

logger = logging.getLogger(__name__)

MOOD_JOB_KIND = "mood.sample"
CARE_JOB_KIND = "mood.care"
DEFAULT_POLL_INTERVAL = 0.3
MAX_PER_TICK = 20


class MoodWorker:
    def __init__(
        self,
        service: ProfilesService,
        queue: JobQueue,
        *,
        delivery=None,
        channels=None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        worker_id: str = "mood-worker",
    ) -> None:
        self.service = service
        self.queue = queue
        self.delivery = delivery
        self.channels = channels
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
            lease = self.queue.claim(
                self.worker_id, kinds=(MOOD_JOB_KIND, CARE_JOB_KIND)
            )
            if lease is None:
                break
            payload = lease.payload_json()
            owner_id = int(payload.get("owner_id") or 0)
            try:
                if lease.kind == CARE_JOB_KIND:
                    self._deliver_care(owner_id, payload)
                else:
                    await self._sample(owner_id, payload)
            except Exception as exc:  # noqa: BLE001  采样/关怀失败不应阻塞其他 job
                logger.warning(
                    "情绪任务失败 kind=%s owner=%s: %s", lease.kind, owner_id, exc
                )
                self.queue.fail(lease, str(exc), retryable=False)
            else:
                self.queue.complete(lease)
            count += 1
        return count

    async def _sample(self, owner_id: int, payload: dict) -> None:
        text = str(payload.get("text") or "")
        run_id = str(payload.get("run_id") or "")
        await self.service.sample_run_for_owner_async(
            owner_id, text, run_id=run_id,
            entry_date=str(payload.get("date") or ""),
        )
        decision = self.service.care_due(owner_id)
        if decision is not None:
            self.queue.enqueue(
                kind=CARE_JOB_KIND,
                dedup_key=f"mood-care:{owner_id}:{decision.local_date}",
                payload={
                    "owner_id": owner_id,
                    "date": decision.local_date,
                    "message": decision.message,
                },
                owner_id=owner_id,
            )

    def _care_allowed(self, owner_id: int, payload: dict) -> tuple[object, str] | None:
        message = str(payload.get("message") or "")
        if not message:
            return None
        if self.delivery is None or self.channels is None:
            logger.warning("关怀任务跳过：投递未装配 owner=%s", owner_id)
            return None
        profile = self.service.get_by_owner(owner_id)
        if not profile.mood_opt_in:
            logger.info("关怀任务跳过：用户已关闭情绪 owner=%s", owner_id)
            return None
        if profile.proactivity == "low":
            logger.info("关怀任务跳过：主动性为 low owner=%s", owner_id)
            return None
        resolved = self.channels.delivery_target_for_owner(owner_id)
        if not resolved:
            logger.warning("关怀任务跳过：用户未绑定渠道 owner=%s", owner_id)
            return None
        from backend.modules.delivery.contracts import target_from_channel

        return target_from_channel(resolved), message

    def _deliver_care(self, owner_id: int, payload: dict) -> None:
        checked = self._care_allowed(owner_id, payload)
        if checked is None:
            return
        target, message = checked
        quiet = self.service.quiet_window(owner_id)
        delay = max(0.0, quiet.end_epoch - self.service.clock()) if quiet.active else 0.0
        local_date = str(payload.get("date") or "")
        if delay > 0:
            # 不把“延迟投递”交给 delivery 后立刻记成功；先排一个安静时段结束后的
            # 复核任务，届时重新检查 opt-in/主动性/绑定，发送成功才写 last_care_at。
            self.queue.enqueue(
                kind=CARE_JOB_KIND,
                dedup_key=(
                    f"mood-care-wake:{owner_id}:{local_date}:{int(quiet.end_epoch)}"
                ),
                payload=payload,
                owner_id=owner_id,
                delay_seconds=delay,
            )
            return
        # 只入队；last_care_at / mood_care_log 由 delivery 实际 sent 回调推进。
        delivery_id = self.delivery.enqueue_text(
            owner_id=owner_id, target=target, text=message,
            dedup_key=f"mood-care:{owner_id}:{local_date}",
            source="care",
        )
        # 关闭/删除/降低主动性可能恰好发生在入队前检查之后；入队后再复核一次
        # 并自行取消，缩小“已失效却仍排队发送”的竞态窗口。
        profile = self.service.get_by_owner(owner_id)
        if not profile.mood_opt_in or profile.proactivity == "low":
            cancel = getattr(self.delivery, "cancel", None)
            if cancel is not None:
                cancel(delivery_id, reason="用户删除/关闭情绪或降低主动性，取消关怀")

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("情绪 worker tick 失败")
            await asyncio.sleep(self.poll_interval)
