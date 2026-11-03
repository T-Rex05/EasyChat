"""
数据持久化控制器 - 负责对话历史和配置的数据库存储
提供 /api/data 前缀的端点，与前端 API 配置对应
"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Header, Depends

from backend.utils.log_utils import log

logger = log

# 创建路由器
data_router = APIRouter(prefix="/api/data", tags=["数据存储"])

# 数据库连接实例（与 chat_controller 共享）
_db_conn = None


def _get_db_conn():
    """获取数据库连接 — 每次从连接池获取新连接，避免缓存过期连接"""
    try:
        from backend.db.connection_pool import get_pool_connection
        return get_pool_connection()
    except Exception as e:
        logger.warning(f"获取数据库连接失败: {e}")
        return None


def init_data_controller(conv_mapper=None):
    """初始化数据控制器"""
    global _db_conn
    if conv_mapper and hasattr(conv_mapper, '_get'):
        _db_conn = conv_mapper._get()
    logger.info("数据持久化控制器初始化完成")


# ── 认证依赖（统一走 auth_middleware，避免多份重复实现） ──
from backend.service.auth.auth_middleware import get_current_user as _get_current_user


# ============ API端点 ============

@data_router.get("/sessions")
async def get_all_sessions(
    user_id: Optional[int] = None,
    offset: int = 0,
    limit: int = 50,
    session_type: str = "conversation",
    current_user: dict = Depends(_get_current_user),
) -> Dict[str, Any]:
    """获取用户的会话列表（支持分页）

    注意：user_id 必须与当前登录用户一致，防止越权访问
    """
    # 强制使用当前登录用户的 ID，防止越权
    actual_user_id = current_user.get("user_id") or user_id
    if not actual_user_id:
        raise HTTPException(status_code=400, detail="用户 ID 无效")

    conn = _get_db_conn()
    if not conn:
        return {"sessions": [], "offset": offset, "limit": limit, "session_type": session_type, "has_more": False}

    # 限制最大每页数量
    if limit > 100:
        limit = 100
    if limit < 1:
        limit = 50
    if offset < 0:
        offset = 0

    session_type = (session_type or "conversation").strip().lower()
    if session_type not in {"all", "conversation", "schedule", "ide"}:
        session_type = "conversation"

    try:
        cur = conn.cursor()

        # 构建 WHERE 条件 - 强制按当前登录用户过滤（参数化查询防注入）
        where_clause = "WHERE c.status != 0 AND c.user_id = %s"
        where_params = [int(actual_user_id)]

        # IDE 会话通过 chat_mode 字段过滤
        if session_type == "ide":
            where_clause += " AND c.chat_mode = 'ide'"

        # 注意：定时任务会话的判定在下方 Python 侧完成（display_title 前缀，见 is_schedule）；
        # 这里曾有一个 SQL 表达式 `is_schedule_expr`，但从未被拼进查询（死代码），
        # 且其内联的 `%` 一旦被拼入参数化查询就会触发 pymysql 的
        # `TypeError: not enough arguments for format string`，故删除。

        # 获取会话列表 — 加 MAX(c.source) 区分渠道来源
        cur.execute(f"""\
            SELECT
                c.session_id,
                MAX(c.chat_mode) as chat_mode,
                MAX(c.source) as source,
                MAX(c.updated_at) as update_time,
                MIN(c.created_at) as create_time,
                MAX(c.id) as max_conv_id,
                MIN(c.id) as min_conv_id
            FROM conversations c
            {where_clause}
            GROUP BY c.session_id
            ORDER BY update_time DESC
            LIMIT %s OFFSET %s
        """, tuple(where_params) + (limit, offset))

        rows = cur.fetchall()
        if not rows:
            conn.close()
            return {"sessions": [], "offset": offset, "limit": limit, "session_type": session_type, "has_more": False}

        session_ids = [r["session_id"] for r in rows]
        placeholders = ','.join(['%s'] * len(session_ids))

        # 获取每个会话的第一条非空对话作为标题，并优先采用用户自定义标题 session_title
        # 注意：GROUP BY 时 ORDER BY 只能用聚合列，避免 ONLY_FULL_GROUP_BY 报错
        cur.execute(f"""\
            SELECT
                session_id,
                user_question,
                MAX(session_title) AS session_title
            FROM conversations
            WHERE session_id IN ({placeholders})
              AND user_question != ''
            GROUP BY session_id, user_question
            ORDER BY MIN(created_at) ASC
        """, session_ids)

        title_map = {}
        custom_title_map = {}
        for r in cur.fetchall():
            sid = r["session_id"]
            # 收集用户自定义标题：只要任一记录设置了即为会话标题
            st = r.get("session_title")
            if st:
                custom_title_map.setdefault(sid, st)
            # 收集首条非空 question 作为兜底标题
            if sid not in title_map:
                title_map[sid] = r["user_question"][:50] if r["user_question"] else ""

        sessions = []
        for row in rows:
            # 标题优先级：自定义 session_title > 首条 user_question
            display_title = custom_title_map.get(row["session_id"]) or title_map.get(row["session_id"], row["session_id"])
            source = row.get("source", "web") or "web"

            # 微信会话标题加图标标识
            if source == "wechat":
                display_title = "💬 " + display_title

            is_schedule = 1 if (display_title.startswith("【定时任务】") or
                                display_title.startswith("[定时任务]")) else 0

            # 根据 session_type 过滤
            if session_type == "schedule" and not is_schedule:
                continue
            if session_type == "conversation" and is_schedule:
                continue

            sessions.append({
                "id": row["session_id"],
                "session_id": row["session_id"],
                "chat_mode": row.get("chat_mode", "normal"),
                "source": source,
                "user_question": display_title,
                "title": display_title,
                "start_time": str(row["create_time"]) if row["create_time"] else "",
                "end_time": str(row["update_time"]) if row["update_time"] else "",
                "update_time": str(row["update_time"]) if row["update_time"] else "",
                "create_time": str(row["create_time"]) if row["create_time"] else "",
                "message_count": 0,
                "is_schedule": is_schedule,
                "last_status": 1
            })

        # 检查是否还有更多
        has_more = len(sessions) >= limit

        return {
            "sessions": sessions,
            "offset": offset,
            "limit": limit,
            "session_type": session_type,
            "has_more": has_more
        }
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        return {"sessions": [], "offset": offset, "limit": limit, "session_type": session_type, "has_more": False}
    finally:
        if conn:
            conn.close()


@data_router.get("/conversations/user/{user_id}")
async def get_conversations_by_user(user_id: int, limit: int = 50, current_user: dict = Depends(_get_current_user)) -> List[Dict[str, Any]]:
    """根据用户ID获取对话记录（仅本人；持有 trace.manage 权限可查看任意用户）"""
    # 权限检查：本人或有 trace.manage 权限
    perms = current_user.get("permissions") or set()
    if isinstance(perms, list):
        perms = set(perms)
    if int(user_id) != int(current_user.get("user_id")) and "trace.manage" not in perms:
        raise HTTPException(status_code=403, detail="无权查看该用户的对话")
    conn = _get_db_conn()
    if not conn:
        return []

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, session_id, user_id, user_question, agent_answer, status, created_at, updated_at FROM conversations WHERE user_id = %s AND status != 0 ORDER BY created_at DESC LIMIT %s",
            (int(user_id), min(limit, 100)),
        )
        rows = cur.fetchall()
        return [
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "user_id": r["user_id"],
                "user_question": r["user_question"] or "",
                "agent_answer": r["agent_answer"] or "",
                "status": r["status"],
                "create_time": str(r["created_at"]) if r["created_at"] else "",
                "update_time": str(r["updated_at"]) if r["updated_at"] else "",
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"获取用户对话记录失败: {e}")
        return []
    finally:
        if conn:
            conn.close()


@data_router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, current_user: dict = Depends(_get_current_user)) -> Dict[str, Any]:
    """软删除会话记录（标记 status=0）。仅允许删除属于当前用户的会话。"""
    user_id = current_user.get("user_id")
    conn = _get_db_conn()
    if not conn:
        raise HTTPException(status_code=500, detail="数据层未初始化")

    try:
        cur = conn.cursor()
        # 归属校验：会话必须属于当前用户
        cur.execute("SELECT user_id FROM conversations WHERE session_id = %s LIMIT 1", (session_id,))
        row = cur.fetchone()
        if row and int(row.get("user_id") or 0) != int(user_id):
            raise HTTPException(status_code=403, detail="无权删除该会话")
        # 软删除：标记 conversations status = 0
        cur.execute("UPDATE conversations SET status = 0 WHERE session_id = %s AND user_id = %s", (session_id, user_id))
        conn.commit()
        return {"success": True, "message": "会话已删除"}
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@data_router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int, current_user: dict = Depends(_get_current_user)) -> Dict[str, Any]:
    """软删除对话记录（标记 status=0）。仅允许删除属于当前用户的对话。"""
    user_id = current_user.get("user_id")
    conn = _get_db_conn()
    if not conn:
        raise HTTPException(status_code=500, detail="数据层未初始化")

    try:
        cur = conn.cursor()
        cur.execute("UPDATE conversations SET status = 0 WHERE id = %s AND user_id = %s", (conversation_id, user_id))
        conn.commit()
        return {"success": True, "message": "对话已删除"}
    except Exception as e:
        logger.error(f"删除对话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@data_router.get("/model-configs/user/{user_id}")
async def get_model_configs_by_user(user_id: int) -> List[Dict[str, Any]]:
    """获取用户的所有模型配置"""
    return []


@data_router.get("/model-configs/user/{user_id}/list")
async def get_model_configs_list(user_id: int) -> Dict[str, Any]:
    """获取用户的模型配置列表"""
    return {"success": True, "configs": [], "count": 0, "is_admin": False}


@data_router.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "message": "数据持久化服务正常"}
