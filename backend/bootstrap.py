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
    profiles: Any | None = None  # 微信 A+C：人格/安静时段/情绪
    mood_worker: Any | None = None
    briefing: Any | None = None  # 微信 A+C：早/晚/周报
    briefing_worker: Any | None = None
    inbox: Any | None = None  # 微信 A+C：稍后读
    inbox_worker: Any | None = None
    superagent: Any | None = None  # 超级代理：微信收需求 → 编码 → 自动提 PR
    superagent_worker: Any | None = None
    superagent_webhooks: Any | None = None  # GitHub 回流（T7）
    job_queue: Any | None = None  # 共享 JobQueue（run 终态/调度/投递 worker）


async def run_startup(registry: ModuleRegistry) -> None:
    """lifespan 启动序列（架构 §10）。

    先构造全部依赖并完成工具/回调注册，再启动 assistant worker，最后启动
    渠道监听；任何窗口期都不得出现“run 先完成、投递/记忆 job 尚未接线”。
    """
    import logging

    from backend.platform.jobs import JobQueue
    from backend.platform.sqlite import Database

    logger = logging.getLogger(__name__)
    registry.settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    # 部署密钥下限（审计 #1/#9）：加密密钥保护全部凭据信封，弱值/占位值在
    # 构造任何服务之前拒绝启动；留空仍允许（信封子系统整体关闭）。
    encryption_secret = str(registry.settings.encryption_secret or "")
    if encryption_secret:
        from backend.modules.access.api import validate_deployment_secret

        validate_deployment_secret(encryption_secret, kind="EASYCHAT_ENCRYPTION_SECRET")
    db = Database(registry.settings.data_db_path)
    db.migrate()  # 迁移失败抛 MigrationError → 启动终止
    registry.db = db

    # 1) access / usage / models（最小生产依赖）
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

    # 2) 文件 / 账本（账本依赖 files；worker 在 assistant 之后统一启动）
    if registry.access is not None and registry.files is None:
        from backend.modules.files.api import FileService
        from backend.modules.files.local_store import LocalFileStore

        registry.files = FileService(
            db,
            access=registry.access,
            store=LocalFileStore(registry.settings.files_root),
        )

    registry.job_queue = registry.job_queue or JobQueue(db)
    if registry.access is not None and registry.files is not None:
        from backend.integrations.pdf import build_pdf_renderer
        from backend.modules.ledger.api import LedgerService
        from backend.modules.ledger.worker import LedgerWorker

        registry.ledger = LedgerService(
            db, access=registry.access, files=registry.files, queue=registry.job_queue,
            timezone=registry.settings.project_timezone,
            pdf=build_pdf_renderer(registry.settings),
        )
        registry.ledger_worker = LedgerWorker(registry.ledger, registry.job_queue)

    # 3) profiles（人格/安静时段/情绪；assistant 与调度器共用）
    if registry.access is not None:
        from backend.integrations.llm import OpenAICompatibleTextGenerator
        from backend.modules.profiles.api import ProfilesService

        generator = (
            OpenAICompatibleTextGenerator(models=registry.models, usage=registry.usage)
            if registry.models is not None else None
        )
        registry.profiles = ProfilesService(
            db, access=registry.access, queue=registry.job_queue, generator=generator,
            care_canceller=_make_care_canceller(registry),
        )
        try:
            # 保留期不能只靠用户打开周报时被动触发；启动时清理一次过期情绪。
            registry.profiles.purge_expired_mood()
        except Exception:  # noqa: BLE001  清理失败不能阻塞服务启动
            logger.exception("启动时清理过期情绪失败")
        from backend.modules.inbox.api import InboxService
        from backend.modules.inbox.enrich import LinkEnricher
        from backend.modules.inbox.worker import InboxWorker

        registry.inbox = InboxService(
            db, access=registry.access, queue=registry.job_queue, files=registry.files,
            timezone_name=registry.settings.project_timezone,
        )
        registry.inbox_worker = InboxWorker(
            registry.inbox, registry.job_queue, LinkEnricher()
        )

    # 4) runtime（Hermes 构造/工具基座，不启动 run worker）
    if registry.runtime is None and registry.settings.hermes_enabled:
        from backend.runtime.hermes.adapter import HermesRuntimeAdapter

        registry.runtime = HermesRuntimeAdapter(
            hermes_home=registry.settings.artifacts_dir / "hermes",
            usage=registry.usage, models=registry.models,
        )
        await registry.runtime.startup()

    if registry.runtime is not None:
        # Hermes 自带 ddgs 插件缺 plugin.yaml，不会被自动发现；显式注册，
        # 否则只装 ddgs 包时 web_search 仍会报“没有搜索 Provider”。
        from backend.integrations.search import ensure_ddgs_provider

        ensure_ddgs_provider()

    # 5) 记忆服务/worker（capture 读取 assistant 的只读投影，不依赖 repository）
    if registry.access is not None:
        from backend.integrations.llm import OpenAICompatibleTextGenerator
        from backend.modules.memory.api import MemoryService
        from backend.modules.memory.worker import MemoryWorker

        registry.memory = MemoryService(
            db, access=registry.access, queue=registry.job_queue
        )
        memory_generator = (
            OpenAICompatibleTextGenerator(models=registry.models, usage=registry.usage)
            if registry.models is not None else None
        )
        from backend.modules.assistant.transcript import load_run_messages

        # channels 晚于 memory 装配：provider 运行期解析(registry 为可变对象)
        _confirm_writer = make_memory_confirm(
            db, registry,
            lambda owner_id, session_id: (
                registry.channels.make_session_target_provider()(owner_id, session_id)
                if registry.channels is not None else None
            ),
        )
        registry.memory_worker = MemoryWorker(
            registry.memory, registry.job_queue,
            message_loader=lambda owner_id, run_id: load_run_messages(
                db, owner_id, run_id
            ),
            generator=memory_generator,
            confirm_writer=_confirm_writer,
        )

    # 6) assistant 只构造，不 start；依赖已在构造函数注入
    if registry.runtime is not None and registry.access is not None:
        from backend.modules.assistant.api import AssistantService

        registry.assistant = AssistantService(
            db, runtime=registry.runtime, models=registry.models,
            access=registry.access,
            on_run_finished=_make_run_finished(registry),
            profiles=registry.profiles,
            memory=registry.memory,
        )

    # 7) 投递/调度先装配：渠道发送器用 provider 延迟解析，避免先构造渠道再回填。
    if registry.access is not None:
        from backend.modules.delivery.api import (
            CompositeDeliverySender,
            DeliveryService,
        )
        from backend.modules.delivery.reports import ReportService
        from backend.modules.delivery.wechat import (
            DisabledDeliverySender,
            WeChatTextSender,
        )
        from backend.modules.delivery.worker import DeliveryWorker
        from backend.modules.scheduling.api import SchedulingService
        from backend.modules.scheduling.scheduler import Scheduler

        if registry.settings.encryption_secret:
            from backend.modules.delivery.smtp import EmailService, SmtpEmailSender

            registry.email = EmailService(
                db, access=registry.access,
                encryption_secret=registry.settings.encryption_secret,
            )

        smtp_sender: SmtpEmailSender | None = None
        senders: list[Any] = []
        if registry.email is not None:
            smtp_sender = SmtpEmailSender(registry.email)
            senders.append(smtp_sender)
            # 确认邮件走同一发送器（审计 #4：注册≠可信，地址须逐个确认所有权）
            registry.email.confirmation_sender = smtp_sender
        if registry.settings.wechat_enabled:
            # ChannelService 尚未构造；发送时才解析，启动顺序不再靠回填字段。
            senders.append(WeChatTextSender(lambda: registry.channels))
        sender = (
            CompositeDeliverySender(senders)
            if senders else DisabledDeliverySender()
        )
        registry.delivery = DeliveryService(
            db, sender=sender, on_sent=_make_delivery_sent(registry),
            email_recipient_check=(
                registry.email.is_recipient_allowed
                if registry.email is not None else None
            ),
        )
        registry.delivery_worker = DeliveryWorker(registry.delivery)
        registry.scheduling = SchedulingService(
            db, delivery=registry.delivery, access=registry.access,
            timezone_name=registry.settings.project_timezone,
            queue=registry.job_queue,
            # 简报不依赖微信绑定：邮箱目标同样可以创建/发送。
            briefing_enabled=bool(registry.profiles and registry.job_queue),
        )
        registry.scheduler = Scheduler(registry.scheduling)

        # 简报服务：模板兜底；LLM 只做受控润色，失败不影响投递。
        if registry.profiles is not None and registry.job_queue is not None:
            from backend.integrations.llm import OpenAICompatibleTextGenerator
            from backend.integrations.news import NewsService
            from backend.modules.briefing.api import BriefingService

            generator = (
                OpenAICompatibleTextGenerator(
                    models=registry.models, usage=registry.usage
                )
                if registry.models is not None else None
            )
            registry.briefing = BriefingService(
                access=registry.access,
                scheduling=registry.scheduling,
                profiles=registry.profiles,
                inbox=registry.inbox,
                news=NewsService(
                    generator=generator,
                    display_timezone=registry.settings.project_timezone,
                ),
                generator=generator,
            )

        # 7.5) 超级代理服务：命令装配前构造（/开发 命令族需要）；worker 在 9.5 接 runtime
        if registry.superagent is None:
            from backend.modules.superagent.api import SuperagentService

            registry.superagent = SuperagentService(
                db, access=registry.access,
                delivery=registry.delivery,
                channels=None,  # 回执目标在受理时快照，发送不经此引用
                timezone=registry.settings.project_timezone,
            )
            registry.superagent.set_encryption_secret(
                str(registry.settings.encryption_secret or "")
            )

        # 命令处理器只依赖窄接口；在渠道构造前完成，渠道不再晚绑定 commands。
        from backend.modules.channels.commands import CommandServices, WeChatCommands

        command_services = CommandServices(
            profiles=registry.profiles,
            memory=registry.memory,
            ledger=registry.ledger,
            scheduling=registry.scheduling,
            inbox=registry.inbox,
            superagent=(
                _make_superagent_intake(registry.superagent)
                if registry.superagent is not None else None
            ),
            target_for_owner=lambda owner_id: (
                registry.channels.delivery_target_for_owner(owner_id)
                if registry.channels is not None else None
            ),
        )

        # 8) 渠道只构造，不监听（监听必须晚于 delivery/assistant 启动）
        if (
            registry.settings.wechat_enabled
            and registry.assistant is not None
            and registry.access is not None
        ):
            secret = str(registry.settings.encryption_secret or "")
            if secret:
                from backend.integrations.speech import build_stt
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
                    stt=(
                        build_stt(registry.settings, registry.models)
                        if registry.settings.voice_enabled else None
                    ),
                    voice_echo=registry.settings.voice_echo,
                    commands=WeChatCommands(command_services),
                )
            else:
                logger.warning(
                    "EASYCHAT_WECHAT_ENABLED=true 但未设置 EASYCHAT_ENCRYPTION_SECRET，"
                    "渠道模块保持关闭（不会以明文保存 bot token）"
                )

        # 9) 依赖渠道的 worker（渠道可能为空，邮箱/显式目标仍可用）
        # 渠道来源查询晚绑定给 assistant（ToolContext 携带微信回执地址）
        if registry.assistant is not None:
            if registry.channels is not None:
                registry.assistant.set_source_for_session(
                    registry.channels.source_route_for_session
                )
            elif registry.superagent is not None:
                registry.assistant.set_source_for_session(lambda session_id: None)
        if registry.profiles is not None:
            from backend.modules.profiles.worker import MoodWorker

            registry.mood_worker = MoodWorker(
                registry.profiles, registry.job_queue,
                delivery=registry.delivery, channels=registry.channels,
            )
        if registry.briefing is not None and registry.profiles is not None:
            from backend.modules.briefing.worker import BriefingWorker

            registry.briefing_worker = BriefingWorker(
                registry.briefing, registry.job_queue, registry.delivery,
                access=registry.access, channels=registry.channels,
                profiles=registry.profiles,
            )
        if registry.delivery is not None:
            from backend.integrations.pdf import build_pdf_renderer

            registry.report = ReportService(
                delivery=registry.delivery, renderer=build_pdf_renderer(registry.settings),
                artifacts_dir=registry.settings.artifacts_dir,
            )

    # 9.5) 超级代理 worker：服务已在 7.5 构造；这里接 runtime（步骤 12 启动）
    if registry.superagent is not None and registry.runtime is not None:
        registry.superagent.set_run_canceller(registry.runtime.cancel)
        registry.superagent.runner_ready = True
        from backend.modules.superagent.runner import HermesCodingRunner
        from backend.modules.superagent.webhooks import WebhookService
        from backend.modules.superagent.worker import SuperagentWorker

        webhook_service = WebhookService(
            db, superagent=registry.superagent, queue=registry.job_queue,
            webhook_secret=str(registry.settings.github_webhook_secret or ""),
        )
        registry.superagent_worker = SuperagentWorker(
            registry.superagent,
            runner=HermesCodingRunner(registry.runtime),
            delivery=registry.delivery,
            channels_provider=lambda: registry.channels,
            workspace_root=registry.settings.artifacts_dir / "superagent",
            artifacts_root=registry.settings.artifacts_dir / "superagent_verify",
            timezone=registry.settings.project_timezone,
            job_queue=registry.job_queue,
            webhook_service=webhook_service,
        )
        registry.superagent_webhooks = webhook_service

    # 10) 业务工具（提醒/账本/收件箱）必须在 assistant.start 前注册
    if registry.runtime is not None:
        from backend.bootstrap_tools import extra_tools

        registered = registry.runtime.register_extra_tools(extra_tools(registry))
        logger.info("额外业务工具注册数: %s", registered)

    # 11) 启动 assistant worker（此后才允许 finish run）
    if registry.assistant is not None:
        await registry.assistant.start()

    # 12) 启动后台 workers 与调度器
    if registry.ledger_worker is not None:
        await registry.ledger_worker.start()
    if registry.delivery_worker is not None:
        await registry.delivery_worker.start()
    if registry.memory_worker is not None:
        await registry.memory_worker.start()
    if registry.mood_worker is not None:
        await registry.mood_worker.start()
    if registry.briefing_worker is not None:
        await registry.briefing_worker.start()
    if registry.inbox_worker is not None:
        await registry.inbox_worker.start()
    if registry.superagent_worker is not None:
        await registry.superagent_worker.start()
    if registry.scheduler is not None:
        await registry.scheduler.start()

    # 13) 最后启动渠道监听，保证入站消息看到的依赖全部就绪
    if registry.channels is not None:
        await registry.channels.start_listeners()

    # 14) 技能/学习（依赖 assistant 消息与 memory）
    if registry.access is not None:
        from backend.modules.skills.api import SkillService

        registry.skills = SkillService(
            db, access=registry.access,
            content_root=registry.settings.artifacts_dir / "skills",
        )

        from backend.modules.evolution.api import EvolutionService
        from backend.modules.evolution.budget import BudgetManager
        from backend.modules.evolution.worker import EvolutionWorker

        registry.evolution = EvolutionService(
            db, access=registry.access, queue=registry.job_queue,
            budget=BudgetManager(
                db, timezone_name=registry.settings.project_timezone,
            ),
        )
        registry.evolution_worker = EvolutionWorker(registry.evolution, registry.job_queue)
        await registry.evolution_worker.start()

        from backend.modules.evolution.adoption import AdoptionService

        registry.adoption = AdoptionService(db, registry.skills)
    # WP-C：assistant 先于 skills 装配，此处晚绑定技能快照入口。
    if registry.assistant is not None and registry.skills is not None:
        registry.assistant.set_skills(registry.skills)


def make_memory_confirm(db, registry=None, target_provider=None):
    """WP-D：显式记忆写入后的确认——会话内 assistant 消息 + 渠道回执(双通道)。

    独立事务；失败不回滚记忆(已持久化)，由 worker 记录明确原因。
    渠道回执仅在原会话为 wechat 且绑定仍活跃时发送；dedup 键 run 级,不双发。
    """
    from backend.platform.sqlite import utc_now_iso

    def _confirm(owner_id: int, run_id: str, text: str) -> None:
        conn = db.connect()
        try:
            run_row = conn.execute("SELECT session_id FROM runs WHERE id=?", (run_id,)).fetchone()
        finally:
            conn.close()
        if run_row is None:
            return
        session_id = str(run_row["session_id"])
        now = utc_now_iso()
        with db.transaction() as tx:
            cur = tx.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM conversations"
                " WHERE session_id=? AND run_id=?",
                (session_id, run_id),
            )
            seq = int(cur.fetchone()[0])
            tx.execute(
                "INSERT INTO conversations(session_id, owner_id, run_id, role, content,"
                " status, chat_mode, source, seq, created_at, updated_at)"
                " VALUES(?,?,?, 'assistant', ?, 1, 'normal', 'system', ?, ?, ?)",
                (session_id, owner_id, run_id, text, seq, now, now),
            )
        # 渠道回执:原微信指令必须有微信侧回应(缺陷①闭环)
        if target_provider is not None and registry is not None and registry.delivery is not None:
            target = target_provider(owner_id, session_id)
            if target is not None:
                from backend.modules.delivery.contracts import target_from_channel

                with db.transaction() as tx:
                    registry.delivery.enqueue_in_transaction(
                        tx, owner_id=owner_id, target=target_from_channel(target),
                        text=text, dedup_key=f"memory-confirm:{run_id}",
                        source="memory",
                    )

    return _confirm


def _make_superagent_intake(service: Any):
    """命令层只拿窄入口（/开发 /任务 /补充 /取消 /重试）。"""
    from backend.modules.superagent.intake import SuperagentIntake

    return SuperagentIntake(service)


def _make_care_canceller(registry: ModuleRegistry):
    """构造期注入稳定回调；delivery 在之后装配，调用时再解析。"""

    def cancel(owner_id: int) -> int:
        if registry.delivery is None:
            return 0
        return registry.delivery.cancel_unsent(
            owner_id, source="care",
            reason="用户删除/关闭情绪或降低主动性，取消关怀",
        )

    return cancel


def _make_delivery_sent(registry: ModuleRegistry):
    """投递真正 sent 后回调；care 只在这里写 last_care_at/日志，入队不算成功。"""

    def on_sent(delivery: dict[str, Any]) -> None:
        if str(delivery.get("source") or "") != "care":
            return
        if registry.profiles is None:
            return
        owner_id = int(delivery.get("owner_id") or 0)
        care_key = str(delivery.get("dedup_key") or "")
        if owner_id <= 0 or not care_key.startswith(f"mood-care:{owner_id}:"):
            return
        registry.profiles.mark_care_sent(
            owner_id,
            care_key=care_key,
            delivery_created_at=str(delivery.get("created_at") or ""),
        )

    return on_sent


def _make_run_finished(registry: ModuleRegistry):
    """run 终态与投递请求同事务：先取已落库的最终回复，再入队。"""

    def on_run_finished(conn, run) -> None:
        # 显式记忆捕获与平台无关，必须在投递条件之前；失败不能静默吞掉，
        # 否则 run 终态与 job 会不一致（同一事务由调用方回滚）。
        if registry.memory_worker is not None:
            registry.memory_worker.enqueue_capture_tx(conn, run)

        messages: list[dict[str, Any]] = []
        if registry.assistant is not None:
            messages = registry.assistant.messages_for_run_tx(
                conn, int(run["owner_id"]), str(run["id"])
            )
        user_text = next(
            (
                str(item.get("content") or "") for item in messages
                if item.get("role") == "user" and str(item.get("content") or "").strip()
            ),
            "",
        )

        # 情绪采样只入队，不在 run 终态事务里写另一张业务表。
        # 失败/取消/超时 run 不进入情绪统计；日期用完成时间而非创建时间。
        if (
            registry.profiles is not None
            and registry.job_queue is not None
            and str(run.get("status") or "") == "completed"
            and str(run.get("source") or "") in ("web", "wechat")
            and user_text.strip()
        ):
            from datetime import datetime
            from zoneinfo import ZoneInfo

            context = registry.profiles.mood_context_tx(conn, int(run["owner_id"]))
            opted_in, tz_name = context if context is not None else (False, "")
            if opted_in:
                try:
                    finished = datetime.fromisoformat(
                        str(run.get("finished_at") or run.get("created_at") or "")
                    )
                    local_date = finished.astimezone(ZoneInfo(tz_name)).date().isoformat()
                except (TypeError, ValueError):
                    local_date = datetime.now(ZoneInfo(tz_name)).date().isoformat()
                registry.job_queue.enqueue_tx(
                    conn,
                    kind="mood.sample",
                    dedup_key=f"mood:{run['id']}",
                    payload={
                        "owner_id": int(run["owner_id"]),
                        "run_id": str(run["id"]),
                        "text": user_text[:2000],
                        "date": local_date,
                    },
                    owner_id=int(run["owner_id"]),
                )

        if (
            registry.channels is None
            or registry.delivery is None
            or str(run.get("source") or "") != "wechat"
        ):
            return
        target = registry.channels.delivery_target_for_run(run)
        if not target:
            return
        final_reply = ""
        for item in messages:
            if item.get("role") == "assistant" and str(item.get("content") or "").strip():
                final_reply = str(item.get("content") or "")
        if not final_reply:
            # WP-D：失败/取消/中断/空回复补可读终态反馈（此前静默丢弃，
            # 用户在微信侧表现为"发消息无回应"）。dedup 键沿用 run 级，
            # 重复终态不会双发。
            status = str(run.get("status") or "")
            if status == "failed":
                detail = str(run.get("error") or "").strip()
                final_reply = (f"这个任务这次没有完成：{detail[:80]}"
                               if detail else "这个任务这次没有完成，请稍后重试或换一种说法。")
            elif status == "cancelled":
                final_reply = "已按你的要求停止本次回答。"
            elif status == "interrupted":
                final_reply = "服务中断导致这次回答未完成，请重新发送需求。"
            elif status == "completed":
                final_reply = "这次没有产生可发送的回复，请重试或补充说明。"
            else:
                return
        from backend.modules.delivery.contracts import target_from_channel

        registry.delivery.enqueue_run_in_transaction(
            conn, run, target_from_channel(target), final_reply,
        )

    return on_run_finished


async def run_shutdown(registry: ModuleRegistry) -> None:
    """lifespan 关闭序列：停止接收→停任务→关Runtime→最终刷计量→释放连接。

    后续任务按逆序补充；整个流程保持幂等。
    """
    # 先停监听器，避免 shutdown 期间继续把消息标 processed 却不再执行。
    if registry.channels is not None:
        await registry.channels.aclose()
    # 再等 in-flight run 结束：它的 on_run_finished 仍需要 memory/ledger/delivery/job_queue。
    # 这些模块必须等 assistant 关闭后才能置 None，否则 run 会 completed 但回答被静默丢弃。
    if registry.assistant is not None:
        await registry.assistant.aclose()
        registry.assistant = None
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
    if registry.ledger_worker is not None:
        await registry.ledger_worker.stop()
        registry.ledger_worker = None
    if registry.ledger is not None:
        registry.ledger = None
    if registry.mood_worker is not None:
        await registry.mood_worker.stop()
        registry.mood_worker = None
    if registry.profiles is not None:
        registry.profiles = None
    if registry.scheduler is not None:
        await registry.scheduler.stop()
        registry.scheduler = None
    if registry.briefing_worker is not None:
        await registry.briefing_worker.stop()
        registry.briefing_worker = None
    if registry.briefing is not None:
        registry.briefing = None
    if registry.inbox_worker is not None:
        await registry.inbox_worker.stop()
        registry.inbox_worker = None
    if registry.inbox is not None:
        registry.inbox = None
    if registry.superagent_worker is not None:
        await registry.superagent_worker.stop()
        registry.superagent_worker = None
    if registry.superagent is not None:
        registry.superagent = None
    if registry.superagent_webhooks is not None:
        registry.superagent_webhooks = None
    if registry.delivery_worker is not None:
        await registry.delivery_worker.stop()
        registry.delivery_worker = None
    if registry.delivery is not None:
        registry.delivery = None
    if registry.scheduling is not None:
        registry.scheduling = None
    # 共享 JobQueue 持有旧 Database；不释放会让下一次 lifespan 的 worker
    # 拿到已关闭连接。
    registry.job_queue = None
    if registry.channels is not None:
        registry.channels = None
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
