"""Hermes 技能读写桥接：只调用 skills 模块公开接口。

不导入 backend.hermes 与 skills 内部实现；文件编辑、skill_manage 与后台
review 的写入都转换成版本化提案（propose），激活仍走 compare-and-swap。
"""
from __future__ import annotations

from backend.modules.skills.api import SkillService
from backend.modules.skills.contracts import (
    SOURCE_WEB,
    SkillSnapshot,
    SkillVersionView,
    SkillView,
)
from backend.shared.context import Principal


class SkillsBridge:
    """把固定 Principal 的技能读写委托给 SkillService（快照按 owner 过滤）。"""

    def __init__(self, skills: SkillService, principal: Principal) -> None:
        self.skills = skills
        self.principal = principal

    def list_for_runtime(
        self, principal: Principal | None = None
    ) -> tuple[SkillSnapshot, ...]:
        return self.skills.list_for_runtime(principal or self.principal)

    def propose(
        self,
        name: str,
        content: str,
        *,
        source: str = SOURCE_WEB,
        parent_version_id: str | None = None,
    ) -> SkillVersionView:
        return self.skills.propose(
            self.principal,
            name,
            content,
            source=source,
            parent_version_id=parent_version_id,
        )

    def activate(
        self,
        skill_id: str,
        version_id: str,
        expected_active_version_id: str | None,
    ) -> SkillView:
        return self.skills.activate(
            self.principal, skill_id, version_id, expected_active_version_id,
        )
