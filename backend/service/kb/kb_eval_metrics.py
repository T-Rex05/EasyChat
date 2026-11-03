"""
RAG 分层评测指标

检索层（自研，确定性，零 LLM 成本）：
    recall_at_k / mrr / ndcg_at_k / precision_at_k

生成层（RAGAS，LLM 裁判）：
    faithfulness / answer_relevancy / context_recall / answer_correctness

RAGAS 未安装或裁判失败时优雅降级（返回 {} + warnings，不中断整轮）。
"""
import math
from typing import Dict, List, Optional

from backend.utils.log_utils import log, rag

logger = log


# ════════════════════════════════════════════════════════════
# 检索层指标（确定性）
# ════════════════════════════════════════════════════════════

def compute_retrieval_metrics(
    gt_ids: List[int],
    retrieved_ids: List[int],
    k: int,
) -> Dict[str, float]:
    """
    计算单条问题的检索层指标。

    Args:
        gt_ids: 人工标注的 ground-truth chunk id 列表
        retrieved_ids: 检索返回的 chunk id 列表（已按排名排序）
        k: top-K

    Returns:
        {"recall_at_k": 0/1, "mrr": float, "ndcg_at_k": float, "precision_at_k": float}
    """
    gt_set = {int(i) for i in gt_ids}
    top_k = retrieved_ids[:k]

    if not gt_set:
        return {"recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0, "precision_at_k": 0.0}

    # Recall@K / Hit Rate：任一 GT 出现在 top-K
    hit = any(rid in gt_set for rid in top_k)
    recall_at_k = 1.0 if hit else 0.0

    # MRR：首个 GT 的排名倒数
    mrr = 0.0
    for rank, rid in enumerate(top_k, start=1):
        if rid in gt_set:
            mrr = 1.0 / rank
            break

    # NDCG@K：二元相关性
    dcg = 0.0
    for rank, rid in enumerate(top_k, start=1):
        if rid in gt_set:
            dcg += 1.0 / math.log2(rank + 1)
    ideal_hits = min(len(gt_set), len(top_k))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    ndcg = dcg / idcg if idcg > 0 else 0.0

    # Precision@K
    precision = len([rid for rid in top_k if rid in gt_set]) / len(top_k) if top_k else 0.0

    return {
        "recall_at_k": recall_at_k,
        "mrr": round(mrr, 4),
        "ndcg_at_k": round(ndcg, 4),
        "precision_at_k": round(precision, 4),
    }


def aggregate_metrics(metric_list: List[dict]) -> Dict[str, float]:
    """逐条指标 → 均值聚合（缺失键跳过）。"""
    keys = set()
    for m in metric_list:
        keys.update(m.keys())
    agg: Dict[str, float] = {}
    for key in keys:
        values = [m[key] for m in metric_list if key in m and isinstance(m[key], (int, float))]
        if values:
            agg[key] = round(sum(values) / len(values), 4)
    return agg


# ════════════════════════════════════════════════════════════
# 结果七态分类（确定性，零 LLM 成本 —— 借鉴 Eyes 评测六态，新增 refused）
# ════════════════════════════════════════════════════════════

# 分类阈值（可调常量，全局统一）
CLASSIFICATION = {
    "complete": "完整命中",
    "partial": "部分达标",
    "retrieval_miss": "检索未命中",
    "insufficient_context": "依据不足",
    "wrong_answer": "答案错误",
    "refused": "已拒答",
    "unjudgeable": "无法判定",
}
_RETRIEVAL_OK_RECALL = 0.5       # recall_at_k > 0 即视为命中（GT 有任意一条进 top-K）
_JUDGE_PASS = 0.6                 # judge 指标达标线
_WRONG_ANSWER_CORRECTNESS = 0.3   # answer_correctness 低于此值判「答案错误」（LLM 补充合理细节时 RAGAS 语义相似度会降低，需留余量）
_COMPLETE_FAITH_THRESHOLD = 0.9   # faithfulness ≥ 此值直接判 complete（答案高度可信）
_WRONG_ANSWER_FAITH_THRESHOLD = 0.7  # faithfulness ≥ 此值时 ac 信号可信，可判 wrong_answer

# 默认阈值字典（供前端展示 / API 返回）
DEFAULT_THRESHOLDS = {
    "judge_pass": _JUDGE_PASS,
    "wrong_answer_correctness": _WRONG_ANSWER_CORRECTNESS,
    "complete_faith_threshold": _COMPLETE_FAITH_THRESHOLD,
    "wrong_answer_faith_threshold": _WRONG_ANSWER_FAITH_THRESHOLD,
}


def classify_result(metrics: Dict, judge_metrics: Dict, thresholds: Optional[Dict] = None) -> str:
    """
    根据检索层 + 生成层指标做确定性七态分类。

    Args:
        metrics: 检索层指标 {"recall_at_k": 0/1, "mrr": float, ...}
        judge_metrics: 生成层指标 {"faithfulness": float|None, "answer_correctness": float|None, ...}
        thresholds: 可选阈值覆盖 {"judge_pass", "wrong_answer_correctness",
                      "complete_faith_threshold", "wrong_answer_faith_threshold"}

    Returns:
        classification 键（见 CLASSIFICATION 常量）:
          - complete:              检索命中 GT 且 judge 全部达标
          - partial:               检索命中 GT 但 judge 部分不达标
          - retrieval_miss:        检索未命中任何 GT
          - insufficient_context:  检索命中但 faithfulness 低于达标线
          - wrong_answer:          answer_correctness 低于阈值
          - refused:               系统主动拒答（refused=True 标记）
          - unjudgeable:           无任何 judge 分数（未启用裁判/无模型）
    """
    # 解析阈值（支持外部传入覆盖，否则用默认值）
    t = thresholds or {}
    _judge_pass = float(t.get("judge_pass", _JUDGE_PASS))
    _wrong_ac = float(t.get("wrong_answer_correctness", _WRONG_ANSWER_CORRECTNESS))
    _complete_faith = float(t.get("complete_faith_threshold", _COMPLETE_FAITH_THRESHOLD))
    _wrong_faith = float(t.get("wrong_answer_faith_threshold", _WRONG_ANSWER_FAITH_THRESHOLD))

    has_error = bool(metrics.get("error"))
    if has_error:
        return "unjudgeable"

    # ★ 拒答优先判断
    if metrics.get("refused"):
        return "refused"

    recall = float(metrics.get("recall_at_k") or 0.0)
    hit = recall > 0.0

    # 提取有效的 judge 分数（忽略 None）
    judge_values = {}
    for key in ("faithfulness", "answer_relevancy", "context_recall", "answer_correctness"):
        v = (judge_metrics or {}).get(key)
        if isinstance(v, (int, float)):
            judge_values[key] = float(v)

    if not judge_values:
        # 无裁判分数：只能按检索层分类
        return "complete" if hit else "retrieval_miss"

    if not hit:
        return "retrieval_miss"

    faith = judge_values.get("faithfulness")
    correct = judge_values.get("answer_correctness")

    # ★ 分类优先级（阈值均可由用户在界面上调整）：
    # 1. insufficient_context（faith < judge_pass）：答案缺乏依据，无法判断对错
    #    —— faith 低 = 答案没在检索到的 context 里找到支撑，是"答不出来"而非"答错了"
    # 2. wrong_answer（faith ≥ wrong_answer_faith_threshold 且 ac < wrong_answer_correctness）
    #    —— 只有 faithfulness 高时才能信任 answer_correctness 的判定
    # 3. complete（faith ≥ complete_faith_threshold）：答案高度可信
    #    —— RAGAS answer_correctness 基于 embedding 相似度，LLM 补充合理细节时分数被稀释
    # 4. partial：其余 judge 指标部分不达标
    # 5. complete：全部达标

    # 1. 依据不足（优先级最高——faith 低时 ac 不可信）
    if faith is not None and faith < _judge_pass:
        return "insufficient_context"
    # 2. 答案错误（仅当 faith ≥ _wrong_faith，ac 可信时才判）
    faithfulness_high = faith is not None and faith >= _wrong_faith
    if correct is not None and correct < _wrong_ac and faithfulness_high:
        return "wrong_answer"
    # 3. 高 faithfulness 时答案完全可信，ac 低不扣分
    if faith is not None and faith >= _complete_faith:
        return "complete"
    # 4. 其余 judge 指标部分不达标 → 部分达标
    if any(v < _judge_pass for v in judge_values.values()):
        return "partial"
    return "complete"


def aggregate_classifications(classifications: List[str]) -> Dict[str, int]:
    """七态计数聚合（run 汇总用）。"""
    counts = {k: 0 for k in CLASSIFICATION}
    for c in classifications:
        if c in counts:
            counts[c] += 1
    return counts


# ════════════════════════════════════════════════════════════
# 生成层指标（RAGAS 0.4.3）
# ════════════════════════════════════════════════════════════

def _ragas_available() -> bool:
    try:
        import ragas  # noqa: F401
        return True
    except ImportError:
        return False


def _score_to_float(value) -> Optional[float]:
    """RAGAS 分数归一化为 float（兼容 int/float/None/nan）。"""
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f):
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


async def compute_ragas_metrics_async(
    samples: List[dict],
    llm_config: Optional[dict] = None,
    n_runs: int = 1,
) -> tuple:
    """
    批量计算生成层 RAGAS 指标（ragas 0.4.3）。

    Args:
        samples: [{question, answer, contexts, gt_contexts, gt_answer}]
            - contexts: 检索到的 chunk 文本列表（retrieved_contexts）
            - gt_contexts: 人工标注 GT chunk 文本列表（reference_contexts）
            - gt_answer: 参考答案（可选，用于 answer_correctness / context_recall）
        llm_config: {"api_url", "api_key", "model_name"}（OpenAI 兼容，如 DeepSeek）
        n_runs: 多次评估取平均（降低 LLM 裁判随机性，默认 1，建议 2~3）

    Returns:
        (results: List[dict], warnings: List[str])
        results 与 samples 一一对应：{"faithfulness": float|None, "answer_relevancy": ...,
                                      "context_recall": ..., "answer_correctness": ...}
    """
    warnings: List[str] = []
    empty = [{
        "faithfulness": None,
        "answer_relevancy": None,
        "context_recall": None,
        "answer_correctness": None,
    } for _ in samples]

    if not _ragas_available():
        warnings.append("ragas 未安装，生成层指标已跳过（检索层指标不受影响）")
        return empty, warnings

    if not samples or not llm_config or not llm_config.get("api_key"):
        warnings.append("未配置可用 LLM，生成层裁判已跳过")
        return empty, warnings

    n_runs = max(1, min(int(n_runs or 1), 5))  # 限制 1~5 次

    # ★ 并发控制：限制同时进行的 LLM 请求数，避免 429 限流
    # RAGAS 每个指标内部可能多次调用 LLM，所以信号量设小一点
    MAX_CONCURRENT_REQUESTS = 2

    try:
        import asyncio as _asyncio
        from openai import AsyncOpenAI
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerCorrectness,
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )

        # 并发控制信号量
        _semaphore = _asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        # 模型名后缀剥离（[128k] 等标签 API 不识别）
        model = llm_config.get("model_name") or "gpt-4"
        if "[" in model:
            model = model.split("[")[0]

        # ragas ascore 走 agenerate → 需要 AsyncOpenAI 客户端
        # ★ 稳定性优化：temperature=0 + seed=42 消除裁判 LLM 随机性
        # ★ max_tokens=8192：裁判需要输出 JSON 结论，默认值过小会截断导致评测失败
        judge = llm_factory(
            model,
            provider="openai",
            client=AsyncOpenAI(
                api_key=llm_config["api_key"],
                base_url=llm_config["api_url"],
            ),
            temperature=0,
            seed=42,
            max_tokens=8192,
        )

        faith = Faithfulness(llm=judge)
        ctx_recall = ContextRecall(llm=judge)  # Context Recall

        # AnswerRelevancy / AnswerCorrectness 构造需要 embedding 服务（显式配置才启用相似度权重）
        relevancy = None
        correctness = None
        emb_config = _ragas_embedding_config()
        if emb_config is not None:
            try:
                from ragas.embeddings import BaseRagasEmbedding

                # 自定义兼容 embedding：某些 API 要求 input 为数组而非字符串
                class _CompatibleEmbedding(BaseRagasEmbedding):
                    def __init__(self, client, model: str):
                        self.client = client
                        self.model = model

                    async def aembed_text(self, text: str, **kwargs) -> list:
                        # 某些 API（火山方舟、阿里云）要求 input 为数组
                        response = await self.client.embeddings.create(
                            input=[text], model=self.model, **kwargs
                        )
                        return response.data[0].embedding

                    def embed_text(self, text: str, **kwargs) -> list:
                        response = self.client.embeddings.create(
                            input=[text], model=self.model, **kwargs
                        )
                        return response.data[0].embedding

                    async def aembed_texts(self, texts: list, **kwargs) -> list:
                        response = await self.client.embeddings.create(
                            input=texts, model=self.model, **kwargs
                        )
                        return [item.embedding for item in response.data]

                    def embed_texts(self, texts: list, **kwargs) -> list:
                        response = self.client.embeddings.create(
                            input=texts, model=self.model, **kwargs
                        )
                        return [item.embedding for item in response.data]

                embeddings = _CompatibleEmbedding(
                    AsyncOpenAI(api_key=emb_config["api_key"], base_url=emb_config["base_url"]),
                    model=emb_config["model"],
                )
                relevancy = AnswerRelevancy(llm=judge, embeddings=embeddings)
                correctness = AnswerCorrectness(llm=judge, embeddings=embeddings)
            except Exception as e:  # noqa: BLE001
                warnings.append(f"AnswerRelevancy/Correctness 语义相似度跳过（embedding 构建失败）: {e}")
        else:
            warnings.append("AnswerRelevancy 跳过（未配置 RAG_EMBEDDING_BASE_URL，无 embedding 服务）")
            # AnswerCorrectness 无 embedding → 纯事实性权重（不评语义相似度）
            correctness = AnswerCorrectness(llm=judge, weights=[1.0, 0.0])

        async def _score_one(s: dict) -> dict:
            """单条样本逐指标裁判（0.4.3 collections API：metric.ascore）。
            
            ★ 使用信号量控制并发，避免 API 429 限流
            """
            async with _semaphore:
                logger.info(f"[KB-Eval] 开始评测样本: {s['question'][:50]}...")
                item = {
                    "faithfulness": None,
                    "answer_relevancy": None,
                    "context_recall": None,
                    "answer_correctness": None,
                }
                try:
                    r = await faith.ascore(
                        user_input=s["question"], response=s["answer"],
                        retrieved_contexts=s.get("contexts") or [],
                    )
                    item["faithfulness"] = _score_to_float(r.value)
                    logger.info(f"[KB-Eval] Faithfulness={item['faithfulness']}")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[KB-Eval] Faithfulness 失败: {e}")

                # 指标间添加短暂延迟，避免触发限流
                await _asyncio.sleep(0.5)

                if relevancy is not None:
                    try:
                        r = await relevancy.ascore(user_input=s["question"], response=s["answer"])
                        item["answer_relevancy"] = _score_to_float(r.value)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"[KB-Eval] AnswerRelevancy 失败: {e}")
                    await _asyncio.sleep(0.5)

                # ★ Context Precision 已删除（与检索层 Precision@K 功能重叠，且开销大）

                # Context Recall：衡量 GT 答案中的声明能被检索上下文支持的比例
                gt_answer = s.get("gt_answer")
                logger.debug(f"[KB-Eval] GT答案: {bool(gt_answer)}, len={len(gt_answer) if gt_answer else 0}")
                if gt_answer:
                    try:
                        r = await ctx_recall.ascore(
                            user_input=s["question"],
                            retrieved_contexts=s.get("contexts") or [],
                            reference=gt_answer,
                        )
                        item["context_recall"] = _score_to_float(r.value)
                        logger.info(f"[KB-Eval] ContextRecall={item['context_recall']}")
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"[KB-Eval] ContextRecall 失败: {e}")
                    await _asyncio.sleep(0.5)

                if gt_answer and correctness is not None:
                    try:
                        r = await correctness.ascore(
                            user_input=s["question"], response=s["answer"],
                            reference=gt_answer,
                        )
                        item["answer_correctness"] = _score_to_float(r.value)
                        logger.info(f"[KB-Eval] AnswerCorrectness={item['answer_correctness']}")
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"[KB-Eval] AnswerCorrectness 失败: {e}")
            return item

        async def _score_all():
            """单轮全部样本打分。"""
            return await _asyncio.gather(*[_score_one(s) for s in samples])

        # ★ 多次评估取平均（降低 LLM 裁判随机性）
        if n_runs <= 1:
            results = await _score_all()
        else:
            warnings.append(f"多次评估模式: n_runs={n_runs}，各指标取均值以降低方差")
            all_runs = []
            for run_idx in range(n_runs):
                logger.info(f"[KB-Eval] RAGAS 裁判第 {run_idx + 1}/{n_runs} 轮")
                run_results = await _score_all()
                all_runs.append(run_results)
            # 逐样本逐指标取均值
            results = []
            for sample_idx in range(len(samples)):
                avg_item = {}
                for key in ("faithfulness", "answer_relevancy", "context_recall", "answer_correctness"):
                    values = [r[sample_idx][key] for r in all_runs if r[sample_idx].get(key) is not None]
                    avg_item[key] = round(sum(values) / len(values), 4) if values else None
                results.append(avg_item)

    except Exception as e:  # noqa: BLE001 — RAGAS 整体失败则降级
        logger.error(f"[KB-Eval] RAGAS 裁判失败: {e}")
        warnings.append(f"RAGAS 裁判执行失败（已跳过生成层指标）: {e}")
        return empty, warnings

    return results, warnings


def compute_ragas_metrics(
    samples: List[dict],
    llm_config: Optional[dict] = None,
    n_runs: int = 1,
) -> tuple:
    """
    同步包装器：在非异步环境中调用异步版本。
    自动检测是否已在事件循环中。
    """
    import asyncio

    try:
        # 尝试获取当前事件循环
        loop = asyncio.get_running_loop()
        # 如果已经在事件循环中，使用 nest_asyncio 或抛出错误
        # 这里我们创建一个新线程来运行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                compute_ragas_metrics_async(samples, llm_config, n_runs)
            )
            return future.result()
    except RuntimeError:
        # 没有运行中的事件循环，直接使用 asyncio.run
        return asyncio.run(compute_ragas_metrics_async(samples, llm_config, n_runs))


def _ragas_embedding_config() -> Optional[dict]:
    """RAGAS AnswerRelevancy 用 embedding 配置（DB 优先，env 兜底）。

    - provider 非 openai（如 ollama）→ 不支持（AnswerRelevancy 需 OpenAI 兼容 embedding）→ None
    - 无任何配置 → None
    """
    import os

    # ── 1. DB（前端「系统配置」embedding 分类）──
    try:
        from backend.db.connection_pool import get_pool_connection
        from backend.utils.crypto_utils import decrypt
        conn = get_pool_connection()
        try:
            cur = conn.cursor()
            # 查找非多模态的 embedding 模型（RAGAS 需要标准 /embeddings 端点）
            cur.execute(
                "SELECT config_type, api_url, api_key, model_name, is_multimodal "
                "FROM model_configs WHERE category = 'embedding' AND enabled = 1 "
                "AND (is_multimodal = 0 OR is_multimodal IS NULL) "
                "AND model_name NOT LIKE '%vision%' AND model_name NOT LIKE '%multimodal%' "
                "ORDER BY is_current DESC, id DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                api_key = row.get("api_key") or ""
                try:
                    api_key = decrypt(api_key)
                except Exception:
                    pass
                api_key = api_key.strip()
                _ct = (row.get("config_type") or "").upper()
                if _ct != "OLLAMA":  # RAGAS 只支持 OpenAI 兼容接口
                    return {
                        "base_url": (row.get("api_url") or "").strip(),
                        "api_key": api_key or os.getenv("LLM_API_KEY", ""),
                        "model": row.get("model_name") or "text-embedding-3-small",
                    }
        finally:
            conn.close()
    except Exception:
        pass

    # ── 2. 环境变量兜底 ──
    provider = os.getenv("RAG_EMBEDDING_PROVIDER", "openai").lower()
    if provider != "openai":
        return None
    base_url = os.getenv("RAG_EMBEDDING_BASE_URL", "").strip()
    if not base_url:
        return None
    api_key = os.getenv("RAG_EMBEDDING_API_KEY", "").strip() or os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    return {"base_url": base_url, "api_key": api_key, "model": model}
