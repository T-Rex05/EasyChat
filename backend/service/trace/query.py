"""
LLM 链路可观测性 — 查询功能

提供 trace 列表、详情、按会话轮次聚合等查询功能
"""
from typing import Dict, Any, Optional, List
from decimal import Decimal
from backend.utils.log_utils import log

logger = log


def _conn():
    from backend.db.schema import get_conn
    return get_conn()


def list_traces(
    user_id: int = 0,
    session_id: str = "",
    model: str = "",
    source: str = "",
    status: int = -1,
    days: int = 0,
    start_time=None,
    end_time=None,
    offset: int = 0,
    limit: int = 20,
    manage_mode: bool = False,
) -> Dict[str, Any]:
    """查询 trace 列表（支持多维度筛选）"""
    from backend.utils.time_utils import days_start

    conn = _conn()
    try:
        where = ["1=1"]
        params: list = []

        if user_id:
            where.append("t.user_id = %s")
            params.append(user_id)
        if session_id:
            where.append("t.session_id = %s")
            params.append(session_id)
        if model:
            where.append("t.model = %s")
            params.append(model)
        if source:
            where.append("t.source = %s")
            params.append(source)
        if status >= 0:
            where.append("t.status = %s")
            params.append(status)
        if start_time is not None or end_time is not None:
            if start_time is not None:
                where.append("t.created_at >= %s")
                params.append(start_time)
            if end_time is not None:
                where.append("t.created_at < %s")
                params.append(end_time)
        elif days > 0:
            where.append("t.created_at >= %s")
            params.append(days_start(days))

        where_sql = " AND ".join(where)

        # 总数
        cur = conn.execute(
            f"SELECT COUNT(*) as cnt FROM traces t WHERE {where_sql}", params
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        total = rows[0]["cnt"] if rows else 0

        # 列表
        cur = conn.execute(
            f"""SELECT t.id, t.session_id, t.user_id, t.source, t.model, t.provider,
                       t.turn_index, t.input_tokens, t.output_tokens, t.cache_read_tokens,
                       t.cache_write_tokens, t.reasoning_tokens, t.total_tokens,
                       t.latency_ms, t.estimated_cost_usd, t.finish_reason,
                       t.api_call_count, t.status, t.error_message, t.created_at,
                       (SELECT COUNT(*) FROM trace_spans s WHERE s.trace_id = t.id) as span_count,
                       u.username as username
                FROM traces t
                LEFT JOIN users u ON t.user_id = u.id
                WHERE {where_sql}
                ORDER BY t.created_at DESC
                LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        traces = []
        for r in rows:
            item = dict(r)
            if isinstance(item.get("estimated_cost_usd"), Decimal):
                item["estimated_cost_usd"] = float(item["estimated_cost_usd"])
            if item.get("created_at"):
                item["created_at"] = str(item["created_at"])
            traces.append(item)

        return {"traces": traces, "total": total, "has_more": offset + limit < total}
    finally:
        conn.close()


def get_trace_detail(trace_id: int) -> Optional[Dict[str, Any]]:
    """获取 trace 详情 + 所有 spans"""
    conn = _conn()
    try:
        cur = conn.execute("SELECT * FROM traces WHERE id = %s", (trace_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        if not rows:
            return None
        trace = dict(rows[0])
        if isinstance(trace.get("estimated_cost_usd"), Decimal):
            trace["estimated_cost_usd"] = float(trace["estimated_cost_usd"])
        if trace.get("created_at"):
            trace["created_at"] = str(trace["created_at"])

        # spans
        cur = conn.execute(
            "SELECT * FROM trace_spans WHERE trace_id = %s ORDER BY created_at ASC",
            (trace_id,),
        )
        span_rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        trace["spans"] = []
        for s in span_rows:
            span = dict(s)
            if span.get("created_at"):
                span["created_at"] = str(span["created_at"])
            trace["spans"].append(span)

        return trace
    finally:
        conn.close()


def list_turns(
    user_id: int = 0,
    model: str = "",
    source: str = "",
    status: int = -1,
    days: int = 0,
    start_time=None,
    end_time=None,
    offset: int = 0,
    limit: int = 20,
    manage_mode: bool = False,
    with_text: bool = False,
) -> Dict[str, Any]:
    """按 session_id 聚合 trace，一次用户提问显示为一条记录。

    with_text=True 时为每个 turn 附加 user_question / ai_reply（优先 conversations 表，
    始终落库、不依赖采集开关；回退 traces.prompt_text/completion_text）。
    """
    from backend.utils.time_utils import days_start

    conn = _conn()
    try:
        where = ["1=1"]
        params: list = []

        if user_id:
            where.append("t.user_id = %s")
            params.append(user_id)
        if model:
            where.append("t.model = %s")
            params.append(model)
        if source:
            where.append("t.source = %s")
            params.append(source)
        if status >= 0:
            where.append("t.status = %s")
            params.append(status)
        if start_time is not None or end_time is not None:
            if start_time is not None:
                where.append("t.created_at >= %s")
                params.append(start_time)
            if end_time is not None:
                where.append("t.created_at < %s")
                params.append(end_time)
        elif days > 0:
            where.append("t.created_at >= %s")
            params.append(days_start(days))

        where_sql = " AND ".join(where)

        # 聚合查询：按 session_id 分组（一个会话一行，无论期间用了几个模型）
        cur = conn.execute(
            f"""SELECT t.session_id,
                       t.user_id,
                       t.source,
                       MAX(t.model) as model,
                       MAX(t.provider) as provider,
                       SUM(t.total_tokens) as total_tokens,
                       SUM(t.input_tokens) as input_tokens,
                       SUM(t.output_tokens) as output_tokens,
                       SUM(t.cache_read_tokens) as cache_read_tokens,
                       SUM(t.latency_ms) as total_latency_ms,
                       COUNT(*) as api_calls,
                       MAX(t.status) as status,
                       MIN(t.created_at) as started_at,
                       MAX(t.created_at) as ended_at,
                       (SELECT COUNT(*) FROM trace_spans s
                        JOIN traces t2 ON s.trace_id = t2.id
                        WHERE t2.session_id = t.session_id) as span_count,
                       u.username as username
                FROM traces t
                LEFT JOIN users u ON t.user_id = u.id
                WHERE {where_sql}
                GROUP BY t.session_id, t.user_id, t.source
                ORDER BY ended_at DESC
                LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        turns = []
        for r in rows:
            item = dict(r)
            if item.get("started_at"):
                item["started_at"] = str(item["started_at"])
            if item.get("ended_at"):
                item["ended_at"] = str(item["ended_at"])
            # 计算缓存命中率
            cache_read = int(item.get("cache_read_tokens", 0) or 0)
            input_tok = int(item.get("input_tokens", 0) or 0)
            denom = input_tok + cache_read
            item["cache_hit_rate"] = round(cache_read / denom, 4) if denom > 0 else 0.0
            turns.append(item)

        # 附加用户提问 / AI 回复（conversations 优先，traces 文本回退）
        if with_text and turns:
            _attach_qna(conn, turns)

        # 总数（按 session 去重）
        cur = conn.execute(
            f"SELECT COUNT(DISTINCT t.session_id) as cnt FROM traces t WHERE {where_sql}",
            params,
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        total = rows[0]["cnt"] if rows else 0

        return {"turns": turns, "total": total, "has_more": offset + limit < total}
    finally:
        conn.close()


def _attach_qna(conn, turns: List[Dict[str, Any]]) -> None:
    """为聚合 turns 附加 user_question / ai_reply（conversations 最新一条，traces 文本回退）。"""
    session_ids = [t["session_id"] for t in turns]
    if not session_ids:
        return

    # conversations 表：始终落库（user_question / agent_answer），取每个 session 最新一条有答复的
    ph = ",".join("?" for _ in session_ids)
    best: Dict[str, dict] = {}
    try:
        cur = conn.execute(
            f"""SELECT c.session_id, c.user_question, c.agent_answer
                FROM conversations c
                WHERE c.session_id IN ({ph}) AND c.status = 1
                  AND c.agent_answer IS NOT NULL AND c.agent_answer != ''
                ORDER BY c.created_at DESC""",
            session_ids,
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        for r in rows:
            sid = r["session_id"]
            if sid not in best:
                best[sid] = r
    except Exception:
        pass  # conversations 表不可用时走 traces 回退

    for t in turns:
        sid = t["session_id"]
        row = best.get(sid)
        if row:
            t["user_question"] = (row.get("user_question") or "").strip()
            t["ai_reply"] = (row.get("agent_answer") or "").strip()
            continue
        # 回退：traces.prompt_text / completion_text（全量采集模式开启时才有）
        try:
            cur = conn.execute(
                """SELECT prompt_text, completion_text FROM traces
                   WHERE session_id = %s AND (prompt_text != '' OR completion_text != '')
                   ORDER BY id DESC LIMIT 1""",
                (sid,),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if rows:
                t["user_question"] = (rows[0].get("prompt_text") or "").strip()
                t["ai_reply"] = (rows[0].get("completion_text") or "").strip()
                continue
        except Exception:
            pass
        t["user_question"] = ""
        t["ai_reply"] = ""
