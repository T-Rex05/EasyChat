"""技能版本内容存储：不可变文件、sha256 指纹与越界防护。

写路径只由 `skill_id`/`version_id`（模块生成的 ID）决定，与用户提供的 name
无关；写入先落同目录临时文件，fsync 后用 `os.replace` 原子替换到位。
已存在的版本文件永不覆盖（不可变）。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from pathlib import Path

from backend.modules.skills.contracts import SKILLS_SUBDIR
from backend.platform.settings import default_settings
from backend.shared.errors import (
    ConflictError,
    InvalidInputError,
    StorageUnavailableError,
)
from backend.shared.identifiers import is_valid_id

_SKILL_PREFIX = "skl"
_VERSION_PREFIX = "skv"


def default_content_root() -> Path:
    """默认内容根目录：`settings.artifacts_dir/skills`（构造时不创建目录）。"""
    return Path(default_settings().artifacts_dir) / SKILLS_SUBDIR


class SkillContentStore:
    """技能不可变内容文件的读写入口（不使用用户提供的路径片段）。"""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    # ---- 写入 ------------------------------------------------------------------

    def write(self, *, skill_id: str, version_id: str, content: str) -> tuple[str, str]:
        """写入新版本文件，返回 (相对路径, sha256)。已存在同名版本文件时拒绝。"""
        if not is_valid_id(skill_id, prefix=_SKILL_PREFIX):
            raise InvalidInputError(f"非法的技能ID: {skill_id}")
        if not is_valid_id(version_id, prefix=_VERSION_PREFIX):
            raise InvalidInputError(f"非法的技能版本ID: {version_id}")

        directory = self.root / skill_id
        if directory.is_symlink():
            raise InvalidInputError("技能内容目录不能是符号链接")
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageUnavailableError(f"无法创建技能内容目录: {exc}") from exc
        if not self._inside(directory.resolve()):
            raise InvalidInputError("技能内容目录越界（符号链接或路径穿越）")

        relative = f"{skill_id}/{version_id}.md"
        destination = self.root / relative
        if destination.exists() or destination.is_symlink():
            raise ConflictError(f"版本内容已存在，拒绝覆盖: {relative}")

        payload = content.encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        temp = directory / f".{version_id}.{uuid.uuid4().hex}.tmp"
        try:
            with open(temp, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, destination)
        except OSError as exc:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise StorageUnavailableError(f"写入技能版本内容失败: {exc}") from exc
        return relative, digest

    # ---- 读取 ------------------------------------------------------------------

    def read(self, content_path: str, expected_hash: str) -> str:
        """读取并校验内容指纹；缺失/越界/指纹不符都显式失败。"""
        destination = self._resolve(content_path)
        if destination.is_symlink():
            raise InvalidInputError("技能版本内容不能是符号链接")
        if not destination.is_file():
            raise InvalidInputError(f"技能版本内容文件缺失: {content_path}")
        try:
            payload = destination.read_bytes()
        except OSError as exc:
            raise StorageUnavailableError(f"读取技能版本内容失败: {exc}") from exc
        actual = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(actual, str(expected_hash or "")):
            raise InvalidInputError("技能版本内容指纹不匹配（文件可能被篡改或损坏）")
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidInputError("技能版本内容不是有效的 UTF-8 文本") from exc

    # ---- 内部 ------------------------------------------------------------------

    def _resolve(self, content_path: str) -> Path:
        candidate = Path(str(content_path or ""))
        if not str(content_path or "").strip():
            raise InvalidInputError("技能版本内容路径为空")
        if candidate.is_absolute() or candidate.anchor or candidate.drive:
            raise InvalidInputError("技能版本内容路径必须是相对路径")
        if ".." in candidate.parts:
            raise InvalidInputError("技能版本内容路径不允许包含 '..'")
        destination = self.root / candidate
        try:
            resolved = destination.resolve()
        except OSError as exc:
            raise StorageUnavailableError(f"解析技能内容路径失败: {exc}") from exc
        if not self._inside(resolved):
            raise InvalidInputError("技能版本内容路径越界")
        return destination

    def _inside(self, path: Path) -> bool:
        try:
            path.relative_to(self.root)
        except ValueError:
            return False
        return True
