"""0014+ 增量迁移：空库、0013 升级、字段/索引存在、旧 checksum 不变。"""
from __future__ import annotations

import shutil
from pathlib import Path

from backend.platform import sqlite as sqlite_module
from backend.platform.sqlite import Database


OLD_VERSIONS = ("0012", "0013")
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "backend" / "platform" / "migrations"


def _columns(db: Database, table: str) -> set[str]:
    conn = db.connect()
    try:
        return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _checksums(db: Database) -> dict[str, str]:
    conn = db.connect()
    try:
        return {
            str(row["version"]): str(row["checksum"])
            for row in conn.execute("SELECT version, checksum FROM schema_migrations")
        }
    finally:
        conn.close()


def test_fresh_database_reaches_0014_with_new_schema(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    applied = db.migrate()
    assert "0014" in applied
    assert "0015" in applied
    assert "0016" in applied
    assert "0017" in applied
    assert db.ready

    conn = db.connect()
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        indexes = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    finally:
        conn.close()

    assert {
        "assistant_profiles", "inbox_items", "mood_entries", "mood_samples",
        "mood_care_log",
    } <= tables
    assert "idx_inbox_owner_status" in indexes
    assert "uq_inbox_owner_url" in indexes
    assert "idx_mood_care_owner_time" in indexes
    assert {"weekday", "content_kind", "briefing_kind"} <= _columns(db, "scheduled_jobs")
    assert "job_id" in _columns(db, "scheduled_occurrences")
    assert {
        "owner_id",
        "persona_preset",
        "quiet_start",
        "quiet_end",
        "timezone",
        "mood_opt_in",
        "mood_retention_days",
        "proactivity",
        "last_care_at",
        "care_epoch_at",
    } <= _columns(db, "assistant_profiles")


def test_0013_database_upgrades_without_rewriting_old_checksums(tmp_path: Path) -> None:
    """构造真实的仅含 0001–0013 的库，再升级到当前增量。"""
    old_dir = tmp_path / "migrations_0013"
    old_dir.mkdir()
    for source in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if source.name < "0014":
            shutil.copy2(source, old_dir / source.name)

    db = Database(tmp_path / "app.db")
    assert sqlite_module.run_migrations(db, migrations_dir=old_dir)[-1] == "0013"
    before = _checksums(db)
    assert "0014" not in before

    applied = db.migrate()
    assert applied == [f"{number:04d}" for number in range(14, 30)]
    after = _checksums(db)
    assert {version: after[version] for version in before} == before
    assert all(after[version] for version in applied)


def test_0026_memory_upgrade_keeps_active_rows_and_scrubs_tombstones(tmp_path: Path) -> None:
    old_dir = tmp_path / "migrations_0026"
    old_dir.mkdir()
    for source in MIGRATIONS_DIR.glob("*.sql"):
        if source.name[:4] <= "0026":
            shutil.copy2(source, old_dir / source.name)

    db = Database(tmp_path / "old-app.db")
    assert sqlite_module.run_migrations(db, migrations_dir=old_dir)[-1] == "0026"
    now = "2026-01-01T00:00:00Z"
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password, created_at, updated_at) VALUES(1,'u','p',?,?)",
            (now, now),
        )
        conn.executemany(
            "INSERT INTO memories(id, owner_id, kind, status, version, content, source_refs, "
            "recorded_at, created_at, updated_at) VALUES(?,1,'fact',?,?,?,?,?,?,?)",
            (
                ("mem_aaaa", "active", 3, "仍在使用", "[]", now, now, now),
                ("mem_bbbb", "deleted", 2, "", '[{"kind":"message","ref":"run_a","quote":"遗忘原文"}]',
                 now, now, now),
            ),
        )
        conn.execute("INSERT INTO memory_tags(memory_id, tag) VALUES('mem_bbbb','遗忘标签')")
        conn.execute(
            "INSERT INTO memory_revisions(id, memory_id, version, content, created_at) "
            "VALUES('revision_1','mem_bbbb',1,'遗忘前版本',?)", (now,),
        )

    assert db.migrate() == ["0027", "0028", "0029"]
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id, status, version, content, source_refs, persona_id, is_shared FROM memories ORDER BY id",
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("mem_aaaa", "active", 3, "仍在使用", "[]", None, 0),
            ("mem_bbbb", "deleted", 2, "", "[]", None, 0),
        ]
        assert conn.execute("SELECT count(*) FROM memory_tags").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM memory_revisions").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_partial_url_unique_index_allows_multiple_empty_urls(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.migrate()
    now = "2026-01-01T00:00:00Z"
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password, created_at, updated_at) "
            "VALUES(1,'u','p',?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO inbox_items(id, owner_id, kind, url, created_at, updated_at) "
            "VALUES('i1',1,'note','',?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO inbox_items(id, owner_id, kind, url, created_at, updated_at) "
            "VALUES('i2',1,'note','',?,?)",
            (now, now),
        )
    assert db.ready


def test_old_migration_files_unchanged_checksums(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.migrate()
    checksums = _checksums(db)
    for version in OLD_VERSIONS:
        assert checksums[version]
