"""SQL 案例入库服务（已废弃）

注：SQL 案例审核功能已移除，点赞不触发入库。
此文件保留供历史记录处理，不再主动使用。
"""
import json
import re
import time
from typing import Optional

from backend.utils.log_utils import log

logger = log


def _fetch_conversation(conversation_id: Optional[int], thread_id: str) -> Optional[dict]:
    """从 conversations 表取对话（用户问题 + AI 回复）。"""
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            if conversation_id:
                cur = conn.execute(
                    "SELECT id, session_id, user_question, agent_answer, created_at "
                    "FROM conversations WHERE id = ? LIMIT 1",
                    (int(conversation_id),),
                )
            elif thread_id:
                cur = conn.execute(
                    "SELECT id, session_id, user_question, agent_answer, created_at "
                    "FROM conversations WHERE session_id = ? AND agent_answer != '' "
                    "ORDER BY id DESC LIMIT 1",
                    (thread_id,),
                )
            else:
                return None
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if not rows:
                return None
            row = rows[0]
            return {
                "id": row.get("id"),
                "session_id": row.get("session_id") or thread_id,
                "user_question": row.get("user_question") or "",
                "agent_answer": row.get("agent_answer") or "",
                "created_at": str(row.get("created_at") or ""),
            }
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"[SQL-Case] 查询对话失败: {e}")
        return None


def _fetch_sqls(thread_id: str) -> list:
    """从 sql_operation_logs 表取该会话执行过的 SQL（只取成功的）。"""
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT query, status, error_message FROM sql_operation_logs "
                "WHERE thread_id = ? AND query IS NOT NULL AND query != '' AND status = 1 "
                "ORDER BY id ASC",
                (thread_id,),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return [
                {
                    "query": r.get("query") or "",
                    "status": r.get("status", 1),
                    "error_message": r.get("error_message") or "",
                }
                for r in rows
            ]
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"[SQL-Case] 查询 SQL 记录失败: {e}")
        return []


def _extract_table_refs(sql: str) -> list:
    """从 SQL 中提取涉及的表名（FROM/JOIN/UPDATE/INSERT INTO 后的表名）。"""
    refs = []
    if not sql:
        return refs
    # 匹配 FROM / JOIN / INTO / UPDATE 后的表名
    pattern = re.compile(
        r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+`?([a-zA-Z_][a-zA-Z0-9_]*)`?",
        re.IGNORECASE,
    )
    for m in pattern.finditer(sql):
        table = m.group(1)
        if table not in refs:
            refs.append(table)
    return refs[:20]


def _build_case_markdown(conv: dict, sqls: list, user_id: int, comment: str = "") -> str:
    """生成 SQL 案例 markdown（对齐 Eyes good 案例格式）。"""
    question = (conv.get("user_question") or "").strip()[:200]
    answer = (conv.get("agent_answer") or "").strip()
    theme = question[:60] or "TextToSQL 案例"

    lines = [f"## 【示例：{theme}】", ""]
    lines.append("### 原始问题")
    lines.append(question or "-")
    lines.append("")

    # 涉及表
    all_refs = []
    for s in sqls:
        for t in _extract_table_refs(s.get("query") or ""):
            if t not in all_refs:
                all_refs.append(t)
    if all_refs:
        lines.append("### 涉及表")
        lines.append("| 表名 | 说明 |")
        lines.append("|------|------|")
        for t in all_refs:
            lines.append(f"| {t} | 关联表 |")
        lines.append("")

    # SQL
    if sqls:
        lines.append("### 生成SQL")
        for s in sqls:
            sql_text = (s.get("query") or "").strip()
            if not sql_text:
                continue
            lines.append("```sql")
            lines.append(sql_text)
            lines.append("```")
            lines.append("")

    # AI 回复
    if answer:
        lines.append("### AI完整回复")
        lines.append(answer[:1000])
        lines.append("")

    # 反馈信息
    lines.append("### 反馈信息")
    lines.append(f"- 反馈类型: good")
    lines.append(f"- 用户ID: {user_id}")
    if comment:
        lines.append(f"- 评论: {comment[:200]}")
    lines.append("")

    return "\n".join(lines)


def submit_sql_case_for_review(
    user_id: int,
    conversation_id: Optional[int] = None,
    thread_id: str = "",
    comment: str = "",
) -> dict:
    """把一条点👍的对话 + SQL 提交审核（写入 content_pool）。

    Returns:
        {"ok": bool, "pool_id": int|None, "message": str}
    """
    thread_id = (thread_id or "").strip()
    conv = _fetch_conversation(conversation_id, thread_id)
    if not conv:
        return {"ok": False, "pool_id": None, "message": "未找到对应对话记录"}

    effective_thread = conv.get("session_id") or thread_id
    sqls = _fetch_sqls(effective_thread)
    if not sqls:
        return {"ok": False, "pool_id": None, "message": "该对话没有执行成功的 SQL 记录，跳过入库"}

    markdown = _build_case_markdown(conv, sqls, user_id, comment)

    # 写入 content_pool (status=pending, content_type='sql_case')
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            content_name = f"sql_case_{int(time.time())}_{conv.get('id') or 0}"
            metadata = json.dumps({
                "conversation_id": conv.get("id"),
                "thread_id": effective_thread,
                "user_question": conv.get("user_question") or "",
                "sql_count": len(sqls),
                "markdown": markdown,
            }, ensure_ascii=False)

            cur = conn.execute(
                "INSERT INTO content_pool (content_type, content_name, owner_id, submitted_by, status, metadata) "
                "VALUES ('sql_case', ?, ?, ?, 'pending', ?)",
                (content_name, user_id, user_id, metadata),
            )
            conn.commit()
            pool_id = cur.lastrowid

            logger.info(
                f"📝 [SQL-Case] 案例已提交审核 pool_id={pool_id} "
                f"sqls={len(sqls)}"
            )
            return {
                "ok": True,
                "pool_id": pool_id,
                "message": f"已提交 {len(sqls)} 条 SQL 案例待审核",
            }
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[SQL-Case] 提交审核失败: {e}")
        return {"ok": False, "pool_id": None, "message": f"提交审核失败: {e}"}


def ingest_approved_case(pool_id: int, reviewer_id: int) -> dict:
    """审核通过后，将 SQL 案例入库"历史正确案例"知识库。

    Args:
        pool_id: content_pool 记录 ID
        reviewer_id: 审核人 ID

    Returns:
        {"ok": bool, "doc_id": int|None, "message": str}
    """
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT * FROM content_pool WHERE id = ? AND content_type = 'sql_case'",
                (pool_id,),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if not rows:
                return {"ok": False, "doc_id": None, "message": "记录不存在"}
            row = rows[0]
            if row.get("status") != "pending":
                return {"ok": False, "doc_id": None, "message": f"记录状态不是 pending: {row.get('status')}"}

            metadata = json.loads(row.get("metadata") or "{}")
            markdown = metadata.get("markdown", "")
            user_id = row.get("owner_id")

            if not markdown:
                return {"ok": False, "doc_id": None, "message": "metadata 中没有 markdown 内容"}

            # 入库"历史正确案例"知识库
            from backend.service.kb.knowledge_base_service import KnowledgeBaseService
            from backend.service.kb.kb_service import create_document
            import asyncio

            kb_svc = KnowledgeBaseService()
            kb = kb_svc.get_history_correct_kb(user_id)

            filename = f"{row.get('content_name')}.md"

            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    create_document(
                        user_id=user_id,
                        filename=filename,
                        content=markdown.encode("utf-8"),
                        chunk_strategy="parent_child",
                        kb_id=kb["id"],
                    )
                )
            finally:
                loop.close()

            # 更新 content_pool 状态
            conn.execute(
                "UPDATE content_pool SET status = 'active', reviewed_by = ?, reviewed_at = NOW() WHERE id = ?",
                (reviewer_id, pool_id),
            )
            conn.commit()

            logger.info(
                f"✅ [SQL-Case] 案例已入库 kb={kb['id']} doc={result.get('id')} pool_id={pool_id}"
            )
            return {
                "ok": True,
                "doc_id": result.get("id"),
                "message": "SQL 案例已入库",
            }
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[SQL-Case] 入库失败: {e}")
        return {"ok": False, "doc_id": None, "message": f"入库失败: {e}"}


def cancel_sql_case(pool_id: int, user_id: int) -> dict:
    """用户取消点赞（删除 pending 记录）。

    Args:
        pool_id: content_pool 记录 ID
        user_id: 用户 ID（必须是提交者）

    Returns:
        {"ok": bool, "message": str}
    """
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT * FROM content_pool WHERE id = %s AND content_type = 'sql_case' AND owner_id = %s",
                (pool_id, user_id),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if not rows:
                return {"ok": False, "message": "记录不存在或不属于当前用户"}
            row = rows[0]

            if row.get("status") == "pending":
                # pending 状态可以直接删除
                conn.execute("DELETE FROM content_pool WHERE id = %s", (pool_id,))
                conn.commit()
                logger.info(f"[SQL-Case] 用户取消点赞 pool_id={pool_id}")
                return {"ok": True, "message": "已取消点赞"}
            elif row.get("status") == "active":
                # 已审核通过的，标记为 cancelled（后续可清理知识库）
                conn.execute(
                    "UPDATE content_pool SET status = 'cancelled', reviewed_by = %s WHERE id = %s",
                    (user_id, pool_id),
                )
                conn.commit()
                logger.info(f"[SQL-Case] 用户取消已审核的点赞 pool_id={pool_id}（标记为 cancelled）")
                return {"ok": True, "message": "已取消点赞（已审核的记录已标记为 cancelled）"}
            else:
                return {"ok": False, "message": f"无法取消，当前状态: {row.get('status')}"}
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[SQL-Case] 取消点赞失败: {e}")
        return {"ok": False, "message": f"取消点赞失败: {e}"}


# 兼容旧接口（保留给历史记录处理）
def ingest_sql_case(
    user_id: int,
    conversation_id: Optional[int] = None,
    thread_id: str = "",
    comment: str = "",
) -> dict:
    """兼容旧接口。SQL 案例审核已废弃，此函数不再主动使用。"""
    # 不再提交审核，直接返回
    return {"ok": False, "pool_id": None, "message": "SQL 案例审核功能已废弃"}
