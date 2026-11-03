"""微信监听器 - 会话管理"""
import time
from backend.controller.wechat.config import (
    _get_conn, _wx_active_session, _wx_session_titles
)


def _get_session_id(user_id: int, wx_user_id: str) -> str:
    """获取会话ID"""
    return f"wx_{user_id}_{wx_user_id[:12]}"


def _new_session_key(user_id: int, wx_user_id: str) -> str:
    """生成新的会话键"""
    ts = str(int(time.time()))[-8:]
    return f"wx_{user_id}_{wx_user_id[:8]}_{ts}"


def _skey(user_id: int, wx_user_id: str) -> str:
    """生成会话存储键"""
    return f"{user_id}:{wx_user_id}"


def _get_active_session(user_id: int, wx_user_id: str) -> str:
    """获取当前活跃会话"""
    key = _skey(user_id, wx_user_id)
    if key not in _wx_active_session:
        _wx_active_session[key] = {"session_id": _get_session_id(user_id, wx_user_id), "last_active": time.time()}
    else:
        _wx_active_session[key]["last_active"] = time.time()
    return _wx_active_session[key]["session_id"]


def _set_active_session(user_id: int, wx_user_id: str, sid: str):
    """设置活跃会话"""
    _wx_active_session[_skey(user_id, wx_user_id)] = {"session_id": sid, "last_active": time.time()}


def _get_user_sessions(user_id: int, limit: int = 10) -> list[dict]:
    """获取用户的会话列表"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT session_id, MIN(created_at) as first_time, MAX(created_at) as last_time, COUNT(*) as msg_count "
            "FROM conversations WHERE user_id = %s AND source = 'wechat' AND status != 0 "
            "GROUP BY session_id ORDER BY last_time DESC LIMIT %s", (user_id, limit))
        rows = cur.fetchall()
        result = []
        for r in rows:
            title = r["session_id"]
            cur.execute(
                "SELECT user_question FROM conversations WHERE session_id = %s AND user_question != '' "
                "ORDER BY created_at ASC LIMIT 1", (r["session_id"],))
            first = cur.fetchone()
            if first:
                title = first["user_question"][:30]
            # 有自定义标题就用自定义的
            custom = _wx_session_titles.get(r["session_id"])
            if custom:
                title = custom["title"]
                custom["last_active"] = time.time()
            result.append({
                "session_id": r["session_id"],
                "title": title,
                "first_time": str(r["first_time"]),
                "last_time": str(r["last_time"]),
                "msg_count": r["msg_count"]
            })
        return result
    except Exception as e:
        import logging
        logging.getLogger("agentforge.wechat_listener").error(f"获取会话列表失败: {e}")
        return []
    finally:
        conn.close()
