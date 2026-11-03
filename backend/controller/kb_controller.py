"""
知识库 API — 文档上传 / 列表 / 详情 / chunk 浏览 / 重新解析 / 删除 / 下载

权限模型：
- 统一权限：kb.manage（查看/创建/编辑/删除知识库和文档）
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.service.kb import kb_service
from backend.service.auth.auth_middleware import get_current_user
from backend.service.kb.kb_service import KbError, KbInvalidFile, KbNotFound
from backend.utils.log_utils import log

logger = log

router = APIRouter(prefix="/api/kb", tags=["knowledge"])


# ── 权限依赖 ──

async def require_kb_access(user: dict = Depends(get_current_user)) -> dict:
    """kb.manage 权限（统一知识库管理权限）。"""
    perms = user.get("permissions", set())
    if "kb.manage" not in perms:
        raise HTTPException(status_code=403, detail="缺少权限: kb.manage（管理知识库）")
    return user


# require_kb_create / require_kb_admin 已合并到 require_kb_access（统一使用 kb.manage 权限）
require_kb_create = require_kb_access
require_kb_admin = require_kb_access


def _handle_kb_error(e: Exception) -> HTTPException:
    if isinstance(e, KbNotFound):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, KbInvalidFile):
        return HTTPException(status_code=400, detail=str(e))
    return HTTPException(status_code=500, detail=f"服务内部错误: {e}")


# ── Endpoints ──

@router.post("/documents")
async def upload_documents(
    files: List[UploadFile] = File(...),
    chunk_size: Optional[str] = Form(default=None),
    chunk_overlap: Optional[str] = Form(default=None),
    chunk_strategy: Optional[str] = Form(default="fixed"),
    parser: Optional[str] = Form(default=""),
    kb_id: Optional[int] = Form(default=None),
    user: dict = Depends(require_kb_create),
):
    """上传文档（multipart，可多文件）。解析 + 切分同步完成后返回摘要。"""
    if not files:
        raise HTTPException(status_code=400, detail="请选择至少一个文件")

    user_id = user["user_id"]
    results = []
    for f in files:
        try:
            content = await f.read()
            doc = await kb_service.create_document(
                user_id=user_id,
                filename=f.filename or "unnamed",
                content=content,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                parser_pref=parser or "",
                chunk_strategy=(chunk_strategy or "fixed").strip(),
                kb_id=kb_id,
            )
            results.append(doc)
        except KbError as e:
            raise _handle_kb_error(e)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[KB] 上传失败 {f.filename}: {e}")
            raise HTTPException(status_code=500, detail=f"上传失败 {f.filename}: {e}")

    logger.info(f"[KB] 上传完成 user={user_id} count={len(results)}")
    return {"ok": True, "count": len(results), "documents": results}


@router.get("/documents")
async def list_documents(
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
    kb_id: Optional[int] = None,
    user: dict = Depends(require_kb_access),
):
    """文档列表（分页 + 关键词过滤）。kb.manage 可看全部。"""
    try:
        return kb_service.list_documents(
            user_id=user["user_id"],
            permissions=user.get("permissions", set()),
            keyword=keyword,
            page=page,
            page_size=page_size,
            kb_id=kb_id,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"[KB] 列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int, user: dict = Depends(require_kb_access)):
    """文档详情。"""
    try:
        return kb_service.get_document(user["user_id"], doc_id, user.get("permissions", set()))
    except KbError as e:
        raise _handle_kb_error(e)


@router.get("/documents/{doc_id}/chunks")
async def list_chunks(
    doc_id: int,
    page: int = 1,
    page_size: int = 50,
    kind: str = "all",
    user: dict = Depends(require_kb_access),
):
    """chunk 分页列表（按 chunk_index 升序；kind: all/base/topic）。"""
    try:
        return kb_service.list_chunks(
            user["user_id"], doc_id, user.get("permissions", set()),
            page=page, page_size=page_size, kind=kind,
        )
    except KbError as e:
        raise _handle_kb_error(e)


@router.get("/documents/{doc_id}/text")
async def get_document_text(doc_id: int, user: dict = Depends(require_kb_access)):
    """文档解析出的完整原文（「查看原文内容」）。"""
    try:
        return kb_service.get_document_text(
            user["user_id"], doc_id, user.get("permissions", set())
        )
    except KbError as e:
        raise _handle_kb_error(e)


@router.post("/documents/{doc_id}/reprocess")
async def reprocess_document(
    doc_id: int,
    parser: str = Form(default=""),
    chunk_size: Optional[str] = Form(default=None),
    chunk_overlap: Optional[str] = Form(default=None),
    chunk_strategy: Optional[str] = Form(default=None),
    user: dict = Depends(require_kb_access),
):
    """重新解析/切分（可切换解析器/切分参数/主题策略）。"""
    try:
        return await kb_service.reprocess_document(
            user["user_id"], doc_id, user.get("permissions", set()),
            parser_pref=parser or "",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            chunk_strategy=(chunk_strategy or "").strip() or None,
        )
    except KbError as e:
        raise _handle_kb_error(e)
    except Exception as e:  # noqa: BLE001
        logger.error(f"[KB] 重新解析失败 doc_id={doc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, user: dict = Depends(require_kb_access)):
    """删除文档（文件 + chunks + 记录）。"""
    try:
        return kb_service.delete_document(
            user["user_id"], doc_id, user.get("permissions", set())
        )
    except KbError as e:
        raise _handle_kb_error(e)


class MoveDocRequest(BaseModel):
    kb_id: int = Field(description="目标知识库 ID")


@router.post("/documents/{doc_id}/move")
async def move_document(
    doc_id: int,
    req: MoveDocRequest,
    user: dict = Depends(require_kb_access),
):
    """把文档移动到其他知识库（级联更新 chunks 的 kb_id）。"""
    try:
        # 校验文档归属
        kb_service.get_document(user["user_id"], doc_id, user.get("permissions", set()))
        # 校验目标知识库存在且归属当前用户
        kb = kb_service_instance.get_knowledge_base(req.kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="目标知识库不存在")
        # IDOR 防护：目标知识库必须属于当前用户（管理员跳过）
        perms = user.get("permissions", set())
        if "kb.manage" not in perms and int(kb.get("user_id", -1)) != int(user["user_id"]):
            raise HTTPException(status_code=403, detail="无权操作目标知识库")
        # 执行移动
        ok = kb_service.move_document_kb(doc_id, req.kb_id)
        if not ok:
            raise HTTPException(status_code=500, detail="移动失败")
        return {"ok": True, "doc_id": doc_id, "kb_id": req.kb_id}
    except KbError as e:
        raise _handle_kb_error(e)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error(f"[KB] 移动文档失败 doc_id={doc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: int, user: dict = Depends(require_kb_access)):
    """下载原始文件。"""
    try:
        path, original_name = kb_service.resolve_download(
            user["user_id"], doc_id, user.get("permissions", set())
        )
    except KbNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

    return FileResponse(
        path,
        filename=original_name,
        media_type="application/octet-stream",
    )


# ── 知识库管理 API ──

from backend.service.kb.knowledge_base_service import KnowledgeBaseService

kb_service_instance = KnowledgeBaseService()


class KnowledgeBaseCreateRequest(BaseModel):
    kb_name: str
    kb_type: str = "general"
    description: str = ""


class KnowledgeBaseUpdateRequest(BaseModel):
    kb_name: Optional[str] = None
    kb_type: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[int] = None


@router.post("/knowledge-bases")
async def create_knowledge_base(
    req: KnowledgeBaseCreateRequest,
    user: dict = Depends(require_kb_admin),
):
    """创建知识库"""
    try:
        kb = kb_service_instance.create_knowledge_base(
            kb_name=req.kb_name,
            kb_type=req.kb_type,
            description=req.description,
            user_id=user["user_id"]
        )
        return {"ok": True, "knowledge_base": kb}
    except Exception as e:
        logger.error(f"[KB] 创建知识库失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge-bases")
async def list_knowledge_bases(
    kb_type: Optional[str] = None,
    user: dict = Depends(require_kb_access),
):
    """获取知识库列表（知识库全局可见，不按创建者过滤——对齐 Eyes）。
    返回列表附带每个 KB 的 doc_count / chunk_count 统计。
    """
    try:
        kbs = kb_service_instance.list_knowledge_bases(
            kb_type=kb_type
        )
        # 附加文档/分片统计（单次聚合查询）
        if kbs:
            from backend.db.schema import get_conn
            conn = get_conn()
            try:
                cur = conn.execute(
                    "SELECT kb_id, COUNT(*) AS doc_count, "
                    "COALESCE(SUM(chunk_count), 0) AS chunk_count "
                    "FROM kb_documents GROUP BY kb_id"
                )
                rows = cur.fetchall() if hasattr(cur, "fetchall") else []
                stats = {r["kb_id"]: {"doc_count": r["doc_count"], "chunk_count": r["chunk_count"]} for r in rows}

                # 附加层级信息
                from backend.service.auth.data_layer_service import get_kb_layers, list_layers as _list_layers
                all_layers = _list_layers()
                layer_name_map = {l["id"]: l["name"] for l in all_layers}
            finally:
                conn.close()
            for kb in kbs:
                s = stats.get(kb["id"], {"doc_count": 0, "chunk_count": 0})
                kb["doc_count"] = s["doc_count"]
                kb["chunk_count"] = s["chunk_count"]
                layer_ids = get_kb_layers(kb["id"])
                kb["layer_ids"] = layer_ids
                kb["layer_names"] = [layer_name_map.get(lid, f"层级{lid}") for lid in layer_ids]
        return {"ok": True, "knowledge_bases": kbs}
    except Exception as e:
        logger.error(f"[KB] 获取知识库列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge-bases/{kb_id}")
async def get_knowledge_base(kb_id: int, user: dict = Depends(require_kb_access)):
    """获取知识库详情"""
    try:
        kb = kb_service_instance.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        # 附加层级信息
        from backend.service.auth.data_layer_service import get_kb_layers, list_layers as _list_layers
        layer_ids = get_kb_layers(kb_id)
        kb["layer_ids"] = layer_ids
        all_layers = _list_layers()
        layer_name_map = {l["id"]: l["name"] for l in all_layers}
        kb["layer_names"] = [layer_name_map.get(lid, f"层级{lid}") for lid in layer_ids]
        return {"ok": True, "knowledge_base": kb}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[KB] 获取知识库详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/knowledge-bases/{kb_id}")
async def update_knowledge_base(
    kb_id: int,
    req: KnowledgeBaseUpdateRequest,
    user: dict = Depends(require_kb_admin),
):
    """更新知识库（名称/类型/描述/禁用状态）"""
    try:
        kb = kb_service_instance.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        if kb["user_id"] != user["user_id"] and "kb.manage" not in user.get("permissions", set()):
            raise HTTPException(status_code=403, detail="无权修改此知识库")

        success = kb_service_instance.update_knowledge_base(
            kb_id=kb_id,
            kb_name=req.kb_name,
            kb_type=req.kb_type,
            description=req.description,
            is_enabled=req.is_enabled
        )
        return {"ok": success}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[KB] 更新知识库失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(kb_id: int, user: dict = Depends(require_kb_admin)):
    """删除知识库（级联删除文档和分片）"""
    try:
        kb = kb_service_instance.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        if kb["user_id"] != user["user_id"] and "kb.manage" not in user.get("permissions", set()):
            raise HTTPException(status_code=403, detail="无权删除此知识库")
        
        # 检查是否为系统内置知识库
        if kb.get("is_system"):
            raise HTTPException(status_code=400, detail=f"系统内置知识库不可删除: {kb.get('kb_name', '')}")

        success = kb_service_instance.delete_knowledge_base(kb_id)
        return {"ok": success}
    except HTTPException:
        raise
    except ValueError as e:
        # 捕获 mapper 抛出的系统内置知识库保护异常
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[KB] 删除知识库失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
# 检索质量监控
# ════════════════════════════════════════════════════════════


@router.get("/retrieval-stats")
async def get_retrieval_stats(
    days: int = Query(default=7, ge=1, le=90, description="统计天数"),
    user: dict = Depends(get_current_user),
):
    """
    检索质量统计 — 空检索率、命中率、延迟分布、每日趋势。

    基于 kb_retrieval_logs 表聚合，用于发现检索质量劣化。
    """
    from backend.service.kb.kb_retrieval_stats import get_retrieval_stats
    return get_retrieval_stats(user["user_id"], days=days)
