"""
定时任务控制器 — CRUD REST API

端点：
  GET    /api/cron-jobs             — 当前用户的定时任务列表
  POST   /api/cron-jobs             — 创建定时任务
  PUT    /api/cron-jobs/{id}        — 更新任务
  DELETE /api/cron-jobs/{id}        — 删除任务
  PUT    /api/cron-jobs/{id}/toggle — 启用/禁用
  POST   /api/cron-jobs/{id}/run-now — 立即执行一次
  GET    /api/cron-jobs/{id}/executions — 执行历史
  GET    /api/cron-events/{user_id} — SSE 事件流（定时任务状态推送）
"""
import asyncio
import json
from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.utils.log_utils import log
from backend.service.cron.cron_service import CronDataMapper, cron_service
from backend.db.schema import get_conn
from backend.service.auth.auth_middleware import get_current_user

logger = log

router = APIRouter(prefix="/api/cron-jobs", tags=["定时任务"])

# ── SSE 连接管理器 ──
_sse_queues: Dict[int, List[asyncio.Queue]] = {}


class SSEManager:
    """定时任务 SSE 通知管理器"""

    @staticmethod
    def add_connection(user_id: int, queue: asyncio.Queue):
        if user_id not in _sse_queues:
            _sse_queues[user_id] = []
        _sse_queues[user_id].append(queue)

    @staticmethod
    def remove_connection(user_id: int, queue: asyncio.Queue):
        if user_id in _sse_queues and queue in _sse_queues[user_id]:
            _sse_queues[user_id].remove(queue)

    @staticmethod
    async def notify_user(user_id: int, data: dict):
        if user_id not in _sse_queues or not _sse_queues[user_id]:
            return
        message = json.dumps(data)
        event = f"data: {message}\n\n"
        dead = []
        for queue in _sse_queues[user_id][:]:
            try:
                await queue.put(event)
            except Exception:
                dead.append(queue)
        for q in dead:
            SSEManager.remove_connection(user_id, q)


# 为了在 cron_service 中导入，暴露为模块级变量
sse_manager = SSEManager()


# ══════════════════════════════════════════════════════════════
# 请求/响应模型
# ══════════════════════════════════════════════════════════════

class CronJobCreate(BaseModel):
    user_id: int = Field(..., description="创建者用户ID")
    name: str = Field(..., description="任务名称", max_length=255)
    prompt: str = Field(..., description="AI提示词（报告内容指令）")
    schedule_type: str = Field(default="daily", description="调度类型: once / daily / cron / interval")
    schedule_value: str = Field(default="09:00", description="调度值，如 cron 表达式或 '30m'")
    deliver_to: str = Field(default="wechat", description="投递渠道: wechat / email / both")
    report_format: str = Field(default="pdf", description="报告格式: pdf / text / markdown")
    email_sender_id: Optional[int] = Field(default=None, description="指定发件邮箱配置ID")
    email_receiver_id: Optional[int] = Field(default=None, description="指定收件邮箱ID")


class CronJobUpdate(BaseModel):
    name: Optional[str] = Field(None, description="任务名称")
    prompt: Optional[str] = Field(None, description="AI提示词")
    schedule_type: Optional[str] = Field(None, description="调度类型")
    schedule_value: Optional[str] = Field(None, description="调度值")
    deliver_to: Optional[str] = Field(None, description="投递渠道")
    report_format: Optional[str] = Field(None, description="报告格式: pdf / text / markdown")
    email_sender_id: Optional[int] = Field(None, description="指定发件邮箱配置ID")
    email_receiver_id: Optional[int] = Field(None, description="指定收件邮箱ID")


# ══════════════════════════════════════════════════════════════
# REST API
# ══════════════════════════════════════════════════════════════

@router.get("/delivery-options", response_model=dict)
async def get_delivery_options(
    user: dict = Depends(get_current_user),
):
    """获取用户的投递选项（微信绑定 + 邮箱发送方 + 邮箱接收方）。"""
    user_id = user["user_id"]
    try:
        # ── 微信绑定 ──
        wechat_binding = None
        conn = get_conn()
        try:
            cur = conn.execute(
                """SELECT open_id, nickname FROM user_bindings
                   WHERE user_id = ? AND platform = 'wechat' AND enabled = 1 LIMIT 1""",
                (user_id,),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            if rows:
                row = rows[0]
                if isinstance(row, dict):
                    wechat_binding = {"open_id": row.get("open_id"), "nickname": row.get("nickname") or ""}
                else:
                    wechat_binding = {"open_id": row[0], "nickname": row[1] or ""}
        finally:
            conn.close()

        # ── 邮箱发送方（SMTP 配置） ──
        email_senders = []
        conn = get_conn()
        try:
            cur = conn.execute(
                """SELECT id, config_name, sender_email, sender_name, is_current
                   FROM email_configs WHERE (user_id = ? OR user_id = 1) AND enabled = 1
                   ORDER BY is_current DESC, id ASC""",
                (user_id,),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            for row in rows:
                if isinstance(row, dict):
                    email_senders.append({
                        "id": row["id"], "name": row.get("config_name") or row.get("sender_email"),
                        "email": row.get("sender_email"), "sender_name": row.get("sender_name"),
                        "is_current": bool(row.get("is_current")),
                    })
                else:
                    email_senders.append({
                        "id": row[0], "name": row[1] or row[2],
                        "email": row[2], "sender_name": row[3],
                        "is_current": bool(row[3]),
                    })
        finally:
            conn.close()

        # ── 邮箱接收方（个人邮箱） ──
        email_receivers = []
        conn = get_conn()
        try:
            cur = conn.execute(
                """SELECT id, email, is_current FROM personal_emails
                   WHERE user_id = ? ORDER BY is_current DESC, created_at DESC""",
                (user_id,),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            for row in rows:
                if isinstance(row, dict):
                    email_receivers.append({
                        "id": row["id"], "email": row.get("email"),
                        "is_current": bool(row.get("is_current")),
                    })
                else:
                    email_receivers.append({
                        "id": row[0], "email": row[1],
                        "is_current": bool(row[2]),
                    })
        finally:
            conn.close()

        return {
            "success": True,
            "data": {
                "wechat_binding": wechat_binding,
                "email_senders": email_senders,
                "email_receivers": email_receivers,
            },
        }
    except Exception as e:
        logger.error(f"[cron] 获取投递选项失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=dict)
async def list_cron_jobs(
    user: dict = Depends(get_current_user),
):
    """获取当前用户的定时任务列表。"""
    user_id = user["user_id"]
    try:
        mapper = CronDataMapper()
        jobs = mapper.list_jobs(user_id)

        conn = get_conn()
        try:
            for job in jobs:
                job_id = job.get("id")
                next_run = cron_service.get_job_next_run(job_id)
                job["next_run_at"] = next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else job.get("next_run_at")
                job["enabled"] = bool(job.get("enabled"))
                cur = conn.execute(
                    "SELECT status FROM cron_executions WHERE job_id = ? ORDER BY started_at DESC LIMIT 1",
                    (job_id,),
                )
                rows = cur.fetchall() if hasattr(cur, "fetchall") else []
                if rows:
                    row0 = rows[0]
                    job["last_exec_status"] = row0["status"] if isinstance(row0, dict) else row0[0]
                else:
                    job["last_exec_status"] = -1
        finally:
            conn.close()

        return {"success": True, "jobs": jobs, "count": len(jobs)}
    except Exception as e:
        logger.error(f"[cron] 获取任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=dict)
async def create_cron_job(
    req: CronJobCreate,
    user: dict = Depends(get_current_user),
):
    """创建定时任务。"""
    # 强制使用 token 中的 user_id，防止伪造
    req.user_id = user["user_id"]
    try:
        # 验证 schedule_value 不为空
        if not req.schedule_value or not req.schedule_value.strip():
            raise HTTPException(status_code=400, detail="调度时间不能为空")

        mapper = CronDataMapper()
        job_id = mapper.create_job(
            user_id=req.user_id,
            name=req.name,
            prompt=req.prompt,
            schedule_type=req.schedule_type,
            schedule_value=req.schedule_value,
            deliver_to=req.deliver_to,
            report_format=req.report_format,
            email_sender_id=req.email_sender_id,
            email_receiver_id=req.email_receiver_id,
        )

        # 注册到调度器
        success, error_msg = cron_service.add_job(job_id, req.schedule_type, req.schedule_value)
        if not success:
            # 注册失败，删除已创建的任务
            mapper.delete_job(job_id)
            raise HTTPException(status_code=400, detail=error_msg or "调度表达式格式错误")

        logger.info(f"[cron] 创建任务成功: job_id={job_id} name={req.name!r} user_id={req.user_id}")
        return {"success": True, "job_id": job_id, "message": "定时任务创建成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[cron] 创建任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{job_id}", response_model=dict)
async def update_cron_job(
    job_id: int,
    req: CronJobUpdate,
    user: dict = Depends(get_current_user),
):
    """更新定时任务。"""
    try:
        mapper = CronDataMapper()
        existing = mapper.get_job(job_id)
        if not existing:
            raise HTTPException(status_code=404, detail="定时任务不存在")
        
        # 验证用户权限
        if existing.get("user_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="无权修改此任务")

        # 只更新非空字段
        updates = {}
        for k, v in req.model_dump().items():
            if v is not None:
                updates[k] = v

        # 如果修改了调度参数，先验证格式
        st = updates.get("schedule_type") or existing.get("schedule_type")
        sv = updates.get("schedule_value") or existing.get("schedule_value")
        
        if "schedule_type" in updates or "schedule_value" in updates:
            # 验证调度表达式格式
            if not sv or not str(sv).strip():
                raise HTTPException(status_code=400, detail="调度时间不能为空")
            
            # 测试能否构建触发器
            success, error_msg = cron_service.add_job(job_id, st, sv)
            if not success:
                raise HTTPException(status_code=400, detail=error_msg or "调度表达式格式错误")
        else:
            # 没有修改调度参数，但可能修改了 enabled
            new_enabled = updates.get("enabled", existing.get("enabled"))
            if new_enabled and not existing.get("enabled"):
                # 从禁用变为启用，需要注册
                success, error_msg = cron_service.add_job(job_id, st, sv)
                if not success:
                    raise HTTPException(status_code=400, detail=error_msg or "调度表达式格式错误")

        if updates:
            mapper.update_job(job_id, **updates)

        logger.info(f"[cron] 更新任务成功: job_id={job_id}")
        return {"success": True, "message": "定时任务更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[cron] 更新任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{job_id}", response_model=dict)
async def delete_cron_job(
    job_id: int,
    user: dict = Depends(get_current_user),
):
    """删除定时任务。"""
    try:
        mapper = CronDataMapper()
        existing = mapper.get_job(job_id)
        if not existing:
            raise HTTPException(status_code=404, detail="定时任务不存在")
        
        # 验证用户权限
        if existing.get("user_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="无权删除此任务")

        cron_service.remove_job(job_id)
        mapper.delete_job(job_id)

        logger.info(f"[cron] 删除任务成功: job_id={job_id}")
        return {"success": True, "message": "定时任务删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[cron] 删除任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{job_id}/toggle", response_model=dict)
async def toggle_cron_job(
    job_id: int,
    user: dict = Depends(get_current_user),
):
    """启用/禁用定时任务。"""
    try:
        mapper = CronDataMapper()
        existing = mapper.get_job(job_id)
        if not existing:
            raise HTTPException(status_code=404, detail="定时任务不存在")

        # 验证用户权限
        if existing.get("user_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="无权操作此任务")

        new_enabled = 0 if existing.get("enabled") else 1
        mapper.update_job(job_id, enabled=new_enabled)

        if new_enabled:
            cron_service.add_job(
                job_id,
                existing.get("schedule_type") or "cron",
                existing.get("schedule_value") or "",
            )
        else:
            cron_service.remove_job(job_id)

        status_text = "启用" if new_enabled else "禁用"
        logger.info(f"[cron] 任务{status_text}: job_id={job_id}")
        return {"success": True, "enabled": bool(new_enabled), "message": f"定时任务已{status_text}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[cron] 切换任务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/run-now", response_model=dict)
async def run_cron_job_now(
    job_id: int,
    user: dict = Depends(get_current_user),
):
    """立即执行定时任务（手动触发）。"""
    try:
        mapper = CronDataMapper()
        existing = mapper.get_job(job_id)
        if not existing:
            raise HTTPException(status_code=404, detail="定时任务不存在")

        # 验证用户权限
        if existing.get("user_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="无权操作此任务")

        # 在后台执行（避免阻塞请求）
        import threading
        def _fire():
            cron_service._execute_job(job_id)
        threading.Thread(target=_fire, daemon=True).start()

        logger.info(f"[cron] 手动触发执行: job_id={job_id}")
        return {"success": True, "message": "定时任务已触发执行，请稍后查看执行历史"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[cron] 手动执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/executions", response_model=dict)
async def list_executions(
    job_id: int,
    limit: int = Query(default=20),
    user: dict = Depends(get_current_user),
):
    """获取定时任务执行历史。"""
    try:
        mapper = CronDataMapper()
        # 验证任务归属
        existing = mapper.get_job(job_id)
        if not existing:
            raise HTTPException(status_code=404, detail="定时任务不存在")
        if existing.get("user_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="无权查看此任务")
        executions = mapper.list_executions(job_id, limit)
        return {"success": True, "executions": executions, "count": len(executions)}
    except Exception as e:
        logger.error(f"[cron] 获取执行历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════
# SSE 事件流
# ══════════════════════════════════════════════════════════════

@router.get("/events/{user_id}", include_in_schema=False)
async def cron_events(
    request: Request,
    user_id: int,
    user: dict = Depends(get_current_user),
):
    """SSE 事件流 — 定时任务完成时推送通知给前端。"""
    # 只允许接收自己的事件
    if user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权访问此事件流")
    async def event_stream():
        queue = asyncio.Queue()
        sse_manager.add_connection(user_id, queue)

        yield f"data: {json.dumps({'type': 'connected', 'message': 'cron SSE connected'})}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield event
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        except Exception as e:
            logger.error(f"[cron] SSE 异常: user_id={user_id}, error={e}")
        finally:
            sse_manager.remove_connection(user_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )

# 注：此处原有一段"清理已禁用的定时任务"的端点实现（DELETE cron_jobs WHERE enabled = 0
#     + 清理孤儿 cron_executions），但它的 @router 装饰器与 def 定义早已丢失，整段落在
#     上方 SSE 端点的 return 之后，属**永不执行的死代码**（自 b85b4ad 起即如此，非本次引入）。
#     该端点当前**不存在**，前端亦无调用方。因其实为从未运行过的破坏性删除逻辑，
#     重新启用风险大于收益，故删除；如确需该能力，请在 git 历史中取回实现，
#     并补上 @router.post + system.manage 权限门禁后再启用。
