"""
GraphRAG API Controller

提供知识图谱相关的 REST API
"""

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel

from backend.graphrag import (
    Entity, EntityType, Relation, RelationType,
    get_entity_extractor, get_kg_store, Subgraph
)
from backend.service.memory import get_memory_service
from backend.controller.auth_controller import get_current_user
from backend.utils.log_utils import log
from backend.service.memory_audit_service import record_memory_operation
from backend.db.graph_change_log_mapper import get_graph_change_log_mapper

logger = log


router = APIRouter(prefix="/api/graph", tags=["graphrag"])


def _resolve_entity_names(store, entity_ids: list) -> dict:
    """批量解析实体 ID → 名称，返回 {entity_id: entity_name}"""
    result = {}
    for eid in entity_ids:
        if not eid:
            continue
        entity = store.get_entity(eid)
        result[eid] = entity.name if entity else eid
    return result


def _relation_log_name(store, source_id: str, target_id: str, rel_type: str) -> str:
    """生成关系的可读日志名称：「陈元 -[相关]-> 刘备」"""
    names = _resolve_entity_names(store, [source_id, target_id])
    return f"{names.get(source_id, source_id)} -[{rel_type}]-> {names.get(target_id, target_id)}"


# ========== Request/Response Models ==========

class SearchEntitiesRequest(BaseModel):
    """搜索实体请求"""
    query: str
    entity_type: Optional[str] = None
    limit: int = 20


class CreateEntityRequest(BaseModel):
    """创建实体请求"""
    name: str
    entity_type: str
    description: Optional[str] = None
    properties: Optional[dict] = None


class CreateRelationRequest(BaseModel):
    """创建关系请求"""
    source_id: str
    target_id: str
    relation_type: str
    description: Optional[str] = None


class ExtractFromMemoryRequest(BaseModel):
    """从记忆提取请求"""
    memory_id: int


class EditEntityRequest(BaseModel):
    """编辑实体请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    aliases: Optional[list] = None


class EditRelationRequest(BaseModel):
    """编辑关系请求"""
    description: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    is_current: Optional[bool] = None


def _check_permission(user: dict, permission: str) -> bool:
    """检查权限"""
    perms = user.get("permissions") or set()
    role = user.get("role", "")
    
    # 管理员有所有权限
    if role in ("admin", "super_admin"):
        return True
    
    return permission in perms


def _require_permission(permission: str):
    """权限检查依赖"""
    async def check(user: dict = Depends(get_current_user)):
        if not _check_permission(user, permission):
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
        return user
    return check


def _require_any_permission(*permissions: str):
    """权限检查依赖：满足任意一个权限即可"""
    async def check(user: dict = Depends(get_current_user)):
        perms = user.get("permissions") or set()
        role = user.get("role", "")
        if role in ("admin", "super_admin"):
            return user
        if any(p in perms for p in permissions):
            return user
        raise HTTPException(status_code=403, detail=f"Permission denied: need one of {permissions}")
    return check


# ========== Entity Endpoints ==========

@router.get("/entities/search")
async def search_entities(
    query: str = Query(..., min_length=1),
    entity_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user)
):
    """搜索实体"""
    store = get_kg_store()
    
    etype = EntityType(entity_type) if entity_type else None
    user_id = user.get("user_id")
    
    entities = store.search_entities(
        name=query,
        entity_type=etype,
        user_id=user_id,
        limit=limit
    )
    
    return {
        "entities": [e.to_dict() for e in entities],
        "count": len(entities)
    }


@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: str,
    user: dict = Depends(get_current_user)
):
    """获取实体详情"""
    store = get_kg_store()

    entity = store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # user_id 校验：防止跨用户数据泄露
    user_id = user.get("user_id")
    role = user.get("role", "")
    perms = user.get("permissions") or set()

    # 管理员或 graph.manage 权限可以查看所有实体
    is_admin = role in ("admin", "super_admin") or "graph.manage" in perms

    if not is_admin and entity.properties.get("user_id") and entity.properties.get("user_id") != user_id:
        # 实体属于其他用户，返回 404（不泄露实体存在信息）
        raise HTTPException(status_code=404, detail="Entity not found")

    # 获取相关实体
    related = store.get_related_entities(entity_id, user_id=user_id, limit=500)  # 不限制数量
    
    # 收集关联记忆 ID
    memory_ids = set()
    if entity.source_memory_id:
        memory_ids.add(entity.source_memory_id)
    for r in related:
        if r.get("entity") and r["entity"].source_memory_id:
            memory_ids.add(r["entity"].source_memory_id)
    
    # 查询关联记忆
    related_memories = []
    if memory_ids:
        from backend.service.memory.memory_service import get_memory_service
        mem_service = get_memory_service()
        for mid in memory_ids:
            try:
                mem = mem_service.get_memory(mid, user_id=user_id)
                if mem:
                    related_memories.append({
                        "id": mem.get("id"),
                        "content": mem.get("content") or mem.get("key") or "",
                        "memory_type": mem.get("memory_type")
                    })
            except Exception as e:
                logger.debug(f"Failed to get memory {mid}: {e}")
    
    return {
        "entity": entity.to_dict(),
        "related": [
            {
                "entity": r["entity"].to_dict(),
                "relation_type": r["rel_type"],
                "relation": {
                    "id": r["relation"].id if r.get("relation") else "",
                    "description": r["relation"].description if r.get("relation") else "",
                    "source_id": r["relation"].source_id if r.get("relation") else "",
                    "target_id": r["relation"].target_id if r.get("relation") else "",
                    "direction": "out" if (r.get("relation") and r["relation"].source_id == entity_id) else "in",
                } if r.get("relation") else None,
            }
            for r in related
        ],
        "related_memories": related_memories
    }


@router.post("/entities")
async def create_entity(
    request: CreateEntityRequest,
    user: dict = Depends(_require_permission("graph.manage"))
):
    """创建实体"""
    store = get_kg_store()

    try:
        entity_type = EntityType(request.entity_type.lower())
    except ValueError:
        entity_type = EntityType.OTHER

    entity = Entity(
        id="",  # 自动生成
        name=request.name,
        entity_type=entity_type,
        description=request.description or "",
        properties=request.properties or {}
    )

    # 生成 ID
    from backend.graphrag.extractor import EntityExtractor
    entity.id = EntityExtractor._generate_entity_id(entity.name, entity.entity_type)

    user_id = user.get("user_id")
    actual_id = store.create_entity(entity, user_id)

    if actual_id:
        record_memory_operation(
            user_id=user_id,
            username=user.get("username", ""),
            action="graph_create_entity",
            detail=f"创建实体: {entity.name} ({entity.entity_type.value})",
        )
        # 记录变更日志
        change_mapper = get_graph_change_log_mapper()
        change_mapper.insert(
            user_id=user_id,
            event_type="entity_created",
            entity_id=actual_id,
            entity_name=entity.name,
            entity_type=entity.entity_type.value,
            before=None,
            after={"name": entity.name, "type": entity.entity_type.value, "description": entity.description},
        )
        return {"id": actual_id, "name": entity.name, "merged": actual_id != entity.id}
    else:
        raise HTTPException(status_code=500, detail="Failed to create entity")


@router.delete("/entities/{entity_id}")
async def delete_entity(
    entity_id: str,
    soft: bool = Query(True, description="是否软删除（默认True，设置deleted_at；False为物理删除）"),
    user: dict = Depends(_require_permission("graph.manage"))
):
    """删除实体（默认软删除，可通过 soft=false 物理删除）"""
    store = get_kg_store()

    # 删除前获取实体信息（用于日志）
    entity_before = store.get_entity(entity_id)
    before_data = None
    if entity_before:
        before_data = {
            "name": entity_before.name,
            "type": entity_before.entity_type.value if entity_before.entity_type else "",
            "description": entity_before.description,
        }

    success = store.delete_entity(entity_id, soft=soft)

    if success:
        user_id = user.get("user_id")
        
        # 同步删除实体向量（图谱删了、向量还在 → 幽灵召回）
        try:
            from backend.service.kb.entity_vectorstore import delete_entity_vectors
            delete_entity_vectors(user_id, entity_ids=[entity_id])
        except Exception as e:
            logger.warning(f"[Graph] 实体向量删除失败 entity_id={entity_id}: {e}")
            # 不阻断主流程，向量残留可通过 purge_orphan_vectors 清理
        
        record_memory_operation(
            user_id=user_id,
            username=user.get("username", ""),
            action="graph_delete_entity",
            detail=f"删除实体: {entity_id} (soft={soft})",
        )
        # 记录变更日志
        change_mapper = get_graph_change_log_mapper()
        change_mapper.insert(
            user_id=user_id,
            event_type="entity_deleted",
            entity_id=entity_id,
            entity_name=before_data.get("name", "") if before_data else entity_id,
            entity_type=before_data.get("type", "") if before_data else "",
            before=before_data,
            after=None,
        )
        return {"deleted": True, "soft_delete": soft}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete entity")


@router.post("/entities/{entity_id}/restore")
async def restore_entity(
    entity_id: str,
    user: dict = Depends(_require_permission("graph.manage"))
):
    """恢复已软删除的实体"""
    store = get_kg_store()

    # 恢复前获取实体信息（用于日志）
    entity_before = store.get_entity(entity_id)
    after_data = None
    if entity_before:
        after_data = {
            "name": entity_before.name,
            "type": entity_before.entity_type.value if entity_before.entity_type else "",
            "description": entity_before.description,
        }

    success = store.restore_entity(entity_id)

    if success:
        user_id = user.get("user_id")
        record_memory_operation(
            user_id=user_id,
            username=user.get("username", ""),
            action="graph_restore_entity",
            detail=f"恢复实体: {entity_id}",
        )
        # 记录变更日志
        change_mapper = get_graph_change_log_mapper()
        change_mapper.insert(
            user_id=user_id,
            event_type="entity_restored",
            entity_id=entity_id,
            entity_name=after_data.get("name", "") if after_data else entity_id,
            entity_type=after_data.get("type", "") if after_data else "",
            before=None,
            after=after_data,
        )
        return {"restored": True}
    else:
        raise HTTPException(status_code=500, detail="Failed to restore entity")


# ========== Relation Endpoints ==========

@router.get("/entities/{entity_id}/relations")
async def get_entity_relations(
    entity_id: str,
    direction: str = Query("both", regex="^(in|out|both)$"),
    relation_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """获取实体的关系"""
    store = get_kg_store()

    rtype = RelationType(relation_type.lower()) if relation_type else None

    related = store.get_related_entities(
        entity_id,
        relation_type=rtype,
        direction=direction,
        user_id=user.get("user_id"),
        limit=limit
    )
    
    return {
        "relations": [
            {
                "entity": r["entity"].to_dict(),
                "relation": r["relation"].to_dict() if r.get("relation") else None,
                "relation_type": r["rel_type"]
            }
            for r in related
        ],
        "count": len(related)
    }


@router.post("/relations")
async def create_relation(
    request: CreateRelationRequest,
    user: dict = Depends(_require_permission("graph.manage"))
):
    """创建关系"""
    store = get_kg_store()

    try:
        relation_type = RelationType(request.relation_type.lower())
    except ValueError:
        relation_type = RelationType.RELATED_TO

    relation = Relation(
        id="",  # 自动生成
        source_id=request.source_id,
        target_id=request.target_id,
        relation_type=relation_type,
        description=request.description or ""
    )

    # 生成 ID
    from backend.graphrag.extractor import EntityExtractor
    relation.id = EntityExtractor._generate_relation_id(
        relation.source_id, relation.target_id, relation.relation_type
    )

    user_id = user.get("user_id")
    success = store.create_relation(relation, user_id)

    if success:
        # 查询实体名称用于日志展示
        names = _resolve_entity_names(store, [request.source_id, request.target_id])
        source_name = names.get(request.source_id, request.source_id)
        target_name = names.get(request.target_id, request.target_id)

        record_memory_operation(
            user_id=user_id,
            username=user.get("username", ""),
            action="graph_create_relation",
            detail=f"创建关系: {source_name} -[{relation.relation_type.value}]-> {target_name}",
        )
        # 记录变更日志
        change_mapper = get_graph_change_log_mapper()
        change_mapper.insert(
            user_id=user_id,
            event_type="relation_created",
            entity_id=relation.id,
            entity_name=f"{source_name} -[{relation.relation_type.value}]-> {target_name}",
            entity_type=relation.relation_type.value,
            before=None,
            after={
                "source_id": request.source_id,
                "source_name": source_name,
                "target_id": request.target_id,
                "target_name": target_name,
                "relation_type": relation.relation_type.value,
                "description": request.description or "",
            },
        )
        return {"id": relation.id}
    else:
        raise HTTPException(status_code=500, detail="Failed to create relation")


# ========== Subgraph Endpoints ==========

@router.get("/subgraph/{entity_id}")
async def get_subgraph(
    entity_id: str,
    depth: int = Query(2, ge=1, le=4),
    user: dict = Depends(get_current_user)
):
    """获取子图（用于 vis.js 可视化）"""
    store = get_kg_store()

    subgraph = store.get_subgraph(entity_id, depth=depth, user_id=user.get("user_id"))
    
    return subgraph.to_visjs_format()


@router.get("/user-graph")
async def get_user_graph(
    limit: int = Query(1000, ge=1, le=10000),
    user: dict = Depends(get_current_user)
):
    """获取用户的知识图谱"""
    store = get_kg_store()

    user_id = user.get("user_id")
    subgraph = store.get_user_graph(user_id, limit=limit)

    return subgraph.to_visjs_format()


@router.get("/paths")
async def find_entity_paths(
    source_id: str = Query(..., description="起始实体 ID"),
    target_id: str = Query(..., description="目标实体 ID"),
    max_hops: int = Query(4, ge=1, le=6, description="最大跳数"),
    user: dict = Depends(get_current_user)
):
    """
    查找两个实体之间的所有路径（间接关系发现）

    不创建新边，只返回已有路径。路径本身就是解释。

    示例：查询甲和丙的关系
    → 返回路径：甲 →INVESTED→ 乙 →INVESTED→ 丙
    → 前端展示为"间接关系"卡片

    权限：graph.manage
    """
    store = get_kg_store()
    if not store.is_available():
        raise HTTPException(status_code=503, detail="Neo4j 不可用")

    paths = store.find_paths_between(
        source_id=source_id,
        target_id=target_id,
        user_id=user.get("user_id"),
        max_hops=max_hops
    )

    return {
        "source_id": source_id,
        "target_id": target_id,
        "paths": paths,
        "total_paths": len(paths)
    }


@router.get("/reachable")
async def get_reachable_entities(
    source_id: str = Query(..., description="起始实体 ID"),
    max_hops: int = Query(4, ge=1, le=6, description="最大跳数"),
    user: dict = Depends(get_current_user)
):
    """
    查询从某实体出发可达的所有实体（用于前端过滤目标候选）

    返回结果中的每个实体保证在 max_hops 跳内至少存在一条路径。
    使用与 find_paths_between 相同的 user_id 过滤逻辑。

    权限：graph.manage
    """
    store = get_kg_store()
    if not store.is_available():
        raise HTTPException(status_code=503, detail="Neo4j 不可用")

    entities = store.find_reachable_entities(
        source_id=source_id,
        user_id=user.get("user_id"),
        max_hops=max_hops
    )

    return {
        "source_id": source_id,
        "entities": entities,
        "total": len(entities)
    }


# ========== Extraction Endpoints ==========

@router.post("/extract")
async def extract_from_text(
    request: ExtractFromMemoryRequest,
    user: dict = Depends(_require_permission("graph.manage"))
):
    """从记忆提取实体和关系"""
    from backend.db.memory_mapper import get_episodic_mapper, get_semantic_mapper
    from asyncio import get_event_loop

    # 层级感知查找：先 episodic，后 semantic
    episodic_mapper = get_episodic_mapper()
    semantic_mapper = get_semantic_mapper()
    memory = episodic_mapper.get_memory_by_id(request.memory_id, user_id=user["user_id"]) or semantic_mapper.get_memory_by_id(request.memory_id, user_id=user["user_id"])
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    # 定义同步提取函数
    def _extract_sync():
        extractor = get_entity_extractor()
        return extractor.extract(
            text=memory["content"],
            source_memory_id=request.memory_id
        )
    
    # 在线程池中执行以避免阻塞
    try:
        loop = get_event_loop()
        result = await loop.run_in_executor(None, _extract_sync)
    except Exception as e:
        logger.error(f"Failed to extract: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to extract: {e}")
    
    # 存储到图数据库（含清理旧实体、实体对齐、跨层边）
    store = get_kg_store()
    user_id = user.get("user_id")

    # 先清理旧实体（幂等）
    store.delete_entities_by_memory_id(request.memory_id, user_id)

    created_entities = 0
    created_relations = 0
    entity_ids = []

    for entity in result.entities:
        entity.source_memory_id = request.memory_id
        created_id = store.create_entity(entity, user_id, enable_alignment=True)
        if created_id:
            created_entities += 1
            entity_ids.append(created_id)

    for relation in result.relations:
        relation.source_memory_id = request.memory_id
        if store.create_relation(relation, user_id):
            created_relations += 1

    # 创建跨层边
    if entity_ids:
        store.create_memory_entity_edges(request.memory_id, entity_ids, user_id)

    record_memory_operation(
        user_id=user_id,
        username=user.get("username", ""),
        action="graph_extract",
        memory_id=request.memory_id,
        detail=f"单条提取: {created_entities} 实体, {created_relations} 关系, 跨层边: {len(entity_ids)}",
    )

    return {
        "entities": [e.to_dict() for e in result.entities],
        "relations": [r.to_dict() for r in result.relations],
        "created_entities": created_entities,
        "created_relations": created_relations,
        "extraction_time": result.extraction_time
    }


@router.post("/extract-batch")
async def batch_extract_from_memories(
    user: dict = Depends(_require_permission("graph.manage")),
    limit: int = Query(50, ge=1, le=200),
    layer: str = Query("all", description="记忆层: episodic/semantic/all")
):
    """
    批量提取未处理的记忆（实体/关系 → KGStore）

    覆盖两层记忆表：episodic (memory_episodic), semantic (memory_semantic)。
    跳过已有实体的记忆（按 source_memory_id 去重）。
    """
    from backend.db.schema import get_conn
    from asyncio import get_event_loop

    user_id = user.get("user_id")

    # 根据 layer 参数收集待处理的记忆
    # 每项: {"id": int, "content": str, "layer": str}
    memories_to_process = []

    try:
        conn = get_conn()
        try:
            # 已处理过的 memory_id 集合（KGStore 中已有实体）
            # 通过 Neo4j 查询已有 source_memory_id，避免重复提取
            kg_store = get_kg_store()
            processed_memory_ids = set()
            if kg_store.is_available():
                try:
                    client = kg_store._get_graph_client()
                    result = client.run_query(
                        "MATCH (n) WHERE n.source_memory_id IS NOT NULL AND n.deleted_at IS NULL "
                        "RETURN DISTINCT n.source_memory_id AS mid"
                    )
                    processed_memory_ids = {row["mid"] for row in (result or []) if row.get("mid")}
                except Exception:
                    pass

            layers_to_process = ["episodic", "semantic"] if layer == "all" else [layer]

            for lyr in layers_to_process:
                if lyr == "episodic":
                    table = "memory_episodic"
                elif lyr == "semantic":
                    table = "memory_semantic"
                else:
                    continue

                # 查询该层中尚未提取实体的活跃记忆
                try:
                    cur = conn.execute(
                        f"""SELECT id, content FROM {table}
                            WHERE user_id = %s AND deleted_at IS NULL
                              AND content IS NOT NULL AND content != ''
                            ORDER BY id DESC
                            LIMIT %s""",
                        (user_id, limit)
                    )
                    rows = cur.fetchall() if hasattr(cur, "fetchall") else []
                    for row in rows:
                        row_id = row["id"]
                        if row_id not in processed_memory_ids:
                            memories_to_process.append({
                                "id": row_id,
                                "content": row["content"],
                                "layer": lyr,
                            })
                except Exception as e:
                    logger.warning(f"Failed to query {table}: {e}")
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Failed to collect memories for batch extract: {e}")

    if not memories_to_process:
        return {"processed": 0, "message": "No memories to process"}

    # 在线程池中执行提取，避免阻塞
    def _batch_extract_sync():
        extractor = get_entity_extractor()
        store = get_kg_store()

        processed = 0
        total_entities = 0
        total_relations = 0
        total_cross_edges = 0

        for memory in memories_to_process:
            mem_id = memory["id"]
            content = memory["content"]
            lyr = memory["layer"]

            # 先清理旧实体（幂等：防止重复提取）
            store.delete_entities_by_memory_id(mem_id, user_id)

            result = extractor.extract(
                text=content,
                source_memory_id=mem_id
            )

            entity_ids = []
            for entity in result.entities:
                entity.source_memory_id = mem_id
                created_id = store.create_entity(entity, user_id, enable_alignment=True)
                if created_id:
                    total_entities += 1
                    entity_ids.append(created_id)  # 使用实际存储的 ID

            for relation in result.relations:
                relation.source_memory_id = mem_id
                if store.create_relation(relation, user_id):
                    total_relations += 1

            # 创建 Memory ↔ Entity 跨层边
            if entity_ids:
                total_cross_edges += store.create_memory_entity_edges(mem_id, entity_ids, user_id)

            processed += 1

        return {
            "processed": processed,
            "total_entities": total_entities,
            "total_relations": total_relations,
            "total_cross_edges": total_cross_edges,
            "layers": list(set(m["layer"] for m in memories_to_process)),
        }

    try:
        loop = get_event_loop()
        result = await loop.run_in_executor(None, _batch_extract_sync)
    except Exception as e:
        logger.error(f"Failed to batch extract: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to batch extract: {e}")

    record_memory_operation(
        user_id=user.get("user_id"),
        username=user.get("username", ""),
        action="graph_batch_extract",
        detail=(
            f"批量提取: processed={result.get('processed', 0)}, "
            f"entities={result.get('total_entities', 0)}, "
            f"relations={result.get('total_relations', 0)}, "
            f"layers={result.get('layers', [])}"
        ),
    )

    return result


# ========== Statistics Endpoints ==========

@router.get("/stats")
async def get_graph_stats(
    quality: bool = Query(False, description="是否返回质量指标（置信度分布、矛盾检测等）"),
    user: dict = Depends(get_current_user)
):
    """获取图谱统计（可通过 quality=true 获取质量指标）"""
    store = get_kg_store()

    user_id = None
    perms = user.get("permissions") or set()
    # 如果不是管理员，只看自己的图谱
    if "graph.manage" not in perms and user.get("role") not in ("admin", "super_admin"):
        user_id = user.get("user_id")

    entity_count = store.count_entities(user_id)
    relation_count = store.count_relations(user_id)

    result = {
        "entity_count": entity_count,
        "relation_count": relation_count,
        "is_available": store.is_available()
    }

    # 质量指标（可选）
    if quality:
        result["quality"] = store.get_quality_stats(user_id)
        result["confidence_distribution"] = store.get_confidence_distribution(user_id)
        result["conflicts"] = store.detect_conflicts(user_id)

    return result


@router.get("/quality")
async def get_quality_report(
    user: dict = Depends(_require_permission("graph.manage"))
):
    """获取完整的质量报告（管理员专用）"""
    store = get_kg_store()

    return {
        "stats": store.get_quality_stats(),
        "confidence_distribution": store.get_confidence_distribution(),
        "conflicts": store.detect_conflicts(),
        "is_available": store.is_available()
    }


# ========== Document Extraction Endpoints ==========

class DocumentExtractRequest(BaseModel):
    """文档提取请求"""
    chunk_ids: Optional[list] = None  # 可选，指定提取哪些父片


@router.post("/documents/{document_id}/extract")
async def extract_from_document(
    document_id: int,
    request: Optional[DocumentExtractRequest] = None,
    user: dict = Depends(_require_permission("kb.manage"))
):
    """
    从知识库文档提取实体关系
    
    只提取父片内容，保留上下文完整性
    
    权限：kb.manage
    """
    from backend.service.kb.kb_graphrag_service import extract_document_entities
    from backend.service.kb.kb_service import get_document, KbNotFound
    
    # 验证文档存在
    user_id = user.get("user_id")
    try:
        doc = get_document(user_id, document_id, user.get("permissions") or set())
    except KbNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get document: {e}")
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # 提取 - 在线程池中执行以避免阻塞事件循环
    from asyncio import get_event_loop
    from concurrent.futures import ThreadPoolExecutor
    
    try:
        chunk_ids = request.chunk_ids if request else None
        loop = get_event_loop()
        result = await loop.run_in_executor(
            None,  # 使用默认线程池
            extract_document_entities,
            user_id, document_id, chunk_ids
        )
    except Exception as e:
        logger.error(f"Failed to extract entities: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to extract entities: {e}")

    record_memory_operation(
        user_id=user_id,
        username=user.get("username", ""),
        action="graph_doc_extract",
        detail=f"文档提取: doc_id={document_id}, entities={result['entities']}, relations={result['relations']}",
    )

    return {
        "document_id": document_id,
        "entities_created": result["entities"],
        "relations_created": result["relations"],
        "chunks_processed": result["chunks_processed"]
    }


@router.get("/documents/{document_id}/extracting")
async def is_document_extracting(
    document_id: int,
    user: dict = Depends(get_current_user)
):
    """
    检查文档是否正在提取中
    
    用于防止前端重复触发提取
    """
    from backend.service.kb.kb_graphrag_service import is_document_extracting as check_extracting
    return {
        "document_id": document_id,
        "extracting": check_extracting(document_id)
    }


@router.post("/documents/{document_id}/refresh")
async def refresh_document_entities(
    document_id: int,
    user: dict = Depends(_require_permission("kb.manage"))
):
    """
    重新提取文档实体（删除旧实体 + 重新提取）
    
    适用于文档内容修改后需要更新图谱的场景
    
    权限：kb.manage
    """
    from backend.service.kb.kb_graphrag_service import refresh_document_entities
    from backend.service.kb.kb_service import get_document
    
    # 验证文档存在
    user_id = user.get("user_id")
    doc = get_document(user_id, document_id, user.get("permissions") or set())

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # 刷新 - 在线程池中执行
    from asyncio import get_event_loop
    
    try:
        loop = get_event_loop()
        result = await loop.run_in_executor(
            None,
            refresh_document_entities,
            user_id, document_id
        )
    except Exception as e:
        logger.error(f"Failed to refresh entities: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh entities: {e}")

    record_memory_operation(
        user_id=user_id,
        username=user.get("username", ""),
        action="graph_doc_refresh",
        detail=f"文档刷新: doc_id={document_id}, deleted={result['deleted']}, extracted={result['extracted']}",
    )

    return {
        "document_id": document_id,
        "deleted": result["deleted"],
        "extracted": result["extracted"]
    }


@router.delete("/documents/{document_id}/entities")
async def clear_document_entities(
    document_id: int,
    user: dict = Depends(_require_permission("kb.manage"))
):
    """
    清除文档关联的所有实体
    
    权限：kb.manage
    """
    from backend.service.kb.kb_graphrag_service import clear_document_entities
    from backend.service.kb.kb_service import get_document
    
    # 验证文档存在
    user_id = user.get("user_id")
    doc = get_document(user_id, document_id, user.get("permissions") or set())

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # 清除 - 在线程池中执行
    from asyncio import get_event_loop
    
    try:
        loop = get_event_loop()
        result = await loop.run_in_executor(
            None,
            clear_document_entities,
            document_id
        )
    except Exception as e:
        logger.error(f"Failed to clear entities: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear entities: {e}")

    record_memory_operation(
        user_id=user_id,
        username=user.get("username", ""),
        action="graph_doc_clear",
        detail=f"文档实体清除: doc_id={document_id}, entities={result['deleted_entities']}, relations={result['deleted_relations']}",
    )

    return {
        "document_id": document_id,
        "deleted_relations": result["deleted_relations"],
        "deleted_entities": result["deleted_entities"]
    }


@router.get("/documents/{document_id}/extraction-progress")
async def get_extraction_progress(
    document_id: int,
    user: dict = Depends(_require_permission("graph.manage"))
):
    """
    获取文档提取进度
    
    返回文档的提取进度信息：
    - total_chunks: 总 chunk 数
    - processed_chunks: 已处理 chunk 数
    - pending_chunks: 待处理 chunk 数
    - percent: 完成百分比
    - entities_created: 已创建实体数
    - relations_created: 已创建关系数
    - status: 状态（pending/processing/completed）
    
    权限：graph.manage
    """
    from backend.service.kb.kb_graphrag_service import get_extraction_progress
    
    progress = get_extraction_progress(document_id)
    
    if progress is None:
        # 检查文档是否已提取完成
        from backend.service.kb.kb_service import get_document
        user_id = user.get("user_id")
        doc = get_document(user_id, document_id, user.get("permissions") or set())
        
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # 文档未在处理中
        return {
            "document_id": document_id,
            "status": "not_started" if not doc.get("graph_extracted") else "completed",
            "total_chunks": 0,
            "processed_chunks": 0,
            "pending_chunks": 0,
            "percent": 100.0 if doc.get("graph_extracted") else 0.0,
            "entities_created": 0,
            "relations_created": 0
        }
    
    return progress


@router.get("/extraction-progress")
async def get_all_extraction_progress(
    user: dict = Depends(_require_permission("graph.manage"))
):
    """
    获取所有文档的提取进度
    
    权限：graph.manage
    """
    from backend.service.kb.kb_graphrag_service import get_all_extraction_progress
    
    progress_list = get_all_extraction_progress()
    
    return {
        "total": len(progress_list),
        "progress": progress_list
    }


# ========== Time Travel Endpoints ==========

import re
from datetime import datetime


def _validate_iso_date(date_str: str) -> bool:
    """
    校验 ISO 8601 日期格式

    支持的格式：
    - YYYY-MM-DD (如 2020-06-15)
    - YYYY-MM (如 2020-06)
    - YYYY (如 2020)

    Returns:
        True if valid, False otherwise
    """
    patterns = [
        r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
        r'^\d{4}-\d{2}$',         # YYYY-MM
        r'^\d{4}$',               # YYYY
    ]

    for pattern in patterns:
        if re.match(pattern, date_str):
            # 尝试解析为日期
            try:
                if len(date_str) == 10:  # YYYY-MM-DD
                    datetime.strptime(date_str, '%Y-%m-%d')
                elif len(date_str) == 7:  # YYYY-MM
                    datetime.strptime(date_str, '%Y-%m')
                elif len(date_str) == 4:  # YYYY
                    datetime.strptime(date_str, '%Y')
                return True
            except ValueError:
                continue

    return False


@router.get("/entities/{entity_id}/time-travel/{target_date}")
async def get_entity_at_time(
    entity_id: str,
    target_date: str = Path(..., description="目标日期 (ISO 8601 格式，如 2020-06-15)"),
    direction: str = Query("both", pattern="^(in|out|both)$"),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """
    时间旅行查询：获取实体在指定历史时刻的关系

    基于关系的 valid_from/valid_until/is_current 字段，
    返回在 target_date 时刻有效的关系。

    示例：
    - 查询某人在 2020-01-01 时的任职情况
    - 查看历史某个时间点的团队结构

    权限：graph.manage
    """
    # 日期格式校验
    if not _validate_iso_date(target_date):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: '{target_date}'. Expected ISO 8601 format (YYYY-MM-DD, YYYY-MM, or YYYY)"
        )

    store = get_kg_store()

    related = store.get_related_entities_at_time(
        entity_id=entity_id,
        target_date=target_date,
        direction=direction,
        user_id=user.get("user_id"),
        limit=limit
    )

    return {
        "entity_id": entity_id,
        "target_date": target_date,
        "relations": [
            {
                "entity": r["entity"].to_dict(),
                "relation": r["relation"].to_dict() if r.get("relation") else None,
                "relation_type": r["rel_type"],
                "valid_from": r.get("valid_from"),
                "valid_until": r.get("valid_until")
            }
            for r in related
        ],
        "count": len(related)
    }


@router.get("/entities/{entity_id}/timeline")
async def get_entity_timeline(
    entity_id: str,
    relation_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    user: dict = Depends(get_current_user)
):
    """
    获取实体的时间线（所有关系的时间信息）

    返回该实体所有关系的时间属性，按时间排序。
    支持分页，用于展示实体的历史演变过程。

    示例：
    - 展示某人完整的职业经历时间线
    - 展示项目的发展历程

    权限：graph.manage
    """
    store = get_kg_store()

    rtype = RelationType(relation_type.lower()) if relation_type else None

    # 获取完整时间线（内部可优化为分页查询）
    all_timeline = store.get_entity_timeline(
        entity_id=entity_id,
        relation_type=rtype,
        user_id=user.get("user_id")
    )

    # 分页处理
    total = len(all_timeline)
    start = (page - 1) * page_size
    end = start + page_size
    timeline_page = all_timeline[start:end]

    return {
        "entity_id": entity_id,
        "timeline": [
            {
                "related_entity": item["related_entity"].to_dict(),
                "relation_type": item["relation_type"],
                "valid_from": item.get("valid_from"),
                "valid_until": item.get("valid_until"),
                "is_current": item.get("is_current", True),
                "description": item.get("description", "")
            }
            for item in timeline_page
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
            "has_next": end < total,
            "has_prev": page > 1
        }
    }


# ========== 审核候选 API ==========

@router.get("/candidates")
async def list_candidates(
    status: Optional[str] = Query(None, description="筛选状态：pending/merged/confirmed/ignored/edited"),
    candidate_type: Optional[str] = Query(None, description="筛选类型：duplicate/name_collision/low_confidence/relation_direction"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user: dict = Depends(_require_permission("graph.manage"))
):
    """分页查询审核候选列表"""
    from backend.db.kg_candidate_mapper import KgCandidateMapper
    mapper = KgCandidateMapper()
    user_id = user.get("user_id")
    candidates, total = mapper.list_candidates(
        user_id=user_id,
        status=status,
        candidate_type=candidate_type,
        page=page,
        page_size=page_size
    )
    return {
        "candidates": candidates,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
            "has_next": page * page_size < total,
            "has_prev": page > 1
        }
    }


@router.get("/candidates/count")
async def count_pending_candidates(
    user: dict = Depends(get_current_user)
):
    """获取待审核候选数量（用于 Tab badge）"""
    from backend.db.kg_candidate_mapper import KgCandidateMapper
    mapper = KgCandidateMapper()
    user_id = user.get("user_id")
    count = mapper.count_pending(user_id)
    return {"pending_count": count}


@router.post("/candidates/{candidate_id}/merge")
async def merge_candidate(
    candidate_id: int = Path(..., description="候选 ID"),
    user: dict = Depends(_require_permission("graph.manage"))
):
    """合并重复实体（A 保留，B 合并到 A）"""
    from backend.db.kg_candidate_mapper import KgCandidateMapper
    mapper = KgCandidateMapper()
    candidate = mapper.get_candidate(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Candidate already {candidate['status']}")

    store = get_kg_store()
    success = store.merge_entities(
        keep_id=candidate["entity_a_id"],
        remove_id=candidate["entity_b_id"],
        user_id=user.get("user_id")
    )
    if not success:
        raise HTTPException(status_code=500, detail="Merge failed")

    # 同步删除被合并实体的向量（图谱合并了、向量还在 → 幽灵召回）
    user_id = user.get("user_id")
    try:
        from backend.service.kb.entity_vectorstore import delete_entity_vectors
        delete_entity_vectors(user_id, entity_ids=[candidate["entity_b_id"]])
    except Exception as e:
        logger.warning(f"[Graph] 被合并实体向量删除失败 entity_id={candidate['entity_b_id']}: {e}")

    mapper.update_status(candidate_id, "merged")
    return {"merged": True, "kept": candidate["entity_a_id"], "removed": candidate["entity_b_id"]}


@router.post("/candidates/{candidate_id}/confirm")
async def confirm_candidate(
    candidate_id: int = Path(...),
    user: dict = Depends(_require_permission("graph.manage"))
):
    """确认候选正确（标记为 confirmed）"""
    from backend.db.kg_candidate_mapper import KgCandidateMapper
    mapper = KgCandidateMapper()
    candidate = mapper.get_candidate(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    mapper.update_status(candidate_id, "confirmed")
    return {"confirmed": True}


@router.post("/candidates/{candidate_id}/ignore")
async def ignore_candidate(
    candidate_id: int = Path(...),
    user: dict = Depends(_require_permission("graph.manage"))
):
    """忽略候选（标记为 ignored）"""
    from backend.db.kg_candidate_mapper import KgCandidateMapper
    mapper = KgCandidateMapper()
    candidate = mapper.get_candidate(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    mapper.update_status(candidate_id, "ignored")
    return {"ignored": True}


# ========== 实体/关系编辑 API ==========

@router.put("/entities/{entity_id}")
async def edit_entity(
    entity_id: str = Path(...),
    request: EditEntityRequest = ...,
    user: dict = Depends(_require_permission("graph.manage"))
):
    """编辑实体属性（名称/描述/别名）"""
    store = get_kg_store()

    # 编辑前获取实体信息（用于日志）
    entity_before = store.get_entity(entity_id)
    before_data = None
    if entity_before:
        before_data = {
            "name": entity_before.name,
            "type": entity_before.entity_type.value if entity_before.entity_type else "",
            "description": entity_before.description,
            "aliases": entity_before.aliases or [],
        }

    success = store.edit_entity(
        entity_id=entity_id,
        name=request.name,
        description=request.description,
        aliases=request.aliases,
        user_id=user.get("user_id")
    )
    if not success:
        raise HTTPException(status_code=500, detail="Edit entity failed")

    # 记录变更日志
    user_id = user.get("user_id")
    change_mapper = get_graph_change_log_mapper()
    change_mapper.insert(
        user_id=user_id,
        event_type="entity_updated",
        entity_id=entity_id,
        entity_name=request.name,
        entity_type=before_data.get("type", "") if before_data else "",
        before=before_data,
        after={
            "name": request.name,
            "description": request.description,
            "aliases": request.aliases or [],
        },
    )
    return {"updated": True, "entity_id": entity_id}


@router.post("/relations/{relation_id}/flip")
async def flip_relation(
    relation_id: str = Path(...),
    user: dict = Depends(_require_permission("graph.manage"))
):
    """翻转关系方向（source ↔ target 互换）"""
    store = get_kg_store()

    # 翻转前获取关系信息（用于日志）
    relations = store.get_relation_by_id(relation_id)
    before_data = None
    if relations:
        names = _resolve_entity_names(store, [relations.source_id, relations.target_id])
        rel_type = relations.relation_type.value if relations.relation_type else ""
        before_data = {
            "source_id": relations.source_id,
            "source_name": names.get(relations.source_id, relations.source_id),
            "target_id": relations.target_id,
            "target_name": names.get(relations.target_id, relations.target_id),
            "relation_type": rel_type,
            "description": relations.description,
        }

    success = store.flip_relation_direction(relation_id)
    if not success:
        raise HTTPException(status_code=500, detail="Flip relation failed")

    # 记录变更日志
    user_id = user.get("user_id")
    change_mapper = get_graph_change_log_mapper()
    change_mapper.insert(
        user_id=user_id,
        event_type="relation_flipped",
        entity_id=relation_id,
        entity_name=_relation_log_name(store,
            before_data.get("source_id", "") if before_data else "",
            before_data.get("target_id", "") if before_data else "",
            before_data.get("relation_type", "") if before_data else ""
        ) if before_data else "",
        entity_type=before_data.get("relation_type", "") if before_data else "",
        before=before_data,
        after={
            "source_id": before_data.get("target_id", "") if before_data else "",
            "source_name": before_data.get("target_name", "") if before_data else "",
            "target_id": before_data.get("source_id", "") if before_data else "",
            "target_name": before_data.get("source_name", "") if before_data else "",
            "relation_type": before_data.get("relation_type", "") if before_data else "",
            "description": before_data.get("description", "") if before_data else "",
        } if before_data else None,
    )
    return {"flipped": True, "relation_id": relation_id}


@router.put("/relations/{relation_id}")
async def edit_relation(
    relation_id: str = Path(...),
    request: EditRelationRequest = ...,
    user: dict = Depends(_require_permission("graph.manage"))
):
    """编辑关系属性（描述/时间属性）"""
    store = get_kg_store()

    # 编辑前获取关系信息（用于日志）
    relations = store.get_relation_by_id(relation_id)
    before_data = None
    if relations:
        names = _resolve_entity_names(store, [relations.source_id, relations.target_id])
        rel_type = relations.relation_type.value if relations.relation_type else ""
        before_data = {
            "source_name": names.get(relations.source_id, relations.source_id),
            "target_name": names.get(relations.target_id, relations.target_id),
            "relation_type": rel_type,
            "description": relations.description,
            "valid_from": relations.valid_from,
            "valid_until": relations.valid_until,
            "is_current": relations.is_current,
        }

    success = store.edit_relation(
        relation_id=relation_id,
        description=request.description,
        valid_from=request.valid_from,
        valid_until=request.valid_until,
        is_current=request.is_current
    )
    if not success:
        raise HTTPException(status_code=500, detail="Edit relation failed")

    # 记录变更日志
    user_id = user.get("user_id")
    change_mapper = get_graph_change_log_mapper()
    change_mapper.insert(
        user_id=user_id,
        event_type="relation_updated",
        entity_id=relation_id,
        entity_name=_relation_log_name(store,
            relations.source_id if relations else "",
            relations.target_id if relations else "",
            relations.relation_type.value if relations and relations.relation_type else ""
        ) if relations else "",
        entity_type=before_data.get("relation_type", "") if before_data else "",
        before=before_data,
        after={
            "description": request.description,
            "valid_from": request.valid_from,
            "valid_until": request.valid_until,
            "is_current": request.is_current,
        },
    )
    return {"updated": True, "relation_id": relation_id}


@router.delete("/relations/{relation_id}")
async def delete_relation(
    relation_id: str = Path(...),
    user: dict = Depends(_require_permission("graph.manage"))
):
    """删除关系"""
    store = get_kg_store()

    # 删除前获取关系信息（用于日志）
    relations = store.get_relation_by_id(relation_id)
    before_data = None
    if relations:
        names = _resolve_entity_names(store, [relations.source_id, relations.target_id])
        rel_type = relations.relation_type.value if relations.relation_type else ""
        before_data = {
            "source_id": relations.source_id,
            "source_name": names.get(relations.source_id, relations.source_id),
            "target_id": relations.target_id,
            "target_name": names.get(relations.target_id, relations.target_id),
            "relation_type": rel_type,
            "description": relations.description,
        }

    success = store.delete_relation(relation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Relation not found")

    # 记录变更日志
    user_id = user.get("user_id")
    change_mapper = get_graph_change_log_mapper()
    change_mapper.insert(
        user_id=user_id,
        event_type="relation_deleted",
        entity_id=relation_id,
        entity_name=_relation_log_name(store,
            relations.source_id if relations else "",
            relations.target_id if relations else "",
            relations.relation_type.value if relations and relations.relation_type else ""
        ) if relations else "",
        entity_type=before_data.get("relation_type", "") if before_data else "",
        before=before_data,
        after=None,
    )
    return {"deleted": True, "relation_id": relation_id}


# ========== 变更历史 API ==========

@router.get("/change-logs")
async def get_change_logs(
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    event_type: Optional[str] = Query(None, description="筛选事件类型"),
    user: dict = Depends(get_current_user)
):
    """
    获取当前用户的图谱变更历史

    事件类型：entity_created, entity_updated, entity_deleted, entity_restored,
             relation_created, relation_updated, relation_deleted, relation_flipped
    """
    change_mapper = get_graph_change_log_mapper()
    user_id = user.get("user_id")

    logs = change_mapper.list_by_user(
        user_id=user_id,
        limit=limit,
        offset=offset,
        event_type=event_type,
    )
    total = change_mapper.count_by_user(user_id)

    # 格式化时间
    for item in logs:
        if item.get("created_at"):
            item["created_at"] = item["created_at"].isoformat() if hasattr(item["created_at"], "isoformat") else str(item["created_at"])

    return {
        "logs": logs,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/entities/{entity_id}/change-logs")
async def get_entity_change_logs(
    entity_id: str = Path(...),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """获取指定实体的变更历史"""
    change_mapper = get_graph_change_log_mapper()
    logs = change_mapper.list_by_entity(entity_id=entity_id, limit=limit)

    # 格式化时间
    for item in logs:
        if item.get("created_at"):
            item["created_at"] = item["created_at"].isoformat() if hasattr(item["created_at"], "isoformat") else str(item["created_at"])

    return {
        "logs": logs,
        "count": len(logs),
    }


@router.get("/change-logs/{log_id}")
async def get_change_log_detail(
    log_id: int = Path(...),
    user: dict = Depends(get_current_user)
):
    """获取单条变更日志详情"""
    change_mapper = get_graph_change_log_mapper()
    log_item = change_mapper.get_by_id(log_id)

    if not log_item:
        raise HTTPException(status_code=404, detail="Log not found")

    # 检查权限：只能查看自己的日志（除非是 admin）
    user_id = user.get("user_id")
    if log_item.get("user_id") != user_id:
        # 检查是否有 admin 权限
        from backend.permission.checker import has_perm
        if not has_perm(user, "graph.manage"):
            raise HTTPException(status_code=403, detail="No permission")

    # 格式化时间
    if log_item.get("created_at"):
        log_item["created_at"] = log_item["created_at"].isoformat() if hasattr(log_item["created_at"], "isoformat") else str(log_item["created_at"])

    return log_item


@router.post("/change-logs/{log_id}/rollback")
async def rollback_change(
    log_id: int = Path(...),
    user: dict = Depends(_require_permission("graph.manage"))
):
    """
    回滚到指定变更之前的状态

    根据变更日志的 before_json 恢复实体/关系到修改前的状态。
    回滚操作本身也会记录为一条新的变更日志（event_type=rollback）。
    """
    change_mapper = get_graph_change_log_mapper()
    log_item = change_mapper.get_by_id(log_id)

    if not log_item:
        raise HTTPException(status_code=404, detail="Log not found")

    # 检查权限：只能回滚自己的日志（除非是 admin）
    user_id = user.get("user_id")
    if log_item.get("user_id") != user_id:
        from backend.permission.checker import has_perm
        if not has_perm(user, "graph.manage"):
            raise HTTPException(status_code=403, detail="No permission to rollback this log")

    event_type = log_item.get("event_type", "")
    entity_id = log_item.get("entity_id")
    before_data = log_item.get("before_json") or {}
    after_data = log_item.get("after_json") or {}

    store = get_kg_store()
    rollback_success = False
    rollback_detail = ""

    try:
        if event_type == "entity_created":
            # 回滚创建 = 删除实体
            if entity_id:
                rollback_success = store.delete_entity(entity_id, soft=True)
                rollback_detail = f"删除了创建的实体: {log_item.get('entity_name', entity_id)}"

        elif event_type == "entity_deleted":
            # 回滚删除 = 恢复实体
            if entity_id:
                rollback_success = store.restore_entity(entity_id)
                rollback_detail = f"恢复了删除的实体: {log_item.get('entity_name', entity_id)}"

        elif event_type == "entity_updated":
            # 回滚更新 = 用 before_json 恢复属性
            if entity_id and before_data:
                rollback_success = store.edit_entity(
                    entity_id=entity_id,
                    name=before_data.get("name"),
                    description=before_data.get("description"),
                    aliases=before_data.get("aliases"),
                    user_id=user_id
                )
                rollback_detail = f"恢复了实体属性: {before_data.get('name', entity_id)}"

        elif event_type == "entity_restored":
            # 回滚恢复 = 再次删除实体
            if entity_id:
                rollback_success = store.delete_entity(entity_id, soft=True)
                rollback_detail = f"重新删除了实体: {log_item.get('entity_name', entity_id)}"

        elif event_type == "relation_created":
            # 回滚创建关系 = 删除关系
            if entity_id:
                rollback_success = store.delete_relation(entity_id)
                rollback_detail = f"删除了创建的关系: {entity_id}"

        elif event_type == "relation_deleted":
            # 回滚删除关系 = 重新创建关系
            if before_data:
                from backend.graphrag import Relation, RelationType
                rel_type_str = before_data.get("relation_type", "related_to").lower()
                try:
                    rel_type = RelationType(rel_type_str)
                except ValueError:
                    rel_type = RelationType.RELATED_TO

                relation = Relation(
                    id=entity_id or "",
                    source_id=before_data.get("source_id", ""),
                    target_id=before_data.get("target_id", ""),
                    relation_type=rel_type,
                    description=before_data.get("description", "")
                )
                rollback_success = store.create_relation(relation, user_id)
                # 用名称展示（如果有），否则用 ID
                src = before_data.get("source_name") or before_data.get("source_id", "")
                tgt = before_data.get("target_name") or before_data.get("target_id", "")
                rollback_detail = f"恢复了删除的关系: {src} -> {tgt}"

        elif event_type == "relation_updated":
            # 回滚更新关系 = 用 before_json 恢复属性
            if entity_id and before_data:
                rollback_success = store.edit_relation(
                    relation_id=entity_id,
                    description=before_data.get("description"),
                    valid_from=before_data.get("valid_from"),
                    valid_until=before_data.get("valid_until"),
                    is_current=before_data.get("is_current")
                )
                rollback_detail = f"恢复了关系属性: {entity_id}"

        elif event_type == "relation_flipped":
            # 回滚翻转 = 再次翻转
            if entity_id:
                rollback_success = store.flip_relation_direction(entity_id)
                rollback_detail = f"恢复了关系方向: {entity_id}"

        else:
            raise HTTPException(status_code=400, detail=f"Unknown event type: {event_type}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Rollback] Failed for log_id={log_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}")

    if not rollback_success:
        raise HTTPException(status_code=500, detail="Rollback operation returned failure")

    # 记录回滚操作本身的变更日志
    change_mapper.insert(
        user_id=user_id,
        event_type="rollback",
        entity_id=entity_id,
        entity_name=log_item.get("entity_name", ""),
        entity_type=log_item.get("entity_type", ""),
        before=after_data,  # 回滚前的状态（即原操作的 after）
        after=before_data,  # 回滚后的状态（即原操作的 before）
    )

    record_memory_operation(
        user_id=user_id,
        username=user.get("username", ""),
        action="graph_rollback",
        detail=f"回滚操作 log_id={log_id}: {rollback_detail}",
    )

    return {
        "rolled_back": True,
        "log_id": log_id,
        "event_type": event_type,
        "detail": rollback_detail,
    }


# ========== 社区检测 & GraphRAG API ==========

class CommunityDetectRequest(BaseModel):
    """社区检测请求"""
    pass


class CommunityReportRequest(BaseModel):
    """社区报告生成请求"""
    level: Optional[int] = None  # None = 全部层级


class SmartSearchRequest(BaseModel):
    """智能检索请求"""
    query: str
    mode: str = "smart"  # smart / local / global / drift
    top_k: int = 5


@router.post("/communities/detect")
async def detect_communities_endpoint(
    user: dict = Depends(_require_permission("graph.manage"))
):
    """
    执行社区检测（Louvain 算法）

    从 Neo4j 读取全部节点和关系，运行 Louvain 社区检测，
    生成层次化社区结构（Level 0 最细粒度，Level 1-3 逐渐合并），
    结果存储到 MySQL kg_communities 表。

    权限：graph.manage
    """
    from backend.graphrag.community_detector import detect_communities
    from asyncio import get_event_loop

    user_id = user.get("user_id")

    try:
        loop = get_event_loop()
        result = await loop.run_in_executor(None, detect_communities, user_id)
    except Exception as e:
        logger.error(f"社区检测失败: {e}")
        raise HTTPException(status_code=500, detail=f"社区检测失败: {e}")

    record_memory_operation(
        user_id=user_id,
        username=user.get("username", ""),
        action="graph_community_detect",
        detail=f"社区检测: {result.get('communities', 0)} 个社区, {result.get('levels', 0)} 层",
    )

    return result


@router.post("/communities/generate-reports")
async def generate_community_reports_endpoint(
    request: Optional[CommunityReportRequest] = None,
    user: dict = Depends(_require_permission("graph.manage"))
):
    """
    启动社区报告后台生成任务

    异步启动，立即返回 task_id。前端通过 /communities/report-progress/{task_id}
    轮询进度。报告逐个存储到 MySQL，生成过程中可刷新页面查看已完成报告。

    权限：graph.manage
    """
    from backend.graphrag.community_reporter import start_report_generation

    user_id = user.get("user_id")
    level = request.level if request else None

    try:
        task_id = start_report_generation(user_id, level)
    except Exception as e:
        logger.error(f"启动报告生成任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动报告生成任务失败: {e}")

    record_memory_operation(
        user_id=user_id,
        username=user.get("username", ""),
        action="graph_community_reports",
        detail=f"启动报告生成任务: {task_id}",
    )

    return {"task_id": task_id, "status": "started"}


@router.get("/communities/report-progress/{task_id}")
async def get_report_progress_endpoint(
    task_id: str,
    user: dict = Depends(_require_permission("graph.manage"))
):
    """
    查询报告生成进度

    返回：
    - status: starting / running / completed / failed
    - total: 总社区数
    - generated: 已成功数
    - failed: 失败数
    - current: 当前处理到第几个

    权限：graph.manage
    """
    from backend.graphrag.community_reporter import get_report_generation_progress

    progress = get_report_generation_progress(task_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    return progress


@router.get("/communities")
async def list_communities(
    level: Optional[int] = Query(None, description="社区层级（0=最细，不传则全部）"),
    user: dict = Depends(_require_permission("graph.manage"))
):
    """
    获取社区列表

    返回社区的基本信息：ID、层级、实体数、关系数等。

    权限：graph.manage
    """
    from backend.graphrag.community_detector import get_communities

    user_id = user.get("user_id")
    communities = get_communities(user_id, level)

    return {
        "communities": communities,
        "count": len(communities),
        "level_filter": level
    }


@router.get("/communities/reports")
async def list_community_reports(
    level: Optional[int] = Query(None, description="社区层级过滤"),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(_require_permission("graph.manage"))
):
    """
    获取社区报告列表

    返回已生成的社区报告：标题、摘要、评分、关键发现等。

    权限：graph.manage
    """
    from backend.graphrag.community_reporter import get_community_reports

    user_id = user.get("user_id")
    reports = get_community_reports(user_id, level, limit)

    return {
        "reports": reports,
        "count": len(reports)
    }


@router.get("/communities/{community_id}/report")
async def get_community_report(
    community_id: str = Path(...),
    user: dict = Depends(_require_permission("graph.manage"))
):
    """获取指定社区的报告详情

    权限：graph.manage
    """
    from backend.db.schema import get_conn

    user_id = user.get("user_id")

    conn = get_conn()
    try:
        cur = conn.execute(
            """SELECT r.community_id, r.title, r.summary, r.full_content,
                      r.rating, r.findings, r.top_entities, r.status,
                      c.level, c.entity_count, c.relationship_count
               FROM kg_community_reports r
               JOIN kg_communities c ON r.community_id = c.id
               WHERE r.community_id = %s AND c.user_id = %s""",
            (community_id, user_id)
        )
        row = cur.fetchone() if hasattr(cur, 'fetchone') else None
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Community report not found")

    findings = row.get('findings', '[]')
    top_entities = row.get('top_entities', '[]')
    if isinstance(findings, str):
        findings = json.loads(findings)
    if isinstance(top_entities, str):
        top_entities = json.loads(top_entities)

    return {
        "community_id": row['community_id'],
        "title": row['title'],
        "summary": row['summary'],
        "full_content": row['full_content'],
        "rating": row['rating'],
        "findings": findings,
        "top_entities": top_entities,
        "level": row['level'],
        "entity_count": row['entity_count'],
        "relationship_count": row['relationship_count'],
        "status": row['status']
    }


@router.post("/smart-search")
async def smart_search(
    request: SmartSearchRequest,
    user: dict = Depends(_require_permission("graph.manage"))
):
    """
    智能检索（GraphRAG 统一入口）

    根据查询内容自动路由到合适的检索模式：
    - LOCAL: 具体实体问题 → Vector + BM25 + Graph 三路混合检索
    - GLOBAL: 全局主题问题 → 社区报告 Map-Reduce
    - DRIFT: 混合问题 → 社区上下文 + 实体扩展

    也可通过 mode 参数强制指定模式。

    权限：graph.manage
    """
    from backend.service.kb.graphrag_retriever import smart_retrieve

    user_id = user.get("user_id")
    mode = request.mode if request.mode != "smart" else None

    try:
        result = smart_retrieve(
            user_id=user_id,
            query=request.query,
            top_k=request.top_k,
            query_type=mode
        )
    except Exception as e:
        logger.error(f"智能检索失败: {e}")
        raise HTTPException(status_code=500, detail=f"智能检索失败: {e}")

    return result


# ========== Permission Registration ==========

def register_graph_permissions():
    """注册图谱相关权限（已合并为单一的 graph.manage）"""
    from backend.permission.registry import register_perm

    register_perm(
        key="graph.manage",
        label="管理知识图谱",
        description=(
            "知识图谱统一权限：查看图谱（节点/关系/子图/路径）、实体与关系的新增/编辑/删除、"
            "实体审核（可疑实体与关系）、社区检测（Louvain）与社区报告、GraphRAG 智能检索"
        ),
        group_name="kb",
        group_label="知识库",
    )


def register_routes(app):
    """注册路由"""
    # 注册权限
    register_graph_permissions()
    
    app.include_router(router)
    logger.info("GraphRAG API registered")