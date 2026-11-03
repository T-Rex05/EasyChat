"""
知识图谱社区检测

使用 Louvain/Leiden 算法对知识图谱进行社区划分，
生成层次化的社区结构。

算法原理：
- Louvain: 基于模块度优化的社区检测算法，速度快
- Leiden: Louvain 的改进版，支持层次化社区检测，社区质量更好

输出：
- 多层级社区结构（Level 0 最细，Level 2-3 最粗）
- 每个社区包含的实体列表
- 社区间的父子关系

Leiden vs Louvain:
- Leiden 保证社区内部连接性（Louvain 可能有断连节点）
- Leiden 更稳定（同样输入产生相同输出）
- Leiden 分辨率参数更直观
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from backend.utils.log_utils import log

logger = log

# 算法选择：优先 Leiden，回退 Louvain
DEFAULT_COMMUNITY_ALGORITHM = os.getenv("COMMUNITY_ALGORITHM", "leiden").lower()


@dataclass
class Community:
    """社区数据结构"""
    id: str                              # community_xxx
    level: int                           # 层级 (0=最细)
    entity_ids: List[str] = field(default_factory=list)
    relationship_count: int = 0
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)


class CommunityDetector:
    """
    社区检测器

    使用 Louvain 算法对知识图谱进行社区划分
    """

    def __init__(self, user_id: int):
        self.user_id = user_id
        self._kg_store = None
        self._graph: Optional[nx.Graph] = None

    def _get_kg_store(self):
        """获取 KGStore（延迟加载）"""
        if self._kg_store is None:
            from backend.graphrag.kg_store import get_kg_store
            self._kg_store = get_kg_store()
        return self._kg_store

    def _build_networkx_graph(self) -> nx.Graph:
        """
        从 Neo4j 构建 NetworkX 图

        Returns:
            nx.Graph: 无向图（节点=实体，边=关系）
        """
        kg_store = self._get_kg_store()
        client = kg_store._get_graph_client()

        if not client:
            logger.warning("[Community] Neo4j 不可用")
            return nx.Graph()

        # 租户隔离：拿不到用户身份（None）或身份为 0（无归属）时提前返回，避免全图扫描。
        # 显式判空而不是真值判断：意图是"身份不可用就跳过"，不是"0 恰好是假值"。
        if self.user_id is None or int(self.user_id) == 0:
            logger.warning("[Community] user_id 为空，跳过社区检测")
            return nx.Graph()

        # 查询当前用户的实体和关系（两级隔离：KB 文档全局共享，记忆实体按 user_id 隔离）
        entities = client.run_query("""
            MATCH (n)
            WHERE NOT n:Memory AND (n.source_document_id IS NOT NULL OR n.user_id = $user_id)
            RETURN n.id as id, n.name as name, labels(n)[0] as type
        """, {"user_id": self.user_id})

        relationships = client.run_query("""
            MATCH (a)-[r]->(b)
            WHERE NOT a:Memory AND NOT b:Memory
              AND (a.source_document_id IS NOT NULL OR a.user_id = $user_id)
              AND (b.source_document_id IS NOT NULL OR b.user_id = $user_id)
            RETURN a.id as source, b.id as target, type(r) as type
        """, {"user_id": self.user_id})

        # 构建 NetworkX 图
        G = nx.Graph()

        # 添加节点
        for e in entities:
            if e.get('id'):
                G.add_node(e['id'], name=e.get('name', ''), type=e.get('type', ''))

        # 添加边
        for r in relationships:
            src, tgt = r.get('source'), r.get('target')
            if src and tgt and G.has_node(src) and G.has_node(tgt):
                G.add_edge(src, tgt, type=r.get('type', ''))

        logger.debug(f"[Community] 构建 NetworkX 图: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")

        self._graph = G
        return G

    def _run_louvain(self, G: nx.Graph, resolution: float = 1.0) -> Dict[str, int]:
        """
        运行 Louvain 算法

        优先使用 NetworkX 内置实现（3.x+），回退到 python-louvain 包。

        Args:
            G: NetworkX 图
            resolution: 分辨率参数，越大社区越小

        Returns:
            Dict[node_id, community_id]
        """
        if G.number_of_nodes() == 0:
            return {}

        partition: Dict[str, int] = {}

        # 优先：NetworkX 内置 Louvain（3.0+ 自带，无需额外依赖）
        try:
            from networkx.algorithms.community import louvain_communities
            communities = louvain_communities(G, resolution=resolution, seed=42)
            for comm_id, members in enumerate(communities):
                for node in members:
                    partition[node] = comm_id
            logger.debug("[Community] 使用 NetworkX 内置 Louvain")
        except (ImportError, AttributeError):
            # 回退：python-louvain 包（import community）
            community_louvain = None
            try:
                import community as community_louvain
            except ImportError:
                import importlib, sys, site
                for sp in site.getsitepackages() + [site.getusersitepackages()]:
                    if sp not in sys.path:
                        sys.path.insert(0, sp)
                try:
                    community_louvain = importlib.import_module("community")
                except ImportError:
                    pass

            if community_louvain is None:
                raise ImportError(
                    "Louvain 算法不可用。请升级 NetworkX (pip install -U networkx) "
                    "或安装 python-louvain (pip install python-louvain)"
                )
            partition = community_louvain.best_partition(G, resolution=resolution)
            logger.debug("[Community] 使用 python-louvain 包")

        # 统计社区
        community_sizes: Dict[int, int] = {}
        for node, comm_id in partition.items():
            community_sizes[comm_id] = community_sizes.get(comm_id, 0) + 1

        logger.debug(f"[Community] Louvain 检测完成: {len(community_sizes)} 个社区")
        for comm_id, size in sorted(community_sizes.items(), key=lambda x: -x[1])[:10]:
            logger.debug(f"  社区 {comm_id}: {size} 个节点")

        return partition

    def _run_leiden(self, G: nx.Graph, resolution: float = 1.0) -> Dict[str, int]:
        """
        运行 Leiden 算法

        Leiden 是 Louvain 的改进版本：
        - 保证社区内部连接性
        - 更稳定的社区划分
        - 更好的模块度

        Args:
            G: NetworkX 图
            resolution: 分辨率参数，越大社区越小

        Returns:
            Dict[node_id, community_id]
        """
        if G.number_of_nodes() == 0:
            return {}

        partition: Dict[str, int] = {}

        try:
            # 尝试使用 leidenalg 包
            import igraph as ig
            import leidenalg

            # NetworkX → iGraph 转换
            ig_graph = ig.Graph()
            node_list = list(G.nodes())
            node_idx_map = {node: idx for idx, node in enumerate(node_list)}

            ig_graph.add_vertices(len(node_list))
            ig_graph.vs["name"] = [str(n) for n in node_list]

            edges = [(node_idx_map[u], node_idx_map[v]) for u, v in G.edges()]
            ig_graph.add_edges(edges)

            # 运行 Leiden
            communities = leidenalg.find_partition(
                ig_graph,
                leidenalg.RBConfigurationVertexPartition,
                resolution_parameter=resolution,
                seed=42
            )

            # 转换为 {node_id: community_id}
            for comm_id, members in enumerate(communities):
                for node_idx in members:
                    node_id = node_list[node_idx]
                    partition[node_id] = comm_id

            logger.debug(f"[Community] Leiden 完成: {len(communities)} 个社区")

        except ImportError as e:
            logger.warning(f"[Community] leidenalg/igraph 不可用，回退 Louvain: {e}")
            return self._run_louvain(G, resolution)

        except Exception as e:
            logger.warning(f"[Community] Leiden 失败，回退 Louvain: {e}")
            return self._run_louvain(G, resolution)

        return partition

    def _detect_communities(self, G: nx.Graph, resolution: float = 1.0, algorithm: str = "auto") -> Dict[str, int]:
        """
        执行社区检测（自动选择算法）

        Args:
            G: NetworkX 图
            resolution: 分辨率参数
            algorithm: 算法选择 ("leiden", "louvain", "auto")

        Returns:
            Dict[node_id, community_id]
        """
        if algorithm == "auto":
            algorithm = DEFAULT_COMMUNITY_ALGORITHM

        if algorithm == "leiden":
            return self._run_leiden(G, resolution)
        else:
            return self._run_louvain(G, resolution)

    def _build_hierarchical_communities(
        self, G: nx.Graph, max_levels: int = 3, min_community_size: int = 5, algorithm: str = "auto"
    ) -> List[Community]:
        """
        构建层次化社区结构

        通过多次运行 Leiden/Louvain（不同分辨率）生成多层级社区

        Args:
            G: NetworkX 图
            max_levels: 最大层级数
            min_community_size: 最小社区大小
            algorithm: 算法选择 ("leiden", "louvain", "auto")

        Returns:
            所有层级的社区列表
        """
        all_communities: List[Community] = []

        # Level 0: 最细粒度（resolution=1.0）
        level0_partition = self._detect_communities(G, resolution=1.0, algorithm=algorithm)
        level0_communities = self._partition_to_communities(level0_partition, level=0)
        all_communities.extend(level0_communities)

        # 构建上层社区（通过合并小社区）
        prev_level_communities = level0_communities

        for level in range(1, max_levels):
            if len(prev_level_communities) <= 1:
                break

            # 构建社区间的关系图
            community_graph = self._build_community_graph(G, prev_level_communities)

            if community_graph.number_of_nodes() <= 1:
                break

            # 对社区图运行 Leiden/Louvain
            resolution = 0.5 + level * 0.3  # 分辨率递增，社区越来越大
            partition = self._detect_communities(community_graph, resolution=resolution, algorithm=algorithm)

            # 转换为上层社区
            upper_communities = self._partition_to_communities(
                partition, level=level,
                parent_communities=prev_level_communities,
                min_size=min_community_size
            )

            if not upper_communities:
                break

            all_communities.extend(upper_communities)
            prev_level_communities = upper_communities

        logger.debug(f"[Community] 层次化社区构建完成: {len(all_communities)} 个社区")
        return all_communities

    def _partition_to_communities(
        self,
        partition: Dict[Any, int],
        level: int,
        parent_communities: Optional[List[Community]] = None,
        min_size: int = 5
    ) -> List[Community]:
        """
        将分区结果转换为 Community 对象
        """
        # 按社区 ID 分组
        community_entities: Dict[int, List[str]] = {}
        for node_id, comm_id in partition.items():
            if comm_id not in community_entities:
                community_entities[comm_id] = []
            community_entities[comm_id].append(str(node_id))

        communities = []
        for comm_id, entity_ids in community_entities.items():
            # 跳过太小的社区（除了 Level 0）
            if level > 0 and len(entity_ids) < min_size:
                continue

            community = Community(
                id=f"community_{uuid.uuid4().hex[:12]}",
                level=level,
                entity_ids=entity_ids,
                relationship_count=0  # 稍后计算
            )
            communities.append(community)

        return communities

    def _build_community_graph(
        self, G: nx.Graph, communities: List[Community]
    ) -> nx.Graph:
        """
        构建社区间的关系图（用于上层社区检测）

        两个社区之间如果有边连接，则它们之间有权重
        """
        # 节点 -> 社区 映射
        node_to_community = {}
        for comm in communities:
            for entity_id in comm.entity_ids:
                node_to_community[entity_id] = comm.id

        # 构建社区图
        CG = nx.Graph()

        # 添加社区节点
        for comm in communities:
            CG.add_node(comm.id, size=len(comm.entity_ids))

        # 计算社区间的边权重
        edge_weights: Dict[Tuple[str, str], int] = {}
        for u, v in G.edges():
            comm_u = node_to_community.get(u)
            comm_v = node_to_community.get(v)
            if comm_u and comm_v and comm_u != comm_v:
                key = tuple(sorted([comm_u, comm_v]))
                edge_weights[key] = edge_weights.get(key, 0) + 1

        # 添加边
        for (comm1, comm2), weight in edge_weights.items():
            if CG.has_node(comm1) and CG.has_node(comm2):
                CG.add_edge(comm1, comm2, weight=weight)

        return CG

    def detect_and_store(self, algorithm: str = "auto") -> Dict[str, Any]:
        """
        执行社区检测并存储到 MySQL

        Args:
            algorithm: 算法选择 ("leiden", "louvain", "auto")

        Returns:
            {"communities": int, "levels": int, "entities_covered": int, "algorithm": str}
        """
        logger.debug(f"[Community] 开始社区检测 user_id={self.user_id}, algorithm={algorithm}")

        # 1. 构建 NetworkX 图
        G = self._build_networkx_graph()

        if G.number_of_nodes() == 0:
            logger.warning("[Community] 图谱为空，无法进行社区检测")
            return {"communities": 0, "levels": 0, "entities_covered": 0, "algorithm": algorithm}

        # 2. 构建层次化社区
        communities = self._build_hierarchical_communities(G, algorithm=algorithm)

        if not communities:
            logger.warning("[Community] 未检测到任何社区")
            return {"communities": 0, "levels": 0, "entities_covered": 0, "algorithm": algorithm}

        # 3. 计算每个社区的关系数
        for comm in communities:
            entity_set = set(comm.entity_ids)
            count = 0
            for u, v in G.edges():
                if u in entity_set and v in entity_set:
                    count += 1
            comm.relationship_count = count

        # 4. 存储到 MySQL
        self._store_communities(communities)

        # 5. 统计
        levels = max(c.level for c in communities) + 1
        entities_covered = sum(len(c.entity_ids) for c in communities if c.level == 0)

        logger.info(f"[Community] 检测完成: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边 → {len(communities)} 个社区, {levels} 层, algorithm={algorithm}")

        return {
            "communities": len(communities),
            "levels": levels,
            "entities_covered": entities_covered,
            "algorithm": algorithm
        }

    def _store_communities(self, communities: List[Community]) -> None:
        """将社区存储到 MySQL"""
        from backend.db.schema import get_conn

        conn = get_conn()
        try:
            # 先删除旧数据
            conn.execute(
                "DELETE FROM kg_communities WHERE user_id = %s",
                (self.user_id,)
            )

            # 插入新数据
            for comm in communities:
                conn.execute(
                    """INSERT INTO kg_communities
                       (id, user_id, level, parent_id, entity_count, entity_ids, relationship_count)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (
                        comm.id,
                        self.user_id,
                        comm.level,
                        comm.parent_id,
                        len(comm.entity_ids),
                        json.dumps(comm.entity_ids, ensure_ascii=False),
                        comm.relationship_count
                    )
                )

            conn.commit()

        except Exception as e:
            logger.error(f"[Community] 存储社区失败: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_communities(self, level: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取社区列表

        Args:
            level: 指定层级，None 表示全部

        Returns:
            社区列表
        """
        from backend.db.schema import get_conn

        conn = get_conn()
        try:
            if level is not None:
                cur = conn.execute(
                    """SELECT id, level, parent_id, entity_count, relationship_count, entity_ids
                       FROM kg_communities WHERE user_id = %s AND level = %s
                       ORDER BY entity_count DESC""",
                    (self.user_id, level)
                )
            else:
                cur = conn.execute(
                    """SELECT id, level, parent_id, entity_count, relationship_count, entity_ids
                       FROM kg_communities WHERE user_id = %s
                       ORDER BY level, entity_count DESC""",
                    (self.user_id,)
                )

            rows = cur.fetchall() if hasattr(cur, 'fetchall') else []
            result = []
            for row in rows:
                entity_ids = row.get('entity_ids', '[]')
                if isinstance(entity_ids, str):
                    entity_ids = json.loads(entity_ids)
                result.append({
                    "id": row['id'],
                    "level": row['level'],
                    "parent_id": row['parent_id'],
                    "entity_count": row['entity_count'],
                    "relationship_count": row['relationship_count'],
                    "entity_ids": entity_ids
                })
            return result

        finally:
            conn.close()


# 便捷函数
def detect_communities(user_id: int, algorithm: str = "auto") -> Dict[str, Any]:
    """
    执行社区检测

    Args:
        user_id: 用户 ID
        algorithm: 算法选择 ("leiden", "louvain", "auto")
    """
    detector = CommunityDetector(user_id)
    return detector.detect_and_store(algorithm=algorithm)


def get_communities(user_id: int, level: Optional[int] = None) -> List[Dict[str, Any]]:
    """获取社区列表"""
    detector = CommunityDetector(user_id)
    return detector.get_communities(level)
