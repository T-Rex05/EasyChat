"""
RAG 测评 API — 向量化 / 试检索 / 评测集 CRUD / 运行 / 结果查询

权限：
- vectorize / retrieve / chunks search：kb.manage
- 评测集相关：kb.eval 或 kb.manage → require_kb_eval
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.service.kb import kb_eval_service
from backend.service.auth.auth_middleware import get_current_user
from backend.service.kb.kb_eval_service import EvalError, EvalInvalid, EvalNotFound
from backend.service.kb.kb_retriever import RetrieverError
from backend.service.kb.kb_service import KbNotFound
from backend.utils.log_utils import log

logger = log

router = APIRouter(prefix="/api/kb", tags=["kb-eval"])


# ── 权限依赖 ──

async def require_kb_access(user: dict = Depends(get_current_user)) -> dict:
    """kb.manage 权限。"""
    perms = user.get("permissions", set())
    if "kb.manage" not in perms:
        raise HTTPException(status_code=403, detail="缺少权限: kb.manage（管理知识库）")
    return user


async def require_kb_eval(user: dict = Depends(get_current_user)) -> dict:
    """RAG 测评的**功能准入**：只认 `kb.eval`。

    此前写成「`kb.eval` **或** `kb.manage` 任一即可」，导致前端「RAG 测评」这个
    勾选框**从未生效** —— 只要勾了「管理知识库」就能进（实测：qqq/test-1 没有
    kb.eval 但持有 kb.manage，因此三个层面（侧边栏 / 路由守卫 / 本接口）全部放行）。
    现改为只认 `kb.eval`，让勾选成为唯一依据。

    注意区分两件事：
    - **功能准入**（本函数）→ 只看 `kb.eval`
    - **数据范围**（`kb_eval_service` 内部）→ 持有 `kb.manage` 时可看**全部用户**的
      测评集，否则只看自己的。该逻辑保留不变。
    """
    perms = user.get("permissions", set())
    if "kb.eval" not in perms:
        raise HTTPException(status_code=403, detail="缺少权限: kb.eval（RAG 测评）")
    return user


def _handle(e: Exception) -> HTTPException:
    if isinstance(e, (EvalNotFound, KbNotFound)):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, (EvalInvalid, RetrieverError)):
        return HTTPException(status_code=400, detail=str(e))
    return HTTPException(status_code=500, detail=f"服务内部错误: {e}")


# ── 请求模型 ──

class EvalSetCreate(BaseModel):
    name: str = Field(description="测评集名称")
    description: str = Field(default="", description="描述")


class EvalSetUpdate(BaseModel):
    name: str = Field(description="新名称")
    description: str = Field(default="", description="描述")


class EvalItemCreate(BaseModel):
    question: str = Field(description="评测问题")
    ground_truth_chunk_ids: List[int] = Field(default_factory=list, description="人工标注的 GT chunk id 列表")
    ground_truth_answer: str = Field(default="", description="参考答案（可选）")


class EvalItemUpdate(BaseModel):
    question: str = Field(description="评测问题")
    ground_truth_chunk_ids: Optional[List[int]] = Field(default=None, description="GT chunk id 列表")
    ground_truth_answer: Optional[str] = Field(default=None, description="参考答案")


class TestsetGenerateRequest(BaseModel):
    document_ids: List[int] = Field(description="源文档 ID 列表")
    eval_set_id: int = Field(description="目标测评集 ID")
    testset_size: int = Field(default=10, description="生成题目数量（1~50）")


class EvalRunRequest(BaseModel):
    top_k: int = Field(default=5, description="检索返回数量")
    generate_answer: bool = Field(default=True, description="是否用 LLM 生成答案（RAG 仿真）")
    judge_enabled: bool = Field(default=True, description="是否启用 RAGAS LLM 裁判")
    retriever: str = Field(default="auto", description="检索器: auto/vector/bm25/hybrid")
    chunk_kind: str = Field(default="all", description="检索范围: all/base/topic（切分策略对比）")
    n_runs: int = Field(default=1, description="RAGAS 裁判重复次数（取均值降低方差，1~5）")
    min_score: float = Field(default=0.0, description="检索结果最低分数阈值（低于此值的 chunk 被过滤，0=不过滤）")
    query_rewrite: bool = Field(default=False, description="是否启用 LLM 查询重写（语义压缩/纠错）")


# ── 向量化 / 试检索 / chunk 搜索 ──

@router.post("/documents/{doc_id}/vectorize")
async def vectorize_document(doc_id: int, user: dict = Depends(require_kb_access)):
    """向量化文档（chunks → Chroma 每用户 collection）。"""
    import asyncio
    from backend.service.kb.kb_retriever import vectorize_document as _vectorize
    try:
        return await asyncio.to_thread(_vectorize, user["user_id"], doc_id)
    except Exception as e:
        raise _handle(e)


@router.get("/retrieve")
async def try_retrieve(
    query: str = "",
    top_k: int = 5,
    mode: str = "auto",
    kind: str = "all",
    user: dict = Depends(require_kb_access),
):
    """试检索（调试用，与评测使用同一检索器；kind: all/base/topic）。"""
    if not query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    try:
        import asyncio
        from backend.service.kb.kb_retriever import get_retriever
        retriever, warnings = await asyncio.to_thread(get_retriever, user["user_id"], mode, kind)
        results = await asyncio.to_thread(retriever.retrieve, query, max(1, min(top_k, 50)))
        return {"retriever": retriever.name, "kind": kind, "results": results, "warnings": warnings}
    except Exception as e:
        raise _handle(e)


@router.get("/chunks/search")
async def search_chunks(
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
    document_id: Optional[int] = None,
    user: dict = Depends(require_kb_access),
):
    """跨文档按关键词搜索 chunk（GT 标注辅助）。keyword 为空时返回所有 chunk。"""
    from backend.service.kb.kb_eval_service import search_chunks
    try:
        return search_chunks(
            user["user_id"], user.get("permissions", set()),
            keyword, page, page_size, document_id,
        )
    except Exception as e:
        raise _handle(e)


# ── 测评集 CRUD ──

@router.post("/eval-sets")
async def create_eval_set(req: EvalSetCreate, user: dict = Depends(require_kb_eval)):
    try:
        return kb_eval_service.create_eval_set(user["user_id"], req.name, req.description)
    except EvalError as e:
        raise _handle(e)


@router.get("/eval-sets")
async def list_eval_sets(user: dict = Depends(require_kb_eval)):
    return kb_eval_service.list_eval_sets(user["user_id"], user.get("permissions", set()))


@router.get("/eval-sets/{set_id}")
async def get_eval_set(set_id: int, user: dict = Depends(require_kb_eval)):
    try:
        return kb_eval_service.get_eval_set(user["user_id"], set_id, user.get("permissions", set()))
    except EvalError as e:
        raise _handle(e)


@router.put("/eval-sets/{set_id}")
async def update_eval_set(set_id: int, req: EvalSetUpdate, user: dict = Depends(require_kb_eval)):
    try:
        return kb_eval_service.update_eval_set(
            user["user_id"], set_id, user.get("permissions", set()), req.name, req.description
        )
    except EvalError as e:
        raise _handle(e)


@router.delete("/eval-sets/{set_id}")
async def delete_eval_set(set_id: int, user: dict = Depends(require_kb_eval)):
    try:
        return kb_eval_service.delete_eval_set(user["user_id"], set_id, user.get("permissions", set()))
    except EvalError as e:
        raise _handle(e)


# ── 题目 CRUD ──

@router.post("/eval-sets/{set_id}/items")
async def add_item(set_id: int, req: EvalItemCreate, user: dict = Depends(require_kb_eval)):
    try:
        return kb_eval_service.add_item(
            user["user_id"], set_id, user.get("permissions", set()),
            req.question, req.ground_truth_chunk_ids, req.ground_truth_answer,
        )
    except EvalError as e:
        raise _handle(e)


@router.put("/eval-sets/{set_id}/items/{item_id}")
async def update_item(set_id: int, item_id: int, req: EvalItemUpdate, user: dict = Depends(require_kb_eval)):
    try:
        return kb_eval_service.update_item(
            user["user_id"], set_id, item_id, user.get("permissions", set()),
            req.question, req.ground_truth_chunk_ids, req.ground_truth_answer,
        )
    except EvalError as e:
        raise _handle(e)


@router.delete("/eval-sets/{set_id}/items/{item_id}")
async def delete_item(set_id: int, item_id: int, user: dict = Depends(require_kb_eval)):
    try:
        return kb_eval_service.delete_item(
            user["user_id"], set_id, item_id, user.get("permissions", set())
        )
    except EvalError as e:
        raise _handle(e)


# ── 运行 ──

@router.post("/eval-sets/generate")
async def generate_testset(req: TestsetGenerateRequest, user: dict = Depends(require_kb_eval)):
    """基于文档自动生成测评集题目（LLM 生成 QA 对，异步执行）。"""
    from backend.service.kb import kb_eval_generator
    try:
        return await kb_eval_generator.generate_testset(
            user["user_id"], req.document_ids, req.eval_set_id, req.testset_size,
        )
    except Exception as e:
        raise _handle(e)


@router.post("/eval-sets/{set_id}/run")
async def run_eval_set(set_id: int, req: EvalRunRequest, user: dict = Depends(require_kb_eval)):
    try:
        return await kb_eval_service.run_eval_set(
            user["user_id"], set_id, user.get("permissions", set()),
            top_k=req.top_k,
            generate_answer=req.generate_answer,
            judge_enabled=req.judge_enabled,
            retriever_mode=req.retriever,
            chunk_kind=req.chunk_kind,
            n_runs=req.n_runs,
            min_score=req.min_score,
            query_rewrite=req.query_rewrite,
        )
    except EvalError as e:
        raise _handle(e)


@router.get("/eval-sets/{set_id}/runs/compare")
async def compare_runs(
    set_id: int,
    run_ids: str = "",
    user: dict = Depends(require_kb_eval),
):
    """多次 run 指标对比（run_ids 逗号分隔，如 1,2,3）。"""
    if not run_ids.strip():
        raise HTTPException(status_code=400, detail="run_ids 不能为空")
    try:
        ids = [int(x.strip()) for x in run_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="run_ids 格式错误（应为逗号分隔的数字）")
    try:
        return kb_eval_service.compare_runs(user["user_id"], ids, user.get("permissions", set()))
    except EvalError as e:
        raise _handle(e)


@router.get("/eval-sets/{set_id}/runs")
async def list_runs(set_id: int, user: dict = Depends(require_kb_eval)):
    try:
        return kb_eval_service.list_runs(user["user_id"], set_id, user.get("permissions", set()))
    except EvalError as e:
        raise _handle(e)


@router.get("/eval-runs/{run_id}")
async def get_run(run_id: int, user: dict = Depends(require_kb_eval)):
    try:
        return kb_eval_service.get_run(user["user_id"], run_id, user.get("permissions", set()))
    except EvalError as e:
        raise _handle(e)


@router.delete("/eval-runs/{run_id}")
async def delete_run(run_id: int, user: dict = Depends(require_kb_eval)):
    try:
        return kb_eval_service.delete_run(user["user_id"], run_id, user.get("permissions", set()))
    except EvalError as e:
        raise _handle(e)


# ── Bad Case 诊断 ──

@router.get("/eval-runs/{run_id}/diagnosis")
async def batch_diagnosis(run_id: int, user: dict = Depends(require_kb_eval)):
    """批量诊断汇总：按失败模式聚合，列出 top 失败题目。"""
    from backend.service.kb import kb_eval_diagnosis
    try:
        return kb_eval_diagnosis.batch_diagnosis_summary(
            run_id, user["user_id"], user.get("permissions", set())
        )
    except Exception as e:
        raise _handle(e)


@router.get("/eval-runs/{run_id}/results/{result_id}/diagnosis")
async def single_diagnosis(run_id: int, result_id: int, user: dict = Depends(require_kb_eval)):
    """单题深度诊断：检索分析 + 生成分析 + 根因定位 + 优化建议。"""
    from backend.service.kb import kb_eval_diagnosis
    try:
        return kb_eval_diagnosis.diagnose_result(
            run_id, result_id, user["user_id"], user.get("permissions", set())
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── RAG 评测闭环：优化建议 ──

@router.get("/feedback")
async def list_chat_feedback(
    page: int = 1, page_size: int = 20, user: dict = Depends(require_kb_eval),
):
    """聊天反馈列表（自己的；kb.manage 全部）。提交端点见 /api/chat/feedback。"""
    from backend.service.kb import kb_feedback
    return kb_feedback.list_feedback(user["user_id"], user.get("permissions", set()), page, page_size)


@router.delete("/feedback/{feedback_id}")
async def delete_chat_feedback(
    feedback_id: int, user: dict = Depends(require_kb_eval),
):
    """删除聊天反馈记录（只能删自己的；kb.manage 可删任意）。"""
    from backend.service.kb import kb_feedback
    from backend.service.kb.kb_feedback import FeedbackNotFound
    try:
        return kb_feedback.delete_feedback(user["user_id"], feedback_id, user.get("permissions", set()))
    except FeedbackNotFound as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/chat-eval/items")
async def list_chat_eval_items(
    page: int = 1, page_size: int = 50, user: dict = Depends(require_kb_eval),
):
    """聊天反馈「测评集」题目列表：每条反馈含用户问题 + 检索 chunk 详情。"""
    import json as _json
    from backend.service.kb import kb_feedback
    from backend.db.schema import get_conn

    fb_data = kb_feedback.list_feedback(user["user_id"], user.get("permissions", set()), page, page_size)
    items = fb_data.get("items", [])
    if not items:
        return {**fb_data, "items": []}

    # ★ 只保留点踩反馈（rating < 0），点赞不进入「优化闭环」
    items = [it for it in items if (it.get("rating") or 0) < 0]

    # ★ 按 thread_id 去重（保留最新），避免同一条消息被多次点踩导致重复
    seen_threads = {}
    for it in items:
        tid = it.get("thread_id") or f"fb_{it['id']}"
        if tid not in seen_threads:
            seen_threads[tid] = it
    items = list(seen_threads.values())

    # 批量查 chunk 内容预览
    all_chunk_ids = set()
    for it in items:
        for cid in it.get("retrieved_chunk_ids", []):
            all_chunk_ids.add(int(cid))

    chunk_map = {}
    if all_chunk_ids:
        conn = get_conn()
        try:
            placeholders = ",".join("%s" for _ in all_chunk_ids)
            cur = conn.execute(
                f"SELECT id, document_id, LEFT(content, 200) AS preview FROM kb_chunks WHERE id IN ({placeholders})",
                list(all_chunk_ids),
            )
            for r in cur.fetchall():
                chunk_map[r["id"]] = {"id": r["id"], "document_id": r["document_id"], "preview": r.get("preview") or ""}
        finally:
            conn.close()

    # 批量查 conversation 的用户问题
    conv_ids = {it.get("conversation_id") for it in items if it.get("conversation_id")}
    question_map = {}
    if conv_ids:
        conn = get_conn()
        try:
            placeholders = ",".join("%s" for _ in conv_ids)
            cur = conn.execute(
                f"SELECT id, user_question FROM conversations WHERE id IN ({placeholders})",
                list(conv_ids),
            )
            for r in cur.fetchall():
                q = (r.get("user_question") or "").strip()
                if q:
                    question_map[r["id"]] = q[:300]
        finally:
            conn.close()

    enriched = []
    for it in items:
        chunks = [chunk_map[cid] for cid in it.get("retrieved_chunk_ids", []) if cid in chunk_map]
        question = question_map.get(it.get("conversation_id")) or ""
        enriched.append({
            **it,
            "question": question,
            "chunks": chunks,
        })
    return {**fb_data, "items": enriched}


@router.post("/eval-runs/{run_id}/suggestions")
async def generate_suggestions(run_id: int, user: dict = Depends(require_kb_eval)):
    """按 run 六态分类聚合生成优化建议（幂等：同型未关闭建议自动去重）。"""
    import asyncio
    from backend.service.kb import kb_eval_suggestion
    # 归属校验（run 属于用户自己的测评集）
    kb_eval_service.get_run(user["user_id"], run_id, user.get("permissions", set()))
    try:
        ids = await asyncio.to_thread(kb_eval_suggestion.generate_from_run, run_id)
        return {"created": len(ids), "suggestion_ids": ids}
    except Exception as e:
        raise _handle(e)


@router.get("/suggestions")
async def list_suggestions(
    status: str = "", eval_set_id: int = 0, source: str = "",
    page: int = 1, page_size: int = 20,
    user: dict = Depends(require_kb_eval),
):
    """优化建议列表（按测评集/来源筛选）。"""
    from backend.service.kb import kb_eval_suggestion
    return kb_eval_suggestion.list_suggestions(
        user["user_id"], user.get("permissions", set()), status,
        eval_set_id=eval_set_id or None, source=source or None,
        page=page, page_size=page_size,
    )


@router.get("/suggestions/{suggestion_id}")
async def get_suggestion(suggestion_id: int, user: dict = Depends(require_kb_eval)):
    from backend.service.kb import kb_eval_suggestion
    from backend.service.kb.kb_eval_suggestion import SuggestionError
    try:
        return kb_eval_suggestion.get_suggestion(user["user_id"], suggestion_id, user.get("permissions", set()))
    except SuggestionError as e:
        raise _handle(e)


@router.post("/suggestions/{suggestion_id}/run")
async def run_suggestion_verification(suggestion_id: int, user: dict = Depends(require_kb_eval)):
    """对建议发起验证：复用评测 run，完成后自动结算 before/after。"""
    from backend.service.kb import kb_eval_suggestion
    from backend.service.kb.kb_eval_suggestion import SuggestionError
    try:
        return await kb_eval_suggestion.run_verification(
            suggestion_id, user["user_id"], user.get("permissions", set())
        )
    except SuggestionError as e:
        raise _handle(e)


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: int, user: dict = Depends(require_kb_eval)):
    from backend.service.kb import kb_eval_suggestion
    from backend.service.kb.kb_eval_suggestion import SuggestionError
    try:
        return kb_eval_suggestion.dismiss_suggestion(
            user["user_id"], suggestion_id, user.get("permissions", set())
        )
    except SuggestionError as e:
        raise _handle(e)


@router.delete("/suggestions/{suggestion_id}")
async def delete_suggestion(suggestion_id: int, user: dict = Depends(require_kb_eval)):
    """删除优化建议（物理删除）。"""
    from backend.service.kb import kb_eval_suggestion
    from backend.service.kb.kb_eval_suggestion import SuggestionError
    try:
        return kb_eval_suggestion.delete_suggestion(
            user["user_id"], suggestion_id, user.get("permissions", set())
        )
    except SuggestionError as e:
        raise _handle(e)


class ApproveSuggestionRequest(BaseModel):
    edited_sql_content: Optional[str] = Field(default=None, description="管理员编辑后的 SQL 示例内容")
    action: str = Field(default="apply_sql", description="操作类型：apply_sql（自动入库）或 approve_only（仅审批）")


@router.post("/suggestions/{suggestion_id}/approve")
async def approve_suggestion(
    suggestion_id: int,
    req: ApproveSuggestionRequest = ApproveSuggestionRequest(),
    user: dict = Depends(require_kb_eval),
):
    """
    审批通过建议 → 可选自动入库 → 重新解析 → 重新验证。
    
    一个建议可能包含两个解决方案：
    1. SQL 示例（可自动入库到"历史正确案例"）
    2. Chunk 修改建议（需要管理员手动操作）
    
    操作类型：
    - `apply_sql`: 将 SQL 示例自动添加到知识库，然后重新解析和验证
    - `approve_only`: 仅标记审批通过（管理员会手动修改 chunks）
    
    管理员可以在审批前编辑 SQL 示例内容。
    """
    from backend.service.kb import kb_eval_suggestion
    from backend.service.kb.kb_eval_suggestion import SuggestionError
    try:
        result = kb_eval_suggestion.approve_and_apply_suggestion(
            user_id=user["user_id"],
            suggestion_id=suggestion_id,
            permissions=user.get("permissions", set()),
            edited_sql_content=req.edited_sql_content,
            action=req.action,
        )
        return result
    except SuggestionError as e:
        raise _handle(e)


class ModifyChunkRequest(BaseModel):
    new_content: str = Field(..., description="新的 chunk 内容")
    reason: str = Field(default="优化建议执行", description="修改原因")


@router.post("/chunks/{chunk_id}/modify")
async def modify_chunk(
    chunk_id: int,
    req: ModifyChunkRequest,
    user: dict = Depends(require_kb_eval),
):
    """
    手动修改 chunk 内容。

    记录原始内容，支持回滚。
    """
    from backend.service.kb import kb_eval_suggestion
    from backend.service.kb.kb_eval_suggestion import SuggestionError
    try:
        return kb_eval_suggestion.modify_chunk_content(
            chunk_id=chunk_id,
            new_content=req.new_content,
            reason=req.reason,
            user_id=user["user_id"],
            permissions=user.get("permissions", set()),
        )
    except SuggestionError as e:
        raise _handle(e)


@router.post("/chunks/{chunk_id}/rollback")
async def rollback_chunk(
    chunk_id: int,
    user: dict = Depends(require_kb_eval),
):
    """
    回滚 chunk 内容到修改前的状态。

    仅对被手动修改过的 chunk 有效。
    """
    from backend.service.kb import kb_eval_suggestion
    from backend.service.kb.kb_eval_suggestion import SuggestionError
    try:
        return kb_eval_suggestion.rollback_chunk_content(
            chunk_id=chunk_id,
            user_id=user["user_id"],
            permissions=user.get("permissions", set()),
        )
    except SuggestionError as e:
        raise _handle(e)


@router.get("/chunks/{chunk_id}")
async def get_chunk_content(
    chunk_id: int,
    user: dict = Depends(require_kb_eval),
):
    """
    获取 chunk 内容（用于预览）。
    """
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT kc.id, kc.content, kc.document_id, kb.user_id AS kb_owner "
            "FROM kb_chunks kc "
            "JOIN kb_documents kd ON kc.document_id = kd.id "
            "JOIN knowledge_bases kb ON kd.kb_id = kb.id "
            "WHERE kc.id = %s",
            (chunk_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        if not rows:
            raise HTTPException(status_code=404, detail=f"Chunk 不存在: id={chunk_id}")
        row = rows[0]
        # IDOR 防护：校验知识库归属（管理员跳过）
        perms = user.get("permissions", set())
        if "kb.manage" not in perms and int(row.get("kb_owner", -1)) != int(user["user_id"]):
            raise HTTPException(status_code=403, detail="无权访问该 chunk")
        return {
            "id": row["id"],
            "content": row["content"],
            "document_id": row["document_id"],
        }
    finally:
        conn.close()


class ExecuteActionRequest(BaseModel):
    actions: List[dict] = Field(..., description="要执行的动作列表")


@router.post("/suggestions/{suggestion_id}/execute")
async def execute_suggestion(
    suggestion_id: int,
    req: ExecuteActionRequest,
    user: dict = Depends(require_kb_eval),
):
    """
    执行优化建议的多个动作。

    支持的动作类型：
    - chunk_modify: 修改 chunk 内容
    - add_sql_example: 添加 SQL 示例到知识库
    - reparse: 重新解析文档

    执行成功后自动触发回归验证。
    """
    from backend.service.kb import kb_eval_suggestion
    from backend.service.kb.kb_eval_suggestion import SuggestionError
    try:
        return kb_eval_suggestion.execute_suggestion_actions(
            suggestion_id=suggestion_id,
            actions=req.actions,
            user_id=user["user_id"],
            permissions=user.get("permissions", set()),
        )
    except SuggestionError as e:
        raise _handle(e)


@router.post("/feedback/{feedback_id}/generate-suggestion")
async def generate_feedback_suggestion(feedback_id: int, user: dict = Depends(require_kb_eval)):
    """手动为负反馈生成优化建议（调用 LLM 深度分析）。"""
    import asyncio
    from backend.service.kb import kb_eval_suggestion
    from backend.service.kb.kb_feedback import FeedbackNotFound
    
    # 验证反馈归属
    from backend.service.kb.kb_feedback import list_feedback
    fb_list = list_feedback(user["user_id"], user.get("permissions", set()), page=1, page_size=100)
    fb_ids = [fb["id"] for fb in fb_list.get("items", [])]
    if feedback_id not in fb_ids and "kb.manage" not in user.get("permissions", set()):
        raise HTTPException(status_code=404, detail=f"反馈不存在: id={feedback_id}")
    
    try:
        sid = await asyncio.to_thread(kb_eval_suggestion.generate_from_feedback, feedback_id, user["user_id"])
        if sid:
            return {"created": True, "suggestion_id": sid}
        return {"created": False, "reason": "该反馈已处理或无需生成建议"}
    except Exception as e:
        raise _handle(e)


# ── 分类阈值配置 ──

class ClassifyThresholds(BaseModel):
    judge_pass: float = Field(default=0.6, ge=0.0, le=1.0, description="judge 指标达标线（faithfulness 等低于此值判「依据不足」）")
    wrong_answer_correctness: float = Field(default=0.3, ge=0.0, le=1.0, description="answer_correctness 低于此值判「答案错误」")
    complete_faith_threshold: float = Field(default=0.9, ge=0.0, le=1.0, description="faithfulness ≥ 此值直接判「完整命中」")
    wrong_answer_faith_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="faithfulness ≥ 此值时 answer_correctness 信号可信")


@router.get("/classify-thresholds")
async def get_thresholds(user: dict = Depends(require_kb_eval)):
    """获取当前分类阈值配置。"""
    return kb_eval_service.get_classify_thresholds()


@router.put("/classify-thresholds")
async def update_thresholds(req: ClassifyThresholds, user: dict = Depends(require_kb_eval)):
    """更新分类阈值并重新分类所有已有结果。"""
    thresholds = req.dict()
    saved = kb_eval_service.set_classify_thresholds(thresholds)
    reclassified = kb_eval_service.reclassify_all_runs(thresholds=saved)
    return {"thresholds": saved, "reclassified_runs": reclassified}
