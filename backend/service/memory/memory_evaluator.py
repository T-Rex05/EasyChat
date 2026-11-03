"""
Memory Evaluator - 记忆系统评估

负责:
- LLM-as-Judge 评估
- Precision/Recall/F1 计算
- 评估运行管理
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.service.memory import MemoryService, get_memory_service
from backend.utils.log_utils import log

logger = log


class MemoryEvaluator:
    """
    记忆系统评估器
    
    支持:
    - LLM-as-Judge 评估
    - 精确率/召回率/F1 计算
    - 批量评估运行
    """
    
    # LLM 评估提示词
    EVAL_PROMPT = """你是一个记忆检索质量评估专家。

用户查询：
{query}

期望答案：
{expected_answer}

检索到的记忆：
{retrieved_memories}

请评估：
1. 相关性：检索到的记忆是否与查询相关？
2. 完整性：是否包含了回答问题所需的关键信息？
3. 准确性：记忆内容是否准确？

以 JSON 格式返回：
{{
  "is_relevant": true/false,
  "is_complete": true/false,
  "is_accurate": true/false,
  "relevance_score": 0-1,
  "explanation": "简要解释"
}}"""

    def __init__(self):
        """初始化评估器"""
        self._memory_service = get_memory_service()
    
    def evaluate_single(
        self,
        query: str,
        expected_answer: str,
        user_id: int,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        评估单个查询
        
        Args:
            query: 查询文本
            expected_answer: 期望答案
            user_id: 用户ID
            top_k: 检索数量
            
        Returns:
            评估结果
        """
        start_time = time.time()
        
        # 检索记忆
        retrieved = self._memory_service.search_memories(
            user_id=user_id,
            query=query,
            top_k=top_k
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # 提取检索到的内容和ID
        retrieved_ids = [item["memory"]["id"] for item in retrieved]
        retrieved_contents = [item["memory"]["content"] for item in retrieved]
        
        # LLM 评估
        llm_judgment = self._llm_evaluate(
            query=query,
            expected_answer=expected_answer,
            retrieved_memories=retrieved_contents
        )
        
        return {
            "retrieved_memory_ids": json.dumps(retrieved_ids),
            "retrieved_contents": json.dumps(retrieved_contents[:3]),  # 只存前3条
            "llm_judgment": json.dumps(llm_judgment),
            "is_correct": llm_judgment.get("is_relevant", False),
            "relevance_score": llm_judgment.get("relevance_score", 0),
            "latency_ms": latency_ms
        }
    
    def _llm_evaluate(
        self,
        query: str,
        expected_answer: str,
        retrieved_memories: List[str]
    ) -> Dict[str, Any]:
        """
        使用 LLM 进行评估
        
        Args:
            query: 查询
            expected_answer: 期望答案
            retrieved_memories: 检索到的记忆列表
            
        Returns:
            评估结果
        """
        try:
            # 构建提示词
            memories_text = "\n".join([
                f"{i+1}. {mem[:200]}"
                for i, mem in enumerate(retrieved_memories[:5])
            ]) or "无检索结果"

            prompt = self.EVAL_PROMPT.format(
                query=query,
                expected_answer=expected_answer[:500],
                retrieved_memories=memories_text
            )

            # 调用 LLM（通过 traced_llm）
            from backend.utils.traced_llm import traced_llm
            
            # 尝试从上下文获取 user_id
            try:
                from backend.hermes_adapter import _CURRENT_USER_ID_CTX
                uid = int(_CURRENT_USER_ID_CTX.get() or 0)
            except Exception:
                uid = 0

            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="memory_eval",
                user_id=uid,
                source="memory",
                temperature=0,
                max_tokens=1024,
            )
            content = resp.content

            # 解析结果
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(content[start:end])
                return result
            
        except Exception as e:
            logger.warning(f"LLM evaluation failed: {e}")
        
        return {"is_relevant": False, "relevance_score": 0, "explanation": "Evaluation failed"}
    
    def calculate_metrics(
        self,
        expected_ids: List[int],
        retrieved_ids: List[int]
    ) -> Dict[str, float]:
        """
        计算 Precision/Recall/F1
        
        Args:
            expected_ids: 期望的记忆ID列表
            retrieved_ids: 检索到的记忆ID列表
            
        Returns:
            {precision, recall, f1}
        """
        if not expected_ids and not retrieved_ids:
            return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
        
        if not expected_ids:
            return {"precision": 0.0, "recall": 1.0, "f1": 0.0}
        
        if not retrieved_ids:
            return {"precision": 1.0, "recall": 0.0, "f1": 0.0}
        
        expected_set = set(expected_ids)
        retrieved_set = set(retrieved_ids)
        
        true_positives = len(expected_set & retrieved_set)
        
        precision = true_positives / len(retrieved_set) if retrieved_set else 0
        recall = true_positives / len(expected_set) if expected_set else 0
        
        if precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = 0
        
        return {
            "precision": precision,
            "recall": recall,
            "f1": f1
        }
    
    def run_evaluation(
        self,
        eval_set_id: int,
        user_id: int,
        run_type: str = "manual"
    ) -> Dict[str, Any]:
        """
        运行完整评估
        
        Args:
            eval_set_id: 评估集ID
            user_id: 用户ID
            run_type: 运行类型
            
        Returns:
            评估结果
        """
        # 创建运行记录
        run_id = self._create_run(eval_set_id, user_id, run_type)
        
        try:
            # 更新状态为运行中
            self._update_run_status(run_id, "running")
            
            # 获取评估项
            items = self._get_eval_items(eval_set_id)
            if not items:
                self._update_run_status(run_id, "failed", error="No evaluation items")
                return {"status": "failed", "error": "No evaluation items"}
            
            # 执行评估
            results = []
            total_latency = 0
            
            for item in items:
                result = self.evaluate_single(
                    query=item["query"],
                    expected_answer=item.get("expected_answer", ""),
                    user_id=user_id
                )
                
                # 保存结果
                self._save_result(run_id, item["id"], result)
                results.append(result)
                total_latency += result["latency_ms"]
            
            # 计算总体指标
            passed = sum(1 for r in results if r["is_correct"])
            avg_relevance = sum(r["relevance_score"] for r in results) / len(results)
            avg_latency = total_latency // len(results)
            
            # 更新运行记录
            self._update_run_completed(
                run_id,
                total_items=len(items),
                passed_items=passed,
                precision_score=avg_relevance,  # 简化：用相关性分数代替
                recall_score=avg_relevance,
                f1_score=avg_relevance,
                latency_ms=avg_latency
            )
            
            return {
                "status": "completed",
                "run_id": run_id,
                "total_items": len(items),
                "passed_items": passed,
                "precision": avg_relevance,
                "recall": avg_relevance,
                "f1": avg_relevance,
                "latency_ms": avg_latency
            }
            
        except Exception as e:
            logger.error(f"Evaluation run failed: {e}")
            self._update_run_status(run_id, "failed", error=str(e))
            return {"status": "failed", "error": str(e)}
    
    def _create_run(self, eval_set_id: int, user_id: int, run_type: str) -> int:
        """创建运行记录"""
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            cur = conn.execute(
                """INSERT INTO memory_eval_runs
                   (eval_set_id, user_id, run_type, status, started_at)
                   VALUES (%s, %s, %s, 'pending', NOW())""",
                (eval_set_id, user_id, run_type)
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def _update_run_status(self, run_id: int, status: str, error: str = ""):
        """更新运行状态"""
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            if error:
                conn.execute(
                    "UPDATE memory_eval_runs SET status = %s, error_message = %s WHERE id = %s",
                    (status, error, run_id)
                )
            else:
                conn.execute(
                    "UPDATE memory_eval_runs SET status = %s WHERE id = %s",
                    (status, run_id)
                )
            conn.commit()
        finally:
            conn.close()

    def _update_run_completed(
        self,
        run_id: int,
        total_items: int,
        passed_items: int,
        precision_score: float,
        recall_score: float,
        f1_score: float,
        latency_ms: int
    ):
        """更新运行完成"""
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            conn.execute(
                """UPDATE memory_eval_runs
                   SET status = 'completed',
                       total_items = %s,
                       passed_items = %s,
                       precision_score = %s,
                       recall_score = %s,
                       f1_score = %s,
                       latency_ms = %s,
                       completed_at = NOW()
                   WHERE id = %s""",
                (total_items, passed_items, precision_score, recall_score, f1_score, latency_ms, run_id)
            )
            conn.commit()
        finally:
            conn.close()

    def _get_eval_items(self, eval_set_id: int) -> List[dict]:
        """获取评估项"""
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT * FROM memory_eval_items WHERE eval_set_id = %s",
                (eval_set_id,)
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def _save_result(self, run_id: int, item_id: int, result: dict):
        """保存评估结果"""
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            conn.execute(
                """INSERT INTO memory_eval_results
                   (run_id, item_id, retrieved_memory_ids, retrieved_contents,
                    llm_judgment, is_correct, relevance_score, latency_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (run_id, item_id, result["retrieved_memory_ids"],
                 result["retrieved_contents"], result["llm_judgment"],
                 result["is_correct"], result["relevance_score"], result["latency_ms"])
            )
            conn.commit()
        finally:
            conn.close()

    def get_run_results(self, run_id: int) -> Dict[str, Any]:
        """获取运行结果"""
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            # 获取运行记录
            cur = conn.execute(
                "SELECT * FROM memory_eval_runs WHERE id = %s",
                (run_id,)
            )
            run = cur.fetchone()
            if not run:
                return {}

            # 获取详细结果
            cur = conn.execute(
                "SELECT * FROM memory_eval_results WHERE run_id = %s",
                (run_id,)
            )
            results = [dict(row) for row in (cur.fetchall() if hasattr(cur, "fetchall") else [])]

            return {
                "run": dict(run),
                "results": results
            }
        finally:
            conn.close()
    
    def list_runs(
        self,
        eval_set_id: Optional[int] = None,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 20
    ) -> List[dict]:
        """列出评估运行"""
        from backend.db.schema import get_conn
        conn = get_conn()
        try:
            where_clauses = []
            params = []

            if eval_set_id:
                where_clauses.append("eval_set_id = %s")
                params.append(eval_set_id)

            if user_id:
                where_clauses.append("user_id = %s")
                params.append(user_id)

            if status:
                where_clauses.append("status = %s")
                params.append(status)

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            params.append(limit)

            cur = conn.execute(
                f"""SELECT * FROM memory_eval_runs
                    WHERE {where_sql}
                    ORDER BY created_at DESC
                    LIMIT %s""",
                params
            )

            return [dict(row) for row in (cur.fetchall() if hasattr(cur, "fetchall") else [])]
        finally:
            conn.close()


# 单例访问
_evaluator: Optional[MemoryEvaluator] = None


def get_memory_evaluator() -> MemoryEvaluator:
    """获取 MemoryEvaluator 单例"""
    global _evaluator
    if _evaluator is None:
        _evaluator = MemoryEvaluator()
    return _evaluator