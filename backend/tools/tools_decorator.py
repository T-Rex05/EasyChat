"""
AgentForge - 工具定义模板

使用 LangChain @tool 装饰器定义工具，供 Hermes 调用。
这是脚手架的示例文件，展示如何定义和注册自定义工具。

添加新工具的步骤：
1. 在此文件定义工具函数（使用 @tool 装饰器）
2. 在 get_project_tools() 中注册
3. 工具会自动注册到 Hermes ToolRegistry

工具分类：
- get_project_tools(): 返回所有项目自定义工具
"""
import json
from datetime import datetime
from typing import List, Any, Dict

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.utils.log_utils import log, rag

logger = log


# ==================== 工具参数 Schema ====================

class GetCurrentTimeInput(BaseModel):
    """获取当前时间工具的参数"""
    format: str = Field(
        default="%Y-%m-%d %H:%M:%S",
        description="时间格式，默认 %Y-%m-%d %H:%M:%S"
    )


class EchoInput(BaseModel):
    """Echo 工具的参数（示例工具）"""
    message: str = Field(description="要回显的消息")


# ==================== 示例工具 ====================

@tool(args_schema=GetCurrentTimeInput)
def get_current_time(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    获取当前系统时间。

    当 LLM 需要知道当前日期时间时调用此工具。
    例如：计算时间范围、判断是否工作日、生成时间戳等。

    Args:
        format: 时间格式字符串，遵循 Python datetime 格式规范

    Returns:
        str: 格式化的当前时间字符串
    """
    now = datetime.now()
    return now.strftime(format)


get_current_time._toolset = "__always_available__"  # 基础工具，所有用户可用


@tool(args_schema=EchoInput)
def echo_tool(message: str) -> str:
    """
    回显消息（示例工具）。

    这是一个简单的示例工具，用于展示如何定义和注册自定义工具。
    你可以参考这个模板创建自己的工具。

    Args:
        message: 要回显的消息内容

    Returns:
        str: 回显的消息，带有前缀标识
    """
    log.info(f"[EchoTool] 收到消息: {message[:100]}")
    return f"[Echo] {message}"


echo_tool._toolset = "__always_available__"  # 基础工具，所有用户可用


# ==================== 任务管理工具 ====================
# 这些工具允许 LLM 管理待办事项列表，用于复杂任务的分步执行

_todo_store: Dict[str, Dict[str, Any]] = {}
_next_id: Dict[str, int] = {}


def _get_thread_id(config) -> str:
    """从 RunnableConfig 中提取 thread_id"""
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
        return str(configurable.get("thread_id", "default"))
    return "default"


def _current_user_id(default=None, config=None):
    """获取当前用户 ID（配置通道优先，contextvar 兜底）。

    身份只来自 RunDispatcher 构造的可信 ``ToolContext``；工具参数永远不能
    指定 user_id。没有身份时返回 default，由调用方决定拒绝而不是假设 user 0。
    """
    from backend.shared.tool_context import resolve

    context = resolve(config)
    if context is None:
        return default
    try:
        return int(context.principal.user_id)
    except (ValueError, TypeError):
        return default


def _get_todo_key(config) -> str:
    """生成待办列表的键（user_id:thread_id），实现用户隔离。"""
    thread_id = _get_thread_id(config)
    user_id = _current_user_id(config=config)
    if user_id is None:
        # 无身份时拒绝写入共享键，避免所有匿名请求串到 user 0。
        raise RuntimeError("缺少可信用户身份，拒绝访问待办")
    return f"{user_id}:{thread_id}"


class TodoAddInput(BaseModel):
    """添加任务参数"""
    title: str = Field(description="任务标题")
    description: str = Field(description="任务详细描述")


class TodoUpdateInput(BaseModel):
    """更新任务状态参数"""
    task_id: str = Field(description="任务 ID")
    status: str = Field(description="新状态: pending/in_progress/completed")


class TodoGetInput(BaseModel):
    """获取任务列表参数"""
    pass


# ==================== 定时任务创建工具 ====================

class CronJobCreateInput(BaseModel):
    """创建定时任务参数"""
    name: str = Field(description="任务名称，如「每日安全报告」")
    prompt: str = Field(description="AI 提示词，描述要生成的报告内容和格式")
    schedule_type: str = Field(default="daily", description="调度类型: daily(每天) / cron(cron表达式) / interval(间隔)")
    schedule_value: str = Field(default="09:00", description="调度值。daily: 时间如09:00; cron: 表达式如'0 9 * * *'; interval: 如'30m'/'1h'")
    deliver_to: str = Field(default="wechat", description="投递渠道: wechat(微信) / email(邮箱) / both(两者)")
    email_config_id: int = Field(default=None, description="邮箱配置ID（当deliver_to为email或both时必填）。使用list_email_configs工具查询可用配置")
    receiver_email: str = Field(default=None, description="收件人邮箱地址（当deliver_to为email或both时必填）")


@tool(args_schema=CronJobCreateInput)
def cronjob_create(
    name: str, prompt: str, schedule_type: str = "daily",
    schedule_value: str = "09:00", deliver_to: str = "wechat",
    email_config_id: int = None, receiver_email: str = None,
) -> str:
    """
    创建一个定时任务，在指定时间自动生成报告并发送给用户。

    定时任务系统会在设定的时间自动调用 AI 生成报告，然后投递到用户选择的渠道（微信/邮箱）。
    用户可以在「历史记录 → 定时任务」标签查看和管理所有定时任务。

    使用场景：
    - 用户说「每天早上9点给我发一份安全报告」→ schedule_type='daily', schedule_value='09:00'
    - 用户说「每周一上午8点生成周报」→ schedule_type='cron', schedule_value='0 8 * * 1'
    - 用户说「每30分钟检查一次服务器状态」→ schedule_type='interval', schedule_value='30m'

    投递渠道说明：
    - wechat: 微信投递（自动使用用户绑定的微信账号，无需额外配置）
    - email: 邮箱投递（需要指定 email_config_id 和 receiver_email）
    - both: 同时投递到微信和邮箱

    重要：创建邮箱投递前，请先调用 list_delivery_configs 工具查询：
    - 可用的发件邮箱配置（email_config_id）
    - 用户的收件邮箱地址（receiver_email）
    - 用户的微信绑定状态

    Args:
        name: 任务名称（简短描述）
        prompt: AI 提示词（告诉 AI 要生成什么内容）
        schedule_type: 调度类型（daily/cron/interval）
        schedule_value: 调度值（时间/表达式/间隔）
        deliver_to: 投递渠道（wechat/email/both）
        email_config_id: 发件邮箱配置ID（email或both时必填，通过 list_delivery_configs 查询）
        receiver_email: 收件人邮箱（email或both时必填，通过 list_delivery_configs 查询）

    Returns:
        str: 创建结果（成功返回任务ID，失败返回错误信息）
    """
    try:
        # 获取当前用户 ID（权威来源：ToolContext / RunDispatcher）
        user_id = _current_user_id()
        if user_id is None:
            return "❌ 缺少可信用户身份，拒绝创建定时任务。"

        # 权限检查
        from backend.permission.checker import has_permission
        if not has_permission(user_id, "cron.create"):
            return "❌ 权限不足：你没有创建定时任务的权限（cron.create）。请联系管理员为你开通。"

        # 校验参数
        if schedule_type not in ("daily", "cron", "interval"):
            return f"❌ 无效的调度类型: {schedule_type}。可选: daily / cron / interval"

        if not schedule_value.strip():
            return "❌ 调度值不能为空"

        # 邮箱投递参数校验
        if deliver_to in ("email", "both"):
            if not email_config_id:
                return "❌ 邮箱投递需要指定 email_config_id。请使用 list_email_configs 工具查询可用配置。"
            if not receiver_email:
                return "❌ 邮箱投递需要指定 receiver_email（收件人邮箱地址）"
            
            # 验证邮箱配置是否存在
            from backend.db.schema import get_conn
            conn = get_conn()
            try:
                cur = conn.execute(
                    "SELECT id FROM email_configs WHERE id = %s AND enabled = 1",
                    (email_config_id,),
                )
                if not cur.fetchone():
                    return f"❌ 邮箱配置 ID={email_config_id} 不存在或已禁用"
            finally:
                conn.close()

        from backend.service.cron.cron_service import CronDataMapper, cron_service

        mapper = CronDataMapper()
        job_id = mapper.create_job(
            user_id=user_id,
            name=name,
            prompt=prompt,
            schedule_type=schedule_type,
            schedule_value=schedule_value.strip(),
            deliver_to=deliver_to,
            email_sender_id=email_config_id,
            email_receiver_id=None,  # receiver_email 存储在 receiver_email 字段
            receiver_email=receiver_email or "",
        )

        # 注册到调度器
        cron_service.add_job(job_id, schedule_type, schedule_value.strip())

        channel_text = {"wechat": "微信", "email": "邮箱", "both": "微信+邮箱"}.get(deliver_to, deliver_to)
        schedule_text = {
            "daily": f"每天 {schedule_value}",
            "cron": f"Cron: {schedule_value}",
            "interval": f"每 {schedule_value}",
        }.get(schedule_type, schedule_value)

        result = (
            f"✅ 定时任务创建成功！\n"
            f"- 任务 ID: {job_id}\n"
            f"- 名称: {name}\n"
            f"- 调度: {schedule_text}\n"
            f"- 投递: {channel_text}\n"
        )
        
        if deliver_to in ("email", "both"):
            result += f"- 发件人配置ID: {email_config_id}\n"
            result += f"- 收件人邮箱: {receiver_email}\n"
        
        result += "用户可在「历史记录 → 定时任务」标签查看和管理。"
        
        return result
    except Exception as e:
        return f"❌ 创建定时任务失败: {e}"


cronjob_create._toolset = "schedule"


@tool(args_schema=TodoAddInput)
def todo_add(title: str, description: str, config: RunnableConfig = None) -> str:
    """
    添加新任务到待办列表。

    用于规划复杂任务的执行步骤。

    Args:
        title: 任务标题
        description: 任务详细描述

    Returns:
        str: 添加结果和当前任务列表
    """
    todo_key = _get_todo_key(config)

    if todo_key not in _todo_store:
        _todo_store[todo_key] = {}
        _next_id[todo_key] = 1

    task_id = str(_next_id[todo_key])
    _next_id[todo_key] += 1

    _todo_store[todo_key][task_id] = {
        "id": task_id,
        "title": title,
        "description": description,
        "status": "pending"
    }

    tasks = list(_todo_store[todo_key].values())
    return f"任务已添加: {title} (id={task_id})\n\n当前任务列表:\n{json.dumps(tasks, ensure_ascii=False, indent=2)}"


todo_add._toolset = "__always_available__"  # 基础工具，所有用户可用


@tool(args_schema=TodoUpdateInput)
def todo_update(task_id: str, status: str, config: RunnableConfig = None) -> str:
    """
    更新任务状态。

    Args:
        task_id: 任务 ID
        status: 新状态 (pending/in_progress/completed)

    Returns:
        str: 更新结果
    """
    todo_key = _get_todo_key(config)

    if todo_key not in _todo_store or task_id not in _todo_store[todo_key]:
        return f"错误: 未找到任务 {task_id}"

    task = _todo_store[todo_key][task_id]
    old_status = task["status"]
    task["status"] = status

    return f"任务 {task['title']} (id={task_id}) 状态已更新: {old_status} → {status}"


todo_update._toolset = "__always_available__"  # 基础工具，所有用户可用


@tool(args_schema=TodoGetInput)
def todo_get(config: RunnableConfig = None) -> str:
    """
    获取当前任务列表。

    Returns:
        str: 当前所有任务及其状态
    """
    todo_key = _get_todo_key(config)

    if todo_key not in _todo_store or not _todo_store[todo_key]:
        return "当前没有任务。使用 todo_add 添加新任务。"

    tasks = list(_todo_store[todo_key].values())
    return f"当前任务列表 (共 {len(tasks)} 个):\n{json.dumps(tasks, ensure_ascii=False, indent=2)}"


todo_get._toolset = "__always_available__"  # 基础工具，所有用户可用


# ==================== 投递配置查询工具 ====================

class ListDeliveryConfigsInput(BaseModel):
    """查询投递配置参数"""
    pass


@tool(args_schema=ListDeliveryConfigsInput)
def list_delivery_configs() -> str:
    """
    查询当前用户可用的投递配置（发件邮箱、收件邮箱、微信绑定）。

    在创建定时任务（cronjob_create）选择邮箱投递前，必须先调用此工具查询：
    - 可用的发件邮箱配置（email_config_id）
    - 用户的收件邮箱地址（receiver_email）
    - 用户的微信绑定状态

    使用场景：
    - 用户说「每天发报告到我的邮箱」→ 先查有哪些邮箱配置可选
    - 用户说「定时任务发到微信」→ 先确认微信是否已绑定

    Returns:
        str: JSON 格式的投递配置列表，包含：
            - email_configs: 发件邮箱配置列表（id, name, email）
            - personal_emails: 用户收件邮箱列表
            - wechat_bound: 微信是否已绑定
    """
    try:
        # 获取当前用户 ID（权威来源：ToolContext / RunDispatcher）
        user_id = _current_user_id()
        if user_id is None:
            return "❌ 缺少可信用户身份，拒绝读取投递配置。"

        from backend.db.schema import get_conn
        import json as _json

        result = {
            "email_configs": [],
            "personal_emails": [],
            "wechat_bound": False,
        }

        conn = get_conn()
        try:
            # 1. 查询发件邮箱配置（全局启用）
            # 列名以 email_configs 的真实 schema 为准：
            #   id, user_id, config_name, host, port, sender_email, sender_name,
            #   password, is_current, enabled, created_at, updated_at
            # 原写法用了不存在的 name / email 列 → 每次调用都抛
            # "Unknown column 'name' in 'field list'"，工具从未成功过。
            cur = conn.execute(
                "SELECT id, config_name, sender_email FROM email_configs "
                "WHERE enabled = 1 ORDER BY id"
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            result["email_configs"] = [
                {"id": r["id"], "name": r["config_name"], "email": r["sender_email"]}
                for r in rows
            ]

            # 2. 查询用户的收件邮箱
            cur = conn.execute(
                "SELECT email FROM personal_emails WHERE user_id = %s ORDER BY id",
                (user_id,),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            result["personal_emails"] = [r["email"] for r in rows]

            # 3. 查询微信绑定状态
            cur = conn.execute(
                "SELECT COUNT(*) as cnt FROM user_bindings WHERE user_id = %s AND platform = 'wechat'",
                (user_id,),
            )
            row = cur.fetchone() if hasattr(cur, "fetchone") else None
            result["wechat_bound"] = bool(row and row.get("cnt", 0) > 0)

        finally:
            conn.close()

        return _json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return f"❌ 查询投递配置失败: {e}"


list_delivery_configs._toolset = "notification"


# ==================== RAG 知识库工具 ====================

class KnowledgeSearchInput(BaseModel):
    """知识库检索参数"""
    query: str = Field(description="检索问题（自然语言）")
    top_k: int = Field(default=5, description="返回结果数量（默认 5）")


def _load_doc_names(doc_ids: List[int]) -> Dict[int, str]:
    """批量取文档名（用于检索结果引用展示）。"""
    if not doc_ids:
        return {}
    from backend.db.schema import get_conn

    names: Dict[int, str] = {}
    try:
        conn = get_conn()
        try:
            cur = conn.execute(
                f"SELECT id, original_name FROM kb_documents WHERE id IN ({','.join('%s' for _ in doc_ids)})",
                doc_ids,
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            names = {int(r["id"]): r.get("original_name") or "知识库文档" for r in rows}
        finally:
            conn.close()
    except Exception:
        pass
    return names


def _load_chunk_meta(chunk_ids: List[int]) -> Dict[int, dict]:
    """批量取 chunk 的页码和 metadata（用于结构化引用展示）。

    Returns:
        {chunk_id: {"page_start": int|None, "page_end": int|None, "heading": str, "kind": str}}
    """
    if not chunk_ids:
        return {}
    from backend.db.schema import get_conn
    import json as _json

    meta_map: Dict[int, dict] = {}
    try:
        conn = get_conn()
        try:
            cur = conn.execute(
                f"SELECT id, page_start, page_end, metadata, kind FROM kb_chunks WHERE id IN ({','.join('%s' for _ in chunk_ids)})",
                chunk_ids,
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            for r in rows:
                cid = int(r["id"])
                raw_meta = r.get("metadata") or "{}"
                try:
                    meta = _json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})
                except (TypeError, ValueError):
                    meta = {}
                heading = meta.get("heading") or meta.get("title") or meta.get("heading_path") or ""
                meta_map[cid] = {
                    "page_start": r.get("page_start"),
                    "page_end": r.get("page_end"),
                    "heading": str(heading).strip(),
                    "kind": r.get("kind") or "base",
                }
        finally:
            conn.close()
    except Exception:
        pass
    return meta_map


def _format_page_info(page_start, page_end) -> str:
    """格式化页码信息为可读字符串。"""
    if page_start is None:
        return ""
    if page_end and page_end != page_start:
        return f"p.{page_start}-{page_end}"
    return f"p.{page_start}"


def _knowledge_search_legacy(query: str, top_k: int) -> str:
    """非对话上下文（无用户身份）的兜底：走 legacy pipeline，保持历史兼容。"""
    try:
        from backend.rag import get_rag_pipeline

        pipeline = get_rag_pipeline()
        docs = pipeline.retrieve(query, k=top_k)
        if not docs:
            return "未找到相关信息。请确认知识库中已摄入相关文档。"
        results = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "未知来源")
            results.append(f"[{i}] 来源: {source}\n{doc.page_content}")
        return "\n\n---\n\n".join(results)
    except ImportError as e:
        return f"RAG 模块未安装完整依赖: {e}。请检查 requirements.txt 中的 RAG 相关依赖。"
    except Exception as e:
        return f"知识库检索失败: {e}"


@tool(args_schema=KnowledgeSearchInput)
def knowledge_search(query: str, top_k: int = 5, config: RunnableConfig = None) -> str:
    """
    从当前用户的知识库检索相关信息（双路召回）。

    当需要查询用户上传到「知识库」页面的文档（PDF/Markdown/Word 等）时调用此工具。
    支持双路召回：
    - 主路径：LLM 自动选择相关知识库，BM25/向量检索
    - 案例路径：自动召回"历史正确案例"知识库的 SQL 示例

    返回结构化引用格式，每条结果包含引用标签（[资料N]）、来源位置、标题/条款和内容。
    回答时请保留引用标签，并在末尾输出「依据来源」小节。

    Args:
        query: 检索问题（自然语言，如"如何报销？"）
        top_k: 返回结果数量（默认 5）

    Returns:
        str: 结构化引用格式的知识库检索结果
    """
    import time as _time

    top_k = max(1, min(int(top_k or 5), 20))
    thread_id = _get_thread_id(config)

    # 当前用户（Hermes 工作线程中由 copy_context 注入，见 hermes_adapter.run）
    from backend.hermes_adapter import _CURRENT_USER_ID_CTX
    user_id = _CURRENT_USER_ID_CTX.get()

    # 入口日志
    rag.info(f"🔍 [Tool-KnowledgeSearch] 开始检索: query='{query[:50]}{'...' if len(query) > 50 else ''}', user_id={user_id}, top_k={top_k}")

    if user_id is None:
        # 无用户上下文（非对话调用）→ legacy 兜底
        return _knowledge_search_legacy(query, top_k)

    try:
        from backend.service.kb.kb_retriever import dual_path_retrieve, log_retrieval

        start = _time.monotonic()
        # 双路召回：主路径 + 案例路径
        # force_retrieval=True：模型显式调用检索工具，说明"就是要检索"，
        # 不能被 Adaptive RAG 路由器的 NO_RETRIEVAL（短查询直答）整条跳过
        result = dual_path_retrieve(
            user_id=int(user_id),
            query=query,
            main_top_k=top_k,
            case_top_k=3,
            adaptive_routing=True,
            force_retrieval=True,
        )
        elapsed_ms = int((_time.monotonic() - start) * 1000)

        # ── Pipeline Trace: KB 检索结果 ──
        try:
            from backend.service.pipeline_trace import PipelineTrace
            _kb_trace = PipelineTrace.current()
            if _kb_trace:
                _adaptive = result.get("adaptive_routing") or {}
                _strategy = result.get("retrieval_strategy") or {}
                _kb_trace.record("kb_retrieval",
                    query=query[:100],
                    selected_kbs=[kb.get("kb_name") or kb.get("name") for kb in result.get("selected_kbs", [])],
                    main_count=len(result.get("main_results", [])),
                    case_count=len(result.get("case_results", [])),
                    has_graphrag=bool(result.get("graphrag_context")),
                    retrieval_kind=_strategy.get("kind"),
                    retrieval_method=_strategy.get("method"),
                    seed_entities=_strategy.get("seed_entities", [])[:5],
                    top1_entity_score=_strategy.get("top1_entity_score"),
                    adaptive_complexity=_adaptive.get("complexity"),
                    adaptive_reason=_adaptive.get("reason"),
                    top_chunks=[
                        {"content": r.get("content", "")[:100],
                         "score": round(r.get("score", 0), 3),
                         # 真实语义分：Rerank 分 / 实体余弦。RRF 融合会覆盖 score，
                         # 面板上直接显示 score 会把高相关结果显示成 0.0x
                         "rerank_score": r.get("rerank_score"),
                         "entity_score": r.get("entity_score"),
                         "source": r.get("retrieval_source") or r.get("source") or "unknown",
                         "method": r.get("retriever"),
                         "doc_id": r.get("document_id") or r.get("doc_id")}
                        for r in (result.get("main_results", []) or [])[:5]
                    ],
                    elapsed_ms=elapsed_ms,
                )
        except Exception:
            pass

        # 合并结果
        main_results = result.get("main_results", [])
        case_results = result.get("case_results", [])
        graphrag_context = result.get("graphrag_context")
        all_results = main_results + case_results

        # 记录检索日志
        log_retrieval(int(user_id), thread_id, query, top_k, "dual_path", all_results, elapsed_ms)
    except Exception as e:
        return f"知识库检索失败: {e}"

    if not all_results and not graphrag_context:
        quality = result.get("quality_assessment", {})
        if quality.get("quality") == "empty":
            return (
                "资料类型：参考资料\n"
                "知识库中未找到与问题相关的资料。\n"
                "请明确告知用户「知识库中暂无相关信息」，不要编造答案。"
            )
        return (
            "资料类型：参考资料\n"
            "本次没有可公开引用的资料片段。\n"
            "最终回答如需展示依据来源，请省略参考依据行。禁止编造文档名称或原文位置。"
        )

    # 批量加载文档名和 chunk 元数据（页码、标题等）
    doc_names = _load_doc_names([int(r["document_id"]) for r in all_results if r.get("document_id")])
    chunk_meta = _load_chunk_meta([int(r["chunk_id"]) for r in all_results if r.get("chunk_id")])

    results = []
    table_refs_all: List[str] = []

    # ── 头部：资料类型 + 回答策略 + 引用规则 ──
    results.append("资料类型：参考资料")
    results.append("回答策略：基于以下检索结果回答问题，引用时保留来源、标题/条款和原文位置。")
    results.append(
        "引用规则：最终回答引用资料时，统一使用 [资料1]、[资料2] 等标签；"
        "没有公开引用资料时省略参考依据行，禁止编造文档名称或原文位置。"
    )

    # ── 幻觉护栏：基于 CRAG 质量评估注入置信度提示 ──
    quality = result.get("quality_assessment", {})
    quality_level = quality.get("quality", "high")
    if quality_level == "low":
        results.append(
            "注意：检索置信度较低，以下资料相关度不高，请谨慎参考。"
            "如果信息不足以回答问题，请明确告知用户「当前知识库中未找到足够依据」，"
            "不要基于低相关度内容推测回答。"
        )
    elif quality_level == "medium":
        results.append(
            "注意：检索结果相关度中等，请优先使用高相关度的资料，"
            "如果资料不足以完整回答，请标注哪些部分依据不足。"
        )
    # quality == "high" 时不附加额外提示

    # ── 知识图谱关系（按查询信号分档注入：仅关系型问法才给） ──
    _card = result.get("relation_card") or {}
    if _card.get("lines"):
        _tier = _card.get("tier", "")
        _tier_hint = "关系线索" if _tier == "strong" else "实体线索"
        results.append(
            f"\n【知识图谱{_tier_hint}】以下为图谱中与该问题相关的实体/关系，"
            f"用作串联线索；与原文冲突时**以原文为准**：\n"
            + "\n".join(_card["lines"])
        )

    # ── GraphRAG 社区上下文（全局/DRIFT 检索结果） ──
    if graphrag_context:
        gr_type = graphrag_context.get("query_type", "")
        gr_answer = graphrag_context.get("answer", "")
        gr_sources = graphrag_context.get("sources", [])
        if gr_answer:
            source_str = "、".join(gr_sources[:5]) if gr_sources else "知识图谱社区"
            results.append(
                f"\n【知识图谱分析（{gr_type}）】\n"
                f"来源：{source_str}\n"
                f"分析结果：{gr_answer}"
            )

    # ── 主路径结果（结构化格式） ──
    main_index = 0
    if main_results:
        for r in main_results:
            # 网络搜索结果单独格式化，跳过
            if r.get("retriever") == "web_search":
                continue
            main_index += 1
            chunk_id = r.get("chunk_id")
            doc_id = int(r.get("document_id") or 0)
            doc_name = doc_names.get(doc_id, "知识库文档")
            kb_name = r.get("kb_name", "")
            meta = chunk_meta.get(int(chunk_id or 0), {})
            page_str = _format_page_info(meta.get("page_start"), meta.get("page_end"))
            heading = meta.get("heading", "") or ""
            content = (r.get("content") or "").strip()

            # 来源位置：文档名 / 知识库名 / 页码
            source_parts = [doc_name]
            if kb_name:
                source_parts.append(kb_name)
            if page_str:
                source_parts.append(page_str)
            source_location = " / ".join(source_parts)

            # 标题/条款
            title_clause = heading or doc_name

            # 相关度：优先展示"真实语义相关度"，再给融合分做参考。
            #
            # ⚠️ 不能只显示 `score`：多查询 RRF 融合会把 `score` 覆盖成 0.0x 量级的融合分，
            # 明明实体余弦 0.86 的高相关结果会显示成"相关度 0.065"，
            # 模型据此会误判"检索结果不相关"从而不用资料 / 另起 web 搜索。
            # 实体链路把余弦分单独存在 entity_score（见 adaptive_retriever），这里优先用它。
            rerank_score = r.get("rerank_score")
            entity_score = r.get("entity_score")
            fused_score = r.get("score", 0)
            if rerank_score is not None:
                score_str = f"Rerank={rerank_score:.3f}"
            elif entity_score is not None:
                score_str = f"实体相似度={entity_score:.3f}"
            else:
                score_str = f"相关度={fused_score:.3f}"
            if entity_score is not None and rerank_score is not None:
                score_str += f", 实体相似度={entity_score:.3f}"
            if r.get("rrf_fused") or r.get("retriever") in ("hybrid", "entity_local"):
                score_str += f"（融合分 {fused_score:.3f}）"

            results.append(
                f"【结果{main_index}】\n"
                f"引用标签：[资料{main_index}]\n"
                f"来源位置：{source_location}\n"
                f"标题/条款：{title_clause}\n"
                f"相关度：{score_str}\n"
                f"内容：{content}"
            )

            # 收集检索结果中的数据库表关联（text2sql 召回用）
            refs = r.get("table_refs") or []
            for t in refs:
                if str(t) not in table_refs_all:
                    table_refs_all.append(str(t))

    # ── 网络搜索结果（CRAG web search fallback，单独分组） ──
    web_results = [r for r in main_results if r.get("retriever") == "web_search"]
    if web_results:
        web_lines = ["\n【网络搜索补充资料】"]
        results.append(
            "注意：以下资料来自网络搜索（知识库中未找到直接相关内容），"
            "请谨慎参考并标注来源为网络搜索。"
        )
        for i, r in enumerate(web_results, 1):
            web_lines.append(
                f"【网络{i}】\n"
                f"引用标签：[网络{i}]\n"
                f"来源：{r.get('web_title', '')} ({r.get('web_url', '')})\n"
                f"内容：{(r.get('content') or '').strip()}"
            )
        results.append("\n".join(web_lines))

    # ── 案例路径结果（SQL 示例，单独分组） ──
    if case_results:
        case_lines = ["\n【SQL 参考案例（历史正确案例）】"]
        for i, r in enumerate(case_results, 1):
            chunk_id = r.get("chunk_id")
            doc_id = int(r.get("document_id") or 0)
            doc_name = doc_names.get(doc_id, "知识库文档")
            kb_name = r.get("kb_name", "")
            meta = chunk_meta.get(int(chunk_id or 0), {})
            page_str = _format_page_info(meta.get("page_start"), meta.get("page_end"))
            heading = meta.get("heading", "") or ""
            content = (r.get("content") or "").strip()

            source_parts = [doc_name]
            if kb_name:
                source_parts.append(kb_name)
            if page_str:
                source_parts.append(page_str)
            source_location = " / ".join(source_parts)
            title_clause = heading or doc_name

            case_lines.append(
                f"【案例{i}】\n"
                f"来源位置：{source_location}\n"
                f"标题/条款：{title_clause}\n"
                f"内容：{content}"
            )
        results.append("\n".join(case_lines))

    # ── 数据库表关联 → Schema Card 拼装（text2sql 增强） ──
    schema_block = ""
    if table_refs_all:
        try:
            from backend.service.database_semantic_index import resolve_table_schema_context
            schema_ctx = resolve_table_schema_context(table_refs_all, database="mysql", max_tables=10)
            if schema_ctx:
                schema_block = (
                    "\n\n---\n\n## 相关数据库表结构（Schema Card）\n"
                    "以下是与检索内容关联的数据库表结构，如需生成 SQL 查询请基于这些表：\n\n"
                    f"{schema_ctx}"
                )
        except Exception:
            pass  # Schema 拼装失败不影响检索结果

    # 出口日志
    total_results = len(main_results) + len(case_results)
    rag.info(f"✅ [Tool-KnowledgeSearch] 检索完成: 结果数={total_results}, 耗时={elapsed_ms}ms, user_id={user_id}")

    return "\n\n".join(results) + schema_block


# knowledge_search 所有用户可用，不归属任何权限控制的 toolset
# 设置为特殊值 "__always_available__" 表示跳过权限检查
knowledge_search._toolset = "__always_available__"


class WhenResolveInput(BaseModel):
    phrase: str = Field(description="中文时间短语，如：今天、本周、本月、上季度、最近7天、过去6小时")


@tool(args_schema=WhenResolveInput)
def when_resolve(phrase: str) -> str:
    """把中文时间短语解析为具体的起止时间（用于报告/查询的时间范围计算）。"""
    try:
        from backend.utils.when_resolver import resolve_when
        start, end = resolve_when(phrase)
        return f"起: {start.strftime('%Y-%m-%d %H:%M:%S')}  止: {end.strftime('%Y-%m-%d %H:%M:%S')}"
    except ValueError as e:
        return f"无法解析时间短语 {phrase!r}：{e}"


when_resolve._toolset = "__always_available__"  # 基础工具，所有用户可用


def get_kg_tools() -> list:
    """知识图谱工具（惰性导入）。

    R03 后 KG 属移除范围：此函数不再被 get_project_tools 调用，
    仅为兼容期保留入口；只有显式调用才会导入 neo4j 依赖。
    """
    from backend.tools.kg_tools import (
        kg_stats,             # 统计信息（节点/关系/社区数量）
        kg_search,            # 实体搜索（按名称/类型模糊搜索）
        kg_entity_detail,     # 实体详情（含关系和时间线）
        kg_communities,       # 社区查询（层级社区 + 社区报告）
        kg_quality,           # 质量分析（置信度分布、孤立实体等）
    )
    return [kg_stats, kg_search, kg_entity_detail, kg_communities, kg_quality]


# ==================== 工具注册 ====================

def get_project_tools() -> list:
    """
    获取所有项目自定义工具（安全子集）。

    EasyChat 改造（R03/R14）：KB 检索、KG、Text2SQL、Code Mode、论文复现
    工具已从默认注册中移除——它们的模块导入必须保持惰性，禁止在聊天链路
    启动时被拉起。时间/待办/时间解析工具保留；提醒通过新调度 HTTP/页面管理。

    Returns:
        list: 工具列表
    """
    tools = [
        get_current_time,       # 获取当前时间
        todo_add,               # 添加任务
        todo_update,            # 更新任务状态
        todo_get,               # 获取任务列表
        when_resolve,           # 自然语言时间解析
    ]

    # =====================================================
    # 在这里添加你自己的工具
    # 示例：
    # tools.append(your_custom_tool)
    # =====================================================

    return tools


def _get_todo_list(thread_id: str, user_id: int = None) -> Dict[str, Any]:
    """获取指定会话的任务列表（供 API 端点调用）。

    Args:
        thread_id: 会话 ID
        user_id: 用户 ID（用于租户隔离）。为 None 时从 ContextVar 解析 ——
                 现有调用方（hermes_adapter / chat_controller / chat/stream）
                 都只传 thread_id，若默认成 0 会与 `todo_add` 写入用的
                 `{真实 uid}:{thread_id}` 不匹配，导致面板恒空。
    """
    if user_id is None:
        user_id = _current_user_id(default=0)
    todo_key = f"{user_id}:{thread_id}"
    return {
        "thread_id": thread_id,
        "tasks": list(_todo_store.get(todo_key, {}).values()),
    }


def _clear_todo_list(thread_id: str, user_id: int = None) -> None:
    """清理指定会话的任务列表（请求结束时调用，防止内存泄漏）。

    Args:
        thread_id: 会话 ID
        user_id: 用户 ID（用于租户隔离）。为 None 时从 ContextVar 解析，
                 否则会清不掉 `todo_add` 写入的真实键，导致 `_todo_store` 只增不减。
    """
    if user_id is None:
        user_id = _current_user_id(default=0)
    todo_key = f"{user_id}:{thread_id}"
    _todo_store.pop(todo_key, None)
    _next_id.pop(todo_key, None)


def get_all_tool_names() -> List[str]:
    """获取所有工具名称（用于调试）"""
    return [tool.name for tool in get_project_tools()]
