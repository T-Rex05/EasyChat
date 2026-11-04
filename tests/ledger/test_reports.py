"""F10：账本报告生成（确定性排版 + 落 files + 可下载 + 留痕）。"""
from __future__ import annotations

import pytest

from backend.shared.errors import ForbiddenError, InvalidInputError
from tests.ledger.helpers import import_bill, make_ledger_rig
from tests.support.ledger_fixtures import standard_scenario, write_wechat_xlsx


def _plan():
    return {
        "version": 1, "basis": "consumption_net",
        "metrics": ["expense", "income", "refund_received", "net"],
        "period": {"start": "2026-10-01", "end_exclusive": "2026-11-01"},
        "group_by": ["category"], "output": "pdf",
    }


async def _ready(rig, user, tmp_path):
    path = write_wechat_xlsx(tmp_path / "bills" / "report.xlsx", standard_scenario())
    view, _ = await import_bill(rig, user, path)
    rig.ledger.commit_import(user, view.import_id)
    category = rig.ledger.create_category(user, name="餐饮")
    target = next(t for t in rig.ledger.list_transactions(user) if t.amount_minor == 10000)
    rig.ledger.update_transaction(user, target.transaction_id, category_id=category["id"])


async def test_markdown_report_is_saved_and_downloadable(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        await _ready(rig, user, tmp_path)
        result = await rig.ledger.create_report(user, _plan())
        assert result["mime"].startswith("text/markdown")
        assert result["original_name"].endswith(".md")
        assert result["size_bytes"] > 0
        handle = rig.files.open_read(user, result["file_id"])
        try:
            content = handle.read().decode("utf-8")
        finally:
            handle.close()
        assert "微信账单分析报告" in content
        assert "消费净额" in content
        assert "120.00 CNY" in content  # 100 + 50 - 30 退款
        assert "数据说明" not in content or "覆盖" in content
        stored = rig.ledger.get_analysis(user, result["analysis_id"])
        assert stored["report_file_id"] == result["file_id"]
        assert rig.files.reference_counts(user, result["file_id"]).get("analysis") == 1
    finally:
        await rig.aclose()


async def test_csv_report_contains_details(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        await _ready(rig, user, tmp_path)
        result = await rig.ledger.create_report(
            user, {**_plan(), "output": "table"}, fmt="csv",
        )
        assert result["mime"].startswith("text/csv")
        handle = rig.files.open_read(user, result["file_id"])
        try:
            content = handle.read().decode("utf-8-sig")
        finally:
            handle.close()
        assert "expense" in content
        assert "示例便利店" in content
    finally:
        await rig.aclose()


class FakePdfRenderer:
    capability = "fake"

    def __init__(self):
        self.calls = 0

    async def render(self, html: str, dest, *, timeout: float = 60.0):
        self.calls += 1
        assert "微信账单分析报告" in html
        dest.write_bytes(b"%PDF-1.4 fake")
        return dest


async def test_pdf_report_uses_renderer_and_is_saved(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        await _ready(rig, user, tmp_path)
        renderer = FakePdfRenderer()
        rig.ledger.pdf = renderer
        result = await rig.ledger.create_report(user, _plan(), fmt="pdf")
        assert renderer.calls == 1
        assert result["mime"] == "application/pdf"
        assert result["original_name"].endswith(".pdf")
        handle = rig.files.open_read(user, result["file_id"])
        try:
            assert handle.read().startswith(b"%PDF-1.4")
        finally:
            handle.close()
    finally:
        await rig.aclose()


async def test_pdf_without_renderer_is_explicit_error(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        await _ready(rig, user, tmp_path)
        with pytest.raises(InvalidInputError, match="PDF 导出未启用"):
            await rig.ledger.create_report(user, _plan(), fmt="pdf")
    finally:
        await rig.aclose()


async def test_report_rejects_unsupported_format_and_requires_export(tmp_path):
    rig, user = make_ledger_rig(tmp_path, role="admin")
    try:
        await _ready(rig, user, tmp_path)
        with pytest.raises(InvalidInputError):
            await rig.ledger.create_report(user, _plan(), fmt="docx")
    finally:
        await rig.aclose()

    rig2, user2 = make_ledger_rig(tmp_path / "denied", revokes=("ledger.export",))
    try:
        with pytest.raises(ForbiddenError):
            await rig2.ledger.create_report(user2, _plan())
    finally:
        await rig2.aclose()
