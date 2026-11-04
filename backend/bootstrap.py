"""显式装配与启动顺序（架构 §2/A01、§10）。

本模块 import 无任何副作用：不连接数据库、不启动监听、不加载 .env。
所有真实启动发生在 lifespan 阶段显式调用 run_startup。
"""
from dataclasses import dataclass
from typing import Any

from backend.platform.settings import AppSettings, default_settings, settings_from_environment

__all__ = [
    "AppSettings",
    "ModuleRegistry",
    "default_settings",
    "run_shutdown",
    "run_startup",
    "settings_from_environment",
]


@dataclass(slots=True)
class ModuleRegistry:
    """bootstrap 显式构造出的模块集合；任务推进时逐个加入。

    各字段在对应任务完成后才有真实类型；未完成的任务不创建占位实现。
    """

    settings: AppSettings
    db: Any | None = None  # Task 2 (platform.sqlite.Database)
    access: Any | None = None  # Task 3
    models: Any | None = None  # Task 4
    usage: Any | None = None  # Task 4
    runtime: Any | None = None  # Task 5 (ExecutionRuntime)
    assistant: Any | None = None  # Task 6
    channels: Any | None = None  # Task 7
    delivery: Any | None = None  # Task 8
    delivery_worker: Any | None = None  # Task 8（唯一投递 worker）
    email: Any | None = None  # Task 14
    report: Any | None = None  # Task 14
    scheduling: Any | None = None  # Task 8
    scheduler: Any | None = None  # Task 8（唯一提醒调度器）
    memory: Any | None = None  # Task 9
    memory_worker: Any | None = None  # Task 9
    skills: Any | None = None  # Task 10
    evolution: Any | None = None  # Task 11
    evolution_worker: Any | None = None  # Task 11
    adoption: Any | None = None  # Task 12
    files: Any | None = None  # 增量 F1（FileService）
    ledger: Any | None = None  # 增量 F4（LedgerService）
    ledger_worker: Any | None = None  # 增量 F5（账本后台任务 worker）


async def run_startup(registry: ModuleRegistry) -> None:
    """lifespan 启动序列（架构 §10）。

    Task 2 起：执行版本化迁移，失败明确终止启动。模块构造、调度器恢复
    随后续任务在此函数中按固定顺序加入。
    """
    from backend.platform.sqlite import Database

    registry.settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    db = Database(registry.settings.data_db_path)
    db.migrate()  # 迁移失败抛 MigrationError → 启动终止
    registry.db = db

    # Task 15：启动时构造最小生产依赖（access/usage），不再依赖旧 controller 扫描。
    if registry.access is None:
        import secrets

        from backend.modules.access.api import AccessService

        secret = registry.settings.jwt_secret or secrets.token_hex(32)
        registry.access = AccessService(db, jwt_secret=secret)
    registry.access.seed()

    if registry.usage is None:
        from backend.modules.usage.api import UsageService

        registry.usage = UsageService(
            db,
            effective_permissions=lambda principal: registry.access.effective_permissions(
                principal.user_id
            ),
        )

    if registry.models is None and registry.settings.encryption_secret:
        from backend.modules.models.api import ModelsService

        registry.models = ModelsService(
            db, encryption_secret=registry.settings.encryption_secret,
            permission_check=registry.access.require_permission,
        )

    if registry.runtime is None and registry.settings.hermes_enabled:
        from backend.runtime.hermes.adapter import HermesRuntimeAdapter

        registry.runtime = HermesRuntimeAdapter(
            hermes_home=registry.settings.artifacts_dir / "hermes",
            usage=registry.usage, models=registry.models,
        )
        await registry.runtime.startup()

    # Task 6：统一 Assistant（runtime 缺省时不装配——最小工厂仅存活/就绪）
    if registry.runtime is not None and registry.access is not None:
        from backend.modules.assistant.api import AssistantService

        registry.assistant = AssistantService(
            db, runtime=registry.runtime, models=registry.models, access=registry.access,
        )
        await registry.assistant.start()

    if registry.access is not None and registry.files is None:
        # 增量 F1：统一文件权威（原件落本地持久目录，元数据在 app.db）
        from backend.modules.files.api import FileService
        from backend.modules.files.local_store import LocalFileStore

        registry.files = FileService(
            db,
            access=registry.access,
            store=LocalFileStore(registry.settings.files_root),
        )

    if registry.access is not None and registry.files is not None:
        # 增量 F4/F5：账本导入解析与统计（唯一 worker + JobQueue，不阻塞 Web）
        from backend.integrations.pdf import build_pdf_renderer
        from backend.modules.ledger.api import LedgerService
        from backend.modules.ledger.worker import LedgerWorker
        from backend.platform.jobs import JobQueue

        ledger_queue = JobQueue(db)
        registry.ledger = LedgerService(
            db, access=registry.access, files=registry.files, queue=ledger_queue,
            timezone=registry.settings.project_timezone,
            pdf=build_pdf_renderer(registry.settings),
        )
        registry.ledger_worker = LedgerWorker(registry.ledger, ledger_queue)
        await registry.ledger_worker.start()

    # Task 7：渠道模块（默认 wechat_enabled=False，不启动任何监听）。
    # 组装需要部署密钥（凭证加密）；缺失时明确跳过而不是以明文落库。
    if (
        registry.settings.wechat_enabled
        and registry.assistant is not None
        and registry.access is not None
    ):
        secret = str(registry.settings.encryption_secret or "")
        if secret:
            from backend.modules.channels.api import ChannelService
            from backend.modules.channels.wechat.account import AiohttpTransport
            from backend.modules.channels.wechat.media import HttpMediaFetcher

            transport = AiohttpTransport()
            registry.channels = ChannelService(
                db,
                assistant=registry.assistant,
                access=registry.access,
                encryption_secret=secret,
                transport=transport,
                media_fetcher=HttpMediaFetcher(transport),
                media_dir=registry.settings.artifacts_dir / "channels",
                files=registry.files,
            )
            await registry.channels.start_listeners()
        else:
            import logging

            logging.getLogger(__name__).warning(
                "EASYCHAT_WECHAT_ENABLED=true 但未设置 EASYCHAT_ENCRYPTION_SECRET，"
                "渠道模块保持关闭（不会以明文保存 bot token）"
            )

    # Task 8：投递账本 + 唯一投递 worker + 唯一提醒调度器。
    # 无渠道时仍构造账本（email 能力独立），但 sender 显式拒绝而非静默成功。
    if registry.access is not None:
        from backend.modules.delivery.api import DeliveryService
        from backend.modules.delivery.wechat import DisabledDeliverySender, WeChatTextSender
        from backend.modules.delivery.worker import DeliveryWorker

        sender = (
            WeChatTextSender(registry.channels)
            if registry.channels is not None else DisabledDeliverySender()
        )
        registry.delivery = DeliveryService(db, sender=sender)
        registry.delivery_worker = DeliveryWorker(registry.delivery)
        await registry.delivery_worker.start()
        if registry.assistant is not None:
            registry.assistant.dispatcher.on_run_finished = _make_run_finished(registry)

        from backend.modules.scheduling.api import SchedulingService
        from backend.modules.scheduling.scheduler import Scheduler

        registry.scheduling = SchedulingService(
            db, delivery=registry.delivery, access=registry.access,
            timezone_name=registry.settings.project_timezone,
        )
        registry.scheduler = Scheduler(registry.scheduling)
        await registry.scheduler.start()

    # Task 14：邮件配置/报告能力（与渠道解耦；缺少部署密钥时保持不可用）。
    if registry.access is not None and registry.settings.encryption_secret:
        from backend.modules.delivery.smtp import EmailService

        registry.email = EmailService(
            db, access=registry.access,
            encryption_secret=registry.settings.encryption_secret,
        )
        if registry.delivery is not None:
            from backend.integrations.pdf import build_pdf_renderer
            from backend.modules.delivery.reports import ReportService

            registry.report = ReportService(
                delivery=registry.delivery, renderer=build_pdf_renderer(registry.settings),
                artifacts_dir=registry.settings.artifacts_dir,
            )

    # Task 9：记忆服务与幂等信号 worker（runtime 桥接见 runtime/hermes/memory_bridge.py）。
    if registry.access is not None:
        from backend.modules.memory.api import MemoryService
        from backend.modules.memory.worker import MemoryWorker
        from backend.platform.jobs import JobQueue

        job_queue = JobQueue(db)
        registry.memory = MemoryService(db, access=registry.access, queue=job_queue)
        registry.memory_worker = MemoryWorker(registry.memory, job_queue)
        await registry.memory_worker.start()

        # Task 10：技能资产与不可变版本（内容根目录显式落在 artifacts 下）。
        from backend.modules.skills.api import SkillService

        registry.skills = SkillService(
            db, access=registry.access,
            content_root=registry.settings.artifacts_dir / "skills",
        )

        # Task 11：唯一学习调度 + 预算。
        from backend.modules.evolution.api import EvolutionService
        from backend.modules.evolution.budget import BudgetManager
        from backend.modules.evolution.worker import EvolutionWorker

        evolution_queue = JobQueue(db)
        registry.evolution = EvolutionService(
            db, access=registry.access, queue=evolution_queue,
            budget=BudgetManager(
                db, timezone_name=registry.settings.project_timezone,
            ),
        )
        registry.evolution_worker = EvolutionWorker(registry.evolution, evolution_queue)
        await registry.evolution_worker.start()

        from backend.modules.evolution.adoption import AdoptionService

        registry.adoption = AdoptionService(db, registry.skills)


def _make_run_finished(registry: ModuleRegistry):
    """run 终态与投递请求同事务：先取已落库的最终回复，再入队。"""

    def on_run_finished(conn, run) -> None:
        if registry.channels is None or registry.delivery is None:
            return
        if str(run.get("source") or "") != "wechat":
            return
        target_data = registry.channels.delivery_target_for_run(run)
        if not target_data:
            return
        row = conn.execute(
            "SELECT content FROM conversations WHERE run_id=? AND role='assistant' "
            "ORDER BY id DESC LIMIT 1",
            (run["id"],),
        ).fetchone()
        if row is None:
            return
        from backend.modules.delivery.contracts import DeliveryTarget

        registry.delivery.enqueue_run_in_transaction(
            conn, run, DeliveryTarget(**target_data), str(row["content"]),
        )

    return on_run_finished


async def run_shutdown(registry: ModuleRegistry) -> None:
    """lifespan 关闭序列：停止接收→停任务→关Runtime→最终刷计量→释放连接。

    后续任务按逆序补充；整个流程保持幂等。
    """
    if registry.report is not None:
        registry.report = None
    if registry.email is not None:
        registry.email = None
    if registry.adoption is not None:
        registry.adoption = None
    if registry.evolution_worker is not None:
        await registry.evolution_worker.stop()
        registry.evolution_worker = None
    if registry.evolution is not None:
        registry.evolution = None
    if registry.skills is not None:
        registry.skills = None
    if registry.memory_worker is not None:
        await registry.memory_worker.stop()
        registry.memory_worker = None
    if registry.memory is not None:
        registry.memory = None
    if registry.scheduler is not None:
        await registry.scheduler.stop()
        registry.scheduler = None
    if registry.delivery_worker is not None:
        await registry.delivery_worker.stop()
        registry.delivery_worker = None
    if registry.delivery is not None:
        registry.delivery = None
    if registry.scheduling is not None:
        registry.scheduling = None
    if registry.channels is not None:
        await registry.channels.aclose()
        registry.channels = None
    if registry.assistant is not None:
        await registry.assistant.aclose()
        registry.assistant = None
    if registry.runtime is not None:
        aclose = getattr(registry.runtime, "aclose", None)
        if aclose is not None:
            await aclose()
        registry.runtime = None
    if registry.db is not None:
        registry.db.close()
        registry.db = None
    # 连接已关闭：释放依赖旧 db 的模块，保证再次进入 lifespan 时重建
    registry.access = None
    registry.models = None
    registry.usage = None
