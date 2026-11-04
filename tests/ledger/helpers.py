"""账本测试夹具：真实临时 SQLite + 临时文件根 + 合成账单。"""
from __future__ import annotations

from pathlib import Path

from tests.support.rig import TestRig, make_rig


def make_ledger_rig(
    tmp_path: Path, *, role: str = "user", grants: tuple[str, ...] = (),
    revokes: tuple[str, ...] = (), queue: bool = True,
) -> tuple[TestRig, object]:
    """装配 files + ledger；默认授予 user 的账本权限（admin 全量）。"""
    rig = make_rig(tmp_path, seed_access=True)
    rig.attach_files()
    rig.attach_ledger(queue=queue)
    principal = rig.seed_user(role=role, grants=grants, revokes=revokes)
    return rig, principal


async def upload_bill(rig: TestRig, principal, path: Path, *, name: str | None = None):
    """把合成账单登记为受管文件（模拟 Web 上传）。"""
    from backend.modules.files.contracts import SaveMetadata

    data = path.read_bytes()
    return await rig.files.save_stream(
        principal, [data],
        SaveMetadata(original_name=name or path.name, declared_mime="", source="web"),
    )


async def import_bill(rig: TestRig, principal, path: Path, *, name: str | None = None, parse: bool = True):
    """上传 + 登记导入 + 可选立即解析；返回 (import_view, file_result)。"""
    saved = await upload_bill(rig, principal, path, name=name)
    view = await rig.ledger.register_import(
        principal, saved.file.file_id, parse_now=parse,
    )
    return view, saved
