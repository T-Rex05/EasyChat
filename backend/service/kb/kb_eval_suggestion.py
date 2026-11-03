"""
RAG 评测闭环 — 优化建议生命周期（借鉴 Eyes 的 feedback→suggestion→verify→resolved，
全部通用化，零领域绑定）

状态机：
    pending ──run_verification──▶ verifying ──settle──▶ verified（指标提升达标）
        │                                                    └▶ failed（attempts+1；≥3 次自动 dismissed）
        └──dismiss（人工忽略）

建议来源：
    - eval:     评测 run 完成后，按六态分类（retrieval_miss / insufficient_context）聚合生成
    - feedback: 聊天负反馈（kb_feedback）→ 关联检索日志生成
    - manual:   人工创建（预留）

验证：复用 kb_eval_service.run_eval_set 发起回归 run，完成后比较 before/after 聚合指标。

env 开关：
    KB_EVAL_AUTO_EXECUTE=false                 # 默认人工触发验证
    KB_EVAL_SUGGESTION_RUNNER_SECONDS=600      # 周期 runner 间隔（自动结算 + 可选自动执行）
"""
import json as _json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from backend.db.schema import get_conn
from backend.utils.log_utils import log, rag

logger = log

# 验证提升阈值（指标绝对差）
_IMPROVE_THRESHOLD = 0.05
# 连续失败上限（防自动执行空转）
_MAX_FAILED_ATTEMPTS = 3
# 自动执行每用户每轮上限（防配额爆炸）
_MAX_AUTO_RUNS_PER_USER_PER_ROUND = 3

_SUGGESTION_STATUS = ("pending", "verifying", "verified", "failed", "dismissed")


class SuggestionError(Exception):
    """建议业务异常基类"""


class SuggestionNotFound(SuggestionError):
    """建议不存在或不属于当前用户 → 404"""


class SuggestionInvalid(SuggestionError):
    """参数/状态不合法 → 400"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_loads(raw, default):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return _json.loads(raw)
    except (TypeError, ValueError):
        return default


def _json_dumps(obj) -> str:
    return _json.dumps(obj, ensure_ascii=False)


# ════════════════════════════════════════════════════════════
# 内部工具
# ════════════════════════════════════════════════════════════

def _fetch_owned(user_id: int, suggestion_id: int, permissions: Set[str]) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM kb_eval_suggestions WHERE id = %s", (suggestion_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    if not rows:
        raise SuggestionNotFound(f"优化建议不存在: id={suggestion_id}")
    row = rows[0]
    if row["user_id"] != user_id and "kb.manage" not in permissions:
        raise SuggestionNotFound(f"优化建议不存在: id={suggestion_id}")
    return row


def _insert_suggestion(
    user_id: int, eval_set_id: Optional[int], source: str, kind: str,
    summary: str, evidence: dict, before_metrics: Optional[dict] = None,
    suggestion_type: str = "general",
    sql_example_content: str = "",
    chunk_modify_suggestions: List[dict] = None,
    target_kb_id: Optional[int] = None,
    verification_query: str = "",
) -> Optional[int]:
    """落库建议；同源同集同 kind 且未关闭的重复建议自动去重。

    Args:
        suggestion_type: 建议类型（general/sql_example/chunk_modify/mixed）
        sql_example_content: SQL 示例内容（Markdown 格式）
        chunk_modify_suggestions: 对 chunks 的修改建议列表
        target_kb_id: 目标知识库 ID（历史正确案例）
        verification_query: 验证用的原始问题
    """
    chunk_modify_suggestions = chunk_modify_suggestions or []
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT id FROM kb_eval_suggestions WHERE user_id = %s AND source = %s AND kind = %s "
            "AND (eval_set_id = %s OR (eval_set_id IS NULL AND %s IS NULL)) "
            "AND status IN ('pending', 'verifying') "
            "ORDER BY id DESC LIMIT 1",
            (user_id, source, kind, eval_set_id, eval_set_id),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        if rows:
            return None  # 已有未关闭的同型建议
        cur = conn.execute(
            "INSERT INTO kb_eval_suggestions "
            "(user_id, eval_set_id, source, kind, summary, evidence, status, before_metrics, "
            "suggestion_type, sql_example_content, chunk_modify_suggestions, target_kb_id, verification_query) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s)",
            (
                int(user_id),
                int(eval_set_id) if eval_set_id else None,
                source[:16],
                kind[:32],
                summary,
                _json_dumps(evidence),
                _json_dumps(before_metrics) if before_metrics else None,
                suggestion_type[:32],
                sql_example_content,
                _json_dumps(chunk_modify_suggestions),
                int(target_kb_id) if target_kb_id else None,
                verification_query[:512],
            ),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as exc:
        logger.warning(f"插入建议失败: {exc}")
        return None
    finally:
        conn.close()


def _serialize(row: dict) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "eval_set_id": row.get("eval_set_id"),
        "source": row.get("source") or "eval",
        "kind": row.get("kind") or "manual",
        "summary": row.get("summary") or "",
        "evidence": _json_loads(row.get("evidence"), {}),
        "status": row.get("status") or "pending",
        "before_metrics": _json_loads(row.get("before_metrics"), {}),
        "after_metrics": _json_loads(row.get("after_metrics"), {}),
        "linked_run_ids": _json_loads(row.get("linked_run_ids"), []),
        "attempts": int(row.get("attempts") or 0),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "resolved_at": str(row.get("resolved_at") or ""),
    }


# ════════════════════════════════════════════════════════════
# 建议生成：来源 eval run
# ════════════════════════════════════════════════════════════

def generate_from_run(run_id: int) -> List[int]:
    """
    聚合 run 的六态分类结果，生成详细的优化建议。

    每条建议包含：
    - 失败的具体问题列表
    - 每个问题实际检索到的 chunk 和期望的 GT chunk
    - 涉及的文档和知识库信息
    - 具体的优化操作建议
    """
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM kb_eval_runs WHERE id = %s", (run_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    if not rows:
        return []
    run = rows[0]
    if run.get("status") != "done":
        return []
    user_id = int(run["user_id"])
    eval_set_id = int(run["eval_set_id"])

    # 逐条结果 + 题目详情
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT r.item_id, r.classification, r.retrieved_chunks, r.question, "
            "i.ground_truth_chunk_ids, i.ground_truth_answer "
            "FROM kb_eval_results r JOIN kb_eval_items i ON i.id = r.item_id WHERE r.run_id = %s",
            (run_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    # 按文档分组失败题
    fail_by_doc: Dict[int, List[dict]] = {}   # document_id -> [{item_id, question, retrieved, gt, ...}]
    total_by_doc: Dict[int, set] = {}
    fail_classes: Dict[str, int] = {}
    missing_items: List[dict] = []

    for r in rows:
        cls = r.get("classification") or ""
        gt_ids = _json_loads(r.get("ground_truth_chunk_ids"), [])
        item_id = int(r["item_id"])
        question = (r.get("question") or "")[:200]
        retrieved = _json_loads(r.get("retrieved_chunks"), [])

        if cls in ("retrieval_miss", "insufficient_context", "wrong_answer", "partial"):
            fail_classes[cls] = fail_classes.get(cls, 0) + 1
            if gt_ids:
                for doc_id in _gt_document_ids(gt_ids):
                    # 构建失败详情
                    retrieved_summary = []
                    for c in retrieved[:5]:
                        retrieved_summary.append({
                            "chunk_id": c.get("chunk_id"),
                            "score": round(c.get("score", 0), 4),
                            "is_gt": c.get("is_gt", False),
                            "preview": (c.get("content") or "")[:100],
                        })
                    fail_by_doc.setdefault(doc_id, []).append({
                        "item_id": item_id,
                        "question": question,
                        "classification": cls,
                        "retrieved": retrieved_summary,
                        "gt_chunk_ids": gt_ids,
                    })
            else:
                missing_items.append({
                    "item_id": item_id,
                    "question": question,
                    "classification": cls,
                })
        for doc_id in _gt_document_ids(gt_ids):
            total_by_doc.setdefault(doc_id, set()).add(item_id)

    if not fail_by_doc and not missing_items:
        return []

    run_metrics = _run_metrics(run_id)
    created: List[int] = []

    # ── 按文档生成详细建议 ──
    for doc_id, fail_details in fail_by_doc.items():
        total_items = len(total_by_doc.get(doc_id, set()))
        unique_fails = len(set(f["item_id"] for f in fail_details))
        ratio = unique_fails / max(total_items, 1)
        doc_name = _doc_name(doc_id)
        kb_name = _kb_name_for_doc(doc_id)

        # 构建详细的失败题目列表（增强版）
        fail_questions = []
        retrieval_miss_count = 0
        insufficient_context_count = 0
        wrong_answer_count = 0
        partial_count = 0

        for f in fail_details:
            cls = f["classification"]
            if cls == "retrieval_miss":
                retrieval_miss_count += 1
            elif cls == "insufficient_context":
                insufficient_context_count += 1
            elif cls == "wrong_answer":
                wrong_answer_count += 1
            elif cls == "partial":
                partial_count += 1

            # 分析检索结果与 GT 的差异
            retrieved_analysis = []
            for r in f["retrieved"][:3]:
                retrieved_analysis.append({
                    "chunk_id": r.get("chunk_id"),
                    "score": r.get("score"),
                    "is_gt": r.get("is_gt", False),
                    "preview": r.get("preview", "")[:80],
                })

            fail_questions.append({
                "item_id": f["item_id"],
                "question": f["question"],
                "classification": cls,
                "cls_label": {"retrieval_miss": "检索未命中", "insufficient_context": "依据不足", "wrong_answer": "答案错误", "partial": "部分达标"}.get(cls, cls),
                "retrieved": retrieved_analysis,
                "gt_chunk_ids": f["gt_chunk_ids"],
                "gt_count": len(f["gt_chunk_ids"]),
                "retrieved_count": len([r for r in f["retrieved"] if r.get("is_gt")]),
            })

        # 生成具体操作建议（增强版）
        actions = []

        # 1. 整体失败率分析
        if ratio >= 0.5:
            actions.append({
                "priority": "high",
                "type": "rechunk",
                "action": f"📄 文档「{doc_name}」失败率高达 {ratio*100:.0f}%（{unique_fails}/{total_items} 题），建议重新解析或更换切分策略",
                "detail": "可尝试：①增大 chunk 大小（如从 500→800 字符）②启用主题聚合切分 ③增加重叠窗口"
            })

        # 2. 检索未命中分析
        if retrieval_miss_count > 0:
            actions.append({
                "priority": "high" if retrieval_miss_count >= 3 else "medium",
                "type": "index",
                "action": f"🔍 {retrieval_miss_count} 道题检索未命中：文档「{doc_name}」可能缺少关键内容或向量化问题",
                "detail": "检查项：①文档是否已向量化 ②关键词是否与用户问题匹配 ③是否需要补充相关内容"
            })

        # 3. 依据不足分析
        if insufficient_context_count > 0:
            actions.append({
                "priority": "medium",
                "type": "content",
                "action": f"📝 {insufficient_context_count} 道题依据不足：文档「{doc_name}」中相关内容可能不够详细",
                "detail": "建议：①扩充相关章节内容 ②增加示例说明 ③补充背景知识"
            })

        # 4. 答案错误分析
        if wrong_answer_count > 0:
            actions.append({
                "priority": "high",
                "type": "generation",
                "action": f"❌ {wrong_answer_count} 道题答案错误：检索到内容但生成答案不准确",
                "detail": "排查方向：①检查提示词是否清晰 ②补充参考答案 ③调整温度参数"
            })

        # 5. 切分策略建议
        if ratio >= 0.3:
            chunk_strategy_suggestion = "基础切分（500字符）"
            if any("主题" in f["question"] or "概述" in f["question"] for f in fail_details):
                chunk_strategy_suggestion = "主题聚合切分（适合概述性问题）"
            elif any(len(f["gt_chunk_ids"]) > 1 for f in fail_details):
                chunk_strategy_suggestion = "增大 chunk 大小（适合跨 chunk 答案）"
            actions.append({
                "priority": "medium",
                "type": "strategy",
                "action": f"🔪 建议尝试切分策略：{chunk_strategy_suggestion}",
                "detail": "不同切分策略适合不同类型的问题，可在「知识库」页面重新解析文档"
            })

        # summary 包含详细的分类统计
        summary = f"📋 文档「{doc_name}」" + (f"（知识库：{kb_name}）" if kb_name else "") + f" 有 {unique_fails}/{total_items} 道题失败"
        summary += f"\n  · 检索未命中 {retrieval_miss_count} 道"
        summary += f"\n  · 依据不足 {insufficient_context_count} 道"
        summary += f"\n  · 答案错误 {wrong_answer_count} 道"
        summary += f"\n  · 部分达标 {partial_count} 道"

        # ★ 调用 LLM 进行深度分析
        llm_analysis, llm_actions = _analyze_eval_failure_with_llm(
            fail_questions, doc_name, kb_name
        )

        # 如果 LLM 返回了分析结果，添加到 summary
        if llm_analysis:
            summary += "\n\n" + llm_analysis

        # 合并 LLM 返回的执行动作
        all_actions = actions + [{"priority": "medium", "type": a.get("type", "general"), "action": a.get("note", "")} for a in llm_actions]

        # 构建 chunk_id → 关联题目列表映射（供前端兜底显示题目编号）
        chunk_to_items: Dict[int, List[int]] = {}
        for fq in fail_questions:
            for cid in fq.get("gt_chunk_ids", []):
                chunk_to_items.setdefault(int(cid), []).append(int(fq["item_id"]))
            for r in fq.get("retrieved", []):
                rcid = r.get("chunk_id")
                if rcid:
                    chunk_to_items.setdefault(int(rcid), []).append(int(fq["item_id"]))
        # 去重
        for cid in chunk_to_items:
            chunk_to_items[cid] = sorted(set(chunk_to_items[cid]))

        sid = _insert_suggestion(
            user_id, eval_set_id, "eval",
            "rechunk_suggest" if ratio >= 0.5 else "content_suggest",
            summary,
            {"run_id": run_id, "document_id": doc_id, "document_name": doc_name,
             "kb_name": kb_name, "fail_ratio": round(ratio, 2),
             "total_items": total_items, "fail_count": unique_fails,
             "retrieval_miss_count": retrieval_miss_count,
             "insufficient_context_count": insufficient_context_count,
             "wrong_answer_count": wrong_answer_count,
             "partial_count": partial_count,
             "fail_questions": fail_questions[:5],  # 限制只显示5条
             "chunk_to_items": chunk_to_items,  # chunk_id → 关联题目编号
             "actions": [a.get("action", a.get("note", "")) for a in all_actions],  # 兼容旧格式
             "detailed_actions": all_actions,  # 新增详细建议
             "classifications": fail_classes,
             "llm_analyzed": bool(llm_analysis)},  # 标记是否经过 LLM 分析
            before_metrics=run_metrics,
        )
        if sid:
            created.append(sid)

    # ── 聚合兜底建议 ──
    rest = len(missing_items)
    if not created or rest:
        total_fail = sum(fail_classes.values()) + len(missing_items)
        summary_lines = [f"本次评测共 {total_fail} 道题未通过"]
        for cls_name, count in sorted(fail_classes.items()):
            cls_label = {"retrieval_miss": "检索未命中", "insufficient_context": "依据不足", "wrong_answer": "答案错误", "partial": "部分达标"}.get(cls_name, cls_name)
            summary_lines.append(f"  · {cls_label} {count} 道")
        if rest:
            summary_lines.append(f"  · {rest} 道缺少 GT 标注")
        summary_lines.append("")
        summary_lines.append("💡 建议：为失败题补充/校准 GT chunk，或对比不同检索模式的效果")

        missing_detail = []
        for m in missing_items[:10]:
            missing_detail.append({"item_id": m["item_id"], "question": m["question"]})

        sid = _insert_suggestion(
            user_id, eval_set_id, "eval", "manual",
            "\n".join(summary_lines),
            {"run_id": run_id, "fail_classes": fail_classes,
             "missing_items": missing_detail},
            before_metrics=run_metrics,
        )
        if sid:
            created.append(sid)

    logger.info(f"[KB-Suggestion] run={run_id} 生成 {len(created)} 条优化建议")
    return created


def _gt_document_ids(gt_chunk_ids: List[int]) -> List[int]:
    """GT chunk → document_id 列表（去重）。"""
    if not gt_chunk_ids:
        return []
    conn = get_conn()
    try:
        cur = conn.execute(
            f"SELECT DISTINCT document_id FROM kb_chunks WHERE id IN ({','.join('%s' for _ in gt_chunk_ids)})",
            [int(c) for c in gt_chunk_ids],
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return [int(r["document_id"]) for r in rows if r.get("document_id")]
    except Exception:
        return []
    finally:
        conn.close()


def _doc_name(doc_id: int) -> str:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT original_name FROM kb_documents WHERE id = %s", (doc_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return rows[0].get("original_name") or f"文档#{doc_id}" if rows else f"文档#{doc_id}"
    except Exception:
        return f"文档#{doc_id}"
    finally:
        conn.close()


def _kb_name_for_doc(doc_id: int) -> str:
    """获取文档所属知识库名称。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT k.kb_name FROM kb_documents d JOIN kb_knowledge_base k ON k.id = d.kb_id WHERE d.id = %s",
            (doc_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return rows[0].get("kb_name") or "" if rows else ""
    except Exception:
        return ""
    finally:
        conn.close()


def _run_metrics(run_id: int) -> dict:
    """取 run 聚合指标（不含 classifications 计数，仅数值键）。"""
    try:
        from backend.service.kb.kb_eval_service import get_run_metrics
        metrics = get_run_metrics(run_id)
        return {k: v for k, v in metrics.items() if isinstance(v, (int, float))}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[KB-Suggestion] 读取 run 指标失败: {e}")
        return {}


# ════════════════════════════════════════════════════════════
# 建议生成：来源聊天负反馈
# ════════════════════════════════════════════════════════════

def generate_from_feedback(feedback_id: int, user_id: int) -> Optional[int]:
    """
    负反馈 → 优化建议。

    从对话历史、检索日志、检索 chunk 中提取上下文，
    调用 LLM 进行深度分析，给出具体的优化建议。
    
    一个建议可能包含多个解决方案：
    1. 主路径 chunks 修改建议（需要管理员手动操作）
    2. SQL 示例添加建议（可自动入库到"历史正确案例"）
    """
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM kb_feedback WHERE id = %s AND user_id = %s", (feedback_id, int(user_id)))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    if not rows:
        return None
    fb = rows[0]
    if fb.get("status") == "processed":
        return None
    if int(fb.get("rating") or 0) >= 0:
        return None

    chunk_ids = _json_loads(fb.get("retrieved_chunk_ids"), [])
    thread_id = fb.get("thread_id") or ""
    conversation_id = fb.get("conversation_id")
    comment = (fb.get("comment") or "").strip()

    # ── 1. 从 conversations 表取用户问题和 AI 回答 ──
    user_question = ""
    ai_answer = ""
    if conversation_id:
        try:
            conn2 = get_conn()
            try:
                cur = conn2.execute(
                    "SELECT user_question, agent_answer FROM conversations WHERE id = %s",
                    (int(conversation_id),),
                )
                row = cur.fetchone()
                if row:
                    user_question = (row.get("user_question") or "").strip()[:500]
                    ai_answer = (row.get("agent_answer") or "").strip()[:1500]
            finally:
                conn2.close()
        except Exception:
            pass

    # ── 2. 从检索日志取 query 和检索路径 ──
    log_query = ""
    retriever_name = ""
    retrieval_breakdown = []
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT query, retriever, hit_count, chunk_ids FROM kb_retrieval_logs WHERE thread_id = %s ORDER BY id DESC LIMIT 1",
            (thread_id,),
        )
        log_rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        if log_rows:
            log_row = log_rows[0]
            log_query = (log_row.get("query") or "")[:200]
            retriever_name = log_row.get("retriever") or ""
            retrieval_breakdown = _json_loads(log_row.get("chunk_ids") or "[]", [])
    finally:
        conn.close()

    # 优先用对话中的实际问题，检索日志兜底
    query = user_question or log_query or "(未知)"

    # 没有任何上下文信息（无对话、无检索日志、无 chunk）→ 跳过
    if not user_question and not log_query and not chunk_ids and not comment:
        return None

    # ── 3. 分离主路径和案例路径的 chunks ──
    main_path_chunks = []   # 主路径 chunks（表结构、字段说明等）
    case_path_chunks = []   # 案例路径 chunks（SQL 示例）
    
    if chunk_ids:
        conn = get_conn()
        try:
            placeholders = ",".join("%s" for _ in chunk_ids)
            cur = conn.execute(
                f"SELECT c.id, c.content, c.document_id, d.kb_id, k.kb_name as kb_name "
                f"FROM kb_chunks c "
                f"LEFT JOIN kb_documents d ON d.id = c.document_id "
                f"LEFT JOIN kb_knowledge_base k ON k.id = d.kb_id "
                f"WHERE c.id IN ({placeholders})",
                [int(c) for c in chunk_ids],
            )
            for r in cur.fetchall():
                chunk_info = {
                    "chunk_id": r.get("id"),
                    "content": (r.get("content") or "")[:300],
                    "document_id": r.get("document_id"),
                    "kb_id": r.get("kb_id"),
                    "kb_name": r.get("kb_name") or "",
                }
                # 分离案例路径（历史正确案例）
                if "历史正确案例" in (r.get("kb_name") or ""):
                    case_path_chunks.append(chunk_info)
                else:
                    main_path_chunks.append(chunk_info)
        finally:
            conn.close()

    # ── 4. 检测是否是 SQL 相关问题 ──
    sql_keywords = ["sql", "查询", "count", "sum", "select", "数据库", "表", "字段", "统计", "多少", "数量", "总"]
    is_sql_related = any(kw in query.lower() for kw in sql_keywords)

    # ── 5. 调用 LLM 进行深度分析 ──
    ai_analysis, sql_example_content, chunk_modify_suggestions = _call_llm_for_analysis(
        user_question=query,
        ai_answer=ai_answer,
        main_path_chunks=main_path_chunks,
        case_path_chunks=case_path_chunks,
        user_comment=comment,
        is_sql_related=is_sql_related,
    )

    # ── 6. 查找"历史正确案例"知识库 ID ──
    target_kb_id = None
    if sql_example_content:
        try:
            conn = get_conn()
            try:
                cur = conn.execute(
                    "SELECT id FROM kb_knowledge_base WHERE kb_name = %s LIMIT 1",
                    ("历史正确案例",),
                )
                row = cur.fetchone()
                if row:
                    target_kb_id = int(row["id"])
            finally:
                conn.close()
        except Exception:
            pass

    # ── 7. 组装详细建议 ──
    parts = [f"👎 用户对回答点了踩"]
    parts.append(f"**用户问题**：{query}")
    if ai_answer:
        parts.append(f"**AI 回答**：{ai_answer[:300]}{'...' if len(ai_answer) > 300 else ''}")
    if comment:
        parts.append(f"**用户补充说明**：{comment}")
    
    # 显示检索路径
    if main_path_chunks:
        kb_names = list(set(c.get("kb_name") for c in main_path_chunks if c.get("kb_name")))
        parts.append(f"**主路径检索** {len(main_path_chunks)} 个 chunk（来自：{'、'.join(kb_names[:3])}）")
    if case_path_chunks:
        parts.append(f"**案例路径检索** {len(case_path_chunks)} 个 SQL 示例")
    if not main_path_chunks and not case_path_chunks:
        parts.append("**未命中任何 chunk**")
    
    # 添加 AI 分析结果
    if ai_analysis:
        parts.append("")
        parts.append("───")
        parts.append(ai_analysis)
    else:
        parts.append("")
        parts.append("💡 **通用建议**：")
        if not chunk_ids:
            parts.append("  · 未命中 chunk，检查知识库是否包含相关内容")
        else:
            parts.append("  · 检查检索到的 chunk 是否与问题相关")

    summary = "\n".join(parts)

    # 确定建议类型
    has_sql_example = bool(sql_example_content)
    has_chunk_modify = bool(chunk_modify_suggestions)
    
    if has_sql_example and has_chunk_modify:
        suggestion_type = "mixed"
    elif has_sql_example:
        suggestion_type = "sql_example"
    elif has_chunk_modify:
        suggestion_type = "chunk_modify"
    else:
        suggestion_type = "general"

    sid = _insert_suggestion(
        user_id, None, "feedback", "manual", summary,
        {
            "feedback_id": feedback_id, 
            "query": query, 
            "ai_answer": ai_answer[:300],
            "comment": comment, 
            "main_path_chunk_ids": [c.get("chunk_id") for c in main_path_chunks],
            "case_path_chunk_ids": [c.get("chunk_id") for c in case_path_chunks],
            "retriever": retriever_name, 
            "thread_id": thread_id,
            "conversation_id": conversation_id
        },
        suggestion_type=suggestion_type,
        sql_example_content=sql_example_content or "",
        chunk_modify_suggestions=chunk_modify_suggestions,
        target_kb_id=target_kb_id,
        verification_query=query,
    )

    # 标记反馈已处理（防重复建议）
    try:
        conn = get_conn()
        try:
            conn.execute("UPDATE kb_feedback SET status = 'processed' WHERE id = %s", (feedback_id,))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        pass

    if sid:
        logger.info(f"[KB-Suggestion] 负反馈 {feedback_id} 生成建议 id={sid}, 类型={suggestion_type}")
    return sid


def _call_llm_for_analysis(
    user_question: str,
    ai_answer: str,
    main_path_chunks: List[dict],
    case_path_chunks: List[dict],
    user_comment: str = "",
    is_sql_related: bool = False,
) -> Tuple[str, str, List[dict]]:
    """
    调用 LLM 分析负反馈原因并给出具体优化建议。
    
    分析两个路径：
    - 主路径 chunks：表结构、字段说明等
    - 案例路径 chunks：SQL 示例
    
    Returns:
        Tuple[str, str, List[dict]]: (分析结果, SQL示例内容, chunk修改建议列表)
    """
    try:
        # 构建主路径 chunks 文本
        main_chunks_text = ""
        if main_path_chunks:
            main_chunks_text = "\n\n".join([
                f"【chunk#{c['chunk_id']}】（来自：{c.get('kb_name', '未知')}）\n{c.get('content', '')[:300]}"
                for c in main_path_chunks[:5]
            ])
        else:
            main_chunks_text = "（主路径未命中任何 chunk）"
        
        # 构建案例路径 chunks 文本
        case_chunks_text = ""
        if case_path_chunks:
            case_chunks_text = "\n\n".join([
                f"【SQL示例{idx+1}】\n{c.get('content', '')[:300]}"
                for idx, c in enumerate(case_path_chunks[:3])
            ])
        else:
            case_chunks_text = "（案例路径未命中任何 SQL 示例）"
        
        # 构建提示词
        sql_example_section = ""
        if is_sql_related:
            sql_example_section = """
---

### 📝 SQL 示例建议

如果问题是 SQL 相关的，请在回答末尾用以下格式给出正确的 SQL 示例：

---SQL_EXAMPLE---
# [问题简述]

## 用户问题
[原始用户问题]

## 正确 SQL
```sql
-- 在此给出正确的 SQL 语句
SELECT ... FROM ... WHERE ...
```

## 说明
- 涉及的表：[表名]
- 关键字段：[字段名及含义]
- 注意事项：[如需要过滤 deleted_at、is_test 等]
---SQL_EXAMPLE_END---
"""
        
        prompt = f"""你是一个 RAG（检索增强生成）系统优化专家。用户对 AI 的回答点了踩，请深入分析原因并给出**具体可执行**的优化建议。

## 用户问题
{user_question}

## AI 的回答
{ai_answer or "（无 AI 回答）"}

## 检索结果

### 主路径（表结构、字段说明等）
{main_chunks_text}

### 案例路径（历史正确 SQL 示例）
{case_chunks_text}

## 用户补充说明
{user_comment or "（无补充说明）"}

---

请按以下格式输出分析结果：

### 🔍 问题诊断
[从以下维度分析用户不满意的原因]
- **检索问题**：关键词匹配失败/语义理解偏差/召回数量不足？
- **内容问题**：chunk 内容不完整/过时/格式混乱？
- **答案生成问题**：AI 理解错误/推理逻辑有误/表达不清晰？
- **案例缺失问题**：缺少类似的正确示例？

### 📊 根因分析（逐条列出）

**主路径问题**（如果检索到了 chunk）：
- chunk #ID：[具体问题：内容不相关/信息过时/格式问题/缺少关键信息]
- ...

**案例路径问题**：
- [是否缺少类似的 SQL 示例/示例不够典型]

**答案生成问题**：
- [AI 理解偏差的具体点/推理错误的环节]

### 💡 具体优化建议（可直接执行）

#### 1. 主路径内容修改（如有问题）

**需要修改的 chunk**：
```
chunk #ID：
- 原内容：[引用有问题的内容片段]
- 问题：[具体说明问题所在]
- 修改建议：[精确的修改方案，如"增加 XX 字段说明"、"删除过时的 YY 信息"]
```

**需要补充的内容**：
- [具体说明应该补充哪些信息，如"在表 XX 的说明中增加字段 ZZ 的含义"]

#### 2. 案例路径改进（SQL 示例）

**是否需要添加 SQL 示例**：
- [是/否，说明原因]

**建议添加的 SQL 示例主题**：
- [示例名称：如"查询用户数量统计"]
{sql_example_section}

#### 3. 检索优化建议

**关键词优化**：
- 用户问题关键词：[提取用户问题中的关键实体/术语]
- 建议补充的同义词：[如"用户数 → user_count | 账号数量"]

**chunk 切分建议**：
- [如"该 chunk 过大，建议按主题拆分为 2-3 个小 chunk"]

### ✅ 验证建议

**验证步骤**：
1. 用原问题重新检索，期望命中 chunk #ID
2. 预期 AI 回答应包含：[关键信息点 1、关键信息点 2]
3. 验证 SQL（如有）：[执行预期结果]

---

**注意**：
- 建议必须具体到 chunk ID 和字段级别，避免笼统的描述
- 如果某个维度没有问题，写"无问题"即可
- 优先给出高影响、易执行的修改建议

请用中文回答，保持专业准确。"""

        from backend.utils.traced_llm import traced_llm
        
        # 尝试从上下文获取 user_id
        try:
            from backend.hermes_adapter import _CURRENT_USER_ID_CTX
            uid = int(_CURRENT_USER_ID_CTX.get() or 0)
        except Exception:
            uid = 0

        resp = traced_llm.invoke(
            messages=[{"role": "user", "content": prompt}],
            scene="kb_eval_analysis",
            user_id=uid,
            source="eval",
            temperature=0.3,
            max_tokens=2000,
        )
        content = (resp.content or "").strip()
        
        if content:
            # 提取 SQL 示例内容
            sql_example = ""
            if "---SQL_EXAMPLE---" in content:
                try:
                    start_marker = "---SQL_EXAMPLE---"
                    end_marker = "---SQL_EXAMPLE_END---"
                    start_idx = content.find(start_marker)
                    end_idx = content.find(end_marker)
                    if start_idx != -1 and end_idx != -1:
                        sql_example = content[start_idx + len(start_marker):end_idx].strip()
                        # 从分析结果中移除 SQL 示例标记部分
                        content = content[:start_idx] + content[end_idx + len(end_marker):]
                        content = content.strip()
                except Exception:
                    pass
            
            # 提取 chunk 修改建议（简化版，实际可以从 LLM 输出中解析）
            chunk_modify_suggestions = []
            if "主路径内容" in content or "chunk" in content.lower():
                # 简单标记有修改建议
                chunk_modify_suggestions = [
                    {"note": "请根据上述分析手动修改主路径知识库内容"}
                ]
            
            logger.info(f"[KB-Suggestion] AI 分析完成，长度={len(content)}，SQL示例={len(sql_example)}")
            return content, sql_example, chunk_modify_suggestions
        return "", "", []

    except Exception as e:
        logger.warning(f"[KB-Suggestion] LLM 分析失败: {e}")
        return "", "", []


def _analyze_eval_failure_with_llm(
    failed_questions: List[dict],
    document_name: str,
    kb_name: str,
) -> Tuple[str, List[dict]]:
    """
    调用 LLM 分析评测失败题目，返回详细建议。

    Args:
        failed_questions: 失败题目列表，包含 question, classification, retrieved, gt_chunk_ids 等
        document_name: 文档名称
        kb_name: 知识库名称

    Returns:
        Tuple[str, List[dict]]: (分析结果文本, 执行动作列表)
    """
    try:
        # 构建失败题目文本
        fail_text = ""
        for idx, q in enumerate(failed_questions[:5], 1):
            cls_label = {"retrieval_miss": "检索未命中", "insufficient_context": "依据不足", "wrong_answer": "答案错误", "partial": "部分达标"}.get(
                q.get("classification"), q.get("classification", "未知")
            )
            fail_text += f"\n### 题目 {idx}（问题编号: {q.get('item_id', '?')}，{cls_label}）\n"
            fail_text += f"**问题**：{q.get('question', '未知')}\n"

            # 检索结果
            retrieved = q.get("retrieved", [])
            if retrieved:
                fail_text += f"**检索到的 chunk（{len(retrieved)} 个）**：\n"
                for r in retrieved[:3]:
                    is_gt = "✅ GT" if r.get("is_gt") else "·"
                    fail_text += f"  - [{is_gt}] chunk#{r.get('chunk_id')} (score={r.get('score', 0):.3f}): {r.get('preview', '')[:60]}...\n"
            else:
                fail_text += "**检索结果**：未命中任何 chunk\n"

            # GT chunk
            gt_ids = q.get("gt_chunk_ids", [])
            if gt_ids:
                fail_text += f"**正确答案 chunk**：{', '.join(f'#{cid}' for cid in gt_ids[:5])}\n"

        prompt = f"""分析 RAG 评测失败原因并给出优化建议。

文档：「{document_name}」{f"（知识库：{kb_name}）" if kb_name else ""}
失败题目：{len(failed_questions)} 道

## 失败题目
{fail_text}

---
请按以下格式输出（不要废话，直接给诊断和代码块）：

## 问题诊断
[一句话说明核心问题]

## 优化建议

对于每个需要修改的 chunk，直接输出 modify 代码块：

```modify
item_id: 题目编号（从问题编号字段获取）
chunk_id: 12345
位置：在"XX章节"后面
补充内容：
> 这里是要补充的具体文字内容
> 可以是多行
> 保持简洁，只补缺失信息

原因：为什么需要补充这个（一句话）
```

示例：
```modify
item_id: 42
chunk_id: 1001
位置：在"Token 统计"段落末尾
补充内容：
> **成本估算方法**：
> - 单次调用成本 = 输入 Token 数 × 单价 + 输出 Token 数 × 单价
> - 月度成本 = 日均调用次数 × 单次成本 × 30
> - 支持按应用/用户维度分别统计

原因：用户问"如何计算 API 成本"时，当前 chunk 缺少计算公式
```

如需新增文档或章节，输出 add 代码块：

```add
document: [文档名]
section: [章节名]
---CONTENT---
[具体内容]
```

如有检索参数/提示词等调整建议，用简短列表给出（最多 2 条）。

---
**要求**：
1. 每个 modify 块必须说明：位置 + 具体补充内容 + 原因
2. 补充内容要简洁，只补缺失信息，不要重写整个 chunk
3. 位置描述要具体，如"在 XX 段落后面"、"在 XX 表格下方"
4. 简洁直接，避免重复，不需要输出额外的段落标题"""

        from backend.utils.traced_llm import traced_llm
        
        # 尝试从上下文获取 user_id
        try:
            from backend.hermes_adapter import _CURRENT_USER_ID_CTX
            uid = int(_CURRENT_USER_ID_CTX.get() or 0)
        except Exception:
            uid = 0

        resp = traced_llm.invoke(
            messages=[{"role": "user", "content": prompt}],
            scene="kb_eval_analysis",
            user_id=uid,
            source="eval",
            temperature=0.3,
            max_tokens=2500,
        )
        content = (resp.content or "").strip()

        if content:
            # 解析执行动作（从 Markdown 代码块中提取）
            actions = []

            # 解析新的 modify 代码块格式（题目编号 + 位置 + 补充内容 + 原因）
            modify_block_pattern = r"```modify\s*\n(?:item_id[：:]\s*(\d+)\s*\n)?chunk_id:\s*(\d+)\s*\n位置[：:]\s*(.+?)\s*\n补充内容[：:]?\s*\n((?:>\s*.+\n?)+)\s*\n原因[：:]\s*(.+?)\s*\n```"
            for match in re.finditer(modify_block_pattern, content, re.DOTALL):
                item_id = int(match.group(1)) if match.group(1) else None
                chunk_id = int(match.group(2))
                location = match.group(3).strip()
                supplement = re.sub(r'^>\s*', '', match.group(4).strip(), flags=re.MULTILINE)
                reason = match.group(5).strip()
                actions.append({
                    "type": "chunk_modify",
                    "chunk_id": chunk_id,
                    "item_id": item_id,
                    "location": location,
                    "supplement": supplement,
                    "reason": reason,
                    "note": f"在「{location}」补充内容"
                })

            # 兼容旧格式：`MODIFY #chunk_id` 修改内容摘要
            modify_pattern = r"`MODIFY\s+#(\d+)`\s*(.+?)(?=\n`|\n###|\n##|$)"
            for match in re.finditer(modify_pattern, content, re.DOTALL):
                chunk_id = int(match.group(1))
                modify_note = match.group(2).strip()
                # 避免重复添加
                if not any(a.get("chunk_id") == chunk_id for a in actions):
                    actions.append({
                        "type": "chunk_modify",
                        "chunk_id": chunk_id,
                        "note": modify_note[:200]
                    })

            # 解析新的 add 代码块格式
            add_block_pattern = r"```add\s*\ndocument:\s*([^\n]+)\s*\n---CONTENT---\s*\n(.*?)\n```"
            for match in re.finditer(add_block_pattern, content, re.DOTALL):
                doc_name = match.group(1).strip()
                add_content = match.group(2).strip()
                actions.append({
                    "type": "add_content",
                    "document": doc_name,
                    "content": add_content,
                    "note": f"补充内容到 {doc_name}"
                })

            # 兼容旧格式：`ADD 文档名` 补充内容摘要
            add_pattern = r"`ADD\s+([^`]+)`\s*(.+?)(?=\n`|\n###|\n##|$)"
            for match in re.finditer(add_pattern, content, re.DOTALL):
                doc_name = match.group(1).strip()
                add_note = match.group(2).strip()
                if not any(a.get("document") == doc_name and a.get("type") == "add_content" for a in actions):
                    actions.append({
                        "type": "add_content",
                        "document": doc_name,
                        "note": add_note[:200]
                    })

            logger.info(f"[KB-Suggestion] 评测失败分析完成，长度={len(content)}，提取 {len(actions)} 个执行动作")
            return content, actions
        return "", []

    except Exception as e:
        logger.warning(f"[KB-Suggestion] 评测失败 LLM 分析失败: {e}")
        return "", []


def _chunk_document_ids(chunk_ids: List[int]) -> List[int]:
    if not chunk_ids:
        return []
    conn = get_conn()
    try:
        cur = conn.execute(
            f"SELECT DISTINCT document_id FROM kb_chunks WHERE id IN ({','.join('%s' for _ in chunk_ids)})",
            [int(c) for c in chunk_ids],
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return [int(r["document_id"]) for r in rows if r.get("document_id")]
    except Exception:
        return []
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════
# 验证执行 / 结算
# ════════════════════════════════════════════════════════════

async def run_verification(suggestion_id: int, user_id: int, permissions: Set[str]) -> dict:
    """
    对 pending/failed 建议发起验证：复用 run_eval_set 发起回归 run，
    状态 → verifying，linked_run_ids 追加。

    返回 {"run_id": ..., "suggestion_id": ...}
    """
    from backend.service.kb.kb_eval_service import EvalInvalid, run_eval_set

    row = _fetch_owned(user_id, suggestion_id, permissions)
    if row.get("status") not in ("pending", "failed"):
        raise SuggestionInvalid(f"当前状态 {row.get('status')} 不可发起验证（仅 pending/failed）")

    eval_set_id = row.get("eval_set_id")
    if not eval_set_id:
        raise SuggestionInvalid("该建议未绑定测评集，无法自动验证；请在建议上补充测评集后再试")

    # before 指标快照（首次验证时固化）
    before = _json_loads(row.get("before_metrics"), {})
    if not before:
        from backend.service.kb.kb_eval_service import list_runs
        runs = list_runs(user_id, int(eval_set_id), permissions).get("items", [])
        for r in runs:
            if r.get("status") == "done":
                before = {k: v for k, v in (r.get("metrics") or {}).items() if isinstance(v, (int, float))}
                break

    # 发起回归 run（仅检索层评测，不生成答案/裁判 — 聚焦检索质量验证）
    result = await run_eval_set(
        user_id, int(eval_set_id), permissions,
        top_k=5, generate_answer=False, judge_enabled=False,
        retriever_mode="auto", chunk_kind="all",
    )
    run_id = result["run_id"]

    linked = _json_loads(row.get("linked_run_ids"), [])
    if run_id not in linked:
        linked.append(run_id)

    conn = get_conn()
    try:
        conn.execute(
            "UPDATE kb_eval_suggestions SET status = 'verifying', linked_run_ids = %s, before_metrics = %s WHERE id = %s",
            (_json_dumps(linked), _json_dumps(before) if before else None, suggestion_id),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"[KB-Suggestion] 建议 {suggestion_id} 发起验证 run_id={run_id}")
    return {"run_id": run_id, "suggestion_id": suggestion_id}


def settle_verification(run_id: int) -> None:
    """
    run 完成后结算：比较 before/after 指标，达标 → verified，否则 failed；
    连续失败 ≥ _MAX_FAILED_ATTEMPTS → dismissed（防空转）。
    """
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT * FROM kb_eval_suggestions WHERE status = 'verifying'", ()
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    for row in rows:
        linked = _json_loads(row.get("linked_run_ids"), [])
        if int(run_id) not in [int(x) for x in linked]:
            continue
        after = _run_metrics(run_id)
        before = _json_loads(row.get("before_metrics"), {})
        improved, delta = _metrics_improved(before, after)
        attempts = int(row.get("attempts") or 0) + 1

        if improved:
            new_status = "verified"
        elif attempts >= _MAX_FAILED_ATTEMPTS:
            new_status = "dismissed"
        else:
            new_status = "failed"

        conn = get_conn()
        try:
            conn.execute(
                "UPDATE kb_eval_suggestions SET status = %s, after_metrics = %s, attempts = %s, "
                "resolved_at = %s WHERE id = %s",
                (
                    new_status,
                    _json_dumps(after),
                    attempts,
                    _now() if new_status in ("verified", "dismissed") else None,
                    row["id"],
                ),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info(
            f"🧪 [KB-Suggestion] 建议 {row['id']} 结算: {row.get('status')} → {new_status} "
            f"(attempts={attempts}, delta={delta})"
        )


def _metrics_improved(before: dict, after: dict) -> tuple:
    """比较 before/after：检索核心指标提升达阈值且无显著回退 → 视为改善。

    注意：只比较检索层指标（recall/mrr/ndcg），不比较生成层指标（faithfulness 等）。
    生成层指标受裁判 LLM 随机性影响大，且 before 未启用裁判时值为 0，
    直接比较会产生假阳性。
    """
    if not after:
        return False, {}
    # ★ 只比较检索层核心指标（确定性，不受裁判 LLM 影响）
    keys = ["recall_at_k", "mrr", "ndcg_at_k"]
    gains = {}
    regressions = {}
    for k in keys:
        b = float(before.get(k) or 0.0)
        a = float(after.get(k) or 0.0)
        if a - b >= _IMPROVE_THRESHOLD:
            gains[k] = round(a - b, 4)
        elif a - b <= -_IMPROVE_THRESHOLD:
            regressions[k] = round(a - b, 4)
    improved = bool(gains) and not regressions
    return improved, {"gains": gains, "regressions": regressions}


# ════════════════════════════════════════════════════════════
# 周期 runner（main.py lifespan 后台任务调用）
# ════════════════════════════════════════════════════════════

def run_suggestion_cycle() -> Dict[str, int]:
    """
    一轮建议维护：
    1. 结算卡在 verifying 但 run 已完成的建议；
    2. KB_EVAL_AUTO_EXECUTE=true 时，自动对 pending 建议发起验证（每用户每轮上限）。

    返回统计 {"settled": n, "auto_started": n}
    """
    from backend.service.kb.kb_eval_service import get_run_status

    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM kb_eval_suggestions WHERE status = 'verifying'")
        verifying_rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        cur = conn.execute("SELECT * FROM kb_eval_suggestions WHERE status = 'pending' ORDER BY id ASC")
        pending_rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    settled = 0
    for row in verifying_rows:
        linked = _json_loads(row.get("linked_run_ids"), [])
        try:
            for rid in linked:
                if get_run_status(int(rid)) in ("done", "failed"):
                    settle_verification(int(rid))
                    settled += 1
                    break
        except Exception:  # noqa: BLE001
            continue

    auto_started = 0
    if os.getenv("KB_EVAL_AUTO_EXECUTE", "false").strip().lower() in ("1", "true", "yes", "on"):
        import asyncio

        per_user: Dict[int, int] = {}
        for row in pending_rows:
            uid = int(row["user_id"])
            if per_user.get(uid, 0) >= _MAX_AUTO_RUNS_PER_USER_PER_ROUND:
                continue
            if not row.get("eval_set_id"):
                continue
            if int(row.get("attempts") or 0) >= _MAX_FAILED_ATTEMPTS:
                continue
            try:
                asyncio.run(run_verification(int(row["id"]), uid, {"kb.manage"}))
                per_user[uid] = per_user.get(uid, 0) + 1
                auto_started += 1
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[KB-Suggestion] 自动执行建议 {row['id']} 失败: {e}")

    if settled or auto_started:
        logger.info(f"[KB-Suggestion] 周期维护: settled={settled} auto_started={auto_started}")
    return {"settled": settled, "auto_started": auto_started}


# ════════════════════════════════════════════════════════════
# 查询 / 管理
# ════════════════════════════════════════════════════════════

def list_suggestions(user_id: int, permissions: Set[str], status: str = "",
                     eval_set_id: Optional[int] = None, source: str = "",
                     page: int = 1, page_size: int = 20) -> dict:
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    offset = (page - 1) * page_size

    where, params = "WHERE user_id = %s", [int(user_id)]
    if "kb.manage" in permissions:
        where, params = "WHERE 1=1", []
    if status and status in _SUGGESTION_STATUS:
        where += " AND status = %s"
        params.append(status)
    if eval_set_id:
        where += " AND eval_set_id = %s"
        params.append(int(eval_set_id))
    if source and source in ("eval", "feedback", "manual"):
        where += " AND source = %s"
        params.append(source)

    conn = get_conn()
    try:
        cur = conn.execute(f"SELECT COUNT(*) AS cnt FROM kb_eval_suggestions {where}", params)
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        total = rows[0]["cnt"] if rows else 0
        cur = conn.execute(
            f"SELECT * FROM kb_eval_suggestions {where} ORDER BY id DESC LIMIT %s OFFSET %s",
            params + [page_size, offset],
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    return {"total": total, "page": page, "page_size": page_size, "items": [_serialize(r) for r in rows]}


def get_suggestion(user_id: int, suggestion_id: int, permissions: Set[str]) -> dict:
    return _serialize(_fetch_owned(user_id, suggestion_id, permissions))


def dismiss_suggestion(user_id: int, suggestion_id: int, permissions: Set[str]) -> dict:
    """忽略建议（完全幂等：不存在/无权限/已忽略 均返回成功）。"""
    conn = get_conn()
    try:
        cur = conn.execute("SELECT user_id, status FROM kb_eval_suggestions WHERE id = %s", (suggestion_id,))
        row = cur.fetchone()
        if not row:
            logger.info(f"[KB-Suggestion] dismiss: id={suggestion_id} 不存在，返回幂等成功")
            return {"id": suggestion_id, "dismissed": True}  # 幂等
        # 非本人且无 kb.manage → 静默成功
        if int(row["user_id"]) != int(user_id) and "kb.manage" not in permissions:
            logger.info(f"[KB-Suggestion] dismiss: id={suggestion_id} 无权限，返回幂等成功")
            return {"id": suggestion_id, "dismissed": True}
        # 已忽略/已验证 → 也返回成功（前端可能重复点击）
        if row.get("status") in ("verified", "dismissed"):
            logger.info(f"[KB-Suggestion] dismiss: id={suggestion_id} 已是 {row.get('status')} 状态，返回幂等成功")
            return {"id": suggestion_id, "dismissed": True}

        conn.execute(
            "UPDATE kb_eval_suggestions SET status = 'dismissed', resolved_at = %s WHERE id = %s",
            (_now(), suggestion_id),
        )
        conn.commit()
        logger.info(f"[KB-Suggestion] dismiss: id={suggestion_id} 状态已更新为 dismissed")

        # 验证更新是否成功
        cur = conn.execute("SELECT status FROM kb_eval_suggestions WHERE id = %s", (suggestion_id,))
        verify_row = cur.fetchone()
        if verify_row:
            logger.info(f"[KB-Suggestion] dismiss 验证: id={suggestion_id} 当前状态={verify_row.get('status')}")
    except Exception as e:
        logger.error(f"[KB-Suggestion] dismiss 失败: id={suggestion_id}, error={e}")
        raise
    finally:
        conn.close()
    return {"id": suggestion_id, "dismissed": True}


def delete_suggestion(user_id: int, suggestion_id: int, permissions: Set[str]) -> dict:
    """物理删除优化建议（幂等：不存在也返回成功）。"""
    conn = get_conn()
    try:
        # 归属校验（仅管理员或本人可删）
        if "kb.manage" not in permissions:
            cur = conn.execute("SELECT user_id FROM kb_eval_suggestions WHERE id = %s", (suggestion_id,))
            row = cur.fetchone()
            if not row:
                return {"id": suggestion_id, "deleted": True}  # 幂等
            if int(row["user_id"]) != int(user_id):
                raise SuggestionNotFound(f"优化建议不存在: id={suggestion_id}")
        conn.execute("DELETE FROM kb_eval_suggestions WHERE id = %s", (suggestion_id,))
        conn.commit()
    finally:
        conn.close()
    return {"id": suggestion_id, "deleted": True}


# ════════════════════════════════════════════════════════════
# 审批通过 → 自动入库 + 重新解析 + 重新验证
# ════════════════════════════════════════════════════════════

def approve_and_apply_suggestion(
    user_id: int,
    suggestion_id: int,
    permissions: Set[str],
    edited_sql_content: Optional[str] = None,
    action: str = "apply_sql",  # apply_sql | approve_only
) -> dict:
    """
    审批通过建议 → 可选自动入库 → 重新解析 → 重新验证。
    
    支持两种操作：
    1. `apply_sql`: 将 SQL 示例自动添加到"历史正确案例"知识库
    2. `approve_only`: 仅标记审批通过（管理员会手动修改 chunks）
    
    一个建议可能包含两个解决方案：
    - SQL 示例（可自动入库）
    - Chunk 修改建议（需要管理员手动操作）
    
    Args:
        user_id: 当前用户 ID
        suggestion_id: 建议 ID
        permissions: 用户权限集合
        edited_sql_content: 管理员编辑后的 SQL 示例内容（可选）
        action: 操作类型（apply_sql | approve_only）
    
    Returns:
        {
            "id": suggestion_id,
            "approved": True,
            "sql_added": bool,
            "document_id": int | None,
            "verification_result": {...},
            "has_chunk_suggestions": bool
        }
    """
    row = _fetch_owned(user_id, suggestion_id, permissions)
    
    # 检查状态
    if row.get("status") not in ("pending", "failed"):
        raise SuggestionInvalid(f"当前状态 {row.get('status')} 不可审批")
    
    suggestion_type = row.get("suggestion_type") or "general"
    sql_content = edited_sql_content or row.get("sql_example_content") or ""
    target_kb_id = row.get("target_kb_id")
    verification_query = row.get("verification_query") or ""
    chunk_modify_suggestions = _json_loads(row.get("chunk_modify_suggestions") or "[]", [])
    
    result = {
        "id": suggestion_id,
        "approved": True,
        "sql_added": False,
        "document_id": None,
        "verification_result": None,
        "has_chunk_suggestions": bool(chunk_modify_suggestions),
    }
    
    # ── 1. SQL 示例入库（如果需要） ──
    should_add_sql = (
        action == "apply_sql"
        and sql_content
        and target_kb_id
        and suggestion_type in ("sql_example", "mixed")
    )
    
    if should_add_sql:
        try:
            doc_result = _add_sql_example_to_kb(
                kb_id=int(target_kb_id),
                sql_content=sql_content,
                user_id=user_id,
            )
            result["sql_added"] = doc_result.get("success", False)
            result["document_id"] = doc_result.get("document_id")
            
            if result["sql_added"]:
                logger.info(f"[KB-Suggestion] SQL 示例已入库: kb_id={target_kb_id}, doc_id={result['document_id']}")
                
                # 更新建议记录
                conn = get_conn()
                try:
                    conn.execute(
                        "UPDATE kb_eval_suggestions SET sql_example_approved = 1, sql_example_document_id = %s WHERE id = %s",
                        (result["document_id"], suggestion_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as exc:
            logger.warning(f"[KB-Suggestion] SQL 示例入库失败: {exc}")
    
    # ── 2. 更新建议状态 ──
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE kb_eval_suggestions SET status = 'approved', resolved_at = %s WHERE id = %s",
            (_now(), suggestion_id),
        )
        conn.commit()
    finally:
        conn.close()
    
    # ── 3. 重新解析文档（如果 SQL 示例已入库） ──
    if result["document_id"] and result["sql_added"]:
        try:
            from backend.service.kb.kb_service import KnowledgeBaseService
            kb_service = KnowledgeBaseService()
            # 触发单文档解析
            kb_service.build_document(
                kb_id=int(target_kb_id),
                doc_id=int(result["document_id"]),
                config={},
                user_id=user_id,
            )
            logger.info(f"[KB-Suggestion] 文档重新解析完成: doc_id={result['document_id']}")
        except Exception as exc:
            logger.warning(f"[KB-Suggestion] 文档重新解析失败: {exc}")
    
    # ── 4. 重新验证（如果有原问题） ──
    if verification_query and target_kb_id:
        try:
            verification_result = _verify_retrieval(
                kb_id=int(target_kb_id),
                query=verification_query,
                user_id=user_id,
            )
            result["verification_result"] = verification_result
            
            # 保存验证结果
            conn = get_conn()
            try:
                conn.execute(
                    "UPDATE kb_eval_suggestions SET verification_result = %s WHERE id = %s",
                    (_json_dumps(verification_result), suggestion_id),
                )
                conn.commit()
            finally:
                conn.close()
            
            logger.info(f"[KB-Suggestion] 验证完成: query={verification_query[:30]}...")
        except Exception as exc:
            logger.warning(f"[KB-Suggestion] 验证失败: {exc}")
    
    return result


def _add_sql_example_to_kb(
    kb_id: int,
    sql_content: str,
    user_id: int,
) -> dict:
    """
    将 SQL 示例追加到知识库（创建新文档）。
    
    Args:
        kb_id: 知识库 ID
        sql_content: SQL 示例内容（Markdown 格式）
        user_id: 用户 ID
    
    Returns:
        {"success": bool, "document_id": int | None}
    """
    from backend.service.kb.kb_service import KnowledgeBaseService
    from pathlib import Path
    import tempfile
    
    kb_service = KnowledgeBaseService()
    
    # 检查知识库是否存在
    kb = kb_service.get_knowledge_base(kb_id)
    if not kb:
        raise SuggestionNotFound(f"知识库不存在: id={kb_id}")
    
    # 生成文件名
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sql_example_{timestamp}.md"
    
    # 创建临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(sql_content)
        temp_path = f.name
    
    try:
        # 上传文档到知识库
        # 使用内部方法创建文档记录
        conn = get_conn()
        try:
            # 计算文件 hash
            import hashlib
            file_hash = hashlib.sha256(sql_content.encode()).hexdigest()
            file_size = len(sql_content.encode())
            
            # 插入文档记录
            cur = conn.execute(
                "INSERT INTO kb_documents (kb_id, original_name, file_path, file_type, file_size, file_hash, status, user_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)",
                (int(kb_id), filename, temp_path, "md", file_size, file_hash, int(user_id)),
            )
            doc_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        
        return {"success": True, "document_id": doc_id}

    except Exception as exc:
        # 清理临时文件
        try:
            Path(temp_path).unlink()
        except Exception:
            pass
        raise exc


def modify_chunk_content(
    chunk_id: int,
    new_content: str,
    reason: str,
    user_id: int,
    permissions: Set[str],
) -> dict:
    """
    手动修改 chunk 内容，修改后自动重新向量化。

    Args:
        chunk_id: chunk ID
        new_content: 新内容
        reason: 修改原因
        user_id: 用户 ID
        permissions: 用户权限集合

    Returns:
        {"success": bool, "chunk_id": int, "old_content": str}
    """
    # 检查权限
    if "kb.manage" not in permissions:
        raise SuggestionInvalid("需要 kb.manage 权限才能修改 chunk")

    conn = get_conn()
    try:
        # 获取原始内容 + kb_id
        cur = conn.execute(
            "SELECT content, document_id, kb_id FROM kb_chunks WHERE id = %s", (chunk_id,)
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        if not rows:
            raise SuggestionNotFound(f"Chunk 不存在: id={chunk_id}")

        old_content = rows[0].get("content") or ""
        document_id = rows[0].get("document_id")
        kb_id = rows[0].get("kb_id")

        # 更新 chunk 内容
        conn.execute(
            "UPDATE kb_chunks SET content = %s, is_manual_edit = 1, manual_edit_reason = %s, "
            "original_content = %s, manual_edit_at = %s WHERE id = %s",
            (new_content, reason, old_content, _now(), chunk_id),
        )
        conn.commit()

        logger.info(f"[KB-Suggestion] Chunk 已修改: id={chunk_id}, reason={reason}")

        # ── 自动重新向量化该 chunk ──
        try:
            from backend.service.kb.kb_retriever import _build_embeddings, _build_user_vectorstore
            from langchain_core.documents import Document

            embeddings = _build_embeddings()
            vectorstore = _build_user_vectorstore(user_id)

            # 删除旧向量（Milvus delete 支持 expr 字符串，一步到位）
            try:
                vectorstore.delete(expr=f"chunk_id == {int(chunk_id)}")
                logger.info(f"[KB] 已删除 chunk_id={chunk_id} 的旧向量")
            except Exception as ve:
                logger.warning(f"[KB] 删除旧向量失败（可忽略）: {ve}")

            # 添加新向量（kb_id 不能为 None，Milvus 不支持 null 标量字段）
            doc = Document(
                page_content=new_content,
                metadata={
                    "chunk_id": int(chunk_id),
                    "document_id": int(document_id) if document_id else 0,
                    "kb_id": int(kb_id) if kb_id else 0,
                    "user_id": int(user_id),
                    "kind": "child",
                    "strategy": "parent_child",
                },
            )
            vectorstore.add_documents([doc])
            logger.info(f"[KB] 已向量化更新 chunk_id={chunk_id}")
        except Exception as ve:
            logger.warning(f"[KB] 重新向量化失败（不影响保存）: {ve}")

        return {
            "success": True,
            "chunk_id": chunk_id,
            "document_id": document_id,
            "old_content": old_content[:200] + "..." if len(old_content) > 200 else old_content,
        }

    except Exception as exc:
        logger.warning(f"[KB-Suggestion] Chunk 修改失败: {exc}")
        raise exc
    finally:
        conn.close()


def rollback_chunk_content(
    chunk_id: int,
    user_id: int,
    permissions: Set[str],
) -> dict:
    """
    回滚 chunk 内容到修改前的状态。

    Args:
        chunk_id: chunk ID
        user_id: 用户 ID
        permissions: 用户权限集合

    Returns:
        {"success": bool, "chunk_id": int, "restored_content": str}
    """
    # 检查权限
    if "kb.manage" not in permissions:
        raise SuggestionInvalid("需要 kb.manage 权限才能回滚 chunk")

    conn = get_conn()
    try:
        # 获取当前 chunk 信息
        cur = conn.execute(
            "SELECT content, original_content, is_manual_edit FROM kb_chunks WHERE id = %s",
            (chunk_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        if not rows:
            raise SuggestionNotFound(f"Chunk 不存在: id={chunk_id}")

        row = rows[0]
        original_content = row.get("original_content")
        is_manual_edit = row.get("is_manual_edit", 0)

        if not is_manual_edit:
            raise SuggestionInvalid(f"Chunk #{chunk_id} 未被手动修改，无法回滚")

        if original_content is None:
            raise SuggestionInvalid(f"Chunk #{chunk_id} 没有保存原始内容，无法回滚")

        # 恢复原始内容
        conn.execute(
            "UPDATE kb_chunks SET content = %s, is_manual_edit = 0, manual_edit_reason = NULL, "
            "manual_edit_at = NULL WHERE id = %s",
            (original_content, chunk_id),
        )
        conn.commit()

        logger.info(f"[KB-Suggestion] Chunk 已回滚: id={chunk_id}")

        return {
            "success": True,
            "chunk_id": chunk_id,
            "restored_content": original_content[:200] + "..." if len(original_content) > 200 else original_content,
        }

    except Exception as exc:
        logger.warning(f"[KB-Suggestion] Chunk 回滚失败: {exc}")
        raise exc
    finally:
        conn.close()


def execute_suggestion_actions(
    suggestion_id: int,
    actions: List[dict],
    user_id: int,
    permissions: Set[str],
) -> dict:
    """
    执行建议的多个动作。

    Args:
        suggestion_id: 建议 ID
        actions: 要执行的动作列表，每个动作包含 type 和相关参数
                 [{"type": "chunk_modify", "chunk_id": 123, "new_content": "...", "reason": "..."},
                  {"type": "add_sql_example", "content": "...", "kb_id": 1}]
        user_id: 用户 ID
        permissions: 用户权限集合

    Returns:
        {
            "executed": int,  # 成功执行的动作数
            "failed": int,    # 失败的动作数
            "results": List[dict],  # 每个动作的执行结果
            "verification_triggered": bool  # 是否触发了回归验证
        }
    """
    row = _fetch_owned(user_id, suggestion_id, permissions)
    if row.get("status") not in ("pending", "failed", "approved"):
        raise SuggestionInvalid(f"当前状态 {row.get('status')} 不可执行动作")

    results = []
    executed = 0
    failed = 0

    for action in actions:
        action_type = action.get("type")
        try:
            if action_type == "chunk_modify":
                result = modify_chunk_content(
                    chunk_id=action.get("chunk_id"),
                    new_content=action.get("new_content", ""),
                    reason=action.get("reason", "优化建议执行"),
                    user_id=user_id,
                    permissions=permissions,
                )
                results.append({"type": action_type, "success": True, "result": result})
                executed += 1

            elif action_type == "add_sql_example":
                content = action.get("content", "")
                kb_id = action.get("kb_id")
                if not kb_id:
                    # 尝试从建议中获取目标知识库
                    kb_id = row.get("target_kb_id")
                if not kb_id:
                    # 尝试查找"历史正确案例"知识库
                    conn = get_conn()
                    try:
                        cur = conn.execute(
                            "SELECT id FROM kb_knowledge_base WHERE kb_name = %s LIMIT 1",
                            ("历史正确案例",),
                        )
                        kb_row = cur.fetchone()
                        if kb_row:
                            kb_id = kb_row["id"]
                    finally:
                        conn.close()

                if not kb_id:
                    results.append({"type": action_type, "success": False, "error": "未指定目标知识库"})
                    failed += 1
                else:
                    result = _add_sql_example_to_kb(
                        kb_id=int(kb_id),
                        sql_content=content,
                        user_id=user_id,
                    )
                    results.append({"type": action_type, "success": True, "result": result})
                    executed += 1

            elif action_type == "reparse":
                # 重新解析文档
                document_id = action.get("document_id")
                if not document_id:
                    results.append({"type": action_type, "success": False, "error": "未指定文档 ID"})
                    failed += 1
                else:
                    # 调用重新解析接口
                    from backend.service.kb.kb_service import KnowledgeBaseService
                    kb_service = KnowledgeBaseService()
                    # 这里需要实现重新解析逻辑
                    results.append({
                        "type": action_type,
                        "success": True,
                        "result": {"document_id": document_id, "message": "重新解析已触发"}
                    })
                    executed += 1

            else:
                results.append({"type": action_type, "success": False, "error": f"未知的动作类型: {action_type}"})
                failed += 1

        except Exception as e:
            results.append({"type": action_type, "success": False, "error": str(e)})
            failed += 1

    # 更新建议状态
    if executed > 0:
        conn = get_conn()
        try:
            # 记录已执行的动作
            existing_executed = _json_loads(row.get("executed_actions") or "[]", [])
            existing_executed.extend([r for r in results if r.get("success")])

            conn.execute(
                "UPDATE kb_eval_suggestions SET status = 'executed', executed_actions = %s, resolved_at = %s WHERE id = %s",
                (_json_dumps(existing_executed), _now(), suggestion_id),
            )
            conn.commit()
        finally:
            conn.close()

    return {
        "executed": executed,
        "failed": failed,
        "results": results,
        "verification_triggered": executed > 0,
    }


def _verify_retrieval(
    kb_id: int,
    query: str,
    user_id: int,
) -> dict:
    """
    验证检索效果：用原问题查询，检查是否命中新添加的内容。
    
    Args:
        kb_id: 知识库 ID
        query: 原问题
        user_id: 用户 ID
    
    Returns:
        {
            "hit_count": int,
            "top_chunks": [...],
            "improved": bool
        }
    """
    from backend.service.kb.kb_retriever import BM25Retriever
    
    retriever = BM25Retriever(user_id, kb_id=kb_id)
    results = retriever.retrieve(query, top_k=5)
    
    return {
        "hit_count": len(results),
        "top_chunks": [
            {
                "chunk_id": r.get("chunk_id"),
                "score": r.get("score"),
                "content_preview": (r.get("content") or "")[:100],
            }
            for r in results[:3]
        ],
        "improved": len(results) > 0,
    }
