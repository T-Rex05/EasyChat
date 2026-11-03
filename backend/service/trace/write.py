"""
LLM 链路可观测性 — 数据写入

traces 表：每次 LLM API 调用一条记录
trace_spans 表：每次工具调用一条记录
"""
from typing import Dict, Any
from backend.utils.log_utils import log
from backend.service.trace.config import is_detail_enabled, get_max_text_chars

logger = log


def _conn():
    from backend.db.schema import get_conn
    return get_conn()


def _get_session_source(session_id: str) -> str:
    """从 conversations 表获取会话来源渠道。"""
    # 微信会话 ID 前缀直接判定渠道：微信链路是先走 Hermes（TraceObserver 在此
    # 时记 trace）后落库，全新会话第一轮 conversations 表尚无记录，若只查表会
    # 误判为 web。用既有的 wx_ 前缀约定兜底。
    if session_id and session_id.startswith("wx_"):
        return "wechat"
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT source FROM conversations WHERE session_id = %s LIMIT 1",
            (session_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        if rows and rows[0].get("source"):
            return rows[0]["source"]
        return "web"
    except Exception:
        return "web"
    finally:
        conn.close()


def record_trace(
    session_id: str,
    user_id: int,
    api_request_id: str,
    model: str,
    provider: str = "",
    turn_index: int = 0,
    approx_input_tokens: int = 0,
    prompt_text: str = "",
    source_override: str = "",
) -> int:
    """创建 trace 记录（pre_api_request 时调用）。返回 trace_id。"""
    source = source_override if source_override else _get_session_source(session_id)
    # 防御超长 api_request_id
    if api_request_id and len(api_request_id) > 500:
        api_request_id = api_request_id[:500]
    conn = _conn()
    try:
        # 全量模式下保存 prompt
        saved_prompt = ""
        if prompt_text and is_detail_enabled():
            max_chars = get_max_text_chars()
            saved_prompt = prompt_text[:max_chars]

        cur = conn.execute(
            """INSERT INTO traces
               (session_id, user_id, source, api_request_id, model, provider,
                turn_index, input_tokens, status, prompt_text)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 2, %s)""",
            (session_id, user_id, source, api_request_id, model, provider,
             turn_index, approx_input_tokens, saved_prompt),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.error(f"record_trace 失败: {e}")
        return 0
    finally:
        conn.close()


def update_trace(
    api_request_id: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    reasoning_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: int = 0,
    estimated_cost_usd: float = 0,
    finish_reason: str = "",
    api_call_count: int = 0,
    completion_text: str = "",
) -> None:
    """更新 trace 记录（post_api_request 时调用）"""
    if api_request_id and len(api_request_id) > 500:
        api_request_id = api_request_id[:500]
    conn = _conn()
    try:
        updates: Dict[str, Any] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_write_tokens": cache_write_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
            "estimated_cost_usd": estimated_cost_usd,
            "finish_reason": finish_reason,
            "api_call_count": api_call_count,
            "status": 1,  # 成功
        }
        if completion_text and is_detail_enabled():
            max_chars = get_max_text_chars()
            updates["completion_text"] = completion_text[:max_chars]

        sets = ", ".join(f"{k} = %s" for k in updates)
        vals = list(updates.values()) + [api_request_id]
        conn.execute(f"UPDATE traces SET {sets} WHERE api_request_id = %s", vals)

        # 累加用户 token 统计（user_token_stats 已废弃，统一由 daily_user_stats 聚合）
        if total_tokens is not None and total_tokens > 0:
            cur = conn.execute(
                "SELECT user_id FROM traces WHERE api_request_id = %s LIMIT 1",
                (api_request_id,),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if rows:
                uid = rows[0]["user_id"]
                # 累加每日用户统计（排行榜数据源）
                if uid:
                    conn.execute(
                        """INSERT INTO daily_user_stats (stat_date, user_id, total_tokens, api_calls)
                           VALUES (CURDATE(), %s, %s, 1)
                           ON DUPLICATE KEY UPDATE
                             total_tokens = total_tokens + %s,
                             api_calls = api_calls + 1""",
                        (uid, total_tokens, total_tokens),
                    )
        conn.commit()
    except Exception as e:
        logger.error(f"update_trace 失败: {e}")
    finally:
        conn.close()


def mark_trace_error(api_request_id: str, error_message: str) -> None:
    """标记 trace 失败（api_request_error 时调用）"""
    if api_request_id and len(api_request_id) > 500:
        api_request_id = api_request_id[:500]
    conn = _conn()
    try:
        conn.execute(
            "UPDATE traces SET status = 0, error_message = %s WHERE api_request_id = %s",
            (error_message[:500], api_request_id),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"mark_trace_error 失败: {e}")
    finally:
        conn.close()


def sync_trace_texts(session_id: str, user_question: str, agent_answer: str) -> None:
    """将用户问题和 AI 最终回复写入该会话的最后一条 trace 记录。

    在对话完成后调用，替代原始 LLM API 的 prompt/completion（含系统提示词等噪音）。
    """
    if not session_id:
        return
    conn = _conn()
    try:
        # 找到该会话最新的一条 trace
        cur = conn.execute(
            "SELECT id FROM traces WHERE session_id = %s ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        if not rows:
            return
        trace_id = rows[0]["id"]

        # 截断过长文本
        max_chars = get_max_text_chars() if is_detail_enabled() else 0
        prompt = user_question[:max_chars] if max_chars and user_question else ""
        completion = agent_answer[:max_chars] if max_chars and agent_answer else ""

        conn.execute(
            "UPDATE traces SET prompt_text = %s, completion_text = %s WHERE id = %s",
            (prompt, completion, trace_id),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"sync_trace_texts 失败: {e}")
    finally:
        conn.close()


def record_span(
    trace_id: int,
    tool_name: str,
    duration_ms: int = 0,
    status: int = 1,
    error_message: str = "",
    span_type: str = "tool_call",
) -> int:
    """创建 trace_span 记录（post_tool_call 时调用）。返回 span_id。"""
    if not trace_id:
        return 0
    conn = _conn()
    try:
        cur = conn.execute(
            """INSERT INTO trace_spans
               (trace_id, span_type, tool_name, duration_ms, status, error_message)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (trace_id, span_type, tool_name, duration_ms, status,
             error_message[:500] if error_message else ""),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.error(f"record_span 失败: {e}")
        return 0
    finally:
        conn.close()
