"""
记忆条目管理 API — 支持三层记忆系统

功能：
- 按类型（preference/fact/event/skill）管理记忆
- 向量检索
- 图关联查看
- 手动触发合并
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from backend.service.memory.memory_service import get_memory_service, MemoryService
from backend.service.auth.auth_middleware import get_current_user
from backend.service.memory_audit_service import record_memory_operation
from backend.utils.log_utils import log

logger = log

router = APIRouter(prefix="/api/memories", tags=["记忆条目管理"])


def _get_client_ip(request: Request) -> str:
    """获取客户端 IP（兼容代理）"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _audit(user: dict, action: str, memory_id: Optional[int] = None,
           memory_layer: str = "", detail: str = "", ip: str = "", status: int = 1):
    """快捷审计记录"""
    record_memory_operation(
        user_id=user.get("user_id"),
        username=user.get("username", ""),
        action=action,
        memory_id=memory_id,
        memory_layer=memory_layer,
        detail=detail,
        ip_address=ip,
        status=status,
    )


# ========== 权限检查 ==========

def _has_perm(user: dict, perm: str) -> bool:
    role = user.get("role", "")
    if role in ("admin", "super_admin"):
        return True
    perms = user.get("permissions") or set()
    if isinstance(perms, list):
        perms = set(perms)
    return perm in perms


def _require_edit(user: dict = Depends(get_current_user)) -> dict:
    if not _has_perm(user, "memory.edit"):
        raise HTTPException(status_code=403, detail="需要个人记忆管理权限（memory.edit）")
    return user


# ========== 请求/响应模型 ==========

class CreateMemoryRequest(BaseModel):
    """创建记忆请求"""
    memory_type: str = Field(..., description="记忆类型: preference/fact/event/skill")
    content: str = Field(..., min_length=1, description="记忆内容")
    importance: float = Field(default=0.5, ge=0, le=1, description="重要性分数 (0-1)")


class UpdateMemoryRequest(BaseModel):
    """更新记忆请求"""
    content: Optional[str] = Field(None, description="新的记忆内容")
    importance: Optional[float] = Field(None, ge=0, le=1, description="新的重要性分数")


class SearchMemoryRequest(BaseModel):
    """搜索记忆请求"""
    query: str = Field(..., min_length=1, description="搜索查询")
    memory_type: Optional[str] = Field(None, description="记忆类型过滤")
    top_k: int = Field(default=10, ge=1, le=100, description="返回数量")


class MemoryItemResponse(BaseModel):
    """记忆条目响应"""
    id: int
    user_id: int
    memory_type: str
    content: str
    importance_score: float
    version: int = 1
    source_thread_id: Optional[str] = None
    access_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    embedding_id: Optional[str] = None
    graph_node_id: Optional[str] = None


class MemoryStatsResponse(BaseModel):
    """记忆统计响应"""
    total: int
    by_type: dict
    episodic: int = 0
    semantic: int = 0


class PromoteMemoryRequest(BaseModel):
    """晋升记忆请求"""
    content: Optional[str] = Field(None, description="可选：修改后的内容（为空则使用原内容）")
    importance: Optional[float] = Field(None, ge=0, le=1, description="可选：新的重要性分数")


class EpisodicMemoryResponse(BaseModel):
    """情景记忆响应（近期记忆）"""
    id: int
    user_id: int
    memory_type: str
    content: str
    importance_score: float
    access_count: int = 0
    ttl_days: int = 30
    expires_at: Optional[datetime] = None
    source_thread_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    embedding_id: Optional[str] = None


class SemanticMemoryResponse(BaseModel):
    """语义记忆响应（永久知识）"""
    id: int
    user_id: int
    memory_type: str
    content: str
    importance_score: float
    access_count: int = 0
    source_thread_id: Optional[str] = None
    source_episodic_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    embedding_id: Optional[str] = None
    graph_node_id: Optional[str] = None


class ConsolidationResultResponse(BaseModel):
    """合并结果响应"""
    deduped: int
    merged: int
    expired: int
    delete_from_db: List[int]
    update_count: int
    remaining: int


# ========== API 端点 ==========

@router.get("", response_model=List[MemoryItemResponse])
async def list_memories(
    memory_type: Optional[str] = Query(None, description="记忆类型过滤"),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """
    获取用户的记忆列表

    支持按类型过滤：preference/fact/event/skill
    """
    service = get_memory_service()

    if memory_type and memory_type not in MemoryService.MEMORY_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的记忆类型，可选: {MemoryService.MEMORY_TYPES}")

    memories = service.get_user_memories(
        user_id=user["user_id"],
        memory_type=memory_type,
        limit=limit
    )

    return [MemoryItemResponse(**m) for m in memories]


@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(user: dict = Depends(get_current_user)):
    """获取用户记忆统计"""
    service = get_memory_service()
    stats = service.get_memory_stats(user["user_id"])
    return MemoryStatsResponse(**stats)


# ========== 两层记忆 API（情景记忆 + 语义记忆）==========
# 注意：静态路由必须在 /{memory_id} 动态路由之前定义，
# 否则 FastAPI 会把 "episodic" 等字符串当成 memory_id 解析

@router.get("/episodic", response_model=List[EpisodicMemoryResponse])
async def list_episodic_memories(
    memory_type: Optional[str] = Query(None, description="记忆类型过滤"),
    include_expired: bool = Query(False, description="是否包含已过期的记忆"),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """
    获取用户的情景记忆列表（近期记忆）

    情景记忆特点：
    - 有 TTL（默认 30 天）
    - 过期后会被自动清理
    - 可以通过晋升转为语义记忆
    """
    service = get_memory_service()

    memories = service.get_episodic_memories(
        user_id=user["user_id"],
        memory_type=memory_type,
        include_expired=include_expired,
        limit=limit
    )

    return [EpisodicMemoryResponse(**m) for m in memories]


@router.get("/semantic", response_model=List[SemanticMemoryResponse])
async def list_semantic_memories(
    memory_type: Optional[str] = Query(None, description="记忆类型过滤"),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """
    获取用户的语义记忆列表（永久知识）

    语义记忆特点：
    - 永久存储，无 TTL
    - 会写入知识图谱
    - 可由情景记忆晋升而来
    """
    service = get_memory_service()

    memories = service.get_semantic_memories(
        user_id=user["user_id"],
        memory_type=memory_type,
        limit=limit
    )

    return [SemanticMemoryResponse(**m) for m in memories]


@router.get("/episodic/stats")
async def get_episodic_stats(user: dict = Depends(get_current_user)):
    """获取情景记忆统计"""
    service = get_memory_service()

    stats = service.get_episodic_stats(user["user_id"])
    return stats


@router.get("/semantic/stats")
async def get_semantic_stats(user: dict = Depends(get_current_user)):
    """获取语义记忆统计"""
    service = get_memory_service()

    stats = service.get_semantic_stats(user["user_id"])
    return stats


# ========== 记忆监控看板 ==========

@router.get("/dashboard")
async def get_memory_dashboard(user: dict = Depends(get_current_user)):
    """
    记忆系统监控看板

    返回各层记忆数量、合并统计、Outbox 健康状态、
    向量化/图节点覆盖率、加密覆盖率、版本历史统计、TTL 到期预警。

    需要 memory.view 权限（可在角色编辑里勾选）。
    """
    if not _has_perm(user, "memory.view"):
        raise HTTPException(status_code=403, detail="无权限查看记忆看板")

    from backend.service.memory.memory_dashboard import get_memory_dashboard_service
    dashboard_service = get_memory_dashboard_service()
    return dashboard_service.get_dashboard()


@router.get("/{memory_id}", response_model=MemoryItemResponse)
async def get_memory(memory_id: int, user: dict = Depends(get_current_user)):
    """获取单个记忆详情"""
    service = get_memory_service()
    memory = service.get_memory(memory_id, user_id=user["user_id"])
    
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    
    # 权限检查：只能查看自己的记忆
    if memory["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权查看他人记忆")

    return MemoryItemResponse(**memory)


@router.post("", response_model=MemoryItemResponse, status_code=201)
async def create_memory(req: CreateMemoryRequest, request: Request, user: dict = Depends(_require_edit)):
    """
    创建新记忆

    支持四种类型：
    - preference: 用户偏好
    - fact: 事实知识
    - event: 事件记录
    - skill: 技能知识
    """
    service = get_memory_service()

    if req.memory_type not in MemoryService.MEMORY_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的记忆类型，可选: {MemoryService.MEMORY_TYPES}")

    memory_id = service.create_memory(
        user_id=user["user_id"],
        memory_type=req.memory_type,
        content=req.content,
        importance_score=req.importance,
        vectorize=True,
        extract_graph=True
    )

    if not memory_id:
        _audit(user, "create", detail=f"失败: type={req.memory_type}", ip=_get_client_ip(request), status=0)
        raise HTTPException(status_code=500, detail="创建记忆失败")

    _audit(user, "create", memory_id=memory_id, memory_layer="episodic",
           detail=f"type={req.memory_type}, content={req.content[:50]}", ip=_get_client_ip(request))

    memory = service.get_memory(memory_id, user_id=user["user_id"])
    return MemoryItemResponse(**memory)


@router.put("/{memory_id}", response_model=MemoryItemResponse)
async def update_memory(
    memory_id: int,
    req: UpdateMemoryRequest,
    request: Request,
    user: dict = Depends(_require_edit)
):
    """更新记忆内容或重要性"""
    service = get_memory_service()

    # 获取现有记忆
    memory = service.get_memory(memory_id, user_id=user["user_id"])
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")

    # 权限检查
    if memory["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权修改他人记忆")

    # 更新
    success = service.update_memory(
        memory_id=memory_id,
        content=req.content,
        importance_score=req.importance,
        re_vectorize=True,
        user_id=user["user_id"]
    )

    if not success:
        _audit(user, "update", memory_id=memory_id, detail="失败", ip=_get_client_ip(request), status=0)
        raise HTTPException(status_code=500, detail="更新记忆失败")

    _audit(user, "update", memory_id=memory_id,
           detail=f"content={req.content[:50] if req.content else ''}, importance={req.importance}",
           ip=_get_client_ip(request))

    memory = service.get_memory(memory_id, user_id=user["user_id"])
    return MemoryItemResponse(**memory)


@router.delete("/{memory_id}")
async def delete_memory(memory_id: int, request: Request, user: dict = Depends(_require_edit)):
    """删除记忆"""
    service = get_memory_service()

    # 获取现有记忆
    memory = service.get_memory(memory_id, user_id=user["user_id"])
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")

    # 权限检查
    if memory["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权删除他人记忆")

    success = service.delete_memory(memory_id, user_id=user["user_id"])

    if not success:
        _audit(user, "delete", memory_id=memory_id, detail="失败", ip=_get_client_ip(request), status=0)
        raise HTTPException(status_code=500, detail="删除记忆失败")

    _audit(user, "delete", memory_id=memory_id,
           detail=f"type={memory.get('memory_type', '')}", ip=_get_client_ip(request))

    return {"ok": True, "deleted_id": memory_id}


@router.post("/search")
async def search_memories(req: SearchMemoryRequest, request: Request, user: dict = Depends(get_current_user)):
    """
    向量检索记忆

    使用语义相似度搜索相关记忆，支持按类型过滤
    """
    service = get_memory_service()

    if req.memory_type and req.memory_type not in MemoryService.MEMORY_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的记忆类型，可选: {MemoryService.MEMORY_TYPES}")

    results = service.search_memories(
        user_id=user["user_id"],
        query=req.query,
        top_k=req.top_k,
        memory_type=req.memory_type
    )

    _audit(user, "search", detail=f"query={req.query[:50]}, top_k={req.top_k}, results={len(results)}",
           ip=_get_client_ip(request))

    return {
        "query": req.query,
        "count": len(results),
        "results": [
            {
                "memory": MemoryItemResponse(**r["memory"]),
                "score": r["score"]
            }
            for r in results
        ]
    }


# ========== 图关联 ==========

@router.get("/{memory_id}/graph")
async def get_memory_graph(
    memory_id: int,
    max_hops: int = Query(2, ge=1, le=3),
    user: dict = Depends(get_current_user)
):
    """
    获取记忆的图关联
    
    返回与该记忆通过 FOLLOWS/SIMILAR_TO/CAUSES/BELONGS_TO 边相连的其他记忆
    """
    from backend.memory.graph_memory import get_graph_memory
    
    service = get_memory_service()
    memory = service.get_memory(memory_id, user_id=user["user_id"])
    
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    
    if memory["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权查看他人记忆")

    graph_memory = get_graph_memory()
    if not graph_memory or not graph_memory._available():
        return {"memory_id": memory_id, "related": [], "graph_available": False}

    related_ids = graph_memory.find_related(memory_id, max_hops=max_hops, user_id=user["user_id"])
    
    # 加载关联记忆详情
    related_memories = []
    for rid in related_ids[:20]:  # 限制返回数量
        related_memory = service.get_memory(rid, user_id=user["user_id"])
        if related_memory:
            # 已在 Neo4j 查询中过滤，这里只做二次确认
            related_memories.append(MemoryItemResponse(**related_memory))
    
    return {
        "memory_id": memory_id,
        "graph_available": True,
        "related_count": len(related_memories),  # 返回实际返回的数量
        "related": related_memories
    }


# ========== 版本历史 ==========

class MemoryVersionResponse(BaseModel):
    """记忆版本响应"""
    id: int
    memory_id: int
    version: int
    content: str
    importance_score: float
    memory_type: Optional[str] = None
    change_reason: str
    source_memory_id: Optional[int] = None
    created_at: Optional[datetime] = None


class VersionHistoryResponse(BaseModel):
    """版本历史响应"""
    memory_id: int
    current_content: str
    current_importance: float
    versions: List[MemoryVersionResponse]
    total_versions: int


@router.get("/{memory_id}/versions", response_model=VersionHistoryResponse)
async def get_memory_versions(
    memory_id: int,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """
    获取记忆的版本历史

    返回该记忆的所有历史版本，包括：
    - 合并/去重前的旧内容
    - 冲突解决的记录
    - 用户编辑的历史
    """
    service = get_memory_service()

    # 获取当前记忆
    memory = service.get_memory(memory_id, user_id=user["user_id"])
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")

    # 权限检查
    if memory["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权查看他人记忆版本")

    # 获取版本历史
    from backend.db.memory_mapper import get_memory_versions_mapper
    mapper = get_memory_versions_mapper()

    versions = mapper.get_memory_versions(memory_id, limit=limit)
    total_versions = mapper.get_version_count(memory_id)

    return VersionHistoryResponse(
        memory_id=memory_id,
        current_content=memory["content"],
        current_importance=memory["importance_score"],
        versions=[MemoryVersionResponse(**v) for v in versions],
        total_versions=total_versions
    )


@router.get("/{memory_id}/versions/{version}", response_model=MemoryVersionResponse)
async def get_memory_version(
    memory_id: int,
    version: int,
    user: dict = Depends(get_current_user)
):
    """获取记忆的特定版本"""
    service = get_memory_service()

    # 获取当前记忆（用于权限检查）
    memory = service.get_memory(memory_id, user_id=user["user_id"])
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")

    # 权限检查
    if memory["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权查看他人记忆版本")

    from backend.db.memory_mapper import get_memory_versions_mapper
    mapper = get_memory_versions_mapper()

    ver = mapper.get_memory_version(memory_id, version)
    if not ver:
        raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")

    return MemoryVersionResponse(**ver)


@router.post("/{memory_id}/restore/{version}", response_model=MemoryItemResponse)
async def restore_memory_version(
    memory_id: int,
    version: int,
    request: Request,
    user: dict = Depends(_require_edit)
):
    """
    恢复到指定版本

    流程：
    1. 保存当前内容为新版本（change_reason='restore'）
    2. 用目标版本的内容覆盖当前记忆
    3. 触发向量重新生成
    """
    service = get_memory_service()

    # 获取当前记忆
    memory = service.get_memory(memory_id, user_id=user["user_id"])
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")

    # 权限检查
    if memory["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权恢复他人记忆")

    from backend.db.memory_mapper import get_memory_versions_mapper
    mapper = get_memory_versions_mapper()

    # 获取目标版本
    target_version = mapper.get_memory_version(memory_id, version)
    if not target_version:
        raise HTTPException(status_code=404, detail=f"版本 {version} 不存在")

    # 保存当前内容为新版本
    current_version = memory.get("version", 1)
    mapper.insert_memory_version(
        memory_id=memory_id,
        version=current_version,
        content=memory["content"],
        importance_score=memory["importance_score"],
        memory_type=memory["memory_type"],
        change_reason="restore_backup"
    )

    # 恢复目标版本内容
    success = service.update_memory(
        memory_id=memory_id,
        content=target_version["content"],
        importance_score=target_version.get("importance_score", memory["importance_score"]),
        re_vectorize=True,
        user_id=user["user_id"]
    )

    if not success:
        _audit(user, "restore", memory_id=memory_id, detail=f"失败: version={version}", ip=_get_client_ip(request), status=0)
        raise HTTPException(status_code=500, detail="恢复失败")

    _audit(user, "restore", memory_id=memory_id,
           detail=f"version={version}", ip=_get_client_ip(request))

    updated_memory = service.get_memory(memory_id, user_id=user["user_id"])
    return MemoryItemResponse(**updated_memory)


# ========== 合并操作 ==========

@router.post("/consolidate")
async def trigger_consolidation(request: Request, user: dict = Depends(_require_edit)):
    """
    手动触发记忆合并

    执行三阶段合并：衰减 → 去重/合并 → 双条件淘汰
    """
    from backend.memory.agentforge_provider import AgentForgeMemoryProvider
    from backend.memory.consolidator import get_consolidator
    
    # 获取合并器
    consolidator = get_consolidator()

    # 获取用户的记忆（从 episodic + semantic 表查询）
    service = get_memory_service()
    episodic = service.get_episodic_memories(user["user_id"], limit=1000)
    semantic = service.get_semantic_memories(user["user_id"], limit=1000)
    # 标上层级：图谱 Memory 节点身份是 "{layer}:{id}"，两张表 id 会重号，
    # 不带层级就可能定位/删除到另一层的同号记忆
    for _m in episodic:
        _m["_layer"] = "episodic"
    for _m in semantic:
        _m["_layer"] = "semantic"
    memories = episodic + semantic

    if len(memories) < 2:
        return {"message": "记忆数量不足，无需合并", "result": None}
    
    # 批量计算 embedding（合并依赖向量相似度，不能用 TF 词袋降级）
    embeddings_map = {}  # {memory_id: embedding_vector}
    try:
        contents = [m["content"] for m in memories if m.get("content")]
        ids = [m["id"] for m in memories if m.get("content")]
        # 分批调用 embedding API（每批 200 条，避免超限）
        batch_size = 200
        for i in range(0, len(contents), batch_size):
            batch_contents = contents[i:i + batch_size]
            batch_ids = ids[i:i + batch_size]
            batch_embeddings = service._get_embeddings(batch_contents)
            if batch_embeddings:
                for mid, emb in zip(batch_ids, batch_embeddings):
                    embeddings_map[mid] = emb
        logger.info(f"Consolidate: loaded {len(embeddings_map)} embeddings for {len(memories)} memories")
    except Exception as e:
        logger.warning(f"Consolidate: embedding load failed, fallback to TF cosine: {e}")

    # 转换为 MemoryItem（含 embedding）
    from backend.memory.types import MemoryItem
    import time as _time
    items = [
        MemoryItem(
            id=m["id"],
            content=m["content"],
            importance=m["importance_score"],
            embedding=embeddings_map.get(m["id"]),
            created_at=m["created_at"].timestamp() if m.get("created_at") else _time.time(),
            last_accessed=m["last_accessed"].timestamp() if m.get("last_accessed") else _time.time(),
            category=m["memory_type"],
            user_id=m["user_id"],
            access_count=m.get("access_count", 0),
            is_user_pinned=bool(m.get("is_user_pinned", 0)),
            layer=m.get("_layer"),
        )
        for m in memories
    ]
    
    # 执行合并
    result = consolidator.consolidate(items)

    # 同步到数据库
    for mid in result.delete_from_db:
        service.delete_memory(mid, user_id=user["user_id"])

    for item in result.update_in_db:
        if item.id:
            service.update_memory(item.id, content=item.content, importance_score=item.importance, user_id=user["user_id"])

    # 持久化旧版本快照
    if result.versions_to_save:
        try:
            from backend.db.memory_mapper import get_memory_versions_mapper
            mapper = get_memory_versions_mapper()
            mapper.batch_insert_memory_versions(result.versions_to_save)
        except Exception as e:
            logger.warning(f"Save memory versions failed: {e}")

    _audit(user, "consolidate",
           detail=f"deduped={result.deduped}, merged={result.merged}, expired={result.expired}, remaining={result.remaining}",
           ip=_get_client_ip(request))

    return {
        "message": "记忆合并完成",
        "result": result.to_dict()
    }


# 注意：/episodic, /semantic, /episodic/stats, /semantic/stats, /dashboard
# 这些静态 GET 路由已移到 /{memory_id} 之前，避免被动态路由吞掉

@router.post("/episodic/{memory_id}/promote", response_model=SemanticMemoryResponse)
async def promote_episodic_to_semantic(
    memory_id: int,
    request: Request,
    req: PromoteMemoryRequest = None,
    user: dict = Depends(_require_edit)
):
    """
    将情景记忆晋升为语义记忆

    流程：
    1. 从情景记忆中删除（同时删除向量）
    2. 创建语义记忆（同时创建向量 + 图节点）
    3. 如果提供了新内容，使用新内容；否则使用原内容

    前端可以：
    - 直接晋升（使用原内容）
    - 编辑后晋升（用户修改内容再晋升）
    """
    service = get_memory_service()

    # 获取情景记忆
    episodic = service.get_episodic_memory(memory_id, user_id=user["user_id"])
    if not episodic:
        raise HTTPException(status_code=404, detail="情景记忆不存在")

    # 权限检查
    if episodic["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权晋升他人记忆")

    # 确定晋升内容和重要性
    content = req.content if (req and req.content) else episodic["content"]
    importance = req.importance if (req and req.importance is not None) else episodic["importance_score"]

    # 执行晋升
    semantic_id = service.promote_to_semantic(
        episodic_id=memory_id,
        user_id=user["user_id"],
        new_content=content,
        new_importance=importance
    )

    if not semantic_id:
        raise HTTPException(status_code=500, detail="晋升失败")

    # 返回新创建的语义记忆
    semantic = service.get_semantic_memory(semantic_id, user_id=user["user_id"])
    if not semantic:
        raise HTTPException(status_code=500, detail="晋升后查询失败")

    _audit(user, "promote", memory_id=memory_id, memory_layer="episodic",
           detail=f"semantic_id={semantic_id}, content={content[:50]}", ip=_get_client_ip(request))

    return SemanticMemoryResponse(**semantic)


# ========== Outbox 死信队列 ==========


class OutboxListParams(BaseModel):
    """死信队列查询参数"""
    status: str = "dead"
    target: Optional[str] = None
    event_type: Optional[str] = None
    limit: int = 50
    offset: int = 0


@router.get("/outbox/list")
async def list_outbox_events(
    status: str = Query("dead", description="筛选状态: pending/processing/processed/dead"),
    target: Optional[str] = Query(None, description="目标库: milvus/neo4j/redis"),
    event_type: Optional[str] = Query(None, description="事件类型"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """查询 Outbox 事件列表（默认查死信）

    返回详细信息：事件类型、目标库、重试次数、最后错误、payload 等。
    需要 memory.view 权限（可在角色编辑里勾选）。
    """
    if not _has_perm(user, "memory.view"):
        raise HTTPException(status_code=403, detail="无权查看 Outbox")

    from backend.db.schema import get_conn
    import json

    conn = get_conn()
    try:
        # 构造查询条件
        conditions = ["status = %s"]
        params = [status]

        if target:
            conditions.append("target = %s")
            params.append(target)
        if event_type:
            conditions.append("event_type = %s")
            params.append(event_type)

        where_clause = " AND ".join(conditions)

        # 查总数
        cur = conn.execute(
            f"SELECT COUNT(*) as total FROM memory_outbox WHERE {where_clause}",
            params
        )
        total = cur.fetchone()["total"]

        # 查详情（按创建时间倒序，最新的在前面）
        cur = conn.execute(
            f"""SELECT id, event_id, memory_id, memory_version, event_type, target,
                       payload, status, attempts, last_error, memory_layer,
                       available_at, locked_at, locked_by, processed_at, created_at
                FROM memory_outbox
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s""",
            params + [limit, offset]
        )
        rows = cur.fetchall()

        events = []
        for row in rows:
            event = dict(row)
            # payload 可能是 JSON 字符串，尝试解析
            if isinstance(event.get("payload"), str):
                try:
                    event["payload"] = json.loads(event["payload"])
                except (json.JSONDecodeError, TypeError):
                    pass
            # datetime 转字符串
            for k in ("available_at", "locked_at", "processed_at", "created_at"):
                if event.get(k) and hasattr(event[k], "isoformat"):
                    event[k] = event[k].isoformat()
            events.append(event)

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "events": events,
        }
    except Exception as e:
        logger.warning(f"Failed to list outbox events: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")
    finally:
        conn.close()


@router.post("/outbox/retry")
async def retry_outbox_events(
    request: Request,
    event_ids: Optional[List[int]] = None,
    retry_all: bool = False,
    user: dict = Depends(get_current_user),
):
    """重试死信事件

    - 指定 event_ids: 重试特定事件
    - retry_all=true: 重试所有 dead 事件

    重试时将 status 重置为 pending，attempts 清零，让 Worker 重新处理。
    需要 memory.edit 权限（可在角色编辑里勾选）。
    """
    if not _has_perm(user, "memory.edit"):
        raise HTTPException(status_code=403, detail="无权重试 Outbox 事件")

    from backend.db.schema import get_conn

    if not event_ids and not retry_all:
        raise HTTPException(status_code=400, detail="请指定 event_ids 或设置 retry_all=true")

    conn = get_conn()
    try:
        conn._conn.autocommit = False

        if retry_all:
            # 重试所有死信
            cur = conn.execute(
                """UPDATE memory_outbox
                   SET status = 'pending',
                       attempts = 0,
                       last_error = NULL,
                       available_at = NOW(),
                       locked_at = NULL,
                       locked_by = NULL
                   WHERE status = 'dead'"""
            )
            count = cur.rowcount
        else:
            # 重试指定事件（只重试 dead 状态的）
            placeholders = ",".join(["%s"] * len(event_ids))
            cur = conn.execute(
                f"""UPDATE memory_outbox
                   SET status = 'pending',
                       attempts = 0,
                       last_error = NULL,
                       available_at = NOW(),
                       locked_at = NULL,
                       locked_by = NULL
                   WHERE id IN ({placeholders}) AND status = 'dead'""",
                event_ids
            )
            count = cur.rowcount

        conn.commit()

        _audit(user, "outbox_retry", detail=f"retried {count} dead events",
               ip=_get_client_ip(request))

        logger.info(f"Outbox retry: {count} events reset to pending by user {user.get('username')}")
        return {"ok": True, "retried": count}
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to retry outbox events: {e}")
        raise HTTPException(status_code=500, detail=f"重试失败: {e}")
    finally:
        conn._conn.autocommit = True
        conn.close()
