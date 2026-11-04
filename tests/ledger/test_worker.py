"""F4/F5：账本解析 worker 的队列语义（认领、完成、损坏文件不无限重试）。"""
from __future__ import annotations

from backend.modules.ledger.api import PARSE_JOB_KIND
from backend.modules.ledger.worker import LedgerWorker
from tests.ledger.helpers import make_ledger_rig, upload_bill
from tests.support.ledger_fixtures import standard_scenario, write_wechat_xlsx


def _jobs(rig):
    conn = rig.db.connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM jobs ORDER BY created_at"
        ).fetchall()]
    finally:
        conn.close()


async def test_register_enqueues_and_worker_parses(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        worker = LedgerWorker(rig.ledger, rig.ledger_queue, worker_id="w1")
        path = write_wechat_xlsx(tmp_path / "bills" / "queued.xlsx", standard_scenario())
        saved = await upload_bill(rig, user, path)
        view = await rig.ledger.register_import(user, saved.file.file_id)
        assert view.state == "saved"
        jobs = _jobs(rig)
        assert len(jobs) == 1 and jobs[0]["kind"] == PARSE_JOB_KIND
        assert jobs[0]["state"] == "pending"

        processed = await worker.tick()
        assert processed == 1
        assert rig.ledger.get_import(user, view.import_id).state == "validated"
        jobs = _jobs(rig)
        assert jobs[0]["state"] == "succeeded"
    finally:
        await rig.aclose()


async def test_tick_without_jobs_is_noop(tmp_path):
    rig, _user = make_ledger_rig(tmp_path)
    try:
        worker = LedgerWorker(rig.ledger, rig.ledger_queue, worker_id="w1")
        assert await worker.tick() == 0
    finally:
        await rig.aclose()


async def test_duplicate_parse_jobs_do_not_duplicate_rows(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        worker = LedgerWorker(rig.ledger, rig.ledger_queue, worker_id="w1")
        path = write_wechat_xlsx(tmp_path / "bills" / "twice.xlsx", standard_scenario())
        saved = await upload_bill(rig, user, path)
        view = await rig.ledger.register_import(user, saved.file.file_id)
        rig.ledger_queue.enqueue(
            kind=PARSE_JOB_KIND, dedup_key=f"parse:{view.import_id}",
            payload={"import_id": view.import_id}, owner_id=user.user_id,
        )
        await worker.tick()
        await worker.tick()
        conn = rig.db.connect()
        try:
            count = conn.execute(
                "SELECT count(*) FROM ledger_source_rows WHERE import_id=?",
                (view.import_id,),
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 4
    finally:
        await rig.aclose()


async def test_corrupt_file_ends_in_failed_state_without_retry(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        from openpyxl import Workbook

        worker = LedgerWorker(rig.ledger, rig.ledger_queue, worker_id="w1")
        workbook = Workbook()
        workbook.active.append(["随便", "一张", "表"])
        corrupt = tmp_path / "no-header.xlsx"
        workbook.save(corrupt)
        saved = await upload_bill(rig, user, corrupt, name="no-header.xlsx")
        view = await rig.ledger.register_import(user, saved.file.file_id)
        await worker.tick()
        refreshed = rig.ledger.get_import(user, view.import_id)
        assert refreshed.state == "failed"
        assert refreshed.error
        jobs = _jobs(rig)
        assert jobs[0]["state"] == "succeeded"
    finally:
        await rig.aclose()


async def test_missing_blob_is_retryable_not_permanent_failure(tmp_path):
    rig, user = make_ledger_rig(tmp_path)
    try:
        worker = LedgerWorker(rig.ledger, rig.ledger_queue, worker_id="w1")
        path = write_wechat_xlsx(tmp_path / "bills" / "gone.xlsx", standard_scenario())
        saved = await upload_bill(rig, user, path)
        view = await rig.ledger.register_import(user, saved.file.file_id)
        # 模拟存储短时不可用：物理文件被外部移走
        rig.files.internal_path(user, saved.file.file_id).unlink()
        await worker.tick()
        refreshed = rig.ledger.get_import(user, view.import_id)
        assert refreshed.state == "saved"
        assert refreshed.error
        jobs = _jobs(rig)
        assert jobs[0]["state"] == "retry_wait"
        assert jobs[0]["attempts"] == 1
    finally:
        await rig.aclose()
