"""
Neo4j 客户端封装 - 用于 GraphRAG 知识图谱存储

设计原则:
- 可选依赖：neo4j 包未安装或连接失败时静默降级
- 优雅降级：不可用时 status=unavailable，is_available()=False
- 仅当 is_available()=True 时才执行图操作
"""

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Cypher 标识符白名单校验（防注入）
_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _validate_cypher_ident(value: str, kind: str = "identifier") -> str:
    """校验 Cypher 标识符（标签名、属性名、关系类型），防止注入。"""
    if not value or not _IDENT_RE.match(value):
        raise ValueError(f"非法 Neo4j {kind}: {value!r}")
    return value

# 尝试导入 neo4j
try:
    from neo4j import GraphDatabase, Driver, Session
    from neo4j.exceptions import ServiceUnavailable, AuthError
    _HAS_NEO4J = True
except ImportError:
    _HAS_NEO4J = False
    GraphDatabase = None
    Driver = None
    Session = None
    ServiceUnavailable = Exception
    AuthError = Exception
    logger.debug("neo4j package not installed, GraphRAG features disabled")


@dataclass
class Neo4jStatus:
    """Neo4j 连接状态"""
    connected: bool = False
    uri: str = ""
    database: str = "neo4j"
    error: Optional[str] = None


class Neo4jClient:
    """
    Neo4j 图数据库客户端
    
    用法:
        client = Neo4jClient()
        if client.is_available():
            client.create_entity(...)
            client.create_relation(...)
    """
    
    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: str = "neo4j",
        max_retries: int = 3,
        retry_delay: float = 2.0
    ):
        """
        初始化 Neo4j 客户端
        
        Args:
            uri: Neo4j 连接 URI (bolt://host:7687)，默认从环境变量 NEO4J_URI
            username: 用户名，默认从 NEO4J_USERNAME
            password: 密码，默认从 NEO4J_PASSWORD
            database: 数据库名，默认 neo4j
            max_retries: 最大重试次数，默认 3
            retry_delay: 重试间隔秒数，默认 2.0
        """
        self._uri = uri or os.getenv("NEO4J_URI", "")
        self._username = username or os.getenv("NEO4J_USERNAME", "neo4j")
        self._password = password or os.getenv("NEO4J_PASSWORD", "")
        self._database = database
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        
        self._driver: Optional[Any] = None
        self._status = Neo4jStatus(
            uri=self._uri,
            database=self._database
        )
        
        # 连接可用性缓存（避免频繁验证）
        self._last_available_check: float = 0
        self._available_cache_ttl: float = 30.0  # 缓存有效期 30 秒
        
        # 尝试连接（带重试）
        self._connect_with_retry()
    
    def _connect_with_retry(self) -> None:
        """尝试建立连接（带重试机制）"""
        for attempt in range(self._max_retries):
            if attempt > 0:
                logger.info(f"Neo4j connection retry {attempt + 1}/{self._max_retries}...")
                time.sleep(self._retry_delay)
            
            if self._connect():
                return
        
        logger.warning(f"Neo4j connection failed after {self._max_retries} attempts")
    
    def _connect(self) -> bool:
        """尝试建立连接，返回是否成功"""
        if not _HAS_NEO4J:
            self._status.error = "neo4j package not installed"
            logger.info("Neo4j not available: package not installed")
            return False
        
        if not self._uri:
            self._status.error = "NEO4J_URI not configured"
            logger.debug("Neo4j not available: NEO4J_URI not configured")
            return False
        
        try:
            # 添加连接超时配置
            self._driver = GraphDatabase.driver(
                self._uri,
                auth=(self._username, self._password),
                max_connection_lifetime=3600,  # 连接最大生命周期 1 小时
                max_connection_pool_size=50,
                connection_timeout=10.0,  # 连接超时 10 秒
            )
            # 抑制 Neo4j 驱动的通知 WARNING（图谱查询中使用 FOLLOWS|SIMILAR_TO|CAUSES|
            # BELONGS_TO 等关系类型，部分在 DB 中尚未创建时，驱动会为每个缺失类型发一条
            # 通知，且通知同时通过标准 logging 和 warnings 双路输出（每条 × 2），
            # 在记忆图谱遍历时产生大量噪声。WARNING 级通知不影响查询结果。
            # 注意：notifications_min_severity 参数在旧版 Neo4j server 上不被支持
            # （报 "Could not parse a NotificationConfig's minimum severity."），
            # 因此改在 logging 层面抑制 neo4j.notifications logger 的 WARNING。
            logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
            # 验证连接
            with self._driver.session(database=self._database) as session:
                session.run("RETURN 1").single()
            
            self._status.connected = True
            self._status.error = None
            logger.info(f"Neo4j connected: {self._uri}")

            # 连接成功后确保索引存在
            self._ensure_indexes()

            return True
            
        except ServiceUnavailable as e:
            self._status.error = f"Service unavailable: {e}"
            logger.warning(f"Neo4j service unavailable: {e}")
            self._driver = None
            return False
            
        except AuthError as e:
            self._status.error = f"Authentication failed: {e}"
            logger.warning(f"Neo4j auth failed: {e}")
            self._driver = None
            return False
            
        except Exception as e:
            self._status.error = f"Connection error: {e}"
            logger.warning(f"Neo4j connection error: {e}")
            self._driver = None
            return False
    
    @property
    def status(self) -> Neo4jStatus:
        """获取连接状态"""
        return self._status
    
    def is_available(self) -> bool:
        """检查 Neo4j 是否可用（带缓存，避免频繁验证）"""
        if not self._status.connected or self._driver is None:
            return False
        
        # 如果上次检查成功且在缓存有效期内，直接返回 True
        now = time.time()
        if now - self._last_available_check < self._available_cache_ttl:
            return True
        
        # 真正验证连接是否仍然有效
        try:
            # Neo4j 5.x 使用 verify_connectivity()
            if hasattr(self._driver, 'verify_connectivity'):
                self._driver.verify_connectivity()
            else:
                # 旧版本使用 session 验证
                with self._driver.session(database=self._database) as session:
                    session.run("RETURN 1").single()
            
            # 更新缓存时间戳
            self._last_available_check = now
            return True
            
        except Exception as e:
            # 连接已断开，尝试重连
            logger.warning(f"Neo4j connection lost: {e}")
            self._status.connected = False
            self._status.error = str(e)
            # 尝试重连
            self._reconnect()
            return self._status.connected
    
    def _reconnect(self) -> None:
        """重新连接（带重试）"""
        if self._driver:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None

        self._connect_with_retry()

    def _ensure_indexes(self) -> bool:
        """
        确保必要的索引已创建

        索引列表：
        - id: 实体唯一标识（所有标签）
        - user_id: 用户隔离
        - entity_type: 类型过滤
        - name: 名称搜索

        Returns:
            是否成功创建索引
        """
        if not self.is_available():
            return False

        indexes = [
            # 通用 Entity 标签索引
            "CREATE INDEX entity_id IF NOT EXISTS FOR (n:Entity) ON (n.id)",
            "CREATE INDEX entity_user_id IF NOT EXISTS FOR (n:Entity) ON (n.user_id)",
            "CREATE INDEX entity_type IF NOT EXISTS FOR (n:Entity) ON (n.entity_type)",
            "CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)",
            # 各类型标签索引
            "CREATE INDEX person_id IF NOT EXISTS FOR (n:Person) ON (n.id)",
            "CREATE INDEX person_user_id IF NOT EXISTS FOR (n:Person) ON (n.user_id)",
            "CREATE INDEX org_id IF NOT EXISTS FOR (n:Organization) ON (n.id)",
            "CREATE INDEX org_user_id IF NOT EXISTS FOR (n:Organization) ON (n.user_id)",
            "CREATE INDEX location_id IF NOT EXISTS FOR (n:Location) ON (n.id)",
            "CREATE INDEX concept_id IF NOT EXISTS FOR (n:Concept) ON (n.id)",
            "CREATE INDEX skill_id IF NOT EXISTS FOR (n:Skill) ON (n.id)",
            "CREATE INDEX project_id IF NOT EXISTS FOR (n:Project) ON (n.id)",
            "CREATE INDEX tool_id IF NOT EXISTS FOR (n:Tool) ON (n.id)",
            # Memory 节点索引
            "CREATE INDEX memory_id IF NOT EXISTS FOR (n:Memory) ON (n.mem_id)",
            "CREATE INDEX memory_user_id IF NOT EXISTS FOR (n:Memory) ON (n.user_id)",
        ]

        success_count = 0
        for index_query in indexes:
            try:
                self.run_query(index_query)
                success_count += 1
            except Exception as e:
                # 索引创建失败不阻塞启动，仅记录警告
                logger.debug(f"Index creation skipped: {e}")

        if success_count > 0:
            logger.info(f"Neo4j indexes ensured: {success_count}/{len(indexes)}")

        return success_count > 0

    def close(self) -> None:
        """关闭连接"""
        if self._driver:
            self._driver.close()
            self._driver = None
            self._status.connected = False
            logger.info("Neo4j connection closed")
    
    def _get_session(self) -> Optional[Any]:
        """获取会话（内部方法）"""
        if not self.is_available():
            return None
        return self._driver.session(database=self._database)
    
    # ========== 实体操作 ==========
    
    def create_entity(
        self,
        label: str,
        properties: dict,
        unique_key: str = "id"
    ) -> bool:
        """
        创建或更新实体节点
        
        Args:
            label: 节点标签（如 Person, Concept, Memory）
            properties: 节点属性
            unique_key: 唯一标识属性名，用于 MERGE
            
        Returns:
            是否成功
        """
        if not self.is_available():
            return False
        
        if unique_key not in properties:
            logger.warning(f"Unique key '{unique_key}' not in properties")
            return False

        # 安全校验：防止 Cypher 注入
        _validate_cypher_ident(label, "label")
        _validate_cypher_ident(unique_key, "property name")

        try:
            with self._get_session() as session:
                # 使用 MERGE 确保幂等
                query = f"""
                MERGE (n:{label} {{{unique_key}: $unique_value}})
                SET n += $properties
                RETURN n
                """
                result = session.run(
                    query,
                    unique_value=properties[unique_key],
                    properties=properties
                )
                return result.single() is not None
                
        except Exception as e:
            logger.error(f"Failed to create entity: {e}")
            return False
    
    def get_entity(
        self,
        label: str,
        unique_key: str,
        value: Any
    ) -> Optional[dict]:
        """
        获取实体
        
        Args:
            label: 节点标签
            unique_key: 唯一标识属性名
            value: 唯一标识值
            
        Returns:
            实体属性字典，不存在返回 None
        """
        if not self.is_available():
            return None
        
        try:
            with self._get_session() as session:
                query = f"""
                MATCH (n:{label} {{{unique_key}: $value}})
                RETURN n
                """
                result = session.run(query, value=value)
                record = result.single()
                if record:
                    return dict(record["n"])
                return None
                
        except Exception as e:
            logger.error(f"Failed to get entity: {e}")
            return None
    
    def delete_entity(
        self,
        label: str,
        unique_key: str,
        value: Any
    ) -> bool:
        """
        删除实体及其关系
        
        Args:
            label: 节点标签
            unique_key: 唯一标识属性名
            value: 唯一标识值
            
        Returns:
            是否成功
        """
        if not self.is_available():
            return False
        
        try:
            with self._get_session() as session:
                query = f"""
                MATCH (n:{label} {{{unique_key}: $value}})
                DETACH DELETE n
                """
                session.run(query, value=value)
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete entity: {e}")
            return False
    
    # ========== 关系操作 ==========
    
    def create_relation(
        self,
        from_label: str,
        from_key: str,
        from_value: Any,
        to_label: str,
        to_key: str,
        to_value: Any,
        relation_type: str,
        properties: Optional[dict] = None
    ) -> bool:
        """
        创建节点间关系
        
        Args:
            from_label: 起始节点标签（可选，传空字符串则忽略）
            from_key: 起始节点唯一标识属性
            from_value: 起始节点唯一标识值
            to_label: 目标节点标签（可选，传空字符串则忽略）
            to_key: 目标节点唯一标识属性
            to_value: 目标节点唯一标识值
            relation_type: 关系类型
            properties: 关系属性（可选）
            
        Returns:
            是否成功
        """
        if not self.is_available():
            return False
        
        try:
            with self._get_session() as session:
                # 如果标签为空或 "Entity"，使用通用查询匹配任意标签的节点
                if not from_label or from_label == "Entity":
                    query = f"""
                    MATCH (a {{{from_key}: $from_value}})
                    MATCH (b {{{to_key}: $to_value}})
                    MERGE (a)-[r:{relation_type}]->(b)
                    SET r += $properties
                    RETURN r
                    """
                else:
                    query = f"""
                    MATCH (a:{from_label} {{{from_key}: $from_value}})
                    MATCH (b:{to_label} {{{to_key}: $to_value}})
                    MERGE (a)-[r:{relation_type}]->(b)
                    SET r += $properties
                    RETURN r
                    """
                result = session.run(
                    query,
                    from_value=from_value,
                    to_value=to_value,
                    properties=properties or {}
                )
                return result.single() is not None
                
        except Exception as e:
            logger.error(f"Failed to create relation: {e}")
            return False
    
    def get_related_entities(
        self,
        label: str,
        unique_key: str,
        value: Any,
        relation_type: Optional[str] = None,
        direction: str = "out",
        limit: int = 100
    ) -> list:
        """
        获取相关实体
        
        Args:
            label: 起始节点标签
            unique_key: 唯一标识属性
            value: 唯一标识值
            relation_type: 关系类型（None 表示所有）
            direction: 关系方向 'out'(出边), 'in'(入边), 'both'(双向)
            limit: 返回数量限制
            
        Returns:
            相关实体列表 [{node: {...}, relation: {...}, direction: ...}]
        """
        if not self.is_available():
            return []
        
        try:
            with self._get_session() as session:
                # 安全校验：防止 Cypher 注入
                _validate_cypher_ident(label, "label")
                _validate_cypher_ident(unique_key, "property name")
                if relation_type:
                    _validate_cypher_ident(relation_type, "relation type")

                # 构建关系过滤器
                rel_filter = f":{relation_type}" if relation_type else ""

                # 构建方向模式（使用 f-string 直接构建，避免 str.replace 破坏）
                if direction == "out":
                    arrow = f"(n:{label} {{{unique_key}: $value}})-[r{rel_filter}]->(m)"
                elif direction == "in":
                    arrow = f"(n:{label} {{{unique_key}: $value}})<-[r{rel_filter}]-(m)"
                else:
                    arrow = f"(n:{label} {{{unique_key}: $value}})-[r{rel_filter}]-(m)"

                query = f"""
                MATCH {arrow}
                RETURN m as node, r as relation, type(r) as rel_type
                LIMIT $limit
                """
                
                result = session.run(query, value=value, limit=limit)
                entities = []
                for record in result:
                    entities.append({
                        "node": dict(record["node"]),
                        "relation": dict(record["relation"]),
                        "rel_type": record["rel_type"]
                    })
                return entities
                
        except Exception as e:
            logger.error(f"Failed to get related entities: {e}")
            return []
    
    # ========== 图查询 ==========
    
    def run_query(
        self,
        cypher: str,
        parameters: Optional[dict] = None
    ) -> list:
        """
        执行 Cypher 查询
        
        Args:
            cypher: Cypher 查询语句
            parameters: 查询参数
            
        Returns:
            结果记录列表（所有 Neo4j 对象已转换为 Python 字典）
        """
        if not self.is_available():
            return []
        
        def serialize_value(value):
            """递归序列化 Neo4j 对象"""
            if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
                # Neo4j Node 或 Relationship
                if hasattr(value, 'properties'):
                    return dict(value)
                # 列表
                return [serialize_value(v) for v in value]
            return value
        
        try:
            with self._get_session() as session:
                result = session.run(cypher, parameters or {})
                records = []
                for record in result:
                    row = {}
                    for key in record.keys():
                        value = record[key]
                        # 处理 Neo4j Node 对象
                        if hasattr(value, 'properties'):
                            row[key] = dict(value)
                        # 处理 Neo4j Relationship 对象
                        elif hasattr(value, 'start_node') and hasattr(value, 'end_node'):
                            rel = dict(value)
                            rel['_type'] = type(value).__name__
                            row[key] = rel
                        else:
                            row[key] = value
                    records.append(row)
                return records
                
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []
    
    def get_subgraph(
        self,
        label: str,
        unique_key: str,
        value: Any,
        depth: int = 2
    ) -> dict:
        """
        获取以某节点为中心的子图（用于 GraphRAG 前端展示）
        
        Args:
            label: 中心节点标签
            unique_key: 唯一标识属性
            value: 唯一标识值
            depth: 遍历深度
            
        Returns:
            {nodes: [...], edges: [...]}
        """
        if not self.is_available():
            return {"nodes": [], "edges": []}
        
        try:
            with self._get_session() as session:
                # 安全校验：防止 Cypher 注入 + DoS
                _validate_cypher_ident(label, "label")
                _validate_cypher_ident(unique_key, "property name")
                depth = max(1, min(int(depth), 5))  # 上限 5 层，防指数级遍历
                query = f"""
                MATCH path = (center:{label} {{{unique_key}: $value}})-[*1..{depth}]-(other)
                RETURN 
                    [n IN nodes(path) | {{id: id(n), labels: labels(n), properties: properties(n)}}] as nodes,
                    [r IN relationships(path) | {{id: id(r), type: type(r), properties: properties(r), 
                        source: id(startNode(r)), target: id(endNode(r))}}] as edges
                """
                result = session.run(query, value=value)
                
                # 合并所有路径的节点和边（去重）
                all_nodes = {}
                all_edges = {}
                
                for record in result:
                    for node in record["nodes"]:
                        all_nodes[node["id"]] = node
                    for edge in record["edges"]:
                        all_edges[edge["id"]] = edge
                
                return {
                    "nodes": list(all_nodes.values()),
                    "edges": list(all_edges.values())
                }
                
        except Exception as e:
            logger.error(f"Failed to get subgraph: {e}")
            return {"nodes": [], "edges": []}
    
    # ========== 统计与维护 ==========
    
    def count_entities(self, label: Optional[str] = None) -> int:
        """
        统计实体数量
        
        Args:
            label: 节点标签（None 表示所有）
            
        Returns:
            实体数量
        """
        if not self.is_available():
            return 0
        
        try:
            with self._get_session() as session:
                if label:
                    query = f"MATCH (n:{label}) RETURN count(n) as count"
                else:
                    query = "MATCH (n) RETURN count(n) as count"
                
                result = session.run(query)
                record = result.single()
                return record["count"] if record else 0
                
        except Exception as e:
            logger.error(f"Failed to count entities: {e}")
            return 0
    
    def count_relations(self, relation_type: Optional[str] = None) -> int:
        """
        统计关系数量
        
        Args:
            relation_type: 关系类型（None 表示所有）
            
        Returns:
            关系数量
        """
        if not self.is_available():
            return 0
        
        try:
            with self._get_session() as session:
                if relation_type:
                    query = f"MATCH ()-[r:{relation_type}]->() RETURN count(r) as count"
                else:
                    query = "MATCH ()-[r]->() RETURN count(r) as count"
                
                result = session.run(query)
                record = result.single()
                return record["count"] if record else 0
                
        except Exception as e:
            logger.error(f"Failed to count relations: {e}")
            return 0
    
    def clear_all(self, label: Optional[str] = None) -> bool:
        """
        清除数据（危险操作，仅用于测试）
        
        Args:
            label: 仅清除指定标签（None 表示全部）
            
        Returns:
            是否成功
        """
        if not self.is_available():
            return False
        
        try:
            with self._get_session() as session:
                if label:
                    query = f"MATCH (n:{label}) DETACH DELETE n"
                else:
                    query = "MATCH (n) DETACH DELETE n"
                
                session.run(query)
                logger.warning(f"Cleared {'all' if not label else label} nodes from Neo4j")
                return True
                
        except Exception as e:
            logger.error(f"Failed to clear: {e}")
            return False
    
    def __repr__(self) -> str:
        status = "connected" if self.is_available() else "unavailable"
        return f"Neo4jClient(uri={self._uri}, database={self._database}, status={status})"


# ========== 单例实例 ==========

_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j_client() -> Neo4jClient:
    """
    获取全局 Neo4j 客户端实例（单例）
    
    Returns:
        Neo4jClient 实例（可用性通过 is_available() 检查）
    """
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    return _neo4j_client