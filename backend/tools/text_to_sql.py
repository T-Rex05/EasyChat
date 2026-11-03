"""Text2SQL 工具 — 基于 AgentForge 系统表的自然语言转 SQL 查询

工具清单：
- sql_db_get_schema: 查询表结构（从 database_schema_reference.md 读取）
- sql_db_query: 执行只读 SQL（安全限制：仅 SELECT，自动 LIMIT 兜底）

安全设计：
- 只允许 SELECT 查询（禁止 INSERT/UPDATE/DELETE/DROP/ALTER 等写操作）
- 无 LIMIT 时自动追加 LIMIT 100（上限 1000）
- SQL 语句经过词法检查，识别危险关键字直接拒绝
- 所有查询记录到 sql_operation_logs 审计表

改进：
- 添加详细的执行过程日志
- 表格格式化输出结果
- 自动计算汇总行（数值列）
"""
import re
import time
from typing import List, Optional, Dict, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.utils.log_utils import log
from backend.tools.table_scope import (
    _queryable_tables, _queryable_tables_hint, _validate_tables
)

logger = log

# ── 安全限制 ──
_MAX_QUERY_LIMIT = 1000
_DEFAULT_QUERY_LIMIT = 100

# 危险关键字（写操作/危险语句，正则词边界匹配）
_DANGEROUS_KEYWORDS = [
    r"\b(insert|update|delete|drop|alter|truncate|create|replace|grant|revoke)\b",
    r"\b(load_file|outfile|dumpfile|sleep)\s*\(",
    r"(--|#|/\*).*$",  # 注释
    r"\binto\s+outfile\b",
]

_DANGEROUS_RE = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _DANGEROUS_KEYWORDS]


class GetSchemaInput(BaseModel):
    """查询数据库表结构参数"""
    table_names: str = Field(description="表名（多个表名用逗号分隔，如 'categories,kb_knowledge_base'）")


class QuerySQLInput(BaseModel):
    """执行 SQL 查询参数"""
    query: str = Field(description="只读 SELECT SQL 语句")


def _validate_read_only(query: str) -> Optional[str]:
    """校验 SQL 是否为只读查询；返回错误信息或 None。"""
    stripped = (query or "").strip()
    if not stripped:
        return "SQL 不能为空"
    # 去掉末尾分号
    stripped = stripped.rstrip(";").strip()
    # 必须以 SELECT 开头（允许 WITH 前缀）
    if not re.match(r"^(SELECT|WITH)\b", stripped, re.IGNORECASE):
        return "只允许 SELECT 查询（拒绝写操作）"
    # 危险关键字检查
    for pattern in _DANGEROUS_RE:
        m = pattern.search(stripped)
        if m:
            return f"SQL 包含危险关键字: {m.group(0).strip()[:50]}"
    return None


# OFFSET 上限（防止大 offset 导致内存溢出）
# 依据：offset 10000 意味着数据库需要扫描至少 10000 行后才返回结果
# 这个值足够满足分页需求，同时避免超大内存占用
_MAX_OFFSET = 10000


class LimitValidationError(Exception):
    """LIMIT 校验错误（用于返回错误信息给调用方）"""
    pass


def _ensure_limit(query: str) -> str:
    """确保 LIMIT 不超过上限；无 LIMIT 时追加默认值。

    安全限制：
    - LIMIT 必须是纯数字（拒绝表达式如 5000000+0）
    - LIMIT 上限：1000
    - OFFSET 上限：10000
    - 无 LIMIT 时追加默认值 100

    Returns:
        处理后的 SQL（已添加或重写 LIMIT）

    Raises:
        LimitValidationError: LIMIT 格式非法或超出上限
    """
    stripped = query.rstrip(";").strip()

    # 检查是否有 LIMIT 子句
    limit_match = re.search(r"\bLIMIT\s+(.+?)\s*$", stripped, re.IGNORECASE)

    if not limit_match:
        # 无 LIMIT，追加默认值
        return f"{stripped} LIMIT {_DEFAULT_QUERY_LIMIT}"

    limit_clause = limit_match.group(1).strip()

    # 形式 1: LIMIT N（单数字）
    simple_match = re.match(r'^(\d+)$', limit_clause)
    if simple_match:
        limit_val = int(simple_match.group(1))
        if limit_val > _MAX_QUERY_LIMIT:
            # 超过上限，重写
            return re.sub(r"\bLIMIT\s+\d+\s*$", f"LIMIT {_MAX_QUERY_LIMIT}", stripped, flags=re.IGNORECASE)
        return stripped

    # 形式 2: LIMIT offset, count（MySQL 分页语法）
    offset_match = re.match(r'^(\d+)\s*,\s*(\d+)$', limit_clause)
    if offset_match:
        offset = int(offset_match.group(1))
        limit_val = int(offset_match.group(2))

        # 检查 offset 上限
        if offset > _MAX_OFFSET:
            raise LimitValidationError(
                f"OFFSET 值 {offset} 超过上限 {_MAX_OFFSET}。"
                f"过大的 OFFSET 会导致数据库扫描大量数据，可能引发性能问题。"
            )

        # 检查 limit 上限
        if limit_val > _MAX_QUERY_LIMIT:
            # 超过上限，重写
            return re.sub(
                r"\bLIMIT\s+\d+\s*,\s*\d+\s*$",
                f"LIMIT {min(offset, _MAX_OFFSET)}, {_MAX_QUERY_LIMIT}",
                stripped,
                flags=re.IGNORECASE
            )
        return stripped

    # 其他形式（表达式、非法格式等）一律拒绝
    raise LimitValidationError(
        f"LIMIT 格式非法: 'LIMIT {limit_clause}'。"
        f"只支持纯数字格式: LIMIT N 或 LIMIT offset, count。"
        f"不支持表达式（如 LIMIT 100+0）或其他格式。"
    )


def _record_sql_operation(thread_id: str, query: str, status: int = 1, error: Optional[str] = None) -> None:
    """记录 SQL 操作到审计日志（sql_operation_logs 表）。"""
    try:
        from backend.service.sql_recorder import record
        record(thread_id=thread_id, query=query, status=status, error=error)
    except Exception as e:
        logger.debug(f"[Text2SQL] 审计记录失败: {e}")


def _get_thread_id(config) -> str:
    """从 RunnableConfig 中提取 thread_id。"""
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
        return str(configurable.get("thread_id", "default"))
    return "default"


def _is_numeric(value: Any) -> bool:
    """判断值是否为数值类型"""
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False
    return False


def _to_float(value: Any) -> float:
    """将值转换为浮点数"""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def _format_number(value: Any) -> str:
    """格式化数值（添加千分位）"""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value != int(value):
            return f"{value:,.2f}"
        return f"{int(value):,}"
    if isinstance(value, str):
        try:
            num = float(value)
            if num == int(num):
                return f"{int(num):,}"
            return f"{num:,.2f}"
        except (ValueError, TypeError):
            return value
    return str(value)


def _format_table_output(rows: List[Dict[str, Any]], title: str = "查询结果") -> str:
    """将查询结果格式化为表格形式
    
    特性：
    - 自动对齐列宽
    - 数值列添加千分位
    - 自动计算汇总行（数值列）
    - 边框样式美化
    """
    if not rows:
        return "查询成功，返回 0 行结果。"
    
    # 获取所有列名
    columns = list(rows[0].keys())
    
    # 计算每列最大宽度
    col_widths = {}
    for col in columns:
        max_width = len(col)
        for row in rows:
            val_str = _format_number(row.get(col, "")) if _is_numeric(row.get(col)) else str(row.get(col, "") or "")
            max_width = max(max_width, min(len(val_str), 50))  # 限制最大宽度
        col_widths[col] = max_width
    
    # 构建分隔线
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths.values()) + "+"
    
    # 构建表头
    header = "|" + "|".join(f" {col:<{col_widths[col]}} " for col in columns) + "|"
    
    # 构建数据行
    data_lines = []
    numeric_cols = [col for col in columns if all(_is_numeric(row.get(col)) for row in rows)]
    totals = {col: 0.0 for col in numeric_cols}
    
    for row in rows:
        cells = []
        for col in columns:
            val = row.get(col, "")
            if _is_numeric(val):
                formatted = _format_number(val)
                cells.append(f" {formatted:>{col_widths[col]}} ")
                totals[col] += _to_float(val)
            else:
                val_str = str(val or "")[:50]  # 截断长文本
                cells.append(f" {val_str:<{col_widths[col]}} ")
        data_lines.append("|" + "|".join(cells) + "|")
    
    # 构建汇总行
    summary_line = None
    if numeric_cols:
        cells = []
        for col in columns:
            if col in numeric_cols:
                formatted = _format_number(totals[col])
                cells.append(f" {formatted:>{col_widths[col]}} ")
            else:
                cells.append(f" {'':<{col_widths[col]}} ")
        # 第一列显示"合计"
        cells[0] = f" {'合计':<{col_widths[columns[0]]}} "
        summary_line = "|" + "|".join(cells) + "|"
    
    # 组装完整表格
    lines = [
        "",
        f"[{title}]",
        separator,
        header,
        separator,
    ]
    lines.extend(data_lines)
    if summary_line:
        lines.append(separator)
        lines.append(summary_line)
    lines.append(separator)
    
    return "\n".join(lines)


def _format_schema_output(table_name: str, schema_text: str) -> str:
    """格式化表结构输出"""
    lines = [
        "",
        f"[表结构: {table_name}]",
        "-" * 50,
    ]
    
    # 解析 schema 文本，提取关键信息
    fields_section = False
    for line in schema_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("字段:"):
            fields_section = True
            lines.append("")
            lines.append("字段列表:")
            continue
        if line.startswith("- ") and fields_section:
            # 提取字段名和类型
            field_match = re.match(r"-\s+(\w+):\s+(\w+[^[]*)", line)
            if field_match:
                field_name = field_match.group(1)
                field_type = field_match.group(2).strip()
                # 提取语义说明
                semantic_match = re.search(r"\[语义:\s*([^\]]+)\]", line)
                semantic = semantic_match.group(1) if semantic_match else ""
                lines.append(f"  * {field_name}: {field_type}" + (f" -- {semantic}" if semantic else ""))
    
    return "\n".join(lines)


@tool(args_schema=GetSchemaInput)
def sql_db_get_schema(table_names: str) -> str:
    """
    查询数据库表结构（Schema Card）。

    【前置条件】
    在调用此工具之前，**应先调用 `knowledge_search` 检索知识库**，获取：
    - 表的业务含义和字段说明
    - 历史正确的 SQL 示例
    - 相关的业务规则

    当需要了解数据库表结构、字段信息、表关联关系时调用此工具。
    表结构来自人工维护的 database_schema_reference.md，包含字段说明、数据类型、关联线索。

    Args:
        table_names: 表名列表（逗号分隔，如 "categories,kb_knowledge_base"）

    Returns:
        str: 表结构信息（含字段、类型、说明、关联关系）
    """
    start_time = time.monotonic()
    
    output_lines = [
        "",
        "[Text2SQL Step 2] sql_db_get_schema",
        "-" * 50,
    ]
    
    try:
        from backend.service.database_semantic_index import format_table_schema_context

        names = [n.strip() for n in (table_names or "").split(",") if n.strip()]
        if not names:
            # 不传表名 → 返回可查表清单（正向引导：先告诉 LLM「能查什么」）
            return (
                "[Text2SQL Step 2] sql_db_get_schema\n"
                "-" * 50 + "\n"
                "未指定表名。当前可查询的表：\n"
                + _queryable_tables_hint()
                + "\n\n提示：使用 knowledge_search 检索知识库获取相关表和示例。"
            )

        # 白名单过滤
        allowed = _queryable_tables()
        denied = [n for n in names if n.lower() not in allowed]
        if denied:
            return (
                f"[Text2SQL Step 2] sql_db_get_schema\n"
                "-" * 50 + "\n"
                f"[X] 表 {', '.join(denied)} 不在可查询白名单内。\n\n"
                f"当前可查询的表：\n{_queryable_tables_hint()}\n\n"
                "如果 knowledge_search 没有召回到相关的表或 SQL 示例，说明该数据不在可查询范围内。"
            )

        output_lines.append(f"> 查询表: {', '.join(names)}")
        output_lines.append("")

        ctx = format_table_schema_context("mysql", names)
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        
        if not ctx:
            output_lines.append("[X] 未找到表结构定义")
            output_lines.append(f"   表名: {names}")
            output_lines.append("   提示: 该表不在 database_schema_reference.md 收录范围内")
            output_lines.append("   建议: 请告知表名以查询结构；information_schema 不可查询")
            output_lines.append("")
            output_lines.append(f"[耗时] {elapsed_ms}ms")
            return "\n".join(output_lines)
        
        output_lines.append(f"[OK] 找到 {len(names)} 个表的结构定义")
        output_lines.append(f"[耗时] {elapsed_ms}ms")
        
        # 返回原始 schema 文本
        output_lines.append("")
        output_lines.append("-" * 50)
        output_lines.append(ctx)
        
        return "\n".join(output_lines)
        
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        output_lines.append(f"[X] 获取表结构失败: {e}")
        output_lines.append(f"[耗时] {elapsed_ms}ms")
        logger.error(f"[Text2SQL] 获取表结构失败: {e}")
        return "\n".join(output_lines)


sql_db_get_schema._toolset = "__always_available__"  # 所有用户可用


@tool(args_schema=QuerySQLInput)
def sql_db_query(query: str, config: RunnableConfig = None) -> str:
    """
    执行只读 SQL 查询（SELECT）。

    【强制前置条件】
    在调用此工具之前，**必须先调用 `knowledge_search` 检索知识库**！
    
    原因：
    - 知识库中包含历史正确的 SQL 示例（如用户统计、Token 消耗等）
    - 知识库中包含表的业务含义和字段说明（不只是字段名和类型）
    - 知识库中可能包含特殊的过滤条件（如 deleted_at IS NULL、is_test=0 等）

    正确流程：
    1. 先调用 knowledge_search(query="用户统计" 或相关关键词)
    2. 根据检索结果获取表名、SQL 示例、业务规则
    3. 再调用 sql_db_get_schema 确认表结构
    4. 最后调用 sql_db_query 执行查询

    仅支持 SELECT 查询，自动限制返回行数（默认 100，上限 1000）。

    Args:
        query: 只读 SELECT SQL 语句

    Returns:
        str: 查询结果（表格格式），或错误信息
    """
    import json
    
    start_time = time.monotonic()
    thread_id = _get_thread_id(config)
    
    output_lines = [
        "",
        "[Text2SQL Step 3] sql_db_query",
        "-" * 50,
    ]
    
    # ── Step 1: 安全校验 ──
    output_lines.append("[Step 1] 安全校验")
    output_lines.append(f"   SQL: {query[:100]}{'...' if len(query) > 100 else ''}")
    
    err = _validate_read_only(query)
    if err:
        output_lines.append(f"   [X] 校验失败: {err}")
        output_lines.append("")
        _record_sql_operation(thread_id, query, status=0, error=err)
        return "\n".join(output_lines)

    # 表白名校验
    err = _validate_tables(query)
    if err:
        output_lines.append(f"   [X] 表名校验失败: {err}")
        output_lines.append("")
        _record_sql_operation(thread_id, query, status=0, error=err)
        return "\n".join(output_lines)

    output_lines.append("   [OK] 只读查询 (SELECT only)")
    output_lines.append("   [OK] 无危险关键字")
    output_lines.append("   [OK] 表名在白名单内")

    # ── Step 2: LIMIT 兜底 ──
    output_lines.append("")
    output_lines.append("[Step 2] 查询优化")
    try:
        safe_query = _ensure_limit(query)
    except LimitValidationError as e:
        output_lines.append(f"   [X] LIMIT 校验失败: {e}")
        output_lines.append("")
        _record_sql_operation(thread_id, query, status=0, error=str(e))
        return "\n".join(output_lines)

    if safe_query != query.rstrip(";").strip():
        output_lines.append("   [OK] 已自动追加/重写 LIMIT (默认 100，上限 1000)")
    else:
        output_lines.append("   [OK] 查询已包含有效 LIMIT")

    # ── Step 3: 执行查询 ──
    output_lines.append("")
    output_lines.append("[Step 3] 执行查询")
    output_lines.append(f"   连接数据库...")

    from backend.db.schema import get_conn

    conn = None
    try:
        conn = get_conn()
        output_lines.append(f"   执行 SQL...")

        exec_start = time.monotonic()
        cur = conn.execute(safe_query)

        # 使用有界读取，避免全量入内存
        # fetchmany 只获取需要的行数，不会一次性加载所有结果
        rows = []
        while len(rows) < _MAX_QUERY_LIMIT:
            batch = cur.fetchmany(_MAX_QUERY_LIMIT - len(rows))
            if not batch:
                break
            rows.extend(batch)

        exec_elapsed_ms = int((time.monotonic() - exec_start) * 1000)

        # 转换为 list of dict
        result = [dict(r) for r in rows]
        total_elapsed_ms = int((time.monotonic() - start_time) * 1000)

        output_lines.append(f"   [OK] 查询完成")
        output_lines.append(f"   返回行数: {len(result)}")
        output_lines.append(f"   执行耗时: {exec_elapsed_ms}ms")
        
        # 限制返回行数（防止超长输出）
        limited = result[:_MAX_QUERY_LIMIT]
        
        _record_sql_operation(thread_id, safe_query, status=1)
        
        if not limited:
            output_lines.append("")
            output_lines.append("[查询结果] 0 行")
            output_lines.append(f"[总耗时] {total_elapsed_ms}ms")
            return "\n".join(output_lines)
        
        # ── Step 4: 格式化输出 ──
        output_lines.append("")
        output_lines.append("[Step 4] 结果格式化")
        
        # 截断长文本
        truncated_rows = []
        for row in limited:
            row_dict = {}
            for k, v in row.items():
                s = str(v)
                row_dict[k] = s if len(s) <= 500 else s[:500] + "..."
            truncated_rows.append(row_dict)
        
        # 表格格式化
        table_output = _format_table_output(truncated_rows, title="查询结果")
        
        output_lines.append(f"   [OK] 已格式化为表格")
        output_lines.append(f"   [OK] 已添加汇总行")
        
        # 最终输出
        output_lines.append("")
        output_lines.append("-" * 50)
        output_lines.append(table_output)
        
        if len(result) > _MAX_QUERY_LIMIT:
            output_lines.append("")
            output_lines.append(f"[!] 共 {len(result)} 行，已截断到前 {_MAX_QUERY_LIMIT} 行")
        
        # JSON 格式（供程序解析）
        output_lines.append("")
        output_lines.append("[JSON 格式] (供程序解析):")
        output_lines.append(f"```json")
        output_lines.append(json.dumps(truncated_rows, ensure_ascii=False, indent=2))
        output_lines.append("```")
        
        output_lines.append("")
        output_lines.append(f"[总耗时] {total_elapsed_ms}ms")
        output_lines.append("[OK] SQL 操作已记录到审计日志 (sql_operation_logs)")
        
        return "\n".join(output_lines)
        
    except Exception as e:
        total_elapsed_ms = int((time.monotonic() - start_time) * 1000)
        output_lines.append(f"   [X] 查询失败: {e}")
        output_lines.append(f"[总耗时] {total_elapsed_ms}ms")
        _record_sql_operation(thread_id, safe_query, status=0, error=str(e)[:300])
        logger.warning(f"[Text2SQL] SQL 执行失败: {e}")
        return "\n".join(output_lines)
        
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


sql_db_query._toolset = "__always_available__"  # 所有用户可用

# 把可查表清单并入工具描述：让 LLM 在生成 SQL 之前就知道边界
sql_db_query.description = (
    (sql_db_query.description or "")
    + "\n\n【可查询的表（白名单，未列出的表一律不可查）】\n"
    + _queryable_tables_hint()
    + "\n\n如果 knowledge_search 没有召回到相关的表或 SQL 示例，说明该数据不在可查询范围内："
    "请直接告知用户「该数据无法通过 SQL 查询」，不要猜测表名、不要尝试未列出的表。"
)