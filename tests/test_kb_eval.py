"""
RAG 分层评测单元测试

- 检索层指标（Recall@K / MRR / NDCG / Precision）确定性计算
- 分词器（中英混合）
- BM25 检索器（需 MySQL）
- 测评集 CRUD + 用户隔离（需 MySQL）
- run 执行状态机（mock 检索器 + mock 裁判，需 MySQL）
- 向量化/清理（FakeEmbeddings + 临时 Chroma，需 MySQL）
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


def _mysql_available() -> bool:
    try:
        from backend.db.connection_pool import get_pool_connection
        conn = get_pool_connection()
        conn.close()
        return True
    except Exception:
        return False


requires_mysql = pytest.mark.skipif(
    not _mysql_available(), reason="MySQL 不可用，跳过 DB 集成测试"
)


# ════════════════════════════════════════════════════════════
# 检索层指标
# ════════════════════════════════════════════════════════════

class TestRetrievalMetrics:
    def test_hit_at_rank1(self):
        from backend.service.kb.kb_eval_metrics import compute_retrieval_metrics
        m = compute_retrieval_metrics([3], [3, 7, 9, 1, 2], k=5)
        assert m["recall_at_k"] == 1.0
        assert m["mrr"] == 1.0
        assert m["precision_at_k"] == 0.2
        assert 0.99 <= m["ndcg_at_k"] <= 1.0

    def test_miss(self):
        from backend.service.kb.kb_eval_metrics import compute_retrieval_metrics
        m = compute_retrieval_metrics([100], [1, 2, 3], k=3)
        assert m["recall_at_k"] == 0.0
        assert m["mrr"] == 0.0
        assert m["ndcg_at_k"] == 0.0
        assert m["precision_at_k"] == 0.0

    def test_hit_at_rank3(self):
        from backend.service.kb.kb_eval_metrics import compute_retrieval_metrics
        m = compute_retrieval_metrics([9], [1, 2, 9, 4, 5], k=5)
        assert m["recall_at_k"] == 1.0
        assert m["mrr"] == pytest.approx(1 / 3, abs=1e-4)
        assert m["precision_at_k"] == 0.2

    def test_multiple_gt(self):
        from backend.service.kb.kb_eval_metrics import compute_retrieval_metrics
        m = compute_retrieval_metrics([2, 4], [2, 4, 7, 8, 9], k=5)
        assert m["recall_at_k"] == 1.0
        assert m["mrr"] == 1.0
        assert m["precision_at_k"] == 0.4
        # DCG = 1/log2(2) + 1/log2(3)；IDCG 同（2 个 GT 命中前两位）→ NDCG=1
        assert m["ndcg_at_k"] == pytest.approx(1.0, abs=1e-6)

    def test_empty_gt(self):
        from backend.service.kb.kb_eval_metrics import compute_retrieval_metrics
        m = compute_retrieval_metrics([], [1, 2, 3], k=3)
        assert m == {"recall_at_k": 0.0, "mrr": 0.0, "ndcg_at_k": 0.0, "precision_at_k": 0.0}

    def test_aggregate(self):
        from backend.service.kb.kb_eval_metrics import aggregate_metrics
        agg = aggregate_metrics([
            {"recall_at_k": 1.0, "mrr": 0.5},
            {"recall_at_k": 0.0, "mrr": 1.0},
            {"recall_at_k": 1.0, "mrr": 0.0, "extra": 2},
        ])
        assert agg["recall_at_k"] == pytest.approx(2 / 3, abs=1e-4)
        assert agg["mrr"] == pytest.approx(0.5, abs=1e-4)
        assert agg["extra"] == 2


class TestTokenizer:
    def test_chinese_jieba(self):
        from backend.service.kb.kb_retriever import _tokenize
        tokens = _tokenize("Redis 为什么会缓存雪崩")
        assert "缓存" in tokens and "雪崩" in tokens

    def test_english_words(self):
        from backend.service.kb.kb_retriever import _tokenize
        tokens = _tokenize("JWT is stateless by design")
        assert "jwt" in tokens and "stateless" in tokens

    def test_empty(self):
        from backend.service.kb.kb_retriever import _tokenize
        assert _tokenize("") == []


# ════════════════════════════════════════════════════════════
# BM25 检索器（需 MySQL）
# ════════════════════════════════════════════════════════════

@requires_mysql
class TestBM25Retriever:
    @pytest.fixture(autouse=True)
    def _init(self, tmp_path):
        from backend.db.schema import init_db
        init_db()
        self.tmp = tmp_path

    def _make_doc(self, user_id: int, filename: str, text: str):
        from backend.service.kb import kb_service
        return asyncio.run(kb_service.create_document(
            user_id=user_id, filename=filename, content=text.encode("utf-8"),
            chunk_size=500, chunk_overlap=0,
        ))

    def test_retrieve_hits(self):
        from backend.service.kb.kb_service import delete_document
        from backend.service.kb.kb_retriever import BM25Retriever

        self._make_doc(900, "a.txt", "缓存雪崩是指大量缓存同时失效导致数据库压力激增的现象。")
        self._make_doc(900, "b.txt", "JWT 是无状态的令牌，服务端不保存会话信息。")
        try:
            retriever = BM25Retriever(900)
            results = retriever.retrieve("什么是缓存雪崩", top_k=3)
            assert results, "BM25 应检索到结果"
            assert "缓存雪崩" in results[0]["content"]
            assert results[0]["chunk_id"]
        finally:
            from backend.service.kb import kb_service
            listing = kb_service.list_documents(900, set(), page_size=100)
            for d in listing["items"]:
                delete_document(900, d["id"], set())

    def test_user_isolation(self):
        """
        知识库内容的隔离边界是**数据层级（部门）**，不是"上传者"。

        历史版本断言"其他用户检索结果为空"（按 d.user_id 过滤），这在共享知识库设计下
        不成立 —— 它当时能通过，只是因为 BM25 索引构建是坏的（恒返回空）。
        本用例验证真正的边界：**受限层级的 chunk 不出现在其他层级用户的召回里**
        （其他可共享文档的 chunk 正常出现，因此不做"全空"的过强断言）。
        """
        from backend.db.schema import get_conn
        from backend.service.kb.kb_retriever import BM25Retriever

        doc = self._make_doc(901, "only_a.txt", "只有受限层级的独特内容 量子计算退火算法")
        conn = get_conn()
        try:
            cur = conn.execute("SELECT id FROM kb_chunks WHERE document_id = %s", (doc["id"],))
            own_chunk_ids = {int(r["id"]) for r in (cur.fetchall() if hasattr(cur, "fetchall") else [])}
            assert own_chunk_ids, "测试文档应有 chunk"

            # 1) 未挂层级（NULL → 继承 KB 默认全员）：其他用户能检索到
            hits = BM25Retriever(902).retrieve("量子计算退火算法", top_k=5)
            assert own_chunk_ids & {h["chunk_id"] for h in hits}, "未挂层级时该文档应可见"

            # 2) 挂到受限层级 999 → 其他层级用户（{0}）不应再召回它
            conn.execute(
                "UPDATE kb_chunks SET scope_layer_id = 999 WHERE document_id = %s", (doc["id"],)
            )
            conn.commit()
            hits2 = BM25Retriever(902).retrieve("量子计算退火算法", top_k=5)
            assert not (own_chunk_ids & {h["chunk_id"] for h in hits2}), \
                "受限层级的 chunk 不应被其他层级用户检索到"
        finally:
            conn.close()
            from backend.service.kb import kb_service
            listing = kb_service.list_documents(901, set(), page_size=100)
            for d in listing["items"]:
                kb_service.delete_document(901, d["id"], set())


# ════════════════════════════════════════════════════════════
# 测评集 CRUD + 运行（需 MySQL）
# ════════════════════════════════════════════════════════════

@requires_mysql
class TestEvalService:
    @pytest.fixture(autouse=True)
    def _init(self, tmp_path):
        from backend.db.schema import init_db
        init_db()
        self.tmp = tmp_path

    def _make_doc_and_chunks(self, user_id: int):
        from backend.service.kb import kb_service
        doc = asyncio.run(kb_service.create_document(
            user_id=user_id, filename="eval_doc.txt",
            content="缓存雪崩章节内容。".encode("utf-8"),
            chunk_size=200, chunk_overlap=0,
        ))
        chunks = kb_service.list_chunks(user_id, doc["id"], set(), page_size=100)
        return doc, chunks["items"]

    def test_crud_and_ownership(self):
        from backend.service.kb import kb_eval_service as svc

        set_id = svc.create_eval_set(1, "测试集")["id"]
        # 他人不可见（无 kb.manage）
        with pytest.raises(svc.EvalNotFound):
            svc.get_eval_set(2, set_id, set())
        # 管理员可见
        detail = svc.get_eval_set(1, set_id, set())
        assert detail["name"] == "测试集"
        svc.update_eval_set(1, set_id, set(), name="改名后")
        assert svc.get_eval_set(1, set_id, set())["name"] == "改名后"
        svc.delete_eval_set(1, set_id, set())
        with pytest.raises(svc.EvalNotFound):
            svc.get_eval_set(1, set_id, set())

    def test_item_gt_validation(self):
        from backend.service.kb import kb_eval_service as svc

        doc, chunks = self._make_doc_and_chunks(910)
        set_id = svc.create_eval_set(910, "gt 测试")["id"]
        try:
            # 不存在的 chunk → 400 语义
            with pytest.raises(svc.EvalInvalid):
                svc.add_item(910, set_id, set(), "问题?", [999999])
            # 他人的测评集对非管理员不可见 → 404 语义
            with pytest.raises(svc.EvalNotFound):
                svc.add_item(911, set_id, set(), "问题?", [chunks[0]["id"]])
            # 正常添加
            item = svc.add_item(910, set_id, set(), "什么是缓存雪崩？", [chunks[0]["id"]])
            detail = svc.get_eval_set(910, set_id, set())
            assert len(detail["items"]) == 1
            assert detail["items"][0]["ground_truth_chunk_ids"] == [chunks[0]["id"]]
            svc.delete_item(910, set_id, item["id"], set())
            assert svc.get_eval_set(910, set_id, set())["items"] == []
        finally:
            svc.delete_eval_set(910, set_id, set())
            from backend.service.kb import kb_service
            kb_service.delete_document(910, doc["id"], set())

    def test_run_execution(self, monkeypatch):
        from backend.service.kb import kb_eval_service as svc
        from unittest.mock import MagicMock

        doc, chunks = self._make_doc_and_chunks(920)
        gt_id = chunks[0]["id"]
        set_id = svc.create_eval_set(920, "run 测试")["id"]
        svc.add_item(920, set_id, set(), "缓存雪崩是什么？", [gt_id])
        svc.add_item(920, set_id, set(), "另一个问题？", [gt_id])

        # ── mock 检索器：GT 排第一 + 干扰项 ──
        class FakeRetriever:
            name = "fake"

            def retrieve(self, query, top_k=5):
                return [
                    {"chunk_id": gt_id, "content": chunks[0]["content"], "score": 0.99, "is_gt": False},
                    {"chunk_id": 999901, "content": "干扰内容A", "score": 0.5, "is_gt": False},
                    {"chunk_id": 999902, "content": "干扰内容B", "score": 0.4, "is_gt": False},
                ]

        monkeypatch.setattr("backend.service.kb.kb_retriever.get_retriever",
                           lambda uid, mode="auto", kind="all", kb_id=None: (FakeRetriever(), []))
        monkeypatch.setattr(svc, "_get_model_config",
                           lambda uid: {"api_url": "http://x", "api_key": "k", "model_name": "test-model"})
        monkeypatch.setattr(svc, "_generate_answer",
                           lambda cfg, q, ctxs: f"答案: {q[:10]}")
        monkeypatch.setattr(
            svc, "compute_ragas_metrics",
            lambda samples, cfg, n_runs=1: (
                [{"faithfulness": 0.9, "answer_relevancy": 0.8,
                  "context_precision": 1.0, "answer_correctness": None} for _ in samples],
                [],
            ),
        )

        async def _run_and_wait():
            res = await svc.run_eval_set(920, set_id, set(), top_k=5, generate_answer=True, judge_enabled=True)
            run_id = res["run_id"]
            for _ in range(200):
                await asyncio.sleep(0.05)
                run = svc.get_run(920, run_id, set())
                if run["status"] != "running":
                    return run
            raise AssertionError("run 未在超时内完成")

        try:
            run = asyncio.run(_run_and_wait())
            assert run["status"] == "done"
            assert run["metrics"]["recall_at_k"] == 1.0
            assert run["metrics"]["mrr"] == 1.0
            assert run["metrics"]["faithfulness"] == pytest.approx(0.9, abs=1e-4)
            assert run["progress"]["done"] == 2
            detail = svc.get_run(920, run["id"], set())
            assert len(detail["results"]) == 2
            r0 = detail["results"][0]
            assert r0["answer"].startswith("答案:")
            assert any(c["is_gt"] for c in r0["retrieved_chunks"])
            # 他人不可见
            with pytest.raises(svc.EvalNotFound):
                svc.get_run(921, run["id"], set())
        finally:
            svc.delete_eval_set(920, set_id, set())
            from backend.service.kb import kb_service
            kb_service.delete_document(920, doc["id"], set())


# ════════════════════════════════════════════════════════════
# 向量化 / 清理（FakeEmbeddings，需 MySQL）
# ════════════════════════════════════════════════════════════

@requires_mysql
class TestVectorize:
    def test_vectorize_and_cleanup(self, tmp_path, monkeypatch):
        from backend.db.schema import init_db
        init_db()

        from backend.rag.config import RAGConfig
        monkeypatch.setattr(
            "backend.rag.vectorstore.get_rag_config",
            lambda: RAGConfig(vectorstore_type="chroma", persist_dir=str(tmp_path / "chroma")),
        )
        from langchain_core.embeddings import FakeEmbeddings
        monkeypatch.setattr(
            "backend.service.kb.kb_retriever._build_embeddings",
            lambda: FakeEmbeddings(size=16),
        )

        from backend.service.kb import kb_service
        from backend.service.kb.kb_retriever import (
            VectorRetriever, vectorize_document, unvectorize_document,
        )

        doc = asyncio.run(kb_service.create_document(
            user_id=930, filename="vec.txt",
            content="向量化测试内容：缓存穿透与缓存击穿的区别。".encode("utf-8"),
            chunk_size=200, chunk_overlap=0,
        ))
        try:
            result = vectorize_document(930, doc["id"])
            assert result["vectorized"] is True
            assert result["vectorized_chunks"] >= 1

            retriever = VectorRetriever(930)
            hits = retriever.retrieve("缓存穿透是什么", top_k=5)
            assert hits, "FakeEmbeddings 下相似度搜索应返回结果"

            unvectorize_document(930, doc["id"])
            detail = kb_service.get_document(930, doc["id"], set())
            assert detail["vectorized"] is False
        finally:
            kb_service.delete_document(930, doc["id"], set())

    def test_vectorize_missing_doc(self):
        from backend.service.kb.kb_retriever import vectorize_document
        from backend.service.kb.kb_service import KbNotFound
        with pytest.raises(KbNotFound):
            vectorize_document(999999, 999999)

