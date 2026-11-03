"""通知控制器 — 待审核数量统计（用于前端红点显示）

API:
    GET /api/notifications/pending-counts — 获取各类型待审核数量
"""
from fastapi import APIRouter, Depends

from backend.controller.auth_controller import get_current_user
from backend.utils.log_utils import log

logger = log

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/pending-counts")
async def get_pending_counts(user: dict = Depends(get_current_user)):
    """获取各类型待审核数量（用于前端红点显示）。

    返回:
        {
            "skill": int,         # 技能待审核数量
            "memory": int,        # 记忆分享待审核数量
            "suggestion": int,    # 优化建议待处理数量
        }
    """
    user_id = user["user_id"]
    permissions = user.get("permissions", set())

    counts = {
        "skill": 0,
        "memory": 0,
        "suggestion": 0,
        "graphCandidate": 0,
    }

    # 检查用户是否有审核权限
    # 统一为纯权限判定：admin 角色在 DB 中本就持有 skill.pool.review / skill.manage /
    # graph.manage（见 backend/permission/builtin.py），所以这里的角色旁路是冗余的，
    # 留着反而会让"在角色编辑里取消勾选"不生效。can_review_kb 本来就没有旁路，
    # 三者现在口径一致。
    # 口径与「功能准入」保持一致，否则红点会提示一个点不进去的功能：
    #   - can_review_pool：只认 skill.pool.review（原为 或 skill.manage）
    #   - can_review_kb  ：只认 kb.eval（原为 或 kb.manage）
    can_review_pool = "skill.pool.review" in permissions
    can_review_kb = "kb.eval" in permissions
    can_review_graph = "graph.manage" in permissions

    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            # 内容池待审核数量（技能/工具）
            if can_review_pool:
                # 技能待审核
                cur = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM content_pool WHERE content_type = 'skill' AND status = 'pending'"
                )
                row = cur.fetchone()
                counts["skill"] = row["cnt"] if row else 0

                # 工具待审核
                cur = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM content_pool WHERE content_type = 'tool' AND status = 'pending'"
                )
                row = cur.fetchone()
                counts["tool"] = row["cnt"] if row else 0

            # 优化建议待处理数量（需要 kb.eval 或 kb.manage 权限）
            if can_review_kb:
                cur = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM kb_eval_suggestions WHERE user_id = ? AND status IN ('pending', 'verifying')",
                    (user_id,),
                )
                row = cur.fetchone()
                counts["suggestion"] = row["cnt"] if row else 0

            # 知识图谱审核候选数量
            if can_review_graph:
                from backend.db.kg_candidate_mapper import KgCandidateMapper
                mapper = KgCandidateMapper()
                counts["graphCandidate"] = mapper.count_pending(user_id)
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[Notification] 获取待审核数量失败: {e}")

    return counts
