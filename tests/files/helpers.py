"""files 测试公共设施：真实临时 SQLite + 临时磁盘目录，不触碰仓库 data/。"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from tests.support.rig import TestRig, make_rig


def make_files_rig(
    tmp_path: Path,
    *,
    role: str = "user",
    grants: tuple[str, ...] = (),
    revokes: tuple[str, ...] = (),
    min_free_bytes: int = 0,
) -> tuple[TestRig, object]:
    """返回 (rig, principal)；调用方负责 await rig.aclose()。"""
    rig = make_rig(tmp_path, seed_access=True)
    principal = rig.seed_user(role=role, grants=grants, revokes=revokes)
    rig.attach_files(min_free_bytes=min_free_bytes)
    return rig, principal


def chunks_of(payload: bytes, size: int = 7) -> Iterable[bytes]:
    """分块字节流（验证不把整文件读进内存的处理路径）。"""
    for index in range(0, len(payload), size):
        yield payload[index: index + size]


async def async_chunks_of(payload: bytes, size: int = 7):
    for chunk in chunks_of(payload, size):
        yield chunk
