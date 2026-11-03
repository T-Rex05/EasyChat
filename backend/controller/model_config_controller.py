"""模型配置 API — LLM 模型的多配置保存与切换

提供 /api/model-configs 下的端点：
- GET   /api/model-configs          列表（api_key 脱敏）
- POST  /api/model-configs          新增配置（加密 api_key，并设为当前激活）
- PUT   /api/model-configs/{id}/active  设为当前激活
- DELETE /api/model-configs/{id}    删除配置

鉴权：POST/PUT/DELETE 需要 system.config 权限（可在角色编辑里勾选）；GET 需登录。
"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from backend.service.auth.auth_middleware import get_current_user
from backend.service.auth.permission_service import has_permission
from backend.utils.crypto_utils import encrypt, decrypt
from backend.utils.log_utils import log
from backend.utils.multimodal_detect import is_multimodal_model, probe_image_support
from backend.service.model_router import invalidate_model_config_cache
import os
import json

logger = log
router = APIRouter(prefix="/api/model-configs", tags=["model-configs"])

# 模型配置分类（每类各自维护 is_current=1 的激活项）
MODEL_CATEGORIES = {
    "chat": "聊天模型",       # 对话 / RAG 裁判
    "embedding": "Embedding 模型",  # 知识库向量化 / 检索
    "rerank": "Rerank 模型",  # RAG 检索精排
}


def _normalize_category(category: str) -> str:
    cat = (category or "chat").strip().lower()
    return cat if cat in MODEL_CATEGORIES else "chat"


class ModelConfigCreate(BaseModel):
    config_name: str = Field(default="", description="配置名称")
    config_type: str = Field(default="URL", description="URL / OLLAMA / LOCAL")
    api_url: str = Field(default="", description="OpenAI 兼容 Base URL")
    api_key: str = Field(default="", description="API Key（列表返回时脱敏）")
    model_name: str = Field(default="", description="模型名，如 gpt-4")
    provider: str = Field(default="", description="Hermes provider ID，留空则自动检测")
    reasoning_effort: str = Field(default="", description="推理深度: low/medium/high/max/ultra")
    category: str = Field(default="chat", description="配置分类: chat（聊天模型）/ embedding（Embedding 模型）")
    is_multimodal: int = Field(default=0, description="多模态标记；embedding 分类下表示使用多模态端点（doubao-embedding-vision 等）")
    dimension: int = Field(default=0, ge=0, le=8192, description="Embedding 向量维度（0=使用模型默认值；切换维度需重新向量化）")
    send_dimensions: int = Field(default=0, description="是否在 API 请求中发送 dimensions 参数（部分模型支持）")
    cost_per_1k_input: float = Field(default=0, description="每1000输入token成本(USD)")
    cost_per_1k_output: float = Field(default=0, description="每1000输出token成本(USD)")
    context_length: int = Field(default=0, description="模型上下文窗口大小")
    capabilities: Optional[dict] = Field(default=None, description="模型能力标签 {code:true, vision:true, json_mode:true}")
    description: str = Field(default="", description="模型描述/备注")


def _get_conn():
    """获取 MySQL 连接（走统一连接池）。"""
    from backend.db.connection_pool import get_pool_connection
    return get_pool_connection()


@router.get("")
async def list_model_configs(user: dict = Depends(get_current_user)):
    """获取模型配置列表（以激活项优先，api_key 脱敏，含 category 分类）。"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, config_name, config_type, api_url, api_key, "
            "model_name, provider, category, is_multimodal, reasoning_effort, "
            "dimension, send_dimensions, is_current, enabled, "
            "priority, cost_per_1k_input, cost_per_1k_output, context_length, "
            "capabilities, description, "
            "created_at, updated_at "
            "FROM model_configs ORDER BY category ASC, is_current DESC, updated_at DESC"
        )
        rows = cur.fetchall()
        for r in rows:
            if r.get("api_key"):
                r["api_key"] = "***已配置***"
        # 附上当前是否有 env 兜底配置的信息（供 UI 显示）+ 分类元信息
        env_configured = bool(os.getenv("LLM_BASE_URL") and os.getenv("LLM_API_KEY"))
        return {
            "configs": rows,
            "env_configured": env_configured,
            "categories": MODEL_CATEGORIES,
        }
    finally:
        conn.close()


@router.post("")
async def create_model_config(req: ModelConfigCreate, user: dict = Depends(get_current_user)):
    """新增模型配置，并设为当前分类激活。需要 system.config 权限。"""
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="缺少权限: system.config")

    name = (req.config_name or "").strip()
    url = (req.api_url or "").strip()
    model = (req.model_name or "").strip()
    category = _normalize_category(req.category)
    if not name:
        name = model or url or "未命名配置"
    if not url or not model:
        raise HTTPException(status_code=400, detail="Base URL 与模型名称不能为空")

    conn = _get_conn()
    try:
        cur = conn.cursor()
        encrypted_key = encrypt(req.api_key) if req.api_key else ""
        # 多模态标记：embedding 分类由用户手动指定（多模态 Embedding 走 /embeddings/multimodal）；
        # chat 分类自动检测模型名
        if category == "chat":
            multimodal = 1 if is_multimodal_model(model) else 0
        else:
            multimodal = 1 if req.is_multimodal else 0
        # 同类配置仅一个激活：先把该分类下所有 is_current 置 0
        cur.execute("UPDATE model_configs SET is_current = 0 WHERE category = %s", (category,))
        cur.execute(
            "INSERT INTO model_configs "
            "(user_id, config_name, config_type, api_url, api_key, model_name, provider, category, "
            "is_multimodal, reasoning_effort, dimension, send_dimensions, "
            "cost_per_1k_input, cost_per_1k_output, context_length, capabilities, description, "
            "is_current, enabled) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 1)",
            (int(user.get("user_id") or 1), name, (req.config_type or "URL").upper(),
             url, encrypted_key, model, (req.provider or "").strip().lower(), category,
             multimodal, (req.reasoning_effort or "").strip(),
             int(req.dimension or 0), int(req.send_dimensions or 0),
             float(req.cost_per_1k_input or 0), float(req.cost_per_1k_output or 0),
             int(req.context_length or 0),
             json.dumps(req.capabilities, ensure_ascii=False) if req.capabilities else None,
             (req.description or "").strip()),
        )
        new_id = cur.lastrowid
        conn.commit()
        # 缓存失效：新配置写入，失效该分类的列表缓存
        invalidate_model_config_cache(category=category)
        return {"ok": True, "id": new_id, "config": {"id": new_id, "config_name": name, "model_name": model, "category": category, "is_multimodal": bool(multimodal)}}
    except Exception as e:
        logger.error(f"新增模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"新增模型配置失败: {e}")
    finally:
        conn.close()


@router.put("/{config_id}/active")
async def set_active(config_id: int, user: dict = Depends(get_current_user)):
    """将指定配置设为当前激活（同类配置唯一）。"""
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="缺少权限: system.config")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, category, model_name, is_multimodal FROM model_configs WHERE id = %s AND enabled = 1", (config_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模型配置不存在或已禁用")
        category = _normalize_category(row.get("category"))
        
        # 重新检测多模态（如果静态规则更新后可能变化）
        model_name = row.get("model_name", "")
        detected_multimodal = 1 if is_multimodal_model(model_name) else 0
        if detected_multimodal != row.get("is_multimodal", 0):
            cur.execute("UPDATE model_configs SET is_multimodal = %s WHERE id = %s", (detected_multimodal, config_id))
            logger.info(f"多模态标记已更新: {model_name} -> {detected_multimodal}")
        
        # 同类仅一个激活
        cur.execute("UPDATE model_configs SET is_current = 0 WHERE category = %s", (category,))
        cur.execute("UPDATE model_configs SET is_current = 1, updated_at = NOW() WHERE id = %s", (config_id,))
        conn.commit()
        # 缓存失效：is_current 变更，失效该分类的列表缓存
        invalidate_model_config_cache(category=category)
        return {"ok": True, "id": config_id, "category": category, "is_multimodal": bool(detected_multimodal)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置激活模型配置失败: {e}")
        raise HTTPException(status_code=500, detail="设置激活失败")
    finally:
        conn.close()


@router.delete("/{config_id}")
async def delete_config(config_id: int, user: dict = Depends(get_current_user)):
    """删除配置（激活项被删除后需重新选择）。"""
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="缺少权限: system.config")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        # 先查 category 用于精确失效缓存
        cur.execute("SELECT category FROM model_configs WHERE id = %s", (config_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模型配置不存在")
        category = _normalize_category(row.get("category"))
        cur.execute("DELETE FROM model_configs WHERE id = %s", (config_id,))
        conn.commit()
        # 缓存失效：失效该配置 ID + 该分类列表缓存
        invalidate_model_config_cache(config_id=config_id, category=category)
        return {"ok": True, "deleted": config_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除模型配置失败: {e}")
        raise HTTPException(status_code=500, detail="删除失败")
    finally:
        conn.close()


@router.put("/{config_id}/multimodal")
async def toggle_multimodal(config_id: int, user: dict = Depends(get_current_user)):
    """手动切换多模态标记（供管理员覆盖自动检测结果）。"""
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="缺少权限: system.config")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, is_multimodal FROM model_configs WHERE id = %s", (config_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模型配置不存在")
        new_val = 0 if row["is_multimodal"] else 1
        cur.execute("UPDATE model_configs SET is_multimodal = %s, updated_at = NOW() WHERE id = %s", (new_val, config_id))
        conn.commit()
        # 缓存失效：配置属性变更
        invalidate_model_config_cache(config_id=config_id)
        return {"ok": True, "id": config_id, "is_multimodal": bool(new_val)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换多模态标记失败: {e}")
        raise HTTPException(status_code=500, detail="切换失败")
    finally:
        conn.close()


@router.post("/redetect-multimodal")
async def redetect_all_multimodal(user: dict = Depends(get_current_user)):
    """重新检测所有 chat 分类配置的多模态标记（静态规则更新后调用）。"""
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="缺少权限: system.config")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, model_name, is_multimodal FROM model_configs WHERE category = 'chat' AND enabled = 1")
        rows = cur.fetchall()
        updated = []
        for r in rows:
            detected = 1 if is_multimodal_model(r.get("model_name", "")) else 0
            if detected != r.get("is_multimodal", 0):
                cur.execute("UPDATE model_configs SET is_multimodal = %s WHERE id = %s", (detected, r["id"]))
                updated.append({"id": r["id"], "model_name": r["model_name"], "old": r.get("is_multimodal", 0), "new": detected})
        conn.commit()
        # 缓存失效：批量更新 chat 分类的多模态标记
        invalidate_model_config_cache(category="chat")
        return {"ok": True, "updated_count": len(updated), "updated": updated}
    except Exception as e:
        logger.error(f"重新检测多模态失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新检测失败: {e}")
    finally:
        conn.close()


REASONING_EFFORTS = ["", "low", "medium", "high", "max", "ultra"]


@router.put("/reasoning-effort")
async def update_reasoning_effort(
    effort: str = "",
    user: dict = Depends(get_current_user),
):
    """更新当前激活配置的推理深度。"""
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="缺少权限: system.config")
    effort = (effort or "").strip().lower()
    if effort and effort not in REASONING_EFFORTS:
        raise HTTPException(status_code=400, detail=f"无效值，可选: {', '.join(REASONING_EFFORTS[1:])} 或空")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE model_configs SET reasoning_effort = %s, updated_at = NOW() "
            "WHERE is_current = 1 AND category = 'chat'"
        )
        conn.commit()
        # 缓存失效：chat 分类的推理深度变更
        invalidate_model_config_cache(category="chat")
        return {"ok": True, "reasoning_effort": effort}
    except Exception as e:
        logger.error(f"更新推理深度失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.put("/{config_id}")
async def update_config(config_id: int, req: ModelConfigCreate, user: dict = Depends(get_current_user)):
    """编辑已有模型配置。api_key 留空则保持原有密钥不变。"""
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="缺少权限: system.config")
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, category, is_current FROM model_configs WHERE id = %s", (config_id,))
        existing = cur.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="模型配置不存在")

        name = (req.config_name or "").strip()
        url = (req.api_url or "").strip()
        model = (req.model_name or "").strip()
        if not name:
            name = model or url or "未命名配置"
        if not url or not model:
            raise HTTPException(status_code=400, detail="Base URL 与模型名称不能为空")

        new_category = _normalize_category(req.category)
        old_category = _normalize_category(existing.get("category"))
        was_current = bool(existing.get("is_current"))

        _provider = (req.provider or "").strip().lower()
        _effort = (req.reasoning_effort or "").strip()
        # 多模态标记：embedding 分类由用户手动指定，chat 分类自动检测
        if new_category == "chat":
            _multimodal = 1 if is_multimodal_model(model) else 0
        else:
            _multimodal = 1 if req.is_multimodal else 0

        _capabilities_json = json.dumps(req.capabilities, ensure_ascii=False) if req.capabilities else None
        if req.api_key and req.api_key.strip():
            encrypted_key = encrypt(req.api_key.strip())
            cur.execute(
                "UPDATE model_configs SET config_name=%s, config_type=%s, api_url=%s, "
                "api_key=%s, model_name=%s, provider=%s, category=%s, is_multimodal=%s, reasoning_effort=%s, "
                "dimension=%s, send_dimensions=%s, "
                "cost_per_1k_input=%s, cost_per_1k_output=%s, context_length=%s, "
                "capabilities=%s, description=%s, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                (name, (req.config_type or "URL").upper(), url, encrypted_key, model, _provider,
                 new_category, _multimodal, _effort,
                 int(req.dimension or 0), int(req.send_dimensions or 0),
                 float(req.cost_per_1k_input or 0), float(req.cost_per_1k_output or 0),
                 int(req.context_length or 0), _capabilities_json,
                 (req.description or "").strip(), config_id),
            )
        else:
            cur.execute(
                "UPDATE model_configs SET config_name=%s, config_type=%s, api_url=%s, "
                "model_name=%s, provider=%s, category=%s, is_multimodal=%s, reasoning_effort=%s, "
                "dimension=%s, send_dimensions=%s, "
                "cost_per_1k_input=%s, cost_per_1k_output=%s, context_length=%s, "
                "capabilities=%s, description=%s, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                (name, (req.config_type or "URL").upper(), url, model, _provider,
                 new_category, _multimodal, _effort,
                 int(req.dimension or 0), int(req.send_dimensions or 0),
                 float(req.cost_per_1k_input or 0), float(req.cost_per_1k_output or 0),
                 int(req.context_length or 0), _capabilities_json,
                 (req.description or "").strip(), config_id),
            )

        # 分类变更后的激活一致性：目标分类只保留一个激活
        if new_category != old_category:
            cur.execute("UPDATE model_configs SET is_current = 0 WHERE category = %s AND id != %s", (new_category, config_id))
            cur.execute(
                "UPDATE model_configs SET is_current = %s WHERE id = %s",
                (1 if was_current else 0, config_id),
            )
        conn.commit()
        # 缓存失效：失效该配置 + 新旧分类列表缓存
        invalidate_model_config_cache(config_id=config_id, category=new_category)
        if new_category != old_category:
            invalidate_model_config_cache(category=old_category)
        return {"ok": True, "id": config_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新失败: {e}")
    finally:
        conn.close()


@router.post("/{config_id}/test")
async def test_connection(config_id: int, user: dict = Depends(get_current_user)):
    """测试模型配置连接性。

    - chat 分类：GET /v1/models 探测（OpenAI/DashScope 兼容模式）
    - embedding 分类：POST /embeddings 最小请求（火山方舟 Ark 等不实现 GET /models，
      用真实 embedding 调用路径验证 Key 与 Base URL）
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, api_url, api_key, model_name, category FROM model_configs WHERE id = %s AND enabled = 1",
            (config_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="模型配置不存在或已禁用")
    finally:
        conn.close()

    import time, urllib.request, json as _json
    api_url = (row.get("api_url") or "").strip()
    encrypted_key = row.get("api_key") or ""
    api_key = ""
    if encrypted_key:
        try:
            api_key = decrypt(encrypted_key)
        except Exception:
            api_key = encrypted_key  # 明文兼容
    api_key = (api_key or "").strip()  # 容错：去除首尾空格/换行（粘贴时常见）

    if not api_url:
        raise HTTPException(status_code=400, detail="未配置 Base URL，无法测试")

    base = api_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    import ssl
    ctx = ssl.create_default_context() if hasattr(ssl, "create_default_context") else None

    start = time.time()
    last_error_detail = ""

    # ── Embedding 分类：POST /embeddings（及多模态端点）真实调用路径探测 ──
    if _normalize_category(row.get("category")) == "embedding":
        return _test_embedding_endpoint(
            base, api_key, row.get("model_name") or "",
            headers, ctx, start,
            multimodal=bool(row.get("is_multimodal")),
        )

    tried_urls: list = []

    # 自动检测多模态（名称匹配 + 图片探测）
    model_name_for_detect = (row.get("model_name") or "").strip()
    detected_multimodal = is_multimodal_model(model_name_for_detect)
    stored_multimodal = bool(row.get("is_multimodal", 0))

    # Layer 3 — 图片探测预检（优先于静态规则）
    probe_ok = None
    probe_msg = ""
    try:
        probe_ok, probe_msg = probe_image_support(api_url, api_key, model_name_for_detect, timeout=15)
    except Exception:
        pass

    # 判定逻辑：存储标记 > 图片探测确认 > 静态规则
    # 图片探测只做正向确认：探测通过 → 多模态；其他情况不覆盖静态规则
    if stored_multimodal:
        multimodal = True
    elif probe_ok is True:
        multimodal = True
    else:
        multimodal = detected_multimodal

    # 探测确认多模态但数据库未标记时，回写数据库
    if probe_ok is True and not stored_multimodal and row.get("category") == "chat":
        try:
            upd_conn = _get_conn()
            try:
                upd_conn.cursor().execute(
                    "UPDATE model_configs SET is_multimodal = 1 WHERE id = %s",
                    (config_id,),
                )
                upd_conn.commit()
            finally:
                upd_conn.close()
        except Exception as e:
            logger.warning(f"回写多模态标记失败: {e}")

    # ── 判断是否为 Anthropic 兼容端点（只支持 POST /messages，GET 一律 404） ──
    is_anthropic = "/anthropic" in base or base.endswith("/messages")

    if is_anthropic:
        # Anthropic 端点：发一个最小的 POST 测试连通性
        # DeepSeek Anthropic 兼容端点用 x-api-key（Bearer 兼容两种都带上）
        # Anthropic Messages API 路径为 /v1/messages，需补齐
        base_clean = base.rstrip("/")
        if base_clean.endswith("/v1/messages") or base_clean.endswith("/v1"):
            test_url = base_clean
        elif base_clean.endswith("/messages"):
            test_url = base_clean
        else:
            test_url = f"{base_clean}/v1/messages"
        tried_urls.append(test_url)
        body = _json.dumps({"model": (row.get("model_name") or "").strip(),
                            "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}).encode()
        headers["anthropic-version"] = "2023-06-01"
        if api_key and "x-api-key" not in headers:
            headers["x-api-key"] = api_key
        try:
            req_obj = urllib.request.Request(test_url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req_obj, context=ctx, timeout=15) as resp:
                elapsed_ms = round((time.time() - start) * 1000)
                return {
                    "ok": True, "status_code": resp.status, "latency_ms": elapsed_ms,
                    "tested_url": test_url, "models": [], "is_multimodal": multimodal,
                    "probe_multimodal": probe_ok, "probe_message": probe_msg,
                    "message": f"Anthropic 端点可达（HTTP {resp.status}），耗时 {elapsed_ms}ms",
                }
        except urllib.error.HTTPError as e:
            elapsed_ms = round((time.time() - start) * 1000)
            if e.code in (401, 403):
                return {
                    "ok": False, "latency_ms": elapsed_ms, "tested_url": test_url,
                    "is_multimodal": multimodal,
                    "probe_multimodal": probe_ok, "probe_message": probe_msg,
                    "message": f"服务器可达（HTTP {e.code}），但 API Key 被拒绝。请检查 Key 是否正确",
                }
            if 200 <= e.code < 300:
                return {
                    "ok": True, "status_code": e.code, "latency_ms": elapsed_ms,
                    "tested_url": test_url, "models": [], "is_multimodal": multimodal,
                    "probe_multimodal": probe_ok, "probe_message": probe_msg,
                    "message": f"服务器响应 HTTP {e.code}，连接正常，耗时 {elapsed_ms}ms",
                }
            return {
                "ok": False, "status_code": e.code, "latency_ms": elapsed_ms,
                "tested_url": test_url, "is_multimodal": multimodal,
                "probe_multimodal": probe_ok, "probe_message": probe_msg,
                "message": f"服务器可达（HTTP {e.code}），但端点路径不正确。请确认 Base URL：{test_url}",
            }
        except urllib.error.URLError as e:
            elapsed_ms = round((time.time() - start) * 1000)
            reason = str(e.reason or e)
            return {
                "ok": False, "latency_ms": elapsed_ms, "tested_urls": tried_urls,
                "is_multimodal": multimodal,
                "probe_multimodal": probe_ok, "probe_message": probe_msg,
                "message": f"无法连接到 {test_url}\n错误: {reason}\n请检查 Base URL 是否正确、网络是否可达",
            }

    # ── OpenAI 兼容端点：GET 探测模型列表 → 根路径连通性 ──
    candidates = [f"{base}/v1/models", f"{base}/models", base]
    if base.endswith("/v1"):
        candidates = [f"{base}/models", base]

    for test_url in candidates:
        tried_urls.append(test_url)
        urlopen_kwargs = {"timeout": 10}
        if ctx:
            urlopen_kwargs["context"] = ctx
        try:
            req_obj = urllib.request.Request(test_url, headers=headers, method="GET")
            with urllib.request.urlopen(req_obj, **urlopen_kwargs) as resp:
                elapsed_ms = round((time.time() - start) * 1000)
                model_ids: list = []
                try:
                    data = _json.loads(resp.read().decode("utf-8", errors="replace"))
                    if isinstance(data, dict):
                        items = data.get("data") or data.get("models") or []
                        for item in items[:20]:
                            mid = item.get("id") or item.get("model") or ""
                            if mid:
                                model_ids.append(mid)
                except Exception:
                    pass
                return {
                    "ok": True, "status_code": resp.status, "latency_ms": elapsed_ms,
                    "tested_url": test_url, "models": model_ids, "is_multimodal": multimodal,
                    "probe_multimodal": probe_ok, "probe_message": probe_msg,
                    "message": f"连接成功（HTTP {resp.status}），耗时 {elapsed_ms}ms" + (
                        f"，检测到 {len(model_ids)} 个模型" if model_ids else ""),
                }
        except urllib.error.HTTPError as e:
            elapsed_ms = round((time.time() - start) * 1000)
            if e.code in (401, 403):
                return {
                    "ok": False, "latency_ms": elapsed_ms, "tested_url": test_url,
                    "is_multimodal": multimodal,
                    "probe_multimodal": probe_ok, "probe_message": probe_msg,
                    "message": f"服务器可达（HTTP {e.code}），但 API Key 被拒绝。请检查 Key 是否正确",
                }
            if e.code == 404:
                last_error_detail = f"{test_url} → HTTP 404（该路径不存在）"
                continue
            return {
                "ok": True, "status_code": e.code, "latency_ms": elapsed_ms,
                "tested_url": test_url, "models": [], "is_multimodal": multimodal,
                "probe_multimodal": probe_ok, "probe_message": probe_msg,
                "message": f"服务器可达（HTTP {e.code}），连接正常，耗时 {elapsed_ms}ms",
            }
        except urllib.error.URLError as e:
            last_error_detail = f"{test_url} → {e.reason}"
            continue
        except Exception as e:
            last_error_detail = f"{test_url} → {e}"
            continue

    elapsed_ms = round((time.time() - start) * 1000)
    return {
        "ok": False, "latency_ms": elapsed_ms, "tested_urls": tried_urls,
        "is_multimodal": multimodal,
        "probe_multimodal": probe_ok, "probe_message": probe_msg,
        "message": f"无法连接到服务器（可能是网络不通、DNS 解析失败或 SSL 证书问题）。\n已尝试: {', '.join(tried_urls)}\n最后错误: {last_error_detail}",
    }


def _build_embedding_probe_endpoints(base: str, vision: bool = False) -> list:
    """根据 Base URL 构造 embedding 探测端点。

    - vision 多模态模型（doubao-embedding-vision 等）：POST /embeddings/multimodal
    - 普通模型：POST /embeddings（OpenAI 兼容）
    """
    base = base.rstrip("/")
    candidates = []
    if base.endswith("/embeddings/multimodal"):
        candidates = [base]
    elif vision:
        candidates = [f"{base}/embeddings/multimodal"]
        if not base.endswith("/embeddings"):
            candidates.append(f"{base}/embeddings")
    elif base.endswith("/embeddings"):
        candidates = [base]
    elif base.endswith("/v1"):
        candidates = [f"{base}/embeddings"]
    else:
        # 兼容 Ark(/api/v3)、DashScope 兼容模式(/compatible-mode)、vLLM(/v1) 等
        candidates = [f"{base}/embeddings", f"{base}/v1/embeddings"]
    # 去重保持顺序
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _test_embedding_endpoint(base, api_key, model_name, headers, ctx, start, multimodal: bool = False) -> dict:
    """
    Embedding 分类连通性测试。

    背景：火山方舟（Ark）等平台不实现 OpenAI 的 GET /models 接口，
    用 GET 探测会误报 401/404；真实调用路径是 POST /embeddings。
    多模态 embedding 模型（doubao-embedding-vision，或 ep-xxx 接入点 + 多模态开关）
    走 POST /embeddings/multimodal，input 为内容块数组格式。

    探测策略：按配置把 multimodal 与文本端点都试一遍，任一 200 即通过；
    400/404 记录后继续尝试下一个端点，最后汇总报告。
    """
    import time, urllib.request, json as _json

    from backend.rag.embeddings import _is_vision_embedding_model

    use_multimodal = multimodal or _is_vision_embedding_model(model_name)

    # 候选端点：multimodal 优先（多模态配置），文本端点兜底
    multimodal_urls = _build_embedding_probe_endpoints(base, vision=True)
    text_urls = [u for u in _build_embedding_probe_endpoints(base, vision=False) if u not in multimodal_urls]
    candidates = (multimodal_urls + text_urls) if use_multimodal else (text_urls + multimodal_urls)

    tried = []
    details = []
    key_rejected = False

    for test_url in candidates:
        tried.append(test_url)
        is_mm = "multimodal" in test_url
        if is_mm:
            body_obj = {"model": model_name or "", "input": [{"type": "text", "text": "ping"}]}
        else:
            body_obj = {"model": model_name or "text-embedding-3-small", "input": ["ping"]}
        body = _json.dumps(body_obj).encode()
        req_obj = urllib.request.Request(test_url, data=body, headers=headers, method="POST")
        try:
            urlopen_kwargs = {"timeout": 15}
            if ctx:
                urlopen_kwargs["context"] = ctx
            with urllib.request.urlopen(req_obj, **urlopen_kwargs) as resp:
                elapsed_ms = round((time.time() - start) * 1000)
                return {
                    "ok": True, "status_code": resp.status, "latency_ms": elapsed_ms,
                    "tested_url": test_url, "models": [], "is_multimodal": False,
                    "probe_multimodal": None, "probe_message": None,
                    "message": f"✅ Embedding 接口可达（HTTP {resp.status}），耗时 {elapsed_ms}ms。Key 验证通过",
                }
        except urllib.error.HTTPError as e:
            elapsed_ms = round((time.time() - start) * 1000)
            body_snippet = ""
            try:
                raw = e.read().decode("utf-8", errors="replace")[:300]
                if raw:
                    body_snippet = f" 平台返回: {raw}"
            except Exception:
                pass
            if e.code in (401, 403):
                key_rejected = True
                host_hint = _volcengine_host_hint(test_url)
                return {
                    "ok": False, "status_code": e.code, "latency_ms": elapsed_ms,
                    "tested_url": test_url, "models": [], "is_multimodal": False,
                    "probe_multimodal": None, "probe_message": None,
                    "message": (
                        f"服务器可达（HTTP {e.code}），但 API Key 被拒绝。\n"
                        f"请求地址: {test_url}\n"
                        f"{host_hint}"
                        "请检查：\n"
                        "1. API Key：在方舟控制台「API Key 管理」复制完整 Key（注意区分大小写、不要带多余空格或引号，方舟 Key 形如 ark-xxx）\n"
                        "2. Base URL 是否正确：方舟模型 API 应为 https://ark.cn-beijing.volces.com/api/v3\n"
                        "3. 模型开通：方舟需先开通 doubao-embedding-vision 模型（模型广场 → 开通），或用推理接入点 ID（ep-xxxxxx）作为模型名"
                        f"{body_snippet}"
                    ),
                }
            # 400/404/其他：记录后继续尝试下一个端点
            details.append(f"{test_url} → HTTP {e.code}{body_snippet}")
        except urllib.error.URLError as e:
            details.append(f"{test_url} → {e.reason}")
        except Exception as e:
            details.append(f"{test_url} → {e}")

    elapsed_ms = round((time.time() - start) * 1000)
    summary = "\n".join(f"  - {d}" for d in details) or "  （无请求发出）"
    hint = "Key 被拒绝" if key_rejected else "全部端点均失败"
    return {
        "ok": False, "latency_ms": elapsed_ms, "tested_urls": tried,
        "is_multimodal": False, "probe_multimodal": None, "probe_message": None,
        "message": (
            f"Embedding 接口测试失败（{hint}）。\n"
            f"已尝试 {len(tried)} 个端点：\n{summary}\n\n"
            "常见排查（多模态 embedding doubao-embedding-vision）：\n"
            "1. 确认「多模态 Embedding」开关已勾选（配置保存后生效）\n"
            "2. 模型未开通：方舟控制台 → 「开通管理」→ 开通 doubao-embedding-vision，复制准确的「模型 ID」\n"
            "3. 或创建「推理接入点」后用 ep-xxxxxx 作为模型名\n"
            "4. Base URL 应为 https://ark.cn-beijing.volces.com/api/v3"
        ),
    }


def _volcengine_host_hint(test_url: str) -> str:
    """识别火山引擎常见填错产品域的情况，返回针对性提示。"""
    host = (test_url or "").lower()
    if "operator.las" in host or "las.cn-beijing" in host:
        return (
            "⚠️ 检测到 Base URL 指向火山「智能体平台」（operator.las.cn-beijing.volces.com），"
            "该平台与方舟「模型 API」是两套独立产品、Key 不通用。\n"
            "方舟模型 API 的 Base URL 应为：https://ark.cn-beijing.volces.com/api/v3\n"
        )
    if "volces.com" in host and "/api/v1" in host:
        return (
            "⚠️ Base URL 路径为 /api/v1（可能是其他火山产品），方舟模型 API 路径应为 /api/v3。\n"
        )
    return ""


# ════════════════════════════════════════════════════════════
# 模型路由规则 API（降级链 + 场景路由）
# ════════════════════════════════════════════════════════════

_route_router = APIRouter(prefix="/api/model-routes", tags=["model-routes"])


@_route_router.get("/fallback-chain")
async def get_fallback_chain(user: dict = Depends(get_current_user)):
    """获取降级链配置（按顺序排列的 model_config 完整信息列表）。"""
    from backend.service.model_router import router as _model_router
    chain = _model_router.get_fallback_chain_configs()
    return {"ok": True, "fallback_chain": chain}


@_route_router.put("/fallback-chain")
async def save_fallback_chain(
    body: dict,
    user: dict = Depends(get_current_user),
):
    """更新降级链配置。body: {"model_ids": [3, 1, 5]}"""
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="缺少权限: system.config")
    model_ids = body.get("model_ids", [])
    if not isinstance(model_ids, list):
        raise HTTPException(status_code=400, detail="model_ids 必须为数组")
    # 验证所有 ID 存在且启用
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if model_ids:
            placeholders = ','.join(['%s'] * len(model_ids))
            cur.execute(
                f"SELECT id FROM model_configs WHERE id IN ({placeholders}) AND enabled = 1",
                tuple(model_ids),
            )
            valid_ids = {r["id"] for r in cur.fetchall()}
            invalid = [i for i in model_ids if i not in valid_ids]
            if invalid:
                raise HTTPException(status_code=400, detail=f"以下模型配置不存在或已禁用: {invalid}")
    finally:
        conn.close()
    from backend.db.model_route_mapper import route_mapper
    route_mapper.save_fallback_chain([int(i) for i in model_ids])
    return {"ok": True, "model_ids": model_ids}


@_route_router.get("/scene-routing")
async def get_scene_routing(user: dict = Depends(get_current_user)):
    """获取场景路由配置。"""
    from backend.db.model_route_mapper import route_mapper
    routing = route_mapper.get_scene_routing()
    # 附带模型名称方便前端展示
    enriched = {}
    if routing:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            ids = list(set(routing.values()))
            if ids:
                placeholders = ','.join(['%s'] * len(ids))
                cur.execute(
                    f"SELECT id, config_name, model_name FROM model_configs WHERE id IN ({placeholders})",
                    tuple(ids),
                )
                id_to_name = {r["id"]: {"config_name": r.get("config_name", ""), "model_name": r.get("model_name", "")} for r in cur.fetchall()}
                for scene, mid in routing.items():
                    enriched[scene] = {"model_config_id": mid, **(id_to_name.get(mid, {}))}
        finally:
            conn.close()
    return {"ok": True, "routing": enriched}


@_route_router.put("/scene-routing")
async def save_scene_routing(
    body: dict,
    user: dict = Depends(get_current_user),
):
    """更新场景路由配置。body: {"code": 2, "summary": 4, "chat": 1}"""
    if not has_permission(user.get("user_id"), "system.config"):
        raise HTTPException(status_code=403, detail="缺少权限: system.config")
    routing = body.get("routing", {})
    if not isinstance(routing, dict):
        raise HTTPException(status_code=400, detail="routing 必须为对象")
    # 验证所有模型 ID 存在且启用
    model_ids = [int(v) for v in routing.values() if v]
    if model_ids:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            placeholders = ','.join(['%s'] * len(model_ids))
            cur.execute(
                f"SELECT id FROM model_configs WHERE id IN ({placeholders}) AND enabled = 1",
                tuple(model_ids),
            )
            valid_ids = {r["id"] for r in cur.fetchall()}
            invalid = [i for i in model_ids if i not in valid_ids]
            if invalid:
                raise HTTPException(status_code=400, detail=f"以下模型配置不存在或已禁用: {invalid}")
        finally:
            conn.close()
    from backend.db.model_route_mapper import route_mapper
    route_mapper.save_scene_routing({str(k): int(v) for k, v in routing.items()})
    return {"ok": True, "routing": routing}


@_route_router.post("/evaluate")
async def evaluate_route(
    scene: str = "",
    category: str = "chat",
    user: dict = Depends(get_current_user),
):
    """测试/预览当前路由规则会选中哪个模型。"""
    from backend.service.model_router import router as _model_router
    result = _model_router.evaluate_route(category=category, scene=scene)
    return {"ok": True, **result}


@_route_router.get("/scenes")
async def list_scenes(user: dict = Depends(get_current_user)):
    """获取所有可用的 LLM 使用场景（供前端配置场景路由时选择）。

    返回场景列表，按分类排序，包含：
    - key: 场景标识（用于 API 传参）
    - name: 显示名称
    - category: 分类（memory/rag/context/graph/utility/entry/custom）
    - description: 场景描述
    - recommended_model: 推荐模型类型提示
    - is_builtin: 是否为内置场景
    """
    from backend.service.scene_registry import scenes
    return {"ok": True, **scenes.to_dict()}
