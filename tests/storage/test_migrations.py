"""迁移行为测试：幂等、checksum、失败回滚、外键完整性。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.platform.sqlite import (
    Database,
    MigrationError,
    foreign_key_check,
    load_migrations,
    run_migrations,
)


def _db(tmp_path: Path) -> Database:
    return Database(tmp_path / "app.db")


def _make_migration_dir(tmp_path: Path, name: str, sql: str) -> Path:
    mdir = tmp_path / name
    mdir.mkdir()
    return mdir


def test_migrate_twice_idempotent_seed_not_duplicated(tmp_path):
    db = _db(tmp_path)
    first = db.migrate()
    assert "0001" in first
    assert db.ready
    second = db.migrate()
    assert second == []  # 重复迁移不重复执行
    conn = db.connect()
    rows = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
    seed = conn.execute("SELECT count(*) FROM app_settings WHERE key='timezone'").fetchone()[0]
    conn.close()
    assert rows >= 1
    assert seed == 1  # 播种不重复


def test_all_core_tables_present(tmp_path):
    db = _db(tmp_path)
    db.migrate()
    expected = {
        "users", "roles", "role_permissions", "user_permissions", "permission_defs",
        "channel_accounts", "channel_bindings", "channel_events",
        "sessions", "runs", "conversations", "attachments",
        "llm_calls", "daily_user_stats", "model_configs",
        "app_settings", "jobs",
    }
    conn = db.connect()
    actual = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    missing = expected - actual
    assert not missing, f"缺表: {missing}"


def test_run_unique_including_empty_channel_scope(tmp_path):
    """Web 无渠道账号（channel_account_scope=''）的重复提交唯一键有效（架构 §5.2）。"""
    db = _db(tmp_path)
    db.migrate()
    now = "2026-01-01T00:00:00Z"
    with db.transaction() as conn:
        conn.execute("INSERT INTO users(id, username, password, created_at, updated_at) VALUES(1,'u','p',?,?)", (now, now))
        conn.execute(
            "INSERT INTO sessions(id, owner_id, created_at, updated_at) VALUES('s1', 1, ?, ?)", (now, now)
        )
        conn.execute(
            "INSERT INTO runs(id, owner_id, session_id, source, channel_account_scope, client_message_id, created_at) "
            "VALUES('r1',1,'s1','web','','msg-1',?)",
            (now,),
        )
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO runs(id, owner_id, session_id, source, channel_account_scope, client_message_id, created_at) "
            "VALUES('r2',1,'s1','web','','msg-1',?)",
            (now,),
        )


def test_checksum_mismatch_fails(tmp_path):
    db = _db(tmp_path)
    mdir = _make_migration_dir(tmp_path, "migs", "")
    (mdir / "0001_a.sql").write_text("CREATE TABLE t(a INTEGER);\n", encoding="utf-8")
    assert run_migrations(db, migrations_dir=mdir) == ["0001"]
    # 同版本不同内容 → checksum 不一致必须失败
    (mdir / "0001_a.sql").write_text("CREATE TABLE t(a TEXT);\n", encoding="utf-8")
    with pytest.raises(MigrationError):
        run_migrations(db, migrations_dir=mdir)


def test_failed_migration_rolls_back_and_not_ready(tmp_path):
    db = _db(tmp_path)
    mdir = _make_migration_dir(tmp_path, "migrations", "")
    bad_sql = (
        "CREATE TABLE should_rollback(a INTEGER);\n"
        "INSERT INTO should_rollback(a) VALUES(1);\n"
        "THIS IS NOT VALID SQL;\n"
    )
    (mdir / "0001_bad.sql").write_text(bad_sql, encoding="utf-8")
    with pytest.raises(sqlite3.Error):
        run_migrations(db, migrations_dir=mdir)
    # 回滚：表不存在、无登记记录、db 未就绪
    conn = db.connect()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    registered = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
    conn.close()
    assert "should_rollback" not in tables
    assert registered == 0
    assert not db.ready


def test_migrations_applied_in_order(tmp_path):
    db = _db(tmp_path)
    mdir = _make_migration_dir(tmp_path, "migrations", "")
    (mdir / "0002_second.sql").write_text("CREATE TABLE second(a);\n", encoding="utf-8")
    (mdir / "0001_first.sql").write_text("CREATE TABLE first(a);\n", encoding="utf-8")
    applied = run_migrations(db, migrations_dir=mdir)
    assert applied == ["0001", "0002"]
    conn = db.connect()
    versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()]
    conn.close()
    assert versions == ["0001", "0002"]


def test_foreign_key_check_after_migrate(tmp_path):
    db = _db(tmp_path)
    db.migrate()
    assert foreign_key_check(db) == []


def test_load_migrations_sorted_with_versions(tmp_path):
    mdir = tmp_path / "m"
    mdir.mkdir()
    (mdir / "0002_b.sql").write_text("--b", encoding="utf-8")
    (mdir / "0001_a.sql").write_text("--a", encoding="utf-8")
    migs = load_migrations(mdir)
    assert [v for v, _ in migs] == ["0001", "0002"]


def test_lifespan_migration_failure_stops_startup(tmp_path):
    """迁移失败时 run_startup 明确抛错，启动不得继续（架构 §5.4）。"""
    import asyncio

    from backend.bootstrap import ModuleRegistry, run_startup
    from backend.platform.settings import AppSettings

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # 预先写入一个损坏的 schema_migrations checksum
    db = Database(data_dir / "app.db")
    db.migrate()
    conn = db.connect()
    conn.execute("UPDATE schema_migrations SET checksum='tampered'")
    conn.close()
    db.close()

    settings = AppSettings(
        data_db_path=data_dir / "app.db",
        state_db_path=data_dir / "state.db",
        artifacts_dir=data_dir / "artifacts",
    )
    with pytest.raises(MigrationError):
        asyncio.run(run_startup(ModuleRegistry(settings=settings)))
