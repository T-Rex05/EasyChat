"""报告/PDF 测试（Task 14）：能力关闭明确失败、artifact 不可变、附件投递不重渲染。"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from backend.integrations.pdf import DisabledPdfRenderer, build_pdf_renderer
from backend.modules.delivery.api import DeliveryService
from backend.modules.delivery.contracts import DELIVERY_SENT, DeliveryTarget
from backend.modules.delivery.reports import ReportService
from backend.modules.delivery.worker import DeliveryWorker
from backend.platform.settings import default_settings
from backend.shared.errors import CapabilityUnavailableError
from tests.support.delivery import FakeSender
from tests.support.rig import FakeClock, make_rig


class FakeRenderer:
    capability = "fake"

    def __init__(self) -> None:
        self.calls = 0

    async def render(self, html: str, dest: Path, *, timeout: float = 60.0) -> Path:
        self.calls += 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF-1.4 " + html.encode("utf-8")[:20])
        return dest


class TimeoutRenderer:
    capability = "timeout"

    async def render(self, html: str, dest: Path, *, timeout: float = 60.0) -> Path:
        raise CapabilityUnavailableError("PDF 渲染超时，已终止渲染进程")


@pytest.fixture
def env(tmp_path):
    clock = FakeClock(1_000_000.0)
    rig = make_rig(tmp_path, clock=clock, seed_access=True)
    sender = FakeSender()
    delivery = DeliveryService(rig.db, sender=sender, clock=clock)
    renderer = FakeRenderer()
    reports = ReportService(
        delivery=delivery, renderer=renderer, artifacts_dir=rig.settings.artifacts_dir,
    )
    user = rig.seed_user(role="user", username=f"rep_{uuid.uuid4().hex[:6]}")
    yield rig, delivery, reports, sender, renderer, user
    rig.db.close()


async def test_pdf_artifact_then_email_delivery_without_rerender(env):
    rig, delivery, reports, sender, renderer, user = env
    artifact_id = await reports.create_pdf_artifact(
        owner_id=user.user_id, html="<h1>日报</h1>", title="日报",
    )
    artifact = delivery.repo.get_artifact(artifact_id)
    assert Path(artifact["file_path"]).is_file()
    assert artifact["kind"] == "report"
    assert artifact["mime"] == "application/pdf"

    target = DeliveryTarget(kind="email", ref="boss@example.com")
    delivery_id = reports.enqueue_email_report(
        owner_id=user.user_id, target=target, artifact_id=artifact_id,
        subject="每日报告", body="见附件",
    )
    await DeliveryWorker(delivery).tick()
    assert delivery.status(user.user_id, delivery_id).status == DELIVERY_SENT
    assert sender.artifacts[0]["subject"] == "每日报告"
    assert Path(artifact["file_path"]).is_file()  # 投递后不删被引用产物
    assert renderer.calls == 1  # 投递失败/重试也不会重新渲染


async def test_disabled_pdf_fails_explicitly_without_artifact(env):
    rig, delivery, _, _, _, user = env
    disabled = ReportService(
        delivery=delivery, renderer=DisabledPdfRenderer(),
        artifacts_dir=rig.settings.artifacts_dir,
    )
    with pytest.raises(CapabilityUnavailableError):
        await disabled.create_pdf_artifact(owner_id=user.user_id, html="<p>x</p>", title="x")
    conn = rig.db.connect()
    try:
        assert conn.execute("SELECT count(*) AS c FROM artifacts").fetchone()["c"] == 0
    finally:
        conn.close()


async def test_render_timeout_fails_explicitly(env):
    rig, delivery, _, _, _, user = env
    service = ReportService(
        delivery=delivery, renderer=TimeoutRenderer(),
        artifacts_dir=rig.settings.artifacts_dir,
    )
    with pytest.raises(CapabilityUnavailableError):
        await service.create_pdf_artifact(owner_id=user.user_id, html="<p>x</p>", title="x")


def test_pdf_capability_checks_are_lazy():
    disabled = build_pdf_renderer(default_settings())
    assert isinstance(disabled, DisabledPdfRenderer)
    assert disabled.capability == "disabled"
