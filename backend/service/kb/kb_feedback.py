"""
知识库聊天反馈（RAG 评测闭环的入口）

用户在聊天中对助手答案点赞/点踩 → 落库 kb_feedback →
关联该会话最近一次知识库检索的 chunk_ids（kb_retrieval_logs）→
负反馈异步触发优化建议生成（kb_eval_suggestion.generate_from_feedback）。
"""
import json as _json
from typing import List, Optional

from backend.db.schema import get_conn
from backend.utils.log_utils import log, rag

logger = log


class FeedbackInvalid(Exception):
    """反馈参数不合法 → 400"""


class FeedbackNotFound(Exception):
    """会话不存在或不属于当前用户 → 404"""


def _parse_thread_user(thread_id: str) -> Optional[int]:
    """从 thread_id 解析 user_id（web: {user_id}_{ts}；微信: wx_{user_id}_{wxid}）。"""
    if not thread_id:
        return None
    if thread_id.startswith("wx_"):
        parts = thread_id.split("_", 2)
        if len(parts) >= 3:
            try:
                return int(parts[1])
            except ValueError:
                return None
        return None
    if "_" not in thread_id:
        return None
    try:
        return int(thread_id.split("_")[0])
    except ValueError:
        return None


def _thread_belongs_to(thread_id: str, user_id: int) -> bool:
    """会话归属校验：thread_id 前缀优先，conversations 表兜底。"""
    parsed = _parse_thread_user(thread_id)
    if parsed is not None:
        return parsed == int(user_id)
    try:
        from backend.db.conversation_store import ConversationStore
        rows = ConversationStore().get_conversations_by_session(thread_id)
        return any(int(r.get("user_id") or 0) == int(user_id) for r in rows)
    except Exception:
        return False


def _check_conversation_ownership(conversation_id: Optional[int], user_id: int) -> Optional[str]:
    """校验 conversation 归属；返回该会话的 thread_id（session_id）。"""
    if not conversation_id:
        return None
    try:
        from backend.db.conversation_store import ConversationStore
        row = ConversationStore().get_conversation_by_id(int(conversation_id))
    except Exception:
        return None
    if not row:
        raise FeedbackNotFound(f"对话记录不存在: id={conversation_id}")
    if int(row.get("user_id") or 0) != int(user_id):
        raise FeedbackNotFound(f"对话记录不存在: id={conversation_id}")
    return row.get("session_id") or ""


def create_feedback(
    user_id: int,
    conversation_id: Optional[int],
    thread_id: str,
    rating: int,
    comment: str = "",
) -> dict:
    """
    记录一条聊天反馈。

    返回: {"id": feedback_id, "chunk_ids": [...]}
    归属校验：conversation_id 或 thread_id 至少其一能归属到当前用户。
    """
    rating = int(rating)
    if rating not in (1, -1):
        raise FeedbackInvalid("rating 仅支持 1（赞）或 -1（踩）")

    # ── 归属校验（conversation_id 优先，thread_id 兜底）──
    session_id = _check_conversation_ownership(conversation_id, user_id)
    if session_id:
        thread_id = thread_id or session_id
    if not thread_id or not _thread_belongs_to(thread_id, user_id):
        raise FeedbackNotFound("无法校验会话归属，请提供合法的 conversation_id / thread_id")

    # ── 关联最近一次知识库检索（归因 + 用户隔离）──
    from backend.service.kb.kb_retriever import latest_retrieval_chunk_ids
    chunk_ids = latest_retrieval_chunk_ids(thread_id, user_id=user_id)

    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO kb_feedback (user_id, conversation_id, thread_id, rating, comment, retrieved_chunk_ids) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                int(user_id),
                int(conversation_id) if conversation_id else None,
                str(thread_id)[:128],
                rating,
                (comment or "").strip()[:512],
                _json.dumps(chunk_ids),
            ),
        )
        conn.commit()
        feedback_id = cur.lastrowid
    finally:
        conn.close()

    logger.info(f"[KB-Feedback] user={user_id} conv={conversation_id} rating={rating} chunks={len(chunk_ids)}")

    # ── 负反馈异步生成优化建议（fire-and-forget，失败不影响反馈主链路）──
    if rating < 0:
        _schedule_suggestion(feedback_id, user_id)

    return {"id": feedback_id, "chunk_ids": chunk_ids}


def _schedule_suggestion(feedback_id: int, user_id: int) -> None:
    """异步触发建议生成（有事件循环时挂后台任务）。"""
    import asyncio

    try:
        from backend.service.kb.kb_eval_suggestion import generate_from_feedback

        async def _run():
            try:
                await asyncio.to_thread(generate_from_feedback, feedback_id, user_id)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[KB-Feedback] 建议生成失败（静默）: {e}")

        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        # 无事件循环（同步调用场景）→ 直接同步生成
        try:
            from backend.service.kb.kb_eval_suggestion import generate_from_feedback
            generate_from_feedback(feedback_id, user_id)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[KB-Feedback] 建议生成失败（静默）: {e}")


def list_feedback(user_id: int, permissions, page: int = 1, page_size: int = 20) -> dict:
    """反馈列表（kb.manage 看全部，否则只看自己的）。"""
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    offset = (page - 1) * page_size

    where = "WHERE f.user_id = %s"
    params: List = [int(user_id)]
    if "kb.manage" in permissions:
        where = "WHERE 1=1"
        params = []

    conn = get_conn()
    try:
        cur = conn.execute(f"SELECT COUNT(*) AS cnt FROM kb_feedback f {where}", params)
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        total = rows[0]["cnt"] if rows else 0
        cur = conn.execute(
            f"SELECT * FROM kb_feedback f {where} ORDER BY f.id DESC LIMIT %s OFFSET %s",
            params + [page_size, offset],
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    items = [{
        "id": r["id"],
        "user_id": r["user_id"],
        "conversation_id": r.get("conversation_id"),
        "thread_id": r.get("thread_id") or "",
        "rating": r.get("rating", 0),
        "comment": r.get("comment") or "",
        "retrieved_chunk_ids": _json.loads(r["retrieved_chunk_ids"]) if isinstance(r.get("retrieved_chunk_ids"), str) else (r.get("retrieved_chunk_ids") or []),
        "status": r.get("status") or "open",
        "created_at": str(r.get("created_at") or ""),
    } for r in rows]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def delete_feedback(user_id: int, feedback_id: int, permissions) -> dict:
    """
    删除聊天反馈记录。

    权限：只能删除自己的反馈，或 kb.manage 可删除任意反馈。
    """
    conn = get_conn()
    try:
        # 查询反馈记录
        cur = conn.execute("SELECT * FROM kb_feedback WHERE id = %s", (feedback_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        if not rows:
            raise FeedbackNotFound(f"反馈记录不存在: id={feedback_id}")

        fb = rows[0]

        # 权限校验
        if fb["user_id"] != int(user_id) and "kb.manage" not in permissions:
            raise FeedbackNotFound(f"反馈记录不存在: id={feedback_id}")

        # 删除反馈记录
        conn.execute("DELETE FROM kb_feedback WHERE id = %s", (feedback_id,))
        conn.commit()

        logger.info(f"[KB-Feedback] 删除反馈 id={feedback_id} user={user_id}")
        return {"id": feedback_id, "deleted": True}
    finally:
        conn.close()
