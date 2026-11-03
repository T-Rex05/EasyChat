"""skills 测试辅助：真实临时 SQLite + 独立临时内容根目录（不写仓库 data/）。"""
from __future__ import annotations

import uuid
from pathlib import Path

from backend.modules.skills.api import SkillService
from tests.support.rig import TestRig, make_rig


def make_skill_rig(tmp_path: Path) -> tuple[TestRig, SkillService, Path]:
    rig = make_rig(tmp_path, seed_access=True)
    root = rig.settings.artifacts_dir / "skills"
    service = SkillService(rig.db, access=rig.access, content_root=root)
    return rig, service, root


def new_service(rig: TestRig, root: Path) -> SkillService:
    """模拟进程重启：同一 DB/同一内容根目录重新构造模块。"""
    return SkillService(rig.db, access=rig.access, content_root=root)


def make_user(
    rig: TestRig,
    *,
    role: str = "user",
    grants: tuple[str, ...] = (),
    revokes: tuple[str, ...] = (),
    tag: str = "skill",
):
    return rig.seed_user(
        role=role,
        grants=grants,
        revokes=revokes,
        username=f"{tag}_{uuid.uuid4().hex[:8]}",
    )


def version_file(root: Path, version) -> Path:
    return Path(root) / version.content_path
