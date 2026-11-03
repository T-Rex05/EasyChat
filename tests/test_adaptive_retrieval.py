"""
自适应检索链路测试（知识库 + 记忆）

覆盖：
1. 链路分类：总结型（社区报告） vs 自适应（实体 local → 文本块兜底）
2. 实体描述构建
3. 实体向量库的过滤器/相似度换算
4. 知识库自适应检索的三条分支（entity_local / basic 兜底 / 实体命中但无文本块再兜底）
5. 记忆自适应检索的两条分支（memory_local / memory_basic）+ 意图过滤回退
"""

import pytest

from backend.service.kb import adaptive_retriever as ar
from backend.service.kb.entity_vectorstore import build_entity_description, _filter_kwargs, _to_similarity
from backend.service.memory.adaptive_retriever import (
    AdaptiveMemoryRetriever,
    METHOD_MEMORY_BASIC,
    METHOD_MEMORY_LOCAL,
)


# ════════════════════════════════════════════════════════════
# 1. 链路分类
# ════════════════════════════════════════════════════════════

class TestClassifyRetrievalKind:
    """总结型判定：只认强总结信号，不能误伤实体型问题"""

    @pytest.mark.parametrize("query", [
        "总结一下三国演义的主要内容",
        "概括这份文档的核心观点",
        "这份报告整体讲了什么",
        "帮我梳理一下发展历程",
        "对比所有渠道的差异和发展历程",   # 弱信号 ≥2
        "为什么会出现这种趋势，分析所有可能的原因",  # 弱信号多命中
    ])
    def test_summary_queries(self, query):
        assert ar.classify_retrieval_kind(query) == ar.KIND_SUMMARY

    @pytest.mark.parametrize("query", [
        "关羽的武器是什么？",
        "五虎上将是哪五将，有什么故事背景？",   # 设计文档 §8.1：必须走 Local Search
        "刘备的结义兄弟是谁？",
        "MySQL 的配置项怎么写？",
        "",
        "   ",
    ])
    def test_adaptive_queries(self, query):
        assert ar.classify_retrieval_kind(query) == ar.KIND_ADAPTIVE

    def test_short_single_analytic_signal_is_adaptive(self):
        """单个弱信号 + 短查询 → 不算总结型（避免"核心武器是什么"被误判）"""
        assert ar.classify_retrieval_kind("核心武器是什么") == ar.KIND_ADAPTIVE


# ════════════════════════════════════════════════════════════
# 2. 实体描述与向量库工具
# ════════════════════════════════════════════════════════════

class TestEntityDescription:

    def test_full_description(self):
        entity = {
            "name": "关羽",
            "entity_type": "person",
            "description": "三国时期蜀汉名将",
            "aliases": ["云长"],
        }
        rels = [
            {"relation_type": "WORKS_WITH", "other_name": "刘备"},
            {"relation_type": "LIKES", "other_name": "青龙偃月刀"},
            {"relation_type": "KNOWS", "other_name": "张飞"},
            {"relation_type": "KNOWS", "other_name": "曹操"},  # 第 4 条应被裁剪
        ]
        text = build_entity_description(entity, rels)
        assert text.startswith("关羽，person，三国时期蜀汉名将")
        assert "别名云长" in text
        assert "与刘备共事" in text
        assert "与青龙偃月刀喜欢" in text
        assert "曹操" not in text  # 只取前 3 条关系

    def test_minimal_description(self):
        assert build_entity_description({"name": "刘备"}, None) == "刘备"

    def test_aliases_as_json_string(self):
        entity = {"name": "玄德", "aliases": '["刘备", "刘皇叔"]'}
        assert "别名刘备、刘皇叔" in build_entity_description(entity)

    def test_empty(self):
        assert build_entity_description({}, None) == ""


class TestVectorStoreHelpers:

    def test_cosine_metric_is_identity(self):
        assert _to_similarity(0.83, "cosine") == pytest.approx(0.83)
        assert _to_similarity(1.2, "cosine") == 1.0     # 钳位
        assert _to_similarity(-0.5, "cosine") == 0.0

    def test_chroma_cosine_space_distance(self):
        # Chroma cosine 空间返回 1-cos 的距离
        assert _to_similarity(0.2, "l2") == pytest.approx(0.8)

    def test_milvus_expr_filter(self):
        class FakeMilvus:
            pass

        kwargs = _filter_kwargs(FakeMilvus(), {"source_type": "memory", "source_memory_id": 12})
        assert kwargs["expr"] == 'source_type == "memory" and source_memory_id == 12'

    def test_chroma_filter_multi_condition(self):
        from langchain_chroma import Chroma  # noqa: F401 —— 仅用于取类名判断

        class FakeStore:
            pass

        FakeStore.__module__ = "langchain_chroma.vectorstores"
        kwargs = _filter_kwargs(FakeStore(), {"source_type": "doc", "user_id": 1})
        assert kwargs["filter"] == {"$and": [{"source_type": "doc"}, {"user_id": 1}]}


# ════════════════════════════════════════════════════════════
# 3. 知识库自适应检索
# ════════════════════════════════════════════════════════════

def _entity_hit(name="关羽", score=0.86, chunk_id=101, entity_id="e1", memory_id=0):
    return {
        "entity_id": entity_id,
        "entity_name": name,
        "entity_type": "person",
        "description": f"{name}的描述",
        "source_type": "doc" if not memory_id else "memory",
        "source_document_id": 1,
        "source_chunk_id": chunk_id,
        "source_memory_id": memory_id,
        "user_id": 1,
        "confidence": 1.0,
        "score": score,
    }


class TestKBAdaptiveRetriever:

    def _retriever(self, monkeypatch, entity_hits):
        r = ar.AdaptiveRetriever(user_id=1)
        monkeypatch.setattr(r, "search_entities", lambda q: list(entity_hits))
        monkeypatch.setattr(r, "_filter_by_scope_layer", lambda results, layers: results)
        return r

    def test_entity_local_hit(self, monkeypatch):
        """实体门控放行 → 只走实体 local（不跑分片检索），文本块来自种子实体与图扩展"""
        # 两个强命中实体（≥0.6）才判"够用"
        r = self._retriever(monkeypatch, [_entity_hit(), _entity_hit(name="青龙偃月刀", score=0.81)])
        monkeypatch.setattr(
            r, "_expand_from_entities",
            lambda ids: {
                "entities": [{"entity_id": "e2", "entity_name": "青龙偃月刀", "entity_type": "tool"}],
                "relationships": [{"relation_type": "USES", "target_entity_name": "青龙偃月刀"}],
                "chunk_scores": {202: 0.45},
            },
        )
        monkeypatch.setattr(
            r, "_load_chunks",
            staticmethod(lambda ids: {
                101: {"id": 101, "document_id": 1, "content": "关羽字云长", "kind": "parent"},
                202: {"id": 202, "document_id": 1, "content": "青龙偃月刀重八十二斤", "kind": "parent"},
            }),
        )
        # 分片检索不该被调用
        monkeypatch.setattr(
            r, "_basic_search",
            lambda *a, **kw: (_ for _ in ()).throw(AssertionError("门控放行时不应跑分片检索")),
        )

        out = r.retrieve("关羽的武器是什么", top_k=5)
        assert out["method"] == ar.METHOD_ENTITY_LOCAL
        assert out["confident"] is True
        assert out["kind"] == ar.KIND_ADAPTIVE
        assert set(out["routes"].keys()) == {"entity_local"}
        assert len(out["results"]) == 2
        # 种子实体（0.86）应排在邻居实体（0.45）之前
        assert out["results"][0]["chunk_id"] == 101
        assert out["results"][0]["retrieval_source"] == ar.METHOD_ENTITY_LOCAL
        # entity_score 保留实体余弦分（score 会被 RRF 融合覆盖）
        assert out["results"][0]["entity_score"] == pytest.approx(0.86)

    def test_single_strong_entity_is_not_confident(self, monkeypatch):
        """只有一个强命中实体 → 判"不够"（单点擦边命中够不到同文档其他块），走两路补齐"""
        r = self._retriever(monkeypatch, [_entity_hit(score=0.65)])
        monkeypatch.setattr(
            r, "_expand_from_entities",
            lambda ids: {"entities": [], "relationships": [], "chunk_scores": {}},
        )
        monkeypatch.setattr(
            r, "_load_chunks",
            staticmethod(lambda ids: {101: {"id": 101, "document_id": 1, "content": "关羽", "kind": "parent"}}),
        )
        monkeypatch.setattr(
            r, "_basic_search",
            lambda *a, **kw: {"method": ar.METHOD_BASIC,
                              "results": [{"chunk_id": 999, "content": "另一块", "score": 0.9}]},
        )

        out = r.retrieve("关羽", top_k=5)
        assert out["confident"] is False
        assert out["strong_entity_count"] == 1
        assert "强实体不足" in out["fallback_reason"]
        # 实体块与分片块都在（两路补检）
        assert set(out["routes"].keys()) == {"entity_local", "basic"}
        ids = {r["chunk_id"] for r in out["results"]}
        assert ids == {101, 999}

    def test_entity_miss_falls_back_to_basic(self, monkeypatch):
        """实体未命中（空结果）→ 文本块兜底"""
        r = self._retriever(monkeypatch, [])
        called = {}

        def fake_basic(query, top_k, kb_id, mode="hybrid", _user_layers=None):
            called["mode"] = mode
            return {"method": ar.METHOD_BASIC, "results": [{"chunk_id": 1, "content": "x", "score": 0.9}]}

        monkeypatch.setattr(r, "_basic_search", fake_basic)

        out = r.retrieve("完全不存在的实体问题", top_k=5)
        assert out["confident"] is False
        assert out["fallback_reason"] == "实体未命中"
        assert out["results"][0]["chunk_id"] == 1

    def test_low_entity_score_falls_back_to_basic(self, monkeypatch):
        """实体分低于阈值 → 文本块兜底（阈值语义：余弦 < 0.5）"""
        r = self._retriever(monkeypatch, [_entity_hit(score=0.31)])
        monkeypatch.setattr(
            r, "_basic_search",
            lambda *a, **kw: {"method": ar.METHOD_BASIC, "results": [{"chunk_id": 9, "score": 0.5}]},
        )

        out = r.retrieve("弱相关问题", top_k=5)
        assert out["confident"] is False
        assert "实体分数不足" in out["fallback_reason"]
        assert out["top1_entity_score"] == pytest.approx(0.31)

    def test_entity_hit_without_chunks_falls_back(self, monkeypatch):
        """实体命中但图扩展拿不到文本块 → 仍然兜底，绝不返回空，且原因必须准确"""
        r = self._retriever(monkeypatch, [_entity_hit(chunk_id=0), _entity_hit(name="B", score=0.7)])
        monkeypatch.setattr(
            r, "_expand_from_entities",
            lambda ids: {"entities": [], "relationships": [], "chunk_scores": {}},
        )
        monkeypatch.setattr(
            r, "_basic_search",
            lambda *a, **kw: {"method": ar.METHOD_BASIC, "results": [{"chunk_id": 3, "score": 0.4}]},
        )

        out = r.retrieve("实体没有来源文本块", top_k=5)
        assert out["results"]
        # 不能报成"实体分数不足"（top1=0.86 ≥ 阈值），否则日志与真实原因不符
        assert "实体命中但未取到文本块" in out["fallback_reason"]

    def test_routes_dedup_same_chunk(self, monkeypatch):
        """两路命中同一个 chunk → 去重成一条（且分数叠加，排更前）"""
        r = self._retriever(monkeypatch, [_entity_hit(score=0.65)])
        monkeypatch.setattr(
            r, "_load_chunks",
            staticmethod(lambda ids: {101: {"id": 101, "document_id": 1, "content": "关羽", "kind": "parent"}}),
        )
        monkeypatch.setattr(
            r, "_expand_from_entities",
            lambda ids: {"entities": [], "relationships": [], "chunk_scores": {}},
        )
        monkeypatch.setattr(
            r, "_basic_search",
            lambda *a, **kw: {"method": ar.METHOD_BASIC, "results": [
                {"chunk_id": 101, "content": "关羽", "score": 0.9},     # 与实体路同一块
                {"chunk_id": 202, "content": "另一块", "score": 0.8},
            ]},
        )

        out = r.retrieve("关羽", top_k=5)
        ids = [x["chunk_id"] for x in out["results"]]
        assert ids.count(101) == 1, "同一 chunk 必须在融合后只出现一次"
        assert 101 in ids

    def test_rewrite_query_skips_graph_expansion(self, monkeypatch):
        """改写查询只做实体检索（不做图扩展），避免重复遍历同一批邻居"""
        r = self._retriever(monkeypatch, [_entity_hit(score=0.7)])
        calls = {"expand": 0}

        def fake_expand(ids):
            calls["expand"] += 1
            return {"entities": [], "relationships": [], "chunk_scores": {}}

        monkeypatch.setattr(r, "_expand_from_entities", fake_expand)
        monkeypatch.setattr(
            r, "_load_chunks",
            staticmethod(lambda ids: {101: {"id": 101, "document_id": 1, "content": "关羽", "kind": "parent"}}),
        )
        monkeypatch.setattr(
            r, "_basic_search",
            lambda *a, **kw: {"method": ar.METHOD_BASIC, "results": []},
        )

        r.retrieve("改写措辞", top_k=5, enable_graph_expansion=False)
        assert calls["expand"] == 0

    def test_precomputed_entity_hits_are_reused(self, monkeypatch):
        """上层已做过门控探针 → 复用命中，不再重复 embedding + Milvus"""
        r = ar.AdaptiveRetriever(user_id=1)
        monkeypatch.setattr(
            r, "search_entities",
            lambda q: (_ for _ in ()).throw(AssertionError("不应重复做实体检索")),
        )
        monkeypatch.setattr(r, "_filter_by_scope_layer", lambda results, layers: results)
        monkeypatch.setattr(r, "_load_chunks", staticmethod(lambda ids: {}))
        monkeypatch.setattr(
            r, "_basic_search",
            lambda *a, **kw: {"method": ar.METHOD_BASIC, "results": []},
        )
        out = r.retrieve("关羽", top_k=3, entity_hits=[_entity_hit(score=0.3)])
        assert out["entity_hits"] == 1

    def test_count_strong_and_is_confident(self):
        r = ar.AdaptiveRetriever(user_id=1)
        hits = [_entity_hit(score=s) for s in (0.9, 0.7, 0.61, 0.59, 0.2)]
        assert r.count_strong(hits) == 3
        assert r.is_confident(hits) is True
        assert r.is_confident([_entity_hit(score=0.8)]) is False

    def test_community_report_search_returns_none_without_reports(self, monkeypatch):
        r = ar.AdaptiveRetriever(user_id=1)
        monkeypatch.setattr(r, "_has_community_reports", lambda: False)
        assert r.community_report_search("总结一下") is None

    def test_community_report_search_returns_answer(self, monkeypatch):
        r = ar.AdaptiveRetriever(user_id=1)
        monkeypatch.setattr(r, "_has_community_reports", lambda: True)

        class FakeGlobal:
            def __init__(self, user_id, map_workers=5):
                pass

            def _get_all_reports(self):
                return [{"community_id": "c1", "title": "五虎上将社区", "summary": "五虎上将"}]

            def retrieve(self, query, max_reports=8, reports=None):
                return {"answer": "三国核心是群雄逐鹿", "reports_used": 7, "sources": ["五虎上将社区"]}

        import backend.service.kb.graphrag_retriever as gr

        monkeypatch.setattr(gr, "GlobalRetriever", FakeGlobal)

        out = r.community_report_search("总结三国演义的主题")
        assert out["method"] == ar.METHOD_GLOBAL
        assert out["reports_used"] == 7
        assert "群雄逐鹿" in out["answer"]

    def test_community_report_placeholder_answer_falls_back(self, monkeypatch):
        """GlobalRetriever 的兜底文案非空但无信息量 → 必须按失败处理（否则拿到一句废话且不降级）"""
        r = ar.AdaptiveRetriever(user_id=1)
        monkeypatch.setattr(r, "_has_community_reports", lambda: True)

        class FakeGlobal:
            def __init__(self, user_id, map_workers=5):
                pass

            def _get_all_reports(self):
                return []

            def retrieve(self, query, max_reports=8, reports=None):
                return {
                    "answer": "无法从社区报告中提取相关信息",
                    "reports_used": 0,
                    "sources": [],
                }

        import backend.service.kb.graphrag_retriever as gr

        monkeypatch.setattr(gr, "GlobalRetriever", FakeGlobal)
        assert r.community_report_search("总结一下") is None

    def test_select_reports_falls_back_without_embeddings(self, monkeypatch):
        """报告相关性预筛失败 → 按原顺序取前 N 份（不能因此拿不到报告）"""
        import backend.rag.embeddings as emb_mod

        monkeypatch.setattr(
            emb_mod, "get_embeddings",
            lambda: (_ for _ in ()).throw(RuntimeError("embedding 不可用")),
        )
        r = ar.AdaptiveRetriever(user_id=1)
        reports = [{"community_id": f"c{i}", "title": f"t{i}", "summary": "s"} for i in range(5)]
        out = r._select_reports("查询", reports, top_n=2)
        assert [x["community_id"] for x in out] == ["c0", "c1"]

    def test_select_reports_ranks_by_similarity(self, monkeypatch):
        """有 embedding 时按语义相似度选取最相关的 N 份"""
        import backend.rag.embeddings as emb_mod

        class FakeEmbeddings:
            def embed_query(self, text):
                return [1.0, 0.0]

            def embed_documents(self, texts):
                # 第 3 份报告与查询同向 → 应排第一
                return [[0.0, 1.0], [0.2, 0.98], [1.0, 0.0], [0.1, 0.99], [0.3, 0.95]]

        monkeypatch.setattr(emb_mod, "get_embeddings", lambda: FakeEmbeddings())
        r = ar.AdaptiveRetriever(user_id=1)
        reports = [{"community_id": f"c{i}", "title": f"t{i}", "summary": "s"} for i in range(5)]
        out = r._select_reports("查询", reports, top_n=2)
        assert out[0]["community_id"] == "c2"


class TestForceRetrievalOverride:
    """
    显式检索入口不能被 Adaptive RAG 路由器的 NO_RETRIEVAL 短路。

    实测事故：模型调用 knowledge_search(query="关羽 武器")（len=5、无检索信号）→
    路由器判 no_retrieval → 整条检索被跳过 → 用户得到"知识库中暂无相关信息"，
    而知识库里其实有该文档。
    """

    @staticmethod
    def _stub_router(monkeypatch):
        import backend.service.kb.kb_adaptive_router as router_mod

        class SkipResult:
            complexity = type("C", (), {"value": "no_retrieval"})()
            skip_retrieval = True
            enable_rewrite = False
            enable_sub_queries = False
            enable_web_fallback = False
            top_k_multiplier = 0.0
            reason = "短查询(len=5)，LLM 直答"

        monkeypatch.setattr(router_mod, "route_query", lambda query, user_id=0: SkipResult())

    @staticmethod
    def _stub_kb_selection(monkeypatch):
        from backend.service.kb.knowledge_base_service import KnowledgeBaseService

        monkeypatch.setattr(KnowledgeBaseService, "candidate_kbs_for_route", lambda self, user_id: [])
        monkeypatch.setattr(
            KnowledgeBaseService, "llm_select_kbs", lambda self, query, user_id, cands: []
        )

    def test_force_retrieval_bypasses_no_retrieval(self, monkeypatch):
        from backend.service.kb.kb_retriever import dual_path_retrieve

        self._stub_router(monkeypatch)
        self._stub_kb_selection(monkeypatch)

        result = dual_path_retrieve(
            user_id=1, query="关羽 武器",
            adaptive_routing=True, force_retrieval=True,
            enable_semantic_cache=False, confidence_gate=False,
        )
        assert (result.get("quality_assessment") or {}).get("reason") != "no_retrieval"

    def test_without_force_retrieval_keeps_short_circuit(self, monkeypatch):
        from backend.service.kb.kb_retriever import dual_path_retrieve

        self._stub_router(monkeypatch)
        self._stub_kb_selection(monkeypatch)

        result = dual_path_retrieve(
            user_id=1, query="关羽 武器",
            adaptive_routing=True, force_retrieval=False,
            enable_semantic_cache=False, confidence_gate=False,
        )
        assert (result.get("quality_assessment") or {}).get("reason") == "no_retrieval"


class TestSmartRetrieverUnification:
    """SmartRetriever（mode="smart" / 调试端点）的分类规则必须与主链路一致"""

    @staticmethod
    def _stub(monkeypatch):
        from backend.service.kb.graphrag_retriever import SmartRetriever

        calls = {}
        monkeypatch.setattr(
            SmartRetriever, "_retrieve_local",
            lambda self, query, top_k: calls.setdefault("local", (query, top_k)) or {"query_type": "local"},
        )
        monkeypatch.setattr(
            SmartRetriever, "_retrieve_global",
            lambda self, query: calls.setdefault("global", query) or {"query_type": "global"},
        )
        return SmartRetriever(1), calls

    def test_summary_goes_global(self, monkeypatch):
        retriever, calls = self._stub(monkeypatch)
        retriever.retrieve("总结一下这份文档的整体内容")
        assert "global" in calls and "local" not in calls

    def test_entity_question_goes_local(self, monkeypatch):
        """关键回归：'五虎上将是哪五将，有什么故事背景' 不能被旧分类器判成 GLOBAL"""
        retriever, calls = self._stub(monkeypatch)
        retriever.retrieve("五虎上将是哪五将，有什么故事背景")
        assert "local" in calls and "global" not in calls


class TestEmptyResultAndEmptyKB:
    """
    pymilvus 3.0.1 的空结果解析 Bug 与"空知识库"防护。

    实测（2026-09-23，pymilvus 3.0.1 + Milvus）：
    - `kb_id == 5`（有数据）→ 正常返回
    - `kb_id == 1` / `kb_id > 9999` / `kb_id in [1]`（零命中）→
      抛 `MilvusException: Unsupported field type: 0`（结果解析阶段，非过滤语法问题）
    若不识别，会把"没有相关内容"渲染成"向量库故障"，触发一堆 ERROR traceback 与空转降级。
    """

    def test_empty_result_error_recognized(self):
        from backend.service.kb.kb_retriever import _is_empty_result_milvus_error

        assert _is_empty_result_milvus_error(
            Exception("<MilvusException: (code=Unsupported field type: 0, message=)>")
        )

    def test_connection_error_is_not_treated_as_empty(self):
        from backend.service.kb.kb_retriever import _is_empty_result_milvus_error

        assert not _is_empty_result_milvus_error(
            Exception("<MilvusException: (code=2, message=failed to connect to Milvus)>")
        )
        assert not _is_empty_result_milvus_error(TimeoutError("timeout"))

    def test_vector_retriever_skips_kb_without_vectors(self, monkeypatch):
        """空库直接返回空，不调用向量库（避免零命中过滤报错 + 无谓 embedding 调用）"""
        import backend.service.kb.kb_retriever as kb_mod

        monkeypatch.setattr(
            kb_mod, "get_kb_index_status",
            lambda kb_id: {"vectors": False, "chunks": False},
        )
        monkeypatch.setattr(
            kb_mod, "_build_user_vectorstore",
            lambda user_id: (_ for _ in ()).throw(AssertionError("不应该去建向量库")),
        )

        retriever = kb_mod.VectorRetriever.__new__(kb_mod.VectorRetriever)
        retriever.user_id = 1
        retriever.kind = "all"
        retriever.kb_id = 1
        retriever._store = None

        assert retriever.retrieve("关羽 武器", top_k=3) == []

    def test_bm25_retriever_skips_kb_without_chunks(self, monkeypatch):
        import backend.service.kb.kb_retriever as kb_mod

        monkeypatch.setattr(
            kb_mod, "get_kb_index_status",
            lambda kb_id: {"vectors": True, "chunks": False},
        )
        monkeypatch.setattr(
            kb_mod.BM25Retriever, "_get_index",
            lambda self: (_ for _ in ()).throw(AssertionError("不应该去建 BM25 索引")),
        )

        retriever = kb_mod.BM25Retriever(1, kb_id=1)
        assert retriever.retrieve("关羽 武器", top_k=3) == []

    def test_empty_kb_dropped_in_dual_path(self, monkeypatch):
        """空知识库从主路径中剔除（LLM 可能选中一个没有文档的库）"""
        import backend.service.kb.kb_retriever as kb_mod

        status = {
            1: {"vectors": False, "chunks": False},   # 空库 → 剔除
            5: {"vectors": True, "chunks": True},     # 有数据 → 保留
        }
        monkeypatch.setattr(kb_mod, "get_kb_index_status", lambda kb_id: status[int(kb_id)])

        from backend.service.kb.knowledge_base_service import KnowledgeBaseService

        monkeypatch.setattr(
            KnowledgeBaseService, "candidate_kbs_for_route",
            lambda self, user_id: [{"id": 1, "kb_name": "默认知识库"}, {"id": 5, "kb_name": "三国演义"}],
        )
        monkeypatch.setattr(
            KnowledgeBaseService, "llm_select_kbs",
            lambda self, query, user_id, cands: [1, 5],
        )

        captured = {}

        class FakeAdaptive:
            def __init__(self, user_id):
                pass

            def search_entities(self, query):
                return []

            def count_strong(self, hits):
                return 0

            def is_confident(self, hits):
                return False

            def retrieve(self, query, **kwargs):
                captured["kb_id"] = kwargs.get("kb_id")
                return {"method": "basic", "results": [], "kind": "adaptive",
                        "routes": {"basic": []}, "confident": False}

        import backend.service.kb.adaptive_retriever as ar_mod

        monkeypatch.setattr(ar_mod, "AdaptiveRetriever", FakeAdaptive)

        result = kb_mod.dual_path_retrieve(
            user_id=1, query="关羽的武器是什么",
            adaptive_routing=False, enable_semantic_cache=False, confidence_gate=False,
        )
        # 只对"有数据的库 5"做检索，空库 1 被跳过
        assert captured.get("kb_id") == 5
        assert [kb["id"] for kb in result["selected_kbs"]] == [1, 5]


class TestRelationCard:
    """关系卡片：按查询信号分档注入（strong/weak/none）"""

    @staticmethod
    def _entities():
        return [
            {"entity_id": "e1", "entity_name": "关羽", "entity_type": "person", "description": "蜀汉名将"},
            {"entity_id": "e2", "entity_name": "青龙偃月刀", "entity_type": "tool", "description": "关羽的兵器"},
        ]

    @staticmethod
    def _relations():
        return [
            {"source_entity_name": "关羽", "target_entity_name": "青龙偃月刀",
             "relation_type": "USES", "target_entity_id": "e2"},
            {"source_entity_name": "关羽", "target_entity_name": "刘备",
             "relation_type": "KNOWS", "target_entity_id": "e3"},
        ]

    def test_no_signal_no_injection(self):
        card = ar.build_relation_card("关羽的武器是什么", self._entities(), self._relations())
        assert card["tier"] == "none"
        assert card["lines"] == []

    def test_strong_signal_injects_entities_and_edges(self):
        card = ar.build_relation_card("关羽和张飞是什么关系", self._entities(), self._relations())
        assert card["tier"] == "strong"
        assert any("关羽" in line and "person" in line for line in card["lines"])
        assert any("--[使用]-->" in line for line in card["lines"])

    def test_weak_signal_only_entity_cards(self):
        """两个已命中实体并列出现（无关系型问法）→ 只给实体卡片，不给关系边"""
        card = ar.build_relation_card("关羽 和 青龙偃月刀 怎么样", self._entities(), self._relations())
        assert card["tier"] == "weak"
        assert card["lines"]
        assert not any("--[" in line for line in card["lines"])

    def test_signal_classifier(self):
        assert ar.classify_relation_signal("谁隶属于曹操") == "strong"
        assert ar.classify_relation_signal("随便问问") == "none"


class TestBm25Serialization:
    """回归：BM25 索引序列化只能碰真实存在的属性（否则非空语料必然崩）"""

    def test_round_trip(self):
        import rank_bm25

        from backend.service.kb.kb_retriever import BM25Retriever

        bm = rank_bm25.BM25Okapi([["a", "b"], ["b", "c"], ["c", "d"]])
        data = BM25Retriever._serialize_bm25(bm)
        assert "doc_term_freqs" not in data  # 这个属性在 rank_bm25 里不存在
        back = BM25Retriever._deserialize_bm25(data)
        assert len(back.get_scores(["b"])) == 3

    def test_scores_match_original(self):
        import rank_bm25

        from backend.service.kb.kb_retriever import BM25Retriever

        corpus = [["关羽", "武器"], ["张飞", "性格"], ["关羽", "青龙偃月刀"]]
        bm = rank_bm25.BM25Okapi(corpus)
        back = BM25Retriever._deserialize_bm25(BM25Retriever._serialize_bm25(bm))
        assert list(back.get_scores(["关羽"])) == list(bm.get_scores(["关羽"]))

    def test_none_passthrough(self):
        from backend.service.kb.kb_retriever import BM25Retriever

        assert BM25Retriever._serialize_bm25(None) is None
        assert BM25Retriever._deserialize_bm25(None) is None


# ════════════════════════════════════════════════════════════
# 4. 记忆自适应检索
# ════════════════════════════════════════════════════════════

class FakeMemoryService:
    """最小记忆服务替身：只提供 hybrid_search / rerank_memories"""

    def __init__(self, vector_results=None, rerank_top_k=None):
        self.vector_results = vector_results if vector_results is not None else []
        self.calls = []
        self.rerank_top_k = rerank_top_k

    def hybrid_search(self, user_id, query, top_k=30, memory_type=None, min_score=0.3):
        self.calls.append(memory_type)
        if memory_type is not None and not self.vector_results:
            return []
        return list(self.vector_results)

    def rerank_memories(self, memories, top_k=10):
        ranked = sorted(memories, key=lambda m: m.get("score", 0), reverse=True)
        return ranked[:top_k]


class TestMemoryAdaptiveRetriever:

    def test_local_search_hit(self, monkeypatch):
        """记忆实体命中 → memory_local，记忆来自 source_memory_id + 跨层边"""
        service = FakeMemoryService()
        r = AdaptiveMemoryRetriever(service)
        monkeypatch.setattr(
            AdaptiveMemoryRetriever, "_search_entities",
            lambda self, user_id, query, memory_type: [_entity_hit(memory_id=436, chunk_id=0)],
        )
        monkeypatch.setattr(
            r, "_expand_from_entities",
            lambda user_id, ids: {"entities": [], "relationships": [], "memory_ids": [139]},
        )
        monkeypatch.setattr(
            AdaptiveMemoryRetriever, "_load_memories",
            staticmethod(lambda user_id, ids: {
                436: {"id": 436, "user_id": user_id, "content": "用户需要对比分析报告",
                      "memory_type": "fact", "importance_score": 0.8, "access_count": 1,
                      "created_at": "2026-09-01 00:00:00", "memory_layer": "episodic"},
                139: {"id": 139, "user_id": user_id, "content": "用户用 Python 做后端",
                      "memory_type": "skill", "importance_score": 0.7, "access_count": 2,
                      "created_at": "2026-09-02 00:00:00", "memory_layer": "episodic"},
            }),
        )

        out = r.retrieve(user_id=1, query="用户偏好什么", top_k=8)
        assert out["method"] == METHOD_MEMORY_LOCAL
        assert out["seed_entities"] == ["关羽"]
        ids = sorted(item["memory"]["id"] for item in out["results"])
        assert ids == [139, 436]

    def test_basic_search_when_no_entity(self, monkeypatch):
        """实体未命中 → 记忆向量检索兜底"""
        service = FakeMemoryService(vector_results=[
            {"memory": {"id": 1, "content": "记忆A", "importance_score": 0.5, "created_at": "2026-09-01 00:00:00"},
             "score": 0.66},
        ])
        r = AdaptiveMemoryRetriever(service)
        monkeypatch.setattr(
            AdaptiveMemoryRetriever, "_search_entities",
            lambda self, user_id, query, memory_type: [],
        )

        out = r.retrieve(user_id=1, query="随便问问", top_k=8, memory_type="preference")
        assert out["method"] == METHOD_MEMORY_BASIC
        assert out["fallback_reason"] == "实体未命中"
        assert len(out["results"]) == 1
        assert out["results"][0]["memory"]["id"] == 1

    def test_intent_filter_fallback(self, monkeypatch):
        """意图过滤后为空 → 自动回退到不过滤类型（宁可多召回也不要空）"""
        service = FakeMemoryService()

        def hybrid(user_id, query, top_k=30, memory_type=None, min_score=0.3):
            service.calls.append(memory_type)
            if memory_type is not None:
                return []
            return [{"memory": {"id": 2, "content": "兜底记忆", "importance_score": 0.5,
                                "created_at": "2026-09-01 00:00:00"}, "score": 0.6}]

        service.hybrid_search = hybrid
        r = AdaptiveMemoryRetriever(service)
        monkeypatch.setattr(
            AdaptiveMemoryRetriever, "_search_entities",
            lambda self, user_id, query, memory_type: [],
        )

        out = r.retrieve(user_id=1, query="用户喜欢什么", top_k=8, memory_type="preference")
        assert out["method"] == METHOD_MEMORY_BASIC
        assert service.calls == ["preference", None]   # 先过滤、再回退
        assert out["results"][0]["memory"]["id"] == 2

    def test_low_score_falls_back(self, monkeypatch):
        service = FakeMemoryService(vector_results=[
            {"memory": {"id": 3, "content": "记忆B", "importance_score": 0.5,
                        "created_at": "2026-09-01 00:00:00"}, "score": 0.7},
        ])
        r = AdaptiveMemoryRetriever(service)
        monkeypatch.setattr(
            AdaptiveMemoryRetriever, "_search_entities",
            lambda self, user_id, query, memory_type: [_entity_hit(score=0.2, memory_id=1, chunk_id=0)],
        )

        out = r.retrieve(user_id=1, query="低相关", top_k=8)
        assert out["method"] == METHOD_MEMORY_BASIC
        assert "实体分数不足" in out["fallback_reason"]

    def test_local_hit_without_memories_falls_back(self, monkeypatch):
        """实体命中但没有可回捞的记忆 → 兜底，不返回空，且降级原因必须准确"""
        service = FakeMemoryService(vector_results=[
            {"memory": {"id": 4, "content": "记忆C", "importance_score": 0.5,
                        "created_at": "2026-09-01 00:00:00"}, "score": 0.5},
        ])
        r = AdaptiveMemoryRetriever(service)
        monkeypatch.setattr(
            AdaptiveMemoryRetriever, "_search_entities",
            lambda self, user_id, query, memory_type: [_entity_hit(memory_id=0, chunk_id=0)],
        )
        monkeypatch.setattr(
            r, "_expand_from_entities",
            lambda user_id, ids: {"entities": [], "relationships": [], "memory_ids": []},
        )

        out = r.retrieve(user_id=1, query="实体没有挂记忆", top_k=8)
        assert out["method"] == METHOD_MEMORY_BASIC
        assert out["results"]
        # 不能报成"实体分数不足"（top1=0.86 ≥ 阈值），否则日志与真实原因不符
        assert "实体命中但未取到记忆" in out["fallback_reason"]
