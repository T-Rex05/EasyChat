"""
LLM 链路可观测性 — REST API 端点

端点清单:
  GET  /api/traces/dashboard     Dashboard 聚合统计
  GET  /api/traces               当前用户的 trace 列表
  GET  /api/traces/all           所有用户的 trace（trace.manage）
  GET  /api/traces/ranking       排行榜（trace.view —— 原 trace.ranking 已并入）
  GET  /api/traces/users/search  搜索用户（trace.manage）
  GET  /api/traces/{id}          trace 详情 + spans
  GET  /api/traces/config        获取采集配置（trace.manage）
  PUT  /api/traces/config        更新采集配置（trace.manage）
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from backend.service.trace import trace_service
from backend.service.auth.auth_middleware import get_current_user
from backend.utils.log_utils import log

logger = log

router = APIRouter(prefix="/api/traces", tags=["可观测性"])


# ── Pydantic Models ──

class TraceConfigUpdate(BaseModel):
    trace_detail_enabled: Optional[bool] = None
    trace_max_text_chars: Optional[int] = None
    trace_retention_days: Optional[int] = None


def _is_manage(user: dict) -> bool:
    """判断当前用户是否有 trace.manage 权限"""
    role = user.get("role", "")
    if role in ("super_admin", "admin"):
        return True
    perms = user.get("permissions") or set()
    if isinstance(perms, list):
        perms = set(perms)
    return "trace.manage" in perms


# ── Dashboard ──

@router.get("/dashboard")
async def dashboard(
    days: int = Query(default=7, ge=0, le=365),
    user: dict = Depends(get_current_user),
):
    """Dashboard 聚合统计数据"""
    try:
        uid = user.get("user_id", 0)
        manage = _is_manage(user)
        return trace_service.get_dashboard_stats(user_id=uid, days=days, manage_mode=manage)
    except Exception as e:
        logger.error(f"Dashboard 统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Trace 列表 ──

@router.get("")
async def list_traces(
    model: str = Query(default=""),
    source: str = Query(default=""),
    status: int = Query(default=-1),
    days: int = Query(default=0, ge=0),
    when: str = Query(default="", description="自然语言时间短语（今天/本周/本月/最近7天...）"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """当前用户的 trace 列表（按会话轮次聚合）。when 参数优先于 days。"""
    try:
        uid = user.get("user_id", 0)
        start_time = end_time = None
        if when and when.strip():
            from backend.utils.when_resolver import resolve_when
            start_time, end_time = resolve_when(when.strip())
            days = 0  # when 优先
        return trace_service.list_turns(
            user_id=uid, model=model,
            source=source, status=status, days=days,
            start_time=start_time, end_time=end_time, offset=offset, limit=limit,
        )
    except Exception as e:
        logger.error(f"列出 trace 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all")
async def list_all_traces(
    user_id: int = Query(default=0),
    username: str = Query(default=""),
    session_id: str = Query(default=""),
    model: str = Query(default=""),
    source: str = Query(default=""),
    status: int = Query(default=-1),
    days: int = Query(default=0, ge=0),
    when: str = Query(default="", description="自然语言时间短语（本周/本月/最近7天...），优先于 days"),
    aggregated: int = Query(default=1, ge=0, le=1, description="1=按会话聚合（含用户问题/AI回复），0=原始 LLM 调用记录"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """所有用户的 trace 列表（trace.manage 权限）。

    aggregated=1（默认）：按 session 聚合，一次问答一条，附 user_question/ai_reply。
    aggregated=0：原始每次 LLM 调用记录（兼容旧前端）。
    """
    if not _is_manage(user):
        raise HTTPException(status_code=403, detail="需要 trace.manage 权限")
    try:
        # 如果按用户名搜索，先查出 user_id
        search_uid = user_id
        if username and not search_uid:
            from backend.db.schema import get_conn
            conn = get_conn()
            try:
                cur = conn.execute(
                    "SELECT id FROM users WHERE username LIKE %s LIMIT 1",
                    (f"%{username}%",),
                )
                rows = cur.fetchall() if hasattr(cur, "fetchall") else []
                if rows:
                    search_uid = rows[0]["id"]
                else:
                    return {"turns": [], "traces": [], "total": 0, "has_more": False}
            finally:
                conn.close()

        start_time = end_time = None
        when_str = when if isinstance(when, str) else ""
        if when_str.strip():
            from backend.utils.when_resolver import resolve_when
            start_time, end_time = resolve_when(when_str.strip())
            days = 0  # when 优先

        if aggregated:
            result = trace_service.list_turns(
                user_id=search_uid, model=model,
                source=source, status=status, days=days,
                start_time=start_time, end_time=end_time,
                offset=offset, limit=limit,
                manage_mode=True, with_text=True,
            )
            result["traces"] = []  # 兼容旧前端字段
            return result
        return trace_service.list_traces(
            user_id=search_uid, session_id=session_id, model=model,
            source=source, status=status, days=days,
            start_time=start_time, end_time=end_time, offset=offset, limit=limit,
            manage_mode=True,
        )
    except Exception as e:
        logger.error(f"列出全部 trace 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ranking")
async def ranking(
    days: int = Query(default=7, ge=0, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """排行榜 — 基于 daily_user_stats（trace.view 权限）

    注：`trace.ranking` 已合并进 `trace.view`（查看排行榜并入查看链路），
    持有旧 key 的角色由 `registry.seed_to_db()` 的先授后删自动迁移。
    """
    perms = user.get("permissions") or set()
    if isinstance(perms, list):
        perms = set(perms)
    if "trace.view" not in perms:
        raise HTTPException(status_code=403, detail="需要 trace.view 权限")
    try:
        return trace_service.get_ranking(days=days, limit=limit)
    except Exception as e:
        logger.error(f"排行榜查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/search")
async def search_users(
    q: str = Query(default="", max_length=50),
    limit: int = Query(default=10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """搜索用户（trace.manage 权限）"""
    if not _is_manage(user):
        raise HTTPException(status_code=403, detail="需要 trace.manage 权限")
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT id, username FROM users WHERE username LIKE %s AND status = 1 LIMIT %s",
                (f"%{q}%", limit),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return [{"id": r["id"], "username": r["username"]} for r in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"用户搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/turns/{session_id}")
async def turn_detail(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """按 session_id 获取轮次详情（聚合所有 API 调用 + 用户提问/AI 回复）"""
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            # 聚合统计
            cur = conn.execute(
                """SELECT MAX(t.user_id) as user_id, MAX(t.model) as model, MAX(t.source) as source,
                          SUM(t.total_tokens) as total_tokens,
                          SUM(t.input_tokens) as input_tokens,
                          SUM(t.output_tokens) as output_tokens,
                          SUM(t.cache_read_tokens) as cache_read_tokens,
                          SUM(t.cache_write_tokens) as cache_write_tokens,
                          SUM(t.reasoning_tokens) as reasoning_tokens,
                          SUM(t.latency_ms) as total_latency_ms,
                          COUNT(*) as api_calls,
                          MIN(t.created_at) as started_at,
                          MAX(t.created_at) as ended_at
                   FROM traces t WHERE t.session_id = %s""",
                (session_id,),
            )
            row = cur.fetchone() if hasattr(cur, "fetchone") else None
            if not row:
                raise HTTPException(status_code=404, detail="轮次不存在")
            detail = dict(row)

            # 权限检查
            if not _is_manage(user) and detail.get("user_id") != user.get("user_id"):
                raise HTTPException(status_code=403, detail="无权查看")

            # 取最新一条 trace 的 prompt_text / completion_text（用户提问 + AI 回复）
            cur = conn.execute(
                """SELECT prompt_text, completion_text FROM traces
                   WHERE session_id = %s AND (prompt_text != '' OR completion_text != '')
                   ORDER BY id DESC LIMIT 1""",
                (session_id,),
            )
            text_row = cur.fetchone() if hasattr(cur, "fetchone") else None
            if text_row:
                detail["prompt_text"] = text_row.get("prompt_text", "") or ""
                detail["completion_text"] = text_row.get("completion_text", "") or ""
            else:
                detail["prompt_text"] = ""
                detail["completion_text"] = ""

            # 获取 spans（工具调用链）— 相同工具合并，统计调用次数/总时长
            cur = conn.execute(
                """SELECT s.tool_name,
                          COUNT(*) as calls,
                          SUM(s.duration_ms) as total_duration_ms,
                          AVG(s.duration_ms) as avg_duration_ms,
                          MAX(s.status) as status,
                          MIN(s.created_at) as first_at,
                          MAX(s.created_at) as last_at
                   FROM trace_spans s
                   JOIN traces t ON s.trace_id = t.id
                   WHERE t.session_id = %s
                   GROUP BY s.tool_name
                   ORDER BY MIN(s.created_at) ASC""",
                (session_id,),
            )
            spans = cur.fetchall() if hasattr(cur, "fetchall") else []
            detail["spans"] = []
            for s in spans:
                span = dict(s)
                if span.get("first_at"):
                    span["first_at"] = str(span["first_at"])
                if span.get("last_at"):
                    span["last_at"] = str(span["last_at"])
                detail["spans"].append(span)

            # 该会话全部问答轮次（conversations 表，始终落库，不依赖采集开关）
            try:
                cur = conn.execute(
                    """SELECT c.user_question, c.agent_answer, c.created_at
                       FROM conversations c
                       WHERE c.session_id = %s AND c.status = 1
                         AND c.agent_answer IS NOT NULL AND c.agent_answer != ''
                       ORDER BY c.created_at ASC
                       LIMIT 200""",
                    (session_id,),
                )
                qna_rows = cur.fetchall() if hasattr(cur, "fetchall") else []
                detail["qna_list"] = []
                for q in qna_rows:
                    detail["qna_list"].append({
                        "question": (q.get("user_question") or "").strip(),
                        "reply": (q.get("agent_answer") or "").strip(),
                        "created_at": str(q.get("created_at") or ""),
                    })
            except Exception:
                detail["qna_list"] = []

            # 获取该会话中有内容回复的子 trace（过滤纯思考过程）
            cur = conn.execute(
                """SELECT id, turn_index, model, total_tokens, input_tokens, output_tokens,
                          cache_read_tokens, cache_write_tokens, reasoning_tokens,
                          latency_ms, finish_reason, api_call_count, status,
                          prompt_text, completion_text, created_at
                   FROM traces WHERE session_id = %s AND completion_text != ''
                   ORDER BY created_at ASC""",
                (session_id,),
            )
            sub_traces = cur.fetchall() if hasattr(cur, "fetchall") else []
            detail["traces"] = []
            for st in sub_traces:
                t = dict(st)
                if t.get("created_at"):
                    t["created_at"] = str(t["created_at"])
                detail["traces"].append(t)

            # 格式化时间
            for k in ("started_at", "ended_at"):
                if detail.get(k):
                    detail[k] = str(detail[k])

            return detail
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取轮次详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Trace 详情 ──

@router.get("/{trace_id}")
async def trace_detail(trace_id: int, user: dict = Depends(get_current_user)):
    """trace 详情 + spans"""
    try:
        detail = trace_service.get_trace_detail(trace_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Trace 不存在")

        # 权限检查：非管理员只能看自己的
        if not _is_manage(user) and detail.get("user_id") != user.get("user_id"):
            raise HTTPException(status_code=403, detail="无权查看此 trace")
        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 trace 详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 配置管理 ──

@router.get("/config/me")
async def get_config(user: dict = Depends(get_current_user)):
    """获取采集配置（trace.manage 权限）"""
    if not _is_manage(user):
        raise HTTPException(status_code=403, detail="需要 trace.manage 权限")
    try:
        config = trace_service.get_all_config()
        return {
            "trace_detail_enabled": config.get("trace_detail_enabled", "false") == "true",
            "trace_max_text_chars": int(config.get("trace_max_text_chars", "10000")),
            "trace_retention_days": int(config.get("trace_retention_days", "30")),
        }
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config")
async def update_config(
    body: TraceConfigUpdate,
    user: dict = Depends(get_current_user),
):
    """更新采集配置（trace.manage 权限）"""
    if not _is_manage(user):
        raise HTTPException(status_code=403, detail="需要 trace.manage 权限")
    try:
        if body.trace_detail_enabled is not None:
            trace_service.set_config(
                "trace_detail_enabled",
                "true" if body.trace_detail_enabled else "false",
            )
        if body.trace_max_text_chars is not None:
            clamped = max(1000, min(100000, body.trace_max_text_chars))
            trace_service.set_config("trace_max_text_chars", str(clamped))
        if body.trace_retention_days is not None:
            clamped = max(1, min(365, body.trace_retention_days))
            trace_service.set_config("trace_retention_days", str(clamped))
        return {"success": True}
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
