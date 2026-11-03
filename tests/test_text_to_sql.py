"""Text2SQL 工具 单元测试（安全校验 + LIMIT 兜底 + Schema 查询）"""
import pytest

from backend.tools.text_to_sql import (
    _validate_read_only,
    _ensure_limit,
    sql_db_get_schema,
)


class TestValidateReadOnly:
    def test_select_ok(self):
        """SELECT 查询应通过。"""
        assert _validate_read_only("SELECT * FROM users") is None

    def test_select_with_where_ok(self):
        """带 WHERE 的 SELECT 应通过。"""
        assert _validate_read_only("SELECT id, username FROM users WHERE status = 1") is None

    def test_with_cte_ok(self):
        """WITH 开头的查询应通过。"""
        assert _validate_read_only("WITH t AS (SELECT 1) SELECT * FROM t") is None

    def test_insert_rejected(self):
        """INSERT 应被拒绝。"""
        err = _validate_read_only("INSERT INTO users (username) VALUES ('x')")
        assert err is not None
        assert "只允许" in err

    def test_update_rejected(self):
        """UPDATE 应被拒绝。"""
        assert _validate_read_only("UPDATE users SET role = 'admin'") is not None

    def test_delete_rejected(self):
        """DELETE 应被拒绝。"""
        assert _validate_read_only("DELETE FROM users") is not None

    def test_drop_rejected(self):
        """DROP 应被拒绝。"""
        assert _validate_read_only("DROP TABLE users") is not None

    def test_alter_rejected(self):
        """ALTER 应被拒绝。"""
        assert _validate_read_only("ALTER TABLE users ADD COLUMN x INT") is not None

    def test_comment_rejected(self):
        """带注释的 SQL 应被拒绝。"""
        assert _validate_read_only("SELECT * FROM users -- comment") is not None

    def test_empty_rejected(self):
        """空 SQL 应被拒绝。"""
        assert _validate_read_only("") is not None

    def test_union_select_ok(self):
        """UNION 组合 SELECT 应通过。"""
        assert _validate_read_only("SELECT 1 UNION SELECT 2") is None


class TestEnsureLimit:
    def test_no_limit_appended(self):
        """无 LIMIT 时应追加默认 LIMIT。"""
        assert _ensure_limit("SELECT * FROM users").endswith("LIMIT 100")

    def test_existing_limit_kept(self):
        """已有 LIMIT 时保持原样。"""
        sql = "SELECT * FROM users LIMIT 50"
        assert _ensure_limit(sql) == sql

    def test_offset_limit_kept(self):
        """带 OFFSET 的 LIMIT 保持原样。"""
        sql = "SELECT * FROM users LIMIT 10, 20"
        assert _ensure_limit(sql) == sql

    def test_trailing_semicolon(self):
        """末尾分号应被处理。"""
        result = _ensure_limit("SELECT * FROM users;")
        assert result.endswith("LIMIT 100")
        assert not result.endswith(";LIMIT")


class TestGetSchema:
    """T2.1b：`sql_db_get_schema` 是四层防御的**第 2 层（schema 注入路径）**。

    只对白名单内的表返回结构；敏感表（`users`/`traces`/`conversations`/`model_configs` …）
    **连字段名都拿不到**，只返回"不可查询 + 当前可查清单"。
    可查表共 7 张：categories / item_status / data_layers / kb_data_layers /
    kb_knowledge_base / skill_meta / content_pool（单一事实源 `backend/tools/table_scope.py`）。
    """

    _ALLOWED = ["categories", "kb_knowledge_base"]

    def test_get_schema_known_table(self):
        """敏感表（users）必须被整体拒绝，且**不泄露任何字段名**。"""
        result = sql_db_get_schema.invoke({"table_names": "users"})
        # 被拒绝
        assert "不在可查询" in result
        # 不得泄露 users 的字段名
        for field in ("password", "password_hash", "username", "email", "role_id", "用户ID"):
            assert field not in result, f"泄露了 users 的字段名: {field}"
        # 但要告知可查范围
        assert "categories" in result

    def test_get_schema_multiple_tables(self):
        """多表时**整体拒绝**，不能只拒第一个。"""
        result = sql_db_get_schema.invoke({"table_names": "users,traces"})
        assert "不在可查询" in result
        assert "users" in result and "traces" in result  # 两个都要点名
        # 不得返回 traces 的字段结构
        assert "trace_id" not in result
        assert "session_key" not in result

    def test_get_schema_sensitive_mixed_with_allowed(self):
        """敏感表与白名单表混传 → 整体拒绝（不能只放行白名单那部分）。"""
        result = sql_db_get_schema.invoke(
            {"table_names": "users,conversations,model_configs"}
        )
        assert "不在可查询" in result
        for field in ("api_key", "password_hash", "user_question"):
            assert field not in result, f"泄露了敏感字段: {field}"

    def test_get_schema_allowed_tables_return_structure(self):
        """白名单内的表应正常返回结构。"""
        result = sql_db_get_schema.invoke({"table_names": "categories,kb_knowledge_base"})
        assert "categories" in result
        assert "kb_knowledge_base" in result
        assert "不在可查询" not in result

    def test_get_schema_unknown_table(self):
        """不在白名单的表（含根本不存在的表）应被拒绝。"""
        result = sql_db_get_schema.invoke({"table_names": "no_such_table_xyz"})
        assert "不在可查询" in result

    def test_get_schema_empty(self):
        """不传表名 → 返回**当前可查表清单**（让 LLM 一开始就知道能查什么）。"""
        result = sql_db_get_schema.invoke({"table_names": ""})
        for table in self._ALLOWED:
            assert table in result
        # 不得把敏感表列为"可查"
        assert "users" not in result.split("当前可查询")[-1]

    def test_never_allowed_tables_not_queryable(self):
        """`_NEVER_ALLOWED_TABLES` 里的表一律拿不到结构（硬闸优先）。"""
        from backend.tools.table_scope import _queryable_tables

        allowed = set(_queryable_tables())
        assert "users" not in allowed
        assert "traces" not in allowed
        assert "conversations" not in allowed
        assert "model_configs" not in allowed
        assert len(allowed) == 7
