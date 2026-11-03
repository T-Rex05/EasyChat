"""RunRegistry 单元测试 — SSE run 生命周期（事件驱动 subscribe）"""
import asyncio
import time

import pytest

from backend.service.run_registry import RunRegistry, ThreadBusyError


async def _frames(*items, gap=0.001):
    for it in items:
        yield it
        await asyncio.sleep(gap)


def _expected_frames(seqs):
    """subscribe() 的 SSE 契约：每帧先发 `id: N`（供浏览器 Last-Event-ID
    断线续传），再发帧本身。所以期望序列是 id 行与帧交替出现。"""
    out = []
    for i in seqs:
        out += [f"id: {i}\n", f"f{i}"]
    return out


class TestRunRegistry:
    def test_get_or_create_runs_to_done(self):
        async def main():
            reg = RunRegistry()

            async def producer():
                async for f in _frames("a", "b"):
                    yield f

            run, created = reg.get_or_create("t1", "m1", producer)
            assert created is True
            assert run.status == "RUNNING"
            await run.task
            assert run.status == "DONE"
            assert run.seq == 2
        asyncio.run(main())

    def test_same_thread_busy(self):
        async def main():
            reg = RunRegistry()

            async def slow():
                yield "x"
                await asyncio.sleep(0.2)

            run, _ = reg.get_or_create("t1", "m1", slow)
            with pytest.raises(ThreadBusyError):
                reg.get_or_create("t1", "m2", slow)
            run.task.cancel()
            try:
                await run.task
            except (asyncio.CancelledError, Exception):
                pass
        asyncio.run(main())

    def test_subscribe_receives_all_frames(self):
        async def main():
            reg = RunRegistry()

            async def producer():
                for i in range(5):
                    yield f"f{i}"

            run, _ = reg.get_or_create("t1", "m1", producer)
            got = []
            async for frame in reg.subscribe(run, from_seq=0):
                got.append(frame)
            assert got == _expected_frames(range(5))
        asyncio.run(main())

    def test_subscribe_from_seq_resumes(self):
        async def main():
            reg = RunRegistry()

            async def producer():
                for i in range(5):
                    yield f"f{i}"
                    await asyncio.sleep(0.005)

            run, _ = reg.get_or_create("t1", "m1", producer)
            # 等前 3 帧产出
            while run.seq < 3:
                await asyncio.sleep(0.005)
            got = []
            async for frame in reg.subscribe(run, from_seq=2):
                got.append(frame)
            assert got == _expected_frames((2, 3, 4))
        asyncio.run(main())

    def test_live_frames_during_subscribe(self):
        async def main():
            reg = RunRegistry()

            async def producer():
                for i in range(5):
                    yield f"f{i}"
                    await asyncio.sleep(0.01)

            run, _ = reg.get_or_create("t1", "m1", producer)
            got = []

            async def consume():
                async for frame in reg.subscribe(run, from_seq=0):
                    got.append(frame)

            # 边生产边消费
            await asyncio.gather(consume(), run.task)
            assert got == _expected_frames(range(5))
        asyncio.run(main())

    def test_user_cancel(self):
        async def main():
            reg = RunRegistry()

            async def slow():
                while True:
                    yield "x"
                    await asyncio.sleep(0.01)

            run, _ = reg.get_or_create("t1", "m1", slow)
            assert reg.user_cancel("t1", "m1") is True
            with pytest.raises(asyncio.CancelledError):
                await run.task
            assert run.status == "CANCELLED"
            assert reg.user_cancel("t1", "m1") is False
        asyncio.run(main())

    def test_sweep_removes_finished(self):
        async def main():
            reg = RunRegistry()

            async def producer():
                yield "a"

            run, _ = reg.get_or_create("t1", "m1", producer)
            await run.task
            # sweep 现在要求完成后 60 秒才清理，模拟已过期
            run.completed_at = time.time() - 61
            reg.sweep()
            assert "t1:m1" not in reg._runs
        asyncio.run(main())

    def test_done_run_not_busy(self):
        async def main():
            reg = RunRegistry()

            async def producer():
                yield "a"

            run, _ = reg.get_or_create("t1", "m1", producer)
            await run.task
            # 同 thread 新 run 不再被已结束的 run 阻塞
            run2, created2 = reg.get_or_create("t1", "m2", producer)
            assert created2 is True
            await run2.task
        asyncio.run(main())