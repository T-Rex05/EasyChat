"""
Text2SQL 可查询表白名单（默认拒绝）—— 供 text_to_sql 与 database_semantic_index 共用。

单独成模块是为了避免循环导入：text_to_sql 会 import database_semantic_index，
后者不能反过来在顶层 import text_to_sql。

安全设计原则：
1. 判定点越靠前越好，最靠前的一层是"知识源里根本不写敏感表"
2. 白名单只放"无论如何都不该有争议"的全局共享表
3. 需要查按 user_id 分片的数据时，另建专用工具，不要往白名单里加表
"""

import re
from typing import Optional

# ── 查询表白名单（默认拒绝）──
# 原则：只放「全局共享、不含任何用户内容」的表。
# 需要查按 user_id 分片的数据时，另建专用工具做强制过滤，不要往这里加表。
_ALLOWED_TABLES = frozenset({
    # 字典 / 结构
    "categories", "item_status", "data_layers", "kb_data_layers",
    # 知识库元数据（不含正文；kb_knowledge_base.user_id 是创建者，已确认可暴露）
    "kb_knowledge_base",
    # 技能池 / 内容池元数据
    "skill_meta", "content_pool",
})

# 第二道闸（优先级最高）：即使有人误把敏感表加进白名单或环境变量，这里也一律拒绝
# 覆盖范围：65 张业务表 = 上面 7 张可查 + 下面 58 张禁止，无模糊地带
_NEVER_ALLOWED_TABLES = frozenset({
    # 账号 / 权限 / 配置 / 凭据
    "users", "roles", "role_permissions", "user_permissions", "permission_defs",
    "user_configs", "user_bindings", "personal_emails", "email_configs",
    "model_configs", "model_route_settings", "platform_config",
    "host_whitelist", "command_blacklist", "exec_approval_logs", "trace_config",
    # 会话 / 可观测 / 按用户分片的统计
    "conversations", "attachments", "traces", "trace_spans", "daily_user_stats",
    # 记忆全家族
    "memory_items", "memory_episodic", "memory_semantic", "memory_versions",
    "memory_outbox", "memory_rounds", "memory_consolidation_logs",
    "memory_operation_logs", "memory_eval_sets", "memory_eval_runs",
    "memory_eval_items", "memory_eval_results", "memory_ab_experiments",
    "memory_ab_events", "delegation_tasks",
    # 知识库正文与检索痕迹：正文受 kb_chunks.scope_layer_id 层级授权保护，
    # 用 SQL 全表 dump 会绕过 RAG 的 _filter_by_scope_layer，故一律不可查
    "kb_documents", "kb_chunks", "kb_topics", "kb_retrieval_logs",
    "kb_feedback", "kb_eval_sets", "kb_eval_items", "kb_eval_runs", "kb_eval_results",
    "kb_eval_suggestions",
    # 按用户/租户分片的运维与图谱数据（含 owner_id 或 FK 指向按用户分片的表）
    "cron_jobs", "cron_executions", "content_installs", "user_data_layers",
    "agent_operation_logs", "sql_operation_logs",
    "rag_embedding_configs", "kg_communities", "kg_community_reports",
    "kg_archived_entities", "kg_alignment_candidates", "graph_change_log",
    # 元数据库
    "information_schema", "mysql", "performance_schema", "sys",
})

# 每张可查表的一句话用途（用于第二层「不传表名时返回清单」，让 LLM 一开始就知道能查什么）
_TABLE_PURPOSE = {
    "categories":        "分类字典",
    "item_status":       "条目状态字典",
    "data_layers":       "数据层级定义",
    "kb_data_layers":    "知识库与层级的关联",
    "kb_knowledge_base": "知识库列表（含名称、类型、创建者）",
    "skill_meta":        "技能池元数据",
    "content_pool":      "内容池元数据",
}


def _queryable_tables() -> set:
    """当前可查询的表集合 = 白名单 ∪ 环境变量追加 − 硬黑名单（硬闸优先）。"""
    import os

    allowed = set(_ALLOWED_TABLES)
    extra = os.environ.get("TEXT2SQL_EXTRA_TABLES", "")
    if extra:
        allowed |= {t.strip().lower() for t in extra.split(",") if t.strip()}
    return allowed - _NEVER_ALLOWED_TABLES


def _queryable_tables_hint() -> str:
    """可查表清单 + 用途（给 LLM 看的正向提示，用于工具描述与 schema 工具）。"""
    lines = []
    for t in sorted(_queryable_tables()):
        purpose = _TABLE_PURPOSE.get(t, "")
        lines.append(f"  - {t}" + (f"（{purpose}）" if purpose else ""))
    return "\n".join(lines)


# ── 表名提取正则（第一层校验）──
# 支持所有连接语法：
# - FROM table
# - FROM table1, table2, ...（逗号隐式连接）
# - JOIN / LEFT [OUTER] JOIN / RIGHT [OUTER] JOIN / INNER JOIN / CROSS JOIN
# - STRAIGHT_JOIN / NATURAL JOIN
# 注意：不匹配子查询 FROM (SELECT ...) 中的表名（因为括号前没有表名）

# 主正则：匹配 FROM/JOIN 关键字后的表名
_TABLE_REF_RE = re.compile(
    r"""
    \b
    (?:from|join|straight_join|cross\s+join|natural\s+(?:left\s+|right\s+)?(?:outer\s+)?join|inner\s+join|left\s+(?:outer\s+)?join|right\s+(?:outer\s+)?join)
    \s+
    `?([A-Za-z_][A-Za-z0-9_]*)`?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# 逗号分隔正则：匹配 FROM 子句中逗号后面的表名
# 需要在 FROM 后找到逗号，然后提取逗号后的表名
_COMMA_TABLE_RE = re.compile(
    r"""
    \bfrom\b
    [^,]*?                  # FROM 后面直到第一个逗号的内容（可能包含表名和别名）
    (?:,\s*`?([A-Za-z_][A-Za-z0-9_]*)`?)+  # 一个或多个逗号分隔的表名
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _extract_table_refs(query: str) -> set:
    """提取 SQL 中 FROM/JOIN 引用的表名。

    支持：
    - FROM table
    - FROM table1, table2, ...（逗号隐式连接）
    - 各种 JOIN 类型

    注意：提取不全只会「拒绝合法查询」（可接受），不会「放过非法查询」——
    因为判定是"每个引用到的表都必须在可查集合里"，默认拒绝。
    但第二层防线（_scan_never_allowed_tables）会兜住任何提取遗漏。
    """
    if not query:
        return set()

    result = set()

    # 1. 提取 FROM/JOIN 关键字后的表名
    for m in _TABLE_REF_RE.finditer(query):
        result.add(m.group(1).lower())

    # 2. 提取逗号分隔的表名（隐式连接）
    # 需要单独处理，因为正则只匹配最后一个捕获组
    # 改用更简单的方式：找到 FROM 子句中的所有逗号分隔表名
    from_match = re.search(r'\bfrom\b', query, re.IGNORECASE)
    if from_match:
        # 从 FROM 开始到下一个关键字（WHERE/ORDER/GROUP/LIMIT/HAVING/;）
        from_pos = from_match.end()
        rest = query[from_pos:]
        # 找到 FROM 子句的结束位置
        end_match = re.search(
            r'\b(where|order\s+by|group\s+by|having|limit|;|$)\b',
            rest, re.IGNORECASE
        )
        if end_match:
            from_clause = rest[:end_match.start()]
        else:
            from_clause = rest

        # 提取逗号分隔的表名
        # 移除子查询和括号内容，避免误匹配
        from_clause_clean = re.sub(r'\([^)]*\)', '', from_clause)
        # 分割并提取表名
        parts = re.split(r',', from_clause_clean)
        for part in parts:
            # 提取表名（去掉别名和空格）
            part = part.strip()
            # 匹配 `table_name` 或 `table_name alias` 或 `table_name AS alias`
            m = re.match(r'`?([A-Za-z_][A-Za-z0-9_]*)`?', part, re.IGNORECASE)
            if m:
                result.add(m.group(1).lower())

    return result


# ── 第二层防线：Token 级扫描 ──
# 对整条 SQL 做一次扫描，只要出现 _NEVER_ALLOWED_TABLES 里的任意表名
# （作为独立标识符，不被引号/字符串包裹、不是更长标识符的一部分）就直接拒绝
# 这一层不依赖提取器正确性，能兜住任何提取遗漏

# 标识符正则：匹配独立的表名（词边界）
_IDENTIFIER_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\b')


def _scan_never_allowed_tables(query: str) -> Optional[str]:
    """第二层防线：扫描 SQL 中是否出现禁止访问的表名。

    直接对整条 SQL 做词法扫描，查找任何 _NEVER_ALLOWED_TABLES 中的表名。
    这一层不依赖提取器的正确性，能兜住任何提取遗漏。

    Returns:
        如果发现禁止的表名，返回错误信息；否则返回 None。
    """
    if not query:
        return None

    # 预处理：移除字符串字面量和注释，避免误匹配字符串中的表名
    cleaned = query
    # 移除单引号字符串
    cleaned = re.sub(r"'[^']*'", '', cleaned)
    # 移除双引号字符串
    cleaned = re.sub(r'"[^"]*"', '', cleaned)
    # 移除单行注释
    cleaned = re.sub(r'--[^\n]*', '', cleaned)
    # 移除多行注释
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)

    # 扫描标识符
    found_forbidden = []
    for m in _IDENTIFIER_RE.finditer(cleaned):
        identifier = m.group(1).lower()
        if identifier in _NEVER_ALLOWED_TABLES:
            found_forbidden.append(identifier)

    if found_forbidden:
        # 去重并排序
        found_forbidden = sorted(set(found_forbidden))
        return (
            f"[安全拦截] SQL 中包含禁止访问的表: {', '.join(found_forbidden)}\n"
            f"这些表包含敏感数据，禁止通过 SQL 查询。"
        )

    return None


def _validate_tables(query: str) -> Optional[str]:
    """表白名校验（双重防线）。

    第一层：改进的提取器，支持逗号隐式连接和各种 JOIN 类型
    第二层：Token 级扫描，直接拒绝任何 _NEVER_ALLOWED_TABLES 中的表名

    Returns:
        错误信息或 None（允许查询）
    """
    # 第二层防线优先：扫描禁止访问的表名
    # 这一层不依赖提取器，能兜住任何提取遗漏
    forbidden_err = _scan_never_allowed_tables(query)
    if forbidden_err:
        return forbidden_err

    # 第一层：白名单校验
    allowed = _queryable_tables()
    refs = _extract_table_refs(query)
    if not refs:
        return "无法识别查询涉及的表（请显式写出 FROM <表名>）"
    denied = sorted(t for t in refs if t not in allowed)
    if denied:
        return (
            f"表 {', '.join(denied)} 不在可查询白名单内。\n"
            f"当前可查询的表：\n{_queryable_tables_hint()}"
        )
    return None