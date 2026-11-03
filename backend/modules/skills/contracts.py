"""skills 模块公开契约（架构 §9、Task 10）。

只暴露值对象；数据库行/游标、文件句柄和 Hermes 对象不出现在公开接口。
版本内容不可变，激活指针由 DB 条件更新维护。
"""
from __future__ import annotations

from dataclasses import dataclass

# ---- 来源 / 归属 --------------------------------------------------------------

SOURCE_USER = "user"
SOURCE_WEB = "web"
SOURCE_BACKGROUND = "background"
SOURCE_EVOLUTION = "evolution"
VALID_SOURCES: frozenset[str] = frozenset(
    {SOURCE_USER, SOURCE_WEB, SOURCE_BACKGROUND, SOURCE_EVOLUTION}
)
# 后台自动写入受 pin 保护（用户显式写入不受限制）
AUTOMATED_SOURCES: frozenset[str] = frozenset({SOURCE_BACKGROUND, SOURCE_EVOLUTION})

ORIGIN_USER = "user"
ORIGIN_WEB = "web"
ORIGIN_BACKGROUND = "background"
ORIGIN_EVOLUTION = "evolution"
VALID_ORIGINS: frozenset[str] = VALID_SOURCES

# ---- 版本状态 ------------------------------------------------------------------

VERSION_DRAFT = "draft"
VERSION_VALIDATED = "validated"
VERSION_REJECTED = "rejected"
VERSION_ACTIVE = "active"
VERSION_SUPERSEDED = "superseded"
VALID_VERSION_STATUSES: frozenset[str] = frozenset(
    {VERSION_DRAFT, VERSION_VALIDATED, VERSION_REJECTED, VERSION_ACTIVE, VERSION_SUPERSEDED}
)

# ---- 限制 ----------------------------------------------------------------------

MAX_NAME_LENGTH = 64
MAX_CONTENT_BYTES = 200 * 1024
SKILLS_SUBDIR = "skills"


@dataclass(frozen=True, slots=True)
class SkillVersionView:
    """版本元数据视图；content_path 只由模块内部生成（相对内容根目录）。"""

    version_id: str
    skill_id: str
    version_seq: int
    content_path: str
    content_hash: str
    parent_version_id: str | None
    source: str
    status: str
    created_at: str


@dataclass(frozen=True, slots=True)
class SkillView:
    skill_id: str
    owner_id: int
    name: str
    description: str
    origin: str
    pinned: bool
    archived: bool
    active_version_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class SkillSnapshot:
    """运行时固定版本快照：更新只影响下一轮，不改变已注入内容。"""

    skill_id: str
    owner_id: int
    name: str
    description: str
    version_id: str
    version_seq: int
    content_hash: str
    content: str
