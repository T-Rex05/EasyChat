"""
Graph Memory - 记忆图谱增强层

与 KGStore 的区别：
- KGStore：文档图谱，处理 Entity/Relation
- GraphMemory：记忆图谱，处理 Memory 节点和 FOLLOWS/SIMILAR_TO 边

边类型：
- FOLLOWS: 时序相邻（上一条对话记忆 → 当前）
- SIMILAR_TO: 语义相似度超阈值（存储时自动连接）
- CAUSES: 因果推断（LLM 提取，可选）
- BELONGS_TO: 话题归属
"""

import logging
import math
import threading
from typing import List, Optional, Any, Dict

from backend.memory.types import MemoryItem
from backend.infrastructure.safe_executor import go_safe

logger = logging.getLogger(__name__)


class GraphMemory:
    """
    长期记忆的图增强层
    
    持有 Neo4jClient 直接操作 :Memory 节点和边。
    Neo4jClient 不可用时所有方法静默返回，调用方无需关心降级。
    """
    
    # 边类型常量
    EDGE_FOLLOWS = "FOLLOWS"        # 时序相邻
    EDGE_SIMILAR_TO = "SIMILAR_TO"  # 语义相似
    EDGE_CAUSES = "CAUSES"          # 因果推断
    EDGE_BELONGS_TO = "BELONGS_TO"  # 话题归属

    # ══════════════════════════════════════════════════════════
    # Memory 节点的身份键：**必须带层级维度**
    # ══════════════════════════════════════════════════════════
    # 为什么不能只用 mem_id：`memory_episodic` 与 `memory_semantic` 的 id 各自从 1
    # 开始自增，实测 **218 条 semantic 记忆全部与 episodic 重号**（其中 194 条归属不同）。
    # 若 `MERGE (m:Memory {mem_id: $id})` 只按 id 认身份，两条不同记忆会被合并成
    # 同一个节点 —— 后写的覆盖 content / user_id，另一条直接从图谱里消失。
    # 故键 = "{layer}:{id}"；layer 缺失时退化为 "legacy:{id}"（仍与显式层级区分开）。
    LAYER_LEGACY = "legacy"

    @classmethod
    def _mem_key(cls, mem_id: Any, layer: Optional[str] = None) -> str:
        """生成 Memory 节点的身份键（层级 + id）。"""
        lyr = (str(layer).strip().lower() if layer else "") or cls.LAYER_LEGACY
        return f"{lyr}:{int(mem_id)}"

    @classmethod
    def _key_expr(cls, var: str = "m") -> str:
        """Cypher 侧的键表达式：节点没有 mem_key 时退化为 'legacy:<id>'。

        这样即使迁移脚本还没跑，也能address到历史节点；迁移跑完后 mem_key 生效。
        """
        return f"coalesce({var}.mem_key, '{cls.LAYER_LEGACY}:' + toString({var}.mem_id))"
    
    def __init__(
        self,
        similarity_threshold: float = 0.7,
        indegree_protect_threshold: int = 3,
        max_hops: int = 2
    ):
        """
        初始化 GraphMemory
        
        Args:
            similarity_threshold: SIMILAR_TO 边的相似度阈值
            indegree_protect_threshold: 图中心度保护阈值（入度 >= 此值的节点免于删除）
            max_hops: 检索时最大跳数
        """
        self._graph_client = None
        self._sim_threshold = similarity_threshold
        self._indegree_threshold = indegree_protect_threshold
        self._max_hops = max_hops
        
        # 上一个记忆 ID（用于建立 FOLLOWS 边），按 user_id 隔离
        self._prev_ids: Dict[int, int] = {}
        self._prev_id_lock = threading.Lock()
        self._prev_ids_max_size = 10000  # 防止无界增长
        
        # LongTerm 反向引用（用于代理方法）
        self._ltm: Optional[Any] = None
    
    def _get_graph_client(self):
        """获取图客户端（延迟加载）"""
        if self._graph_client is None:
            try:
                from backend.infrastructure import get_graph_client
                self._graph_client = get_graph_client()
            except Exception as e:
                logger.debug(f"Graph client not available: {e}")
        return self._graph_client
    
    def _available(self) -> bool:
        """检查图数据库是否可用"""
        client = self._get_graph_client()
        return client is not None and client.is_available()
    
    def set_ltm(self, ltm: Optional[Any]) -> None:
        """挂载 LongTerm 反向引用"""
        self._ltm = ltm
    
    # ========== 核心操作 ==========
    
    def add_to_graph(
        self,
        item: MemoryItem,
        neighbors: Optional[List[MemoryItem]] = None,
        user_id: Optional[int] = None
    ) -> int:
        """
        将记忆同步进图（异步执行，主路径不阻塞）
        
        流程：
        1. 主线程计算 mem_id 和 prev_id
        2. 后台线程执行节点 upsert 和边写入
        3. 失败不影响主路径
        
        Args:
            item: 记忆条目
            neighbors: 邻居记忆（用于建立 SIMILAR_TO 边）
            user_id: 用户ID（用于用户隔离）
            
        Returns:
            mem_id，不可用时返回 -1
        """
        if not self._available() or item.id is None:
            return -1
        
        mem_id = int(item.id)
        content = item.content
        importance = item.importance
        category = item.category or "general"
        uid = user_id or item.user_id  # 优先使用参数，其次使用 item 的 user_id
        layer = item.layer  # 层级维度：Memory 节点身份的一部分（见 _mem_key）
        
        # 获取 prev（用于 FOLLOWS 边，按用户隔离）：存 (mem_id, layer) 以还原正确的键
        with self._prev_id_lock:
            prev = self._prev_ids.get(uid)
        prev_id = prev[0] if prev else -1
        prev_layer = prev[1] if prev else None
        
        # 复制邻居 embedding 避免竞争
        neighbor_pairs = []
        if neighbors and item.embedding:
            for old in neighbors:
                if old is item or old.id == mem_id:
                    continue
                if old.embedding and len(old.embedding) == len(item.embedding):
                    neighbor_pairs.append((old.id, old.embedding, item.embedding, old.layer))
        
        def _write():
            # 1. upsert 节点（包含 user_id 与 layer）
            self._upsert_memory_node(mem_id, content, importance, category, uid, layer)
            
            # 2. FOLLOWS 边（时序链）- 仅同用户
            if prev_id >= 0 and prev_id != mem_id:
                self._add_memory_edge(prev_id, mem_id, self.EDGE_FOLLOWS, 1.0,
                                      from_layer=prev_layer, to_layer=layer)
            
            # 3. SIMILAR_TO 边（语义相似）- 仅同用户
            for old_id, old_emb, new_emb, old_layer in neighbor_pairs:
                sim = self._cosine(old_emb, new_emb)
                if sim >= self._sim_threshold:
                    self._add_memory_edge(old_id, mem_id, self.EDGE_SIMILAR_TO, sim,
                                          from_layer=old_layer, to_layer=layer)
        
        go_safe("graph_memory.add_to_graph", _write)
        
        # 更新 prev（按用户隔离，防止无界增长）
        with self._prev_id_lock:
            self._prev_ids[uid] = (mem_id, layer)
            if len(self._prev_ids) > self._prev_ids_max_size:
                # 淘汰一半旧条目（简单策略：保留最近插入的）
                keys = list(self._prev_ids.keys())
                for k in keys[:len(keys) // 2]:
                    del self._prev_ids[k]
        
        return mem_id
    
    def find_related(self, item_id: int, max_hops: Optional[int] = None,
                     user_id: Optional[int] = None, layer: Optional[str] = None) -> List[int]:
        """
        从记忆出发，沿图扩展关联记忆
        
        Args:
            item_id: 种子记忆 ID
            max_hops: 最大跳数（默认使用配置值）
            user_id: 用户ID（用于用户隔离，只返回同用户的关联记忆）
            
        Returns:
            关联记忆 ID 列表
        """
        if not self._available():
            return []
        
        client = self._get_graph_client()
        hops = max_hops if max_hops is not None else self._max_hops
        # 安全校验 hops 范围
        hops = max(1, min(int(hops), 5))
        
        # 构建查询：从种子记忆出发，遍历所有边类型
        # 如果指定了 user_id，则只返回同用户的关联记忆
        # ⚠️ 种子必须按 mem_key 定位（给了 layer 时）。若只按 mem_id，两条重号记忆
        #    会命中同一个节点 —— 等于从"别人的记忆"出发做扩展。
        if user_id is not None:
            if layer:
                seed_match = f"MATCH (m:Memory) WHERE {self._key_expr('m')} = $seed_key"
                params = {"seed_key": self._mem_key(item_id, layer), "id": item_id,
                          "user_id": user_id}
            else:
                # 未给层级（老调用方）：退回按 id 匹配任意层，靠 n.user_id 兜住安全
                seed_match = "MATCH (m:Memory {mem_id: $id})"
                params = {"id": item_id, "user_id": user_id}
            query = f"""
            {seed_match}
            MATCH (m)-[:FOLLOWS|SIMILAR_TO|CAUSES|BELONGS_TO*1..{hops}]-(n:Memory)
            WHERE n.mem_id <> $id AND n.user_id = $user_id
            RETURN DISTINCT n.mem_id AS related_id
            """
        else:
            # 无 user_id 时仅返回空（防止跨用户泄露）
            logger.warning("find_related called without user_id, returning empty for safety")
            return []
        
        try:
            results = client.run_query(query, params)
            return [r.get("related_id") for r in results if r.get("related_id") is not None]
        except Exception as e:
            logger.warning(f"find_related failed: {e}")
            return []
    
    def delete_from_graph(self, item_id: int, user_id: Optional[int] = None,
                          layer: Optional[str] = None) -> None:
        """
        从图中删除记忆节点（连同其所有边）

        Args:
            item_id: 记忆 ID
            user_id: 可选，校验节点归属
            layer: 可选，记忆层级；给了就按 mem_key 精确删（避免把重号的另一层删掉）
        """
        if not self._available():
            return

        client = self._get_graph_client()
        conds, params = [], {"id": item_id}
        if layer:
            conds.append(f"{self._key_expr('m')} = $key")
            params["key"] = self._mem_key(item_id, layer)
        else:
            conds.append("m.mem_id = $id")
        if user_id is not None:
            conds.append("m.user_id = $user_id")
            params["user_id"] = user_id
        query = f"MATCH (m:Memory) WHERE {' AND '.join(conds)} DETACH DELETE m"
        
        try:
            client.run_query(query, params)
        except Exception as e:
            logger.warning(f"delete_from_graph failed: {e}")
        
        # 重置 prev（如果删除的是当前 prev，需遍历所有用户）
        with self._prev_id_lock:
            for uid, prev in list(self._prev_ids.items()):
                pid = prev[0] if isinstance(prev, tuple) else prev
                if pid == item_id:
                    self._prev_ids[uid] = (-1, None)
    
    def filter_protected(self, candidate_ids: List[int]) -> List[int]:
        """
        返回高入度节点（应豁免删除）
        
        用于 consolidate 阶段保护核心记忆。
        入度 >= threshold 的节点不会被删除。
        
        Args:
            candidate_ids: 待删除候选列表
            
        Returns:
            受保护节点列表
        """
        if not self._available() or not candidate_ids:
            return []
        
        client = self._get_graph_client()
        query = """
        MATCH (m:Memory)
        WHERE m.mem_id IN $ids
        WITH m, size([(m)<-[]-() | 1]) AS indegree
        WHERE indegree >= $threshold
        RETURN m.mem_id AS id
        """
        
        try:
            results = client.run_query(
                query,
                {"ids": candidate_ids, "threshold": self._indegree_threshold}
            )
            return [r.get("id") for r in results if r.get("id") is not None]
        except Exception as e:
            logger.warning(f"filter_protected failed: {e}")
            return []
    
    def update_node(self, item: MemoryItem) -> None:
        """
        更新记忆节点属性
        
        Args:
            item: 记忆条目
        """
        if not self._available() or item.id is None:
            return
        self._upsert_memory_node(
            item.id,
            item.content,
            item.importance,
            item.category or "general",
            item.user_id,
            item.layer,
        )
    
    def bulk_index(self, items: List[MemoryItem]) -> int:
        """
        批量索引：把一批记忆同步进图（启动期从存储恢复时使用）
        
        会按顺序建立 FOLLOWS 链。
        
        Args:
            items: 记忆列表
            
        Returns:
            成功 upsert 的节点数
        """
        if not self._available():
            return 0
        
        count = 0
        prev_local = None  # (mem_id, layer)
        
        for item in items:
            if item.id is None:
                continue
            
            mem_id = int(item.id)
            self._upsert_memory_node(
                mem_id,
                item.content,
                item.importance,
                item.category or "general",
                item.user_id,
                item.layer,
            )
            
            if prev_local is not None and prev_local[0] != mem_id:
                self._add_memory_edge(prev_local[0], mem_id, self.EDGE_FOLLOWS, 1.0,
                                      from_layer=prev_local[1], to_layer=item.layer)
            
            prev_local = (mem_id, item.layer)
            count += 1
        
        with self._prev_id_lock:
            if items:
                last_uid = items[-1].user_id
                if last_uid is not None and prev_local is not None:
                    self._prev_ids[last_uid] = prev_local
        
        logger.info(f"GraphMemory bulk_index: {count} nodes")
        return count
    
    def sync_prev_id(self, user_id: Optional[int] = None) -> None:
        """
        从 LTM 拉取 last_id 同步到 self._prev_ids[user_id]

        未注入 LTM 时静默 no-op
        """
        if self._ltm is None or user_id is None:
            return
        try:
            last = getattr(self._ltm, 'last_id', -1)
            if callable(last):
                last = last()
            if last is None:
                last = -1
            with self._prev_id_lock:
                # 与 add_to_graph 保持一致：值统一是 (mem_id, layer) 元组。
                # 这里拿不到层级（LTM 只存 last_id），置 None → 键退化为 legacy:<id>，
                # 与显式层级的节点区分开，不会串到别的层。
                self._prev_ids[user_id] = (int(last), None)
        except Exception as e:
            logger.warning(f"sync_prev_id failed: {e}")
    
    # ========== 内部方法 ==========

    def _ensure_user_node(self, user_id: int) -> None:
        """
        确保 User 节点存在（幂等）

        Args:
            user_id: 用户 ID
        """
        client = self._get_graph_client()
        query = """
        MERGE (u:User {user_id: $user_id})
        SET u.updated_at = datetime()
        """
        try:
            client.run_query(query, {"user_id": user_id})
        except Exception as e:
            logger.warning(f"ensure_user_node failed (user_id={user_id}): {e}")

    def _add_user_belongs_edge(self, mem_id: int, user_id: int) -> None:
        """
        创建 Memory → User 的 BELONGS_TO 边

        Args:
            mem_id: 记忆 ID
            user_id: 用户 ID
        """
        client = self._get_graph_client()
        query = """
        MATCH (m:Memory {mem_id: $mem_id})
        MATCH (u:User {user_id: $user_id})
        MERGE (m)-[r:BELONGS_TO_USER]->(u)
        SET r.created_at = datetime()
        """
        try:
            client.run_query(query, {"mem_id": mem_id, "user_id": user_id})
        except Exception as e:
            logger.warning(f"add_user_belongs_edge failed (mem={mem_id}→user={user_id}): {e}")

    def _upsert_memory_node(
        self,
        mem_id: int,
        content: str,
        importance: float,
        category: str,
        user_id: Optional[int] = None,
        layer: Optional[str] = None,
    ) -> None:
        """
        MERGE 记忆节点（幂等）— 单次查询完成 User + Memory + BELONGS_TO_USER

        ⚠️ 节点身份用 `mem_key`（= "{layer}:{id}"）而不是裸 mem_id：
        两张记忆表的 id 会重号，只用 mem_id 会把不同记忆合并成同一节点。
        """
        client = self._get_graph_client()
        key = self._mem_key(mem_id, layer)
        lyr = (str(layer).strip().lower() if layer else "") or self.LAYER_LEGACY

        if user_id is not None:
            # 合并为单条查询：MERGE User + MERGE Memory + MERGE BELONGS_TO_USER
            query = """
            MERGE (u:User {user_id: $user_id})
            ON CREATE SET u.created_at = datetime()
            MERGE (m:Memory {mem_key: $key})
            SET m.mem_id = $id,
                m.layer = $layer,
                m.content = $content,
                m.importance = $importance,
                m.category = $category,
                m.user_id = $user_id
            MERGE (m)-[r:BELONGS_TO_USER]->(u)
            SET r.user_id = $user_id
            """
            params = {
                "key": key,
                "id": mem_id,
                "layer": lyr,
                "content": content,
                "importance": importance,
                "category": category,
                "user_id": user_id
            }
        else:
            query = """
            MERGE (m:Memory {mem_key: $key})
            SET m.mem_id = $id,
                m.layer = $layer,
                m.content = $content,
                m.importance = $importance,
                m.category = $category
            """
            params = {
                "key": key,
                "id": mem_id,
                "layer": lyr,
                "content": content,
                "importance": importance,
                "category": category
            }

        try:
            client.run_query(query, params)
        except Exception as e:
            logger.warning(f"upsert_memory_node failed (id={mem_id}, layer={lyr}): {e}")

    def _add_memory_edge(
        self,
        from_id: int,
        to_id: int,
        edge_type: str,
        weight: float,
        from_layer: Optional[str] = None,
        to_layer: Optional[str] = None,
    ) -> None:
        """在两条记忆之间添加关系边（按 mem_key 定位，避免 id 重号串节点）"""
        if edge_type not in (self.EDGE_FOLLOWS, self.EDGE_SIMILAR_TO,
                             self.EDGE_CAUSES, self.EDGE_BELONGS_TO):
            raise ValueError(f"Invalid edge type: {edge_type} (must be one of FOLLOWS/SIMILAR_TO/CAUSES/BELONGS_TO)")
        
        client = self._get_graph_client()
        # ⚠️ 必须同时写 r.user_id：可见性谓词是
        #   (r.source_document_id IS NOT NULL AND ...) OR (r.source_document_id IS NULL AND r.user_id = $user_id)
        # 记忆层的边两者都没有 → 对**所有**用户都不可见，于是 get_subgraph /
        # find_paths_between 里记忆节点永远没有边（find_related 因为是直查所以看不出来）。
        # 两端都是 Memory，用 a.user_id 即可（FOLLOWS/SIMILAR_TO 本就是同用户内建的）。
        from_key = self._mem_key(from_id, from_layer)
        to_key = self._mem_key(to_id, to_layer)
        # 用 coalesce 兼容"迁移前还没有 mem_key 的历史节点"
        query = f"""
        MATCH (a:Memory) WHERE {self._key_expr('a')} = $from_key
        MATCH (b:Memory) WHERE {self._key_expr('b')} = $to_key
        MERGE (a)-[r:{edge_type}]->(b)
        SET r.weight = $weight
        SET r.user_id = coalesce(a.user_id, b.user_id)
        """
        try:
            client.run_query(query, {
                "from_key": from_key,
                "to_key": to_key,
                "weight": weight
            })
        except Exception as e:
            logger.warning(f"add_memory_edge failed ({from_key}→{to_key}): {e}")
    
    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
    
    def close(self) -> None:
        """关闭连接（语义对齐 Go 版）"""
        with self._prev_id_lock:
            self._prev_ids.clear()
        # 底层 driver 由 Neo4jClient 拥有，这里只清状态


# 全局实例
_graph_memory: Optional[GraphMemory] = None
_graph_memory_lock = threading.Lock()


def get_graph_memory() -> Optional[GraphMemory]:
    """获取 GraphMemory 单例"""
    global _graph_memory
    with _graph_memory_lock:
        if _graph_memory is None:
            try:
                _graph_memory = GraphMemory()
            except Exception as e:
                logger.debug(f"GraphMemory init failed: {e}")
        return _graph_memory