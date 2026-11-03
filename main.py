"""
AgentForge - 通用 Hermes Agent 脚手架

基于 eyes-agent 的 Hermes 集成模式，抽象出通用的 AI Agent 服务框架。
用于快速搭建基于 Hermes 的智能体应用。

启动方式：
    python main.py              # 开发模式（端口 8001）
    python main.py start 8080   # 指定端口
"""
import sys
from pathlib import Path

# Add Hermes to Python path
project_root = Path(__file__).parent
hermes_path = project_root / "backend" / "hermes"
if str(hermes_path) not in sys.path:
    sys.path.insert(0, str(hermes_path))

import logging
import os
import warnings
from contextlib import asynccontextmanager

from fastapi.middleware.cors import CORSMiddleware

# Windows 控制台编码修复
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")
    os.environ["PYTHONIOENCODING"] = "utf-8"

warnings.filterwarnings('ignore', message='.*non-interactive.*')

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.utils.port_killer import kill_port
from backend.utils.log_utils import log as logger

# 日志配置已统一到 backend/utils/log_utils.py（InterceptHandler 桥接 + loguru 管控）
# 不再使用 logging.basicConfig，避免覆盖 InterceptHandler

# 加载环境变量
load_dotenv(override=True)

# 全局标志
_initialized = False
_app_instance = None


def create_app():
    """创建并配置 FastAPI 应用"""
    global _initialized, _app_instance

    if _app_instance is not None:
        logger.info("🔄 返回已存在的应用实例...")
        return _app_instance

    logger.info("🚀 AgentForge 开始初始化...")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # startup
        import asyncio
        from backend.controller import stream_runner
        app.state._run_sweeper_task = asyncio.create_task(stream_runner.run_periodic_sweep())

        # ── 平台渠道网关（微信为第一适配器，统一启停；飞书/企微后续注册） ──
        try:
            from backend.service.platform_gateway import gateway as _pgw
            _pgw.start()
        except Exception as e:
            logger.warning(f"平台网关启动跳过: {e}")
        
        # ── 后台任务启动 ──
        _bg_tasks = []
        
        # 微信缓存清理任务
        try:
            from backend.controller.wechat.cleanup import cleanup_wechat_caches
            app.state._wechat_cleanup_task = asyncio.create_task(cleanup_wechat_caches())
            _bg_tasks.append("微信缓存清理(5m)")
        except Exception as e:
            logger.warning(f"微信缓存清理任务启动跳过: {e}")
        
        # 聊天缓存清理任务
        try:
            from backend.controller.chat_cleanup import cleanup_chat_caches
            from backend.controller.conversation_controller import chat_histories, _cancelled_threads
            from backend.controller.chat.stream import completed_threads
            app.state._chat_cleanup_task = asyncio.create_task(
                cleanup_chat_caches(chat_histories, _cancelled_threads, completed_threads)
            )
            _bg_tasks.append("聊天缓存清理(5m)")
        except Exception as e:
            logger.warning(f"聊天缓存清理任务启动跳过: {e}")

        # Trace 数据周期清理
        try:
            from backend.service.trace.trace_service import cleanup_old_traces

            async def _trace_cleanup_loop():
                while True:
                    await asyncio.sleep(24 * 3600)  # 每天一次
                    try:
                        cleaned = await asyncio.to_thread(cleanup_old_traces)
                        if cleaned:
                            logger.info(f"🧹 Trace 周期清理: {cleaned} 条过期记录已删除")
                    except Exception as e:
                        logger.warning(f"⚠️ Trace 周期清理失败: {e}")

            app.state._trace_cleanup_task = asyncio.create_task(_trace_cleanup_loop())
            _bg_tasks.append("Trace清理(24h)")
        except Exception as e:
            logger.warning(f"⚠️ Trace 周期清理任务启动跳过: {e}")

        # 上传附件 TTL 清理任务
        try:
            from backend.controller.chat_cleanup import cleanup_upload_files
            app.state._upload_cleanup_task = asyncio.create_task(cleanup_upload_files())
            _bg_tasks.append("附件清理(6h)")
        except Exception as e:
            logger.warning(f"⚠️ 上传附件清理任务启动跳过: {e}")

        # 定时任务调度器
        try:
            from backend.service.cron.cron_service import cron_service
            restored = cron_service.restore_jobs_from_db()
            if restored > 0:
                _bg_tasks.append(f"定时任务({restored}个)")
        except Exception as e:
            logger.warning(f"定时任务调度器启动跳过: {e}")

        # RAG 评测闭环
        try:
            from backend.service.kb.kb_eval_suggestion import run_suggestion_cycle

            _suggestion_interval = int(os.getenv("KB_EVAL_SUGGESTION_RUNNER_SECONDS", "600") or 600)
            _suggestion_interval = max(30, _suggestion_interval)

            async def _suggestion_cycle_loop():
                import asyncio as _aio
                while True:
                    await _aio.sleep(_suggestion_interval)
                    try:
                        await _aio.to_thread(run_suggestion_cycle)
                    except Exception as e:
                        logger.warning(f"⚠️ RAG 建议周期维护失败: {e}")

            app.state._suggestion_cycle_task = asyncio.create_task(_suggestion_cycle_loop())
            _bg_tasks.append(f"RAG评测({int(_suggestion_interval/60)}m)")
        except Exception as e:
            logger.warning(f"⚠️ RAG 建议周期维护启动跳过: {e}")

        # ── Hermes 预热：把核心模块导入、插件发现、项目工具注册、工具定义缓存等
        #    冷启动开销从首次用户请求转移到应用启动阶段，首次会话延迟大幅降低 ──
        try:
            from backend.hermes_adapter import prewarm_hermes
            prewarm_hermes()
        except Exception as _pw_exc:
            logger.warning(f"⚠️ Hermes 预热失败（不阻断启动）: {_pw_exc}")

        # ── 后台任务汇总 ──
        if _bg_tasks:
            logger.info(f"🔄 后台任务已启动: {', '.join(_bg_tasks)}")

        yield
        # shutdown
        _stopped = []
        task = getattr(app.state, "_run_sweeper_task", None)
        if task is not None:
            task.cancel()
            _stopped.append("RunRegistry")
        
        wechat_cleanup = getattr(app.state, "_wechat_cleanup_task", None)
        if wechat_cleanup is not None:
            wechat_cleanup.cancel()
            _stopped.append("微信缓存")

        trace_cleanup = getattr(app.state, "_trace_cleanup_task", None)
        if trace_cleanup is not None:
            trace_cleanup.cancel()
            _stopped.append("Trace清理")

        upload_cleanup = getattr(app.state, "_upload_cleanup_task", None)
        if upload_cleanup is not None:
            upload_cleanup.cancel()
            _stopped.append("上传清理")

        suggestion_cycle = getattr(app.state, "_suggestion_cycle_task", None)
        if suggestion_cycle is not None:
            suggestion_cycle.cancel()
            _stopped.append("RAG评测")

        if _stopped:
            logger.info(f"🛑 后台任务已停止: {', '.join(_stopped)}")

        # 停止 GraphRAG 提取线程池
        try:
            from backend.service.graph.extractor_pool import stop_extractor_pool
            stop_extractor_pool()
        except Exception:
            pass

        # 关闭定时任务调度器
        try:
            from backend.service.cron.cron_service import cron_service
            cron_service.shutdown()
        except Exception:
            pass

        # 停止平台渠道网关
        try:
            from backend.service.platform_gateway import gateway as _pgw_stop
            _pgw_stop.stop()
        except Exception:
            pass

    # 创建 FastAPI 应用
    app = FastAPI(
        title="AgentForge - Hermes Agent Scaffold",
        description="通用 Hermes Agent 脚手架，快速搭建智能体应用",
        version="1.0.0",
        lifespan=lifespan
    )

    # 配置 CORS
    allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-New-Token"],
    )

    # SPA history 模式 fallback - 使用中间件拦截 404 响应
    # 对于非 API 路由的 404 响应，返回 index.html，让前端 Vue Router 处理路由
    from starlette.responses import FileResponse as StarletteFileResponse
    
    @app.middleware("http")
    async def spa_fallback_middleware(request, call_next):
        response = await call_next(request)
        if response.status_code == 404:
            path = request.url.path
            # 不拦截 API 路由、静态资源、健康检查、文档等
            if not path.startswith(("/api/", "/health", "/docs", "/openapi.json", "/redoc", "/assets/", "/static/")):
                # 检查是否设置了 SPA index path
                if hasattr(request.app.state, "spa_index_path"):
                    logger.info(f"SPA middleware: returning index.html for {path}")
                    return StarletteFileResponse(request.app.state.spa_index_path)
                else:
                    logger.warning("SPA middleware: spa_index_path not set")
        return response

    # 配置 API 限流（slowapi）
    try:
        from slowapi.errors import RateLimitExceeded
        from slowapi import _rate_limit_exceeded_handler
        from backend.utils.rate_limit import limiter
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        logger.info("✅ API 限流已启用（默认 120/分钟）")
    except Exception as e:
        logger.warning(f"⚠️ API 限流启用失败: {e}")

    # 健康检查（深度检查 DB / 连接池 / LLM 配置）
    @app.get("/health", include_in_schema=False)
    async def health_check():
        import time as _time

        result = {
            "status": "healthy",
            "service": "agentforge",
            "timestamp": _time.time(),
            "checks": {},
        }

        # ── 数据库连接检查 ──
        db_status = "unhealthy"
        db_detail = ""
        try:
            from backend.db.schema import get_conn
            conn = get_conn()
            try:
                cur = conn.execute("SELECT 1 AS ok")
                rows = cur.fetchall() if hasattr(cur, "fetchall") else []
                if rows:
                    db_status = "healthy"
            finally:
                conn.close()
        except Exception as e:
            db_detail = str(e)
        result["checks"]["database"] = {"status": db_status, "detail": db_detail}

        # ── 连接池状态 ──
        pool_status = "healthy"
        pool_detail = ""
        try:
            from backend.db.connection_pool import get_pool_stats
            stats = get_pool_stats()
            if stats is None:
                pool_status = "unhealthy"
                pool_detail = "连接池未初始化"
            else:
                pool_detail = stats
        except Exception as e:
            pool_status = "unhealthy"
            pool_detail = str(e)
        result["checks"]["connection_pool"] = {"status": pool_status, "detail": pool_detail}

        # ── LLM 配置检查 ──
        llm_status = "healthy"
        llm_detail = ""
        try:
            from backend.controller.agent_controller import get_current_model_config
            llm_cfg = get_current_model_config(1)
            if not llm_cfg or not llm_cfg.get("api_key"):
                llm_status = "degraded"
                llm_detail = "未配置 LLM API Key"
            else:
                llm_detail = {"model": llm_cfg.get("model_name", "unknown")}
        except Exception as e:
            llm_status = "unhealthy"
            llm_detail = str(e)
        result["checks"]["llm"] = {"status": llm_status, "detail": llm_detail}

        # ── Milvus 向量库检查 ──
        milvus_status = "degraded"
        milvus_detail = ""
        try:
            from backend.infrastructure import get_infrastructure
            infra = get_infrastructure()
            if infra.is_memory_available():
                milvus_status = "healthy"
                milvus_detail = infra.milvus.status
            else:
                milvus_detail = "向量库不可用（记忆功能降级）"
        except Exception as e:
            milvus_detail = str(e)
        result["checks"]["milvus"] = {"status": milvus_status, "detail": milvus_detail}

        # ── Neo4j 图数据库检查 ──
        neo4j_status = "degraded"
        neo4j_detail = ""
        try:
            from backend.infrastructure import get_infrastructure
            infra = get_infrastructure()
            if infra.is_graphrag_available():
                neo4j_status = "healthy"
                neo4j_detail = infra.neo4j.status
            else:
                neo4j_detail = "图数据库不可用（GraphRAG 功能跳过）"
        except Exception as e:
            neo4j_detail = str(e)
        result["checks"]["neo4j"] = {"status": neo4j_status, "detail": neo4j_detail}

        # ── Redis 缓存检查 ──
        redis_status = "degraded"
        redis_detail = ""
        try:
            from backend.infrastructure import get_infrastructure
            infra = get_infrastructure()
            if infra.is_cache_available():
                redis_status = "healthy"
                cache = infra.redis
                redis_detail = cache.stats()
            else:
                redis_detail = "Redis 不可用（缓存降级到进程内 LRU）"
        except Exception as e:
            redis_detail = str(e)
        result["checks"]["redis"] = {"status": redis_status, "detail": redis_detail}

        # ── 汇总状态 ──
        statuses = [c["status"] for c in result["checks"].values()]
        if "unhealthy" in statuses:
            result["status"] = "unhealthy"
        elif "degraded" in statuses:
            result["status"] = "degraded"

        return result

    # 构建指纹端点（版本取证）
    @app.get("/version", include_in_schema=False)
    async def version_info():
        try:
            from backend.build_info import BUILD_INFO
            return BUILD_INFO
        except Exception:
            return {"commit": "unknown", "branch": "unknown", "build_time": None, "dirty": None}

    # 自动注册所有控制器
    from backend.controller import register_all_routers
    register_all_routers(app)
    
    # 特殊处理：聊天控制器（需要 create_controller 函数）
    from backend.controller.chat_controller import create_controller
    create_controller(app)
    logger.info("✅ Chat controller 已注册")

    # ── 数据库初始化 ──
    try:
        from backend.db.schema import init_db
        init_db()
        # 清理过期 trace 数据
        from backend.service.trace.trace_service import cleanup_old_traces
        cleaned = cleanup_old_traces()
        if cleaned:
            logger.info(f"🧹 Trace 数据清理: {cleaned} 条过期记录已删除")
    except Exception as e:
        logger.warning(f"⚠️ 数据库初始化失败: {e}")

    # ── 权限定义播种 ──
    try:
        from backend.permission import register_all_builtin_permissions, seed_to_db
        register_all_builtin_permissions()
        seed_to_db()
        logger.info("✅ 权限定义已同步到数据库")
    except Exception as e:
        logger.warning(f"⚠️ 权限播种失败: {e}")

    # ── 基础设施初始化（Milvus/Neo4j）──
    try:
        from backend.infrastructure import init_infrastructure
        infra_status = init_infrastructure()
        
        # 组件状态图标
        mysql_icon = "✅" if infra_status.is_mysql_available() else "❌"
        milvus_icon = "✅" if infra_status.is_milvus_available() else "⚠️"
        neo4j_icon = "✅" if infra_status.is_neo4j_available() else "⚠️"
        redis_icon = "✅" if infra_status.is_redis_available() else "⚠️"

        logger.info(
            f"\n"
            f"╔══════════════════════════════════════════════════════════════╗\n"
            f"║  🔧 基础设施                                                   ║\n"
            f"╠══════════════════════════════════════════════════════════════╣\n"
            f"║  {mysql_icon} MySQL:   {'可用' if infra_status.is_mysql_available() else '不可用':<46} ║\n"
            f"║  {milvus_icon} Milvus: {'可用 (向量存储)' if infra_status.is_milvus_available() else '不可用 → 降级 ChromaDB':<40} ║\n"
            f"║  {neo4j_icon} Neo4j:  {'可用 (知识图谱)' if infra_status.is_neo4j_available() else '不可用 → GraphRAG 降级':<40} ║\n"
            f"║  {redis_icon} Redis:  {'可用 (缓存层)' if infra_status.is_redis_available() else '不可用 → 降级本地缓存':<40} ║\n"
            f"╚══════════════════════════════════════════════════════════════╝"
        )
        
        if not infra_status.is_mysql_available():
            logger.warning(f"⚠️ 基础设施初始化异常: {infra_status.error}")
    except Exception as e:
        logger.warning(f"⚠️ 基础设施初始化跳过: {e}")

    # ── 记忆系统状态检查 ──
    try:
        from backend.memory.agentforge_provider import AgentForgeMemoryProvider
        from backend.memory.graph_memory import get_graph_memory
        from backend.memory.consolidator import get_consolidator
        
        _provider = AgentForgeMemoryProvider()
        _provider_available = _provider.is_available()
        
        _graph_mem = get_graph_memory()
        _graph_available = _graph_mem._available() if _graph_mem else False
        
        _consolidator = get_consolidator()
        _consolidator_available = _consolidator is not None
        
        # 记忆统计
        memory_stats = {"total": 0, "types": {}}
        try:
            # 本函数后面（RAG 检查段）也有 `from backend.db.schema import get_conn`，
            # 那会让 get_conn 成为**整个 create_app 的局部名** → 此处若先引用就会
            # UnboundLocalError（被下面的 except 吞掉，启动横幅的记忆统计永远是 0）。
            # 因此必须在这里先绑定，而不是把 import 提到函数开头（那会改变模块加载顺序）。
            from backend.db.schema import get_conn
            conn = get_conn()
            cur = conn.execute(
                "SELECT COUNT(*) AS cnt FROM memory_episodic WHERE deleted_at IS NULL"
            )
            episodic_cnt = cur.fetchone()["cnt"] if hasattr(cur, "fetchone") else 0
            cur = conn.execute(
                "SELECT COUNT(*) AS cnt FROM memory_semantic WHERE deleted_at IS NULL"
            )
            semantic_cnt = cur.fetchone()["cnt"] if hasattr(cur, "fetchone") else 0
            memory_stats["total"] = episodic_cnt + semantic_cnt
            memory_stats["types"] = {"episodic": episodic_cnt, "semantic": semantic_cnt}
            conn.close()
        except Exception:
            pass
        
        # 构建状态描述
        components = []
        if _provider_available:
            components.append("MySQL")
            components.append("向量库")
        if _graph_available:
            components.append("图增强")
        if _consolidator_available:
            components.append("三阶段合并")
        
        type_str = " | ".join([f"{k}:{v}" for k, v in memory_stats["types"].items()]) if memory_stats["types"] else "无"
        
        logger.info(
            f"\n"
            f"╔══════════════════════════════════════════════════════════════╗\n"
            f"║  🧠 记忆系统                                                   ║\n"
            f"╠══════════════════════════════════════════════════════════════╣\n"
            f"║  状态: {'✅ 完整就绪' if _provider_available and _graph_available else ('⚠️ 基本就绪' if _provider_available else '❌ 不可用'):<48} ║\n"
            f"║  组件: {' + '.join(components) if components else '无':<48} ║\n"
            f"╠────────────────────────────────────────────────────────────────╣\n"
            f"║  记忆统计: {memory_stats['total']} 条{'':<44} ║\n"
            f"║  类型分布: {type_str:<45} ║\n"
            f"╚══════════════════════════════════════════════════════════════╝"
        )
    except Exception as e:
        logger.warning(f"⚠️ 记忆系统状态检查失败: {e}")
    
    # ── 记忆一致性架构启动（Outbox Worker + Reconciler）──
    try:
        from backend.service.memory.outbox_worker import start_outbox_worker
        from backend.service.memory.reconciler import start_reconciler
        
        start_outbox_worker()
        start_reconciler()
        logger.info("✅ 记忆一致性组件已启动 (Outbox Worker + Reconciler)")
    except Exception as e:
        logger.warning(f"⚠️ 记忆一致性组件启动失败: {e}")
    
    # ── GraphRAG 提取线程池 ──
    try:
        from backend.service.graph.extractor_pool import start_extractor_pool
        start_extractor_pool()
    except Exception as e:
        logger.warning(f"⚠️ GraphRAG 提取线程池启动失败: {e}")

    # ── 对话持久化 ──
    try:
        from backend.db.conversation_store import ConversationStore
        from backend.controller.chat_controller import set_conversation_mapper
        conv_store = ConversationStore()
        set_conversation_mapper(conv_store)
    except Exception as e:
        logger.warning(f"⚠️ 对话持久化初始化失败: {e}")

    # ── 数据 API 控制器（/api/data/sessions 等端点） ──
    try:
        from backend.controller.data_controller import data_router, init_data_controller
        init_data_controller(conv_store)
        app.include_router(data_router)
    except Exception as e:
        logger.warning(f"⚠️ Data controller 注册失败: {e}")

    # ── RAG 模块可用性检查 ──
    try:
        from backend.rag.config import get_rag_config
        from backend.service.kb.kb_retriever import _rerank_enabled, _user_has_vectors
        from backend.db.schema import get_conn
        
        rag_config = get_rag_config()
        
        # 检查 Rerank 模型
        rerank_enabled = False
        rerank_model = "-"
        try:
            from backend.service.kb.kb_retriever import _get_rerank_config
            rerank_cfg = _get_rerank_config()
            if rerank_cfg:
                rerank_enabled = True
                rerank_model = rerank_cfg.get("model_name", "unknown")
        except Exception:
            pass
        
        # 知识库统计
        kb_stats = {"total": 0, "system": 0, "enabled": 0}
        try:
            conn = get_conn()
            cur = conn.execute("SELECT COUNT(*) AS cnt FROM kb_knowledge_base")
            kb_stats["total"] = cur.fetchone()["cnt"] if hasattr(cur, "fetchone") else 0
            cur = conn.execute("SELECT COUNT(*) AS cnt FROM kb_knowledge_base WHERE is_system = 1")
            kb_stats["system"] = cur.fetchone()["cnt"] if hasattr(cur, "fetchone") else 0
            cur = conn.execute("SELECT COUNT(*) AS cnt FROM kb_knowledge_base WHERE is_enabled = 1")
            kb_stats["enabled"] = cur.fetchone()["cnt"] if hasattr(cur, "fetchone") else 0
            conn.close()
        except Exception:
            pass
        
        # 文档统计
        doc_stats = {"total": 0, "vectorized": 0, "chunks": 0}
        try:
            conn = get_conn()
            cur = conn.execute("SELECT COUNT(*) AS cnt FROM kb_documents")
            doc_stats["total"] = cur.fetchone()["cnt"] if hasattr(cur, "fetchone") else 0
            cur = conn.execute("SELECT COUNT(*) AS cnt FROM kb_documents WHERE vectorized = 1")
            doc_stats["vectorized"] = cur.fetchone()["cnt"] if hasattr(cur, "fetchone") else 0
            cur = conn.execute("SELECT COUNT(*) AS cnt FROM kb_chunks")
            doc_stats["chunks"] = cur.fetchone()["cnt"] if hasattr(cur, "fetchone") else 0
            conn.close()
        except Exception:
            pass
        
        # 检索模式说明 - 动态检测实际向量库类型
        retrieval_modes = []
        _actual_vectorstore = "chroma"  # 默认
        try:
            import os as _os
            _milvus_host = _os.getenv("MILVUS_HOST", "")
            if _milvus_host:
                try:
                    from pymilvus import MilvusClient as _  # noqa: F401
                    _actual_vectorstore = "milvus"
                except ImportError:
                    pass
        except Exception:
            pass
        
        if _actual_vectorstore == "milvus":
            retrieval_modes.append(f"向量(Milvus@{_milvus_host})")
        else:
            retrieval_modes.append("向量(ChromaDB)")
        retrieval_modes.append("BM25(关键词)")
        
        # GraphRAG 可用性
        graphrag_available = False
        try:
            from backend.infrastructure import get_infrastructure
            graphrag_available = get_infrastructure().is_graphrag_available()
            if graphrag_available:
                retrieval_modes.append("GraphRAG(Neo4j)")
        except Exception:
            pass
        
        logger.info(
            f"\n"
            f"╔══════════════════════════════════════════════════════════════╗\n"
            f"║  📚 RAG 模块就绪                                              ║\n"
            f"╠══════════════════════════════════════════════════════════════╣\n"
            f"║  嵌入模型: {rag_config.embedding_provider}/{rag_config.embedding_model:<36} ║\n"
            f"║  向量库:   {('Milvus' if _actual_vectorstore == 'milvus' else 'ChromaDB'):<48} ║\n"
            f"║  Rerank:   {'✅ ' + rerank_model if rerank_enabled else '❌ 未配置':<44} ║\n"
            f"╠────────────────────────────────────────────────────────────────╣\n"
            f"║  知识库统计                                                    ║\n"
            f"║  ├─ 总数: {kb_stats['total']} 个 (启用 {kb_stats['enabled']} 个, 系统内置 {kb_stats['system']} 个){'':<22} ║\n"
            f"║  ├─ 文档: {doc_stats['total']} 个 (已向量化 {doc_stats['vectorized']} 个){'':<26} ║\n"
            f"║  └─ 分片: {doc_stats['chunks']} 个{'':<47} ║\n"
            f"╠────────────────────────────────────────────────────────────────╣\n"
            f"║  检索模式: {' + '.join(retrieval_modes):<47} ║\n"
            f"║  检索策略: 双路召回 (主路径 + 案例路径) + RRF 融合{'':<20} ║\n"
            f"╚══════════════════════════════════════════════════════════════╝"
        )
    except Exception as e:
        logger.debug(f"RAG 模块未启用: {e}")

    # =====================================================
    # 在这里添加你自己的控制器
    # 示例：
    # from backend.controller.your_controller import your_router
    # app.include_router(your_router)
    # =====================================================
    
    # ── API 控制器批量注册 ──
    _controllers_registered = []
    
    # 记忆评估 API
    try:
        from backend.controller.memory_eval_controller import register_routes as register_memory_eval
        register_memory_eval(app)
        _controllers_registered.append("memory-eval")
    except Exception as e:
        logger.warning(f"⚠️ Memory eval controller 注册失败: {e}")

    # 记忆条目管理 API（前端「记忆管理」/「记忆监控」页面依赖）
    # 此前该 router 从未被 include → 两个页面全部 404
    try:
        from backend.controller.memory_items_controller import router as mem_items_router
        app.include_router(mem_items_router)
        _controllers_registered.append("memory-items")
    except Exception as e:
        logger.warning(f"⚠️ Memory items controller 注册失败: {e}")
    
    # GraphRAG API
    try:
        from backend.controller.graphrag_controller import register_routes as register_graphrag
        register_graphrag(app)
        _controllers_registered.append("graphrag")
    except Exception as e:
        logger.warning(f"⚠️ GraphRAG controller 注册失败: {e}")

    # 平台配置 API（微信/飞书/邮箱）
    from backend.controller.platform_config_controller import router as pcfg_router
    app.include_router(pcfg_router)
    _controllers_registered.append("platform-config")

    # 用户绑定 API（用户↔平台账号绑定）
    from backend.controller.user_binding_controller import router as bind_router
    app.include_router(bind_router)
    _controllers_registered.append("user-binding")

    # 定时任务 API
    from backend.controller.cron_controller import router as cron_router
    app.include_router(cron_router)
    _controllers_registered.append("cron")

    # 可观测性 API
    from backend.controller.trace_controller import router as trace_router
    app.include_router(trace_router)
    _controllers_registered.append("trace")

    # 主机白名单 API
    from backend.controller.host_whitelist_controller import router as hw_router
    app.include_router(hw_router)
    _controllers_registered.append("host-whitelist")

    # 命令黑名单 API
    from backend.controller.command_blacklist_controller import router as cb_router
    app.include_router(cb_router)
    _controllers_registered.append("command-blacklist")

    # 通知 API（待审核数量统计）
    from backend.controller.notification_controller import router as notif_router
    app.include_router(notif_router)
    _controllers_registered.append("notification")

    # 工具直接调用 API（论文复现等场景）
    try:
        from backend.controller.tool_controller import register_tool_routes
        register_tool_routes(app)
        _controllers_registered.append("tools")
    except Exception as e:
        logger.warning(f"⚠️ Tool controller 注册失败: {e}")

    try:
        from backend.controller.model_config_controller import _route_router
        app.include_router(_route_router)
        _controllers_registered.append("model-routes")
    except Exception as e:
        logger.warning(f"⚠️ Model routes controller 注册失败: {e}")

    if _controllers_registered:
        logger.info(f"✅ API 控制器已注册: {', '.join(_controllers_registered)}")

    # 同步 Hermes 内置危险命令规则到黑名单
    try:
        from backend.service.command_blacklist_service import sync_hermes_builtin_patterns
        added = sync_hermes_builtin_patterns()
        if added > 0:
            logger.info(f"📦 安全规则: 已同步 Hermes 内置危险命令 {added} 条")
    except Exception as e:
        logger.warning(f"⚠️ Hermes 内置规则同步失败: {e}")

    # ── 前端静态文件服务 ──
    # 优先从 PROJECT_ROOT 环境变量加载（支持 PyInstaller 打包后的部署）
    project_root = os.environ.get("PROJECT_ROOT", os.path.dirname(__file__))
    vite_dist_path = os.path.join(project_root, "agent_frontend", "dist")
    
    if os.path.exists(vite_dist_path) and os.path.isdir(vite_dist_path):
        # Vite 构建模式（生产推荐）
        assets_dir = os.path.join(vite_dist_path, "assets")
        index_path = os.path.join(vite_dist_path, "index.html")

        if os.path.exists(index_path) and os.path.exists(assets_dir) and os.path.isdir(assets_dir):
            @app.get("/", include_in_schema=False)
            async def read_root_vite():
                return FileResponse(index_path)

            app.mount("/assets", StaticFiles(directory=assets_dir), name="vite_assets")
            # 保存 index_path 供中间件使用
            app.state.spa_index_path = index_path
            logger.info(f"📁 前端静态文件: {vite_dist_path}")
        else:
            logger.warning("⚠️ Vite 前端构建不完整。请运行: cd agent_frontend && npm install && npm run build")
    elif os.path.exists(os.path.join(os.path.dirname(__file__), "agent_frontend", "src")):
        logger.warning("⚠️ 前端未构建。请运行: cd agent_frontend && npm install && npm run build")
    else:
        logger.warning("⚠️ 前端目录不存在，跳过静态文件服务")

    # ── 数据目录与静态服务 ──
    from backend.config.paths import init_data_directories, DATA_ROOT
    
    # 初始化所有数据目录
    init_data_directories()
    
    # 静态服务挂载
    for _name, _subdir in [("uploads", "uploads"), ("charts", "charts"), ("reports", "reports")]:
        _dir = os.path.join(DATA_ROOT, _subdir)
        os.makedirs(_dir, exist_ok=True)
        app.mount(f"/static/{_name}", StaticFiles(directory=_dir), name=_name)
    
    logger.info(f"📁 数据目录: {DATA_ROOT}")

    _app_instance = app
    _initialized = True
    return app


# 创建应用实例
app = create_app()


def start_server(port=8001):
    """启动服务器"""
    import socket
    import time

    logger.info(
        f"\n"
        f"╔══════════════════════════════════════════════════════════════╗\n"
        f"║  🚀 AgentForge - Hermes Agent Scaffold                      ║\n"
        f"╠══════════════════════════════════════════════════════════════╣\n"
        f"║  📡 SSE 端点: http://localhost:{port:<5} /chat/stream           ║\n"
        f"║  🏠 前端页面: http://localhost:{port:<5} /                      ║\n"
        f"║  📖 API 文档: http://localhost:{port:<5} /docs                 ║\n"
        f"╚══════════════════════════════════════════════════════════════╝"
    )

    # 检查并杀死占用端口的进程
    kill_port(port)
    time.sleep(2)

    # 验证端口可用
    for attempt in range(2):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
                break
            except OSError as e:
                if attempt < 1:
                    logger.warning(f"⚠️ 端口 {port} 仍被占用，等待...")
                    time.sleep(2)
                else:
                    logger.error(f"❌ 端口 {port} 无法使用: {e}")
                    sys.exit(1)

    # 启动服务器
    # log_config=None: 禁止 uvicorn 添加自己的 StreamHandler，
    # 所有日志统一走 log_utils.py 的 InterceptHandler → loguru 管控
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "start":
            port = int(sys.argv[2]) if len(sys.argv) > 2 else 8001
            start_server(port)
        else:
            print(f"未知命令: {sys.argv[1]}")
            print("用法:")
            print("  python main.py              # 启动服务器（默认端口 8001）")
            print("  python main.py start 8080   # 指定端口")
            sys.exit(1)
    else:
        start_server(8001)
