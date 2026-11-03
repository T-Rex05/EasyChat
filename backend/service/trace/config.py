"""
LLM 链路可观测性 — 配置管理

trace_config 表：全局采集配置（KV 存储）
"""
from typing import Dict
from backend.utils.log_utils import log

logger = log


def _conn():
    from backend.db.schema import get_conn
    return get_conn()


def get_config(key: str, default: str = "") -> str:
    """读取 trace_config 配置值"""
    conn = _conn()
    try:
        cur = conn.execute("SELECT value FROM trace_config WHERE `key` = %s", (key,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return rows[0]["value"] if rows else default
    finally:
        conn.close()


def get_all_config() -> Dict[str, str]:
    """读取所有 trace_config"""
    conn = _conn()
    try:
        cur = conn.execute("SELECT `key`, value FROM trace_config")
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


def set_config(key: str, value: str) -> None:
    """更新 trace_config 配置值"""
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO trace_config (`key`, value) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE value = %s",
            (key, value, value),
        )
        conn.commit()
    finally:
        conn.close()


def is_detail_enabled() -> bool:
    """是否开启全量采集模式"""
    return get_config("trace_detail_enabled", "false").lower() == "true"


def get_max_text_chars() -> int:
    """全量模式下文本截断长度"""
    try:
        return int(get_config("trace_max_text_chars", "10000"))
    except (ValueError, TypeError):
        return 10000
