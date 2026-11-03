"""
Bad Case 诊断工具

对评测结果中的单题做深度诊断，帮助定位失败原因：
- 检索层：哪些 chunk 被召回？分数如何？是否命中 GT？
- 生成层：答案 vs 参考答案的差异分析
- 六态分类原因说明
- 优化建议

参考：守护之眼 RAG 测评文档「Bad case 的解决策略以及如何排查问题」
"""
import json
from typing import Dict, List, Optional

from backend.db.schema import get_conn
from backend.utils.log_utils import log

logger = log


def _json_loads(raw, default):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def diagnose_result(run_id: int, result_id: int, user_id: int, permissions: set) -> dict:
    """
    对单条评测结果做深度诊断。

    Returns:
        {
            "result_id": ...,
            "question": ...,
            "classification": ...,
            "classification_label": ...,
            "retrieval_analysis": {
                "total_retrieved": ...,
                "gt_hit_count": ...,
                "gt_miss_count": ...,
                "top_chunks": [{"chunk_id", "content_preview", "score", "is_gt", "source"}, ...],
                "max_score": ...,
                "min_score": ...,
            },
            "generation_analysis": {
                "answer_preview": ...,
                "gt_answer_preview": ...,
                "judge_metrics": {...},
            },
            "diagnosis": {
                "root_cause": "retrieval_miss" | "insufficient_context" | "wrong_answer" | "hallucination" | "ok",
                "explanation": "...",
                "suggestions": ["...", ...],
            },
        }
    """
    # 校验 run 归属
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT r.*, rs.eval_set_id, rs.user_id AS run_user_id "
            "FROM kb_eval_results r JOIN kb_eval_runs rs ON rs.id = r.run_id "
            "WHERE r.id = ? AND r.run_id = ?",
            (result_id, run_id),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    if not rows:
        raise ValueError(f"评测结果不存在: result_id={result_id}")
    row = rows[0]

    # 权限校验
    if row["run_user_id"] != user_id and "kb.manage" not in permissions:
        raise ValueError("无权查看此评测结果")

    metrics = _json_loads(row.get("metrics"), {})
    judge_metrics = _json_loads(row.get("judge_metrics"), {})
    retrieved = _json_loads(row.get("retrieved_chunks"), [])
    classification = row.get("classification") or "unjudgeable"

    from backend.service.kb.kb_eval_metrics import CLASSIFICATION
    label = CLASSIFICATION.get(classification, classification)

    # ── 检索层分析 ──
    gt_chunk_ids = _get_gt_chunk_ids(row.get("item_id"))
    gt_id_set = set(gt_chunk_ids)

    # 父子分片：用 original_chunk_id（子片 ID）匹配 GT，否则用 chunk_id
    def _eval_id(r):
        return r.get("original_chunk_id") or r.get("chunk_id")

    gt_hits = [r for r in retrieved if _eval_id(r) in gt_id_set]
    gt_misses = [cid for cid in gt_chunk_ids if cid not in {_eval_id(r) for r in retrieved}]

    scores = [r.get("score", 0) for r in retrieved if r.get("score") is not None]
    max_score = max(scores) if scores else 0
    min_score = min(scores) if scores else 0

    top_chunks = []
    for r in retrieved[:10]:
        content = r.get("content") or ""
        top_chunks.append({
            "chunk_id": r.get("chunk_id"),
            "original_chunk_id": r.get("original_chunk_id"),
            "content_preview": content[:200] + ("..." if len(content) > 200 else ""),
            "score": r.get("score"),
            "is_gt": _eval_id(r) in gt_id_set,
            "source": r.get("retrieval_source", "unknown"),
        })

    retrieval_analysis = {
        "total_retrieved": len(retrieved),
        "gt_hit_count": len(gt_hits),
        "gt_miss_count": len(gt_misses),
        "gt_miss_ids": gt_misses[:10],
        "top_chunks": top_chunks,
        "max_score": round(max_score, 4) if max_score else None,
        "min_score": round(min_score, 4) if min_score else None,
    }

    # ── 生成层分析 ──
    answer = row.get("answer") or ""
    generation_analysis = {
        "answer_preview": answer[:500] + ("..." if len(answer) > 500 else ""),
        "has_answer": bool(answer.strip()),
        "judge_metrics": judge_metrics,
    }

    # ── 诊断结论 ──
    root_cause, explanation, suggestions = _diagnose(
        classification, metrics, judge_metrics, retrieval_analysis, gt_chunk_ids
    )

    return {
        "result_id": result_id,
        "item_id": row.get("item_id"),
        "question": row.get("question") or "",
        "classification": classification,
        "classification_label": label,
        "retrieval_analysis": retrieval_analysis,
        "generation_analysis": generation_analysis,
        "diagnosis": {
            "root_cause": root_cause,
            "explanation": explanation,
            "suggestions": suggestions,
        },
    }


def _get_gt_chunk_ids(item_id: int) -> List[int]:
    """获取题目的 GT chunk id 列表。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT ground_truth_chunk_ids FROM kb_eval_items WHERE id = ?", (item_id,)
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    if not rows:
        return []
    return _json_loads(rows[0].get("ground_truth_chunk_ids"), [])


def _diagnose(
    classification: str,
    metrics: dict,
    judge_metrics: dict,
    retrieval_analysis: dict,
    gt_chunk_ids: List[int],
) -> tuple:
    """
    根据分类和指标生成诊断结论。

    Returns:
        (root_cause, explanation, suggestions)
    """
    root_cause = "ok"
    explanation = ""
    suggestions: List[str] = []

    if classification == "complete":
        root_cause = "ok"
        explanation = "检索命中 GT 且生成质量达标，无需优化。"
        return root_cause, explanation, suggestions

    if classification == "refused":
        root_cause = "retrieval_miss"
        explanation = "系统主动拒答：检索结果最高分低于拒答阈值，判定为知识库中无相关信息。"
        suggestions.append("检查文档是否覆盖了该问题领域的知识")
        suggestions.append("如果是合理问题，考虑降低拒答阈值或补充相关知识文档")
        return root_cause, explanation, suggestions

    if classification == "retrieval_miss":
        root_cause = "retrieval_miss"
        max_score = retrieval_analysis.get("max_score") or 0
        if max_score < 0.5:
            explanation = f"检索完全失效：最高相似度仅 {max_score}，说明 query 与知识库内容语义差距过大。"
            suggestions.append("检查问题表述是否与文档用语一致（如专业术语 vs 口语化表达）")
            suggestions.append("尝试启用查询重写（query_rewrite）进行语义压缩/纠错")
            suggestions.append("考虑更换切分策略（topic 模式可能提升主题完整性）")
        else:
            explanation = f"检索未命中 GT：最高分 {max_score} 尚可，但 GT chunk 未进入 top-K。"
            suggestions.append("增大 top_k 参数看是否能召回 GT")
            suggestions.append("检查 GT chunk 标注是否正确（可能标注的 chunk 本身内容不相关）")
            suggestions.append("尝试 hybrid 混合检索（向量 + BM25 RRF 融合）")
        if not gt_chunk_ids:
            suggestions.append("⚠️ 该题缺少 GT chunk 标注，无法精确判断检索质量，请补充标注")
        return root_cause, explanation, suggestions

    if classification == "insufficient_context":
        root_cause = "insufficient_context"
        faith = judge_metrics.get("faithfulness")
        explanation = f"检索命中但生成不忠实：Faithfulness={faith}，模型回答包含上下文中不存在的信息（幻觉）。"
        suggestions.append("更换更强的生成模型（如从 deepseek-chat 换为 qwen3.6-plus 等低幻觉模型）")
        suggestions.append("优化系统提示词，强调「仅基于参考内容回答，禁止编造」")
        suggestions.append("减小 chunk size 减少上下文噪声")
        suggestions.append("设置 temperature=0 降低生成随机性")
        return root_cause, explanation, suggestions

    if classification == "wrong_answer":
        root_cause = "wrong_answer"
        correct = judge_metrics.get("answer_correctness")
        explanation = f"答案与参考答案严重偏离：AnswerCorrectness={correct}。"
        suggestions.append("检查参考答案（ground_truth）是否过时或本身有误")
        suggestions.append("对比生成答案与参考答案，判断是事实错误还是表述差异")
        suggestions.append("如果是知识更新导致答案过时，需更新知识库文档")
        return root_cause, explanation, suggestions

    if classification == "partial":
        root_cause = "partial"
        low_keys = [k for k, v in judge_metrics.items() if isinstance(v, (int, float)) and v < 0.6]
        explanation = f"部分指标未达标：{', '.join(low_keys)} 低于 0.6 达标线。"
        suggestions.append("针对低分指标定向优化")
        if "faithfulness" in low_keys:
            suggestions.append("Faithfulness 低 → 减少幻觉（换模型/优化提示词）")
        if "answer_relevancy" in low_keys:
            suggestions.append("AnswerRelevancy 低 → 答案可能偏题（优化提示词聚焦问题核心）")
        if "context_precision" in low_keys:
            suggestions.append("ContextPrecision 低 → 检索噪声多（启用 minScore 过滤）")
        if "context_recall" in low_keys:
            suggestions.append("ContextRecall 低 → GT 答案的关键信息未被检索到（补充知识/调整切分）")
        return root_cause, explanation, suggestions

    # unjudgeable
    root_cause = "unknown"
    explanation = "无法判定：缺少裁判分数或评测过程出错。"
    suggestions.append("检查 LLM 模型配置是否正常")
    suggestions.append("查看系统日志排查具体错误")
    return root_cause, explanation, suggestions


def batch_diagnosis_summary(run_id: int, user_id: int, permissions: set) -> dict:
    """
    对 run 的全部结果做批量诊断汇总。

    Returns:
        {
            "total": ...,
            "by_classification": {"complete": n, "retrieval_miss": n, ...},
            "failure_patterns": [
                {"pattern": "检索失效（最高分<0.5）", "count": n, "item_ids": [...]},
                ...
            ],
            "top_failure_items": [{"item_id", "question", "classification", "root_cause"}, ...],
        }
    """
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT r.id, r.item_id, r.question, r.classification, r.metrics, r.judge_metrics, "
            "r.retrieved_chunks "
            "FROM kb_eval_results r WHERE r.run_id = ? ORDER BY r.id",
            (run_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    by_cls: Dict[str, int] = {}
    patterns: Dict[str, List[int]] = {}
    failure_items = []

    for r in rows:
        cls = r.get("classification") or "unjudgeable"
        by_cls[cls] = by_cls.get(cls, 0) + 1

        if cls in ("complete",):
            continue

        metrics = _json_loads(r.get("metrics"), {})
        retrieved = _json_loads(r.get("retrieved_chunks"), [])
        scores = [c.get("score", 0) for c in retrieved if c.get("score") is not None]
        max_score = max(scores) if scores else 0

        # 识别失败模式
        if cls == "retrieval_miss" and max_score < 0.5:
            pattern = "检索失效（最高分<0.5）"
        elif cls == "retrieval_miss":
            pattern = "检索未命中 GT（分数尚可但 GT 未进 top-K）"
        elif cls == "insufficient_context":
            pattern = "生成幻觉（Faithfulness 低）"
        elif cls == "wrong_answer":
            pattern = "答案错误（AnswerCorrectness 低）"
        elif cls == "refused":
            pattern = "系统拒答"
        elif cls == "partial":
            pattern = "部分指标未达标"
        else:
            pattern = "其他/无法判定"

        patterns.setdefault(pattern, []).append(r["item_id"])
        failure_items.append({
            "item_id": r["item_id"],
            "question": (r.get("question") or "")[:80],
            "classification": cls,
            "root_cause": pattern,
        })

    # 按模式聚合排序
    failure_patterns = [
        {"pattern": p, "count": len(ids), "item_ids": ids[:20]}
        for p, ids in sorted(patterns.items(), key=lambda x: -len(x[1]))
    ]

    return {
        "total": len(rows),
        "by_classification": by_cls,
        "failure_patterns": failure_patterns,
        "top_failure_items": failure_items[:20],
    }
