"""skills 模块数据访问：技能元数据、不可变版本与激活指针（架构 §5.2/§5.3）。

只有本模块写 skills/skill_versions；激活指针用条件更新（compare-and-swap）。
"""
from __future__ import annotations

import sqlite3
from typing import Any

from backend.modules.skills.contracts import (
    VERSION_ACTIVE,
    VERSION_VALIDATED,
    SkillVersionView,
    SkillView,
)
from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import ConflictError, NotFoundError
from backend.shared.identifiers import new_skill_id


def _skill(row: Any) -> SkillView:
    d = dict(row)
    return SkillView(
        skill_id=str(d["id"]),
        owner_id=int(d["owner_id"]),
        name=str(d["name"]),
        description=str(d["description"] or ""),
        origin=str(d["origin"]),
        pinned=bool(d["pinned"]),
        archived=bool(d["archived"]),
        active_version_id=(
            str(d["active_version_id"]) if d.get("active_version_id") else None
        ),
        created_at=str(d["created_at"]),
        updated_at=str(d["updated_at"]),
    )


def _version(row: Any) -> SkillVersionView:
    d = dict(row)
    return SkillVersionView(
        version_id=str(d["id"]),
        skill_id=str(d["skill_id"]),
        version_seq=int(d["version_seq"]),
        content_path=str(d["content_path"]),
        content_hash=str(d["content_hash"]),
        parent_version_id=(
            str(d["parent_version_id"]) if d.get("parent_version_id") else None
        ),
        source=str(d["source"]),
        status=str(d["status"]),
        created_at=str(d["created_at"]),
    )


class SkillRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- 技能 ------------------------------------------------------------------

    def get_skill(self, skill_id: str) -> SkillView:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise NotFoundError(f"技能不存在: {skill_id}")
        return _skill(row)

    def find_skill(self, owner_id: int, name: str) -> SkillView | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM skills WHERE owner_id=? AND name=?", (owner_id, name)
            ).fetchone()
        finally:
            conn.close()
        return _skill(row) if row else None

    def ensure_skill(
        self, *, owner_id: int, name: str, origin: str, description: str = ""
    ) -> SkillView:
        """按 (owner, name) 取已有技能，缺失则创建；不覆盖已有 origin/description。"""
        skill_id = new_skill_id()
        now = utc_now_iso()
        try:
            with self.db.transaction() as conn:
                row = conn.execute(
                    "SELECT * FROM skills WHERE owner_id=? AND name=?", (owner_id, name)
                ).fetchone()
                if row is not None:
                    return _skill(row)
                conn.execute(
                    "INSERT INTO skills(id, owner_id, name, description, origin, pinned, "
                    "archived, active_version_id, created_at, updated_at) "
                    "VALUES(?,?,?,?,?,0,0,NULL,?,?)",
                    (skill_id, owner_id, name, description, origin, now, now),
                )
                return SkillView(
                    skill_id=skill_id, owner_id=owner_id, name=name,
                    description=description, origin=origin, pinned=False, archived=False,
                    active_version_id=None, created_at=now, updated_at=now,
                )
        except sqlite3.IntegrityError as exc:  # 并发/唯一键兜底
            raise ConflictError(f"同名技能已存在: {name}") from exc

    def set_pinned(self, skill_id: str, pinned: bool) -> SkillView:
        return self._set_flag(skill_id, "pinned", pinned)

    def set_archived(self, skill_id: str, archived: bool) -> SkillView:
        return self._set_flag(skill_id, "archived", archived)

    def _set_flag(self, skill_id: str, column: str, value: bool) -> SkillView:
        with self.db.transaction() as conn:
            cur = conn.execute(
                f"UPDATE skills SET {column}=?, updated_at=? WHERE id=?",
                (1 if value else 0, utc_now_iso(), skill_id),
            )
            if cur.rowcount != 1:
                raise NotFoundError(f"技能不存在: {skill_id}")
        return self.get_skill(skill_id)

    def list_by_owner(
        self, owner_id: int, *, include_archived: bool = False
    ) -> list[SkillView]:
        sql = "SELECT * FROM skills WHERE owner_id=?"
        if not include_archived:
            sql += " AND archived=0"
        sql += " ORDER BY pinned DESC, updated_at DESC"
        conn = self.db.connect()
        try:
            rows = conn.execute(sql, (owner_id,)).fetchall()
        finally:
            conn.close()
        return [_skill(r) for r in rows]

    def list_all(self, *, include_archived: bool = True) -> list[SkillView]:
        sql = "SELECT * FROM skills"
        if not include_archived:
            sql += " WHERE archived=0"
        sql += " ORDER BY updated_at DESC"
        conn = self.db.connect()
        try:
            rows = conn.execute(sql).fetchall()
        finally:
            conn.close()
        return [_skill(r) for r in rows]

    # ---- 版本 ------------------------------------------------------------------

    def create_version(
        self,
        *,
        version_id: str,
        skill_id: str,
        content_path: str,
        content_hash: str,
        parent_version_id: str | None,
        source: str,
        status: str,
    ) -> SkillVersionView:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version_seq), 0) + 1 AS seq "
                "FROM skill_versions WHERE skill_id=?",
                (skill_id,),
            ).fetchone()
            seq = int(row["seq"])
            conn.execute(
                "INSERT INTO skill_versions(id, skill_id, version_seq, content_path, "
                "content_hash, parent_version_id, source, status, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (version_id, skill_id, seq, content_path, content_hash,
                 parent_version_id, source, status, now),
            )
        return SkillVersionView(
            version_id=version_id, skill_id=skill_id, version_seq=seq,
            content_path=content_path, content_hash=content_hash,
            parent_version_id=parent_version_id, source=source, status=status,
            created_at=now,
        )

    def get_version(self, version_id: str) -> SkillVersionView:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM skill_versions WHERE id=?", (version_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise NotFoundError(f"技能版本不存在: {version_id}")
        return _version(row)

    def list_versions(self, skill_id: str) -> list[SkillVersionView]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM skill_versions WHERE skill_id=? ORDER BY version_seq",
                (skill_id,),
            ).fetchall()
        finally:
            conn.close()
        return [_version(r) for r in rows]

    def compare_and_swap_active(
        self,
        *,
        skill_id: str,
        owner_id: int,
        version_id: str,
        expected_active_version_id: str | None,
    ) -> bool:
        """条件切换激活指针；0 行表示指针已变化（并发失败），旧指针不变。"""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE skills SET active_version_id=?, updated_at=? "
                "WHERE id=? AND owner_id=? AND active_version_id IS ?",
                (version_id, now, skill_id, owner_id, expected_active_version_id),
            )
            if cur.rowcount != 1:
                return False
            if expected_active_version_id:
                conn.execute(
                    "UPDATE skill_versions SET status=? "
                    "WHERE id=? AND skill_id=? AND status=?",
                    (VERSION_VALIDATED, expected_active_version_id, skill_id, VERSION_ACTIVE),
                )
            conn.execute(
                "UPDATE skill_versions SET status=? WHERE id=? AND skill_id=?",
                (VERSION_ACTIVE, version_id, skill_id),
            )
            return True
