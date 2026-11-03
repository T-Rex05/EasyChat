"""候选生成：只调用 skills.propose，不直接写文件或改验证器。"""
from __future__ import annotations

from typing import Callable

from backend.modules.evolution.contracts import ExperienceView
from backend.modules.skills.api import SkillService
from backend.modules.skills.contracts import SOURCE_EVOLUTION, SkillVersionView
from backend.shared.context import Principal


class ProposalService:
    def __init__(self, skills: SkillService) -> None:
        self.skills = skills

    def propose(
        self,
        actor: Principal,
        *,
        name: str,
        content: str,
        parent_version_id: str | None = None,
        source: str = SOURCE_EVOLUTION,
    ) -> SkillVersionView:
        return self.skills.propose(
            actor, name, content, source=source, parent_version_id=parent_version_id,
        )

    def propose_from_experience(
        self,
        actor: Principal,
        experience: ExperienceView,
        *,
        name: str,
        builder: Callable[[ExperienceView], str],
        parent_version_id: str | None = None,
    ) -> SkillVersionView:
        """候选内容由注入 builder 产生；本模块不拼提示词、不调用模型。"""
        content = builder(experience)
        return self.propose(
            actor, name=name, content=content,
            parent_version_id=parent_version_id, source=SOURCE_EVOLUTION,
        )
