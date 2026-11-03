"""
测评集自动生成（基于 RAGAS TestsetGenerator）

从已上传的知识文档中自动生成 question + ground_truth 对，
减少人工标注成本。

参考：守护之眼 RAG 测评文档「基于文档生成用于评测的数据集」

流程：
1. 从 kb_chunks 表读取指定文档的全部 chunk 内容
2. 拼接为完整文档文本（按 chunk_index 排序）
3. 调用 RAGAS TestsetGenerator 生成 QA 对
4. 导入到指定测评集

注意：
- 需要 embedding 服务（RAGAS 内部用 embedding 做文本关联）
- 生成过程较慢（取决于文档大小和 LLM 速度），异步执行
- 生成的 QA 对建议人工抽检后再用于正式评测
"""
import asyncio
from typing import Dict, List, Optional

from backend.db.schema import get_conn
from backend.utils.log_utils import log, rag

logger = log


class GeneratorError(Exception):
    """生成器业务异常"""


class GeneratorInvalid(GeneratorError):
    """参数不合法"""


def _json_dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(raw, default):
    import json
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _get_document_text(user_id: int, document_ids: List[int]) -> str:
    """从 kb_chunks 拼接指定文档的完整文本（按 chunk_index 排序）。"""
    conn = get_conn()
    try:
        placeholders = ",".join("?" for _ in document_ids)
        cur = conn.execute(
            f"SELECT c.content, c.chunk_index, d.original_name "
            f"FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id "
            f"WHERE c.document_id IN ({placeholders}) AND d.user_id = ? "
            f"ORDER BY c.document_id, c.chunk_index",
            document_ids + [user_id],
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    if not rows:
        raise GeneratorInvalid("指定文档无可用内容（或不属于当前用户）")
    return "\n\n".join(r["content"] for r in rows if r.get("content"))


async def generate_testset(
    user_id: int,
    document_ids: List[int],
    eval_set_id: int,
    testset_size: int = 10,
    llm_config: Optional[dict] = None,
) -> dict:
    """
    基于文档自动生成测评集题目。

    Args:
        user_id: 用户 ID
        document_ids: 文档 ID 列表（从中提取知识生成 QA 对）
        eval_set_id: 目标测评集 ID（生成的题目导入此集合）
        testset_size: 生成题目数量（默认 10）
        llm_config: LLM 配置（可选，默认使用用户当前模型）

    Returns:
        {"status": "started", "eval_set_id": ..., "testset_size": ...}
    """
    if not document_ids:
        raise GeneratorInvalid("请至少选择一个文档")
    testset_size = max(1, min(int(testset_size or 10), 50))

    # 校验测评集归属
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT id, user_id FROM kb_eval_sets WHERE id = ?", (eval_set_id,)
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    if not rows:
        raise GeneratorInvalid(f"测评集不存在: id={eval_set_id}")
    if rows[0]["user_id"] != user_id:
        raise GeneratorInvalid("测评集不属于当前用户")

    # 提取文档文本
    doc_text = await asyncio.to_thread(_get_document_text, user_id, document_ids)
    if len(doc_text) < 100:
        raise GeneratorInvalid("文档内容过少，无法生成有效测评集（至少需要 100 字符）")

    # 异步启动生成任务
    asyncio.get_running_loop().create_task(
        _execute_generation(user_id, document_ids, eval_set_id, doc_text, testset_size, llm_config)
    )
    return {"status": "started", "eval_set_id": eval_set_id, "testset_size": testset_size}


async def _execute_generation(
    user_id: int,
    document_ids: List[int],
    eval_set_id: int,
    doc_text: str,
    testset_size: int,
    llm_config: Optional[dict],
) -> None:
    """后台执行生成任务。"""
    try:
        # 获取 LLM 配置
        if llm_config is None:
            from backend.service.kb.kb_eval_service import _get_model_config
            llm_config = _get_model_config(user_id)
        if not llm_config or not llm_config.get("api_key"):
            logger.error("[KB-Gen] 未配置 LLM，无法生成测评集")
            return

        # 获取 embedding 配置
        from backend.service.kb.kb_eval_metrics import _ragas_embedding_config
        emb_config = _ragas_embedding_config()

        # 调用 RAGAS TestsetGenerator
        generated = await asyncio.to_thread(
            _run_ragas_generator, doc_text, testset_size, llm_config, emb_config
        )

        if not generated:
            logger.warning("[KB-Gen] RAGAS 未生成任何题目")
            return

        # 导入到测评集
        imported = await asyncio.to_thread(
            _import_to_eval_set, eval_set_id, generated
        )
        logger.info(f"[KB-Gen] 测评集自动生成完成: {imported}/{len(generated)} 条导入成功")

    except Exception as e:
        logger.error(f"[KB-Gen] 测评集生成失败: {e}")


def _run_ragas_generator(
    doc_text: str,
    testset_size: int,
    llm_config: dict,
    emb_config: Optional[dict],
) -> List[dict]:
    """调用 RAGAS TestsetGenerator 生成 QA 对。"""
    try:
        from langchain_core.documents import Document
        from openai import OpenAI, AsyncOpenAI
        from ragas.llms import llm_factory
        from ragas.testset import TestsetGenerator

        model = llm_config.get("model_name") or "gpt-4"
        if "[" in model:
            model = model.split("[")[0]

        # 构建 LLM
        client = OpenAI(api_key=llm_config["api_key"], base_url=llm_config["api_url"])
        llm = llm_factory(model, provider="openai", client=client, temperature=0.7)

        # 构建 embedding（可选）
        embeddings = None
        if emb_config:
            try:
                from ragas.embeddings import OpenAIEmbeddings
                emb_client = OpenAI(api_key=emb_config["api_key"], base_url=emb_config["base_url"])
                embeddings = OpenAIEmbeddings(emb_client, model=emb_config["model"])
            except Exception as e:
                logger.warning(f"[KB-Gen] embedding 构建失败，跳过: {e}")

        # 构造文档（单一大文档）
        docs = [Document(page_content=doc_text, metadata={"source": "knowledge_base"})]

        # 生成
        generator = TestsetGenerator(llm=llm, embedding_model=embeddings)
        dataset = generator.generate_with_langchain_docs(docs, testset_size=testset_size)
        df = dataset.to_pandas()

        results = []
        for _, row in df.iterrows():
            question = str(row.get("question") or row.get("user_input") or "").strip()
            answer = str(row.get("answer") or row.get("ground_truth") or "").strip()
            contexts = row.get("contexts") or row.get("retrieved_contexts") or []
            if isinstance(contexts, str):
                contexts = [contexts]
            if question and answer:
                results.append({
                    "question": question,
                    "ground_truth_answer": answer,
                    "ground_truth_contexts": list(contexts),
                })
        return results

    except ImportError:
        logger.error("[KB-Gen] ragas 未安装，无法自动生成测评集")
        return []
    except Exception as e:
        logger.error(f"[KB-Gen] RAGAS 生成失败: {e}")
        return []


def _import_to_eval_set(eval_set_id: int, items: List[dict]) -> int:
    """将生成的 QA 对导入测评集。"""
    conn = get_conn()
    try:
        # 获取当前最大 sort_order
        cur = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) AS max_order FROM kb_eval_items WHERE eval_set_id = ?",
            (eval_set_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        next_order = (rows[0]["max_order"] if rows else -1) + 1

        imported = 0
        for item in items:
            cur = conn.execute(
                "INSERT INTO kb_eval_items (eval_set_id, question, ground_truth_chunk_ids, ground_truth_answer, sort_order) "
                "VALUES (?, ?, '[]', ?, ?)",
                (eval_set_id, item["question"], item["ground_truth_answer"], next_order),
            )
            next_order += 1
            imported += 1
        conn.commit()
        return imported
    finally:
        conn.close()
