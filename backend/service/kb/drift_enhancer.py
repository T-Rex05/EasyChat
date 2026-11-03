"""
DRIFT Search 增强器

微软 GraphRAG 的 DRIFT Search 结合了：
1. 社区上下文
2. 迭代扩展
3. Follow-up 问题生成

流程：
```
查询 → 社区报告检索 → Follow-up 生成 → 实体扩展 → 再次检索 → 迭代 → 最终答案
```
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.utils.log_utils import log

logger = log


# ════════════════════════════════════════════════════════════
# Follow-up 问题生成器
# ════════════════════════════════════════════════════════════

FOLLOWUP_PROMPT = """你是一个研究助手。根据以下信息，生成 1-3 个可以帮助深入探索的问题。

【已检索信息】
{context}

【原始问题】
{query}

【生成规则】
1. 关注未覆盖的关键点
2. 追问因果关系
3. 探索相关实体或事件
4. 问题应该具体、可检索

【输出格式】
以 JSON 格式返回：
{{
  "follow_ups": [
    "问题1？",
    "问题2？"
  ],
  "reasoning": "简要说明为什么这些问题有助于深入探索"
}}

只返回 JSON，不要其他文字。"""


@dataclass
class FollowUpResult:
    """Follow-up 生成结果"""
    questions: List[str] = field(default_factory=list)
    reasoning: str = ""


class FollowUpGenerator:
    """
    Follow-up 问题生成器

    根据已检索信息生成后续问题
    """

    def __init__(self, user_id: int = 0):
        self.user_id = user_id

    def generate(
        self,
        query: str,
        context: str,
        max_followups: int = 3
    ) -> FollowUpResult:
        """
        生成 Follow-up 问题

        Args:
            query: 原始查询
            context: 已检索的上下文
            max_followups: 最大问题数

        Returns:
            FollowUpResult
        """
        if not context or len(context) < 50:
            return FollowUpResult()

        try:
            from backend.utils.traced_llm import traced_llm

            prompt = FOLLOWUP_PROMPT.format(
                query=query,
                context=context[:2000]  # 限制长度
            )

            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="graph_drift_followup",
                user_id=self.user_id,
                source="graphrag",
                temperature=0.3,
                max_tokens=512,
            )

            content = resp.content or ""
            return self._parse_response(content, max_followups)

        except Exception as e:
            logger.warning(f"[FollowUp] Generation failed: {e}")
            return FollowUpResult()

    def _parse_response(self, content: str, max_followups: int) -> FollowUpResult:
        """解析 LLM 响应"""
        try:
            # 提取 JSON
            json_str = self._extract_json(content)
            if not json_str:
                return FollowUpResult()

            data = json.loads(json_str)
            questions = data.get("follow_ups", [])[:max_followups]
            reasoning = data.get("reasoning", "")

            # 过滤无效问题
            valid_questions = []
            for q in questions:
                q = q.strip()
                if q and len(q) > 5 and (q.endswith("?") or q.endswith("？")):
                    valid_questions.append(q)

            return FollowUpResult(
                questions=valid_questions,
                reasoning=reasoning
            )

        except Exception as e:
            logger.warning(f"[FollowUp] Parse failed: {e}")
            return FollowUpResult()

    def _extract_json(self, content: str) -> Optional[str]:
        """从内容中提取 JSON"""
        content = content.strip()

        # 尝试找 { }
        start = content.find("{")
        if start == -1:
            return None

        # 找到最后一个 }
        end = content.rfind("}")
        if end == -1:
            return None

        return content[start:end + 1]


# ════════════════════════════════════════════════════════════
# 迭代扩展器
# ════════════════════════════════════════════════════════════

@dataclass
class IterationResult:
    """迭代结果"""
    iteration: int
    query: str
    results: List[Dict[str, Any]] = field(default_factory=list)
    follow_ups: List[str] = field(default_factory=list)
    entities_found: List[str] = field(default_factory=list)


class IterativeExpander:
    """
    迭代扩展器

    支持 DRIFT Search 的多轮检索
    """

    def __init__(self, user_id: int = 0, max_iterations: int = 2):
        self.user_id = user_id
        self.max_iterations = max_iterations
        self.followup_gen = FollowUpGenerator(user_id)

    def expand(
        self,
        initial_query: str,
        initial_context: str,
        retriever: Any,  # AdaptiveRetriever
    ) -> List[IterationResult]:
        """
        迭代扩展检索

        Args:
            initial_query: 初始查询
            initial_context: 初始上下文
            retriever: 检索器

        Returns:
            每次迭代的结果列表
        """
        results: List[IterationResult] = []

        # 第一轮
        first = IterationResult(
            iteration=1,
            query=initial_query,
            results=[],  # 由调用方填充
        )
        results.append(first)

        # 生成 Follow-up
        followup_result = self.followup_gen.generate(
            query=initial_query,
            context=initial_context
        )
        first.follow_ups = followup_result.questions

        if not first.follow_ups:
            logger.info("[Iterative] No follow-ups generated, stop iteration")
            return results

        logger.info(f"[Iterative] Generated {len(first.follow_ups)} follow-ups")

        # 后续迭代
        for i in range(self.max_iterations - 1):
            iteration = i + 2

            # 用 Follow-up 检索
            iteration_results = []
            for fq in first.follow_ups[:1]:  # 只用第一个 Follow-up
                try:
                    result = retriever.retrieve(fq, top_k=5)
                    if result.get("results"):
                        iteration_results.extend(result["results"])

                        # 记录发现的实体
                        for entity in result.get("entities", []):
                            name = entity.get("name") or entity.get("entity_name")
                            if name:
                                first.entities_found.append(name)

                except Exception as e:
                    logger.warning(f"[Iterative] Follow-up retrieval failed: {e}")
                    continue

            # 创建迭代结果
            iter_result = IterationResult(
                iteration=iteration,
                query=first.follow_ups[0] if first.follow_ups else "",
                results=iteration_results[:10],
            )
            results.append(iter_result)

            # 如果没有新结果，停止迭代
            if not iteration_results:
                logger.info(f"[Iterative] No results in iteration {iteration}, stop")
                break

            # 生成下一轮 Follow-up（如果有）
            if iteration < self.max_iterations:
                new_context = "\n".join([
                    r.get("content", "")[:200]
                    for r in iteration_results[:3]
                ])
                next_followups = self.followup_gen.generate(
                    query=initial_query,
                    context=new_context
                )
                if next_followups.questions:
                    iter_result.follow_ups = next_followups.questions
                else:
                    break

        return results


# ════════════════════════════════════════════════════════════
# DRIFT Search 增强
# ════════════════════════════════════════════════════════════

def enhance_drift_search(
    query: str,
    community_reports: List[Dict[str, Any]],
    user_id: int = 0,
    retriever: Any = None,
    enable_iteration: bool = True,
) -> Dict[str, Any]:
    """
    增强 DRIFT Search

    Args:
        query: 用户查询
        community_reports: 相关社区报告
        user_id: 用户 ID
        retriever: AdaptiveRetriever 实例
        enable_iteration: 是否启用迭代扩展

    Returns:
        {
            "context": "社区上下文",
            "claims": [...],
            "iterations": [...],
            "answer": "最终答案"
        }
    """
    # 1. 构建社区上下文
    context_parts = []
    for report in community_reports[:5]:
        context_parts.append(
            f"【{report.get('title', '社区')}】\n"
            f"{report.get('summary', '')}\n"
            f"关键发现: {', '.join(report.get('findings', []))}"
        )

    context = "\n\n".join(context_parts)

    result = {
        "context": context,
        "claims": [],
        "iterations": [],
        "answer": "",
    }

    # 2. 检索相关 Claim
    try:
        from backend.graphrag.kg_store import get_kg_store
        kg_store = get_kg_store()

        claims = kg_store.search_claims(query, user_id=user_id, limit=10)
        result["claims"] = [
            {
                "id": c.id,
                "claim_text": c.claim_text,
                "subject": c.subject,
                "object": c.object,
                "confidence": c.confidence,
            }
            for c in claims
        ]

    except Exception as e:
        logger.warning(f"[DRIFT] Claim search failed: {e}")

    # 3. 迭代扩展（如果启用）
    if enable_iteration and retriever:
        try:
            expander = IterativeExpander(user_id=user_id, max_iterations=2)
            iterations = expander.expand(
                initial_query=query,
                initial_context=context,
                retriever=retriever
            )
            result["iterations"] = [
                {
                    "iteration": it.iteration,
                    "query": it.query,
                    "results_count": len(it.results),
                    "follow_ups": it.follow_ups,
                    "entities_found": list(set(it.entities_found)),
                }
                for it in iterations
            ]

            # 合并迭代结果到上下文
            for it in iterations:
                for r in it.results[:3]:
                    content = r.get("content", "")[:200]
                    if content and content not in context:
                        context += f"\n\n[补充信息]\n{content}"

            result["context"] = context

        except Exception as e:
            logger.warning(f"[DRIFT] Iterative expansion failed: {e}")

    # 4. 生成最终答案
    try:
        from backend.utils.traced_llm import traced_llm

        # 构建答案生成提示词
        claims_text = ""
        if result["claims"]:
            claims_text = "\n\n【相关事实】\n" + "\n".join([
                f"- {c['claim_text']}"
                for c in result["claims"][:5]
            ])

        prompt = f"""根据以下信息回答问题。

问题: {query}

【社区背景】
{context}
{claims_text}

请给出完整的答案，引用相关事实。"""

        resp = traced_llm.invoke(
            messages=[{"role": "user", "content": prompt}],
            scene="graph_drift_answer",
            user_id=user_id,
            source="graphrag",
            temperature=0.1,
            max_tokens=1024,
        )

        result["answer"] = resp.content or ""

    except Exception as e:
        logger.error(f"[DRIFT] Answer generation failed: {e}")
        result["answer"] = "答案生成失败"

    return result