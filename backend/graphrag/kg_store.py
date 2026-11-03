"""
Knowledge Graph Store - 知识图谱存储

负责:
- Neo4j 节点/边的 CRUD
- 子图查询
- 与 MySQL 记忆表同步
"""

import os
import time
from typing import Any, Dict, List, Optional
from functools import lru_cache

from backend.graphrag.types import (
    Entity,
    EntityType,
    Relation,
    RelationType,
    Subgraph,
    Claim,  # 新增：Claim 类型
)
from backend.infrastructure import get_graph_client
from backend.db.memory_mapper import get_semantic_mapper
from backend.db.kg_candidate_mapper import KgCandidateMapper
from backend.utils.log_utils import log

logger = log


# ========== 时间线查询缓存 ==========
# 使用简单的 TTL 缓存，因为时间线数据变化较少

class _TimelineCache:
    """时间线查询的简单 TTL 缓存"""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self._cache: Dict[str, tuple] = {}  # key -> (timestamp, data)
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        """获取缓存，如果过期或不存在返回 None"""
        if key not in self._cache:
            return None

        timestamp, data = self._cache[key]
        if time.time() - timestamp > self._ttl:
            # 过期
            del self._cache[key]
            return None

        return data

    def set(self, key: str, data: Any) -> None:
        """设置缓存，如果超过 max_size 则淘汰最旧的"""
        # 淘汰最旧的
        if len(self._cache) >= self._max_size and key not in self._cache:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]

        self._cache[key] = (time.time(), data)

    def invalidate(self, entity_id: str) -> None:
        """使指定实体的缓存失效"""
        keys_to_delete = [k for k in self._cache if k.startswith(f"timeline:{entity_id}:")]
        for key in keys_to_delete:
            del self._cache[key]

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()


# 全局缓存实例
_timeline_cache = _TimelineCache(max_size=100, ttl_seconds=300)  # 5 分钟 TTL


class KGStore:
    """
    知识图谱存储
    
    负责 Neo4j 的读写操作
    """
    
    # Neo4j 节点标签映射
    ENTITY_LABELS = {
        EntityType.PERSON: "Person",
        EntityType.ORGANIZATION: "Organization",
        EntityType.LOCATION: "Location",
        EntityType.CONCEPT: "Concept",
        EntityType.EVENT: "Event",
        EntityType.SKILL: "Skill",
        EntityType.PREFERENCE: "Preference",
        EntityType.FACT: "Fact",
        EntityType.PROJECT: "Project",
        EntityType.TOOL: "Tool",
        EntityType.OTHER: "Entity"
    }
    
    def __init__(self):
        """初始化 KGStore

        注意: 只用 SemanticMapper — episodic 层不入图（outbox_worker 会跳过），
              因此 graph_node_id 回写只针对 memory_semantic 表。
        """
        self._graph_client = None
        self._memory_mapper = get_semantic_mapper()
    
    def _get_graph_client(self):
        """获取图客户端（延迟 + 自动重连）"""
        if self._graph_client is None:
            self._graph_client = get_graph_client()
        # 如果客户端存在但不可用，尝试重新获取
        elif not self._graph_client.is_available():
            logger.info("[KGStore] Graph client unavailable, attempting to reconnect...")
            self._graph_client = get_graph_client()
            if self._graph_client and self._graph_client.is_available():
                logger.info("[KGStore] Reconnected successfully")
        return self._graph_client
    
    def is_available(self) -> bool:
        """检查图数据库是否可用"""
        client = self._get_graph_client()
        return client is not None and client.is_available()

    def _calculate_search_depth(self, query_entity, graph_entity) -> int:
        """
        计算图谱检索的动态深度

        策略：
        - 核心实体（高置信度 + 重要类型）→ 2 跳
        - 普通实体 → 1 跳

        Args:
            query_entity: 查询中提取的实体
            graph_entity: 图谱中匹配的实体

        Returns:
            搜索深度（1 或 2）
        """
        # 核心实体类型（人物、组织、事件）
        core_types = {"person", "organization", "event"}

        # 高置信度阈值
        high_confidence_threshold = 0.85

        # 判断是否为核心实体
        is_core_type = (
            query_entity.entity_type.value.lower() in core_types or
            graph_entity.entity_type.value.lower() in core_types
        )

        # 判断是否高置信度
        is_high_confidence = (
            query_entity.confidence >= high_confidence_threshold or
            graph_entity.confidence >= high_confidence_threshold
        )

        # 核心实体 + 高置信度 → 2 跳（发现更多关联）
        if is_core_type and is_high_confidence:
            logger.debug(
                f"[GraphRAG] Using depth=2 for core entity: "
                f"{query_entity.name} (type={query_entity.entity_type.value}, conf={query_entity.confidence:.2f})"
            )
            return 2

        # 其他情况 → 1 跳（避免噪音）
        return 1

    # ══════════════════════════════════════════════════════════
    # 两级可见性谓词（**所有读路径必须走这里**）
    # ══════════════════════════════════════════════════════════
    # 规则：
    #   - KB 文档实体（source_document_id 非空）→ 按**部门/数据层级**隔离：
    #     该文档必须落在"该用户可见的文档集合"（$visible_doc_ids）里
    #   - 记忆实体（source_document_id 为空）→ 按 **user_id** 隔离
    #
    # ⚠️ 旧谓词是 `source_document_id IS NOT NULL OR user_id = $user_id`，
    #    等于**任何** KB 文档实体对所有用户可见 —— 完全没有部门隔离。
    #    这里把前半段收紧成"文档在可见集合内"。
    #
    # ⚠️ fail-closed：$visible_doc_ids 为空列表时 Cypher 的 `IN []` 恒为 false，
    #    KB 文档实体一律不可见（拿不到层级信息时宁可看不见）。
    #
    # ⚠️ 可见文档集合**每次实时查库**（不缓存），因为部门归属随时可能被改，
    #    缓存会让"收紧可见范围"延迟生效。

    @staticmethod
    def _vis_pred(var: str) -> str:
        """生成变量 `var` 的两级可见性谓词片段。

        使用前必须同时注入 `$user_id` 与 `$visible_doc_ids` 两个参数
        （用 `_vis_params()` 构造）。
        """
        return (
            f"(({var}.source_document_id IS NOT NULL "
            f"AND {var}.source_document_id IN $visible_doc_ids) "
            f"OR ({var}.source_document_id IS NULL AND {var}.user_id = $user_id))"
        )

    def _visible_doc_ids(self, user_id: Optional[int]) -> List[int]:
        """该用户可见的 KB 文档 ID 列表（部门/层级隔离，fail-closed）。"""
        if user_id is None:
            return []
        try:
            from backend.service.auth.data_layer_service import get_visible_document_ids

            return get_visible_document_ids(int(user_id))
        except Exception as e:
            logger.warning(
                f"[KGStore] 计算可见文档集合失败 → fail-closed（KB 实体不可见）: {e}"
            )
            return []

    def _vis_params(self, user_id: Optional[int]) -> dict:
        """构造两级可见性谓词所需的 Cypher 参数。"""
        return {"user_id": user_id, "visible_doc_ids": self._visible_doc_ids(user_id)}

    # ========== 实体操作 ==========

    def create_entity(
        self,
        entity: Entity,
        user_id: Optional[int] = None,
        enable_alignment: bool = True,
        name_cache: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        创建实体节点（支持实体对齐）

        Args:
            entity: 实体对象
            user_id: 用户ID（用于隔离）
            enable_alignment: 是否启用实体对齐（默认开启）
            name_cache: 文档级名称缓存 {entity_name: entity_id}，
                        用于批量导入时跳过重复的 Neo4j 对齐查询。
                        生命周期跟随单次文档提取，函数结束后自动释放。

        Returns:
            创建成功返回实际存储的 entity_id（对齐合并时返回已有实体的 id），
            失败返回 None
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            logger.debug("Graph DB not available, skip entity creation")
            return None

        try:
            # 0. 快速路径：内存缓存命中（跳过 Neo4j 查询）
            if name_cache and entity.name in name_cache:
                cached_id = name_cache[entity.name]
                logger.debug(f"[Align] Cache hit: '{entity.name}' -> {cached_id}")
                return cached_id

            # 1. 实体对齐检查（创建前查找相似实体）
            if enable_alignment:
                similar = self.find_similar_entities(entity, user_id, similarity_threshold=0.85)
                if similar:
                    best_match, score = similar[0]
                    if score >= 0.95:
                        # 漏斗式分层判断（参考企业级 Entity Resolution 最佳实践）
                        # 类型一致性已由 search_entities 的 label 过滤保证
                        is_exact_name = (entity.name == best_match.name)
                        has_desc = bool(entity.description and best_match.description)
                        both_desc_long = has_desc and len(entity.description) >= 10 and len(best_match.description) >= 10
                        desc_containment = self._containment_similarity(entity.description, best_match.description) if has_desc else 0.0

                        if is_exact_name:
                            # 名称精确匹配（最强信号，score=1.0）
                            if both_desc_long and desc_containment <= 0.2:
                                # 同名但描述差异大 → 同名不同实体，不合并
                                self._record_candidate(
                                    user_id=user_id,
                                    candidate_type="name_collision",
                                    entity_a=best_match,
                                    entity_b=entity,
                                    score=desc_containment,
                                    reason=f"同名'{entity.name}'但描述差异大(containment={desc_containment:.2f})：'{best_match.description[:30]}' vs '{entity.description[:30]}'"
                                )
                                logger.info(f"[Align] Name collision: '{entity.name}' has different descriptions, skip merge")
                                # 不合并，继续走创建流程
                            else:
                                # 名称相同 + 描述不矛盾（或描述太短无法判断） → 自动合并
                                logger.info(f"[Align] Merged '{entity.name}' -> '{best_match.name}' (score={score})")
                                self._merge_entity_aliases(best_match, entity)
                                if name_cache:
                                    name_cache[entity.name] = best_match.id
                                    for alias in (entity.aliases or []):
                                        name_cache.setdefault(alias, best_match.id)
                                return best_match.id
                        else:
                            # 别名匹配（score=0.95，需要描述交叉验证）
                            if both_desc_long:
                                # 描述足够长，包含度可信
                                if desc_containment >= 0.5:
                                    # 描述高度重叠 → 确认是同一实体，自动合并
                                    logger.info(f"[Align] Merged '{entity.name}' -> '{best_match.name}' (alias match, desc_containment={desc_containment:.2f})")
                                    self._merge_entity_aliases(best_match, entity)
                                    if name_cache:
                                        name_cache[entity.name] = best_match.id
                                        for alias in (entity.aliases or []):
                                            name_cache.setdefault(alias, best_match.id)
                                    return best_match.id
                                else:
                                    # 别名命中但描述不相似 → 不同实体，记候选
                                    self._record_candidate(
                                        user_id=user_id,
                                        candidate_type="duplicate",
                                        entity_a=best_match,
                                        entity_b=entity,
                                        score=desc_containment,
                                        reason=f"别名命中但描述不相似(containment={desc_containment:.2f})：'{best_match.name}'({best_match.description[:20]}) vs '{entity.name}'({entity.description[:20]})"
                                    )
                                    logger.info(f"[Align] Alias match but low desc containment: '{entity.name}' ~ '{best_match.name}' (containment={desc_containment:.2f}), recorded as candidate")
                                    # 不合并，继续走创建流程
                            else:
                                # 描述太短（<10字），包含度不可信
                                # 别名匹配信号足够强，直接合并
                                logger.info(f"[Align] Merged '{entity.name}' -> '{best_match.name}' (alias match, desc too short to verify)")
                                self._merge_entity_aliases(best_match, entity)
                                if name_cache:
                                    name_cache[entity.name] = best_match.id
                                    for alias in (entity.aliases or []):
                                        name_cache.setdefault(alias, best_match.id)
                                return best_match.id
                    elif score >= 0.85:
                        # 中等置信度：记录日志 + 写入审核候选表，仍创建新实体
                        logger.info(f"[Align] Potential duplicate: '{entity.name}' ~ '{best_match.name}' (score={score})")
                        self._record_candidate(
                            user_id=user_id,
                            candidate_type="duplicate",
                            entity_a=best_match,
                            entity_b=entity,
                            score=score,
                            reason=f"描述相似度={score:.2f}，名称不同但上下文高度重叠"
                        )

            # 2. 正常创建流程
            # 获取节点标签
            label = self.ENTITY_LABELS.get(entity.entity_type, "Entity")

            # 准备属性
            from datetime import datetime
            properties = {
                "id": entity.id,
                "name": entity.name,
                "description": entity.description,
                "entity_type": entity.entity_type.value,
                "source_memory_id": entity.source_memory_id,
                "source_document_id": entity.source_document_id,
                "source_chunk_id": entity.source_chunk_id,
                "confidence": entity.confidence,
                # 时序版本控制字段
                "valid_from": datetime.now().isoformat(),
                "valid_to": None,  # null 表示当前有效版本
                "version": 1,
            }

            # 存储别名列表
            if entity.aliases:
                properties["aliases"] = entity.aliases

            if user_id is not None:
                properties["user_id"] = user_id

            # 添加额外属性
            properties.update(entity.properties)

            # 创建节点
            success = client.create_entity(
                label=label,
                properties=properties,
                unique_key="id"
            )

            if success:
                # 更新 MySQL 中的 graph_node_id
                if entity.source_memory_id:
                    self._memory_mapper.update_graph_node_id(
                        entity.source_memory_id,
                        entity.id
                    )
                logger.debug(f"Created entity: {entity.name}")
                # 缓存新创建的实体名称和别名
                if name_cache:
                    name_cache[entity.name] = entity.id
                    for alias in (entity.aliases or []):
                        name_cache.setdefault(alias, entity.id)
                return entity.id

            return None

        except Exception as e:
            logger.error(f"Failed to create entity: {e}")
            return None

    def find_similar_entities(
        self,
        entity: Entity,
        user_id: Optional[int] = None,
        similarity_threshold: float = 0.85
    ) -> List[tuple]:
        """
        查找相似实体（三层匹配：名称 → 别名 → 描述相似度）

        Args:
            entity: 待比对的实体
            user_id: 用户ID（用于隔离）
            similarity_threshold: 相似度阈值

        Returns:
            [(相似实体, 相似度), ...] 按相似度降序排列
        """
        candidates = []
        seen_ids = set()

        # 1. 名称精确匹配
        name_matches = self.search_entities(
            entity.name,
            entity_type=entity.entity_type,
            user_id=user_id,
            limit=10
        )
        for match in name_matches:
            if match.id != entity.id and match.id not in seen_ids:
                seen_ids.add(match.id)
                candidates.append((match, 1.0))  # 精确匹配 = 1.0

        # 2. 别名匹配
        for alias in entity.aliases:
            alias_matches = self.search_entities(
                alias,
                entity_type=entity.entity_type,
                user_id=user_id,
                limit=5
            )
            for match in alias_matches:
                if match.id != entity.id and match.id not in seen_ids:
                    seen_ids.add(match.id)
                    candidates.append((match, 0.95))  # 别名匹配 = 0.95

        # 3. 描述相似度兜底（名称和别名都没命中时，比较描述内容）
        #    场景：文本中"玄德"和"刘备"没有别名关联，但 description 都包含
        #    "蜀汉""刘备""主公"等关键词 → 高描述重叠 → 标记为疑似重复
        if entity.description and len(entity.description) >= 4:
            desc_candidates = self._find_by_description_similarity(
                entity, user_id, seen_ids
            )
            for match, score in desc_candidates:
                if match.id not in seen_ids:
                    seen_ids.add(match.id)
                    candidates.append((match, score))

        # 按相似度降序排列
        candidates.sort(key=lambda x: x[1], reverse=True)

        return candidates[:5]  # 最多返回5个候选

    def _find_by_description_similarity(
        self,
        entity: Entity,
        user_id: Optional[int],
        exclude_ids: set,
        desc_threshold: float = 0.55,
        name_overlap_max: float = 0.3,
        desc_score: float = 0.85
    ) -> List[tuple]:
        """
        通过描述相似度查找潜在重复实体

        策略：从 description 中提取关键词片段搜索同类型实体，
        然后用 containment（包含度）计算描述重叠。

        关键：只标记"名字不同 + 描述高度重叠"的实体对。
        - 名字无重叠 + 描述高重叠 -> 疑似重复（如"玄德"和"刘备"）
        - 名字有重叠 + 描述高重叠 -> 可能是相关实体（如"关羽"和"关平"），跳过

        得分 0.85（中等置信度）：记录日志但不自动合并。
        """
        results = []
        desc = entity.description
        name_chars = set(entity.name)

        # 从描述中提取 2-4 字的片段用于搜索（优先长片段）
        search_terms = set()
        for length in range(2, min(5, len(desc))):
            for i in range(len(desc) - length + 1):
                term = desc[i:i + length]
                if any(c.isalnum() for c in term):
                    search_terms.add(term)

        # 限制搜索次数：只取前 5 个片段
        search_terms = sorted(search_terms, key=len, reverse=True)[:5]

        checked_ids = set()

        for term in search_terms:
            matches = self.search_entities(
                term,
                entity_type=entity.entity_type,
                user_id=user_id,
                limit=5
            )
            for match in matches:
                if match.id == entity.id or match.id in exclude_ids or match.id in checked_ids:
                    continue
                if not match.description:
                    continue
                checked_ids.add(match.id)

                # 条件1：名字字符重叠度低（排除"关羽"和"关平"这种同姓相关实体）
                match_name_chars = set(match.name)
                name_overlap = len(name_chars & match_name_chars) / max(len(name_chars | match_name_chars), 1)
                if name_overlap > name_overlap_max:
                    continue

                # 条件2：描述 containment 高（短文本有多少比例出现在长文本中）
                containment = self._containment_similarity(desc, match.description)
                if containment >= desc_threshold:
                    logger.info(
                        f"[Align] Description similarity: '{entity.name}' ~ '{match.name}' "
                        f"containment={containment:.2f} name_overlap={name_overlap:.2f} "
                        f"desc1='{desc[:30]}...' desc2='{match.description[:30]}...'")
                    results.append((match, desc_score))

        return results

    @staticmethod
    def _containment_similarity(text1: str, text2: str) -> float:
        """
        包含度：短文本的字符集有多少比例出现在长文本中

        比 Jaccard 更适合检测"同一实体的不同描述"——
        因为两个描述可能长度不同，但核心信息相同（一个包含另一个）。
        """
        chars1 = {c for c in text1 if c.isalnum()}
        chars2 = {c for c in text2 if c.isalnum()}
        if not chars1 or not chars2:
            return 0.0
        shorter, longer = (chars1, chars2) if len(chars1) <= len(chars2) else (chars2, chars1)
        return len(shorter & longer) / len(shorter)

    def _merge_entity_aliases(self, existing: Entity, new_entity: Entity) -> None:
        """
        合并别名到已有实体

        Args:
            existing: 已有实体
            new_entity: 新实体（将被合并）
        """
        client = self._get_graph_client()
        if not client:
            return

        # 合并别名列表
        existing_aliases = set(existing.aliases) if existing.aliases else set()
        new_aliases = set(new_entity.aliases) if new_entity.aliases else set()
        # 把新实体的名称也加入别名（因为它可能是已有实体的别名）
        new_aliases.add(new_entity.name)

        all_aliases = list(existing_aliases | new_aliases)

        # 更新 Neo4j 中的别名
        label = self.ENTITY_LABELS.get(existing.entity_type, "Entity")
        query = f"""
        MATCH (n:{label} {{id: $id}})
        SET n.aliases = $aliases
        """
        try:
            client.run_query(query, {"id": existing.id, "aliases": all_aliases})
            logger.debug(f"[Align] Merged aliases for '{existing.name}': {all_aliases}")
        except Exception as e:
            logger.warning(f"Failed to merge aliases: {e}")

    def _record_candidate(
        self,
        user_id: Optional[int],
        candidate_type: str,
        entity_a: Entity,
        entity_b: Optional[Entity] = None,
        score: Optional[float] = None,
        reason: str = ""
    ) -> None:
        """写入审核候选表（去重：相同候选不重复写入）"""
        if user_id is None:
            return
        try:
            mapper = KgCandidateMapper()
            a_id = entity_a.id
            a_name = entity_a.name
            b_id = entity_b.id if entity_b else None
            b_name = entity_b.name if entity_b else ""
            # 避免重复写入
            if mapper.exists_pending(user_id, candidate_type, a_id, b_id):
                return
            mapper.insert_candidate(
                user_id=user_id,
                candidate_type=candidate_type,
                entity_a_id=a_id,
                entity_a_name=a_name,
                entity_b_id=b_id,
                entity_b_name=b_name,
                score=score,
                reason=reason
            )
            logger.debug(f"[Review] Recorded {candidate_type}: '{a_name}' ~ '{b_name}'")
        except Exception as e:
            logger.warning(f"Failed to record candidate: {e}")

    def merge_entities(self, keep_id: str, remove_id: str, user_id: int) -> bool:
        """
        合并两个实体：将 remove 的别名+关系全部归入 keep，然后删除 remove

        Args:
            keep_id: 保留的实体 ID
            remove_id: 被合并（删除）的实体 ID
            user_id: 用户 ID

        Returns:
            是否成功
        """
        client = self._get_graph_client()
        if not client:
            return False

        keep = self.get_entity(keep_id)
        remove = self.get_entity(remove_id)
        if not keep or not remove:
            logger.warning(f"[Merge] Entity not found: keep={keep_id}, remove={remove_id}")
            return False

        try:
            # 1. 合并别名
            existing_aliases = set(keep.aliases) if keep.aliases else set()
            new_aliases = set(remove.aliases) if remove.aliases else set()
            new_aliases.add(remove.name)
            all_aliases = list(existing_aliases | new_aliases)

            label = self.ENTITY_LABELS.get(keep.entity_type, "Entity")
            client.run_query(
                f"MATCH (n:{label} {{id: $id}}) SET n.aliases = $aliases",
                {"id": keep_id, "aliases": all_aliases}
            )

            # 2. 重定向 remove 的所有关系 → keep
            #    先获取所有关系类型，再逐类型重定向（避免 APOC 依赖）
            remove_label = self.ENTITY_LABELS.get(remove.entity_type, "Entity")
            rel_types_result = client.run_query(
                f"""MATCH (n:{remove_label} {{id: $remove_id}})-[r]-()
                    RETURN DISTINCT type(r) as rel_type""",
                {"remove_id": remove_id}
            )
            rel_types = [r.get("rel_type") for r in (rel_types_result or [])]

            for rel_type in rel_types:
                # 出边：remove -> X 改为 keep -> X
                client.run_query(
                    f"""MATCH (a {{id: $remove_id}})-[r:{rel_type}]->(b {{id: $keep_id}})
                        DELETE r""",
                    {"remove_id": remove_id, "keep_id": keep_id}
                )
                client.run_query(
                    f"""MATCH (a {{id: $remove_id}})-[r:{rel_type}]->(b)
                        WHERE b.id <> $keep_id
                        WITH a, b, r, properties(r) as props
                        DETACH DELETE r
                        WITH a, b, props
                        MATCH (keep {{id: $keep_id}})
                        CREATE (keep)-[r2:{rel_type}]->(b)
                        SET r2 = props""",
                    {"remove_id": remove_id, "keep_id": keep_id}
                )
                # 入边：X -> remove 改为 X -> keep
                client.run_query(
                    f"""MATCH (a {{id: $keep_id}})-[r:{rel_type}]->(b {{id: $remove_id}})
                        DELETE r""",
                    {"remove_id": remove_id, "keep_id": keep_id}
                )
                client.run_query(
                    f"""MATCH (a)-[r:{rel_type}]->(b {{id: $remove_id}})
                        WHERE a.id <> $keep_id
                        WITH a, b, r, properties(r) as props
                        DETACH DELETE r
                        WITH a, b, props
                        MATCH (keep {{id: $keep_id}})
                        CREATE (a)-[r2:{rel_type}]->(keep)
                        SET r2 = props""",
                    {"remove_id": remove_id, "keep_id": keep_id}
                )

            # 3. 删除 remove 节点
            client.run_query(
                f"MATCH (n:{remove_label} {{id: $remove_id}}) DETACH DELETE n",
                {"remove_id": remove_id}
            )

            logger.info(f"[Merge] Merged '{remove.name}' -> '{keep.name}' (aliases: {all_aliases})")
            return True

        except Exception as e:
            logger.error(f"[Merge] Failed: {e}")
            return False

    def edit_entity(
        self,
        entity_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        user_id: Optional[int] = None
    ) -> bool:
        """编辑实体属性（名称/描述/别名）"""
        client = self._get_graph_client()
        if not client:
            return False

        entity = self.get_entity(entity_id)
        if not entity:
            return False

        label = self.ENTITY_LABELS.get(entity.entity_type, "Entity")
        set_clauses = []
        params = {"id": entity_id}

        if name is not None:
            set_clauses.append("n.name = $name")
            params["name"] = name
        if description is not None:
            set_clauses.append("n.description = $description")
            params["description"] = description
        if aliases is not None:
            set_clauses.append("n.aliases = $aliases")
            params["aliases"] = aliases

        if not set_clauses:
            return True

        query = f"MATCH (n:{label} {{id: $id}}) SET {', '.join(set_clauses)}"
        try:
            client.run_query(query, params)
            logger.info(f"[Edit] Updated entity '{entity_id}': {set_clauses}")
            return True
        except Exception as e:
            logger.error(f"[Edit] Failed: {e}")
            return False

    def edit_relation(
        self,
        relation_id: str,
        description: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
        is_current: Optional[bool] = None
    ) -> bool:
        """编辑关系属性（描述/时间属性）"""
        client = self._get_graph_client()
        if not client:
            return False

        set_clauses = []
        params: Dict[str, Any] = {"relation_id": relation_id}

        if description is not None:
            set_clauses.append("r.description = $description")
            params["description"] = description
        if valid_from is not None:
            set_clauses.append("r.valid_from = $valid_from")
            params["valid_from"] = valid_from
        if valid_until is not None:
            set_clauses.append("r.valid_until = $valid_until")
            params["valid_until"] = valid_until
        if is_current is not None:
            set_clauses.append("r.is_current = $is_current")
            params["is_current"] = is_current

        if not set_clauses:
            return True

        query = f"MATCH ()-[r {{id: $relation_id}}]->() SET {', '.join(set_clauses)}"
        try:
            client.run_query(query, params)
            logger.info(f"[Edit] Updated relation '{relation_id}': {set_clauses}")
            return True
        except Exception as e:
            logger.error(f"[Edit] Failed: {e}")
            return False

    def get_relation_by_id(self, relation_id: str) -> Optional[Relation]:
        """根据关系ID获取关系信息"""
        client = self._get_graph_client()
        if not client:
            return None

        try:
            result = client.run_query(
                """MATCH (a)-[r {id: $relation_id}]->(b)
                   RETURN a.id as source_id, b.id as target_id,
                          type(r) as rel_type, properties(r) as props""",
                {"relation_id": relation_id}
            )
            if not result:
                return None

            row = result[0]
            props = row.get("props", {})

            # 解析关系类型
            rel_type_str = row.get("rel_type", "RELATED_TO").lower()
            try:
                rel_type = RelationType(rel_type_str)
            except ValueError:
                rel_type = RelationType.RELATED_TO

            return Relation(
                id=relation_id,
                source_id=row.get("source_id", ""),
                target_id=row.get("target_id", ""),
                relation_type=rel_type,
                description=props.get("description", ""),
                source_memory_id=props.get("source_memory_id"),
                source_document_id=props.get("source_document_id"),
                source_chunk_id=props.get("source_chunk_id"),
                confidence=props.get("confidence", 1.0),
                weight=props.get("weight", 1.0),
                valid_from=props.get("valid_from"),
                valid_until=props.get("valid_until"),
                is_current=props.get("is_current", True),
            )
        except Exception as e:
            logger.warning(f"[KG] get_relation_by_id failed: {e}")
            return None

    def flip_relation_direction(self, relation_id: str) -> bool:
        """翻转关系方向（source ↔ target 互换）"""
        client = self._get_graph_client()
        if not client:
            return False

        try:
            # 1. 获取当前关系信息
            result = client.run_query(
                """MATCH (a)-[r {id: $relation_id}]->(b)
                   RETURN a.id as source_id, b.id as target_id,
                          type(r) as rel_type, properties(r) as props""",
                {"relation_id": relation_id}
            )
            if not result:
                logger.warning(f"[Flip] Relation not found: {relation_id}")
                return False

            row = result[0]
            source_id = row["source_id"]
            target_id = row["target_id"]
            rel_type = row["rel_type"]
            props = row.get("props", {})

            # 2. 删除原边
            client.run_query(
                "MATCH ()-[r {id: $relation_id}]->() DELETE r",
                {"relation_id": relation_id}
            )

            # 3. 创建反向边（保留原属性）
            props["id"] = relation_id  # 保持同一个 ID
            set_props = ", ".join(f"r2.{k} = ${k}" for k in props.keys())
            client.run_query(
                f"""MATCH (a {{id: $target_id}}), (b {{id: $source_id}})
                    CREATE (a)-[r2:{rel_type}]->(b)
                    SET {set_props}""",
                {"target_id": target_id, "source_id": source_id, **props}
            )

            logger.info(f"[Flip] Reversed relation '{relation_id}': {target_id} -> {source_id}")
            return True

        except Exception as e:
            logger.error(f"[Flip] Failed: {e}")
            return False

    def delete_relation(self, relation_id: str) -> bool:
        """删除关系（通过 id 属性定位）"""
        client = self._get_graph_client()
        if not client:
            return False
        try:
            result = client.run_query(
                "MATCH ()-[r {id: $relation_id}]->() DELETE r RETURN count(r) as deleted",
                {"relation_id": relation_id}
            )
            deleted = result[0].get("deleted", 0) if result else 0
            if deleted > 0:
                logger.info(f"[KG] Deleted relation: {relation_id}")
                return True
            logger.warning(f"[KG] Relation not found: {relation_id}")
            return False
        except Exception as e:
            logger.error(f"[KG] Failed to delete relation: {e}")
            return False

    def get_entity(self, entity_id: str, user_id: Optional[int] = None) -> Optional[Entity]:
        """
        获取实体

        Args:
            entity_id: 实体ID
            user_id: 可选的租户ID，用于访问控制

        Returns:
            实体对象，不存在或无权限返回 None
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return None

        try:
            # 不使用标签过滤，直接用 id 属性查询
            with client._get_session() as session:
                if user_id is not None:
                    # 两级隔离（含部门/层级）：KB 文档实体须落在用户可见文档集合内，
                    # 记忆实体按 user_id 隔离。且必须排除软删节点（否则已删实体会被
                    # kg_entity_detail 查出来，与 search_entities 的行为不一致）
                    query = f"""
                    MATCH (n {{id: $entity_id}})
                    WHERE {self._vis_pred('n')}
                      AND n.deleted_at IS NULL
                    RETURN n
                    """
                    result = session.run(
                        query, entity_id=entity_id, **self._vis_params(user_id)
                    )
                else:
                    # 无租户限制（向后兼容），同样排除软删节点
                    query = """
                    MATCH (n {id: $entity_id})
                    WHERE n.deleted_at IS NULL
                    RETURN n
                    """
                    result = session.run(query, entity_id=entity_id)
                record = result.single()

                if record and record.get("n"):
                    node = record["n"]
                    props = dict(node)
                    # 获取标签推断类型
                    labels = list(node.labels) if hasattr(node, 'labels') else []
                    entity_type = self._infer_entity_type(labels)
                    props["_entity_type"] = entity_type
                    return self._dict_to_entity(props)

                return None

        except Exception as e:
            logger.error(f"Failed to get entity: {e}")
            return None

    def get_entities_by_memory_id(self, memory_id: int) -> List[Entity]:
        """
        反向查询：获取从指定记忆提取的所有实体

        Args:
            memory_id: 记忆ID

        Returns:
            实体列表
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        try:
            query = """
            MATCH (n)
            WHERE n.source_memory_id = $memory_id
              AND n.deleted_at IS NULL
            RETURN n
            """
            results = client.run_query(query, {"memory_id": memory_id})

            entities = []
            for record in results:
                entity = self._dict_to_entity(record.get("n", {}))
                if entity:
                    entities.append(entity)

            return entities

        except Exception as e:
            logger.error(f"Failed to get entities by memory_id: {e}")
            return []

    def get_relations_by_memory_id(self, memory_id: int) -> List[Relation]:
        """
        反向查询：获取从指定记忆提取的所有关系

        Args:
            memory_id: 记忆ID

        Returns:
            关系列表
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        try:
            query = """
            MATCH ()-[r]->()
            WHERE r.source_memory_id = $memory_id
              AND r.deleted_at IS NULL
            RETURN r
            """
            results = client.run_query(query, {"memory_id": memory_id})

            relations = []
            for record in results:
                relation = self._dict_to_relation(record.get("r", {}))
                if relation:
                    relations.append(relation)

            return relations

        except Exception as e:
            logger.error(f"Failed to get relations by memory_id: {e}")
            return []

    def delete_entities_by_memory_id(self, memory_id: int, user_id: Optional[int] = None) -> dict:
        """
        软删除从指定记忆提取的所有实体和关系

        当记忆被删除或内容更新时调用，清理 KGStore 中的旧数据。

        注意：如果一个实体被多个记忆引用（通过实体对齐合并），只删除
        当前记忆的 EXTRACTED_ENTITY 边，不删除实体本身。

        Args:
            memory_id: 记忆ID
            user_id: 用户ID（用于租户隔离的 GC 清理）

        Returns:
            {"deleted_entities": int, "deleted_relations": int, "deleted_edges": int}
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return {"deleted_entities": 0, "deleted_relations": 0, "deleted_edges": 0}

        result = {"deleted_entities": 0, "deleted_relations": 0, "deleted_edges": 0}

        try:
            # 1. 软删除关系（source_memory_id 匹配）
            rel_query = """
            MATCH ()-[r]->()
            WHERE r.source_memory_id = $memory_id
              AND r.deleted_at IS NULL
            SET r.deleted_at = datetime()
            RETURN count(r) as cnt
            """
            rel_results = client.run_query(rel_query, {"memory_id": memory_id})
            if rel_results:
                result["deleted_relations"] = rel_results[0].get("cnt", 0)

            # 2. 删除跨层边（Memory → Entity 的 EXTRACTED_ENTITY 边）
            #    同时返回这些实体是否还被其他 Memory 引用
            edge_query = """
            MATCH (m:Memory {mem_id: $memory_id})-[r:EXTRACTED_ENTITY]->(e)
            OPTIONAL MATCH (other_m:Memory)-[other_r:EXTRACTED_ENTITY]->(e)
            WHERE other_m.mem_id <> $memory_id
              AND other_m.deleted_at IS NULL
            DELETE r
            RETURN e.id as entity_id, count(other_r) as other_refs
            """
            edge_results = client.run_query(edge_query, {"memory_id": memory_id}) or []
            result["deleted_edges"] = len(edge_results)

            # 3. 软删除实体
            #    两种情况需要删除：
            #    a) source_memory_id = 当前记忆（直接创建的实体）
            #    b) 通过实体对齐合并到已有实体，跨层边已删除后变成孤立节点
            entities_to_delete = [
                r["entity_id"] for r in edge_results
                if r.get("other_refs", 0) == 0
            ]

            if entities_to_delete:
                entity_query = """
                MATCH (n)
                WHERE n.id IN $entity_ids
                  AND n.deleted_at IS NULL
                SET n.deleted_at = datetime(),
                    n.version = coalesce(n.version, 1) + 1
                RETURN count(n) as cnt
                """
                entity_results = client.run_query(
                    entity_query,
                    {"entity_ids": entities_to_delete}
                )
                if entity_results:
                    result["deleted_entities"] = entity_results[0].get("cnt", 0)

                # 记录被保留的实体（仍被其他记忆引用）
                preserved_count = len(entities_to_delete) - result["deleted_entities"]
                if preserved_count > 0:
                    logger.debug(
                        f"[KG] Preserved {preserved_count} entities for memory {memory_id} "
                        f"(still referenced by other memories)"
                    )

            # 4. 孤儿实体 GC：清理当前用户不再被任何活跃记忆引用的实体节点
            #    兜底步骤，处理因处理顺序/时序导致的遗留孤立实体
            #    添加租户过滤，避免跨租户删除
            if user_id is not None:
                gc_query = """
                MATCH (e)
                WHERE e.deleted_at IS NULL
                  AND NOT (e:Memory)
                  AND e.user_id = $user_id
                  AND e.source_memory_id IS NOT NULL
                  AND size([(m:Memory)-[:EXTRACTED_ENTITY]->(e) WHERE m.deleted_at IS NULL | 1]) = 0
                SET e.deleted_at = datetime(),
                    e.version = coalesce(e.version, 1) + 1
                RETURN count(e) as cnt
                """
                try:
                    gc_results = client.run_query(gc_query, {"user_id": user_id})
                    if gc_results:
                        gc_count = gc_results[0].get("cnt", 0)
                        if gc_count > 0:
                            result["deleted_entities"] += gc_count
                            logger.info(f"[KG] GC cleaned up {gc_count} orphaned entities for user {user_id}")
                except Exception as e:
                    logger.debug(f"[KG] Orphan entity GC failed (non-critical): {e}")
            else:
                logger.debug("[KG] GC skipped: user_id not provided")

            # 5. 清除时间线缓存
            self.invalidate_cache_by_memory_id(memory_id)

            if result["deleted_entities"] > 0 or result["deleted_relations"] > 0:
                logger.info(
                    f"[KG] Soft-deleted {result['deleted_entities']} entities, "
                    f"{result['deleted_relations']} relations, "
                    f"{result['deleted_edges']} cross-layer edges for memory {memory_id}"
                )

        except Exception as e:
            logger.warning(f"[KG] delete_entities_by_memory_id failed for memory {memory_id}: {e}")

        return result

    def create_memory_entity_edges(self, memory_id: int, entity_ids: List[str],
                                   user_id: Optional[int] = None,
                                   layer: Optional[str] = None) -> int:
        """
        创建 GraphMemory 与 KGStore 之间的跨层边

        在 Memory 节点（GraphMemory 层）和 Entity 节点（KGStore 层）之间
        建立 EXTRACTED_ENTITY 关系，使两层图谱数据互相链接。

        Args:
            memory_id: 记忆ID（对应 :Memory 节点的 mem_id 属性）
            entity_ids: 提取的实体ID列表（对应 :Entity 节点的 id 属性）
            user_id: 用户ID（用于幂等，如果已存在则跳过）

        Returns:
            创建的边数量
        """
        if not entity_ids:
            return 0

        client = self._get_graph_client()
        if not client or not client.is_available():
            return 0

        edges_created = 0
        # Memory 节点身份是 "{layer}:{id}"（两张记忆表的 id 会重号）；
        # 给了 layer 就按 mem_key 精确定位，否则退回"只匹配自己的记忆节点"。
        from backend.memory.graph_memory import GraphMemory as _GM
        try:
            for entity_id in entity_ids:
                # 不使用标签约束：实体创建时使用具体标签（:Person、:Organization 等），
                # 不是通用的 :Entity 标签，所以这里通过 id 属性匹配即可
                # ⚠️ 不写 `OR m.user_id IS NULL`：那是跨用户后门（mem_id 重号时会把
                #    自己的实体挂到别人名下的"无归属"记忆节点上）。
                if layer:
                    query = f"""
                    MATCH (m:Memory)
                    WHERE {_GM._key_expr('m')} = $mem_key
                    MATCH (e {{id: $entity_id}})
                    WHERE e.deleted_at IS NULL
                    MERGE (m)-[rel:EXTRACTED_ENTITY]->(e)
                    SET rel.user_id = coalesce(m.user_id, $user_id)
                    """
                    params = {"entity_id": entity_id,
                              "mem_key": _GM._mem_key(memory_id, layer),
                              "user_id": user_id}
                else:
                    query = """
                    MATCH (m:Memory {mem_id: $memory_id})
                    MATCH (e {id: $entity_id})
                    WHERE e.deleted_at IS NULL
                    MERGE (m)-[rel:EXTRACTED_ENTITY]->(e)
                    SET rel.user_id = coalesce(m.user_id, $user_id)
                    """
                    params = {"memory_id": memory_id, "entity_id": entity_id,
                              "user_id": user_id}
                client.run_query(query, params)
                edges_created += 1

            if edges_created > 0:
                logger.debug(f"[KG] Created {edges_created} EXTRACTED_ENTITY edges for memory {memory_id}")

        except Exception as e:
            logger.warning(f"[KG] create_memory_entity_edges failed for memory {memory_id}: {e}")

        return edges_created

    def delete_entity(self, entity_id: str, soft: bool = True) -> bool:
        """
        删除实体（默认软删除）

        Args:
            entity_id: 实体ID
            soft: True=软删除（设置deleted_at），False=物理删除

        Returns:
            是否成功
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return False

        try:
            if soft:
                # 软删除：设置 deleted_at 时间戳，递增版本号
                query = """
                MATCH (n {id: $entity_id})
                SET n.deleted_at = datetime(),
                    n.version = coalesce(n.version, 1) + 1
                """
                client.run_query(query, {"entity_id": entity_id})
                logger.info(f"[KG] Soft deleted entity: {entity_id}")
            else:
                # 物理删除（慎用）：删除所有标签的实体
                for label in self.ENTITY_LABELS.values():
                    client.delete_entity(label, "id", entity_id)
                logger.info(f"[KG] Hard deleted entity: {entity_id}")

            # 缓存失效：实体删除时清除该实体的时间线缓存
            _timeline_cache.invalidate(entity_id)

            return True

        except Exception as e:
            logger.error(f"Failed to delete entity: {e}")
            return False

    def restore_entity(self, entity_id: str) -> bool:
        """
        恢复已软删除的实体

        Args:
            entity_id: 实体ID

        Returns:
            是否成功
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return False

        try:
            query = """
            MATCH (n {id: $entity_id})
            WHERE n.deleted_at IS NOT NULL
            SET n.deleted_at = NULL
            """
            client.run_query(query, {"entity_id": entity_id})
            logger.info(f"[KG] Restored entity: {entity_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to restore entity: {e}")
            return False

    def search_entities(
        self,
        name: str,
        entity_type: Optional[EntityType] = None,
        user_id: Optional[int] = None,
        limit: int = 20
    ) -> List[Entity]:
        """
        搜索实体
        
        Args:
            name: 名称（模糊匹配）
            entity_type: 实体类型过滤
            user_id: 用户ID过滤
            limit: 返回数量限制
            
        Returns:
            实体列表
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return []
        
        try:
            # 构建 Cypher 查询 - 使用 toLower 做大小写不敏感搜索
            # 两级隔离（含部门/层级）：KB 文档实体须落在用户可见文档集合内，
            # 记忆实体按 user_id 隔离
            _vis = self._vis_pred("n")
            if entity_type:
                label = self.ENTITY_LABELS.get(entity_type, "Entity")
                query = f"""
                MATCH (n:{label})
                WHERE toLower(n.name) CONTAINS toLower($name)
                AND n.deleted_at IS NULL
                {f'AND {_vis}' if user_id is not None else ''}
                RETURN n
                LIMIT $limit
                """
            else:
                # 不限制标签，搜索所有节点
                query = f"""
                MATCH (n)
                WHERE toLower(n.name) CONTAINS toLower($name)
                AND n.deleted_at IS NULL
                """ + (f"AND {_vis} " if user_id is not None else "") + """
                RETURN n
                LIMIT $limit
                """
            
            params = {"name": name, "limit": limit}
            if user_id is not None:
                params.update(self._vis_params(user_id))
            
            results = client.run_query(query, params)
            
            return [self._dict_to_entity(r.get("n", {})) for r in results if r.get("n")]
            
        except Exception as e:
            logger.error(f"Failed to search entities: {e}")
            return []
    
    # ========== 关系操作 ==========
    
    def create_relation(self, relation: Relation, user_id: Optional[int] = None) -> bool:
        """
        创建关系

        Args:
            relation: 关系对象
            user_id: 用户ID

        Returns:
            是否成功
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return False

        try:
            # 准备属性
            properties = {
                "id": relation.id,
                "description": relation.description,
                "source_memory_id": relation.source_memory_id,
                "source_document_id": relation.source_document_id,
                "source_chunk_id": relation.source_chunk_id,
                "confidence": relation.confidence,
                "weight": relation.weight,
                # 时间属性（P2+ 优化：区分"曾任职"和"任职"）
                "valid_from": relation.valid_from,
                "valid_until": relation.valid_until,
                "is_current": relation.is_current
            }

            if user_id is not None:
                properties["user_id"] = user_id

            # 创建关系
            success = client.create_relation(
                from_label="Entity",  # 使用通用标签
                from_key="id",
                from_value=relation.source_id,
                to_label="Entity",
                to_key="id",
                to_value=relation.target_id,
                relation_type=relation.relation_type.value.upper(),
                properties=properties
            )
            
            if success:
                logger.debug(f"Created relation: {relation.source_id} -> {relation.target_id}")
                # 清除相关实体的时间线缓存
                _timeline_cache.invalidate(relation.source_id)
                _timeline_cache.invalidate(relation.target_id)

            return success

        except Exception as e:
            logger.error(f"Failed to create relation: {e}")
            return False

    # ══════════════════════════════════════════════════════════
    # Claim 操作
    # ══════════════════════════════════════════════════════════

    def create_claim(
        self,
        claim: "Claim",
        user_id: Optional[int] = None
    ) -> bool:
        """
        创建 Claim 节点

        Claim 是从文本中提取的事实陈述，与实体和关系不同：
        - Entity: 人/物/概念
        - Relation: 实体间关系
        - Claim: 事实陈述（如"关羽在公元 219 年败走麦城"）

        Args:
            claim: Claim 对象
            user_id: 用户 ID（用于隔离）

        Returns:
            创建成功返回 True，失败返回 False
        """
        from backend.graphrag.types import Claim

        client = self._get_graph_client()
        if not client or not client.is_available():
            logger.debug("Graph DB not available, skip claim creation")
            return False

        try:
            # 准备属性
            from datetime import datetime
            now = datetime.now().isoformat()

            props = {
                "id": claim.id,
                "claim_type": claim.claim_type.value,
                "claim_text": claim.claim_text,
                "subject": claim.subject,
                "object": claim.object or "",
                "claim_value": claim.claim_value,
                "time": claim.time or "",
                "confidence": claim.confidence,
                "status": claim.status.value,
                "source_entity_id": claim.source_entity_id or "",
                "source_chunk_id": claim.source_chunk_id if claim.source_chunk_id is not None else 0,
                "source_document_id": claim.source_document_id if claim.source_document_id is not None else 0,
                "created_at": claim.created_at or now,
                "updated_at": claim.updated_at or now,
            }

            # 添加额外属性
            if claim.properties:
                props["properties"] = claim.properties

            # Cypher 创建
            query = """
            CREATE (c:Claim $props)
            RETURN c.id as id
            """

            result = client.run_query(query, {"props": props})

            if result:
                logger.debug(f"Created claim: {claim.id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to create claim: {e}")
            return False

    def get_claims_by_entity(
        self,
        entity_name: str,
        user_id: Optional[int] = None,
        limit: int = 20
    ) -> List["Claim"]:
        """
        获取与实体相关的 Claim

        Args:
            entity_name: 实体名称
            user_id: 用户 ID（用于隔离）
            limit: 返回数量限制

        Returns:
            Claim 列表
        """
        from backend.graphrag.types import Claim, ClaimType, ClaimStatus

        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        try:
            # 查询以该实体为 subject 或 object 的 Claim
            query = """
            MATCH (c:Claim)
            WHERE (c.subject = $entity_name OR c.object = $entity_name)
            RETURN c
            ORDER BY c.confidence DESC
            LIMIT $limit
            """

            results = client.run_query(query, {
                "entity_name": entity_name,
                "limit": limit
            })

            claims = []
            for item in results:
                c = item.get("c", {})
                try:
                    claim = Claim(
                        id=c.get("id", ""),
                        claim_type=ClaimType(c.get("claim_type", "fact")),
                        claim_text=c.get("claim_text", ""),
                        subject=c.get("subject", ""),
                        object=c.get("object") or None,
                        claim_value=c.get("claim_value", ""),
                        time=c.get("time") or None,
                        confidence=c.get("confidence", 1.0),
                        source_entity_id=c.get("source_entity_id") or None,
                        source_chunk_id=c.get("source_chunk_id") or None,
                        source_document_id=c.get("source_document_id") or None,
                        status=ClaimStatus(c.get("status", "active")),
                        created_at=c.get("created_at"),
                        updated_at=c.get("updated_at"),
                    )
                    claims.append(claim)
                except Exception as e:
                    logger.warning(f"Failed to parse claim: {e}")
                    continue

            return claims

        except Exception as e:
            logger.error(f"Failed to get claims by entity: {e}")
            return []

    def get_claims_by_entities(
        self,
        entity_names: List[str],
        user_id: Optional[int] = None,
        limit: int = 20
    ) -> List["Claim"]:
        """
        批量获取与多个实体相关的 Claim（避免 N+1 查询）

        Args:
            entity_names: 实体名称列表
            user_id: 用户 ID（用于隔离）
            limit: 返回数量限制

        Returns:
            Claim 列表（按置信度排序）
        """
        from backend.graphrag.types import Claim, ClaimType, ClaimStatus

        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        if not entity_names:
            return []

        try:
            # 批量查询：subject 或 object 在实体列表中的 Claim
            query = """
            MATCH (c:Claim)
            WHERE c.subject IN $entity_names OR c.object IN $entity_names
            RETURN c
            ORDER BY c.confidence DESC
            LIMIT $limit
            """

            results = client.run_query(query, {
                "entity_names": entity_names,
                "limit": limit
            })

            claims = []
            for item in results:
                c = item.get("c", {})
                try:
                    claim = Claim(
                        id=c.get("id", ""),
                        claim_type=ClaimType(c.get("claim_type", "fact")),
                        claim_text=c.get("claim_text", ""),
                        subject=c.get("subject", ""),
                        object=c.get("object") or None,
                        claim_value=c.get("claim_value", ""),
                        time=c.get("time") or None,
                        confidence=c.get("confidence", 1.0),
                        source_entity_id=c.get("source_entity_id") or None,
                        source_chunk_id=c.get("source_chunk_id") or None,
                        source_document_id=c.get("source_document_id") or None,
                        status=ClaimStatus(c.get("status", "active")),
                        created_at=c.get("created_at"),
                        updated_at=c.get("updated_at"),
                    )
                    claims.append(claim)
                except Exception as e:
                    logger.warning(f"Failed to parse claim: {e}")
                    continue

            return claims

        except Exception as e:
            logger.error(f"Failed to get claims by entities: {e}")
            return []

    def search_claims(
        self,
        query: str,
        user_id: Optional[int] = None,
        limit: int = 20,
        use_vector: bool = True
    ) -> List["Claim"]:
        """
        搜索 Claim（优先向量相似度搜索，回退文本匹配）

        Args:
            query: 搜索关键词
            user_id: 用户 ID
            limit: 返回数量限制
            use_vector: 是否使用向量搜索（默认 True）

        Returns:
            Claim 列表
        """
        from backend.graphrag.types import Claim, ClaimType, ClaimStatus

        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        # 1. 尝试向量搜索
        if use_vector and query:
            try:
                from backend.service.kb.claim_vectorstore import search_claims_by_vector
                vector_results = search_claims_by_vector(
                    query,
                    user_id=user_id or 0,
                    top_k=limit
                )

                if vector_results:
                    # 从 Neo4j 获取完整 Claim 信息
                    claim_ids = [r["id"] for r in vector_results]
                    claims = self._get_claims_by_ids(claim_ids, user_id)
                    if claims:
                        logger.debug(f"[Claim] Vector search found {len(claims)} results")
                        return claims

            except Exception as e:
                logger.debug(f"[Claim] Vector search failed, fallback to text: {e}")

        # 2. 回退文本匹配搜索
        try:
            cypher = """
            MATCH (c:Claim)
            WHERE c.claim_text CONTAINS $query
               OR c.subject CONTAINS $query
               OR c.object CONTAINS $query
            RETURN c
            ORDER BY c.confidence DESC
            LIMIT $limit
            """

            results = client.run_query(cypher, {
                "query": query,
                "limit": limit
            })

            claims = []
            for item in results:
                c = item.get("c", {})
                try:
                    claim = Claim(
                        id=c.get("id", ""),
                        claim_type=ClaimType(c.get("claim_type", "fact")),
                        claim_text=c.get("claim_text", ""),
                        subject=c.get("subject", ""),
                        object=c.get("object") or None,
                        claim_value=c.get("claim_value", ""),
                        time=c.get("time") or None,
                        confidence=c.get("confidence", 1.0),
                        source_entity_id=c.get("source_entity_id") or None,
                        source_chunk_id=c.get("source_chunk_id") or None,
                        source_document_id=c.get("source_document_id") or None,
                        status=ClaimStatus(c.get("status", "active")),
                        created_at=c.get("created_at"),
                        updated_at=c.get("updated_at"),
                    )
                    claims.append(claim)
                except Exception as e:
                    logger.warning(f"Failed to parse claim: {e}")
                    continue

            return claims

        except Exception as e:
            logger.error(f"Failed to search claims: {e}")
            return []

    def _get_claims_by_ids(
        self,
        claim_ids: List[str],
        user_id: Optional[int] = None
    ) -> List["Claim"]:
        """
        根据 ID 列表获取 Claim

        Args:
            claim_ids: Claim ID 列表
            user_id: 用户 ID

        Returns:
            Claim 列表
        """
        from backend.graphrag.types import Claim, ClaimType, ClaimStatus

        if not claim_ids:
            return []

        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        try:
            cypher = """
            MATCH (c:Claim)
            WHERE c.id IN $claim_ids
            RETURN c
            """

            results = client.run_query(cypher, {"claim_ids": claim_ids})

            # 按 ID 顺序返回
            claim_map = {}
            for item in results:
                c = item.get("c", {})
                try:
                    claim = Claim(
                        id=c.get("id", ""),
                        claim_type=ClaimType(c.get("claim_type", "fact")),
                        claim_text=c.get("claim_text", ""),
                        subject=c.get("subject", ""),
                        object=c.get("object") or None,
                        claim_value=c.get("claim_value", ""),
                        time=c.get("time") or None,
                        confidence=c.get("confidence", 1.0),
                        source_entity_id=c.get("source_entity_id") or None,
                        source_chunk_id=c.get("source_chunk_id") or None,
                        source_document_id=c.get("source_document_id") or None,
                        status=ClaimStatus(c.get("status", "active")),
                        created_at=c.get("created_at"),
                        updated_at=c.get("updated_at"),
                    )
                    claim_map[claim.id] = claim
                except Exception as e:
                    logger.warning(f"Failed to parse claim: {e}")
                    continue

            # 按 ID 列表顺序返回
            return [claim_map[cid] for cid in claim_ids if cid in claim_map]

        except Exception as e:
            logger.error(f"Failed to get claims by IDs: {e}")
            return []

    def get_claims_by_document(
        self,
        document_id: int,
        user_id: Optional[int] = None,
        limit: int = 100
    ) -> List["Claim"]:
        """
        获取文档的所有 Claim

        Args:
            document_id: 文档 ID
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            Claim 列表
        """
        from backend.graphrag.types import Claim, ClaimType, ClaimStatus

        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        try:
            cypher = """
            MATCH (c:Claim)
            WHERE c.source_document_id = $document_id
            RETURN c
            ORDER BY c.confidence DESC
            LIMIT $limit
            """

            results = client.run_query(cypher, {
                "document_id": document_id,
                "limit": limit
            })

            claims = []
            for item in results:
                c = item.get("c", {})
                try:
                    claim = Claim(
                        id=c.get("id", ""),
                        claim_type=ClaimType(c.get("claim_type", "fact")),
                        claim_text=c.get("claim_text", ""),
                        subject=c.get("subject", ""),
                        object=c.get("object") or None,
                        claim_value=c.get("claim_value", ""),
                        time=c.get("time") or None,
                        confidence=c.get("confidence", 1.0),
                        source_entity_id=c.get("source_entity_id") or None,
                        source_chunk_id=c.get("source_chunk_id") or None,
                        source_document_id=c.get("source_document_id") or None,
                        status=ClaimStatus(c.get("status", "active")),
                        created_at=c.get("created_at"),
                        updated_at=c.get("updated_at"),
                    )
                    claims.append(claim)
                except Exception as e:
                    logger.warning(f"Failed to parse claim: {e}")
                    continue

            return claims

        except Exception as e:
            logger.error(f"Failed to get claims by document: {e}")
            return []

    def get_related_entities(
        self,
        entity_id: str,
        relation_type: Optional[RelationType] = None,
        direction: str = "both",
        user_id: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取相关实体

        Args:
            entity_id: 实体ID
            relation_type: 关系类型过滤
            direction: 方向 ('out', 'in', 'both')
            user_id: 用户ID过滤（防止跨用户数据泄露）
            limit: 返回数量限制

        Returns:
            [{entity: Entity, relation: Relation}, ...]
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        try:
            # 使用 id 属性直接查询，不限制标签
            # 因为实际节点标签可能是 Project, Concept, Tool 等
            query = f"""
            MATCH (n {{id: $entity_id}})
            """

            if direction == "out":
                query += "-[r]->(m)"
            elif direction == "in":
                query += "<-[r]-(m)"
            else:
                query += "-[r]-(m)"

            # 构建 WHERE 条件
            where_clauses = []
            # 两端节点都要做两级可见性过滤（含部门/层级），防止跨用户/跨部门泄露
            if user_id is not None:
                where_clauses.append(self._vis_pred("n"))
            if relation_type:
                where_clauses.append("type(r) = $relation_type")
            if user_id is not None:
                where_clauses.append(self._vis_pred("m"))

            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)

            query += """
            RETURN DISTINCT m as node, r as relation, type(r) as rel_type,
                            startNode(r).id as rel_source_id, endNode(r).id as rel_target_id
            LIMIT $limit
            """

            params = {"entity_id": entity_id, "limit": limit}
            if relation_type:
                params["relation_type"] = relation_type.value.upper()
            if user_id is not None:
                params.update(self._vis_params(user_id))

            results = client.run_query(query, params)

            # 转换结果并去重
            related = []
            seen_ids = set()
            for item in results:
                entity = self._dict_to_entity(item.get("node", {}))
                # rel_obj 是 run_query 序列化后的 dict（关系属性）
                rel_obj = item.get("relation") or {}
                rel_id = rel_obj.get("id", "") if isinstance(rel_obj, dict) else ""
                rel_desc = rel_obj.get("description", "") if isinstance(rel_obj, dict) else ""
                rel_source = item.get("rel_source_id", "")
                rel_target = item.get("rel_target_id", "")
                rel_type_val = item.get("rel_type", "related_to")
                try:
                    relation_type = RelationType(rel_type_val.lower())
                except ValueError:
                    relation_type = RelationType.RELATED_TO
                relation = Relation(
                    id=rel_id,
                    source_id=rel_source,
                    target_id=rel_target,
                    relation_type=relation_type,
                    description=rel_desc,
                    confidence=1.0,
                )
                if entity and entity.id not in seen_ids:
                    seen_ids.add(entity.id)
                    related.append({
                        "entity": entity,
                        "relation": relation,
                        "rel_type": rel_type_val
                    })

            return related

        except Exception as e:
            logger.error(f"Failed to get related entities: {e}")
            return []

    def get_related_entities_at_time(
        self,
        entity_id: str,
        target_date: str,
        relation_type: Optional[RelationType] = None,
        direction: str = "both",
        user_id: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        时间旅行查询：获取某实体在指定时间点的相关实体

        基于关系的 valid_from/valid_until/is_current 字段，
        返回在 target_date 时刻有效的关系。

        Args:
            entity_id: 实体ID
            target_date: 目标日期（ISO 8601 格式，如 "2020-06-15"）
            relation_type: 关系类型过滤
            direction: 方向 ('out', 'in', 'both')
            user_id: 用户ID过滤
            limit: 返回数量限制

        Returns:
            [{"entity": Entity, "relation": Relation, "valid_from": str, "valid_until": str}, ...]
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        try:
            # 构建查询
            query = f"""
            MATCH (n {{id: $entity_id}})
            """

            if direction == "out":
                query += "-[r]->(m)"
            elif direction == "in":
                query += "<-[r]-(m)"
            else:
                query += "-[r]-(m)"

            # 时间条件：关系在 target_date 时刻有效
            # 逻辑：valid_from <= target_date AND (valid_until >= target_date OR valid_until IS NULL)
            # 注意：is_current=true 时，valid_until 应该为 NULL，否则以 valid_until 为准
            time_condition = """
            WHERE (r.valid_from IS NULL OR r.valid_from <= $target_date)
            AND (r.valid_until IS NULL OR r.valid_until >= $target_date)
            AND n.deleted_at IS NULL
            AND r.deleted_at IS NULL
            """

            if relation_type:
                # 使用参数化查询避免注入
                time_condition += " AND type(r) = $relation_type"

            if user_id is not None:
                # 关系与目标节点都要做两级可见性过滤（含部门/层级）
                time_condition += f" AND {self._vis_pred('r')}"
                time_condition += f" AND {self._vis_pred('m')}"

            query += time_condition + """
            RETURN DISTINCT m as node, r as relation, type(r) as rel_type
            LIMIT $limit
            """

            params = {
                "entity_id": entity_id,
                "target_date": target_date,
                "limit": limit
            }
            if relation_type:
                params["relation_type"] = relation_type.value.upper()
            if user_id is not None:
                params.update(self._vis_params(user_id))

            results = client.run_query(query, params)

            # 转换结果
            related = []
            seen_ids = set()
            for item in results:
                entity = self._dict_to_entity(item.get("node", {}))
                # 修复：正确获取 relation 数据
                relation_data = item.get("relation", {})
                relation = self._dict_to_relation(relation_data) if relation_data else None
                if entity and entity.id not in seen_ids:
                    seen_ids.add(entity.id)
                    related.append({
                        "entity": entity,
                        "relation": relation,
                        "rel_type": item.get("rel_type"),
                        "valid_from": relation_data.get("valid_from") if relation_data else None,
                        "valid_until": relation_data.get("valid_until") if relation_data else None
                    })

            return related

        except Exception as e:
            logger.error(f"Failed to get related entities at time: {e}")
            return []

    def get_entity_timeline(
        self,
        entity_id: str,
        relation_type: Optional[RelationType] = None,
        user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取实体的时间线（所有关系的时间信息）

        返回该实体所有关系的时间属性，按时间排序。
        NULL 值（未知时间）排在最后。

        支持缓存：相同查询 5 分钟内直接返回缓存结果。

        Args:
            entity_id: 实体ID
            relation_type: 关系类型过滤
            user_id: 用户ID过滤

        Returns:
            [
                {
                    "related_entity": Entity,
                    "relation_type": str,
                    "valid_from": str,
                    "valid_until": str,
                    "is_current": bool,
                    "description": str
                },
                ...
            ]
        """
        # 生成缓存 key
        cache_key = f"timeline:{entity_id}:{relation_type.value if relation_type else 'all'}:{user_id or 'all'}"

        # 尝试从缓存获取
        cached_result = _timeline_cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Timeline cache hit: {cache_key}")
            return cached_result

        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        try:
            query = """
            MATCH (n {id: $entity_id})-[r]-(m)
            WHERE n.deleted_at IS NULL AND r.deleted_at IS NULL
            """

            # 中心节点/关系/对端节点三层两级可见性过滤（含部门/层级）
            conditions = []
            if user_id is not None:
                conditions.append(self._vis_pred("n"))
            if relation_type:
                # 使用参数化查询避免注入
                conditions.append("type(r) = $relation_type")
            if user_id is not None:
                conditions.append(self._vis_pred("r"))
                conditions.append(self._vis_pred("m"))

            if conditions:
                query += " AND " + " AND ".join(conditions)

            # 排序：有 valid_from 的按时间升序，NULL 的排在最后
            query += """
            RETURN m as related_entity, type(r) as relation_type,
                   r.valid_from as valid_from, r.valid_until as valid_until,
                   r.is_current as is_current, r.description as description
            ORDER BY
                CASE WHEN r.valid_from IS NULL THEN 1 ELSE 0 END,
                r.valid_from ASC
            """

            params = {"entity_id": entity_id}
            if relation_type:
                params["relation_type"] = relation_type.value.upper()
            if user_id is not None:
                params.update(self._vis_params(user_id))

            results = client.run_query(query, params)

            timeline = []
            for item in results:
                entity = self._dict_to_entity(item.get("related_entity", {}))
                if entity:
                    timeline.append({
                        "related_entity": entity,
                        "relation_type": item.get("relation_type"),
                        "valid_from": item.get("valid_from"),
                        "valid_until": item.get("valid_until"),
                        "is_current": item.get("is_current", True),
                        "description": item.get("description", "")
                    })

            # 存入缓存
            _timeline_cache.set(cache_key, timeline)

            return timeline

        except Exception as e:
            logger.error(f"Failed to get entity timeline: {e}")
            return []

    def invalidate_timeline_cache(self, entity_id: str = None) -> None:
        """
        使时间线缓存失效

        Args:
            entity_id: 指定实体ID则只清除该实体的缓存，为 None 则清除所有缓存
        """
        if entity_id:
            _timeline_cache.invalidate(entity_id)
            logger.info(f"Invalidated timeline cache for entity: {entity_id}")
        else:
            _timeline_cache.clear()
            logger.info("Cleared all timeline cache")

    def invalidate_cache_by_memory_id(self, memory_id: int) -> None:
        """
        清除从指定记忆提取的所有实体的时间线缓存

        当记忆被更新或删除时调用，确保缓存不会返回过期数据。

        查找逻辑（覆盖两种情况）：
        1. source_memory_id = memory_id 的实体（直接创建）
        2. 通过跨层边 (EXTRACTED_ENTITY) 关联的实体（包括实体对齐合并的）

        Args:
            memory_id: 记忆ID
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return

        invalidated_count = 0

        try:
            # 1. 通过 source_memory_id 查找实体
            entities_by_source = self.get_entities_by_memory_id(memory_id)
            for entity in entities_by_source:
                _timeline_cache.invalidate(entity.id)
                invalidated_count += 1

            # 2. 通过跨层边查找实体（覆盖实体对齐合并的情况）
            #    实体对齐后，合并实体的 source_memory_id 指向原始创建者记忆
            #    但跨层边仍然连接当前记忆和合并实体
            edge_query = """
            MATCH (m:Memory {mem_id: $memory_id})-[:EXTRACTED_ENTITY]->(e)
            WHERE e.deleted_at IS NULL
            RETURN DISTINCT e.id as entity_id
            """
            edge_results = client.run_query(edge_query, {"memory_id": memory_id})

            for record in (edge_results or []):
                entity_id = record.get("entity_id")
                if entity_id:
                    _timeline_cache.invalidate(entity_id)
                    invalidated_count += 1

            if invalidated_count > 0:
                logger.info(
                    f"Invalidated timeline cache for {invalidated_count} entities from memory {memory_id}"
                )

        except Exception as e:
            logger.warning(f"Failed to invalidate cache by memory_id {memory_id}: {e}")

    # ========== 子图查询 ==========
    
    def get_subgraph(
        self,
        entity_id: str,
        depth: int = 2,
        user_id: Optional[int] = None
    ) -> Subgraph:
        """
        获取以某实体为中心的子图
        
        Args:
            entity_id: 中心实体ID
            depth: 遍历深度
            user_id: 用户ID过滤
            
        Returns:
            Subgraph 对象
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return Subgraph()
        
        try:
            # 不使用标签过滤，直接用 id 属性查询
            # 因为实际节点标签可能是 Project, Concept, Tool 等
            with client._get_session() as session:
                user_filter = ""
                params = {"entity_id": entity_id}
                if user_id is not None:
                    # ⚠️ 必须校验**路径上的每一个节点与每一条关系**。
                    # 旧实现只过滤两端（center / other），而返回的是
                    # `nodes(path)` / `relationships(path)` 的**全集** ——
                    # 于是路径中间的节点（别人的记忆实体、其他部门的 KB 实体）
                    # 会连带出现在 nodes/edges 里，等于绕着端点过滤把数据漏出去。
                    _vis_node = self._vis_pred("pn")
                    _vis_rel = self._vis_pred("pr")
                    user_filter = (
                        f"WHERE all(pn IN nodes(path) WHERE {_vis_node}) "
                        f"AND all(pr IN relationships(path) WHERE {_vis_rel})"
                    )
                    params.update(self._vis_params(user_id))

                query = f"""
                MATCH path = (center {{id: $entity_id}})-[*1..{depth}]-(other)
                {user_filter}
                RETURN
                    [n IN nodes(path) | {{id: n.id, labels: labels(n), properties: properties(n)}}] as nodes,
                    [r IN relationships(path) | {{type: type(r), properties: properties(r),
                        source: startNode(r).id, target: endNode(r).id}}] as edges
                """
                result = session.run(query, **params)
                
                # 合并所有路径的节点和边（去重）
                all_nodes = {}
                all_edges = {}
                
                for record in result:
                    for node in record["nodes"]:
                        node_id = node.get("id")
                        if node_id:
                            all_nodes[node_id] = node
                    for edge in record["edges"]:
                        edge_key = f"{edge.get('source')}-{edge.get('target')}"
                        all_edges[edge_key] = edge
                
                # 解析节点
                nodes = []
                for node_data in all_nodes.values():
                    props = node_data.get("properties", {})
                    # 从标签推断实体类型
                    labels = node_data.get("labels", [])
                    entity_type = self._infer_entity_type(labels)
                    props["_entity_type"] = entity_type
                    
                    entity = self._dict_to_entity(props)
                    if entity:
                        nodes.append(entity)
                
                # 解析边
                edges = []
                for edge_data in all_edges.values():
                    relation = self._edge_to_relation_simple(edge_data)
                    if relation:
                        edges.append(relation)

                # ── 回退：中心节点自己可见、但它的邻居全都在别的部门/别人的记忆里 ──
                # 上面的 MATCH 要求"至少存在一条全可见路径"，于是这种节点会返回**空子图**，
                # 而用户其实有权看到这个节点本身（图谱页 get_user_graph 也会画出它）。
                # 这种"能看见的节点却查出空"会让实体详情/GraphRAG 上下文莫名变空，
                # 所以这里补一次单独取中心节点。
                if not nodes and user_id is not None:
                    try:
                        center = self.get_entity(entity_id, user_id=user_id)
                        if center is not None:
                            nodes.append(center)
                            logger.debug(
                                f"[KGStore] 中心节点 {entity_id} 可见但无可见邻居，"
                                f"按单独节点返回（部门隔离所致）"
                            )
                    except Exception as _ce:
                        logger.debug(f"中心节点回退查询失败（忽略）: {_ce}")

                return Subgraph(
                    nodes=nodes,
                    edges=edges,
                    center_id=entity_id,
                    depth=depth
                )
            
        except Exception as e:
            logger.error(f"Failed to get subgraph: {e}")
            return Subgraph()

    def find_paths_between(
        self,
        source_id: str,
        target_id: str,
        user_id: Optional[int] = None,
        max_hops: int = 4,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        查找两个实体之间的所有路径（间接关系发现）

        不创建新边，只返回已有路径。路径本身就是解释。

        Args:
            source_id: 起始实体 ID
            target_id: 目标实体 ID
            user_id: 用户 ID（安全过滤）
            max_hops: 最大跳数（默认 4）
            limit: 返回路径数量限制

        Returns:
            [
                {
                    "nodes": [{"id": "...", "name": "甲", "type": "person"}, ...],
                    "edges": [{"type": "INVESTED", "source": "...", "target": "..."}, ...],
                    "hops": 2,
                    "description": "甲 →INVESTED→ 乙 →INVESTED→ 丙"
                }
            ]
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        try:
            with client._get_session() as session:
                params = {
                    "source_id": source_id,
                    "target_id": target_id,
                    "max_hops": max_hops,
                    "limit": limit
                }

                # 可见性过滤：路径上的**所有节点与所有关系**都必须可见。
                # 旧实现只校验节点（且端点条件与 ALL(...) 重复），关系上的
                # source_document_id / user_id 完全没校验 → 跨部门、跨用户的关系
                # 会随路径一起漏出。
                where_parts = []
                if user_id is not None:
                    where_parts.append(
                        f"all(pn IN nodes(path) WHERE {self._vis_pred('pn')})"
                    )
                    where_parts.append(
                        f"all(pr IN relationships(path) WHERE {self._vis_pred('pr')})"
                    )
                    params.update(self._vis_params(user_id))
                where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

                query = f"""
                MATCH path = (a {{id: $source_id}})-[*1..{max_hops}]->(b {{id: $target_id}})
                {where_sql}
                RETURN
                    [n IN nodes(path) | {{
                        id: n.id, name: n.name, type: n.entity_type
                    }}] as nodes,
                    [r IN relationships(path) | {{
                        type: type(r),
                        source: startNode(r).id,
                        target: endNode(r).id,
                        confidence: r.confidence
                    }}] as edges,
                    length(path) as hops
                ORDER BY hops ASC
                LIMIT $limit
                """

                result = session.run(query, **params)

                paths = []
                for record in result:
                    nodes = record.get("nodes", [])
                    edges = record.get("edges", [])
                    hops = record.get("hops", 0)

                    paths.append({
                        "nodes": nodes,
                        "edges": edges,
                        "hops": hops,
                        "description": self._format_path_description(nodes, edges)
                    })

                return paths

        except Exception as e:
            logger.error(f"Failed to find paths between {source_id} and {target_id}: {e}")
            return []

    def _format_path_description(
        self,
        nodes: List[Dict],
        edges: List[Dict]
    ) -> str:
        """
        生成人类可读的路径描述

        示例输出："甲 →INVESTED→ 乙 →INVESTED→ 丙"
        """
        parts = []
        for i, node in enumerate(nodes):
            name = node.get("name", node.get("id", "?"))
            parts.append(name)
            if i < len(edges):
                edge = edges[i]
                rel_type = edge.get("type", "RELATED")
                parts.append(f"→{rel_type}→")
        return " ".join(parts)

    def find_reachable_entities(
        self,
        source_id: str,
        user_id: Optional[int] = None,
        max_hops: int = 4,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        查找从 source 出发可达的所有实体（用于前端过滤目标实体候选）

        与 find_paths_between 使用相同的 user_id 过滤逻辑（路径上所有节点都过滤），
        确保下拉框里出现的实体一定存在至少一条路径。

        Args:
            source_id: 起始实体 ID
            user_id: 用户 ID（安全过滤）
            max_hops: 最大跳数（与路径查询一致，默认 4）
            limit: 返回数量上限（防止大图中爆炸）

        Returns:
            [{"id": "...", "name": "乙", "type": "person"}, ...]
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        try:
            with client._get_session() as session:
                params = {
                    "source_id": source_id,
                    "max_hops": max_hops,
                    "limit": limit
                }

                # 可见性：路径上所有节点与关系都要可见。
                # ⚠️ 旧实现把 `a.source_document_id IS NOT NULL OR a.user_id = $user_id`
                #    写在 WHERE 里但**没有按 user_id is not None 判断**，
                #    于是 user_id=None 时 SQL 引用了未注入的 $user_id →
                #    Neo4j 报 ParameterMissing → 被 except 吞掉 → 恒返回 []。
                where_parts = ["a.id <> b.id"]
                if user_id is not None:
                    where_parts.append(
                        f"all(pn IN nodes(path) WHERE {self._vis_pred('pn')})"
                    )
                    where_parts.append(
                        f"all(pr IN relationships(path) WHERE {self._vis_pred('pr')})"
                    )
                    params.update(self._vis_params(user_id))

                query = f"""
                MATCH path = (a {{id: $source_id}})-[*1..{max_hops}]->(b)
                WHERE {" AND ".join(where_parts)}
                RETURN DISTINCT
                    b.id as id, b.name as name, b.entity_type as type
                LIMIT $limit
                """

                result = session.run(query, **params)
                return [
                    {"id": r["id"], "name": r["name"] or r["id"], "type": r["type"] or "other"}
                    for r in result
                    if r.get("id")
                ]

        except Exception as e:
            logger.error(f"Failed to find reachable entities from {source_id}: {e}")
            return []

    def get_user_graph(
        self,
        user_id: int,
        limit: int = 100
    ) -> Subgraph:
        """
        获取用户的知识图谱

        可见性规则：
        - KB 文档实体（有 source_document_id）：按**部门/数据层级**隔离 ——
          只有其来源文档落在当前用户可见文档集合内才可见
        - 记忆实体（有 source_memory_id）：按 user_id 隔离，只看自己的

        Args:
            user_id: 用户ID
            limit: 节点数量限制

        Returns:
            Subgraph 对象
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return Subgraph()

        try:
            # 查询可见节点（两级：KB 文档实体按部门/层级、记忆实体按 user_id）：
            # 1. KB 文档实体：source_document_id 必须落在该用户可见文档集合内
            # 2. 用户自己的记忆实体：source_document_id 为空 → user_id = $user_id
            # 3. 一律排除软删节点（否则图谱页会把已删的"僵尸节点"也画出来，
            #    与 search_entities 的 deleted_at 过滤行为不一致）
            nodes_query = f"""
            MATCH (n)
            WHERE {self._vis_pred('n')}
              AND n.deleted_at IS NULL
            RETURN n
            LIMIT $limit
            """

            _np = self._vis_params(user_id)
            _np["limit"] = limit
            nodes_results = client.run_query(nodes_query, _np)
            
            # 解析节点
            nodes = {}
            for record in nodes_results:
                if record.get("n"):
                    entity = self._dict_to_entity(record["n"])
                    if entity and entity.id:
                        nodes[entity.id] = entity

            node_ids = list(nodes.keys())

            # 查询用户的所有关系（仅返回与已获取节点相连的边）
            if not node_ids:
                return Subgraph(nodes=[], edges=[])

            edges_query = """
            MATCH (a)-[r]->(b)
            WHERE a.id IN $node_ids AND b.id IN $node_ids
            RETURN r, a.id AS source_id, b.id AS target_id
            """

            edges_results = client.run_query(edges_query, {"node_ids": node_ids})
            
            # 解析边
            edges = {}
            for record in edges_results:
                if record.get("r"):
                    edge_data = record["r"]
                    # 添加起点和终点 ID
                    edge_data["source"] = record.get("source_id", "")
                    edge_data["target"] = record.get("target_id", "")
                    
                    relation = self._edge_to_relation(edge_data)
                    if relation and relation.id:
                        edges[relation.id] = relation
            
            return Subgraph(
                nodes=list(nodes.values()),
                edges=list(edges.values())
            )
            
        except Exception as e:
            logger.error(f"Failed to get user graph: {e}")
            return Subgraph()
    
    # ========== 统计 ==========
    
    def count_entities(self, user_id: Optional[int] = None) -> int:
        """统计实体数量（KB 文档实体按部门/层级隔离，记忆实体按 user_id 隔离）"""
        client = self._get_graph_client()
        if not client or not client.is_available():
            return 0

        try:
            if user_id is not None:
                # KB 文档实体（可见文档集合内）+ 用户自己的记忆实体
                query = f"""
                MATCH (n)
                WHERE {self._vis_pred('n')}
                RETURN count(n) as count
                """
                results = client.run_query(query, self._vis_params(user_id))
            else:
                results = client.run_query("MATCH (n) RETURN count(n) as count")

            return results[0].get("count", 0) if results else 0

        except Exception as e:
            logger.error(f"Failed to count entities: {e}")
            return 0

    def count_relations(self, user_id: Optional[int] = None) -> int:
        """统计关系数量（KB 文档关系按部门/层级隔离，记忆关系按 user_id 隔离）"""
        client = self._get_graph_client()
        if not client or not client.is_available():
            return 0

        try:
            if user_id is not None:
                # KB 文档关系（可见文档集合内）+ 用户自己的记忆关系
                query = f"""
                MATCH ()-[r]->()
                WHERE {self._vis_pred('r')}
                RETURN count(r) as count
                """
                results = client.run_query(query, self._vis_params(user_id))
            else:
                results = client.run_query("MATCH ()-[r]->() RETURN count(r) as count")

            return results[0].get("count", 0) if results else 0

        except Exception as e:
            logger.error(f"Failed to count relations: {e}")
            return 0

    # ========== 质量监控统计 ==========

    def get_quality_stats(self, user_id: Optional[int] = None) -> dict:
        """
        获取图谱质量统计

        Returns:
            {
                "entity_count": int,
                "relation_count": int,
                "avg_confidence": float,
                "min_confidence": float,
                "low_confidence_count": int,   # 置信度 < 0.7 的实体数
                "orphan_entity_count": int,   # 孤立实体数（无关系）
                "deleted_entity_count": int,  # 已软删除实体数
                "type_distribution": dict     # 类型分布
            }
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return {}

        result = {
            "entity_count": self.count_entities(user_id),
            "relation_count": self.count_relations(user_id),
        }

        # 与 count_entities / count_relations 使用**同一个**两级可见性谓词。
        # 旧实现用的是 `AND n.user_id = $user_id` —— 那是"只要我自己名下的实体"，
        # 会把 KB 文档实体整个排除掉（除非自己就是上传者），于是同一个面板里
        # entity_count 含 KB 实体、avg_confidence/type_distribution 却不含，
        # 数字自相矛盾；且完全没有部门概念。
        user_filter = ("AND " + self._vis_pred("n")) if user_id is not None else ""
        params = self._vis_params(user_id) if user_id is not None else {}

        # 置信度统计
        try:
            confidence_query = f"""
            MATCH (n)
            WHERE n.deleted_at IS NULL
            {user_filter}
            RETURN
                avg(n.confidence) as avg_confidence,
                min(n.confidence) as min_confidence,
                sum(CASE WHEN n.confidence < 0.7 THEN 1 ELSE 0 END) as low_confidence_count
            """
            conf_results = client.run_query(confidence_query, params)
            if conf_results:
                result["avg_confidence"] = round(conf_results[0].get("avg_confidence") or 0, 3)
                result["min_confidence"] = round(conf_results[0].get("min_confidence") or 0, 3)
                result["low_confidence_count"] = conf_results[0].get("low_confidence_count") or 0
        except Exception as e:
            logger.debug(f"Confidence stats failed: {e}")

        # 孤立实体统计
        try:
            orphan_query = f"""
            MATCH (n)
            WHERE NOT (n)--() AND n.deleted_at IS NULL
            {user_filter}
            RETURN count(n) as orphan_count
            """
            orphan_results = client.run_query(orphan_query, params)
            if orphan_results:
                result["orphan_entity_count"] = orphan_results[0].get("orphan_count") or 0
        except Exception as e:
            logger.debug(f"Orphan stats failed: {e}")

        # 已删除统计
        try:
            deleted_query = f"""
            MATCH (n)
            WHERE n.deleted_at IS NOT NULL
            {user_filter}
            RETURN count(n) as deleted_count
            """
            deleted_results = client.run_query(deleted_query, params)
            if deleted_results:
                result["deleted_entity_count"] = deleted_results[0].get("deleted_count") or 0
        except Exception as e:
            logger.debug(f"Deleted stats failed: {e}")

        # 类型分布
        try:
            type_query = f"""
            MATCH (n)
            WHERE n.deleted_at IS NULL
            {user_filter}
            RETURN n.entity_type as type, count(n) as count
            ORDER BY count DESC
            LIMIT 20
            """
            type_results = client.run_query(type_query, params)
            result["type_distribution"] = {
                r.get("type", "unknown"): r.get("count", 0)
                for r in type_results if r.get("type")
            }
        except Exception as e:
            logger.debug(f"Type distribution failed: {e}")

        return result

    def get_confidence_distribution(self, user_id: Optional[int] = None) -> dict:
        """
        获取置信度分布

        Returns:
            {"high": int, "medium": int, "low": int, "very_low": int}
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return {}

        # 同 get_quality_stats：统一用两级可见性谓词（含部门/层级），
        # 不再用 `AND n.user_id = $user_id` 把 KB 实体整体排除
        user_filter = ("AND " + self._vis_pred("n")) if user_id is not None else ""
        params = self._vis_params(user_id) if user_id is not None else {}

        query = f"""
        MATCH (n)
        WHERE n.deleted_at IS NULL
        {user_filter}
        RETURN
            CASE
                WHEN n.confidence >= 0.9 THEN 'high'
                WHEN n.confidence >= 0.7 THEN 'medium'
                WHEN n.confidence >= 0.5 THEN 'low'
                ELSE 'very_low'
            END as level,
            count(n) as count
        """

        try:
            results = client.run_query(query, params)
            return {
                r.get("level", "unknown"): r.get("count", 0)
                for r in results if r.get("level")
            }
        except Exception as e:
            logger.error(f"Confidence distribution failed: {e}")
            return {}

    def detect_conflicts(self, user_id: Optional[int] = None) -> list:
        """
        检测矛盾关系

        矛盾规则：
        - 同一人同时 WORKS_AT 多个公司（可能矛盾）

        Returns:
            [{"type": str, "person": str, "companies": list}, ...]
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        conflicts = []

        # 检测矛盾的工作关系 —— 两端节点与关系本身都要可见
        # （旧实现只过滤 p.user_id，公司节点 c 与关系 r 完全没校验 → 跨部门/跨用户泄露）
        if user_id is not None:
            user_filter = (
                f"AND {self._vis_pred('p')} AND {self._vis_pred('c')} "
                f"AND {self._vis_pred('r')}"
            )
            params = self._vis_params(user_id)
        else:
            user_filter = ""
            params = {}

        query = f"""
        MATCH (p)-[r:WORKS_AT]->(c)
        WHERE p.deleted_at IS NULL AND c.deleted_at IS NULL
        {user_filter}
        WITH p, collect(DISTINCT c.name) as companies
        WHERE size(companies) > 1
        RETURN p.name as person, companies
        LIMIT 50
        """

        try:
            results = client.run_query(query, params)
            for r in results:
                conflicts.append({
                    "type": "multiple_workplaces",
                    "person": r.get("person"),
                    "companies": r.get("companies", []),
                    "severity": "warning"
                })
        except Exception as e:
            logger.debug(f"Conflict detection failed: {e}")

        return conflicts

    # ========== 文档图谱操作 ==========
    
    def delete_document_entities(self, document_id: int, user_id: Optional[int] = None) -> dict:
        """
        删除文档关联的所有实体和关系

        参考 AGI-saber 的 delete_document 实现：
        1. 删除该文档的所有关系
        2. 清理孤立节点（无其他来源的实体）

        Args:
            document_id: 文档ID
            user_id: 用户ID（用于隔离，防止跨用户删除）

        Returns:
            {"deleted_relations": int, "deleted_entities": int}
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return {"deleted_relations": 0, "deleted_entities": 0}

        result = {"deleted_relations": 0, "deleted_entities": 0}

        try:
            # 构建 user_id 过滤条件
            user_filter = ""
            params = {"doc_id": document_id}
            if user_id is not None:
                user_filter = "AND (r.user_id = $user_id OR r.user_id IS NULL)"
                params["user_id"] = user_id

            # 1. 删除该文档的所有关系
            delete_rel_query = f"""
            MATCH ()-[r {{source_document_id: $doc_id}}]-()
            WHERE r.deleted_at IS NULL
            {user_filter}
            WITH r, count(r) as rel_count
            SET r.deleted_at = datetime()
            RETURN rel_count
            """
            rel_result = client.run_query(delete_rel_query, params)
            if rel_result:
                result["deleted_relations"] = rel_result[0].get("rel_count", 0)

            # 2. 清理孤立节点（该文档的且无其他关系的实体）
            entity_filter = ""
            if user_id is not None:
                entity_filter = "AND (e.user_id = $user_id OR e.user_id IS NULL)"

            delete_entity_query = f"""
            MATCH (e)
            WHERE e.source_document_id = $doc_id
            AND e.deleted_at IS NULL
            {entity_filter}
            AND NOT (e)--()
            WITH e, count(e) as entity_count
            SET e.deleted_at = datetime(), e.version = coalesce(e.version, 1) + 1
            RETURN entity_count
            """
            entity_result = client.run_query(delete_entity_query, params)
            if entity_result:
                result["deleted_entities"] = entity_result[0].get("entity_count", 0)

            logger.info(
                f"[KG] Deleted document entities: doc_id={document_id}, "
                f"relations={result['deleted_relations']}, entities={result['deleted_entities']}"
            )

        except Exception as e:
            logger.error(f"Failed to delete document entities: {e}")

        return result
    
    def index_document_chunks(
        self,
        document_id: int,
        chunks: List[Dict[str, Any]],
        user_id: Optional[int] = None
    ) -> dict:
        """
        为文档的父片提取实体关系并写入图谱

        参考 AGI-saber 的 index_document 实现：
        - 每个父片调用 extractor.extract() 提取实体关系
        - 使用 MERGE 实现幂等写入
        - 使用文档级名称缓存避免重复的 Neo4j 对齐查询

        Args:
            document_id: 文档ID
            chunks: 父片列表 [{"id": int, "content": str}, ...]
            user_id: 用户ID

        Returns:
            {"entities": int, "relations": int, "chunks_processed": int}
        """
        from backend.graphrag.extractor import get_entity_extractor

        client = self._get_graph_client()
        if not client or not client.is_available():
            logger.debug("Graph DB not available, skip document indexing")
            return {"entities": 0, "relations": 0, "chunks_processed": 0}

        extractor = get_entity_extractor()
        result = {"entities": 0, "relations": 0, "chunks_processed": 0}

        # 文档级名称缓存：{entity_name/alias: entity_id}
        # 生命周期跟随单次文档提取，函数结束后自动释放
        # 避免跨父片重复实体（如"刘备"出现 120 次）触发重复的 Neo4j 对齐查询
        name_cache: Dict[str, str] = {}

        try:
            for chunk in chunks:
                chunk_id = chunk.get("id")
                content = chunk.get("content", "")

                if not content or not chunk_id:
                    continue

                # 提取实体关系
                extraction = extractor.extract(
                    text=content,
                    source_document_id=document_id,
                    source_chunk_id=chunk_id
                )

                # 记录低置信度实体和关系（confidence < 0.7 → 审核候选）
                if user_id is not None:
                    # 构建 id→name 映射，用于关系候选记录时解析实体名称
                    # 同时包含 entity.id → name 和 alias → name，覆盖 LLM 可能使用的任何引用
                    entity_name_map: Dict[str, str] = {}
                    for e in extraction.entities:
                        entity_name_map[e.id] = e.name
                        entity_name_map[e.name] = e.name
                        for alias in (e.aliases or []):
                            entity_name_map[alias] = e.name
                    # 也加入跨 chunk 累积的 name_cache 反向映射
                    for cached_name, cached_id in name_cache.items():
                        if cached_name not in entity_name_map:
                            entity_name_map[cached_name] = cached_name
                        # cached_id 的反向映射：若不知道 canonical name 则用 cached_name
                        if cached_id not in entity_name_map:
                            entity_name_map[cached_id] = cached_name
                    for entity in extraction.entities:
                        if entity.confidence < 0.7:
                            self._record_candidate(
                                user_id=user_id,
                                candidate_type="low_confidence",
                                entity_a=entity,
                                score=entity.confidence,
                                reason=f"实体置信度={entity.confidence:.2f}，描述：'{entity.description[:50]}'"
                            )
                    for relation in extraction.relations:
                        if relation.confidence < 0.7:
                            src_name = entity_name_map.get(relation.source_id, relation.source_id)
                            tgt_name = entity_name_map.get(relation.target_id, relation.target_id)
                            self._record_candidate(
                                user_id=user_id,
                                candidate_type="low_confidence",
                                entity_a=Entity(id=relation.source_id, name=src_name, entity_type=EntityType.OTHER),
                                entity_b=Entity(id=relation.target_id, name=tgt_name, entity_type=EntityType.OTHER),
                                score=relation.confidence,
                                reason=f"关系置信度={relation.confidence:.2f}，类型：{relation.relation_type}，描述：'{relation.description[:50]}'"
                            )

                # 写入实体（传入 name_cache 启用快速路径）
                for entity in extraction.entities:
                    success = self.create_entity(entity, user_id, name_cache=name_cache)
                    if success:
                        result["entities"] += 1
                
                # 写入关系
                for relation in extraction.relations:
                    success = self.create_relation(relation, user_id)
                    if success:
                        result["relations"] += 1
                
                result["chunks_processed"] += 1
            
            logger.info(
                f"[KG] Indexed document: doc_id={document_id}, "
                f"entities={result['entities']}, relations={result['relations']}, "
                f"chunks={result['chunks_processed']}"
            )

        except Exception as e:
            logger.error(f"Failed to index document: {e}")

        return result

    def update_document_entities(
        self,
        document_id: int,
        new_chunks: List[Dict[str, Any]],
        user_id: Optional[int] = None
    ) -> dict:
        """
        增量更新文档的图谱实体（对比差异，避免全量重建）

        流程：
        1. 查询文档现有的实体和关系
        2. 从新 chunks 提取新的实体和关系
        3. 对比差异：
           - 已存在且未变化 → 保留
           - 已存在但变化 → 更新
           - 新增 → 创建
           - 删除 → 软删除
        4. 返回变更统计

        Args:
            document_id: 文档ID
            new_chunks: 新的父片列表 [{"id": int, "content": str}, ...]
            user_id: 用户ID

        Returns:
            {"entities_created": int, "entities_updated": int, "entities_deleted": int,
             "relations_created": int, "relations_deleted": int, "chunks_processed": int}
        """
        from backend.graphrag.extractor import get_entity_extractor

        client = self._get_graph_client()
        if not client or not client.is_available():
            logger.debug("Graph DB not available, skip document update")
            return {
                "entities_created": 0, "entities_updated": 0, "entities_deleted": 0,
                "relations_created": 0, "relations_deleted": 0, "chunks_processed": 0
            }

        extractor = get_entity_extractor()
        result = {
            "entities_created": 0, "entities_updated": 0, "entities_deleted": 0,
            "relations_created": 0, "relations_deleted": 0, "chunks_processed": 0
        }

        try:
            # 1. 查询文档现有实体（包含 chunk_id）
            existing_entities = self.get_document_entities(document_id, user_id=user_id)
            existing_entity_map = {e.id: e for e in existing_entities}

            # 构建实体签名映射（用于检测变更）
            # 签名 = hash(name + type + description)
            def _entity_signature(entity) -> str:
                import hashlib
                content = f"{entity.name}|{entity.entity_type.value}|{entity.description or ''}"
                return hashlib.md5(content.encode()).hexdigest()

            existing_signatures = {
                e.id: _entity_signature(e)
                for e in existing_entities
            }

            # 2. 从新 chunks 提取实体
            name_cache: Dict[str, str] = {}
            new_entities_by_chunk: Dict[int, List[Entity]] = {}
            new_relations_by_chunk: Dict[int, List[Relation]] = {}

            for chunk in new_chunks:
                chunk_id = chunk.get("id")
                content = chunk.get("content", "")

                if not content or not chunk_id:
                    continue

                extraction = extractor.extract(
                    text=content,
                    source_document_id=document_id,
                    source_chunk_id=chunk_id
                )

                new_entities_by_chunk[chunk_id] = extraction.entities
                new_relations_by_chunk[chunk_id] = extraction.relations
                result["chunks_processed"] += 1

            # 3. 扁平化新实体，计算签名
            all_new_entities = []
            for entities in new_entities_by_chunk.values():
                all_new_entities.extend(entities)

            new_entity_signatures = {}
            for e in all_new_entities:
                # 生成临时 ID（基于名称 + 类型）
                temp_id = f"temp_{e.name}_{e.entity_type.value}"
                new_entity_signatures[temp_id] = {
                    "entity": e,
                    "signature": _entity_signature(e)
                }

            # 4. 对比差异
            # 4.1 找出需要删除的实体（在新版本中不存在）
            new_names_types = {(e.name, e.entity_type.value) for e in all_new_entities}
            for existing_e in existing_entities:
                key = (existing_e.name, existing_e.entity_type.value)
                if key not in new_names_types:
                    # 软删除
                    if self.delete_entity(existing_e.id, soft=True):
                        result["entities_deleted"] += 1
                        # 同时删除相关关系
                        deleted_relations = self._delete_relations_by_entity(existing_e.id)
                        result["relations_deleted"] += deleted_relations

            # 4.2 创建新实体或更新已有实体
            for chunk_entities in new_entities_by_chunk.values():
                for new_e in chunk_entities:
                    # 尝试匹配已有实体（按名称 + 类型）
                    existing_match = None
                    for existing_e in existing_entities:
                        if existing_e.name == new_e.name and existing_e.entity_type == new_e.entity_type:
                            existing_match = existing_e
                            break

                    if existing_match:
                        # 已存在：检查是否需要更新
                        old_sig = existing_signatures.get(existing_match.id, "")
                        new_sig = _entity_signature(new_e)

                        if old_sig != new_sig:
                            # 有变更：更新描述、置信度等
                            success = self.update_entity(
                                existing_match.id,
                                description=new_e.description,
                                confidence=new_e.confidence,
                                source_chunk_id=new_e.source_chunk_id
                            )
                            if success:
                                result["entities_updated"] += 1
                    else:
                        # 不存在：创建新实体
                        success = self.create_entity(new_e, user_id, name_cache=name_cache)
                        if success:
                            result["entities_created"] += 1

            # 4.3 创建新关系
            existing_relations = self.get_document_relations(document_id, user_id=user_id)
            existing_relation_keys = {
                (r.source_id, r.target_id, r.relation_type.value)
                for r in existing_relations
            }

            for chunk_relations in new_relations_by_chunk.values():
                for new_r in chunk_relations:
                    # 解析源和目标实体 ID
                    source_id = self._resolve_entity_id(new_r.source_id, name_cache, all_new_entities)
                    target_id = self._resolve_entity_id(new_r.target_id, name_cache, all_new_entities)

                    if not source_id or not target_id:
                        continue

                    key = (source_id, target_id, new_r.relation_type.value)
                    if key not in existing_relation_keys:
                        # 创建新关系
                        new_r.source_id = source_id
                        new_r.target_id = target_id
                        success = self.create_relation(new_r, user_id)
                        if success:
                            result["relations_created"] += 1

            logger.info(
                f"[KG] Updated document: doc_id={document_id}, "
                f"entities +{result['entities_created']} ~{result['entities_updated']} -{result['entities_deleted']}, "
                f"relations +{result['relations_created']} -{result['relations_deleted']}, "
                f"chunks={result['chunks_processed']}"
            )

        except Exception as e:
            logger.error(f"Failed to update document entities: {e}")

        return result

    def _delete_relations_by_entity(self, entity_id: str) -> int:
        """删除与实体相关的所有关系（内部方法）"""
        client = self._get_graph_client()
        if not client or not client.is_available():
            return 0

        try:
            # Cypher 查询：删除涉及该实体的所有关系
            query = """
                MATCH (e {id: $entity_id})-[r]-()
                DELETE r
                RETURN count(r) as deleted
            """
            result = client.run(query, entity_id=entity_id)
            deleted = result[0]["deleted"] if result else 0
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete relations for entity {entity_id}: {e}")
            return 0

    def _resolve_entity_id(
        self,
        reference: str,
        name_cache: Dict[str, str],
        entities: List
    ) -> Optional[str]:
        """
        解析实体引用为实体 ID

        Args:
            reference: 实体引用（可能是名称、别名或 ID）
            name_cache: 名称到 ID 的映射
            entities: 实体列表

        Returns:
            实体 ID 或 None
        """
        # 1. 直接是 ID（以 "ent_" 或类似前缀开头）
        if reference.startswith("ent_") or "_" in reference:
            # 可能是 ID，检查是否在 name_cache 中
            if reference in name_cache:
                return name_cache[reference]
            # 检查是否是真实 ID
            for e in entities:
                if e.id == reference:
                    return reference

        # 2. 是名称，查找对应 ID
        if reference in name_cache:
            return name_cache[reference]

        # 3. 遍历实体列表查找
        for e in entities:
            if e.name == reference or reference in (e.aliases or []):
                return e.id

        return None

    def get_document_relations(
        self,
        document_id: int,
        user_id: Optional[int] = None
    ) -> List[Relation]:
        """
        获取文档的所有关系

        Args:
            document_id: 文档ID
            user_id: 用户ID（用于隔离）

        Returns:
            Relation 列表
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return []

        visible_doc_ids = self._get_visible_doc_ids(user_id)

        try:
            query = """
                MATCH (e1)-[r]->(e2)
                WHERE e1.source_document_id = $doc_id
                   OR e2.source_document_id = $doc_id
                RETURN r
            """
            results = client.run(query, doc_id=document_id)

            relations = []
            for row in results:
                rel_data = dict(row.get("r", {}))
                if rel_data:
                    relation = self._dict_to_relation(rel_data)
                    if relation:
                        relations.append(relation)

            return relations

        except Exception as e:
            logger.error(f"Failed to get document relations: {e}")
            return []

    def update_entity(
        self,
        entity_id: str,
        description: Optional[str] = None,
        confidence: Optional[float] = None,
        source_chunk_id: Optional[int] = None,
        properties: Optional[Dict] = None
    ) -> bool:
        """
        更新实体属性（增量更新）

        Args:
            entity_id: 实体ID
            description: 新描述（可选）
            confidence: 新置信度（可选）
            source_chunk_id: 新来源父片ID（可选）
            properties: 新属性字典（可选）

        Returns:
            是否成功
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return False

        try:
            # 构建动态 SET 子句
            set_clauses = []
            params = {"entity_id": entity_id}

            if description is not None:
                set_clauses.append("e.description = $description")
                params["description"] = description

            if confidence is not None:
                set_clauses.append("e.confidence = $confidence")
                params["confidence"] = confidence

            if source_chunk_id is not None:
                set_clauses.append("e.source_chunk_id = $source_chunk_id")
                params["source_chunk_id"] = source_chunk_id

            if properties:
                for key, value in properties.items():
                    set_clauses.append(f"e.{key} = ${key}")
                    params[key] = value

            if not set_clauses:
                return True  # 无需更新

            set_clauses.append("e.updated_at = timestamp()")

            query = f"""
                MATCH (e {{id: $entity_id}})
                SET {', '.join(set_clauses)}
                RETURN e
            """

            result = client.run(query, **params)
            return len(result) > 0

        except Exception as e:
            logger.error(f"Failed to update entity {entity_id}: {e}")
            return False

    # ========== 辅助方法 ==========
    
    def _dict_to_entity(self, data: dict) -> Optional[Entity]:
        """将字典转换为 Entity"""
        if not data:
            return None
        
        try:
            entity_type = EntityType.OTHER
            # 支持从 entity_type 或 _entity_type 字段获取类型
            type_str = data.get("entity_type") or data.get("_entity_type", "")
            if isinstance(type_str, str):
                type_str = type_str.lower()
            if type_str:
                try:
                    entity_type = EntityType(type_str)
                except ValueError:
                    pass
            
            return Entity(
                id=data.get("id", ""),
                name=data.get("name", ""),
                entity_type=entity_type,
                description=data.get("description", ""),
                source_memory_id=data.get("source_memory_id"),
                source_document_id=data.get("source_document_id"),
                source_chunk_id=data.get("source_chunk_id"),
                confidence=data.get("confidence", 1.0),
                properties={k: v for k, v in data.items() 
                           if k not in ["id", "name", "entity_type", "_entity_type", "description", 
                                        "source_memory_id", "source_document_id", 
                                        "source_chunk_id", "confidence"]}
            )
        except Exception:
            return None
    
    def _dict_to_relation(self, data: dict) -> Optional[Relation]:
        """将字典转换为 Relation"""
        if not data:
            return None
        
        try:
            return Relation(
                id=str(data.get("id", "")),
                source_id=data.get("source", ""),
                target_id=data.get("target", ""),
                relation_type=RelationType.RELATED_TO,
                description=data.get("description", ""),
                confidence=data.get("confidence", 1.0)
            )
        except Exception:
            return None
    
    def _edge_to_relation(self, edge_data: dict) -> Optional[Relation]:
        """将 Neo4j 边数据转换为 Relation"""
        if not edge_data:
            return None
        
        try:
            rel_type = edge_data.get("type", "RELATED_TO")
            try:
                relation_type = RelationType(rel_type.lower())
            except ValueError:
                relation_type = RelationType.RELATED_TO
            
            return Relation(
                id=str(edge_data.get("id", "")),
                source_id=str(edge_data.get("source", "")),
                target_id=str(edge_data.get("target", "")),
                relation_type=relation_type,
                description=edge_data.get("properties", {}).get("description", ""),
                confidence=edge_data.get("properties", {}).get("confidence", 1.0)
            )
        except Exception:
            return None
    
    def _edge_to_relation_simple(self, edge_data: dict) -> Optional[Relation]:
        """将简化的边数据转换为 Relation（用于子图查询）"""
        if not edge_data:
            return None
        
        try:
            rel_type = edge_data.get("type", "RELATED_TO")
            try:
                relation_type = RelationType(rel_type.lower())
            except ValueError:
                relation_type = RelationType.RELATED_TO
            
            source_id = edge_data.get("source", "")
            target_id = edge_data.get("target", "")
            
            if not source_id or not target_id:
                return None
            
            # 生成唯一 ID
            rel_id = f"rel_{source_id}_{target_id}"
            
            return Relation(
                id=rel_id,
                source_id=str(source_id),
                target_id=str(target_id),
                relation_type=relation_type,
                description=edge_data.get("properties", {}).get("description", ""),
                confidence=edge_data.get("properties", {}).get("confidence", 1.0)
            )
        except Exception:
            return None
    
    def _infer_entity_type(self, labels: list) -> str:
        """从 Neo4j 标签推断实体类型"""
        # 标签到实体类型的映射
        label_map = {
            "Project": "project",
            "Concept": "concept",
            "Tool": "tool",
            "Skill": "skill",
            "Person": "person",
            "Organization": "org",
            "Location": "location",
            "Event": "event",
            "Preference": "preference",
            "Fact": "fact",
            "Entity": "other"
        }

        for label in labels:
            if label in label_map:
                return label_map[label]

        return "other"

    # ========== GraphRAG 检索增强 ==========

    def retrieve_by_query(
        self,
        query: str,
        user_id: Optional[int] = None,
        top_k: int = 10,
        enable_archive_fallback: bool = True
    ) -> List[Dict]:
        """
        基于查询的图谱检索（GraphRAG）

        流程：
        1. 从 query 提取实体（调用 EntityExtractor）
        2. 在图谱中查找匹配实体
        3. 扩展实体的邻居和关系
        4. 返回相关上下文
        5. （可选）找不到时降级查 MySQL 归档表

        Args:
            query: 用户查询文本
            user_id: 用户ID（用于隔离）
            top_k: 返回结果数量
            enable_archive_fallback: 是否启用归档表回查（默认 True）

        Returns:
            [{"entity": Entity, "context": str, "score": float, "source_chunk_id": int, "is_archived": bool}, ...]
        """
        from backend.graphrag.extractor import get_entity_extractor

        client = self._get_graph_client()
        if not client or not client.is_available():
            # Neo4j 不可用时，尝试从归档表查询
            if enable_archive_fallback:
                return self._retrieve_from_archive(query, user_id, top_k)
            return []

        try:
            # 1. 从查询中提取实体
            extractor = get_entity_extractor()
            extraction = extractor.extract(query)

            if not extraction.entities:
                # 没有提取到实体，尝试从归档表查询
                if enable_archive_fallback:
                    return self._retrieve_from_archive(query, user_id, top_k)
                return []

            results = []
            seen_entity_ids = set()

            # 2. 对每个提取的实体，在图谱中查找匹配
            for entity in extraction.entities[:5]:  # 最多处理5个实体
                # 查找匹配实体
                matches = self.search_entities(
                    entity.name,
                    entity_type=entity.entity_type,
                    user_id=user_id,
                    limit=3
                )

                for match in matches:
                    if match.id in seen_entity_ids:
                        continue
                    seen_entity_ids.add(match.id)

                    # 3. 获取子图作为上下文（动态深度调整）
                    # 核心实体（高置信度、重要类型）使用 2 跳，普通实体使用 1 跳
                    depth = self._calculate_search_depth(entity, match)

                    subgraph = self.get_subgraph(match.id, depth=depth, user_id=user_id)

                    # 4. 构建上下文文本
                    context = self._subgraph_to_context(subgraph)

                    # 5. 更新访问统计（用于冷热分离）
                    self.update_access_stats(match.id)

                    results.append({
                        "entity": match,
                        "context": context,
                        "score": match.confidence,
                        "source_chunk_id": match.source_chunk_id,
                        "source_memory_id": match.source_memory_id,  # 记忆来源
                        "is_archived": False,  # 标记来源
                        "search_depth": depth  # 记录实际搜索深度
                    })

            # 6. 降级回查归档表（如果主查询结果为空）
            if not results and enable_archive_fallback:
                archive_results = self._retrieve_from_archive(query, user_id, top_k)
                for r in archive_results:
                    r["is_archived"] = True
                    results.append(r)

            # 7. 按分数排序
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]

        except Exception as e:
            logger.error(f"[GraphRAG] retrieve_by_query failed: {e}")
            # 异常时尝试归档表回查
            if enable_archive_fallback:
                return self._retrieve_from_archive(query, user_id, top_k)
            return []

    def _subgraph_to_context(self, subgraph: Subgraph) -> str:
        """
        将子图转换为上下文文本（供 LLM 使用）

        Args:
            subgraph: 子图对象

        Returns:
            格式化的上下文文本
        """
        lines = []

        # 实体信息
        for node in subgraph.nodes:
            lines.append(f"- {node.name}({node.entity_type.value}): {node.description}")

        # 关系信息
        for edge in subgraph.edges:
            source = next((n for n in subgraph.nodes if n.id == edge.source_id), None)
            target = next((n for n in subgraph.nodes if n.id == edge.target_id), None)
            if source and target:
                lines.append(f"- {source.name} --[{edge.relation_type.value}]--> {target.name}")

        return "\n".join(lines) if lines else ""

    def update_access_stats(self, entity_id: str) -> bool:
        """
        更新实体访问统计（用于冷热分离）

        Args:
            entity_id: 实体ID

        Returns:
            是否成功
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return False

        try:
            query = """
            MATCH (n {id: $entity_id})
            SET n.last_accessed_at = datetime(),
                n.access_count = coalesce(n.access_count, 0) + 1
            """
            client.run_query(query, {"entity_id": entity_id})
            return True
        except Exception as e:
            logger.debug(f"[KG] update_access_stats failed: {e}")
            return False

    def _retrieve_from_archive(
        self,
        query: str,
        user_id: Optional[int] = None,
        top_k: int = 10
    ) -> List[Dict]:
        """
        从 MySQL 归档表回查实体（降级方案）

        当 Neo4j 中找不到实体时，尝试从归档表查询。
        注意：归档表的数据不会被"激活"回 Neo4j，只是作为只读结果返回。

        Args:
            query: 查询文本
            user_id: 用户ID（用于过滤）
            top_k: 返回数量

        Returns:
            归档实体列表（格式同 retrieve_by_query）
        """
        import json as _json
        from backend.db.schema import get_conn
        from backend.graphrag.extractor import get_entity_extractor

        try:
            # 1. 从查询中提取实体名称
            extractor = get_entity_extractor()
            extraction = extractor.extract(query)

            if not extraction.entities:
                return []

            entity_names = [e.name for e in extraction.entities[:5]]

            # 2. 查询归档表
            # ⚠️ 归档表没有 source_document_id 列（只在 data JSON 里），也没有层级信息，
            #    所以部门隔离只能在 Python 侧按同一套两级规则做。
            #    旧 SQL 是 `user_id = %s OR user_id IS NULL`，两个方向都不对：
            #      - 放行了 user_id 为 NULL 的归档行 → 对任何人可见（跨用户泄露）；
            #      - 漏掉"归档时 user_id 记成上传者、但我在同一部门"的 KB 实体。
            #    这里改为不在 SQL 里做归属判断，只多取一些候选，再由下面统一过滤。
            visible_docs = set(self._visible_doc_ids(user_id)) if user_id is not None else None

            conn = get_conn()
            try:
                placeholders = ",".join(["%s"] * len(entity_names))
                sql = f"""
                SELECT entity_id, name, entity_type, user_id, data
                FROM kg_archived_entities
                WHERE name IN ({placeholders})
                LIMIT %s
                """
                params = list(entity_names) + [max(top_k * 5, top_k)]

                cur = conn.execute(sql, tuple(params))
                rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            finally:
                conn.close()

            if not rows:
                return []

            # 3. 转换为统一格式
            results = []
            for row in rows:
                data = row.get("data")
                if isinstance(data, str):
                    try:
                        data = _json.loads(data)
                    except (TypeError, ValueError):
                        continue

                entity = Entity.from_dict(data) if data else None
                if not entity:
                    continue

                # ── 两级可见性（与 Cypher 侧同一套规则）──
                if visible_docs is not None:
                    if entity.source_document_id is not None:
                        # KB 文档实体 → 必须落在可见文档集合内（部门/层级隔离）
                        try:
                            if int(entity.source_document_id) not in visible_docs:
                                continue
                        except (TypeError, ValueError):
                            continue
                    else:
                        # 记忆实体 → 必须属于本人
                        try:
                            if int(row.get("user_id")) != int(user_id):
                                continue
                        except (TypeError, ValueError):
                            continue

                # 归档数据没有子图上下文，只返回实体基本信息
                context = f"- {entity.name}({entity.entity_type.value}): {entity.description}"

                results.append({
                    "entity": entity,
                    "context": context,
                    "score": entity.confidence * 0.8,  # 归档数据降权
                    "source_chunk_id": entity.source_chunk_id,
                    "is_archived": True
                })

            logger.debug(f"[KG] Retrieved {len(results)} entities from archive")
            return results[:top_k]

        except Exception as e:
            logger.warning(f"[KG] _retrieve_from_archive failed: {e}")
            return []

    # ========== 冷热分离（P2 优化） ==========

    def archive_cold_entities(
        self,
        days_threshold: int = 30,
        access_threshold: int = 3,
        batch_size: int = 1000
    ) -> dict:
        """
        归档冷数据到 MySQL

        冷数据判定规则：
        - 未删除（deleted_at IS NULL）
        - 超过 N 天未访问（last_accessed_at 为空或超过阈值）
        - 访问次数少于 M 次

        Args:
            days_threshold: 天数阈值（默认30天）
            access_threshold: 访问次数阈值（默认3次）
            batch_size: 批量处理大小

        Returns:
            {"archived": int, "failed": int, "deleted_from_neo4j": int}
        """
        import json as _json

        client = self._get_graph_client()
        if not client or not client.is_available():
            return {"archived": 0, "failed": 0, "deleted_from_neo4j": 0}

        result = {"archived": 0, "failed": 0, "deleted_from_neo4j": 0}

        try:
            # 1. 查找冷数据
            query = """
            MATCH (n)
            WHERE n.deleted_at IS NULL
            AND (n.last_accessed_at IS NULL
                 OR duration.between(n.last_accessed_at, datetime()).days > $days)
            AND coalesce(n.access_count, 0) < $access_threshold
            RETURN n
            LIMIT $batch_size
            """

            cold_entities = client.run_query(query, {
                "days": days_threshold,
                "access_threshold": access_threshold,
                "batch_size": batch_size
            })

            if not cold_entities:
                logger.info("[KG] No cold entities to archive")
                return result

            logger.info(f"[KG] Found {len(cold_entities)} cold entities to archive")

            # 2. 批量归档到 MySQL
            archived_ids = []
            for record in cold_entities:
                node = record.get("n")
                if not node:
                    continue

                entity = self._dict_to_entity(dict(node))
                if not entity:
                    continue

                # 归档到 MySQL
                if self._archive_to_mysql(entity):
                    result["archived"] += 1
                    archived_ids.append(entity.id)
                else:
                    result["failed"] += 1

            # 3. 从 Neo4j 标记为已归档（软删除 + 设置 archived 标志）
            if archived_ids:
                self._mark_as_archived(archived_ids)
                result["deleted_from_neo4j"] = len(archived_ids)

            logger.info(
                f"[KG] Archive complete: archived={result['archived']}, "
                f"failed={result['failed']}, deleted_from_neo4j={result['deleted_from_neo4j']}"
            )

        except Exception as e:
            logger.error(f"[KG] archive_cold_entities failed: {e}")

        return result

    def _archive_to_mysql(self, entity: Entity) -> bool:
        """
        归档实体到 MySQL

        Args:
            entity: 实体对象

        Returns:
            是否成功
        """
        import json as _json
        from backend.db.schema import get_conn

        # 从 entity.properties 获取 user_id
        user_id = entity.properties.get("user_id") if entity.properties else None

        conn = get_conn()
        try:
            conn.execute(
                """INSERT INTO kg_archived_entities
                (entity_id, name, entity_type, user_id, data, archived_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE data = VALUES(data), archived_at = NOW(), user_id = VALUES(user_id)""",
                (
                    entity.id,
                    entity.name,
                    entity.entity_type.value,
                    user_id,
                    _json.dumps(entity.to_dict(), ensure_ascii=False)
                )
            )
            conn.commit()
            return True
        except Exception as e:
            logger.warning(f"[KG] Archive to MySQL failed for {entity.id}: {e}")
            return False
        finally:
            conn.close()

    def _mark_as_archived(self, entity_ids: List[str]) -> None:
        """
        标记实体为已归档（从 Neo4j 软删除）

        Args:
            entity_ids: 实体ID列表
        """
        client = self._get_graph_client()
        if not client or not client.is_available():
            return

        try:
            # 批量软删除（设置 archived 标志 + deleted_at）
            for entity_id in entity_ids:
                query = """
                MATCH (n {id: $entity_id})
                SET n.archived = true,
                    n.deleted_at = datetime(),
                    n.archive_time = datetime()
                """
                client.run_query(query, {"entity_id": entity_id})
        except Exception as e:
            logger.warning(f"[KG] Mark as archived failed: {e}")

    def restore_archived_entity(self, entity_id: str) -> bool:
        """
        恢复已归档的实体

        从 MySQL 归档表读取实体数据，重新写入 Neo4j

        Args:
            entity_id: 实体ID

        Returns:
            是否成功
        """
        import json as _json
        from backend.db.schema import get_conn

        # 1. 从 MySQL 读取归档数据（包含 user_id 用于归属恢复）
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT data, user_id FROM kg_archived_entities WHERE entity_id = %s",
                (entity_id,)
            )
            row = cur.fetchone() if hasattr(cur, "fetchone") else None
            if not row:
                logger.warning(f"[KG] Archived entity not found: {entity_id}")
                return False

            data = _json.loads(row.get("data", "{}")) if isinstance(row.get("data"), str) else row.get("data", {})
            archived_user_id = row.get("user_id")  # 保存归档记录的 user_id
        finally:
            conn.close()

        # 2. 恢复实体
        try:
            entity = Entity.from_dict(data)
            # 清除归档相关字段
            entity.deleted_at = None

            # 写入 Neo4j（禁用实体对齐，避免冲突；传递 user_id 恢复归属）
            success = self.create_entity(entity, user_id=archived_user_id, enable_alignment=False)

            if success:
                # 从 MySQL 归档表删除
                conn = get_conn()
                try:
                    conn.execute(
                        "DELETE FROM kg_archived_entities WHERE entity_id = %s",
                        (entity_id,)
                    )
                    conn.commit()
                finally:
                    conn.close()

                logger.info(f"[KG] Restored archived entity: {entity_id}")

            return success

        except Exception as e:
            logger.error(f"[KG] Restore archived entity failed: {e}")
            return False

    def get_archive_stats(self) -> dict:
        """
        获取归档统计信息

        Returns:
            {"archived_count": int, "oldest_archive": str, "total_size_mb": float}
        """
        from backend.db.schema import get_conn

        conn = get_conn()
        try:
            # 归档数量
            cur = conn.execute("SELECT COUNT(*) as cnt FROM kg_archived_entities")
            row = cur.fetchone() if hasattr(cur, "fetchone") else None
            archived_count = row.get("cnt", 0) if row else 0

            # 最早归档时间
            cur = conn.execute("SELECT MIN(archived_at) as oldest FROM kg_archived_entities")
            row = cur.fetchone() if hasattr(cur, "fetchone") else None
            oldest_archive = str(row.get("oldest", "")) if row else ""

            # 估算大小（假设每条记录约 1KB）
            total_size_mb = round(archived_count * 1.0 / 1024, 2)  # MB

            return {
                "archived_count": archived_count,
                "oldest_archive": oldest_archive,
                "total_size_mb": total_size_mb
            }
        except Exception as e:
            logger.warning(f"[KG] get_archive_stats failed: {e}")
            return {"archived_count": 0, "oldest_archive": "", "total_size_mb": 0}
        finally:
            conn.close()


# 单例访问
_kg_store: Optional[KGStore] = None


def get_kg_store() -> KGStore:
    """获取 KGStore 单例"""
    global _kg_store
    if _kg_store is None:
        _kg_store = KGStore()
    return _kg_store