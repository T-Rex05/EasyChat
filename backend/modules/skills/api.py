"""skills 模块公开接口：提出候选版本、激活/回滚、pin/归档与运行时快照。

规则（架构 §9、Task 10）：
- 技能内容按版本不可变；文件先写、元数据后入库，中断只留孤立文件；
- 激活用 expected_active_version 比较交换，失败不覆盖旧指针；
- 读取固定版本快照（内容+hash）并校验指纹，缺失/篡改显式失败；
- 有效列表只按 owner 过滤，不用 owner_id=1 猜公共归属。
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.modules.skills.contracts import (
    AUTOMATED_SOURCES,
    MAX_CONTENT_BYTES,
    MAX_NAME_LENGTH,
    SOURCE_WEB,
    VALID_SOURCES,
    VERSION_DRAFT,
    VERSION_REJECTED,
    VERSION_VALIDATED,
    SkillSnapshot,
    SkillVersionView,
    SkillView,
)
from backend.modules.skills.repository import SkillRepository
from backend.modules.skills.versions import SkillContentStore, default_content_root
from backend.platform.sqlite import Database
from backend.shared.context import Principal
from backend.shared.errors import (
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    StorageUnavailableError,
)
from backend.shared.identifiers import new_skill_version_id

_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")


def validate_skill_name(name: str) -> str:
    """技能名只用于展示/唯一键，不参与路径；仍拒绝分隔符与路径穿越。"""
    if not isinstance(name, str) or not name:
        raise InvalidInputError("技能名称不能为空")
    if len(name) > MAX_NAME_LENGTH or not _NAME_RE.match(name):
        raise InvalidInputError(
            "技能名称不合法：仅允许字母、数字、点、下划线、连字符，长度 1-64"
        )
    if name in {".", ".."} or ".." in name:
        raise InvalidInputError("技能名称不允许路径穿越片段")
    return name


def validate_content(content: str) -> str:
    if not isinstance(content, str) or not content.strip():
        raise InvalidInputError("技能内容不能为空")
    if len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
        raise InvalidInputError(f"技能内容超过上限 {MAX_CONTENT_BYTES} 字节")
    return content


def validate_source(source: str) -> str:
    if source not in VALID_SOURCES:
        raise InvalidInputError(f"未知技能来源: {source}")
    return source


class SkillService:
    """技能资产的唯一写入口；跨模块只通过本类公开方法访问。"""

    def __init__(
        self,
        db: Database,
        *,
        access,
        content_root: Path | str | None = None,
    ) -> None:
        self.db = db
        self.repo = SkillRepository(db)
        self.access = access
        self.store = SkillContentStore(content_root or default_content_root())

    @property
    def content_root(self) -> Path:
        return self.store.root

    # ---- 权限 ------------------------------------------------------------------

    def _principal(self, actor: Principal) -> Principal:
        return self.access.validate_principal(actor)

    def _can(self, principal: Principal, permission: str) -> bool:
        return self.access.has_permission(principal, permission)

    def _require_write(self, principal: Principal, skill: SkillView) -> None:
        if skill.owner_id == principal.user_id:
            if not (self._can(principal, "skill.create")
                    or self._can(principal, "skill.manage")):
                raise ForbiddenError("缺少权限: skill.create")
            return
        if not self._can(principal, "skill.manage"):
            raise ForbiddenError("无权操作其他用户的技能")

    def _require_view(self, principal: Principal, skill: SkillView) -> None:
        if skill.owner_id != principal.user_id and not self._can(principal, "skill.manage"):
            raise ForbiddenError("无权访问该技能")

    # ---- 候选版本 ----------------------------------------------------------------

    def propose(
        self,
        actor: Principal,
        name: str,
        content: str,
        *,
        source: str = SOURCE_WEB,
        parent_version_id: str | None = None,
    ) -> SkillVersionView:
        """提出候选版本：文件先写不可变路径，再提交元数据。

        `source=background/evolution` 时不得修改 pinned 技能；用户显式写入
        （user/web）不受 pin 限制。跨 owner 只有 skill.manage 可以操作。
        """
        principal = self._principal(actor)
        validate_skill_name(name)
        validate_content(content)
        validate_source(source)
        if not (self._can(principal, "skill.create")
                or self._can(principal, "skill.manage")):
            raise ForbiddenError("缺少权限: skill.create")

        skill = self.repo.find_skill(principal.user_id, name)
        if skill is not None:
            self._require_write(principal, skill)
            if source in AUTOMATED_SOURCES and skill.pinned:
                raise ForbiddenError("已固定（pin）的技能不接受后台/进化写入")
        else:
            skill = self.repo.ensure_skill(
                owner_id=principal.user_id, name=name, origin=source,
            )

        if parent_version_id:
            parent = self.repo.get_version(parent_version_id)
            if parent.skill_id != skill.skill_id:
                raise InvalidInputError("父版本不属于该技能")
            parent_version_id = parent.version_id

        version_id = new_skill_version_id()
        content_path, content_hash = self.store.write(
            skill_id=skill.skill_id, version_id=version_id, content=content,
        )
        # 文件已落盘，元数据插入失败只会留下孤立文件（延迟清理），不覆盖有效文件。
        status = VERSION_DRAFT if source in AUTOMATED_SOURCES else VERSION_VALIDATED
        return self.repo.create_version(
            version_id=version_id,
            skill_id=skill.skill_id,
            content_path=content_path,
            content_hash=content_hash,
            parent_version_id=parent_version_id,
            source=source,
            status=status,
        )

    # ---- 激活 / 回滚 -------------------------------------------------------------

    def activate(
        self,
        actor: Principal,
        skill_id: str,
        version_id: str,
        expected_active_version_id: str | None,
    ) -> SkillView:
        """条件切换激活指针；校验版本归属与内容指纹后才 compare-and-swap。"""
        principal = self._principal(actor)
        skill = self.repo.get_skill(skill_id)
        self._require_write(principal, skill)
        version = self.repo.get_version(version_id)
        if version.skill_id != skill.skill_id:
            raise InvalidInputError("版本不属于该技能")
        if version.status == VERSION_REJECTED:
            raise ConflictError("被拒绝的版本不能激活")
        # 先校验文件存在且指纹一致：坏版本不得破坏旧 active 指针
        self._read_version_text(version)
        activated = self.repo.compare_and_swap_active(
            skill_id=skill_id,
            owner_id=skill.owner_id,
            version_id=version.version_id,
            expected_active_version_id=expected_active_version_id,
        )
        if not activated:
            raise ConflictError(
                f"技能激活指针已变化（期望 {expected_active_version_id or '无'}）"
            )
        return self.repo.get_skill(skill_id)

    def rollback(
        self, actor: Principal, skill_id: str, target_version_id: str
    ) -> SkillView:
        """回退到目标版本：以读取到的当前 active 作为比较交换的期望值。"""
        principal = self._principal(actor)
        skill = self.repo.get_skill(skill_id)
        self._require_write(principal, skill)
        return self.activate(
            principal, skill_id, target_version_id, skill.active_version_id,
        )

    # ---- pin / 归档 --------------------------------------------------------------

    def set_pinned(self, actor: Principal, skill_id: str, pinned: bool) -> SkillView:
        principal = self._principal(actor)
        skill = self.repo.get_skill(skill_id)
        if skill.owner_id != principal.user_id and not self._can(principal, "skill.manage"):
            raise ForbiddenError("只有所有者或有 skill.manage 权限者可以设置 pin")
        return self.repo.set_pinned(skill_id, bool(pinned))

    def set_archived(self, actor: Principal, skill_id: str, archived: bool) -> SkillView:
        principal = self._principal(actor)
        skill = self.repo.get_skill(skill_id)
        if skill.owner_id != principal.user_id and not self._can(principal, "skill.manage"):
            raise ForbiddenError("只有所有者或有 skill.manage 权限者可以归档技能")
        return self.repo.set_archived(skill_id, bool(archived))

    def archive(self, actor: Principal, skill_id: str) -> SkillView:
        return self.set_archived(actor, skill_id, True)

    def unarchive(self, actor: Principal, skill_id: str) -> SkillView:
        return self.set_archived(actor, skill_id, False)

    # ---- 读取 ------------------------------------------------------------------

    def list(
        self,
        actor: Principal,
        *,
        include_archived: bool = False,
        all_owners: bool = False,
    ) -> tuple[SkillView, ...]:
        principal = self._principal(actor)
        if all_owners:
            if not self._can(principal, "skill.manage"):
                raise ForbiddenError("缺少权限: skill.manage")
            return tuple(self.repo.list_all(include_archived=include_archived))
        return tuple(
            self.repo.list_by_owner(
                principal.user_id, include_archived=include_archived,
            )
        )

    def get(self, actor: Principal, skill_id: str) -> SkillView:
        principal = self._principal(actor)
        skill = self.repo.get_skill(skill_id)
        self._require_view(principal, skill)
        return skill

    def list_versions(self, actor: Principal, skill_id: str) -> tuple[SkillVersionView, ...]:
        principal = self._principal(actor)
        skill = self.repo.get_skill(skill_id)
        self._require_view(principal, skill)
        return tuple(self.repo.list_versions(skill_id))

    def read_active_content(self, actor: Principal, skill_id: str) -> str:
        """读取当前激活版本内容；文件缺失/指纹不符显式失败。"""
        principal = self._principal(actor)
        skill = self.repo.get_skill(skill_id)
        self._require_view(principal, skill)
        return self._read_version_text(self._active_version(skill))

    def list_for_runtime(self, actor: Principal) -> tuple[SkillSnapshot, ...]:
        """运行时有效技能：只含 owner 自己的未归档技能，固定版本+内容快照。"""
        principal = self._principal(actor)
        snapshots: list[SkillSnapshot] = []
        for skill in self.repo.list_by_owner(principal.user_id, include_archived=False):
            if not skill.active_version_id:
                continue
            version = self.repo.get_version(skill.active_version_id)
            if version.skill_id != skill.skill_id:
                raise StorageUnavailableError("技能激活指针指向其他技能的版本")
            snapshots.append(
                SkillSnapshot(
                    skill_id=skill.skill_id,
                    owner_id=skill.owner_id,
                    name=skill.name,
                    description=skill.description,
                    version_id=version.version_id,
                    version_seq=version.version_seq,
                    content_hash=version.content_hash,
                    content=self._read_version_text(version),
                )
            )
        return tuple(snapshots)

    # ---- 内部 ------------------------------------------------------------------

    def _active_version(self, skill: SkillView) -> SkillVersionView:
        if not skill.active_version_id:
            raise ConflictError("技能没有激活版本")
        version = self.repo.get_version(skill.active_version_id)
        if version.skill_id != skill.skill_id:
            raise StorageUnavailableError("技能激活指针指向其他技能的版本")
        return version

    def _read_version_text(self, version: SkillVersionView) -> str:
        return self.store.read(version.content_path, version.content_hash)
