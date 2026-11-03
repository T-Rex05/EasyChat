"""公共测试设施（实施计划：公共测试设施与命令约定）。

只用真实临时SQLite/临时产物目录；FakeRuntime/Fake投递只替换外部网络Seam，
不模拟自己的SQL逻辑。随任务推进逐个加入真实模块实例。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Mapping

from backend.bootstrap import AppSettings
from backend.runtime.contracts import RuntimeEvent, RuntimeRequest


class FakeRuntime:
    """ExecutionRuntime 测试替身：记录请求、按预置序列回放事件，不触网。"""

    def __init__(self) -> None:
        self.requests: list[RuntimeRequest] = []
        self.execute_count: int = 0
        self.cancelled: list[str] = []
        self.closed: bool = False
        self._scripted: dict[str, list[RuntimeEvent]] = {}
        self._default: list[RuntimeEvent] = []

    def script_events(self, events: list[RuntimeEvent], *, key: str | None = None) -> None:
        """预置事件序列；key=None 时作为所有未单独预置请求的默认序列。"""
        if key is None:
            self._default = list(events)
        else:
            self._scripted[key] = list(events)

    async def execute(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]:
        self.execute_count += 1
        self.requests.append(request)
        events = self._scripted.get(request.context.run_id, self._default)
        for event in events:
            yield event

    async def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)

    async def aclose(self) -> None:
        self.closed = True


@dataclass(slots=True)
class TestRig:
    """独立配置+临时目录+替身Runtime的测试环境；用完必须 await rig.aclose()。"""

    tmp_path: Path
    settings: AppSettings
    runtime: FakeRuntime = field(default_factory=FakeRuntime)
    _closed: bool = False

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self.runtime.aclose()
        # Task 6 起在此关闭 assistant dispatcher；Task 8 起关闭 jobs worker。


def make_rig(tmp_path: Path, clock: Mapping[str, object] | None = None) -> TestRig:
    """构造独立测试环境。clock 参数在 Task 8（调度）接入注入的UTC时钟函数。"""
    del clock  # 预留：注入 clock 注释见上
    data_dir = tmp_path / "data"
    settings = AppSettings(
        data_db_path=data_dir / "app.db",
        state_db_path=data_dir / "state.db",
        artifacts_dir=data_dir / "artifacts",
    )
    return TestRig(tmp_path=tmp_path, settings=settings)


def run_async(coro: object) -> None:
    """同步入口帮助函数（供未来非async测试使用）。"""
    asyncio.run(coro)  # type: ignore[arg-type]
