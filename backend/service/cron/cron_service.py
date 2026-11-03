"""
定时任务调度服务

基于 APScheduler BackgroundScheduler + MemoryJobStore。
应用启动时从 cron_jobs 表恢复所有启用任务，重启不丢失。

投递通道：
  - wechat → iLink sendmessage API（复用 wechat_listener 的发送链路）
  - email  → SMTP（复用 email_config_controller 的邮箱配置）
  - both   → 同时投递
"""
import asyncio
import threading
import uuid
from datetime import datetime
from typing import Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_MISSED, EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from backend.utils.log_utils import log
from backend.service.cron.data import CronDataMapper
from backend.service.cron.delivery import cron_delivery

logger = log

TZ = pytz.timezone("Asia/Shanghai")

# ── 执行状态常量 ──
STATUS_PENDING = 0    # 等待执行 / 执行中
STATUS_SUCCESS = 1    # 成功
STATUS_FAILED  = 2    # 失败
STATUS_QUALITY_ISSUES = 3  # 成功但有质量问题（报告质量结算降级码，投递不阻断）

# ── 投递状态常量 ──
DELIVER_PENDING = ""         # 未投递
DELIVER_SENDING = "sending"  # 投递中
DELIVER_SENT    = "sent"     # 已投递
DELIVER_FAILED  = "failed"   # 投递失败

# ── 进程内 job 级互斥（防止同一任务重叠执行）──
# APScheduler 的 max_instances=1 只约束**调度器派发**的 run；
# 控制器里的「立即执行」走裸线程直接调 _execute_job，绕过了这层保护 →
# 连点按钮或与计划触发撞车时，同一 job 会并发产出 N 份报告、重复投递 N 封邮件/微信。
# ⚠️ 已知限制：多进程（多 worker）部署下这个进程内集合拦不住跨进程并发
#    （见 docs/修复执行清单.md §0.7「多 worker」行；本任务不引入 DB 锁）。
_running_jobs: set = set()
_running_jobs_lock = threading.Lock()


class CronService:
    """定时任务调度服务（单例）"""

    _instance = None
    _scheduler: Optional[BackgroundScheduler] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_scheduler()
        return cls._instance

    def _init_scheduler(self):
        if self._scheduler is not None:
            return
        self._scheduler = BackgroundScheduler(
            executors={"default": {"type": "threadpool", "max_workers": 3}},
            job_defaults={
                "coalesce": False,
                "max_instances": 1,
                "misfire_grace_time": 300,
            },
            timezone=TZ,
        )
        # 注册事件监听
        self._scheduler.add_listener(self._on_job_missed, EVENT_JOB_MISSED)
        self._scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
        self._scheduler.start()
        logger.info("定时任务调度器已启动")

    def _on_job_missed(self, event):
        logger.warning(f"[cron] job_misfired job_id={event.job_id}")

    def _on_job_error(self, event):
        logger.error(f"[cron] job_error job_id={event.job_id} exception={event.exception}")

    # ── 任务管理 ──

    def add_job(self, job_id: int, schedule_type: str, schedule_value: str) -> tuple:
        """注册/更新一个定时任务到调度器。
        
        返回: (success: bool, error_msg: str or None)
        """
        aps_job_id = f"cron_{job_id}"

        # 移除旧 job
        try:
            self._scheduler.remove_job(aps_job_id)
        except Exception:
            pass

        trigger, error_msg = self._build_trigger(schedule_type, schedule_value)
        if trigger is None:
            logger.error(f"[cron] 无法解析调度表达式: type={schedule_type} value={schedule_value} error={error_msg}")
            return False, error_msg

        self._scheduler.add_job(
            func=self._execute_job,
            trigger=trigger,
            args=[job_id],
            id=aps_job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=False,
            misfire_grace_time=300,
        )
        job = self._scheduler.get_job(aps_job_id)
        logger.info(
            f"[cron] 任务已注册: job_id={job_id} next_run={job.next_run_time if job else '?'}"
        )

        # 更新 next_run_at
        if job and job.next_run_time:
            CronDataMapper().set_next_run(job_id, job.next_run_time)

        return True, None

    def remove_job(self, job_id: int):
        try:
            self._scheduler.remove_job(f"cron_{job_id}")
            logger.info(f"[cron] 任务已移除: job_id={job_id}")
        except Exception:
            pass

    def _build_trigger(self, schedule_type: str, schedule_value: str):
        """根据类型构建 APScheduler 触发器。返回 (trigger, error_msg)"""
        value = (schedule_value or "").strip()
        
        if not value:
            return None, "调度时间不能为空"
        
        try:
            if schedule_type == "once":
                # 一次性执行: "2026-08-10 09:00" 或 "2026-08-10T09:00"
                try:
                    run_date = datetime.strptime(value.replace("T", " "), "%Y-%m-%d %H:%M")
                except ValueError:
                    return None, f"日期格式错误，应为 'YYYY-MM-DD HH:MM'，实际: {value}"
                return DateTrigger(run_date=run_date, timezone=TZ), None
                
            elif schedule_type == "cron":
                parts = value.split()
                if len(parts) != 5:
                    return None, f"Cron 表达式需要 5 个字段（分 时 日 月 周），实际: {value}"
                return CronTrigger(
                    minute=parts[0], hour=parts[1], day=parts[2],
                    month=parts[3], day_of_week=parts[4], timezone=TZ,
                ), None
                
            elif schedule_type == "interval":
                import re
                m = re.match(r"^(\d+)\s*(s|m|h|d)$", value.lower())
                if not m:
                    return None, f"间隔格式错误，应为 '数字+单位'（如 30m、1h、1d），实际: {value}"
                num = int(m.group(1))
                unit = m.group(2)
                kwargs = {"seconds": num} if unit == "s" else \
                         {"minutes": num} if unit == "m" else \
                         {"hours": num} if unit == "h" else \
                         {"days": num}
                return IntervalTrigger(**kwargs, timezone=TZ), None
                
            elif schedule_type == "daily":
                parts = value.split(":")
                if len(parts) != 2:
                    return None, f"时间格式错误，应为 'HH:MM'，实际: {value}"
                try:
                    hour, minute = int(parts[0]), int(parts[1])
                    if not (0 <= hour <= 23 and 0 <= minute <= 59):
                        return None, f"时间范围错误，小时应为 0-23，分钟应为 0-59"
                except ValueError:
                    return None, f"时间格式错误，应为 'HH:MM'，实际: {value}"
                return CronTrigger(hour=hour, minute=minute, timezone=TZ), None
                
            else:
                return None, f"未知的调度类型: {schedule_type}"
                
        except Exception as e:
            return None, f"解析调度表达式失败: {str(e)}"

    def get_job_next_run(self, job_id: int) -> Optional[datetime]:
        try:
            job = self._scheduler.get_job(f"cron_{job_id}")
            return job.next_run_time if job else None
        except Exception:
            return None

    # ── 执行核心 ──

    def _execute_job(self, job_id: int):
        """APScheduler 触发入口 — 在新线程中同步执行。同一 job 不允许重叠执行。"""
        with _running_jobs_lock:
            if job_id in _running_jobs:
                logger.warning(f"定时任务 {job_id} 正在执行，跳过本次触发")
                return
            _running_jobs.add(job_id)
        try:
            asyncio.run(self._execute_job_async(job_id))
        except Exception as e:
            logger.error(f"[cron] 执行失败 job_id={job_id}: {e}")
        finally:
            with _running_jobs_lock:
                _running_jobs.discard(job_id)

    async def _execute_job_async(self, job_id: int):
        """异步执行：读取任务配置 → 调用 LLM 生成报告 → 投递"""
        mapper = CronDataMapper()
        task = mapper.get_job(job_id)
        if not task:
            logger.warning(f"[cron] 任务不存在，跳过: job_id={job_id}")
            return

        user_id = int(task.get("user_id") or 0)
        name = task.get("name") or f"定时任务#{job_id}"
        prompt = task.get("prompt") or ""
        deliver_to = task.get("deliver_to") or "wechat"
        report_format = (task.get("report_format") or "pdf").strip().lower()

        workflow_run_id = f"cron-{job_id}-{uuid.uuid4().hex[:12]}"
        session_id = f"{user_id}_{uuid.uuid4().hex[:8]}"
        execution_id = mapper.create_execution(job_id, session_id)

        logger.info(
            f"[cron] 开始执行: job_id={job_id} name={name!r} "
            f"deliver_to={deliver_to} workflow={workflow_run_id}"
        )

        # 更新 last_run_at
        mapper.mark_run(job_id, STATUS_PENDING)

        result_text = ""
        error_message = ""
        quality_issues = ""
        final_status = STATUS_FAILED
        deliver_status = DELIVER_PENDING

        try:
            # ── 调用 Hermes Runtime 生成报告 ──
            from backend.hermes_adapter import get_runtime
            from backend.controller.agent_controller import get_current_model_config
            from backend.agents.prompts import get_decision_system_prompt
            from backend.permission.checker import get_user_hermes_tools
            from backend.service.cron.delivery import cron_delivery

            model_config = get_current_model_config(user_id)
            # 查询用户可用工具，动态生成系统提示词（定时任务只能使用用户拥有的工具）
            available_tools = get_user_hermes_tools(user_id)
            decision_prompt = get_decision_system_prompt(user_id=user_id, available_tools=available_tools)
            runtime = get_runtime(
                user_id, model_config or {}, decision_prompt, thread_id=session_id,
            )

            cron_prefix = (
                "【定时任务】本任务由定时任务系统自动触发。"
                f"你当前可用的工具：{', '.join(available_tools) if available_tools else '无'}。"
                "请根据以下提示词生成完整报告，不要省略。"
                "如果需要的工具不在可用列表中，请在报告中说明无法完成该功能。"
                "请使用 Markdown 格式输出报告内容（支持标题、列表、表格、代码块），"
                # ⚠️ 这里**不能**点名 fig_inter：该工具未注册到 Hermes registry
                # （不在 get_project_tools()，且其 _toolset="data" 已废弃），
                # 实测 registry.get_entry("fig_inter") 为 None。
                # 旧提示词让模型"调用 fig_inter 生成统计图"，模型每次都会尝试调用一个
                # 不存在的工具 → 图表永远不出现，还会浪费一轮并输出工具失败信息。
                # 如需恢复图表能力，必须先加固 backend/tools/data_visualization.py 的沙箱
                # （其 exec 无 AST 检查且模块对象自带 __builtins__，可 import os 逃逸）
                # 再注册，切勿直接接线。
                "数据统计、趋势、占比或分布请用 Markdown 表格呈现；"
                "不要调用不存在的工具，也不要尝试自行生成图片或 PDF。"
                "不要尝试自行生成 PDF 文件，PDF 由系统统一生成。"
                "\n\n## 重要格式要求"
                "\n- **禁止使用 ASCII 艺术图**：不要使用 `│`, `┌`, `─`, `┐`, `├`, `┤`, `└`, `┘` 等字符绘制架构图或目录树，这些字符在 PDF 中无法正确显示"
                "\n- **架构图请使用 Markdown 表格或列表描述**：例如用表格列出各层组件、用列表说明层级关系"
                "\n- **目录结构请使用缩进列表**：用 `-` 和缩进表示层级，如：\n  ```\n  - 目录/\n    - 文件1\n    - 文件2\n  ```"
            )
            
            full_message = f"{cron_prefix}\n\n{prompt}"

            hermes_result = await runtime.run(user_message=full_message)
            result_text = (hermes_result.get("final_response") or "").strip()

            if not result_text:
                raise RuntimeError("定时任务未生成可发送的报告内容")

            # ── 报告质量结算（借鉴 Eyes：质量门禁不阻断投递，但状态码降级 + 问题标注）──
            from backend.service.report.report_quality import check_report as _check_report
            _quality = _check_report(result_text)
            if not _quality.get("ok"):
                issues = _quality.get("issues") or ["报告存在质量问题"]
                quality_issues = "；".join(str(i) for i in issues)[:1024]
                logger.warning(
                    f"[cron] 报告质量检查未通过 job_id={job_id} issues={quality_issues}"
                )

            # ── 投递 ──
            deliver_status, fail_reasons = await self._deliver_result(
                task=task,
                subject=name,
                body=result_text,
                session_id=session_id,
            )
            if fail_reasons:
                error_message = "投递失败：" + "；".join(fail_reasons)
                final_status = STATUS_FAILED  # 投递失败必须记失败，不要用质量降级码
            else:
                final_status = STATUS_QUALITY_ISSUES if quality_issues else STATUS_SUCCESS
            logger.info(
                f"[cron] 执行完成: job_id={job_id} status={final_status} deliver={deliver_status}"
            )

        except Exception as e:
            error_message = str(e)
            final_status = STATUS_FAILED
            logger.error(f"[cron] 执行失败: job_id={job_id} error={error_message}")

        finally:
            mapper.finish_execution(
                execution_id, final_status, result_text, error_message, deliver_status,
                quality_issues=quality_issues,
            )

            # ── 一次性任务执行后从调度器移除（但保留任务记录，用户可编辑后再次执行）──
            if task.get("schedule_type") == "once":
                self.remove_job(job_id)
                # 不设置 enabled=0，保留任务让用户可以查看执行结果、修改时间再次执行
                logger.info(f"[cron] 一次性任务执行完成: job_id={job_id}")

            # 更新下一次运行时间
            next_run = self.get_job_next_run(job_id)
            if next_run:
                mapper.set_next_run(job_id, next_run)

            # ── 通知前端刷新 ──
            await self._notify_frontend(job_id, user_id, final_status, error_message)

    # ── 投递 ──

    async def _deliver_result(self, task: dict, subject: str, body: str,
                              session_id: str):
        """根据 deliver_to 配置投递报告到微信/邮箱。

        返回 (投递状态字符串, 失败原因列表)。
        """
        deliver_to = (task.get("deliver_to") or "wechat").strip().lower()
        user_id = int(task.get("user_id") or 0)
        statuses = []
        fail_reasons = []

        # ── 邮箱投递 ──
        if deliver_to in ("email", "both"):
            ok, reason = await cron_delivery.deliver_email(task, subject, body, user_id)
            statuses.append("email:ok" if ok else "email:failed")
            if not ok and reason:
                fail_reasons.append(f"邮件：{reason}")

        # ── 微信投递 ──
        if deliver_to in ("wechat", "both"):
            ok, reason = await cron_delivery.deliver_wechat(task, subject, body, user_id)
            statuses.append("wechat:ok" if ok else "wechat:failed")
            if not ok and reason:
                fail_reasons.append(f"微信：{reason}")

        status = "; ".join(statuses) if statuses else "no_channel"
        return status, fail_reasons

    async def _notify_frontend(self, job_id: int, user_id: int,
                               status: int, message: str = ""):
        """通过 SSE 通知前端刷新定时任务列表（使用定时任务专用事件）。"""
        try:
            from backend.controller.cron_controller import sse_manager
            await sse_manager.notify_user(user_id, {
                "type": "cron_task_completed",
                "job_id": job_id,
                "status": status,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.debug(f"[cron] SSE 通知跳过（前端可能不在线）: {e}")

    # ── 启动恢复 ──

    def restore_jobs_from_db(self) -> int:
        """应用启动时从 cron_jobs 表恢复所有启用的定时任务。"""
        mapper = CronDataMapper()
        tasks = mapper.list_all_enabled_jobs()
        restored = 0
        for task in tasks:
            try:
                job_id = int(task.get("id") or 0)
                schedule_type = task.get("schedule_type") or "cron"
                schedule_value = task.get("schedule_value") or ""
                if not job_id or not schedule_value:
                    continue
                self.add_job(job_id, schedule_type, schedule_value)
                restored += 1
            except Exception as e:
                logger.error(f"[cron] 恢复任务失败: id={task.get('id')} error={e}")
        logger.info(f"[cron] 启动恢复完成: 共 {len(tasks)} 条配置，恢复 {restored} 个 job")

        # 启动时清理孤儿执行记录（任务已不存在的记录）
        self._cleanup_orphan_executions()

        return restored

    def _cleanup_orphan_executions(self) -> int:
        """清理孤儿执行记录（任务已不存在的记录）。"""
        try:
            from backend.db.schema import get_conn
            conn = get_conn()
            try:
                # 只删除孤儿执行记录，不删除用户手动禁用的任务
                cur = conn.execute(
                    """DELETE FROM cron_executions 
                       WHERE job_id NOT IN (SELECT id FROM cron_jobs)"""
                )
                deleted = cur.rowcount if hasattr(cur, "rowcount") else 0
                conn.commit()
                if deleted > 0:
                    logger.info(f"[cron] 清理孤儿执行记录: {deleted} 条")
                return deleted
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"[cron] 清理孤儿执行记录失败: {e}")
            return 0

    def shutdown(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("定时任务调度器已关闭")


# 全局单例
cron_service = CronService()
