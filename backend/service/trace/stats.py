"""
LLM 链路可观测性 — 统计与清理

提供 Dashboard 统计、排行榜、数据清理等功能

**Redis 缓存**：
- Dashboard 统计：1 分钟 TTL（允许短暂延迟）
- 排行榜：5 分钟 TTL（变化较慢）
"""
from typing import Dict, Any, List
from backend.utils.log_utils import log
from backend.service.trace.config import get_config
from backend.infrastructure import get_cache, get_key_builder

logger = log


def _conn():
    from backend.db.schema import get_conn
    return get_conn()


def get_dashboard_stats(user_id: int = 0, days: int = 7, manage_mode: bool = False) -> Dict[str, Any]:
    """Dashboard 聚合统计（days=自然日：1=今天，N=最近 N 天）

    **缓存**：1 分钟 TTL，减少数据库压力。
    """
    from backend.utils.time_utils import days_start

    # 尝试从缓存获取
    cache = get_cache()
    kb = get_key_builder()
    # 修复：manage_mode 时使用特殊前缀避免与其他用户混淆
    mode = "admin_all" if manage_mode else f"u{user_id}"
    cache_key = kb.build("trace", "dashboard", mode, days)

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 缓存 miss，查数据库
    conn = _conn()
    try:
        cutoff = days_start(days)
        # ⚠️ 条件与参数必须**按同一顺序**构造。
        # 历史事故：params 按 [user_id, cutoff] 排，而 SQL 里写成 `{date_cond} {user_cond}`，
        # 于是 user_id 被拿去和日期比较（`user_id = '2026-08-21 00:00:00'` → 0 行），
        # 日期条件被架空（`created_at >= 1` 恒真）→ 非管理员的 trend/model/source
        # 三段列表**静默全空**，而 summary 因为有数所以看起来"没坏"。
        # 用下面这种"同一循环里成对 append"的写法从结构上杜绝再次错位。
        conds: List[str] = ["1=1"]
        params: List[Any] = []
        if not manage_mode:
            conds.append("AND user_id = %s")
            params.append(int(user_id))
        if cutoff:
            conds.append("AND created_at >= %s")
            params.append(cutoff)
        where_sql = " ".join(conds)

        # 汇总
        cur = conn.execute(f"""
            SELECT
                COUNT(*) as total_traces,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(AVG(latency_ms), 0) as avg_latency_ms,
                COALESCE(SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) / COUNT(*), 0) as success_rate,
                COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
                COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
                COALESCE(SUM(input_tokens), 0) as total_input_tokens
            FROM traces
            WHERE {where_sql}
        """, params)
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        summary = dict(rows[0]) if rows else {}
        summary["avg_latency_ms"] = round(summary.get("avg_latency_ms", 0) or 0)
        summary["success_rate"] = round(float(summary.get("success_rate", 0) or 0), 4)
        summary["total_tokens"] = int(summary.get("total_tokens", 0) or 0)
        summary["total_traces"] = int(summary.get("total_traces", 0) or 0)
        # 缓存命中率：cache_read / (input + cache_read) — 仅 Anthropic 协议系产生
        total_cache_read = int(summary.get("total_cache_read_tokens", 0) or 0)
        total_cache_write = int(summary.get("total_cache_write_tokens", 0) or 0)
        total_input = int(summary.get("total_input_tokens", 0) or 0)
        cache_denominator = total_input + total_cache_read
        cache_hit_rate = (total_cache_read / cache_denominator) if cache_denominator > 0 else 0.0
        summary["total_cache_read_tokens"] = total_cache_read
        summary["total_cache_write_tokens"] = total_cache_write
        summary["cache_hit_rate"] = round(cache_hit_rate, 4)

        daily = _get_daily_trend(conn, user_id, cutoff, manage_mode)
        models = _get_model_usage(conn, user_id, cutoff, manage_mode)
        sources = _get_source_distribution(conn, user_id, cutoff, manage_mode)
        tools = _get_tool_usage(conn, user_id, cutoff, manage_mode)

        result = {
            "summary": summary,
            "daily_trend": daily,
            "model_usage": models,
            "source_distribution": sources,
            "tool_usage": tools,
        }

        # 写入缓存（1min TTL + 10s jitter）
        cache.set_with_jitter(cache_key, result, base_ttl=60, jitter_range=10)

        return result
    finally:
        conn.close()


def _trace_filters(user_id: int, cutoff, manage_mode: bool):
    """构造 traces 表的 WHERE 片段与参数 —— **条件与参数成对生成，顺序必然一致**。

    这是修 stats 参数错位事故后抽出来的公共部分：三段列表查询原先各自手写
    `user_cond`/`date_cond` 再拼 params，顺序一错就把 user_id 拿去和日期比较，
    导致非管理员的 trend/model/source 静默全空。以后不要再手写这两段。
    """
    conds: List[str] = ["1=1"]
    params: List[Any] = []
    if not manage_mode:
        conds.append("AND user_id = %s")
        params.append(int(user_id))
    if cutoff:
        conds.append("AND created_at >= %s")
        params.append(cutoff)
    return " ".join(conds), params


def _get_daily_trend(conn, user_id: int, cutoff, manage_mode: bool) -> list:
    where_sql, params = _trace_filters(user_id, cutoff, manage_mode)
    cur = conn.execute(f"""
        SELECT DATE(created_at) as date,
               SUM(total_tokens) as tokens,
               COUNT(*) as traces,
               COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
               COALESCE(SUM(input_tokens), 0) as input_tokens
        FROM traces
        WHERE {where_sql}
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    """, params)
    rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    result = []
    for r in rows:
        cache_read = int(r["cache_read_tokens"] or 0)
        input_tok = int(r["input_tokens"] or 0)
        denom = input_tok + cache_read
        hit_rate = (cache_read / denom) if denom > 0 else 0.0
        result.append({
            "date": str(r["date"]),
            "tokens": int(r["tokens"] or 0),
            "traces": int(r["traces"] or 0),
            "cache_read_tokens": cache_read,
            "cache_hit_rate": round(hit_rate, 4),
        })
    return result


def _get_model_usage(conn, user_id: int, cutoff, manage_mode: bool) -> list:
    where_sql, params = _trace_filters(user_id, cutoff, manage_mode)
    cur = conn.execute(f"""
        SELECT model,
               COUNT(*) as traces,
               SUM(total_tokens) as tokens
        FROM traces
        WHERE {where_sql}
        GROUP BY model
        ORDER BY tokens DESC
    """, params)
    rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    return [
        {
            "model": r["model"],
            "traces": int(r["traces"]),
            "tokens": int(r["tokens"] or 0),
        }
        for r in rows
    ]


def _get_source_distribution(conn, user_id: int, cutoff, manage_mode: bool) -> list:
    where_sql, params = _trace_filters(user_id, cutoff, manage_mode)
    cur = conn.execute(f"""
        SELECT source, COUNT(*) as traces
        FROM traces
        WHERE {where_sql}
        GROUP BY source
        ORDER BY traces DESC
    """, params)
    rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    total = sum(r["traces"] for r in rows) or 1
    return [
        {
            "source": r["source"],
            "traces": int(r["traces"]),
            "percentage": round(int(r["traces"]) / total * 100, 1),
        }
        for r in rows
    ]


def _get_tool_usage(conn, user_id: int, cutoff, manage_mode: bool) -> list:
    """工具调用统计（按用户隔离）。

    ⚠️ `trace_spans` **没有 user_id 列**，只能经 `trace_id` JOIN `traces` 才能按用户过滤。
    旧实现只过滤日期、完全不看用户 → 普通用户的 dashboard 里"工具分布"其实是
    **全站所有人**的聚合（实测 user_id=2 自己 traces 为 0，却能看到 17 个工具条目），
    与同一面板里其他三段的按用户隔离自相矛盾。
    """
    # 条件与参数成对生成，顺序必然一致（同 _trace_filters 的纪律）
    conds: List[str] = ["1=1"]
    params: List[Any] = []
    if cutoff:
        conds.append("AND s.created_at >= %s")
        params.append(cutoff)
    if not manage_mode:
        conds.append("AND t.user_id = %s")
        params.append(int(user_id))
    where_sql = " ".join(conds)

    cur = conn.execute(f"""
        SELECT s.tool_name,
               COUNT(*) as calls,
               AVG(s.duration_ms) as avg_duration_ms
        FROM trace_spans s
        JOIN traces t ON t.id = s.trace_id
        WHERE {where_sql}
        GROUP BY s.tool_name
        ORDER BY calls DESC
        LIMIT 20
    """, params)
    rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    return [
        {
            "tool": r["tool_name"],
            "calls": int(r["calls"]),
            "avg_duration_ms": round(r["avg_duration_ms"] or 0),
        }
        for r in rows
    ]


def get_user_ranking(days: int = 7, limit: int = 20) -> Dict[str, Any]:
    """按 Token 消耗量排名的用户列表"""
    from backend.utils.time_utils import days_start

    conn = _conn()
    try:
        cutoff = days_start(days)
        date_cond = "AND t.created_at >= %s" if cutoff else ""
        params = [cutoff] if cutoff else []
        cur = conn.execute(f"""
            SELECT t.user_id,
                   u.username,
                   COUNT(*) as traces,
                   SUM(t.total_tokens) as total_tokens,
                   COALESCE(AVG(t.latency_ms), 0) as avg_latency_ms
            FROM traces t
            LEFT JOIN users u ON t.user_id = u.id
            WHERE 1=1 {date_cond}
            GROUP BY t.user_id, u.username
            ORDER BY total_tokens DESC
            LIMIT {int(limit)}
        """, params)
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        ranking = []
        for i, r in enumerate(rows):
            ranking.append({
                "rank": i + 1,
                "user_id": r["user_id"],
                "username": r.get("username") or f"用户{r['user_id']}",
                "traces": int(r["traces"]),
                "total_tokens": int(r["total_tokens"] or 0),
                "avg_latency_ms": round(r["avg_latency_ms"] or 0),
            })
        return {"ranking": ranking, "days": days}
    finally:
        conn.close()


def cleanup_old_traces(days: int = 0) -> int:
    """清理过期的 trace 和 span 数据。days=0 则读取 trace_config 配置。返回删除条数。"""
    if days <= 0:
        try:
            days = int(get_config("trace_retention_days", "30"))
        except (ValueError, TypeError):
            days = 30
    if days <= 0:
        return 0

    conn = _conn()
    try:
        # 先删 spans（外键关联）
        cur = conn.execute(
            "DELETE FROM trace_spans WHERE trace_id IN ("
            "  SELECT id FROM traces WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)"
            ")",
            (days,),
        )
        spans_deleted = cur.rowcount if hasattr(cur, "rowcount") else 0

        # 再删 traces
        cur = conn.execute(
            "DELETE FROM traces WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)",
            (days,),
        )
        traces_deleted = cur.rowcount if hasattr(cur, "rowcount") else 0
        conn.commit()

        total = spans_deleted + traces_deleted
        if total > 0:
            logger.info(f"[TraceCleanup] 清理 {days} 天前数据: {traces_deleted} traces + {spans_deleted} spans")
        return total
    except Exception as e:
        logger.error(f"cleanup_old_traces 失败: {e}")
        return 0
    finally:
        conn.close()


def get_ranking(days: int = 7, limit: int = 20) -> Dict[str, Any]:
    """排行榜 — 基于 daily_user_stats 预聚合表查询。

    **缓存**：5 分钟 TTL。
    """
    from backend.utils.time_utils import days_start

    # 尝试从缓存获取
    cache = get_cache()
    kb = get_key_builder()
    cache_key = kb.build("trace", "ranking", days, limit)

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    conn = _conn()
    try:
        cutoff = days_start(days)
        date_cond = "AND stat_date >= %s" if cutoff else ""
        params = [cutoff.date()] if cutoff else []
        cur = conn.execute(f"""
            SELECT s.user_id,
                   u.username,
                   SUM(s.total_tokens) as total_tokens,
                   SUM(s.api_calls) as api_calls,
                   COUNT(DISTINCT s.stat_date) as active_days
            FROM daily_user_stats s
            LEFT JOIN users u ON s.user_id = u.id
            WHERE 1=1 {date_cond}
            GROUP BY s.user_id, u.username
            ORDER BY total_tokens DESC
            LIMIT {int(limit)}
        """, params)
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        ranking = []
        for i, r in enumerate(rows):
            ranking.append({
                "rank": i + 1,
                "user_id": r["user_id"],
                "username": r.get("username") or f"用户{r['user_id']}",
                "total_tokens": int(r["total_tokens"] or 0),
                "api_calls": int(r["api_calls"] or 0),
                "active_days": int(r["active_days"] or 0),
            })
        result = {"ranking": ranking, "days": days}

        # 写入缓存（5min TTL + 30s jitter）
        cache.set_with_jitter(cache_key, result, base_ttl=300, jitter_range=30)

        return result
    finally:
        conn.close()
