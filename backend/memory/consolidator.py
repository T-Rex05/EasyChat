"""
Memory Consolidator - 三阶段记忆合并器

对齐 AGI-saber 的 LongTerm.consolidate 实现：

阶段 1: 衰减 - 按每条记忆的 created_at 单独计算
    importance *= decay_rate ** days

阶段 2: 去重/合并 - 两两比对
    sim >= 0.95: 去重（保留 i，删除 j，吸收属性）
    0.85 <= sim < 0.95: 合并（合成新条目替换 i，删除 j）

阶段 3: 双条件淘汰
    days > ttl_days AND importance < min_importance

+ 图中心度保护：入度 >= threshold 的节点豁免删除
"""

import logging
import math
import os
import re
import threading
import time
from collections import Counter
from typing import List, Optional, Any

from backend.memory.types import MemoryItem, ConsolidationResult
from backend.memory.graph_memory import GraphMemory, get_graph_memory
from backend.infrastructure.safe_executor import go_safe

logger = logging.getLogger(__name__)


def _tokenize_zh(text: str) -> List[str]:
    """
    中英文混合分词：中文按字、英文/数字按词
    
    用于 TF 词袋相似度计算（embedding 缺失时的降级方案）
    """
    tokens: List[str] = []
    word = ""
    for ch in text:
        cp = ord(ch)
        # 中文字符
        if 0x4E00 <= cp <= 0x9FFF:
            if word:
                tokens.append(word.lower())
                word = ""
            tokens.append(ch)
        # 英文/数字
        elif ch.isalnum():
            word += ch
        else:
            if word:
                tokens.append(word.lower())
                word = ""
    if word:
        tokens.append(word.lower())
    return tokens


class MemoryConsolidator:
    """
    三阶段记忆合并器
    
    只改内存，不写 DB（持久化由调用方处理）
    返回 ConsolidationResult，告知需要删除/更新的 ID
    """
    
    def __init__(
        self,
        decay_rate: float = 0.99,
        dedup_threshold: float = 0.95,
        merge_threshold: float = 0.85,
        ttl_days: int = 30,
        min_importance: float = 0.1,
        trigger_threshold: int = 10,
        indegree_protect: int = 3,
        # 多因子公式参数
        access_weight: float = 1.0,
        recency_halflife_days: float = 14.0,
        pin_boost: float = 2.0,
    ):
        """
        初始化合并器

        Args:
            decay_rate: 衰减率（每天）
            dedup_threshold: 去重阈值（>= 此值视为重复）
            merge_threshold: 合并阈值（>= 此值但 < dedup_threshold 触发合并）
            ttl_days: 生存期（天），超过此天数且 importance < min_importance 则淘汰
            min_importance: 最低重要性阈值
            trigger_threshold: 触发阈值（新增多少条后触发合并）
            indegree_protect: 图中心度保护阈值（入度 >= 此值免于删除）
            access_weight: 访问频率加成权重（0=禁用，越大访问多的记忆越难衰减）
            recency_halflife_days: 最近访问衰减半衰期（天）
            pin_boost: 用户锁定记忆的分数倍率（>1 表示保护）
        """
        # 合并配置
        self._decay_rate = decay_rate
        self._dedup_threshold = dedup_threshold
        self._merge_threshold = merge_threshold
        self._ttl_days = ttl_days
        self._min_importance = min_importance
        self._trigger_threshold = trigger_threshold
        self._indegree_protect = indegree_protect

        # 多因子公式参数
        self._access_weight = access_weight
        self._recency_halflife_days = max(0.1, recency_halflife_days)
        self._pin_boost = pin_boost
        
        # 图增强层
        self._graph_memory: Optional[GraphMemory] = None
        
        # 计数器
        self._items_since_last = 0
        self._lock = threading.RLock()
    
    def set_graph_memory(self, gm: Optional[GraphMemory]) -> None:
        """注入图增强层"""
        self._graph_memory = gm
    
    def set_consolidation_config(self, config: Any) -> None:
        """
        更新合并配置
        
        Args:
            config: 需具备相关属性的对象（duck typing）
        """
        if config is None:
            return
        with self._lock:
            if hasattr(config, 'memory_consolidation_decay_rate'):
                self._decay_rate = float(config.memory_consolidation_decay_rate or 0.99)
            if hasattr(config, 'memory_consolidation_dedup'):
                self._dedup_threshold = float(config.memory_consolidation_dedup or 0.95)
            if hasattr(config, 'memory_consolidation_similarity'):
                self._merge_threshold = float(config.memory_consolidation_similarity or 0.85)
            if hasattr(config, 'memory_consolidation_ttl_days'):
                self._ttl_days = int(config.memory_consolidation_ttl_days or 30)
            if hasattr(config, 'memory_consolidation_min_import'):
                self._min_importance = float(config.memory_consolidation_min_import or 0.1)
            if hasattr(config, 'memory_consolidation_trigger'):
                self._trigger_threshold = int(config.memory_consolidation_trigger or 10)
            if hasattr(config, 'graph_protect_indegree'):
                self._indegree_protect = int(config.graph_protect_indegree or 3)
            # 多因子公式参数
            if hasattr(config, 'memory_consolidation_access_weight'):
                self._access_weight = float(config.memory_consolidation_access_weight or 1.0)
            if hasattr(config, 'memory_consolidation_recency_halflife'):
                self._recency_halflife_days = float(config.memory_consolidation_recency_halflife or 14.0)
            if hasattr(config, 'memory_consolidation_pin_boost'):
                self._pin_boost = float(config.memory_consolidation_pin_boost or 2.0)
    
    def increment_count(self, count: int = 1) -> None:
        """增加计数器（新增记忆时调用）"""
        with self._lock:
            self._items_since_last += count
    
    def need_consolidation(self) -> bool:
        """检查是否需要触发合并"""
        with self._lock:
            return self._items_since_last >= max(1, self._trigger_threshold)
    
    def consolidate(self, items: List[MemoryItem]) -> ConsolidationResult:
        """
        执行三阶段合并
        
        Args:
            items: 内存中的记忆列表（会被修改）
            
        Returns:
            ConsolidationResult（告知需要删除/更新的 ID）
        """
        result = ConsolidationResult()
        
        with self._lock:
            if len(items) <= 1:
                return result
            
            self._items_since_last = 0
            now = time.time()
            
            # ========== 阶段 1：多因子衰减 ==========
            # score = base_importance
            #         * decay_rate ^ days                     (时间衰减)
            #         * (1 + w * log(1 + access_count))      (访问频率加成)
            #         * 0.5 ^ (days_since_access / halflife)  (最近访问衰减)
            #         * pin_boost (if pinned)                 (用户锁定保护)
            _recency_decay_base = 0.5
            _halflife = self._recency_halflife_days
            _access_w = self._access_weight
            _pin = self._pin_boost

            for item in items:
                days = max(0.0, (now - item.created_at) / 86400.0)

                # 因子 1: 时间衰减（原有逻辑）
                time_decay = self._decay_rate ** days

                # 因子 2: 访问频率加成（log 归一化，避免高频访问过度膨胀）
                access_factor = 1.0 + _access_w * math.log(1 + item.access_count)

                # 因子 3: 最近访问衰减（指数衰减，半衰期可配置）
                days_since_access = max(0.0, (now - item.last_accessed) / 86400.0)
                recency_factor = _recency_decay_base ** (days_since_access / _halflife)

                # 因子 4: 用户锁定保护
                pin_factor = _pin if item.is_user_pinned else 1.0

                # 综合计算
                item.importance *= time_decay * access_factor * recency_factor * pin_factor

                # 防止 importance 超过 1.0
                if item.importance > 1.0:
                    item.importance = 1.0
            
            # ========== 阶段 2：去重/合并 ==========
            removed = [False] * len(items)

            for i in range(len(items)):
                if removed[i]:
                    continue
                for j in range(i + 1, len(items)):
                    if removed[j]:
                        continue

                    item_i = items[i]
                    item_j = items[j]

                    sim = self._compute_similarity(item_i, item_j)

                    if sim >= self._dedup_threshold:
                        # 去重：保留 i，删除 j；i 吸收 j 的属性
                        # → 将被删除的 j 写入版本历史
                        if item_j.id is not None:
                            result.versions_to_save.append({
                                "memory_id": item_j.id,
                                "version": getattr(item_j, '_db_version', 1),
                                "content": item_j.content,
                                "importance_score": item_j.importance,
                                "memory_type": item_j.category,
                                "change_reason": "dedup",
                                "source_memory_id": item_i.id,
                            })
                        item_i.importance = max(item_i.importance, item_j.importance)
                        item_i.tags = list(dict.fromkeys(item_i.tags + item_j.tags))
                        item_i.last_accessed = now
                        removed[j] = True
                        result.deduped += 1
                        if item_j.id is not None:
                            result.delete_from_db.append(item_j.id)
                            result.delete_targets.append((item_j.id, getattr(item_j, "layer", None)))

                    elif sim >= self._merge_threshold:
                        # 合并前：记录 i 和 j 的旧版本快照
                        if item_i.id is not None:
                            result.versions_to_save.append({
                                "memory_id": item_i.id,
                                "version": getattr(item_i, '_db_version', 1),
                                "content": item_i.content,
                                "importance_score": item_i.importance,
                                "memory_type": item_i.category,
                                "change_reason": "merge",
                                "source_memory_id": item_j.id,
                            })
                        if item_j.id is not None:
                            result.versions_to_save.append({
                                "memory_id": item_j.id,
                                "version": getattr(item_j, '_db_version', 1),
                                "content": item_j.content,
                                "importance_score": item_j.importance,
                                "memory_type": item_j.category,
                                "change_reason": "merge",
                                "source_memory_id": item_i.id,
                            })
                        # 合并：合成新条目替换 i，删除 j
                        merged = self._merge_pair(item_i, item_j, now)
                        items[i] = merged
                        removed[j] = True
                        result.merged += 1
                        if item_j.id is not None:
                            result.delete_from_db.append(item_j.id)
                            result.delete_targets.append((item_j.id, getattr(item_j, "layer", None)))
                        result.update_in_db.append(merged)
            
            # ========== 阶段 3：双条件淘汰（锁定记忆豁免）==========
            for idx in range(len(items)):
                if removed[idx]:
                    continue
                item = items[idx]

                # 用户锁定的记忆不参与自动淘汰
                if item.is_user_pinned:
                    continue

                days = max(0.0, (now - item.created_at) / 86400.0)

                if self._ttl_days > 0 and days > self._ttl_days and item.importance < self._min_importance:
                    removed[idx] = True
                    result.expired += 1
                    if item.id is not None:
                        result.delete_from_db.append(item.id)
                        result.delete_targets.append((item.id, getattr(item, "layer", None)))
            
            # 更新剩余数量
            result.remaining = len([m for i, m in enumerate(items) if not removed[i]])

            # ========== 处理矛盾合并中被覆盖的旧版本 ==========
            for idx, item in enumerate(items):
                if not removed[idx] and hasattr(item, '_source_deleted_id'):
                    deleted_id = getattr(item, '_source_deleted_id')
                    if deleted_id is not None and deleted_id not in result.delete_from_db:
                        result.delete_from_db.append(deleted_id)
                        # layer 必须取**被覆盖方**的，而不是合并项（幸存方）的：
                        # 见 _merge_pair 里 _source_deleted_layer 的说明。
                        result.delete_targets.append((
                            deleted_id,
                            getattr(item, "_source_deleted_layer", None)
                            if hasattr(item, "_source_deleted_layer")
                            else getattr(item, "layer", None),
                        ))
                    delattr(item, '_source_deleted_id')
                    if hasattr(item, "_source_deleted_layer"):
                        delattr(item, '_source_deleted_layer')
            
            # ========== 图中心度保护 ==========
            if self._graph_memory and result.delete_from_db:
                try:
                    protected = self._graph_memory.filter_protected(result.delete_from_db)
                    if protected:
                        protected_set = set(protected)
                        before = len(result.delete_from_db)
                        result.delete_from_db = [
                            rid for rid in result.delete_from_db
                            if rid not in protected_set
                        ]
                        # 同步过滤 delete_targets，保持两个字段一致
                        result.delete_targets = [
                            (mid, layer) for (mid, layer) in result.delete_targets
                            if mid not in protected_set
                        ]
                        logger.info(
                            f"Graph indegree protect: {before - len(result.delete_from_db)} "
                            f"memories spared from deletion (indegree >= {self._indegree_protect})"
                        )
                        # Sync removed array - restore protected items
                        for idx, item in enumerate(items):
                            if removed[idx] and item.id in protected_set:
                                removed[idx] = False
                except Exception as e:
                    logger.warning(f"filter_protected failed: {e}")
            
            # ========== 同步删除图节点 ==========
            if self._graph_memory and result.delete_from_db:
                # 用 delete_targets（带 (memory_id, layer)）而不是 delete_from_db（裸 id）：
                # episodic/semantic 两张表的 id 会重号，按裸 id 删会连**另一层的同号节点**
                # 一起 DETACH DELETE 掉。上面的中心度保护已同步过滤过两者，保持一致。
                _targets = result.delete_targets or [(rid, None) for rid in result.delete_from_db]
                for rid, _lyr in _targets:
                    try:
                        self._graph_memory.delete_from_graph(rid, layer=_lyr)
                    except Exception as e:
                        logger.warning(f"delete_from_graph failed: {e}")
            
            # ========== 更新图节点 ==========
            if self._graph_memory:
                for idx, item in enumerate(items):
                    if not removed[idx]:
                        try:
                            self._graph_memory.update_node(item)
                        except Exception as e:
                            logger.debug(f"update_node failed: {e}")
            
            logger.info(
                f"✅ Memory consolidation completed: "
                f"deduped={result.deduped}, merged={result.merged}, expired={result.expired}, "
                f"remaining={result.remaining}"
            )
        
        return result
    
    def consolidate_async(self, items: List[MemoryItem]) -> None:
        """
        异步执行合并（不阻塞主路径）

        Args:
            items: 内存中的记忆列表
        """
        items_copy = list(items)  # 拷贝列表，防止后台线程与主线程共享引用
        def _consolidate():
            self.consolidate(items_copy)

        go_safe("memory.consolidate", _consolidate)
    
    def _compute_similarity(self, a: MemoryItem, b: MemoryItem) -> float:
        """
        计算相似度
        
        优先使用 embedding 余弦，否则降级为 TF 词袋
        """
        if a.embedding and b.embedding and len(a.embedding) == len(b.embedding):
            return self._cosine(a.embedding, b.embedding)
        return self._tf_cosine(a.content, b.content)
    
    def _cosine(self, va: List[float], vb: List[float]) -> float:
        """计算向量余弦相似度"""
        dot = sum(x * y for x, y in zip(va, vb))
        na = math.sqrt(sum(x * x for x in va))
        nb = math.sqrt(sum(x * x for x in vb))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
    
    def _tf_cosine(self, a: str, b: str) -> float:
        """
        TF 词袋 cosine（降级方案）
        
        用于 embedding 缺失时的相似度计算
        """
        ta = _tokenize_zh(a)
        tb = _tokenize_zh(b)
        
        if not ta or not tb:
            return 0.0
        
        # 构建词汇表
        vocab: dict = {}
        for t in ta + tb:
            if t not in vocab:
                vocab[t] = len(vocab)
        
        size = len(vocab)
        va = [0.0] * size
        vb = [0.0] * size
        
        for t, c in Counter(ta).items():
            va[vocab[t]] = float(c)
        for t, c in Counter(tb).items():
            vb[vocab[t]] = float(c)
        
        return self._cosine(va, vb)
    
    def _merge_pair(self, item_i: MemoryItem, item_j: MemoryItem, now: float) -> MemoryItem:
        """
        合并两条记忆（语义合并 + 矛盾检测 + 版本快照）

        策略：
        1. 矛盾检测：否定词 + 主题重叠 → 保留较新的一条，丢弃旧的
        2. 互补合并：调用 LLM 合成精炼内容，失败时降级为分号拼接
        3. 合并后的旧版本通过 consolidate() 写入 versions_to_save

        embedding / importance / tags / 时间戳处理同前。
        """
        content_i = item_i.content
        content_j = item_j.content

        # ── 矛盾检测：否定词 + 主题重叠 → 取较新 ──
        if self._is_contradiction(content_i, content_j):
            # 保留时间戳更新的（created_at 更大），内容直接替换
            newer = item_j if item_j.created_at >= item_i.created_at else item_i
            older = item_i if newer is item_j else item_j
            logger.info(
                f"⚡ Contradiction detected: '{content_i[:30]}...' vs '{content_j[:30]}...' "
                f"→ keep newer (id={newer.id})"
            )
            content = newer.content
            # 将保留方的 id 赋给合并结果
            base_item = newer
            merged_item = MemoryItem(
                id=base_item.id,
                content=content,
                importance=max(item_i.importance, item_j.importance),
                embedding=self._weighted_embedding(item_i, item_j),
                created_at=min(item_i.created_at, item_j.created_at),
                last_accessed=now,
                category=base_item.category,
                tags=list(dict.fromkeys(base_item.tags + (item_j.tags if base_item is item_i else item_i.tags))),
                slot_hint=base_item.slot_hint,
                user_id=base_item.user_id,
                layer=getattr(base_item, "layer", None),
            )
            # 记录被覆盖方 ID，供 consolidate() 写入版本历史
            merged_item._source_deleted_id = older.id  # type: ignore[attr-defined]
            # 必须连**被覆盖方自己的 layer** 一起记下：下面的删除链路会用
            # (id, layer) 定位并删除对应层的行，而合并项（幸存方）与被覆盖方
            # 若分属 episodic / semantic 两层，用幸存方的 layer 会**删错层**
            # （两表 id 各自 AUTO_INCREMENT，撞号完全可能）。
            merged_item._source_deleted_layer = getattr(older, "layer", None)  # type: ignore[attr-defined]
            merged_item._merge_reason = "contradiction"  # type: ignore[attr-defined]
            return merged_item

        # ── 互补合并：LLM 语义融合 ──
        llm_content = self._llm_merge(content_i, content_j, item_i.category)
        if llm_content:
            content = llm_content
        else:
            # 降级：分号拼接
            content = f"{content_i}；{content_j}"

        # embedding 加权平均
        emb = self._weighted_embedding(item_i, item_j)

        # tags 去重合并
        tags = list(dict.fromkeys(item_i.tags + item_j.tags))

        merged_item = MemoryItem(
            id=item_i.id,
            content=content,
            importance=max(item_i.importance, item_j.importance),
            embedding=emb,
            created_at=min(item_i.created_at, item_j.created_at),
            last_accessed=now,
            category=item_i.category or item_j.category,
            tags=tags,
            slot_hint=item_i.slot_hint or item_j.slot_hint,
            user_id=item_i.user_id or item_j.user_id,
            layer=getattr(item_i, "layer", None),
        )
        merged_item._merge_reason = "llm_merge" if llm_content else "fallback_concat"  # type: ignore[attr-defined]
        return merged_item

    def _weighted_embedding(self, a: MemoryItem, b: MemoryItem) -> Optional[List[float]]:
        """按 importance 加权平均 embedding"""
        if a.embedding and b.embedding and len(a.embedding) == len(b.embedding):
            wa, wb = a.importance, b.importance
            total = wa + wb
            if total > 0:
                return [
                    (a.embedding[k] * wa + b.embedding[k] * wb) / total
                    for k in range(len(a.embedding))
                ]
            return list(a.embedding)
        return list(a.embedding or b.embedding or [])  if (a.embedding or b.embedding) else None

    @staticmethod
    def _is_contradiction(text_a: str, text_b: str) -> bool:
        """
        轻量矛盾检测（无需 LLM）

        策略：
        - 检测否定词（不/没/非/un-/dis-/never/no）
        - 一条有否定词、另一条没有，且两者主题重叠（≥40% 字符共享）
        → 判定为矛盾

        设计意图：零延迟、零成本的粗筛，仅捕获「喜欢 X / 不喜欢 X」类显式矛盾。
        更微妙的矛盾由 LLM 合并阶段在下一轮整合中处理。
        """
        neg_pattern = re.compile(
            r'(?:不|没|非|没有|不是|不会|不能|不喜欢|不想|不要'
            r'|un|dis|never|not|no|don\'t|doesn\'t|won\'t|can\'t)',
            re.IGNORECASE
        )
        has_neg_a = bool(neg_pattern.search(text_a))
        has_neg_b = bool(neg_pattern.search(text_b))

        # 两条都有或都没有否定词 → 不视为矛盾
        if has_neg_a == has_neg_b:
            return False

        # 主题重叠度：用字符集 Jaccard 的简化版
        chars_a = set(text_a.replace(" ", ""))
        chars_b = set(text_b.replace(" ", ""))
        if not chars_a or not chars_b:
            return False
        intersection = chars_a & chars_b
        # 去掉标点后的有效重叠
        overlap = len(intersection - set("，。！？、；：""''（）【】"))
        min_len = min(len(chars_a), len(chars_b))
        return min_len > 0 and (overlap / min_len) >= 0.4

    def _llm_merge(self, content_a: str, content_b: str, category: str = "") -> str:
        """
        调用 LLM 将两条互补记忆合并为一条更精炼的表述

        失败时返回空字符串（调用方降级为分号拼接）
        """
        try:
            from backend.utils.traced_llm import traced_llm

            prompt = f"""请将以下两条相关记忆合并为一条简洁、完整、不矛盾的新记忆。
要求：
1. 保留关键信息，去除冗余
2. 如果两条信息有时间先后关系，以最新的为准
3. 输出只有一句话，不要任何解释
4. 类别：{category or '通用'}

记忆A：{content_a}
记忆B：{content_b}

请直接输出合并后的记忆内容："""

            # 尝试从上下文获取 user_id
            try:
                from backend.hermes_adapter import _CURRENT_USER_ID_CTX
                uid = int(_CURRENT_USER_ID_CTX.get() or 0)
            except Exception:
                uid = 0

            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="memory_merge",
                user_id=uid,
                source="memory",
                temperature=0,
                max_tokens=256,
            )
            merged = (resp.content or "").strip()
            # 基本校验：非空且长度合理
            if merged and len(merged) < max(len(content_a) + len(content_b), 500):
                logger.debug(f"LLM merge: '{content_a[:20]}...' + '{content_b[:20]}...' → '{merged[:40]}...'")
                return merged
        except Exception as e:
            logger.warning(f"LLM merge failed, will fallback to concat: {e}")
        return ""


# 全局实例
_consolidator: Optional[MemoryConsolidator] = None
_consolidator_lock = threading.Lock()


def get_consolidator() -> MemoryConsolidator:
    """获取 MemoryConsolidator 单例（从 .env 读取配置）"""
    global _consolidator
    with _consolidator_lock:
        if _consolidator is None:
            _consolidator = MemoryConsolidator(
                decay_rate=float(os.getenv("MEMORY_DECAY_RATE", "0.99")),
                dedup_threshold=float(os.getenv("MEMORY_DEDUP_THRESHOLD", "0.95")),
                merge_threshold=float(os.getenv("MEMORY_MERGE_THRESHOLD", "0.85")),
                ttl_days=int(os.getenv("MEMORY_TTL_DAYS", "30")),
                min_importance=float(os.getenv("MEMORY_MIN_IMPORTANCE", "0.1")),
                trigger_threshold=int(os.getenv("MEMORY_CONSOLIDATION_TRIGGER", "10")),
                indegree_protect=int(os.getenv("MEMORY_INDEGREE_PROTECT", "3")),
                # 多因子公式参数
                access_weight=float(os.getenv("MEMORY_ACCESS_WEIGHT", "1.0")),
                recency_halflife_days=float(os.getenv("MEMORY_RECENCY_HALFLIFE_DAYS", "14.0")),
                pin_boost=float(os.getenv("MEMORY_PIN_BOOST", "2.0")),
            )
        return _consolidator