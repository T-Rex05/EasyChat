"""公共测试设施（实施计划：公共测试设施与命令约定）。

只用真实临时SQLite/临时产物目录；FakeRuntime/Fake投递只替换外部网络Seam，
不模拟自己的SQL逻辑。随任务推进逐个加入真实模块实例。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from backend.bootstrap import AppSettings
from backend.platform.sqlite import Database, utc_now_iso
from backend.runtime.contracts import RuntimeEvent, RuntimeRequest

# 测试专用 JWT 密钥（64位，满足弱密钥拒绝规则）
TEST_JWT_SECRET = "e" * 64
# 测试专用渠道凭证加密密钥（不与生产共享）
TEST_ENCRYPTION_SECRET = "k" * 64


class FakeClock:
    """可推进的确定性时钟（秒）。"""

    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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
    clock: FakeClock = field(default_factory=FakeClock)
    runtime: FakeRuntime = field(default_factory=FakeRuntime)
    db: Database | None = None
    access: object | None = None  # Task 3: AccessService（字符串标注避免导入细节泄漏）
    assistant: object | None = None  # Task 6: AssistantService
    channels: object | None = None  # Task 7: ChannelService
    files: object | None = None  # 增量 F1: FileService
    ledger: object | None = None  # 增量 F4: LedgerService
    ledger_queue: object | None = None  # 增量 F5: JobQueue
    _closed: bool = False

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.channels is not None:
            await self.channels.aclose()
        if self.assistant is not None:
            await self.assistant.aclose()
        await self.runtime.aclose()
        if self.db is not None:
            self.db.close()
        # Task 8 起在此关闭 jobs worker。

    # ---- 种子（真实写入口；说明见各方法 docstring） ---------------------------

    def seed_user(
        self,
        role: str = "user",
        grants: tuple[str, ...] = (),
        revokes: tuple[str, ...] = (),
        username: str | None = None,
    ):
        """经真实 access 注册入口建用户，再按 bootstrap 种子语义设定角色/覆盖。

        角色与覆盖经 repository 写入（等价旧 SQL 播种路径），随后 invalidate_all
        保持缓存一致；有效权限仍由服务层规则计算，测试不手工拼权限集合。
        """
        assert self.access is not None, "make_rig(seed_access=True) 才能使用 seed_user"
        access = self.access
        name = username or f"user_{utc_now_iso()}_{uuid.uuid4().hex[:8]}"
        result = access.register(name, "password6")
        user_id = result["user_id"]
        if role != "user":
            access.repo.set_user_role(user_id, role)
        for perm in grants:
            access.repo.set_user_permission(user_id, perm, True)
        for perm in revokes:
            access.repo.set_user_permission(user_id, perm, False)
        access.invalidate_all()
        return access.snapshot_principal(user_id)

    async def seed_session(self, principal, source: str = "web", external_chat_id: str = "") -> str:
        """真实会话入口创建会话（Task 6：assistant.create_session）。"""
        assert self.assistant is not None, "attach_assistant() 后才能使用 seed_session"
        return await self.assistant.create_session(principal, source=source, external_chat_id=external_chat_id)

    def attach_assistant(self, *, wait_capacity: int = 32) -> None:
        """装配 AssistantService（FakeRuntime + 已迁移的 access）。"""
        from backend.modules.assistant.api import AssistantService

        assert self.access is not None, "make_rig(seed_access=True) 后才能 attach_assistant"
        self.assistant = AssistantService(
            self.db,
            runtime=self.runtime,
            models=None,
            access=self.access,
            wait_capacity=wait_capacity,
        )

    async def start_assistant(self) -> None:
        assert self.assistant is not None
        await self.assistant.start()

    def attach_channels(self, *, transport=None, media_fetcher=None, media_dir=None):
        """装配 ChannelService（Task 7）：默认 FakeTransport，不触网。"""
        from backend.modules.channels.api import ChannelService
        from tests.support.wechat import FakeTransport

        assert self.assistant is not None, "attach_assistant() 后才能 attach_channels"
        assert self.access is not None
        self.channels = ChannelService(
            self.db,
            assistant=self.assistant,
            access=self.access,
            encryption_secret=TEST_ENCRYPTION_SECRET,
            transport=transport or FakeTransport(),
            media_fetcher=media_fetcher,
            media_dir=media_dir,
            clock=self.clock,
        )
        return self.channels

    def attach_files(self, *, min_free_bytes: int = 0, delete_hook=None):
        """装配 FileService（增量 F1）：真实临时 SQLite + 临时文件根目录。"""
        from backend.modules.files.api import FileService
        from backend.modules.files.local_store import LocalFileStore

        assert self.db is not None, "make_rig(seed_access=True) 后才能 attach_files"
        assert self.access is not None
        store = LocalFileStore(self.settings.files_root)
        self.files = FileService(
            self.db, access=self.access, store=store,
            min_free_bytes=min_free_bytes, delete_hook=delete_hook,
        )
        return self.files

    async def drain_runs(self, *, max_polls: int = 600) -> None:
        """推进调度直到无 queued/running/cancel_requested；超限直接失败。"""
        import asyncio

        from backend.modules.assistant.repository import (
            RUN_CANCEL_REQUESTED,
            RUN_QUEUED,
            RUN_RUNNING,
        )

        assert self.assistant is not None
        polls = 0
        while polls < max_polls:
            conn = self.db.connect()
            try:
                row = conn.execute(
                    "SELECT count(*) AS c FROM runs WHERE status IN (?,?,?)",
                    (RUN_QUEUED, RUN_RUNNING, RUN_CANCEL_REQUESTED),
                ).fetchone()
            finally:
                conn.close()
            if int(row["c"]) == 0:
                return
            polls += 1
            await asyncio.sleep(0.02)
        raise AssertionError(f"drain_runs 超时：run 未能推进到终态（polls={max_polls}）")


def make_rig(
    tmp_path: Path,
    clock: FakeClock | None = None,
    *,
    seed_access: bool = False,
) -> TestRig:
    """构造独立测试环境。seed_access=True 时迁移真实临时库并装配 AccessService。

    clock 传入可推进的 FakeClock 以固定时间（Task 8 调度测试使用）。
    """
    from backend.modules.access.api import AccessService

    data_dir = tmp_path / "data"
    settings = AppSettings(
        data_db_path=data_dir / "app.db",
        state_db_path=data_dir / "state.db",
        artifacts_dir=data_dir / "artifacts",
    )
    rig = TestRig(tmp_path=tmp_path, settings=settings)
    if clock is not None:
        rig.clock = clock
    if seed_access:
        rig.db = Database(settings.data_db_path)
        rig.db.migrate()
        access = AccessService(rig.db, jwt_secret=TEST_JWT_SECRET, clock=rig.clock)
        access.seed()
        rig.access = access
    return rig
