"""
AgentForge Memory Provider - Hermes MemoryProvider 实现

连接 Hermes 到 AgentForge 的增强记忆系统：
- 向量存储（Milvus/ChromaDB）
- 图增强（Neo4j，可选）
- 三阶段合并（衰减→去重→淘汰）
- 后台线程保护（go_safe）
"""

import contextvars
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.memory.types import MemoryItem, MemoryCategory, ConsolidationResult
from backend.memory.graph_memory import GraphMemory, get_graph_memory
from backend.memory.consolidator import MemoryConsolidator, get_consolidator
from backend.infrastructure.safe_executor import go_safe, publish_event_safe

logger = logging.getLogger(__name__)

# 记忆引用映射：{tag: memory_info}
# runtime.run() 初始化空 dict → copy_context() 传递到工作线程 → provider.prefetch() 填充
# stream.py 读取 → 解析 LLM 回答中的 [M1] 引用 → 返回给前端
_MEMORY_REFS_CTX: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "_hermes_memory_refs_ctx", default=None
)


def _extract_search_phrases(content: str, max_phrases: int = 2, max_len: int = 15) -> list:
    """
    从记忆内容中提取用于 KGStore 搜索的短关键词短语。

    实体名称通常 ≤15 字，直接用长文本 CONTAINS 搜索永远匹配不到。
    本函数取第一句（按中英文标点截断）或前 max_len 字，提取为搜索词。

    Args:
        content: 记忆内容
        max_phrases: 最多提取几个短语
        max_len: 每个短语最大长度

    Returns:
        短关键词列表
    """
    import re
    phrases = []
    # 按常见标点分句
    sentences = re.split(r'[，。！？；\n,.!?;\s]+', content.strip())
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 2:
            continue
        # 取前 max_len 个字符
        phrase = sent[:max_len]
        if phrase and phrase not in phrases:
            phrases.append(phrase)
        if len(phrases) >= max_phrases:
            break
    # 兜底：直接取开头
    if not phrases and content:
        phrases.append(content[:max_len])
    return phrases


def _classify_memory_intent(query: str) -> Optional[str]:
    """
    轻量意图分类，决定 prefetch 的记忆类型过滤。

    根据查询关键词推断用户想检索的记忆类型，prefetch 会据此
    只搜索对应 memory_type，减少无关记忆注入。

    Returns:
        "preference" | "skill" | "event" | "fact" | None（通用查询，不过滤）
    """
    # preference 类：偏好、喜欢、习惯
    if any(kw in query for kw in ["偏好", "喜欢", "习惯", "偏好设置", "工作流", "配置"]):
        return "preference"
    # skill 类：怎么做、方法、技能
    if any(kw in query for kw in ["怎么做", "如何", "方法", "技能", "技巧", "步骤", "流程"]):
        return "skill"
    # event 类：事件、上次、最近
    if any(kw in query for kw in ["上次", "最近", "之前", "事件", "什么时候", "那天"]):
        return "event"
    # fact 类：是什么、事实
    if any(kw in query for kw in ["是什么", "什么是", "事实", "项目", "定义"]):
        return "fact"
    return None  # 通用查询，不做类型过滤


# ── 矛盾检测辅助 ──
# 常见的对立关键词对（用于快速检测偏好类矛盾）
_CONTRADICTORY_PAIRS = [
    ("表格", "列表"), ("markdown", "纯文本"),
    ("喜欢", "不喜欢"), ("必须", "禁止"),
    ("推荐", "避免"), ("使用", "不用"),
    ("macOS", "Windows"), ("Windows", "macOS"),
    ("VSCode", "IntelliJ"), ("IntelliJ", "VSCode"),
]


def _is_potentially_contradictory(text_a: str, text_b: str) -> bool:
    """
    检测两段记忆文本是否存在潜在矛盾。

    策略：
    1. 两段文本有较高的主题重叠（共享 ≥3 个中文关键词或 ≥2 个英文词）
    2. 但包含对立关键词对（如「表格」vs「列表」）

    这是一个轻量规则检测，不做语义推理。
    """
    if not text_a or not text_b:
        return False

    a_lower = text_a.lower()
    b_lower = text_b.lower()

    # 条件 1：检查是否包含对立关键词对
    has_opposition = False
    for kw_a, kw_b in _CONTRADICTORY_PAIRS:
        if (kw_a.lower() in a_lower and kw_b.lower() in b_lower) or \
           (kw_b.lower() in a_lower and kw_a.lower() in b_lower):
            has_opposition = True
            break

    if not has_opposition:
        return False

    # 条件 2：主题重叠检查（共享足够多的关键词）
    # 简单分词：中文按字，英文按词
    def _simple_tokens(text: str) -> set:
        tokens = set()
        word = ""
        for ch in text:
            if 0x4E00 <= ord(ch) <= 0x9FFF:
                if word:
                    tokens.add(word.lower())
                    word = ""
                tokens.add(ch)
            elif ch.isalnum():
                word += ch
            else:
                if word:
                    tokens.add(word.lower())
                    word = ""
        if word:
            tokens.add(word.lower())
        # 移除停用词
        stop = {"的", "了", "是", "在", "和", "与", "或", "a", "the", "is", "to", "for", "of", "in"}
        return tokens - stop

    tokens_a = _simple_tokens(text_a)
    tokens_b = _simple_tokens(text_b)
    shared = tokens_a & tokens_b

    # 至少共享 3 个 token（说明主题重叠）
    return len(shared) >= 3


class AgentForgeMemoryProvider:
    """
    AgentForge 记忆提供者（增强版）
    
    实现 Hermes MemoryProvider 接口，连接到：
    - MemoryService（MySQL + 向量库）
    - GraphMemory（Neo4j 图增强，可选）
    - MemoryConsolidator（三阶段合并）
    
    特性：
    - 图增强检索：从种子记忆扩展关联记忆
    - 三阶段合并：衰减 → 去重/合并 → 双条件淘汰
    - 图中心度保护：高入度节点免于删除
    - 后台线程保护：所有异步任务走 go_safe
    """
    
    def __init__(self):
        self._session_id: str = ""
        self._user_id: int = 0
        self._hermes_home: str = ""
        self._initialized: bool = False
        self._delay_rounds: int = 10
        
        # 缓存
        self._prefetched_context: str = ""
        self._prefetch_lock = threading.Lock()
        # task_state 注入记录（按 session_id 分别记录）
        # ⚠️ 仅用于日志/统计：注入本身每轮都做（内容相同也注入），
        #    见 _get_task_state_injection 的说明。
        self._last_task_state_text: Dict[str, str] = {}
        # 该 dict 只在 on_session_switch 时 pop，需要上限防止无界增长
        self._MAX_TASK_STATE_TEXT: int = 500
        
        # 后台执行器
        self._executor = ThreadPoolExecutor(max_workers=2)
        
        # 轮次计数器
        self._turn_counter: int = 0

        # Pipeline Trace 引用缓存（initialize 时从 contextvar 获取，
        # prefetch 线程中 contextvar 可能丢失，用此缓存兜底）
        self._pipeline_trace = None
        
        # 内存记忆列表（用于合并），上限 500 防止无界增长
        self._memory_items: List[MemoryItem] = []
        self._memory_lock = threading.RLock()
        self._MAX_MEMORY_ITEMS = 500
        
        # 图增强层（可选）
        self._graph_memory: Optional[GraphMemory] = None
        
        # 合并器
        self._consolidator: Optional[MemoryConsolidator] = None

        # task_state（会话级任务状态维护）
        from backend.context.task_state import get_task_state_maintainer
        self._task_state = get_task_state_maintainer()
    
    # ========== MemoryProvider 接口实现 ==========
    
    @property
    def name(self) -> str:
        return "agentforge"
    
    def is_available(self) -> bool:
        """检查是否可用"""
        try:
            from backend.infrastructure import get_infrastructure
            infra = get_infrastructure()
            # 至少需要 MySQL，向量库和图谱可选
            return infra.mysql
        except Exception:
            return False
    
    def initialize(self, session_id: str, **kwargs) -> None:
        """初始化"""
        self._session_id = session_id
        self._hermes_home = kwargs.get("hermes_home", "")
        
        # 解析用户 ID
        user_id_str = kwargs.get("user_id", "") or kwargs.get("user_id_alt", "")
        if user_id_str:
            try:
                self._user_id = int(user_id_str)
            except ValueError:
                self._user_id = abs(hash(user_id_str)) % (10 ** 8)
        else:
            self._user_id = 1
        
        # 读取配置
        self._delay_rounds = int(os.getenv("MEMORY_DELAY_ROUNDS", "10"))
        
        # 初始化图增强层（如果 Neo4j 可用）
        try:
            self._graph_memory = get_graph_memory()
            if self._graph_memory and self._graph_memory._available():
                logger.info("GraphMemory enabled for memory enhancement")
            else:
                self._graph_memory = None
        except Exception as e:
            logger.debug(f"GraphMemory not available: {e}")
            self._graph_memory = None
        
        # 初始化合并器
        try:
            self._consolidator = get_consolidator()
            if self._graph_memory:
                self._consolidator.set_graph_memory(self._graph_memory)
        except Exception as e:
            logger.debug(f"Consolidator not available: {e}")
            self._consolidator = None
        
        # 加载现有记忆到内存
        self._load_memories_to_cache()
        
        self._initialized = True

        # 缓存 PipelineTrace 引用：initialize() 运行在 _mem_ctx.run() 上下文中，
        # 此时 contextvar 可用。后续 prefetch() 在 threading.Thread 中执行，
        # contextvar 可能丢失（Python threading.Thread 的 context 继承在某些场景不稳定），
        # 因此用实例属性兜底。
        try:
            from backend.service.pipeline_trace import PipelineTrace
            self._pipeline_trace = PipelineTrace.current()
        except Exception:
            self._pipeline_trace = None

        logger.info(
            f"AgentForgeMemoryProvider initialized: session={session_id}, "
            f"user_id={self._user_id}, delay_rounds={self._delay_rounds}, "
            f"graph_enabled={self._graph_memory is not None}"
        )
    
    def system_prompt_block(self) -> str:
        """系统提示词块"""
        if not self._initialized:
            return ""
        
        with self._prefetch_lock:
            if self._prefetched_context:
                return self._prefetched_context
        
        return ""
    
    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """
        检索相关记忆（自适应：记忆实体 local 优先，记忆向量兜底）

        流程：
        1. 意图分类 → 确定 memory_type 过滤
        2. 自适应检索（AdaptiveMemoryRetriever）
           ├─ 记忆实体向量检索命中 → Memory Local Search（实体 → 图扩展 → 关联记忆）
           └─ 未命中 → Memory Basic Search（记忆向量检索，现有实现）
           两条路径都在内部完成 Rerank 多维精排
        3. 图扩展（GraphMemory FOLLOWS/SIMILAR_TO，如果可用）
        4. KGStore 实体上下文补充
        5. 合并并格式化

        注：记忆侧**没有社区报告**这一层（见 docs/memory_adaptive_retrieval_design.md §12.1）
        """
        if not self._initialized or not self._user_id:
            return ""

        try:
            import time as _pt_time
            from backend.service.pipeline_trace import PipelineTrace
            _trace = PipelineTrace.current() or self._pipeline_trace
            _t0 = _pt_time.monotonic()

            from backend.service.memory import get_memory_service
            from backend.service.memory.adaptive_retriever import AdaptiveMemoryRetriever

            service = get_memory_service()

            # 1. 意图分类 → 决定过滤和 top_k（扩大候选池供 reranker 精排）
            intent_type = _classify_memory_intent(query)
            search_top_k = 30  # 给 reranker 足够的候选

            # 2. 自适应检索（实体 local 优先 → 记忆向量兜底；内部已做 Rerank 精排）
            adaptive_out = AdaptiveMemoryRetriever(service).retrieve(
                user_id=self._user_id,
                query=query,
                top_k=8,
                memory_type=intent_type,
                candidate_k=search_top_k,
            )
            results = adaptive_out.get("results") or []

            if not results:
                return ""

            # ── Pipeline Trace: 记忆自适应检索结果 ──
            if _trace:
                _trace.record("memory_hybrid_search",
                    query=query[:100],
                    intent_type=intent_type,
                    method=adaptive_out.get("method"),
                    seed_entities=adaptive_out.get("seed_entities", [])[:5],
                    entity_hits=adaptive_out.get("entity_hits", 0),
                    fallback_reason=adaptive_out.get("fallback_reason"),
                    total_results=len(results),
                    top_results=[
                        {"id": r.get("memory", {}).get("id"),
                         "content": r.get("memory", {}).get("content", "")[:100],
                         "score": round(r.get("final_score", r.get("score", 0)), 3),
                         "source": r.get("source", "unknown")}
                        for r in results[:5]
                    ],
                    elapsed_ms=round((_pt_time.monotonic() - _t0) * 1000),
                )

            reranked = results

            # ── Pipeline Trace: rerank 结果（精排在自适应检索器内部完成）──
            if _trace:
                _trace.record("memory_rerank",
                    method=adaptive_out.get("method"),
                    before=adaptive_out.get("candidate_count", 0), after=len(reranked),
                    top_results=[
                        {"id": r.get("memory", {}).get("id"),
                         "content": r.get("memory", {}).get("content", "")[:100],
                         "score": round(r.get("final_score", r.get("score", 0)), 3),
                         "source": r.get("source", "unknown")}
                        for r in reranked[:5]
                    ],
                    elapsed_ms=round((_pt_time.monotonic() - _t0) * 1000),
                )

            # 收集种子 ID（取 rerank 后的 top-5 做图扩展）
            seed_ids = []
            seed_by_id = {}
            for item in reranked:
                memory = item["memory"]
                mem_id = memory.get("id")
                if mem_id:
                    seed_ids.append(mem_id)
                    seed_by_id[mem_id] = item

            # 4. 图扩展（每步容错，保证部分降级）
            expanded_ids = set()
            if self._graph_memory and seed_ids:
                for sid in seed_ids[:5]:  # 只扩展前 5 个种子
                    try:
                        related = self._graph_memory.find_related(
                            sid, max_hops=2, user_id=self._user_id
                        )
                        expanded_ids.update(related)
                    except Exception as e:
                        # 单个种子扩展失败不阻塞其他种子
                        logger.debug(f"Graph expansion failed for seed {sid} (partial result ok): {e}")

            # ── Pipeline Trace: 图扩展结果 ──
            if _trace:
                _trace.record("memory_graph_expansion",
                    seed_ids=seed_ids[:5],
                    expanded_count=len(expanded_ids),
                    elapsed_ms=round((_pt_time.monotonic() - _t0) * 1000),
                )

            # 4.5 KGStore 实体级扩展（从知识图谱获取实体关系上下文）
            kg_context_items = []
            try:
                from backend.graphrag.kg_store import get_kg_store
                kg_store = get_kg_store()
                if kg_store.is_available():
                    # 从 rerank top-3 记忆中提取关键短语搜索 KGStore
                    for item in reranked[:3]:
                        memory = item.get("memory", {})
                        content = memory.get("content", "")
                        if not content:
                            continue
                        # 提取短关键词用于搜索（实体名通常 ≤15 字）
                        # 取第一句（到第一个句号/逗号/换行）或最多 15 字
                        search_phrases = _extract_search_phrases(content, max_phrases=2, max_len=15)
                        for phrase in search_phrases:
                            matches = kg_store.search_entities(
                                name=phrase, user_id=self._user_id, limit=2
                            )
                            for entity in matches:
                                # 避免重复
                                if any(kg.get("entity_name") == entity.name for kg in kg_context_items):
                                    continue
                                # 获取实体子图作为上下文
                                subgraph = kg_store.get_subgraph(
                                    entity.id, depth=1, user_id=self._user_id
                                )
                                ctx = kg_store._subgraph_to_context(subgraph)
                                if ctx:
                                    kg_context_items.append({
                                        "entity_name": entity.name,
                                        "entity_type": entity.entity_type.value,
                                        "context": ctx,
                                        "confidence": entity.confidence,
                                    })
                                if len(kg_context_items) >= 5:
                                    break
                            if len(kg_context_items) >= 5:
                                break
            except Exception as e:
                logger.debug(f"KGStore expansion failed (non-critical): {e}")

            # 5. 加载扩展记忆
            expanded_items = []
            if expanded_ids:
                for eid in expanded_ids:
                    if eid in seed_by_id:
                        continue  # 跳过已经在种子中的
                    # 从缓存加载
                    item = self._get_memory_by_id(eid)
                    if item:
                        expanded_items.append(item)

            # 6. 合并结果：reranked + 图扩展（图扩展给基础分 0.45）
            all_items = list(reranked) + [
                {"memory": m, "score": 0.45, "final_score": 0.45, "source": "graph"}
                for m in expanded_items
            ]

            # 7. 矛盾检测：检查 top 结果中是否存在语义相似但内容矛盾的记忆对
            conflict_warnings = []
            top_items = all_items[:8]  # 只在 top-8 中检测矛盾
            for i in range(len(top_items)):
                for j in range(i + 1, len(top_items)):
                    ci = top_items[i].get("memory", {}).get("content", "")
                    cj = top_items[j].get("memory", {}).get("content", "")
                    # 简单矛盾检测：长度相似的短文本，包含对立关键词
                    if _is_potentially_contradictory(ci, cj):
                        conflict_warnings.append((i, j))

            # ── Pipeline Trace: 最终合并结果 ──
            if _trace:
                _trace.record("memory_final",
                    total=len(all_items),
                    reranked_count=len(reranked),
                    expanded_count=len(expanded_items),
                    conflict_count=len(conflict_warnings),
                    kg_entity_count=len(kg_context_items),
                    elapsed_ms=round((_pt_time.monotonic() - _t0) * 1000),
                )

            # 8. 格式化为上下文（按 final_score 排序）
            lines = ["\n## 相关记忆"]

            all_items.sort(key=lambda x: x.get("final_score", x.get("score", 0)), reverse=True)

            # 获取共享的记忆引用映射（通过 ContextVar 传递给 stream.py）
            refs_map = _MEMORY_REFS_CTX.get()

            for idx, item in enumerate(all_items[:8], 1):  # 最多 8 条
                tag = f"M{idx}"
                memory = item.get("memory", {})
                mem_id = memory.get("id")
                mem_type = memory.get("memory_type", "unknown")
                content = memory.get("content", "")
                source = item.get("source", "vector")
                source_mark = "🔗" if source == "graph" else ""
                # 带编号标签：[M1] [type] content
                lines.append(f"- [{tag}] [{mem_type}] {content[:200]} {source_mark}")
                # 存入引用映射（stream.py 解析 LLM 回答中的 [M1] 后反查记忆详情）
                if refs_map is not None and mem_id:
                    refs_map[tag] = {
                        "id": mem_id,
                        "content": content[:200],
                        "memory_type": mem_type,
                        "created_at": str(memory.get("created_at", "")),
                    }

            # 矛盾警告（附在记忆列表末尾）
            if conflict_warnings:
                lines.append("\n⚠️ 注意：以上记忆中存在可能矛盾的信息，请以最近更新的为准。")

            # 7.5 KGStore 实体上下文（附在记忆列表之后，作为知识图谱补充）
            if kg_context_items:
                lines.append("\n## 知识图谱实体")
                for kg in kg_context_items:
                    ent_name = kg.get("entity_name", "")
                    ent_type = kg.get("entity_type", "")
                    ctx = kg.get("context", "")
                    confidence = kg.get("confidence", 0)
                    lines.append(f"- 🧩 {ent_name} [{ent_type}] (置信度: {confidence:.2f})")
                    # 子图上下文最多 150 字
                    if ctx:
                        lines.append(f"  {ctx[:150]}")

            context = "\n".join(lines)

            # 缓存（仅缓存记忆检索部分，task_state 每次实时拼接）
            with self._prefetch_lock:
                self._prefetched_context = context

            return context + self._get_task_state_injection()

        except Exception as e:
            logger.warning(f"Prefetch failed: {e}")
            return self._get_task_state_injection()

    def _get_task_state_injection(self) -> str:
        """获取 task_state 注入文本（按需注入）。

        注入策略：
          - 内容变化 → 注入（模型需要看到最新状态）
          - 内容没变 → 跳过（节省 token，避免重复注入加速上下文膨胀）
          - 首次 / 压缩后 session 切换 → 注入（on_session_switch 会 pop 缓存，
            新 session 首次调用时 last_text is None，自然触发注入）

        为什么走 prefetch() 而非 system_prompt_block()：
          Hermes 缓存 _cached_system_prompt（首轮构建、后续复用），
          system_prompt_block() 只在首轮被调用，task_state 无法每轮更新。
          prefetch() 每轮都调用，返回值通过 compose_user_api_content()
          拼到 API 侧 user 消息，不进 stored content。
        """
        if not self._initialized:
            return ""
        try:
            new_text = self._task_state.format_for_injection(self._session_id)
        except Exception as e:
            logger.debug(f"task_state injection failed: {e}")
            return ""

        # 内容为空 → 不注入，同时清理缓存（下次有内容时能触发注入）
        if not new_text:
            self._last_task_state_text.pop(self._session_id, None)
            return ""

        last_text = self._last_task_state_text.get(self._session_id)

        # 内容没变 → 跳过（节省 token）
        if new_text == last_text:
            logger.debug(
                f"task_state 未变化，跳过注入（session={str(self._session_id)[:8]}）"
            )
            return ""

        # 内容变了（或首次 / 压缩后 session 切换）→ 注入
        self._last_task_state_text[self._session_id] = new_text
        if len(self._last_task_state_text) > self._MAX_TASK_STATE_TEXT:
            overflow = len(self._last_task_state_text) - self._MAX_TASK_STATE_TEXT // 2
            for key in list(self._last_task_state_text.keys())[:overflow]:
                self._last_task_state_text.pop(key, None)
        return new_text
    
    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """后台预取下一轮"""
        if not self._initialized:
            return
        
        def _prefetch_task():
            try:
                self.prefetch(query, session_id=session_id)
            except Exception as e:
                logger.debug(f"Background prefetch error: {e}")
        
        go_safe("memory.prefetch", _prefetch_task)
    
    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        同步对话轮次

        每 N 轮（MEMORY_DELAY_ROUNDS，默认 10）异步提取记忆，
        提取时分析最近 N 轮对话作为上下文（窗口 = 触发间隔，无盲区）。
        每 10 轮触发 Dreaming 整合（去重/合并/晋升）。
        """
        if not self._initialized or not self._user_id:
            return

        try:
            from backend.service.memory import get_memory_service

            service = get_memory_service()

            # 处理轮次计数
            should_extract, round_count = service.process_round(
                thread_id=self._session_id,
                user_id=self._user_id,
                message=user_content
            )

            self._turn_counter = round_count

            # ── 每 N 轮异步提取（由 MEMORY_DELAY_ROUNDS 控制，默认 10 轮）──
            if should_extract:
                go_safe(
                    "memory.extract_per_turn",
                    lambda: self._extract_memories(
                        user_content,
                        assistant_content,
                        messages,
                        round_count=round_count
                    )
                )

            # ── Dreaming: 每 10 轮触发整合 ──
            if round_count > 0 and round_count % 10 == 0:
                go_safe(
                    "memory.dreaming",
                    lambda: self._run_dreaming()
                )

            # ── 传统合并：按计数器触发 ──
            if self._consolidator:
                self._consolidator.increment_count()
                if self._consolidator.need_consolidation():
                    go_safe(
                        "memory.consolidate",
                        lambda: self._run_consolidation()
                    )

        except Exception as e:
            logger.warning(f"Sync turn failed: {e}")
    
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        返回工具 schema。

        仅提供 memory_add 和 memory_stats。
        memory_recall 已移除 — 记忆检索由 prefetch() 在 Turn Prologue 阶段
        自动完成（意图驱动），无需模型额外发起工具调用。
        """
        return [
            {
                "name": "memory_add",
                "description": (
                    "主动添加一条长期记忆。"
                    "用于记录重要的用户偏好、事实或学到的技能。"
                    "只有重要信息才应该存储，避免冗余。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "记忆内容，简洁清晰"
                        },
                        "memory_type": {
                            "type": "string",
                            "enum": ["preference", "fact", "event", "skill"],
                            "description": (
                                "记忆类型："
                                "preference(偏好) - 用户的喜好和选择；"
                                "fact(事实) - 已确认的信息；"
                                "event(事件) - 重要的事件记录；"
                                "skill(技能) - 学习到的技能或方法"
                            )
                        },
                        "importance": {
                            "type": "number",
                            "description": "重要性分数 0-1，默认 0.5",
                            "default": 0.5
                        }
                    },
                    "required": ["content", "memory_type"]
                }
            },
            {
                "name": "memory_stats",
                "description": "获取当前用户的记忆统计信息",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        ]
    
    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        """处理工具调用（memory_recall 已移除，只保留 memory_add 和 memory_stats）"""
        if not self._initialized or not self._user_id:
            return json.dumps({"error": "Memory provider not initialized"})

        try:
            from backend.service.memory import get_memory_service

            service = get_memory_service()

            if tool_name == "memory_add":
                # LLM 主动添加的记忆也写入情景记忆层
                memory_id = service.create_episodic(
                    user_id=self._user_id,
                    memory_type=args.get("memory_type", "fact"),
                    content=args.get("content", ""),
                    importance_score=args.get("importance", 0.5),
                    source_thread_id=self._session_id
                )

                if memory_id:
                    # 尝试获取 embedding，用于图 SIMILAR_TO 边建立
                    embedding = None
                    try:
                        embeddings = service._get_embeddings([args.get("content", "")])
                        if embeddings:
                            embedding = embeddings[0]
                    except Exception as e:
                        logger.debug(f"Failed to get embedding for graph: {e}")

                    # 更新缓存
                    item = MemoryItem(
                        id=memory_id,
                        content=args.get("content", ""),
                        importance=args.get("importance", 0.5),
                        category=args.get("memory_type", "fact"),
                        embedding=embedding,  # 传入 embedding 以启用 SIMILAR_TO 边
                        user_id=self._user_id,
                        layer="episodic",  # memory_add 工具创建的是 episodic 层记忆
                    )
                    with self._memory_lock:
                        self._memory_items.append(item)
                        if len(self._memory_items) > self._MAX_MEMORY_ITEMS:
                            self._memory_items = self._memory_items[-self._MAX_MEMORY_ITEMS:]

                    # 图增强（异步，有 embedding 才能建立 SIMILAR_TO 边）
                    if self._graph_memory:
                        with self._memory_lock:
                            neighbors = list(self._memory_items[-50:])  # 最近 50 条（锁内拷贝）
                        go_safe(
                            "memory.graph_add",
                            lambda: self._graph_memory.add_to_graph(
                                item, neighbors, user_id=self._user_id
                            )
                        )

                    # 发布事件
                    publish_event_safe("memory.added", {
                        "user_id": self._user_id,
                        "memory_id": memory_id,
                        "type": args.get("memory_type", "fact")
                    })

                    return json.dumps({
                        "success": True,
                        "memory_id": memory_id,
                        "message": "记忆已存储"
                    }, ensure_ascii=False)
                else:
                    return json.dumps({
                        "success": False,
                        "error": "存储失败"
                    }, ensure_ascii=False)

            elif tool_name == "memory_stats":
                stats = service.get_memory_stats(self._user_id)
                return json.dumps({
                    "success": True,
                    "stats": stats
                }, ensure_ascii=False)

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    def shutdown(self) -> None:
        """关闭"""
        self._executor.shutdown(wait=False)
        
        # 关闭图增强层
        if self._graph_memory:
            try:
                self._graph_memory.close()
            except Exception:
                pass
        
        self._initialized = False
        logger.info("AgentForgeMemoryProvider shutdown")
    
    def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None:
        """轮次开始钩子。

        注意：Hermes 的 on_turn_start 只传 (turn_number, message)，不传 messages 列表，
        因此 provider 在这里拿不到 assistant content。task_state 的更新改由
        hermes_adapter.run() 在 run_conversation 完成后异步提交。
        """
        self._turn_counter = turn_number
    
    def on_delegation(
        self,
        task: str,
        result: str,
        *,
        child_session_id: str = "",
        **kwargs,
    ) -> None:
        """父侧观察钩子：子 Agent 完成后由 Hermes 的 delegate_task 调用。

        此前本 provider 没有实现这个方法，AttributeError 被 MemoryManager 的
        try/except 吞成 debug 日志——父侧对"派了什么/回来什么"一无所知。
        这里做两件事：
          1. 把产出回填到 delegation_tasks 留痕（按 child_session_id 定位那一行）
          2. 记一条 info 日志，便于排查"结果回没回来"
        注意：不在这里写长期记忆——子 Agent 的产出质量参差，直接沉淀会污染
        三层记忆；需要沉淀时走 Supervisor 的常规记忆提取链路。
        """
        try:
            logger.info(
                "子 Agent 完成观察: child_session=%s task=%s result_len=%s",
                child_session_id or "-",
                (task or "")[:80],
                len(result or ""),
            )
        except Exception:
            pass

        if not child_session_id:
            return
        try:
            from backend.service.delegation import store as _delegation_store

            _delegation_store.attach_result_by_child_session(
                child_session_id=child_session_id,
                summary=result or "",
            )
        except Exception as e:
            logger.debug("on_delegation 留痕失败（已忽略）: %s", e)

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """会话结束钩子 - 可选的最终提取

        注意：task_state 不在这里清理。
        task_state 跟着会话历史走（state.db），前端删除会话时由
        delete_hermes_session_history() 顺手清理 task_states 表。
        AgentForge Web 前端路径（/chat/stream）不会触发此钩子
        （仅 Hermes CLI/gateway 会话过期时触发），所以也不应该在这里做清理。
        """
        if not self._initialized or not self._user_id:
            return

        if len(messages) < 3:
            return

        go_safe(
            "memory.session_extract",
            lambda: self._extract_memories_from_session(messages)
        )

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        rewound: bool = False,
        **kwargs,
    ) -> None:
        """会话切换钩子

        注意：task_state 不在这里清理。
        会话切换只是用户暂时离开，还会回来，task_state 应该保留。
        task_state 仅在前端删除会话时（delete_hermes_session_history）清理。
        """
        # 清理旧 session 的 task_state 注入缓存（新 session 首次注入必须生效）
        # 新 session_id 的缓存也清一下，避免残留
        old_session_id = self._session_id
        if old_session_id:
            self._last_task_state_text.pop(old_session_id, None)
        self._last_task_state_text.pop(new_session_id, None)

        self._session_id = new_session_id

        if reset:
            self._turn_counter = 0
            self._prefetched_context = ""

        logger.debug(
            f"Session switch: {old_session_id} -> {new_session_id} "
            f"(reset={reset}, rewound={rewound})"
        )
    
    # ========== 增强功能 ==========
    
    def _load_memories_to_cache(self) -> None:
        """加载用户记忆到内存缓存（episodic + semantic 层）"""
        if not self._user_id:
            return

        try:
            from backend.db.memory_mapper import get_episodic_mapper, get_semantic_mapper

            items = []
            for layer_name, mapper in (("episodic", get_episodic_mapper()),
                                       ("semantic", get_semantic_mapper())):
                try:
                    memories = mapper.get_memories_by_user(
                        user_id=self._user_id,
                        limit=1000
                    )
                    for m in memories:
                        # MySQL DATETIME → float 时间戳（MemoryItem 类型契约要求 float）
                        created_at = m.get("created_at")
                        if isinstance(created_at, datetime):
                            created_at = created_at.timestamp()
                        elif created_at is None:
                            created_at = time.time()
                        else:
                            created_at = float(created_at)

                        last_accessed = m.get("last_accessed")
                        if isinstance(last_accessed, datetime):
                            last_accessed = last_accessed.timestamp()
                        elif last_accessed is None:
                            last_accessed = time.time()
                        else:
                            last_accessed = float(last_accessed)

                        items.append(MemoryItem(
                            id=m.get("id"),
                            content=m.get("content", ""),
                            importance=m.get("importance_score", 0.5),
                            embedding=m.get("embedding"),
                            created_at=created_at,
                            last_accessed=last_accessed,
                            category=m.get("memory_type", "general"),
                            tags=m.get("tags", []),
                            user_id=self._user_id,
                            layer=layer_name,
                            access_count=m.get("access_count", 0),
                            is_user_pinned=bool(m.get("is_user_pinned", 0)),
                        ))
                except Exception as e:
                    logger.debug(f"Cache load layer query failed: {e}")

            with self._memory_lock:
                self._memory_items = items

            logger.debug(f"Loaded {len(items)} memories to cache (episodic + semantic)")

            # 同步图 prev_id
            if self._graph_memory and items:
                try:
                    self._graph_memory.sync_prev_id(user_id=self._user_id)
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"Failed to load memories to cache: {e}")
    
    def _get_memory_by_id(self, memory_id: int) -> Optional[dict]:
        """根据 ID 获取记忆（限定当前用户）"""
        # 先从缓存查找
        with self._memory_lock:
            for item in self._memory_items:
                if item.id == memory_id and item.user_id == self._user_id:
                    return item.to_dict()

        # 缓存未命中，从 episodic → semantic 查找（带 user_id 过滤）
        try:
            from backend.db.memory_mapper import get_episodic_mapper, get_semantic_mapper
            for _layer, mapper in (("episodic", get_episodic_mapper()),
                                   ("semantic", get_semantic_mapper())):
                row = mapper.get_memory_by_id(memory_id, user_id=self._user_id)
                if row and not row.get("deleted_at"):
                    item = MemoryItem(
                        id=row.get("id"),
                        content=row.get("content", ""),
                        importance=row.get("importance_score", 0.5),
                        embedding=row.get("embedding"),
                        created_at=row.get("created_at", time.time()),
                        last_accessed=row.get("last_accessed", time.time()),
                        category=row.get("memory_type", "general"),
                        tags=row.get("tags", []),
                        user_id=row.get("user_id", self._user_id),
                        access_count=row.get("access_count", 0),
                        is_user_pinned=bool(row.get("is_user_pinned", 0)),
                        graph_node_id=row.get("graph_node_id"),
                        # ⚠️ 层级必须带上：图谱 Memory 节点身份是 "{layer}:{id}"，
                        # 两张表的 id 会重号，缺了它就可能定位到另一层的同号记忆
                        layer=_layer,
                    )
                    return item.to_dict()
        except Exception as e:
            logger.warning(f"Failed to get memory {memory_id} from DB: {e}")
        return None
    
    def _run_consolidation(self) -> ConsolidationResult:
        """执行合并"""
        if not self._consolidator:
            return ConsolidationResult()

        with self._memory_lock:
            result = self._consolidator.consolidate(self._memory_items)

        # 同步到数据库
        if result.delete_targets:
            self._sync_deletions(result.delete_targets)
        elif result.delete_from_db:                     # 兼容：老结构没带层级时走原逻辑
            self._sync_deletions([(mid, None) for mid in result.delete_from_db])

        if result.update_in_db:
            self._sync_updates(result.update_in_db)

        # 持久化旧版本快照（合并/去重前的历史）
        if result.versions_to_save:
            self._sync_versions(result.versions_to_save)

        # 发布事件
        publish_event_safe("memory.consolidated", result.to_dict())

        return result

    def _run_dreaming(self) -> None:
        """
        Dreaming 机制：每 10 轮触发的记忆整合

        功能：
        1. 获取 Episodic + Semantic 记忆
        2. 使用 LLM 分析矛盾、重复、合并候选
        3. 清理低质量或矛盾的记忆

        注意：晋升逻辑已移至检索命中时异步检查（_try_auto_promote_episodic）
              不再在 Dreaming 中晋升，避免逻辑冗余

        这是异步执行的，通过 go_safe 调用
        """
        if not self._initialized or not self._user_id:
            return

        try:
            from backend.service.memory import get_memory_service
            from backend.utils.traced_llm import traced_llm

            service = get_memory_service()

            # ── 1. 获取 Episodic + Semantic 记忆 ──
            episodic_memories = service._episodic_mapper.get_memories_by_user(
                user_id=self._user_id,
                limit=100
            )
            semantic_memories = service._semantic_mapper.get_memories_by_user(
                user_id=self._user_id,
                limit=100
            )

            if not episodic_memories and not semantic_memories:
                logger.debug("Dreaming: No memories to consolidate")
                return

            # ── 2. 构建分析上下文（标记来源层，解密内容）──
            from backend.utils.crypto_utils import decrypt_memory_content

            memory_list = []
            # Episodic 记忆（可晋升）
            for mem in episodic_memories[:50]:
                raw_content = mem["content"] or ""
                decrypted_content = decrypt_memory_content(raw_content)
                memory_list.append({
                    "id": mem["id"],
                    "layer": "episodic",
                    "type": mem["memory_type"],
                    "content": decrypted_content[:200],
                    "importance": mem.get("importance_score", 0.5),
                    "created_at": str(mem.get("created_at", "")),
                    "access_count": mem.get("access_count", 0)
                })
            # Semantic 记忆（可去重/合并，不可再晋升）
            for mem in semantic_memories[:30]:
                raw_content = mem["content"] or ""
                decrypted_content = decrypt_memory_content(raw_content)
                memory_list.append({
                    "id": mem["id"],
                    "layer": "semantic",
                    "type": mem["memory_type"],
                    "content": decrypted_content[:200],
                    "importance": mem.get("importance_score", 0.5),
                    "created_at": str(mem.get("created_at", "")),
                    "access_count": mem.get("access_count", 0)
                })

            memories_json = json.dumps(memory_list, ensure_ascii=False, default=str)

            prompt = f"""你是一个记忆整合助手。分析以下记忆（含近期记忆 Episodic 和永久记忆 Semantic），执行整合操作。

【当前记忆列表】
{memories_json}

【任务】
分析这些记忆，返回整合建议的 JSON 对象：

1. **矛盾检测**: 找出相互矛盾的记忆（例如："用户喜欢 Java" vs "用户只用 Python"）
   - 保留更新的一条，标记旧的为矛盾
   - 可以跨层检测（Episodic 与 Semantic 之间的矛盾）

2. **重复检测**: 找出语义相似的记忆（相似度 > 0.85）
   - 合并为一条，保留更高的 importance
   - 可以跨层检测（Episodic 与 Semantic 之间的重复）

3. **清理建议**: 找出 importance < 0.2 且从未被访问的记忆
   - 建议删除

【返回格式】
```json
{{
  "contradictions": [
    {{"keep_id": 1, "remove_id": 2, "reason": "记忆 2 与记忆 1 矛盾"}}
  ],
  "duplicates": [
    {{"keep_id": 1, "remove_id": 2, "merged_content": "合并后的内容"}}
  ],
  "delete_low_quality": [3, 7]
}}
```

如果没有需要处理的，返回空对象 {{}}。
只返回 JSON，不要其他文字。"""

            # ── 3. 调用 LLM 分析 ──
            try:
                resp = traced_llm.invoke(
                    messages=[{"role": "user", "content": prompt}],
                    scene="memory_dreaming",
                    user_id=self._user_id,
                    source="memory_dream",
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )
                content = (resp.content or "").strip()
                suggestions = json.loads(content) if content else {}
            except Exception as e:
                logger.warning(f"Dreaming: LLM analysis failed: {e}")
                suggestions = {}

            # ── 4. 执行整合操作 ──
            # 安全护栏：限制单次 Dreaming 的破坏性操作数量
            MAX_DELETES_PER_DREAM = 5

            deleted_count = 0
            merged_count = 0

            # 4.1 处理矛盾（删除旧的）
            contradictions = suggestions.get("contradictions", [])
            for contradiction in contradictions[:MAX_DELETES_PER_DREAM]:
                remove_id = contradiction.get("remove_id")
                if remove_id:
                    try:
                        service.delete_memory(remove_id, user_id=self._user_id)
                        deleted_count += 1
                        logger.info(f"Dreaming: Removed contradicted memory {remove_id}")
                    except Exception as e:
                        logger.warning(f"Dreaming: Failed to remove {remove_id}: {e}")

            # 4.2 处理重复（合并）
            for duplicate in suggestions.get("duplicates", []):
                keep_id = duplicate.get("keep_id")
                remove_id = duplicate.get("remove_id")
                merged_content = duplicate.get("merged_content")
                if keep_id and remove_id and merged_content:
                    try:
                        # 更新保留的记忆内容
                        service.update_memory(
                            memory_id=keep_id,
                            content=merged_content,
                            user_id=self._user_id
                        )
                        # 删除重复的
                        service.delete_memory(remove_id, user_id=self._user_id)
                        merged_count += 1
                        logger.info(f"Dreaming: Merged memory {remove_id} into {keep_id}")
                    except Exception as e:
                        logger.warning(f"Dreaming: Failed to merge: {e}")

            # 4.3 清理低质量记忆（受 MAX_DELETES_PER_DREAM 限制）
            low_quality = suggestions.get("delete_low_quality", [])
            remaining_deletions = MAX_DELETES_PER_DREAM - deleted_count
            for memory_id in low_quality[:max(0, remaining_deletions)]:
                try:
                    service.delete_memory(memory_id, user_id=self._user_id)
                    deleted_count += 1
                    logger.info(f"Dreaming: Deleted low-quality memory {memory_id}")
                except Exception as e:
                    logger.warning(f"Dreaming: Failed to delete {memory_id}: {e}")

            # ── 5. 输出统计 ──
            total_episodic = len(episodic_memories)
            total_semantic = len(semantic_memories)
            total_memories = total_episodic + total_semantic
            logger.info(
                f"Dreaming complete: "
                f"analyzed {total_memories} memories "
                f"(episodic={total_episodic}, semantic={total_semantic}), "
                f"merged {merged_count}, deleted {deleted_count}"
            )

            # 发布事件
            publish_event_safe("memory.dreaming_complete", {
                "user_id": self._user_id,
                "analyzed": total_memories,
                "episodic": total_episodic,
                "semantic": total_semantic,
                "merged": merged_count,
                "deleted": deleted_count
            })

        except Exception as e:
            logger.warning(f"Dreaming failed: {e}")
    
    def _sync_deletions(self, targets: List[Tuple[int, Optional[str]]]) -> None:
        """同步删除到数据库。

        Args:
            targets: (memory_id, layer) 元组列表。layer 为 None 时由服务层推断。
        """
        try:
            from backend.service.memory import get_memory_service
            service = get_memory_service()
            for mid, layer in targets:
                try:
                    service.delete_memory(mid, user_id=self._user_id, layer=layer)
                except Exception as e:
                    logger.warning(f"Failed to delete memory {mid}: {e}")
        except Exception as e:
            logger.warning(f"Sync deletions failed: {e}")
    
    def _sync_updates(self, items: List[MemoryItem]) -> None:
        """同步更新到数据库"""
        try:
            from backend.service.memory import get_memory_service
            service = get_memory_service()
            for item in items:
                if item.id:
                    try:
                        # 更新内容和重要性，传递 layer 避免删错层
                        service.update_memory(
                            memory_id=item.id,
                            content=item.content,
                            importance_score=item.importance,
                            user_id=self._user_id,
                            layer=getattr(item, "layer", None),
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update memory {item.id}: {e}")
        except Exception as e:
            logger.warning(f"Sync updates failed: {e}")

    def _sync_versions(self, versions: List[dict]) -> None:
        """持久化旧版本快照到 memory_versions 表"""
        try:
            from backend.db.memory_mapper import get_memory_versions_mapper
            mapper = get_memory_versions_mapper()
            count = mapper.batch_insert_memory_versions(versions)
            logger.debug(f"Saved {count} memory version snapshots")
        except Exception as e:
            logger.warning(f"Sync versions failed: {e}")

    # ========== 私有方法 ==========

    def _extract_memories(
        self,
        user_content: str,
        assistant_content: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        *,
        round_count: int = 0
    ) -> None:
        """从 task_state 的 cross_session_signals 提取长期记忆。

        不再解析原始对话消息——cross_session_signals 已由 task_state 每轮维护，
        是去噪后的跨会话信息，输入 token 开销从 ~10000 降到几百。
        """
        try:
            from backend.service.memory import get_memory_service

            service = get_memory_service()

            # ── 从 task_state 读取 cross_session_signals ──
            signals = self._task_state.get_cross_session_signals(self._session_id)

            if not signals:
                logger.info(f"Turn {round_count}: cross_session_signals 为空，跳过记忆提取")
                return

            # ── 构建提取 prompt ──
            signals_text = "\n".join(f"- {s}" for s in signals)

            prompt = f"""分析以下从对话中提取的跨会话信号，判断哪些值得作为长期记忆保存。

【跨会话信号】（由 task_state 每轮维护）
{signals_text}

【提取规则】
- preference：用户偏好（"用户偏好 Python"、"喜欢简洁的代码风格"）
- fact：稳定事实（"用户负责订单系统"、"数据库用 MySQL 8"）
- event：重要事件（"用户上线了 XX 项目"、"用户转岗到 YY 团队"）
- skill：学到的技能/方法（"CI/CD 用 GitHub Actions"）

【禁止提取】
- 当前任务的临时信息（订单号、临时参数等）
- 已经在记忆库中存在的信息

【返回格式】JSON 数组，每项包含：
- type: preference/fact/event/skill
- content: 简洁的记忆内容（一句话）
- importance: 0-1 的重要性分数

如果没有值得记住的，返回空数组 []。
只返回 JSON，不要其他文字。"""

            # ── 结构化输出 ──
            memories = self._invoke_structured_extraction(prompt)

            if not memories:
                logger.info(f"Turn {round_count}: LLM returned empty extraction (no memories)")
                # 提取成功但没值得保留的 → 也清（避免下周期重新审视同一批 signals）
                self._task_state.clear_cross_session_signals(self._session_id)
                return

            created_count = 0
            for mem in memories:
                mem_type = mem.get("type", "fact")
                mem_content = mem.get("content", "")
                importance = mem.get("importance", 0.5)

                if not mem_content or mem_type not in ["preference", "fact", "event", "skill"]:
                    continue

                # cross_session_signals 本身就是跨会话信息 → 全部走 semantic（永久记忆）
                memory_id = service.create_semantic(
                    user_id=self._user_id,
                    memory_type=mem_type,
                    content=mem_content,
                    importance_score=importance,
                    source_thread_id=self._session_id,
                    source_round=round_count
                )

                if memory_id:
                    created_count += 1
                    # 通知合并器（用于三阶段合并调度）
                    if self._consolidator:
                        self._consolidator.increment_count()

                    # 更新内存缓存（Outbox 已处理向量+图谱写入）
                    item = MemoryItem(
                        id=memory_id,
                        content=mem_content,
                        importance=importance,
                        category=mem_type,
                        user_id=self._user_id,
                        layer="semantic",
                    )
                    with self._memory_lock:
                        self._memory_items.append(item)
                        if len(self._memory_items) > self._MAX_MEMORY_ITEMS:
                            self._memory_items = self._memory_items[-self._MAX_MEMORY_ITEMS:]

                    logger.debug(
                        f"Extracted memory from cross_session_signals (round {round_count}): "
                        f"type={mem_type}, importance={importance:.2f}, content={mem_content[:50]}"
                    )

            if created_count > 0:
                logger.info(f"Turn {round_count}: 从 cross_session_signals 提取 {created_count} 条永久记忆")

            # 提取成功 → 清空 signals，避免下一周期重复提取同一批
            self._task_state.clear_cross_session_signals(self._session_id)

        except Exception as e:
            logger.warning(f"Memory extraction failed (round {round_count}): {e}")

    def _invoke_structured_extraction(
        self, prompt: str
    ) -> List[Dict[str, Any]]:
        """
        结构化调用 LLM 提取记忆（使用 TracedLLMClient，自动记录 trace）。

        优先使用 response_format=json_object 模式（大多数 OpenAI 兼容 API 支持），
        失败时降级为手动 JSON 解析。
        """
        from backend.utils.traced_llm import traced_llm

        # ── 尝试 1：json_object 模式 ──
        content = ""
        try:
            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="memory_extract",
                user_id=self._user_id,
                source="memory",
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            content = (resp.content or "").strip()
            if content:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    return parsed
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logger.warning(f"Structured extraction JSON parse failed: {e}, content={content[:200] if content else 'empty'}")
        except Exception as e:
            logger.warning(f"Structured extraction (json_object) failed: {e}")

        # ── 尝试 2：普通调用 + 手动解析 ──
        try:
            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="memory_extract",
                user_id=self._user_id,
                source="memory",
                temperature=0.3,
            )
            content = (resp.content or "").strip()

            # 尝试提取 JSON 数组
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                parsed = json.loads(content[start:end])
                if isinstance(parsed, list):
                    return parsed
            else:
                logger.warning(f"No JSON array found in extraction response")
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logger.warning(f"Fallback JSON parse failed: {e}")
        except Exception as e:
            logger.warning(f"Fallback extraction failed: {e}")

        return []
    
    def _extract_memories_from_session(
        self,
        messages: List[Dict[str, Any]]
    ) -> None:
        """从完整会话提取记忆"""
        if len(messages) < 3:
            return
        
        user_msg = ""
        asst_msg = ""
        
        for msg in reversed(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "user" and not user_msg:
                user_msg = content
            elif role == "assistant" and not asst_msg:
                asst_msg = content
            
            if user_msg and asst_msg:
                break
        
        if user_msg and asst_msg:
            self._extract_memories(user_msg, asst_msg, messages)


__all__ = ["AgentForgeMemoryProvider"]