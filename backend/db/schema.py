"""
AgentForge 数据库连接与初始化

职责：
- 提供 get_conn()：统一的 MySQL 连接入口（包装 pymysql 连接池）
- 提供 init_db()：首次部署/启动时执行 sql/agentforge_schema.sql 完成建表 + 默认数据播种

数据库完整 DDL 见 sql/agentforge_schema.sql（唯一数据源）。
"""
import re
from pathlib import Path

from backend.utils.log_utils import log

logger = log

# 项目根目录
_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_SQL_PATH = _ROOT / "sql" / "agentforge_schema.sql"


# ── 数据库连接（统一走连接池） ──


class _MySQLAdapter:
    """MySQL 连接适配器 — 包装 pymysql 连接，提供统一的 execute/commit/close 接口。"""

    def __init__(self, conn):
        self._conn = conn
        self._cursor = None

    def _cur(self):
        if self._cursor is None:
            import pymysql.cursors
            self._cursor = self._conn.cursor(pymysql.cursors.DictCursor)
        return self._cursor

    def execute(self, sql, params=()):
        c = self._cur()
        # 兼容 SQLite 风格的 ? 占位符 → 自动转换为 MySQL 的 %s
        # 注意：仅替换不在引号内的 ?，避免误替换 JSON 或字符串字面量中的 ?
        if "?" in sql:
            sql = re.sub(r"\?(?=(?:[^']*'[^']*')*[^']*$)", "%s", sql)
        c.execute(sql, params)
        return c

    def executescript(self, sql):
        """按分号分割并执行多条 SQL。
        注意：简单分号分割，不适用于字符串字面量内含分号的场景（init_db 的 DDL 不含此类情况）。
        """
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                self._cur().execute(stmt)

    def batch_execute(self, statements: list[str]):
        """批量执行 DDL/DML 语句（利用 MULTI_STATEMENTS 一次网络往返）。
        单条失败不影响其他语句，失败的语句记日志。"""
        joined = ";\n".join(s.strip().rstrip(";") for s in statements if s.strip())
        if not joined:
            return
        cur = self._cur()
        try:
            cur.execute(joined)
            # 消耗所有结果集，防止 "Commands out of sync"
            while True:
                try:
                    cur.fetchall()
                except Exception as e:
                    # DDL 语句无结果集，pymysql 会抛 ProgrammingError/InterfaceError
                    # 仅忽略此类异常，其他异常记录日志
                    err_name = type(e).__name__
                    if err_name not in ("ProgrammingError", "InterfaceError"):
                        logger.debug(f"batch_execute fetchall 异常: {err_name}: {e}")
                if not cur.nextset():
                    break
        except Exception as e:
            # MULTI_STATEMENTS 模式下若某条失败，整体报错；降级为逐条执行
            logger.warning(f"批量执行失败，降级为逐条执行: {e}")
            for stmt in statements:
                stmt = stmt.strip()
                if stmt:
                    try:
                        self._cur().execute(stmt)
                    except Exception as ex:
                        logger.debug(f"DDL 跳过: {ex}")

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if self._cursor:
            self._cursor.close()
            self._cursor = None
        if self._conn:
            self._conn.close()  # 归还连接到连接池


def get_conn():
    """从统一连接池获取 MySQL 连接（带 _MySQLAdapter 兼容层）。

    用法：
        conn = get_conn()
        try:
            cur = conn.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            rows = cur.fetchall()
        finally:
            conn.close()
    """
    from backend.db.connection_pool import get_pool_connection
    return _MySQLAdapter(get_pool_connection())


# ── 数据库初始化 ──


def init_db() -> None:
    """初始化数据库：执行 sql/agentforge_schema.sql 完成建表 + 默认数据播种。

    - 所有 CREATE TABLE 均使用 IF NOT EXISTS，可安全重复执行
    - INSERT 均使用 IGNORE，已存在则跳过
    - 完整 DDL 唯一数据源：sql/agentforge_schema.sql
    """
    if not _SCHEMA_SQL_PATH.exists():
        logger.warning(f"[init_db] 未找到 Schema 文件: {_SCHEMA_SQL_PATH}")
        return

    sql_text = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")

    # 移除文件开头的 CREATE DATABASE / USE 语句（连接已绑定数据库，无需重建）
    sql_text = re.sub(
        r"^\s*(CREATE\s+DATABASE[^\n]*\n|USE\s+\w+\s*;)\s*",
        "",
        sql_text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    conn = get_conn()
    try:
        conn.executescript(sql_text)
        conn.commit()
        logger.info("[init_db] 数据库初始化完成")
    except Exception as e:
        conn.rollback()
        logger.warning(f"[init_db] 初始化部分语句跳过: {e}")
    finally:
        conn.close()

    # ── 增量迁移：为已有表补充新列（幂等，已存在则跳过）──
    _run_migrations()


def _run_migrations():
    """增量迁移：为已有数据库补充新列（幂等，已存在则跳过）。

    注：新表（data_layers / user_data_layers / kb_data_layers 等）由 init_db() 执行 SQL 文件时
    CREATE TABLE IF NOT EXISTS 创建，此处无需重复。
    """
    conn = get_conn()

    # ── model_configs 列迁移 ──
    try:
        cur = conn.execute("SHOW COLUMNS FROM model_configs")
        mc_cols = {row["Field"] for row in cur.fetchall()} if cur.description else set()
    except Exception:
        mc_cols = set()

    mc_migrations = [
        ("priority", "ALTER TABLE model_configs ADD COLUMN priority INT DEFAULT 0 COMMENT '降级优先级'"),
        ("cost_per_1k_input", "ALTER TABLE model_configs ADD COLUMN cost_per_1k_input DECIMAL(10,6) DEFAULT 0 COMMENT '每1000输入token成本(USD)'"),
        ("cost_per_1k_output", "ALTER TABLE model_configs ADD COLUMN cost_per_1k_output DECIMAL(10,6) DEFAULT 0 COMMENT '每1000输出token成本(USD)'"),
        ("context_length", "ALTER TABLE model_configs ADD COLUMN context_length INT DEFAULT 0 COMMENT '模型上下文窗口大小'"),
        ("capabilities", "ALTER TABLE model_configs ADD COLUMN capabilities JSON COMMENT '模型能力标签'"),
        ("description", "ALTER TABLE model_configs ADD COLUMN description TEXT COMMENT '模型描述/备注'"),
    ]
    applied = []
    for col_name, alter_sql in mc_migrations:
        if col_name not in mc_cols:
            try:
                conn.execute(alter_sql)
                applied.append(col_name)
            except Exception as e:
                logger.debug(f"[migration] 跳过列 {col_name}: {e}")
    if applied:
        try:
            conn.commit()
            logger.info(f"[migration] model_configs 新增列: {', '.join(applied)}")
        except Exception as e:
            logger.warning(f"[migration] 提交失败: {e}")

    # ── kb_chunks.scope_layer_id 列迁移 ──
    try:
        cur = conn.execute("SHOW COLUMNS FROM kb_chunks")
        kc_cols = {row["Field"] for row in cur.fetchall()} if cur.description else set()
    except Exception:
        kc_cols = set()

    if "scope_layer_id" not in kc_cols:
        try:
            conn.execute(
                "ALTER TABLE kb_chunks ADD COLUMN scope_layer_id BIGINT DEFAULT NULL "
                "COMMENT '数据层级ID（NULL=继承KB层级，非NULL=单独指定）'"
            )
            conn.execute("ALTER TABLE kb_chunks ADD INDEX idx_scope_layer (scope_layer_id)")
            conn.commit()
            logger.info("[migration] kb_chunks 新增 scope_layer_id 列")
        except Exception as e:
            logger.debug(f"[migration] 跳过 scope_layer_id: {e}")

    conn.close()
