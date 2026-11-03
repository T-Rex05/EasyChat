"""SQLite 平台模块：连接、事务、迁移与 PRAGMA（架构 §5.4）。

- 每次操作在调用线程内创建/关闭独立连接，不跨线程共享连接。
- journal 模式选 WAL（与内嵌 Hermes state.db 的选择一致；文件系统不支持时
  回退 DELETE——两库是不同文件，互不影响）。
- 写事务必须短小：不跨 await、不含外部调用。
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backend.shared.errors import StorageUnavailableError

DEFAULT_BUSY_TIMEOUT_MS = 5000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Database:
    """app.db 的唯一平台入口。业务模块只通过本类拿到连接/事务。"""

    def __init__(self, path: Path, *, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS) -> None:
        self.path = Path(path)
        self.busy_timeout_ms = busy_timeout_ms
        self._closed = False
        self._ready = False
        self._journal_mode: str | None = None

    # ---- 连接 ---------------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """新建调用方拥有的连接（不进连接池）。调用方负责 close。"""
        if self._closed:
            raise StorageUnavailableError("数据库已关闭")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(self.path, timeout=self.busy_timeout_ms / 1000.0, isolation_level=None)
        except sqlite3.Error as exc:
            raise StorageUnavailableError(f"无法打开数据库 {self.path}: {exc}") from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        return conn

    @contextmanager
    def transaction(self, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        """短写事务：进入即 BEGIN IMMEDIATE，退出提交或回滚，连接自动关闭。

        事务体内不得做网络/LLM/SMTP等外部调用。
        """
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    # ---- 生命周期 ------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def journal_mode(self) -> str | None:
        return self._journal_mode

    def _apply_journal_mode(self, conn: sqlite3.Connection) -> str:
        """设置 journal 模式；WAL 不可用时回退 DELETE（与 Hermes 策略一致）。"""
        row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        mode = row[0] if row else None
        if mode != "wal":
            conn.execute("PRAGMA journal_mode=DELETE")
            row = conn.execute("PRAGMA journal_mode").fetchone()
            mode = row[0] if row else "delete"
        return str(mode)

    def migrate(self) -> list[str]:
        """执行版本化迁移，返回本次实际应用的版本列表。失败时启动不得继续。"""
        if self._closed:
            raise StorageUnavailableError("数据库已关闭")
        conn = self.connect()
        try:
            self._journal_mode = self._apply_journal_mode(conn)
        finally:
            conn.close()
        applied = run_migrations(self)
        self._ready = True
        return applied

    def healthy(self) -> bool:
        try:
            conn = self.connect()
        except StorageUnavailableError:
            return False
        try:
            conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False
        finally:
            conn.close()

    def close(self) -> None:
        self._closed = True


# ---- 迁移机制 ----------------------------------------------------------------


class MigrationError(StorageUnavailableError):
    """迁移失败或 checksum 不一致：启动必须终止（架构 §5.4）。"""


def load_migrations(migrations_dir: Path) -> list[tuple[str, str]]:
    """读取目录中按 `NNNN_name.sql` 命名的迁移，返回 (version, sql) 有序列表。"""
    if not migrations_dir.exists():
        return []
    out = []
    for p in sorted(migrations_dir.glob("*.sql")):
        version = p.stem.split("_", 1)[0]
        out.append((version, p.read_text(encoding="utf-8")))
    return out


def _migration_applied(conn: sqlite3.Connection, version: str, checksum: str) -> bool:
    row = conn.execute("SELECT checksum FROM schema_migrations WHERE version=?", (version,)).fetchone()
    if row is None:
        return False
    if row["checksum"] != checksum:
        raise MigrationError(f"迁移 {version} checksum 不一致：已应用 {row['checksum']}，当前 {checksum}")
    return True


def _split_sql_statements(script: str) -> list[str]:
    """把多行 SQL 拆成完整语句（引号内分号/触发器体安全，注释保留随语句执行）。"""
    statements: list[str] = []
    buf: list[str] = []
    for line in script.splitlines(keepends=True):
        buf.append(line)
        if sqlite3.complete_statement("".join(buf)):
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def run_migrations(db: Database, migrations_dir: Path | None = None) -> list[str]:
    """按版本顺序应用迁移；每个迁移在单个事务内完成并登记 checksum。

    不能用 executescript——它会先隐式提交挂起事务，破坏原子性；这里逐条
    execute 使失败时 ROLLBACK 能撤销整个迁移。
    """
    from backend.platform.migrations import MIGRATIONS_DIR  # 包内默认值

    migrations = load_migrations(migrations_dir or MIGRATIONS_DIR)
    just_applied: list[str] = []
    conn = db.connect()
    try:
        # schema_migrations 自身必须最先存在（0001 内建；为空目录兜底）
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )"""
        )
        for version, sql in migrations:
            checksum = _checksum(sql)
            if _migration_applied(conn, version, checksum):
                continue
            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in _split_sql_statements(sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES(?, ?, ?)",
                    (version, checksum, utc_now_iso()),
                )
                conn.execute("COMMIT")
            except sqlite3.Error:
                conn.execute("ROLLBACK")
                raise
            just_applied.append(version)
        return just_applied
    finally:
        conn.close()


def _checksum(sql: str) -> str:
    import hashlib

    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def foreign_key_check(db: Database) -> list[str]:
    """返回违反外键的表/行标识列表（空列表=健康）。"""
    conn = db.connect()
    try:
        rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        return [f"{r[0]}:{r[1]}" for r in rows]
    finally:
        conn.close()
