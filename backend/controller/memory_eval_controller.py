"""
Memory Evaluation API Controller

提供记忆评估相关的 REST API
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.service.memory import get_memory_evaluator
from backend.controller.auth_controller import get_current_user
from backend.utils.log_utils import log

logger = log


router = APIRouter(prefix="/api/memory/eval", tags=["memory-evaluation"])


# ========== Request/Response Models ==========

class CreateEvalSetRequest(BaseModel):
    """创建评估集请求"""
    name: str
    description: Optional[str] = None


class AddEvalItemRequest(BaseModel):
    """添加评估项请求"""
    query: str
    expected_answer: Optional[str] = None
    expected_memory_ids: Optional[list] = None
    tags: Optional[str] = None
    difficulty: Optional[str] = "medium"


class RunEvaluationRequest(BaseModel):
    """运行评估请求"""
    eval_set_id: int


def _check_permission(user: dict, permission: str) -> bool:
    """检查权限"""
    perms = user.get("permissions") or set()
    role = user.get("role", "")
    
    # 管理员有所有权限
    if role in ("admin", "super_admin"):
        return True
    
    return permission in perms


def _require_permission(permission: str):
    """权限检查依赖"""
    async def check(user: dict = Depends(get_current_user)):
        if not _check_permission(user, permission):
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
        return user
    return check


# ========== Eval Set Endpoints ==========

@router.get("/sets")
async def list_eval_sets(
    user: dict = Depends(get_current_user),
    is_active: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100)
):
    """列出评估集"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        where_clause = "WHERE is_active = %s" if is_active is not None else ""
        params = [is_active, limit] if is_active is not None else [limit]

        cur = conn.execute(
            f"""SELECT * FROM memory_eval_sets
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s""",
            params
        )

        sets = [dict(row) for row in (cur.fetchall() if hasattr(cur, "fetchall") else [])]
        return {"sets": sets}
    finally:
        conn.close()


@router.post("/sets")
async def create_eval_set(
    request: CreateEvalSetRequest,
    user: dict = Depends(_require_permission("kb.manage"))
):
    """创建评估集"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        user_id = user.get("user_id", 0)

        cur = conn.execute(
            """INSERT INTO memory_eval_sets (name, description, user_id)
               VALUES (%s, %s, %s)""",
            (request.name, request.description, user_id)
        )
        conn.commit()

        return {"id": cur.lastrowid, "name": request.name}
    finally:
        conn.close()


@router.get("/sets/{set_id}")
async def get_eval_set(
    set_id: int,
    user: dict = Depends(get_current_user)
):
    """获取评估集详情"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT * FROM memory_eval_sets WHERE id = %s",
            (set_id,)
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Eval set not found")

        eval_set = dict(row)

        # 获取评估项数量
        cur = conn.execute(
            "SELECT COUNT(*) as cnt FROM memory_eval_items WHERE eval_set_id = %s",
            (set_id,)
        )
        eval_set["item_count"] = cur.fetchone()["cnt"]

        return eval_set
    finally:
        conn.close()


@router.delete("/sets/{set_id}")
async def delete_eval_set(
    set_id: int,
    user: dict = Depends(_require_permission("kb.manage"))
):
    """删除评估集"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        # 先删除评估项
        conn.execute("DELETE FROM memory_eval_items WHERE eval_set_id = %s", (set_id,))
        # 删除运行记录和结果
        conn.execute(
            "DELETE FROM memory_eval_results WHERE run_id IN "
            "(SELECT id FROM memory_eval_runs WHERE eval_set_id = %s)",
            (set_id,)
        )
        conn.execute("DELETE FROM memory_eval_runs WHERE eval_set_id = %s", (set_id,))
        # 删除评估集
        conn.execute("DELETE FROM memory_eval_sets WHERE id = %s", (set_id,))
        conn.commit()

        return {"deleted": True}
    finally:
        conn.close()


# ========== Eval Item Endpoints ==========

@router.get("/sets/{set_id}/items")
async def list_eval_items(
    set_id: int,
    user: dict = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500)
):
    """列出评估项"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        cur = conn.execute(
            """SELECT * FROM memory_eval_items
               WHERE eval_set_id = %s
               ORDER BY id
               LIMIT %s""",
            (set_id, limit)
        )

        items = [dict(row) for row in (cur.fetchall() if hasattr(cur, "fetchall") else [])]
        return {"items": items}
    finally:
        conn.close()


@router.post("/sets/{set_id}/items")
async def add_eval_item(
    set_id: int,
    request: AddEvalItemRequest,
    user: dict = Depends(_require_permission("kb.manage"))
):
    """添加评估项"""
    from backend.db.schema import get_conn
    import json
    conn = get_conn()
    try:
        expected_ids_json = json.dumps(request.expected_memory_ids) if request.expected_memory_ids else None

        cur = conn.execute(
            """INSERT INTO memory_eval_items
               (eval_set_id, query, expected_answer, expected_memory_ids, tags, difficulty)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (set_id, request.query, request.expected_answer,
             expected_ids_json, request.tags, request.difficulty)
        )
        conn.commit()

        # 更新评估集的 item_count
        conn.execute(
            "UPDATE memory_eval_sets SET item_count = (SELECT COUNT(*) FROM memory_eval_items WHERE eval_set_id = %s) WHERE id = %s",
            (set_id, set_id)
        )
        conn.commit()

        return {"id": cur.lastrowid}
    finally:
        conn.close()


@router.post("/sets/{set_id}/items/batch")
async def batch_add_eval_items(
    set_id: int,
    items: list[AddEvalItemRequest],
    user: dict = Depends(_require_permission("kb.manage"))
):
    """批量添加评估项"""
    from backend.db.schema import get_conn
    import json
    conn = get_conn()
    try:
        count = 0
        for item in items:
            expected_ids_json = json.dumps(item.expected_memory_ids) if item.expected_memory_ids else None

            conn.execute(
                """INSERT INTO memory_eval_items
                   (eval_set_id, query, expected_answer, expected_memory_ids, tags, difficulty)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (set_id, item.query, item.expected_answer,
                 expected_ids_json, item.tags, item.difficulty)
            )
            count += 1

        conn.commit()

        # 更新评估集的 item_count
        conn.execute(
            "UPDATE memory_eval_sets SET item_count = (SELECT COUNT(*) FROM memory_eval_items WHERE eval_set_id = %s) WHERE id = %s",
            (set_id, set_id)
        )
        conn.commit()

        return {"added": count}
    finally:
        conn.close()


@router.delete("/items/{item_id}")
async def delete_eval_item(
    item_id: int,
    user: dict = Depends(_require_permission("kb.manage"))
):
    """删除评估项"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        # 获取 eval_set_id
        cur = conn.execute("SELECT eval_set_id FROM memory_eval_items WHERE id = %s", (item_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")

        eval_set_id = row["eval_set_id"]

        conn.execute("DELETE FROM memory_eval_items WHERE id = %s", (item_id,))
        conn.commit()

        # 更新评估集的 item_count
        conn.execute(
            "UPDATE memory_eval_sets SET item_count = (SELECT COUNT(*) FROM memory_eval_items WHERE eval_set_id = %s) WHERE id = %s",
            (eval_set_id, eval_set_id)
        )
        conn.commit()

        return {"deleted": True}
    finally:
        conn.close()


# ========== Evaluation Run Endpoints ==========

@router.post("/run")
async def run_evaluation(
    request: RunEvaluationRequest,
    user: dict = Depends(_require_permission("kb.manage"))
):
    """运行评估"""
    evaluator = get_memory_evaluator()
    
    user_id = user.get("user_id", 0)
    
    result = evaluator.run_evaluation(
        eval_set_id=request.eval_set_id,
        user_id=user_id,
        run_type="manual"
    )
    
    return result


@router.get("/runs")
async def list_eval_runs(
    user: dict = Depends(get_current_user),
    eval_set_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100)
):
    """列出评估运行"""
    evaluator = get_memory_evaluator()
    
    user_id = None
    perms = user.get("permissions") or set()
    # 如果不是管理员，只看自己的运行
    if "kb.manage" not in perms and user.get("role") not in ("admin", "super_admin"):
        user_id = user.get("user_id")
    
    runs = evaluator.list_runs(
        eval_set_id=eval_set_id,
        user_id=user_id,
        status=status,
        limit=limit
    )
    
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def get_eval_run(
    run_id: int,
    user: dict = Depends(get_current_user)
):
    """获取评估运行详情"""
    # 归属校验：先查询该 run 的 user_id
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT user_id FROM memory_eval_runs WHERE id = %s",
            (run_id,)
        )
        run_row = cur.fetchone()
    finally:
        conn.close()

    if not run_row:
        raise HTTPException(status_code=404, detail="Run not found")

    # 检查权限：管理员可访问所有，普通用户只能访问自己的
    perms = user.get("permissions") or set()
    run_user_id = run_row["user_id"]
    current_user_id = user.get("user_id")

    if run_user_id != current_user_id:
        # 非自己的 run，检查是否有 kb.manage 权限
        if "kb.manage" not in perms:
            raise HTTPException(status_code=403, detail="无权访问该评估运行记录")

    evaluator = get_memory_evaluator()
    result = evaluator.get_run_results(run_id)

    if not result:
        raise HTTPException(status_code=404, detail="Run not found")

    return result


# ========== Statistics Endpoints ==========

@router.get("/stats")
async def get_eval_stats(
    user: dict = Depends(get_current_user)
):
    """获取评估统计"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        # 总评估集数
        cur = conn.execute("SELECT COUNT(*) as cnt FROM memory_eval_sets")
        total_sets = cur.fetchone()["cnt"]

        # 总评估项数
        cur = conn.execute("SELECT COUNT(*) as cnt FROM memory_eval_items")
        total_items = cur.fetchone()["cnt"]

        # 总运行数
        cur = conn.execute("SELECT COUNT(*) as cnt FROM memory_eval_runs")
        total_runs = cur.fetchone()["cnt"]

        # 平均 F1 分数
        cur = conn.execute(
            "SELECT AVG(f1_score) as avg_f1 FROM memory_eval_runs WHERE status = 'completed'"
        )
        avg_f1 = cur.fetchone()["avg_f1"] or 0

        return {
            "total_sets": total_sets,
            "total_items": total_items,
            "total_runs": total_runs,
            "avg_f1": round(avg_f1, 3)
        }
    finally:
        conn.close()


def register_routes(app):
    """注册路由"""
    app.include_router(router)
    logger.info("Memory evaluation API registered")