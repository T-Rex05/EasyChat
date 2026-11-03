"""数据库 Schema 参考访问器 — 根据表名从 database_schema_reference.md 查询表结构

与 Eyes 的 database_semantic_index.py 同构：
- 参考文档：backend/config/database_schema_reference.md（人工维护）
- 按 `========== 表名 ==========` 区块切分，支持按表名精确查询
- 供 text2sql 召回：检索命中 chunk 的 table_refs → 这里查 Schema Card → 拼装上下文给 LLM
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE_PATH = ROOT / "backend" / "config" / "database_schema_reference.md"

_SECTION_HEADER_RE = re.compile(r"^###\s+(\S+)", re.MULTILINE)
_SOURCE_LINE_RE = re.compile(r"^数据库:\s*(\S+)\s*$", re.MULTILINE)


def _norm(value: str) -> str:
    return re.sub(r"[\s\-_/\\（）()【】\[\]{}·:：,，、.。;；|]+", "", str(value or "").lower())


@lru_cache(maxsize=1)
def _load_table_sections(path: str | None = None) -> list[tuple[str, str, str]]:
    """Return [(table_name, source, section_text), ...] parsed from the reference file."""
    ref_path = Path(path) if path else DEFAULT_REFERENCE_PATH
    if not ref_path.exists():
        return []
    text = ref_path.read_text(encoding="utf-8")
    matches = list(_SECTION_HEADER_RE.finditer(text))
    sections: list[tuple[str, str, str]] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        name = match.group(1).strip()
        body = text[start:end].rstrip()
        source_match = _SOURCE_LINE_RE.search(body)
        source = source_match.group(1).strip().lower() if source_match else "mysql"
        sections.append((name, source, body))
    return sections


def format_table_schema_context(database: str, table_names: list[str] | str | None) -> str:
    """Return schema reference text for requested tables, empty when unavailable."""
    if isinstance(table_names, str):
        requested = [table_names]
    elif table_names:
        requested = [str(item) for item in table_names]
    else:
        requested = []
    requested_norm = {_norm(item) for item in requested if str(item).strip()}
    if not requested_norm:
        return ""

    db = str(database or "").strip().lower()
    filter_source = db if db in {"mysql", "clickhouse"} else None

    sections: list[str] = []
    for name, source, body in _load_table_sections():
        if filter_source and source != filter_source:
            continue
        if _norm(name) not in requested_norm:
            continue
        sections.append(body)
    return "\n\n".join(sections).strip()


def resolve_table_schema_context(
    table_refs: list[str] | None,
    database: str = "mysql",
    max_tables: int = 10,
) -> str:
    """根据 table_refs（检索结果中的数据库表关联）查询 Schema Card。

    Args:
        table_refs: 检索命中 chunk 携带的表名列表
        database: 数据库类型（mysql）
        max_tables: 最多拼装几张表的 schema（防上下文膨胀）

    Returns:
        Schema Card 文本（含表结构、字段、说明），无可用时返回空字符串
    """
    if not table_refs:
        return ""
    # 去重保序
    seen = set()
    unique = []
    for t in table_refs:
        t = str(t).strip()
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    if not unique:
        return ""

    # 白名单过滤：只返回可查询表的 schema
    from backend.tools.table_scope import _queryable_tables
    allowed = _queryable_tables()
    unique = [t for t in unique if t.lower() in allowed]
    if not unique:
        return ""

    context = format_table_schema_context(database, unique[:max_tables])
    return context
