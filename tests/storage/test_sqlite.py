"""platform.sqlite 行为测试：真实临时SQLite，不mock SQL逻辑。"""
from __future__ import annotations

import sqlite3
import threading

import pytest

from backend.platform.sqlite import Database, foreign_key_check
from backend.shared.errors import StorageUnavailableError


def test_connect_fresh_per_call_with_pragmas(tmp_path):
    db = Database(tmp_path / "app.db")
    c1 = db.connect()
    c2 = db.connect()
    assert c1 is not c2  # 每次操作独立连接，不跨线程共享
    assert c1.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert c1.execute("PRAGMA busy_timeout").fetchone()[0] == db.busy_timeout_ms
    c1.execute("CREATE TABLE t(x)")
    c1.close()
    c2.execute("SELECT count(*) FROM t").fetchone()  # 同库可见（WAL/共享文件级）
    c2.close()


def test_journal_mode_follows_wal_safety_rule(tmp_path):
    """journal 模式遵循 Hermes 的 WAL-reset bug 版本规则（架构 §5.4 实测要求）。

    本机 SQLite 3.45.3 在易损区间 → 新库回退 DELETE；修复版本 → WAL。
    """
    import sqlite3 as sq

    from backend.platform.sqlite import _wal_safe_version

    db = Database(tmp_path / "app.db")
    db.migrate()
    expected = "wal" if _wal_safe_version(sq.sqlite_version_info) else "delete"
    assert db.journal_mode == expected
    check = Database(tmp_path / "app.db").connect()
    assert check.execute("PRAGMA journal_mode").fetchone()[0] == expected
    check.close()


def test_wal_safe_version_boundaries():
    from backend.platform.sqlite import _wal_safe_version

    assert _wal_safe_version((3, 51, 3)) is True
    assert _wal_safe_version((3, 51, 2)) is False
    assert _wal_safe_version((3, 50, 7)) is True
    assert _wal_safe_version((3, 50, 6)) is False
    assert _wal_safe_version((3, 44, 6)) is True
    assert _wal_safe_version((3, 45, 3)) is False
    assert _wal_safe_version((3, 52, 0)) is True


def test_foreign_keys_enforced(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    conn = db.connect()
    now = "2026-01-01T00:00:00Z"
    conn.execute(
        "INSERT INTO roles(id, name, created_at, updated_at) VALUES(1,'r',?,?)", (now, now)
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users(id, username, password, role_id, created_at, updated_at) "
            "VALUES(1,'u','x', 999, ?, ?)",
            (now, now),
        )
    conn.close()


def test_transaction_commit_and_rollback(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO app_settings(key, value, updated_at) VALUES('k1','v1','now')"
        )
    with pytest.raises(RuntimeError), db.transaction() as conn:
        conn.execute("INSERT INTO app_settings(key, value, updated_at) VALUES('k2','v2','now')")
        raise RuntimeError("触发回滚")
    conn = db.connect()
    keys = {r[0] for r in conn.execute("SELECT key FROM app_settings").fetchall()}
    conn.close()
    assert keys == {"timezone", "k1"}  # k2 已回滚


def test_transaction_closes_connection(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    with db.transaction():
        pass
    # 事务结束连接应已关闭：写入不再被本模块持有的连接阻塞
    with db.transaction() as conn:
        conn.execute("SELECT 1")


def test_two_worker_threads_write_no_loss(tmp_path):
    """两个工作线程并发写，busy_timeout 内的有界重试不丢记录。"""
    db = Database(tmp_path / "app.db")
    db.migrate()
    n, per_thread = 2, 40
    errors: list[Exception] = []

    def worker(tid: int) -> None:
        try:
            for i in range(per_thread):
                with db.transaction() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO app_settings(key, value, updated_at) VALUES(?,?,?)",
                        (f"worker{tid}_{i}", "x", "now"),
                    )
        except Exception as exc:  # pragma: no cover - 汇集断言
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors
    conn = db.connect()
    count = conn.execute(
        "SELECT count(*) FROM app_settings WHERE key GLOB 'worker[0-9]*'"
    ).fetchone()[0]
    conn.close()
    assert count == n * per_thread


def test_close_blocks_new_connections(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    db.close()
    with pytest.raises(StorageUnavailableError):
        db.connect()
    assert not db.healthy()


def test_healthy_and_missing_dir(tmp_path):
    db = Database(tmp_path / "sub" / "app.db")
    conn = db.connect()  # 自动创建父目录
    conn.close()
    assert db.healthy()


def test_foreign_key_check_clean(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    assert foreign_key_check(db) == []
