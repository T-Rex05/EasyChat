"""
Hermes 适配层 — AIAgent 运行时封装

使用 Hermes AIAgent 作为决策引擎，替代手动 LLM 调用。
Hermes 自带：终端、文件操作、记忆、技能系统
"""
import asyncio
import contextvars
import functools
import json
import logging
import os
import queue
import re as _re
import sys
import threading
import time
import uuid
import atexit
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Any, Optional, List
from backend.utils.log_utils import log
from backend.permission.checker import get_user_hermes_tools
from backend.tools.tool_output_guard import should_truncate, truncate_tool_output

# 标准 logging → loguru 桥接已由 backend/utils/log_utils.py 的 _InterceptHandler 统一处理。
# 此处不再安装额外的 handler，避免同一日志通过两条路径重复输出（一条字符串级别 "INFO"、
# 一条数字级别 "Level 20"）。噪声抑制通过 _console_filter + 源头修复完成：
#   - Hermes 每请求 INFO：_console_filter 按 logger name 抑制
#   - 桌面 GUI 工具 check_fn：HERMES_DESKTOP=1 使其返回 True
#   - Neo4j 关系类型通知：driver 创建时 notifications_min_severity="ERROR"

logger = log

# task_state 异步更新线程池（模块级单例，懒加载）
# 放在 hermes_adapter 层而不是 provider 层，是因为 task_state 的更新时机
# 在 run_conversation 完成后（此时 provider 拿不到 messages 列表）。
_TS_POOL = None  # concurrent.futures.ThreadPoolExecutor，懒加载
_TS_POOL_LOCK = threading.Lock()  # 懒加载锁（避免并发创建多个 executor）
atexit.register(lambda: _TS_POOL.shutdown(wait=False) if _TS_POOL is not None else None)

_HERMES_PATH = str(Path(__file__).parent / "hermes")
if _HERMES_PATH not in sys.path:
    sys.path.insert(0, _HERMES_PATH)

# Hermes 默认把 config/memory/skills/session 落到 ~/.hermes（服务账号家目录），
# 收口成项目自带目录，避免多进程/容器重启后配置漂移或散落到运行 uvicorn 的系统账号
# 家目录里。必须在任何 backend.hermes.* 模块导入之前设置。
#
# ⚠️ 强制覆盖：原先用 `if not os.environ.get("HERMES_HOME")` 收口，导致
# 只要用户/宿主机设了 HERMES_HOME 环境变量，收口就被跳过，技能/记忆/会话全部
# 落盘到用户自定义目录，造成数据漂移且与项目隔离意图冲突。现在改为无条件覆盖——
# 无论环境是否已设 HERMES_HOME，一律收口到项目自带目录，保证多环境行为一致。
#
# 2026-08-30: 统一数据目录到 docker/volumes/hermes/
if getattr(sys, "frozen", False):
    _hermes_home_dir = Path(os.environ.get("AGENTFORGE_DATA_DIR",
        str(Path(sys.executable).parent / "data"))) / "hermes"
else:
    # 使用统一数据目录 docker/volumes/hermes/
    from backend.config.paths import get_hermes_dir
    _hermes_home_dir = get_hermes_dir()
_hermes_home_dir.mkdir(parents=True, exist_ok=True)
os.environ["HERMES_HOME"] = str(_hermes_home_dir)
logger.info(f"🏠 HERMES_HOME 强制收口到: {_hermes_home_dir}")


def _update_hermes_reasoning_effort(effort: str) -> None:
    """更新 Hermes config.yaml 中的 agent.reasoning_effort。

    ⚠️ 已废弃：此函数会修改全局 config.yaml，在多用户并发场景下导致互相覆盖。
    现改为将 reasoning_config 直接传递给 AIAgent 构造参数（见 _get_agent），
    实现每会话独立配置。此函数保留仅作为历史参考，不应再调用。
    """
    import yaml
    config_path = Path(os.environ["HERMES_HOME"]) / "config.yaml"
    config = {}
    if config_path.exists():
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            config = {}

    agent_cfg = config.get("agent") or {}
    if not isinstance(agent_cfg, dict):
        agent_cfg = {}

    current = agent_cfg.get("reasoning_effort", "") or ""
    if current == effort:
        return  # 无变化，跳过写入

    agent_cfg["reasoning_effort"] = effort
    config["agent"] = agent_cfg
    config_path.write_text(yaml.dump(config, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    logger.info(f"🔄 Hermes reasoning_effort 更新: {current or '(默认)'} → {effort or '(关闭)'}")


def _seed_default_skills() -> None:
    """把 backend/hermes/skills/（Hermes 自带的默认技能目录，70 个）拷进 HERMES_HOME/skills/。

    Hermes 正常走 CLI 安装向导（hermes_cli/setup.py 的 seed_skills 一步）时会做这件事；
    脚手架绕过向导直接 new AIAgent()，从没跑过这一步，导致技能目录一直是空的——
    这正是"问它有什么技能，只回答 hermesagent"的根因（get_skills_dir() 只读
    HERMES_HOME/skills/，不会去读包自带的 backend/hermes/skills/ 源码目录）。
    只做一次：目标目录不存在或为空才播种，不覆盖用户后续自己装的技能。
    optional-skills/（111 个，需要额外凭据/环境的可选技能，如 yuanbao、区块链）不自动播种。
    """
    try:
        home = Path(os.environ["HERMES_HOME"])
        target = home / "skills"
        if target.exists() and any(target.iterdir()):
            return
        source = Path(__file__).parent / "hermes" / "skills"
        if not source.is_dir():
            return
        import shutil
        target.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            dest = target / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        logger.info(f"🧰 已播种默认技能目录到 {target}（{len(list(source.iterdir()))} 个分类）")
    except Exception as exc:
        logger.warning(f"⚠️ 播种默认技能目录失败（不阻断启动）: {exc}")


_seed_default_skills()


def _seed_default_config() -> None:
    """写一份精简版 HERMES_HOME/config.yaml，关掉与 Web 服务场景无关的提示词开销。

    Hermes 默认 agent.coding_context="auto"：只要检测到当前 cwd 是 git 仓库就
    会自动注入"编程工作区姿态"——操作简报 + 实时 git/workspace 快照——这是给
    CLI/TUI 编程助手用的，Web 服务场景不需要这段。agent.environment_probe 同理，是给本地终端探测
    python/pip/uv 工具链状态用的，一个跑在 uvicorn 里的服务不需要。两者都只影响
    系统提示词内容，不影响任何工具/记忆行为，只做一次，不覆盖用户后续手改的配置。

    sessions.auto_prune=true：启用 state.db 自动清理，保留 90 天内的会话历史，
    避免 SQLite 无限增长。Hermes 启动时调用 maybe_auto_prune_and_vacuum()，
    每 24 小时检查一次，清理过期 session 并 VACUUM 压缩数据库。
    """
    try:
        home = Path(os.environ["HERMES_HOME"])
        config_path = home / "config.yaml"
        if config_path.exists():
            return
        config_path.write_text(
            "agent:\n"
            "  coding_context: \"off\"\n"
            "  environment_probe: false\n"
            "  image_input_mode: native\n"
            "\n"
            "memory:\n"
            "  provider: agentforge\n"
            "\n"
            "model:\n"
            "  supports_vision: true\n"
            "\n"
            "sessions:\n"
            "  auto_prune: true\n"
            "  retention_days: 90\n"
            "  min_interval_hours: 24\n"
            "  vacuum_after_prune: true\n",
            encoding="utf-8",
        )
        logger.info(f"✅ 已写入精简版 Hermes 配置到 {config_path}（关闭 coding_context/environment_probe，启用 session 自动清理，激活 agentforge 记忆提供者）")
    except Exception as exc:
        logger.warning(f"⚠️ 写入默认 Hermes 配置失败（不阻断启动）: {exc}")


_seed_default_config()

# ── 当前登录用户上下文（用于技能创建时设置 author） ──
_CURRENT_USERNAME_CTX = contextvars.ContextVar("current_username", default=None)
_CURRENT_USER_ID_CTX = contextvars.ContextVar("current_user_id", default=None)


# ── 当前请求的 thread_id，供项目工具的 RunnableConfig 注入 ──
# todo_add/todo_update/todo_get 等工具函数签名里带 config: RunnableConfig，
# LangChain 的 @tool 装饰器会把这类工具的 _run 包装成"必须显式传入 config"
# （不管原函数默认值是不是 None）——直接 tool._run(**args) 会报
# "missing 1 required keyword-only argument: 'config'"。
# 在 HermesRuntime.run() 里随 copy_context() 一起带进 run_in_executor 的工作线程。
_THREAD_ID_CTX: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_hermes_thread_id_ctx", default=None
)
# ── 当前请求的 thread_id，供项目工具的 RunnableConfig 注入 ──


def _compute_user_skill_scope(user_id: int):
    """计算每用户可见技能名集合（AgentForge 技能视图）。

    可见 = 默认技能（backend/hermes/skills 源码目录） + 公共技能（owner_id=1 且非 AI生成）
         + 用户自己的技能 + 用户在内容池安装的技能。
    super_admin / admin / 持 skill.manage 者返回 None（全量）。
    计算失败时返回 None（降级为全量，不阻断对话）。
    """
    try:
        from backend.permission.checker import has_permission
        from backend.service.auth.permission_service import get_user_role

        uid = int(user_id)
        role = get_user_role(uid) or "user"
        if role in ("super_admin", "admin") or has_permission(uid, "skill.manage"):
            return None

        from backend.service.skill_service import _meta_all
        from backend.service.skill.file_manager import _parse_frontmatter
        from backend.db.schema import get_conn

        visible = set()
        # 默认技能：源码目录中所有 SKILL.md 的 name（始终全员可见）
        source_dir = Path(__file__).parent / "hermes" / "skills"
        if source_dir.is_dir():
            for p in source_dir.rglob("SKILL.md"):
                try:
                    fm = _parse_frontmatter(p.read_text(encoding="utf-8", errors="replace")[:4000])
                    nm = fm.get("name") or p.parent.name
                    if nm:
                        visible.add(nm)
                except Exception:
                    pass

        # skill_meta：自己的 + 公共（owner_id=1 且非 AI生成）
        meta_map = _meta_all() or {}
        for name, m in meta_map.items():
            owner = int(m.get("owner_id") or 1)
            category = m.get("category") or ""
            if owner == uid:
                visible.add(name)
            elif owner == 1 and category != "AI生成":
                visible.add(name)

        # 内容池已安装
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT content_name FROM content_installs WHERE content_type = 'skill' AND user_id = %s",
                (uid,),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else [r for r in (cur or [])]
            for r in rows:
                visible.add(dict(r).get("content_name") or "")
        finally:
            conn.close()

        visible.discard("")
        return visible
    except Exception as e:
        logger.warning(f"计算技能视图失败（降级为全量）: {e}")
        return None
# ── 任务规划 SSE 实时推送 ──
# 指向当前请求的 thread_queue（asyncio.Queue 或 threading.Queue）。
# todo_add/todo_update 执行后，handler 把 tool_output SSE 事件直接塞进这个队列，
# chat_controller 的消费循环会把它转成 SSE 发给前端，实现任务面板实时更新。
# 与 _THREAD_ID_CTX 同一套 contextvars 机制，在 run() 里随 copy_context() 一起
# 带进 run_in_executor 的工作线程。
_TODO_QUEUE_CTX: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "_hermes_todo_queue_ctx", default=None
)

# 本轮"派发过委派批次"的一等信号（T3.3）。
# 子 Agent 的 subagent.start 回调在 daemon 池饱和时可能延迟（worker 未及时启动），
# 只靠"本轮 id 集合非空"判断会立即返回 → 5 秒宽限期拿不到完成事件 → SSE 关流 →
# 子 Agent 事件推进了没人读的队列（表现为"必须刷新才更新"）。
# 存放一个 per-turn 的可变 dict：{"dispatched": <批次数>}。
_TURN_DISPATCH_CTX: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "_agentforge_turn_dispatch_ctx", default=None
)

# 派发后等待"第一个 subagent.start 事件"的宽限期（秒）。
# 用于兜住 T3.3 的竞态：派发了但 start 事件延迟时不能立刻退出等待。
_DELEGATION_START_GRACE_S = 5.0


def _make_project_tool_handler(tool):
    """为单个 LangChain 工具生成 Hermes ToolRegistry 用的 handler。

    ToolRegistry.dispatch() 固定按 entry.handler(args, **kwargs) 调用——
    第一个位置参数是模型传来的调用参数字典，kwargs 是 task_id/session_id/
    user_task 等调度元信息（工具本身不需要）。必须用工厂函数把 tool 闭包在
    外层，返回的 handler 第一个位置参数专门留给 args，否则 args 字典会顶替
    掉 tool——这正是之前"工具已注册但调用全部返回 33 字符错误"的根因
    （原实现把 tool 写成 handler 的第一个位置参数，被 args 顶掉后
    getattr(dict, '_run'...) 全部落空，最终调用了 dict 本身触发
    'dict' object is not callable）。

    安全改进：异步结果处理使用更安全的事件循环管理。
    """
    tool_name = getattr(tool, 'name', getattr(tool, '__name__', 'unknown'))

    def _handler(args, **_kwargs):
        try:
            args_preview = json.dumps(args or {}, ensure_ascii=False, default=str)
        except Exception:
            args_preview = str(args)
        if len(args_preview) > 500:
            args_preview = args_preview[:500] + "...(截断)"
        logger.debug(f"工具调用 {tool_name} - 参数: {args_preview}")
        try:
            # 用官方 tool.invoke() 而非裸 tool._run(**args)：todo_add/todo_update/
            # todo_get 等工具函数签名里带 config: RunnableConfig，LangChain 的
            # @tool 装饰器会把它们的 _run 包装成"必须显式传入 config"，裸调用
            # 会报 "missing 1 required keyword-only argument: 'config'"。
            # invoke() 是 LangChain 官方入口，按工具是否声明 config 参数自动
            # 决定要不要注入，对不需要 config 的工具无影响。
            thread_id = _THREAD_ID_CTX.get()
            run_config = {"configurable": {"thread_id": thread_id}} if thread_id else None
            result = tool.invoke(args or {}, config=run_config)
            # 安全处理异步结果：优先检查是否已在异步上下文中
            if asyncio.iscoroutine(result):
                try:
                    # 尝试获取当前运行的事件循环
                    try:
                        asyncio.get_running_loop()  # 仅探测是否已在事件循环内
                        # 已在异步上下文中，不能使用 asyncio.run()
                        # 创建新事件循环在线程中运行
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(asyncio.run, result)
                            result = future.result(timeout=60)
                    except RuntimeError:
                        # 无运行中的事件循环，安全使用 asyncio.run()
                        result = asyncio.run(result)
                except Exception as _async_err:
                    logger.warning(f"异步工具执行失败 {tool_name}: {_async_err}")
                    return f"错误: 异步执行失败 - {_async_err}"
            result_str = str(result)
            # ── 工具输出守卫：超长输出即时截断 + 溢出到文件 ──
            # 参考 Claude Code 三层压缩 Tier 1（零 LLM 成本即时截断）。
            # 不让大输出进入上下文，保护 KV Cache 前缀稳定性。
            # 必须在日志预览之前执行，确保日志记录的是实际发给 LLM 的内容。
            from backend.context.tool_results.runtime import managed_results_active
            if not managed_results_active() and should_truncate(result_str, tool_name):
                result_str = truncate_tool_output(result_str, tool_name)
            result_preview = result_str if len(result_str) <= 800 else result_str[:800] + "...(截断，完整长度" + str(len(result_str)) + "字符)"
            logger.debug(f"工具返回 {tool_name} - 长度={len(result_str)}字符 内容: {result_preview}")
            # ── 任务规划实时推送：todo_add/todo_update/todo_get 执行完后，
            #    把 tool_output SSE 事件塞进 thread_queue，让前端任务面板实时更新 ──
            if tool_name in ('todo_add', 'todo_update', 'todo_get'):
                _todo_q = _TODO_QUEUE_CTX.get()
                if _todo_q is not None:
                    try:
                        from backend.tools.tools_decorator import _get_todo_list
                        _tid = _THREAD_ID_CTX.get()
                        if _tid:
                            _td = _get_todo_list(_tid)
                            _todos = _td.get("tasks", [])
                            _sse_payload = json.dumps({
                                "type": "tool_output",
                                "tool_name": tool_name,
                                "output": result_str,
                                "todos": _todos,
                            }, ensure_ascii=False, default=str)
                            _todo_q.put(f"data: {_sse_payload}\n\n")
                    except Exception as _todo_push_err:
                        logger.warning(f"推送任务面板事件失败: {_todo_push_err}")
            return result_str
        except Exception as e:
            logger.error(f"❌ 工具执行失败 {tool_name}: {e}")
            return f"错误: {e}"
    return _handler


# ── 项目工具注册（在 AIAgent 初始化前注册到 Hermes ToolRegistry） ──
_registered_tools: set = set()  # 已注册的工具名集合，避免重复注册
_registered_tools_lock = threading.Lock()  # 注册集合读写锁（多线程安全）


def _ensure_ddgs_web_search():
    """确保 DuckDuckGo 免费 Web 搜索 provider 已注册到 web_search_registry。

    Hermes 的插件发现机制需要完整的 CLI 环境（entry_points），纯进程内嵌入时
    不会自动加载 ddgs/tavily 等 web 插件。这里直接将 DDGS provider 注入
    web_search_registry，使 web_search 工具无需 API Key 即可工作。

    幂等调用——多次调用不会重复注册。
    """
    try:
        from agent.web_search_registry import get_provider, register_provider
        if get_provider("ddgs") is not None:
            return  # 已注册
        from plugins.web.ddgs.provider import DDGSWebSearchProvider
        _ddgs = DDGSWebSearchProvider()
        if _ddgs.is_available():
            register_provider(_ddgs)
            logger.info("DuckDuckGo Web 搜索已注册（免费，无需 API Key）")
        else:
            logger.info("ddgs 包未安装，DuckDuckGo Web 搜索不可用 — pip install ddgs")
    except Exception as _e:
        logger.debug(f"DuckDuckGo Web 搜索注册跳过: {_e}")


def _register_project_tools(enabled_toolsets: set = None):
    """把项目自定义工具注册到 Hermes ToolRegistry。
    必须在 AIAgent.__init__()→init_agent()→get_tool_definitions() 之前调用。

    所有在 backend/tools/tools_decorator.py 的 get_project_tools() 中返回的工具
    都会自动注册，供 Hermes LLM 调用。

    Args:
        enabled_toolsets: 用户有权启用的 toolset 集合。为 None 时全量注册（向后兼容，
            用于预热阶段）。非 None 时，只注册 _toolset 属性在集合中的工具。
    """
    try:
        from tools.registry import registry
        from backend.tools.tools_decorator import get_project_tools

        seen_names = set()
        tools = []
        for tool in get_project_tools():
            name = getattr(tool, 'name', None)
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            tools.append(tool)

        count = 0
        registered_names = []
        skipped_names = []
        for tool in tools:
            name = tool.name

            # ── 按 toolset 过滤：检查工具的 _toolset 是否在用户权限中 ──
            tool_toolset = getattr(tool, '_toolset', '__always_available__')  # 未标记的工具默认所有用户可用
            # __always_available__ 标记的工具对所有用户可用，跳过权限检查
            if tool_toolset == "__always_available__":
                pass  # 所有用户可用，无需权限检查
            elif enabled_toolsets is not None and tool_toolset not in enabled_toolsets:
                logger.debug(f"跳过工具 {name} (toolset={tool_toolset} 不在用户权限中)")
                skipped_names.append(f"{name}({tool_toolset})")
                continue

            # 已注册过则跳过（幂等）—— 加锁保护 check-and-add，防止并发重复注册
            with _registered_tools_lock:
                if name in _registered_tools:
                    continue
                _registered_tools.add(name)  # 先占位，防止竞态

            schema = {
                "name": name,
                "description": tool.description or "",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
            if tool.args_schema:
                try:
                    s = tool.args_schema.schema() if hasattr(tool.args_schema, 'schema') else {}
                    if name in {"context_read", "context_search"}:
                        # Preserve array items, nullable selectors and defaults for recovery.
                        schema["parameters"] = s
                    else:
                        props = {n: {"type": p.get("type", "string"), "description": p.get("description", "")}
                                 for n, p in s.get("properties", {}).items()}
                        schema["parameters"] = {"type": "object", "properties": props, "required": s.get("required", [])}
                except Exception:
                    pass

            # toolset 名字不能叫 "project"——Hermes 自己内置也有一个同名 toolset
            # （Desktop Projects GUI 的 project_list/create/switch，见
            # backend/hermes/toolsets.py）。名字撞车时，delegate_tool.py 里
            # 走 include_registry=False 静态视图解析 toolset（_expand_parent_
            # toolsets/_strip_blocked_tools 等场景）会只认 Hermes 内置那 3 个工具，
            # 我们注册的工具就从解析结果里消失。用 agentforge_project 避免冲突。
            registry.register(name=name, toolset="agentforge_project", schema=schema,
                              handler=_make_project_tool_handler(tool), is_async=False,
                              description=tool.description or "", emoji="🔧")
            count += 1
            registered_names.append(name)

        if count:
            logger.info(f"📦 注册 {count} 个项目工具到 Hermes: {', '.join(registered_names)}")
        if skipped_names:
            logger.debug(f"按 toolset 过滤跳过 {len(skipped_names)} 个工具: {', '.join(skipped_names)}")

        # ── Pipeline Trace: monkey-patch registry.dispatch 记录所有工具调用 ──
        _patch_dispatch_for_trace()

        # ── Delegation context enrichment: 子 Agent 自动注入 TaskState + 记忆 ──
        _install_delegation_enricher()
        # ── 委派桥接：默认旋钮 + 池满可观测 + 同批重复告警（零侵入，宿主侧） ──
        _apply_delegation_env_defaults()
        _patch_delegation_dispatch_for_quota()
        _patch_delegate_dispatch_for_overlap()

    except Exception as e:
        logger.warning(f"⚠️ 注册项目工具失败: {e}")


# ── Pipeline Trace: dispatch monkey-patch（幂等，只 patch 一次） ──
_dispatch_patched = False

def _patch_dispatch_for_trace():
    """包装 registry.dispatch，在每次工具调用时记录到 PipelineTrace。

    只 patch 一次（幂等），PIPELINE_TRACE != true 时跳过。
    """
    global _dispatch_patched
    if _dispatch_patched:
        return

    from backend.service.pipeline_trace import is_enabled as _pt_enabled
    if not _pt_enabled():
        return

    try:
        from tools.registry import registry
        import time as _time

        _original_dispatch = registry.dispatch

        def _traced_dispatch(name: str, args: dict, **kwargs):
            t0 = _time.monotonic()
            result = None
            try:
                result = _original_dispatch(name, args, **kwargs)
                return result
            finally:
                dur_ms = int((_time.monotonic() - t0) * 1000)
                try:
                    from backend.service.pipeline_trace import PipelineTrace
                    trace = PipelineTrace.current()
                    if trace:
                        result_str = str(result)[:500] if result is not None else "<error>"
                        trace.record_tool(
                            name=name,
                            args=args,
                            result=result_str,
                            duration_ms=dur_ms,
                        )
                except Exception:
                    pass

        registry.dispatch = _traced_dispatch
        _dispatch_patched = True
        logger.info("Pipeline Trace: registry.dispatch 已 patch（工具调用将记录到链路追踪）")
    except Exception as e:
        logger.debug(f"Pipeline Trace dispatch patch 失败: {e}")


# ── Delegation context enrichment: 子 Agent 自动注入 TaskState + 记忆 ──
_delegation_enricher_installed = False


def _install_delegation_enricher():
    """安装委派上下文富化钩子（幂等，只安装一次）。"""
    global _delegation_enricher_installed
    if _delegation_enricher_installed:
        return
    try:
        from backend.hermes.tools.delegate_tool import set_context_enricher
        from backend.service.delegation.context_enrichment import enrich_context

        set_context_enricher(enrich_context)
        _delegation_enricher_installed = True
        logger.info("委派上下文富化钩子已安装（子 Agent 自动注入 TaskState + 记忆）")
    except Exception as e:
        logger.warning(f"委派上下文富化钩子安装失败（子 Agent 将不会获得自动上下文注入）: {e}")


# ══════════════════════════════════════════════════════════════
# 多 Agent 委派：宿主侧桥接（可视化 / 留痕 / 结果回流 / 取消传导）
# ══════════════════════════════════════════════════════════════
# 这四件事 Hermes 都已经铺好了轨道，只是宿主没接线。这里全部走"零侵入"路线：
#   - 可视化：给父 Agent 挂 tool_progress_callback，Hermes 把 subagent.* 事件转发过来，
#     宿主自己拼 SSE 帧（不再需要在 delegate_tool 里埋点）
#   - 留痕：每个子 Agent 的生命周期落 delegation_tasks 表
#   - 回流：本轮结束后 drain process_registry.completion_queue，把子 Agent 结果作为
#     新的一轮注入（Hermes 的 process_registry 注释写明"CLI process_loop 与 gateway
#     每轮结束后 drain 并自动触发新 turn"——AgentForge 这两个消费者都不跑，此前结果
#     会永远留在队列里）
#   - 取消：cancel() 时按 subagent_id 调 Hermes 的 interrupt_subagent()

# 结果回流开关与轮数上限（运行时可改，便于测试与灰度）
def _delegation_followup_enabled() -> bool:
    return os.environ.get("AGENTFORGE_DELEGATION_FOLLOWUP", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _delegation_followup_rounds() -> int:
    try:
        return max(0, int(os.environ.get("AGENTFORGE_DELEGATION_FOLLOWUP_ROUNDS", "2")))
    except Exception:
        return 2


def _delegation_wait_seconds() -> float:
    """父轮内等待后台子 Agent 的上限秒数（默认 180s，0=不等待）。

    为什么要等：SSE 流以父轮结束为退出条件；不等就关流，子 Agent 的实时事件
    推进无人读取的队列，用户只能刷新页面才能看到状态更新。
    """
    try:
        return max(0.0, float(os.environ.get("AGENTFORGE_DELEGATION_WAIT_SECONDS", "180")))
    except Exception:
        return 180.0


def _store():
    """延迟导入留痕层：避免 hermes_adapter 早期导入链被 DB 模块拖累。"""
    from backend.service.delegation import store as _delegation_store

    return _delegation_store


def _submit_store_write(name: str, fn) -> None:
    """留痕写库丢到后台线程池执行。

    这条路径挂在 Agent 主循环的工具回调上（每次子 Agent 工具调用都会触发），
    数据库抖动时不能让它卡住主循环 —— 实测 MySQL 不可用时连接池单次要重试约 15 秒。
    线程池只有 4 个 worker，配合 store 侧的熔断不会堆积。
    """
    try:
        from backend.infrastructure.safe_executor import safe_submit

        safe_submit(f"delegation.{name}", fn)
    except Exception:
        # 兜底**不**同步执行 fn：fn 是留痕写库，同步跑会卡住 Agent 主循环
        # （MySQL 不可用时连接池单次要重试约 15 秒），正是本函数要避免的事。
        # safe_submit 只在执行器已关闭时抛异常（进程关闭期间），此时放弃本次留痕即可。
        logger.opt(exception=True).warning(
            f"留痕任务提交失败，已放弃本次留痕（{name}）"
        )


def build_subagent_progress_callback(
    *,
    thread_queue=None,
    thread_id: Optional[str] = None,
    user_id: int = 0,
    session_id_getter=None,
    active_ids: Optional[set] = None,
    turn_ids: Optional[set] = None,
):
    """构造父 Agent 的 ``tool_progress_callback``：Hermes 转发来的子 Agent 事件

    触发点：``delegate_tool._build_child_progress_callback`` 会把子 Agent 的事件
    （``subagent.start / text / tool / complete``，附带 subagent_id / depth / model /
    toolsets / tokens 等身份字段）转发到父 Agent 的 ``tool_progress_callback``。
    父 Agent 自身的工具进度也走同一通道，这里按 ``subagent.`` 前缀过滤。

    返回的回调永不抛异常 —— 它跑在 Agent 主循环里，任何异常都可能毁掉整轮对话。

    ``active_ids``：runtime 级的跨轮累积集合（保留用于其它消费方）。
    ``turn_ids``：**本轮**派出去的子 Agent id 集合（T3.2）—— ``_await_background_subagents``
    只等这一轮，避免上一轮超时/事件丢失的残留 id 让之后每一轮都先卡满等待上限。
    """
    # 工具调用计数：不逐次写库（会灌满共享线程池），每 10 次落一次，
    # 最终值由 complete 事件里的 tool_count 权威覆盖。
    _tool_counts: dict = {}
    _TOOL_FLUSH_EVERY = 10

    def _cb(event_type, tool_name=None, preview=None, args=None, **kw):
        try:
            et = str(event_type or "")
            if not et.startswith("subagent."):
                return  # 父自身工具进度，不关心

            from backend.service.delegation.sse_bridge import SUBAGENT_EVENT_TO_FRAME, push_frame

            frame_type = SUBAGENT_EVENT_TO_FRAME.get(et)
            subagent_id = str(kw.get("subagent_id") or "")
            store = _store()
            parent_sid = str(session_id_getter() or "") if session_id_getter else None

            if frame_type == "subagent_start":
                if active_ids is not None and subagent_id:
                    active_ids.add(subagent_id)
                if turn_ids is not None and subagent_id:
                    turn_ids.add(subagent_id)
                push_frame(thread_queue, frame_type, {
                    "subagent_id": subagent_id,
                    "goal": kw.get("goal") or preview or "",
                    "depth": kw.get("depth") or 0,
                    "model": kw.get("model") or "",
                })
                _submit_store_write("started", functools.partial(
                    store.record_subagent_started,
                    subagent_id=subagent_id,
                    goal=str(kw.get("goal") or preview or ""),
                    model=kw.get("model"),
                    depth=int(kw.get("depth") or 0),
                    thread_id=thread_id,
                    user_id=int(user_id or 0),
                    parent_session_id=parent_sid,
                    child_session_id=kw.get("child_session_id"),
                ))
                return

            if frame_type == "subagent_token":
                if preview:
                    push_frame(thread_queue, frame_type, {
                        "subagent_id": subagent_id,
                        "content": preview,
                    })
                return

            if frame_type == "subagent_tool":
                push_frame(thread_queue, frame_type, {
                    "subagent_id": subagent_id,
                    "tool_name": tool_name or "",
                    "preview": preview or "",
                    "tool_call_id": kw.get("tool_call_id"),
                    "context_result": kw.get("context_result"),
                    "stage": kw.get("stage", "started"),
                })
                if subagent_id and kw.get("stage", "started") == "started":
                    _tool_counts[subagent_id] = _tool_counts.get(subagent_id, 0) + 1
                    if _tool_counts[subagent_id] % _TOOL_FLUSH_EVERY == 0:
                        _submit_store_write("tool_count", functools.partial(
                            store.set_tool_count, subagent_id, _tool_counts[subagent_id],
                        ))
                return

            if frame_type == "subagent_complete":
                tokens = kw.get("tokens") or {}
                push_frame(thread_queue, frame_type, {
                    "subagent_id": subagent_id,
                    "status": kw.get("status", "completed"),
                    "summary": preview or "",
                    "duration_seconds": kw.get("duration_seconds", 0),
                    "tokens": tokens,
                    "api_calls": kw.get("api_calls", 0),
                })
                _submit_store_write("completed", functools.partial(
                    store.record_subagent_completed,
                    subagent_id=subagent_id,
                    status=str(kw.get("status") or "completed"),
                    tool_count=kw.get("tool_count"),
                    api_calls=int(kw.get("api_calls") or 0),
                    input_tokens=int((tokens or {}).get("input") or 0),
                    output_tokens=int((tokens or {}).get("output") or 0),
                    duration_seconds=float(kw.get("duration_seconds") or 0),
                    summary=preview or None,
                    error=kw.get("error"),
                    child_session_id=kw.get("child_session_id"),
                ))
                if active_ids is not None and subagent_id:
                    active_ids.discard(subagent_id)
                if turn_ids is not None and subagent_id:
                    turn_ids.discard(subagent_id)
                return
        except Exception:
            logger.opt(exception=True).debug("子 Agent 进度回调异常（已忽略）")

    return _cb


def _event_owned_by(evt: dict, session_ids: set) -> bool:
    """严格归属判定：三个身份字段任一命中才算本会话的事件。"""
    if not session_ids:
        return False
    for key in ("session_key", "parent_session_id", "origin_session_id"):
        val = evt.get(key)
        if val and str(val) in session_ids:
            return True
    return False


def drain_owned_delegation_events(session_ids: set, *, max_events: int = 5):
    """取回属于本会话的后台完成事件，返回 ``[(evt, text), ...]``。

    - 未匹配的事件**原样放回队列**：多用户同进程下绝不消费别人的事件
    - async_delegation 事件走 Hermes 的投递认领（claim）：已被其它消费者认领的跳过
    - 取回上限之外的也放回队列，避免一次注入炸掉上下文
    """
    if not session_ids:
        return []

    from tools.process_registry import format_process_notification, process_registry

    q = process_registry.completion_queue
    popped: list = []
    while len(popped) < 200:
        try:
            popped.append(q.get_nowait())
        except Exception:
            break

    owned, foreign = [], []
    for evt in popped:
        if isinstance(evt, dict) and _event_owned_by(evt, session_ids):
            owned.append(evt)
        else:
            foreign.append(evt)

    for evt in foreign:  # 放回：不属于本会话的一律不动
        try:
            q.put(evt)
        except Exception:
            pass

    out: list = []
    for evt in owned:
        if len(out) >= max_events:
            try:
                q.put(evt)
            except Exception:
                pass
            continue
        if evt.get("type") == "async_delegation":
            # 注意函数名：模块级是 claim_event_delivery(evt, consumer)（返回 claim_id /
            # None / ""），DB 级的 claim_completion_delivery(delegation_id, claim_id) 是
            # 另一个两参函数——早期这里调错了名字，异常被吞成 None，事件被静默丢弃。
            claim_id = None
            try:
                from tools.async_delegation import claim_event_delivery

                claim_id = claim_event_delivery(evt, "agentforge")
            except Exception as e:
                logger.warning(f"委派事件认领异常（放回队列重试）: {e}")
                claim_id = None
            if claim_id is None:
                # 已被其它消费者认领 / 认领失败：放回队列，交给后续轮次或下次启动，
                # 绝不在宿主侧静默丢弃（丢了就再也回不来）。
                try:
                    q.put(evt)
                except Exception:
                    pass
                continue
            evt["_claim_id"] = claim_id
        try:
            text = format_process_notification(evt)
        except Exception as e:
            logger.debug(f"委派完成事件格式化失败: {e}")
            text = None
        out.append((evt, text))
    if foreign:
        logger.debug(f"完成队列中有 {len(foreign)} 个事件不属于本会话，已放回")
    return out


def _persist_drained_event(evt: dict, *, thread_id: Optional[str], user_id: int,
                           parent_session_id: Optional[str]) -> None:
    """把回流的事件落库（留痕）。投递确认在注入成功之后单独做。"""
    if evt.get("type") == "async_delegation" and evt.get("results") is not None:
        _store().reconcile_from_completion_event(
            evt,
            thread_id=thread_id,
            user_id=int(user_id or 0),
            parent_session_id=parent_session_id,
        )


def _confirm_event_delivered(evt: dict) -> None:
    """注入成功后确认投递：Hermes 的 WAL 不再重放 + 留痕表标记已回流。"""
    delegation_id = str(evt.get("delegation_id") or "")
    if not delegation_id:
        return
    try:
        from tools.async_delegation import mark_completion_delivered

        mark_completion_delivered(delegation_id)
    except Exception:
        logger.debug(f"确认投递失败（Hermes 侧）: {delegation_id}")
    try:
        _store().mark_delivered(delegation_id)
    except Exception:
        logger.debug(f"确认投递失败（留痕侧）: {delegation_id}")


def _requeue_event(evt: dict) -> None:
    """注入失败时把事件放回队列，留给后续轮次/下次启动重试（Hermes 的 WAL 也会兜底）。

    同时释放认领（release_completion_delivery），否则该行会以"已认领"状态卡住
    300 秒才可被重新认领。
    """
    try:
        from tools.async_delegation import release_completion_delivery

        did = str(evt.get("delegation_id") or "")
        cid = str(evt.get("_claim_id") or "")
        if did and cid:
            release_completion_delivery(did, cid)
    except Exception:
        logger.debug("释放认领失败（已忽略）", exc_info=False)
    try:
        from tools.process_registry import process_registry

        process_registry.completion_queue.put(evt)
    except Exception:
        pass


def _merge_followup_result(base: dict, extra: dict) -> None:
    """把回流轮的产出并入主结果（token / api_calls / messages / 最终答案）。

    关于 token：`run_conversation` 的返回 dict 里**没有** token 字段 ——
    token 统计是从 agent 的累计属性读的（`self._agent.session_prompt_tokens` /
    `session_completion_tokens` / `session_total_tokens`，见 run() 的「Token 统计」段）。
    这些属性是**累计值**，且在 `_inject_delegation_followups` 之后才读，
    所以 token 已经自动包含回流轮，这里不需要（也无法）合并。
    这里补的是 `messages`：回流轮的消息链此前被整个丢弃，
    导致 process_log 缺一段、task_state 也看不到回流轮的最后一条 assistant。
    """
    if not isinstance(base, dict) or not isinstance(extra, dict):
        return
    base_final = base.get("final_response") or ""
    extra_final = extra.get("final_response") or ""
    if extra_final:
        base["final_response"] = f"{base_final}\n\n{extra_final}".strip() if base_final else extra_final
    try:
        base["api_calls"] = int(base.get("api_calls") or 0) + int(extra.get("api_calls") or 0)
    except Exception:
        pass

    # 数字型 token 字段：只要任一侧真的有就相加。
    # （当前 vendored 版本的 result 里没有这些键，保留是为了将来 vendor 加上后不再丢数据。）
    for key in ("tokens", "prompt_tokens", "completion_tokens", "total_tokens"):
        if key in extra or key in base:
            try:
                base[key] = int(base.get(key) or 0) + int(extra.get(key) or 0)
            except Exception:
                pass

    # 消息链拼接（回流轮那段不能丢）
    base_msgs = base.get("messages")
    extra_msgs = extra.get("messages")
    if isinstance(extra_msgs, list) and extra_msgs:
        base["messages"] = (base_msgs + extra_msgs) if isinstance(base_msgs, list) else list(extra_msgs)


def _apply_delegation_env_defaults() -> None:
    """D1：把 Hermes 的 delegation 旋钮设成对 Web 多用户场景更合理的默认值。

    只在环境变量未显式设置时生效（可被 .env / docker-compose 覆盖）。
    Hermes 的优先级：config.yaml > env > 内置默认，所以这里不改 config.yaml。
    """
    defaults = {
        # 后台委派槽位：Hermes 默认 3 且是**进程级**的，多用户同进程会互相挤占
        "DELEGATION_MAX_CONCURRENT_CHILDREN": "6",
        # 子 Agent 墙钟上限：Hermes 默认 None（无上限），Web 端需要一个兜底
        "DELEGATION_CHILD_TIMEOUT_SECONDS": "900",
    }
    for key, val in defaults.items():
        if not os.environ.get(key):
            os.environ[key] = val
            logger.info(f"委派默认值: {key}={val}（可用环境变量覆盖）")


_delegation_dispatch_patched = False


def _normalize_goal_text(text: str) -> str:
    import re as _re

    return _re.sub(r"\s+", " ", str(text or "")).strip().lower()


def find_overlapping_goals(goals, threshold: float = 0.72):
    """找出同一批委派里"疑似重复"的子任务对（C3）。

    返回 ``[(i, j, ratio), ...]``。用 difflib 序列相似度做廉价判定：
    框架层拦不住（也不该拦）LLM 的拆分决策，但必须让它"可见可查"——
    否则同一件事被派给 3 个子 Agent，token 白烧且结果互相冲突。
    """
    from difflib import SequenceMatcher

    norm = [_normalize_goal_text(g) for g in (goals or [])]
    hits = []
    for i in range(len(norm)):
        for j in range(i + 1, len(norm)):
            if not norm[i] or not norm[j]:
                continue
            ratio = SequenceMatcher(None, norm[i], norm[j]).ratio()
            if ratio >= threshold:
                hits.append((i, j, round(ratio, 3)))
    return hits


def _warn_on_overlapping_delegation(function_args: dict) -> None:
    """委派前检查同批任务是否语义重叠，重叠则告警（框架层只告警不拦截）。"""
    if not isinstance(function_args, dict):
        return
    tasks = function_args.get("tasks")
    goals = []
    if isinstance(tasks, list):
        goals = [
            str((t or {}).get("goal") or "")
            for t in tasks
            if isinstance(t, dict) and (t or {}).get("goal")
        ]
    single = function_args.get("goal")
    if not goals and single:
        goals = [str(single)]
    if len(goals) < 2:
        return
    hits = find_overlapping_goals(goals)
    if not hits:
        return
    detail = "; ".join(
        f"#{i}≈#{j}(相似度 {ratio}): {goals[i][:60]} | {goals[j][:60]}" for i, j, ratio in hits
    )
    logger.warning(
        f"[DELEGATION-OVERLAP] 同一批委派存在疑似重复子任务（{len(hits)} 对）：{detail}"
    )


def _patch_delegate_dispatch_for_overlap() -> None:
    """在真实调用路径上做重叠检测（C3）。

    delegate_task 在 agent_runtime_helpers 里被提前拦截走
    ``AIAgent._dispatch_delegate_task``，**不经过 registry.dispatch**，
    所以在 registry 上包一层看不到它；这里包 AIAgent 的方法。
    """
    global _delegation_overlap_patched
    if _delegation_overlap_patched:
        return
    try:
        from run_agent import AIAgent

        original = AIAgent._dispatch_delegate_task

        def _wrapped(self, function_args):
            try:
                _warn_on_overlapping_delegation(function_args)
            except Exception:
                logger.opt(exception=True).debug("委派重叠检测失败（已忽略）")
            return original(self, function_args)

        AIAgent._dispatch_delegate_task = _wrapped
        _delegation_overlap_patched = True
        logger.info("委派重叠检测已挂载（同批任务语义重复会告警）")
    except Exception as e:
        logger.debug(f"委派重叠检测挂载失败（忽略）: {e}")


_delegation_overlap_patched = False


def _patch_delegation_dispatch_for_quota() -> None:
    """B5：后台委派池满时 Hermes 会**静默降级为同步执行**（父轮被阻塞，用户无感）。

    这里在宿主侧包一层 dispatch，把"池满降级"变成一条明确的日志 + 一条留痕记录。
    之所以用 monkey-patch：AgentForge 已有 `_patch_dispatch_for_trace` 的同款先例，
    且 delegate_tool 是"调用时按模块属性解析"，patch 生效且不碰 Hermes 源码。
    """
    global _delegation_dispatch_patched
    if _delegation_dispatch_patched:
        return
    try:
        from tools import async_delegation as _ad

        original = _ad.dispatch_async_delegation_batch

        def _wrapped(**kwargs):
            res = original(**kwargs)
            try:
                # T3.3：记录"本轮派发过批次"——子 Agent 的 subagent.start 回调可能延迟
                # （daemon 池饱和时 worker 未及时启动），等待逻辑不能只依赖 id 集合非空。
                _sig = _TURN_DISPATCH_CTX.get(None)
                if _sig is not None and isinstance(res, dict) and res.get("status") != "rejected":
                    _sig["dispatched"] = int(_sig.get("dispatched") or 0) + 1
            except Exception:
                pass
            try:
                if isinstance(res, dict) and res.get("status") == "rejected":
                    goals = kwargs.get("goals") or []
                    logger.warning(
                        "后台委派池已满，Hermes 将降级为同步执行（父轮会被阻塞）: "
                        f"{res.get('error') or 'capacity'}"
                    )
                    _store().record_rejected_sync(
                        goals=[str(g) for g in goals],
                        thread_id=_THREAD_ID_CTX.get(None),
                        user_id=int(_CURRENT_USER_ID_CTX.get(0) or 0),
                        parent_session_id=str(kwargs.get("parent_session_id") or ""),
                        reason=str(res.get("error") or ""),
                    )
            except Exception:
                logger.opt(exception=True).debug("委派池满留痕失败（已忽略）")
            return res

        _ad.dispatch_async_delegation_batch = _wrapped
        _delegation_dispatch_patched = True
        logger.info("委派调度已包装（池满降级可观测）")
    except Exception as e:
        logger.debug(f"委派调度包装失败（忽略）: {e}")


_HERMES_AVAILABLE = False


def _ensure_hermes():
    global _HERMES_AVAILABLE
    if _HERMES_AVAILABLE:
        return True
    try:
        from run_agent import AIAgent as _A
        from agent.conversation_loop import run_conversation as _C
        from agent.memory_manager import MemoryManager as _M
        _HERMES_AVAILABLE = True
        logger.info("✅ Hermes AIAgent 加载成功")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Hermes 加载失败: {e}")
        return False


def prewarm_hermes():
    """应用启动阶段预热 Hermes：预导入核心模块 + 注册免费 Web 搜索。

    首次请求创建 AIAgent 时，Hermes 需要导入大量模块（run_agent、conversation_loop、
    memory_manager、tools/registry 及 50+ 插件发现），耗时 ~6-8s。把这些开销从首次请求
    转移到应用启动阶段（lifespan），用户打开页面时预热已完成，首次会话延迟大幅降低。

    注意：项目工具不在预热阶段注册——它们按用户 toolset 权限在 _get_agent() 中
    注册，确保每个用户只能看到自己有权限的工具。
    """
    _t0 = time.monotonic()
    try:
        # 1. 预导入核心模块（触发插件发现、provider 注册等重量级 import 链）
        _ensure_hermes()
        _t1 = time.monotonic()

        # 2. 注册免费 Web 搜索（DuckDuckGo）—— 纯进程内嵌入时插件发现不加载 web 插件
        _ensure_ddgs_web_search()
        _t2 = time.monotonic()

        # 3. 预触发 Hermes 工具发现（get_tool_definitions 内部会扫描 registry，
        #    首次调用会加载所有 enabled_toolsets 的工具定义，后续调用直接命中缓存）
        #    注意：agentforge_project 此时可能尚无工具注册，预热仅触发 Hermes
        #    内部的工具发现缓存机制，项目工具会在首次 _get_agent() 时按需注册。
        #    HERMES_DESKTOP=1 让桌面 GUI 工具（close_terminal 等）的 check_fn
        #    返回 True，避免 Web 环境下每 turn 产生 "check_fn returned False" WARNING。
        #    工具实际被调用时 handler 内部会返回错误提示用户。
        os.environ.setdefault("HERMES_DESKTOP", "1")
        try:
            from model_tools import get_tool_definitions as _get_tool_defs
            _get_tool_defs(
                # 禁用 file toolset，强制使用 Code Mode (run_python)
                # delegation 始终启用：子 Agent 委派是核心能力，不纳入权限控制
                enabled_toolsets=["terminal", "web", "skills", "agentforge_project", "delegation"],
                quiet_mode=True,
            )
            _t3 = time.monotonic()
        except Exception as _e:
            logger.warning(f"Hermes 工具发现预热跳过（不阻断）: {_e}")
            _t3 = time.monotonic()

        # 4. models.dev 数据加载（AgentForge 定制：彻底离线化）
        #    数据已静态预置到 backend/config/models_dev.json（随项目打包），
        #    fetch_models_dev() 只读该静态文件，不再发起任何网络请求。
        #    无需后台预取线程，首次调用时直接从静态文件加载到内存。
        _md_cnt = 0
        try:
            from agent.models_dev import fetch_models_dev
            _md = fetch_models_dev()
            _md_cnt = len(_md) if _md else 0
            _t3b = time.monotonic()
        except Exception as _e:
            logger.warning(f"models.dev 加载失败（不阻断）: {_e}")

        _tw = time.monotonic()
        logger.info(
            f"Hermes 预热完成 ({_tw - _t0:.1f}s): "
            f"核心={_t1 - _t0:.1f}s, 搜索={_t2 - _t1:.1f}s, "
            f"工具发现={_t3 - _t2:.1f}s, models={_md_cnt} providers"
        )
    except Exception as exc:
        logger.warning(f"Hermes 预热失败（不阻断启动）: {exc}")


# SSE 流式重置哨兵：放进 thread_queue 里通知 chat_controller "把刚才转发出去的
# token 全部作废、清空重来"（对应既有的 stream_reset SSE 事件）。用一个专门的类
# 而不是普通字符串/dict，避免跟真实的文本 chunk（也可能恰好是个字符串化的 dict）
# 混淆——chat_controller 只需要 `is instance(chunk, HermesStreamReset)` 判断。
class HermesStreamReset:
    """哨兵对象：出现在 thread_queue 里代表"清空已转发的 token，重新开始累积"。"""
    __slots__ = ()


HERMES_STREAM_RESET = HermesStreamReset()


# 占位文案列表（过短的通用开场白，过滤掉）
_THINKING_PLACEHOLDERS = [
    "好的",
    "好的，",
    "我明白了",
    "收到",
    "明白",
    "了解",
]


def _is_placeholder_text(text: str) -> bool:
    """判断是否为过短的占位文案。"""
    if not text or len(text.strip()) < 5:
        return True
    text_stripped = text.strip()
    for placeholder in _THINKING_PLACEHOLDERS:
        if text_stripped == placeholder or text_stripped.startswith(placeholder):
            return True
    return False


def _build_process_log(all_messages: List[dict], final_text: str) -> str:
    """提取思考过程中的推理文本（简化版，对齐 eyes-agent）。

    只保留 assistant 的旁白（content），丢弃 tool_calls 和 tool 结果。
    同时丢弃与 final_response 重复的最后一条 assistant 文本。

    关键：all_messages 包含完整会话历史，必须只取本轮新增部分。
    """
    notes: List[str] = []
    final_stripped = (final_text or "").strip()

    # 找到最后一条 user 消息的位置，只处理它之后的消息（本轮新增）
    last_user_idx = -1
    for i in range(len(all_messages) - 1, -1, -1):
        if isinstance(all_messages[i], dict) and all_messages[i].get("role") == "user":
            last_user_idx = i
            break
    current_turn_msgs = all_messages[last_user_idx + 1:] if last_user_idx >= 0 else all_messages

    for msg in current_turn_msgs:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        # assistant 消息：取 content（旁白）
        if role == "assistant":
            note = (msg.get("content") or "").strip()
            # 过滤：空内容、与最终回答重复、过短的占位文案
            if note and note != final_stripped and not _is_placeholder_text(note):
                # 去重：检查是否已存在相似内容
                def _normalize(s: str) -> str:
                    # 去掉标点和空白
                    return ''.join(c for c in s if c not in '，。！？、：；""''（） \t\n\r')
                note_norm = _normalize(note)
                is_dup = False
                for n in notes:
                    n_norm = _normalize(n)
                    # 完全相同或包含关系
                    if note_norm == n_norm or note_norm in n_norm or n_norm in note_norm:
                        is_dup = True
                        break
                    # 高相似度（>80%）
                    longer, shorter = (note_norm, n_norm) if len(note_norm) > len(n_norm) else (n_norm, note_norm)
                    if shorter in longer and len(shorter) / len(longer) > 0.8:
                        is_dup = True
                        break
                if not is_dup:
                    notes.append(note[:2000])

    try:
        return json.dumps(notes, ensure_ascii=False)
    except Exception:
        return "[]"


def delete_hermes_session_history(thread_id: str) -> bool:
    """删除 Hermes 侧 SessionDB（HERMES_HOME/state.db）里 thread_id 对应的会话记录。

    前端删除会话时联动调用，避免 Hermes 那边留下孤儿会话记录。
    同时清理 task_states 表中该 thread_id 的任务状态（task_state 跟会话历史同生命周期）。
    找不到对应 session 或库不可用时静默返回 False，不阻断自身的删除流程。
    """
    try:
        from hermes_state import SessionDB
        db = SessionDB()
        sid = db.resolve_session_id(thread_id)
        if not sid:
            return False
        deleted = db.delete_session(sid)
        if deleted:
            logger.info(f"Hermes 会话记录已联动删除 thread={thread_id} session={sid}")
            # 顺手清理 task_states（内存 + state.db），task_state 跟着会话历史走
            try:
                from backend.context.task_state import get_task_state_maintainer
                get_task_state_maintainer().clear(thread_id)
            except Exception as ts_exc:
                logger.debug(f"task_state 联动清理失败（不阻断）: {ts_exc}")
            # 清理 Agent 缓存中该 thread_id 对应的条目（避免残留过期 agent）
            try:
                with HermesRuntime._agents_lock:
                    keys_to_remove = [k for k in HermesRuntime._agents if thread_id in k]
                    for k in keys_to_remove:
                        HermesRuntime._agents.pop(k, None)
                # 同步清理全局 runtime 缓存
                with _runtime_cache_lock:
                    rt_keys = [k for k in _runtime_cache if thread_id in k]
                    for k in rt_keys:
                        _runtime_cache.pop(k, None)
                if keys_to_remove or rt_keys:
                    logger.info(f"会话删除联动清理缓存: agents={len(keys_to_remove)}, runtime={len(rt_keys)}")
            except Exception as cache_exc:
                logger.debug(f"缓存联动清理失败（不阻断）: {cache_exc}")
        return deleted
    except Exception as exc:
        logger.warning(f"Hermes 会话记录联动删除失败（不阻断）: thread={thread_id}, error={exc}")
        return False


class HermesRuntime:
    """Hermes AIAgent 运行时
    
    改进：Agent 缓存支持 TTL 过期 + LRU 淘汰，防止长期运行内存泄漏。
    """

    # 缓存结构: key → (agent, created_at, perm_fingerprint)
    _agents: Dict[str, tuple] = OrderedDict()  # (agent, created_at, perm_fingerprint)
    _agents_lock = threading.Lock()  # 缓存读写锁（多线程安全）
    _AGENT_CACHE_TTL = 3600  # 缓存有效期：1 小时
    _AGENT_CACHE_MAX_SIZE = 100  # 最大缓存条目数

    def __init__(self, user_id: int, model_config: dict, system_prompt: str,
                 thread_id: Optional[str] = None, username: Optional[str] = None,
                 disabled_toolsets: Optional[set] = None):
        self.user_id = user_id
        self.model_config = model_config or {}
        self.system_prompt = system_prompt
        self.thread_id = thread_id or f"user-{user_id}-default"
        self.username = username
        # 禁用的工具集（如微信端禁用 terminal 以杜绝无审批 UI 下的危险命令）。
        self.disabled_toolsets = set(disabled_toolsets or ())
        # 本运行时当前活跃的子 Agent（由子 Agent 事件回调维护，供 cancel() 传导取消）
        self._active_subagent_ids: set = set()
        _ensure_hermes()
        _THREAD_ID_CTX.set(self.thread_id)
        if username:
            _CURRENT_USERNAME_CTX.set(username)
        if user_id:
            _CURRENT_USER_ID_CTX.set(int(user_id))
        self._agent = self._get_agent()

    @classmethod
    def _evict_expired_agents(cls):
        """清理过期和超量的 Agent 缓存（类方法）。加锁保护，确保多线程安全。"""
        with cls._agents_lock:
            now = time.time()
            to_remove = []

            # 清理过期缓存
            for key, (agent, created_at, perm_fp) in list(cls._agents.items()):
                if now - created_at > cls._AGENT_CACHE_TTL:
                    to_remove.append(key)
                    logger.debug(f"Agent 缓存过期: {key[:50]}...")

            # LRU 淘汰超量缓存
            if len(cls._agents) - len(to_remove) > cls._AGENT_CACHE_MAX_SIZE:
                # 按创建时间排序，移除最旧的
                sorted_keys = sorted(
                    cls._agents.keys(),
                    key=lambda k: cls._agents[k][1]
                )
                excess = len(cls._agents) - cls._AGENT_CACHE_MAX_SIZE
                for key in sorted_keys[:excess]:
                    if key not in to_remove:
                        to_remove.append(key)
                        logger.debug(f"Agent 缓存 LRU 淘汰: {key[:50]}...")

            # 执行清理
            for key in to_remove:
                cls._agents.pop(key, None)

            if to_remove:
                logger.info(f"Agent 缓存清理: 移除 {len(to_remove)} 条，剩余 {len(cls._agents)} 条")

    def _perm_fingerprint(self) -> str:
        """当前用户权限指纹：role + 可用 toolset 集合。
        角色升降级 / toolset 调整后指纹变化 → 缓存键失效 → 重建 agent，
        杜绝「降级后仍持有旧工具集」的越权残留。"""
        try:
            if not self.user_id:
                return ""
            from backend.permission.checker import get_user_hermes_tools
            from backend.service.auth.permission_service import get_user_role
            role = get_user_role(int(self.user_id)) or "user"
            tools = ",".join(sorted(get_user_hermes_tools(int(self.user_id))))
            return f"{role}|{tools}"
        except Exception:
            return ""

    def _cache_key(self):
        c = self.model_config
        disabled = ",".join(sorted(self.disabled_toolsets))
        # AgentForge-PATCH: 权限指纹加入缓存键
        return f"{self.user_id}:{self.thread_id}:{c.get('config_type')}|{c.get('api_url')}|{c.get('model_name')}|{disabled}|{self._perm_fingerprint()}"

    def _get_agent(self):
        key = self._cache_key()

        # ── 加锁检查缓存 ──
        with self._agents_lock:
            # 检查缓存是否命中且未过期
            if key in self._agents:
                agent, created_at, cached_perm_fp = self._agents[key]
                now = time.time()

                # 检查 TTL 过期
                if now - created_at > self._AGENT_CACHE_TTL:
                    logger.debug(f"Agent 缓存过期，重建: {key[:50]}...")
                    self._agents.pop(key, None)
                else:
                    # 检查权限指纹是否变化
                    current_perm_fp = self._perm_fingerprint()
                    if cached_perm_fp == current_perm_fp:
                        logger.debug(f"Agent 缓存命中: {key[:50]}...")
                        # LRU：移到末尾（最近使用）
                        self._agents.move_to_end(key)
                        return agent
                    else:
                        logger.info(f"权限指纹变化，重建 Agent: {key[:50]}...")
                        self._agents.pop(key, None)

        # 执行缓存清理（在创建新 Agent 前）
        HermesRuntime._evict_expired_agents()

        # 每用户技能视图：仅首次创建 agent 时计算一次（agent 按 (user, thread) 缓存）
        self._skills_scope = _compute_user_skill_scope(self.user_id) if self.user_id else None
        self._perm_fp_at_build = self._perm_fingerprint()
        if self._skills_scope is not None:
            logger.debug(f"用户 {self.user_id} 技能视图: {len(self._skills_scope)} 个可见技能")

        _init_t0 = time.monotonic()
        # 主机白名单守卫（幂等包装 terminal handler）
        _patch_terminal_host_guard()
        from run_agent import AIAgent
        from hermes_state import SessionDB
        cfg = self.model_config
        ct = (cfg.get('config_type') or '').upper()

        # ── 确保免费 Web 搜索可用（DuckDuckGo）──
        _ensure_ddgs_web_search()

        _init_t1 = time.monotonic()

        kwargs = {
            "skip_context_files": True,
            "quiet_mode": True,
            "session_id": self.thread_id,
            "thread_id": self.thread_id,
            "user_id": str(self.user_id),
            # AIAgent 的 session_db 构造参数默认 None，不传就等于关闭 Hermes
            # 自带的 state.db 持久化——_flush_messages_to_session_db 会在
            # `if not self._session_db` 直接静默跳过，_recover_session_history
            # 后续也永远查不到会话。显式传入，让下面 _recover_session_history
            # 依赖的持久化真正生效。
            "session_db": SessionDB(),
            # 关闭 Hermes 自带的跨会话文件记忆（MEMORY.md/USER.md）。
            # AgentForge 已构建三层记忆架构（MySQL + 向量库 + Neo4j 图谱），
            # 通过 AgentForgeMemoryProvider 提供 prefetch/handle_tool_call，
            # 内置文件记忆完全冗余，关闭后不再创建 MemoryStore、不注入系统提示词。
            "skip_memory": True,
            # AgentForge-PATCH: 每用户技能视图（None=全量，super_admin/admin）
            "skills_scope": self._skills_scope,
        }

        # ── 动态工具集：基于用户角色权限 ──
        # get_user_hermes_tools 按角色返回允许的工具集（已排除 vision），
        # 此处再过滤一次 vision 作为双保险。
        # skills / agentforge_project 始终追加：其内部工具自带二次权限检查，
        # 无权限的调用会在工具内部被拒绝，不影响其他工具正常使用。
        hermes_tools: List[str] = []
        if self.user_id:
            hermes_tools = get_user_hermes_tools(self.user_id)
        # A 组：禁用文件操作工具集（file），强制使用 Code Mode (run_python)
        # 这样可以显著减少 Token 消耗（95%+）和工具调用次数
        hermes_tools = [t for t in hermes_tools if t not in ("vision", "session_search", "memory", "file")]
        # 禁用指定工具集（微信端禁用 terminal，避免无审批 UI 下的危险命令）。
        if self.disabled_toolsets:
            hermes_tools = [t for t in hermes_tools if t not in self.disabled_toolsets]
        # skills / agentforge_project / delegation 始终追加：
        # - skills / agentforge_project 内部工具自带二次权限检查，无权限的调用会被拒绝
        # - delegation（子 Agent 委派）是框架核心能力，不纳入权限控制
        # session_search / memory 已禁用（AgentForge 记忆架构原生支持跨会话，
        # 无需 Hermes 原生的文件记忆和历史会话检索工具）。
        kwargs["enabled_toolsets"] = hermes_tools + ["skills", "agentforge_project", "delegation"]

        # 记录本 agent 实际启用的 toolset 集合（用于技能 requires_toolsets 过滤的 contextvar）
        self._enabled_toolsets = set(kwargs["enabled_toolsets"])

        # ── 按用户 toolset 权限注册项目工具 ──
        # agentforge_project 是 Hermes 框架层面的分组名（始终在 enabled_toolsets 中），
        # 但注册前会检查每个工具的 _toolset 属性是否在用户权限中，实现细粒度过滤。
        # 项目工具的 _toolset（email/data/notification/schedule）与角色的
        # hermes_tools 字段（前端「AI 对话工具-扩展」组）一一对应，按组授权。
        # utility 工具（时间/TODO 等）已改为 __always_available__，不走权限过滤。
        _register_project_tools(enabled_toolsets=set(hermes_tools))

        # ── 模型名清理：去除上下文窗口后缀 ──
        # Hermes 内部会在模型名后追加 [1m]/[128k] 等上下文窗口标签，但大部分
        # 第三方 API（DeepSeek、Qwen、GLM 等）不接受这种格式，需要在此剥离。
        _raw_model = cfg.get('model_name', '')
        _clean_model = _re.sub(r'\[\d+[km]\]$', '', _raw_model.strip(), flags=_re.IGNORECASE)
        if _clean_model != _raw_model.strip():
            logger.debug(f"模型名上下文标签已剥离: {_raw_model} → {_clean_model}")

        # ── Base URL 自动补全 /v1 ──
        # 大多数 OpenAI 兼容 API 需要 /v1 路径前缀（DashScope / OpenAI / GLM 等），
        # 但用户在前端配置时可能只填了根域名。Hermes 的 OpenAI SDK 会在 base_url
        # 后直接拼 /chat/completions，不会自动插入 /v1，缺少时会导致 HTTP 404。
        # Anthropic 端点（URL 含 /anthropic 或 /messages）走 Messages API，不需要此处理。
        _raw_url = cfg.get('api_url', '').strip().rstrip('/')
        _is_anthropic_url = bool(_raw_url and ('/anthropic' in _raw_url or '/messages' in _raw_url))

        # ── 确定 Provider ──
        # 优先使用用户在模型配置中手动指定的 provider，留空则先查 Hermes 注册的 Provider
        # 列表（支持 hostname/base_url 匹配），再用内置 fallback 字典兜底。
        _configured_provider = (cfg.get('provider') or '').strip().lower()
        _detected_provider = ""
        _host = ""
        if _raw_url:
            try:
                from urllib.parse import urlparse as _urlparse
                _host = (_urlparse(_raw_url).hostname or "").lower()
                # 1. 优先使用 Hermes ProviderProfile 注册表（动态，新厂商无需改代码）
                try:
                    from backend.hermes.providers import get_provider_profile, list_providers as _list_providers
                    for _profile in _list_providers():
                        _p_host = (_profile.hostname or "").lower()
                        if _p_host and _p_host in _host:
                            _detected_provider = _profile.name
                            break
                        _p_base = (_profile.base_url or "").lower()
                        if _p_base and _host in _p_base:
                            _detected_provider = _profile.name
                            break
                except Exception:
                    pass
                # 2. Hermes 未注册的 Provider 走内置 fallback（最小保留，仅覆盖常见场景）
                if not _detected_provider:
                    _PROVIDER_FALLBACK: dict = {
                        "api.deepseek.com": "deepseek",
                        "api.openai.com": "openai",
                        "api.anthropic.com": "anthropic",
                        "dashscope.aliyuncs.com": "alibaba",
                        "dashscope-intl.aliyuncs.com": "alibaba",
                        "coding.dashscope.aliyuncs.com": "alibaba-coding-plan",
                        "coding-intl.dashscope.aliyuncs.com": "alibaba-coding-plan",
                        "api.moonshot.ai": "kimi-coding",
                        "api.moonshot.cn": "kimi-coding-cn",
                        "api.kimi.com": "kimi-coding",
                        "open.bigmodel.cn": "zhipu",
                        "api.minimax.io": "minimax",
                        "api.minimaxi.com": "minimax-cn",
                        "api.x.ai": "xai",
                        "generativelanguage.googleapis.com": "gemini",
                    }
                    _detected_provider = _PROVIDER_FALLBACK.get(_host, "")
            except Exception:
                pass
        _final_provider = _configured_provider or _detected_provider
        if _final_provider:
            logger.debug(f"Provider: {_final_provider}" + (
                " (手动指定)" if _configured_provider else f" (自动检测 {_host} → {_detected_provider})"
            ))

        if ct == 'URL':
            if _raw_url and not _is_anthropic_url and not _re.search(r'/v\d+$', _raw_url):
                _raw_url = f"{_raw_url}/v1"
                logger.debug(f"Base URL 自动补全 /v1: {cfg.get('api_url', '').strip().rstrip('/')} → {_raw_url}")
            kwargs["base_url"] = _raw_url
            kwargs["api_key"] = cfg.get('api_key', '')
            kwargs["model"] = _clean_model
            kwargs["provider"] = _final_provider
        elif ct == 'OLLAMA':
            ip = cfg.get('ip_address', 'localhost')
            kwargs["base_url"] = f"http://{ip}:{cfg.get('port', 11434)}/v1"
            kwargs["api_key"] = "ollama"
            kwargs["model"] = _clean_model
            kwargs["provider"] = _final_provider or "ollama"
        else:
            kwargs["base_url"] = cfg.get('api_url', '')
            kwargs["api_key"] = cfg.get('api_key', '')
            kwargs["provider"] = _final_provider

        # ── reasoning_config：传递给 AIAgent 的思考深度配置 ──
        # 不再写入 Hermes 全局 config.yaml（会导致跨用户覆盖），
        # 而是直接作为构造参数传递，实现每会话独立配置。
        try:
            reasoning_effort = (cfg.get("reasoning_effort") or "").strip()
            if reasoning_effort:
                # parse_reasoning_effort: "low"/"medium"/"high"/... → {"enabled": True, "effort": "..."}
                # 空字符串或无效值返回 None，AIAgent 会使用全局默认。
                from backend.hermes.hermes_constants import parse_reasoning_effort
                _rc = parse_reasoning_effort(reasoning_effort)
                if _rc is not None:
                    kwargs["reasoning_config"] = _rc
                    logger.debug(f"reasoning_config: {_rc}")
        except Exception as e:
            logger.debug(f"reasoning_config 解析跳过: {e}")

        # ── 构建降级链（fallback_model）传递给 Hermes AIAgent ──
        # 从 model_route_settings 读取降级链，自动故障转移由 Hermes 内部 error_classifier +
        # try_activate_fallback 处理，无需 AgentForge 额外干预。
        try:
            from backend.service.model_router import router as _model_router
            # mask_keys=False: 内部使用，直接解密 api_key（供 Hermes AIAgent 使用）
            _fallback_configs = _model_router.get_fallback_chain_configs(mask_keys=False)
            if _fallback_configs:
                _fallback_chain = []
                for _fc in _fallback_configs:
                    _fb_entry = {
                        "provider": _fc.get("provider") or "",
                        "model": _fc.get("model_name") or "",
                        "base_url": _fc.get("api_url") or "",
                    }
                    _fc_key = _fc.get("api_key") or ""
                    if _fc_key:
                        _fb_entry["api_key"] = _fc_key
                    _fallback_chain.append(_fb_entry)
                if _fallback_chain:
                    kwargs["fallback_model"] = _fallback_chain
                    logger.debug(f"降级链已配置: {[fb.get('model') for fb in _fallback_chain]}")
        except Exception as e:
            logger.debug(f"构建降级链跳过: {e}")

        _init_t2 = time.monotonic()
        agent = AIAgent(**kwargs)
        _init_t3 = time.monotonic()

        # ── 手动注册 AgentForgeMemoryProvider ──
        # skip_memory=True 禁用了 Hermes 内建文件记忆（MEMORY.md/USER.md），
        # 但也阻止了外部 memory provider 插件加载。我们已有完整的三层记忆架构，
        # 需要在此手动创建 MemoryManager 并注册 AgentForgeMemoryProvider，
        # 否则 sync_turn 永远不会被调用，记忆提取流程完全断裂。
        try:
            from agent.memory_manager import MemoryManager as _HermesMemoryManager
            from backend.memory.agentforge_provider import AgentForgeMemoryProvider

            _mem_manager = _HermesMemoryManager()
            _af_provider = AgentForgeMemoryProvider()
            if _af_provider.is_available():
                _mem_manager.add_provider(_af_provider)
                # 初始化 provider（传入 session_id/user_id 等上下文）
                _init_kwargs = {
                    "session_id": self.thread_id or "",
                    "platform": "web",
                    "hermes_home": str(getattr(agent, "_hermes_home", "")),
                    "agent_context": "primary",
                    "user_id": self.user_id,
                }
                _mem_manager.initialize_all(**_init_kwargs)
                agent._memory_manager = _mem_manager
                logger.info(
                    f"AgentForgeMemoryProvider 已注册 user={self.user_id} "
                    f"thread={self.thread_id}"
                )
            else:
                logger.warning("AgentForgeMemoryProvider 不可用，记忆提取功能禁用")
        except Exception as _mem_err:
            logger.warning(f"Memory provider 注册失败: {_mem_err}")

        # ── 上下文压缩策略替换 ──
        # 根据 CONTEXT_STRATEGY 环境变量决定使用哪种压缩策略：
        #   - default     : 保留 Hermes 自带的 ContextCompressor（不动）
        #   - fact_anchor : 包一层事实锚定代理，压缩前先抽关键事实
        #   - none        : 直接禁用压缩（适合超长上下文模型或测试）
        # 工厂返回 None 时：strategy='default' 表示保留现状；strategy='none' 表示清空。
        try:
            from backend.context.config import get_context_strategy
            from backend.context.factory import create_engine

            _strategy = get_context_strategy()
            if _strategy == "default":
                # 保持 Hermes 默认，什么都不做
                pass
            else:
                # 其它策略：基于 Hermes 已创建的 ContextCompressor 构造策略引擎
                # 把 Hermes 自己的 context_compressor 作为代理内核传入
                _inner_cc = getattr(agent, "context_compressor", None)
                if _strategy == "none":
                    # 注意：不要把 context_compressor 置 None —— Hermes 在响应记账路径会无条件
                    # 解引用它，None 会被误判为 API 失败并触发重试。只关掉开关。
                    agent.compression_enabled = False
                    logger.debug("上下文策略: none（已禁用压缩）")
                else:
                    _engine = create_engine(
                        _strategy,
                        engine_kwargs={"inner": _inner_cc},
                    )
                    if _engine is not None:
                        agent.context_compressor = _engine
                        logger.debug(
                            f"上下文策略已切换: {_strategy} → {type(_engine).__name__}"
                        )
        except Exception as _ctx_err:
            # 策略加载失败不应阻塞 agent 创建，回退到 Hermes 默认
            logger.warning(f"上下文策略加载失败，保留 Hermes 默认: {_ctx_err}")

        # ── 注册可观测性钩子 ──
        try:
            from backend.observer.trace_observer import register_trace_hooks
            register_trace_hooks(user_id=self.user_id)
        except Exception as e:
            logger.warning(f"TraceObserver 注册失败: {e}")

        # 缓存 Agent（带时间戳和权限指纹）—— 加锁保护，避免并发覆盖
        perm_fp = self._perm_fingerprint()
        with self._agents_lock:
            self._agents[key] = (agent, time.time(), perm_fp)
            cache_count = len(self._agents)
        logger.info(
            f"创建 Hermes AIAgent user={self.user_id} thread={self.thread_id} "
            f"model={kwargs.get('model','')} 总耗时={_init_t3 - _init_t0:.1f}s "
            f"(工具注册={_init_t1 - _init_t0:.1f}s 参数构建={_init_t2 - _init_t1:.1f}s "
            f"AIAgent构造={_init_t3 - _init_t2:.1f}s) 缓存条目={cache_count}"
        )
        return agent

    def _recover_session_history(self, thread_id: str) -> list:
        """从 hermes_state.SessionDB（HERMES_HOME/state.db）按 thread_id 恢复完整会话历史。

        对应 CLI 的 ``--resume``：Hermes 每轮会把消息持久化到 SessionDB，下一轮 run()
        时若本地已有该 thread_id 的 session，就把它恢复为 conversation_history，实现
        跨轮完整上下文——不再依赖前端注入的裁剪后 history（否则只有 7 条，上下文缺失）。

        无本地 session / 恢复失败时返回 []，由调用方回退到前端注入的 history 兜底。
        """
        try:
            from hermes_state import SessionDB
            db = SessionDB()
            sid = db.resolve_session_id(thread_id)
            if not sid:
                return []
            # repair_alternation=True：本函数是 live replay 的恢复点。
            # vendored 契约（hermes_state.py:6511-6517）规定 live replay 必须传它，
            # 否则一次持久化的交替违规（如取消/中断路径留下的 user;user，
            # 见 chat/stream.py 取消分支）会在该会话余生里**每个请求**都重复触发
            # 预请求防御性修复并打 warning（修复只改 per-request list，不改存储）。
            history = db.get_messages_as_conversation(sid, repair_alternation=True)
            if history:
                logger.debug(f"Hermes 恢复会话历史 thread={thread_id} session={sid} 条数={len(history)}")
            return history or []
        except Exception as exc:
            logger.warning(f"Hermes 会话历史恢复失败（回退前端注入）: {exc}")
            return []

    def _subagent_owner_session_ids(self) -> set:
        """当前运行时"拥有"的 Hermes 会话 id（后台委派事件的归属判定）。

        AgentForge 把 thread_id 当作 Hermes 的 session_id，压缩轮换时会出现第二个 id，
        因此把 thread_id、当前 session_id、上一轮 session_id 都收进来。
        """
        ids = set()
        for cand in (
            self.thread_id,
            getattr(self._agent, "session_id", None),
            getattr(self, "_last_session_id", None),
        ):
            if cand:
                ids.add(str(cand))
        return ids

    def _live_subagent_ids(self) -> Optional[set]:
        """Hermes 侧**真实在跑**的子 Agent id 集合。

        用于以 Hermes 为准裁剪本轮的等待集合（防止 subagent.complete 事件丢失导致永久等待）。
        不可用（import 失败等）时返回 None，表示"无法裁剪"，调用方退回只看集合。
        """
        try:
            from tools.delegate_tool import list_active_subagents

            out = set()
            for rec in list_active_subagents() or ():
                sid = rec.get("subagent_id") if isinstance(rec, dict) else None
                if sid:
                    out.add(str(sid))
            return out
        except Exception as e:
            logger.debug(f"list_active_subagents 不可用，跳过裁剪: {e}")
            return None

    async def _await_background_subagents(
        self, turn_ids: Optional[set] = None, turn_dispatch: Optional[dict] = None
    ) -> int:
        """等**本轮**派出去的后台子 Agent 跑完（有界等待），返回仍在跑的数量。

        为什么必须等：顶层 delegate_task 被 Hermes 强制后台执行，父轮几秒就返回；
        若不等，宿主的 SSE 流会立即关闭（stream.py 的消费循环以 hermes_task 结束为
        退出条件），子 Agent 之后产生的 subagent_* 事件就推进了一个没人读的队列——
        用户只有刷新页面、靠 delegation_tasks 回填才能看到状态。
        在同一个请求里等到子 Agent 结束再走结果回流，用户就能全程实时看到。

        - **轮次作用域**（T3.2）：只等 ``turn_ids``（本轮）里的 id，不再看跨轮累积的
          ``self._active_subagent_ids``。否则只要有一个子 Agent 在上一轮超时
          （子 Agent 上限 900s 远大于等待上限 180s）或 complete 事件丢失，
          之后**每一轮**对话都会先卡满等待上限。
        - **派发信号**（T3.3）：进入条件为"本轮派发过批次 **或** turn_ids 非空"。
          派发后给 ``_DELEGATION_START_GRACE_S`` 的宽限，兜住 start 事件延迟的竞态。
        - **以 Hermes 为准裁剪**：每轮用 ``list_active_subagents()`` 剔除已不在真实
          在跑集合里的 id（防事件丢失导致的永久等待）。
        - 有界：默认 180s（AGENTFORGE_DELEGATION_WAIT_SECONDS 可调，0=不等待）
        - 可取消：用户中断（_interrupt_requested）时立刻停止等待
        - 不阻塞事件循环：用 asyncio.sleep 轮询，不占用工作线程
        """
        wait_s = _delegation_wait_seconds()
        ids = turn_ids if turn_ids is not None else set()
        dispatched = int((turn_dispatch or {}).get("dispatched") or 0)

        # 没等待预算，且本轮既没派发也没有活跃 id → 无事可等
        if wait_s <= 0 or (not ids and dispatched <= 0):
            return len(ids)

        # 派发过批次时，给"第一个 start 事件"留宽限期（T3.3）
        grace_deadline = time.monotonic() + (_DELEGATION_START_GRACE_S if dispatched > 0 else 0.0)
        deadline = time.monotonic() + wait_s
        announced = False
        while time.monotonic() < deadline:
            if getattr(self._agent, "_interrupt_requested", False):
                logger.info("用户已中断，停止等待后台子 Agent")
                break

            # 以 Hermes 为准裁剪：已不在真实在跑集合里的 id 剔除
            # （取不到时返回 None = 无法裁剪，退回只看集合本身）
            try:
                live = self._live_subagent_ids()
            except Exception:
                live = None
            if live is not None:
                for sid in list(ids):
                    if sid not in live:
                        ids.discard(sid)
                        self._active_subagent_ids.discard(sid)

            if not ids:
                if dispatched <= 0:
                    break  # 本轮没派发过且无活跃 id → 没什么可等
                if live:
                    pass  # 真实在跑但 start 事件还没到 → 继续等它进 ids
                elif time.monotonic() >= grace_deadline:
                    break  # 宽限期已过且确实没有在跑的子 Agent → 结束

            if not announced and (ids or live):
                logger.info(
                    f"等待 {len(ids) or len(live or ())} 个后台子 Agent 完成"
                    f"（上限 {wait_s:.0f}s，期间 SSE 保持开启）"
                )
                announced = True
            await asyncio.sleep(0.5)

        remaining = len(ids)
        if remaining:
            logger.warning(
                f"仍有 {remaining} 个子 Agent 未完成（等待超时或已中断）；"
                "结果会在后续轮次回流，留痕见 delegation_tasks"
            )
        return remaining

    async def _drain_with_grace(self, session_ids, *, grace_s: float = 5.0):
        """drain 一次；没有事件时在宽限期内短暂重试。

        子 Agent 的 ``subagent_complete`` 帧由子线程发出，而**批次级**完成事件由
        Hermes 的 batch worker 在所有子任务 join 之后才投递，两者之间有毫秒级到
        秒级的间隙。不留宽限期就会出现"子 Agent 已完成但回流没触发"的假空白。
        """
        deadline = time.monotonic() + max(0.0, grace_s)
        while True:
            items = drain_owned_delegation_events(
                self._subagent_owner_session_ids() | set(session_ids or ())
            )
            if items:
                return items
            if time.monotonic() >= deadline:
                return []
            await asyncio.sleep(0.3)

    async def _inject_delegation_followups(self, *, loop, ctx, run_conversation,
                                           result, session_ids) -> None:
        """把后台子 Agent 的结果注入成新的一轮对话（Hermes 的既有契约）。

        process_registry 的注释写明"CLI process_loop 与 gateway 每轮结束后 drain 并
        自动触发新 turn"；AgentForge 两个消费者都不跑，所以宿主自己补上这一步。

        约定：
          - 只消费属于本会话的事件（多用户同进程下绝不串台），别人的原样放回队列
          - 先落库留痕，再跑 LLM：下一轮失败也能在 delegation_tasks 里查到结果
          - 注入成功才确认投递（Hermes 的 WAL 不再重放）；失败则放回队列重试
          - 全程吞异常：回流失败不该毁掉已经成功的本轮回答
        """
        if not _delegation_followup_enabled():
            return
        rounds = _delegation_followup_rounds()
        if rounds <= 0:
            return

        import functools as _functools

        for i in range(rounds):
            try:
                items = await self._drain_with_grace(session_ids)
            except Exception as e:
                logger.debug(f"委派完成事件 drain 失败: {e}")
                return
            if not items:
                return
            texts = [t for _, t in items if t]
            if not texts:
                return

            parent_sid = str(getattr(self._agent, "session_id", None) or self.thread_id or "")
            for evt, _ in items:
                try:
                    _persist_drained_event(
                        evt,
                        thread_id=self.thread_id,
                        user_id=self.user_id or 0,
                        parent_session_id=parent_sid,
                    )
                except Exception:
                    logger.opt(exception=True).debug("委派留痕失败（已忽略）")

            injected = "\n\n".join(texts)
            logger.info(f"后台委派结果回流: {len(items)} 个事件 → 追加第 {i + 1} 轮")
            try:
                extra = await loop.run_in_executor(
                    None,
                    ctx.run,
                    _functools.partial(
                        run_conversation, self._agent,
                        user_message=injected,
                        system_message=self.system_prompt,
                        conversation_history=None,
                    ),
                )
            except Exception as e:
                logger.warning(
                    f"委派结果注入轮失败（结果已落库 delegation_tasks，可在后台查询）: {e}"
                )
                for evt, _ in items:
                    _requeue_event(evt)  # 放回，留给后续轮次/下次启动
                return

            if isinstance(extra, dict):
                _merge_followup_result(result, extra)
            for evt, _ in items:
                _confirm_event_delivered(evt)

            # 轮换后的 session_id 也要纳入归属集合，避免同一会话多次回流漏认领
            session_ids = self._subagent_owner_session_ids() | set(session_ids or ())

    async def run(self, user_message, history: Optional[List[dict]] = None,
                  thread_queue: Optional["queue.Queue"] = None,
                  mode: str = "normal") -> Dict[str, Any]:
        """执行 Hermes 决策（异步，run_conversation 在后台线程运行避免阻塞事件循环）
        user_message: str 或 list[dict]（多模态 content_blocks）
        mode: 会话模式（透传给钩子，通用脚手架不解析此字段）"""
        import functools
        from agent.conversation_loop import run_conversation

        # 文本预览（兼容 list 格式的多模态消息）
        if isinstance(user_message, list):
            _text_for_log = " ".join(
                b.get("text", "") for b in user_message if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            _text_for_log = str(user_message)

        # 恢复会话历史：优先从 hermes_state.SessionDB（HERMES_HOME/state.db）按 thread_id
        # 恢复**完整历史**（库级 CLI --resume 语义）——本地有 session 时，跨轮上下文靠它恢复，
        # 前端注入的 history 仅作为"换服务器/无本地 session"场景的兜底（避免把裁剪后的
        # 7 条当完整历史，否则就会出现"7次限制"导致上下文缺失）。见 _recover_session_history。
        conv_history = self._recover_session_history(self.thread_id)
        if not conv_history and history:
            for msg in history:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    conv_history.append({"role": msg["role"], "content": msg["content"]})

        # ── 对话开始日志 ──
        _msg_preview = _text_for_log[:50] + "..." if len(_text_for_log) > 50 else _text_for_log
        logger.debug(f"用户提问: {_msg_preview}")

        # 流式状态追踪
        _stream_state = {"last_tool_key": None, "streamed_since_reset": False}
        _stream_stats = {"chunk_count": 0, "char_count": 0, "tool_calls": []}
        _iteration_count = [0]  # 用列表包装以便在闭包中修改

        def _on_stream_delta(text: str) -> None:
            if not text or thread_queue is None:
                return
            _stream_state["streamed_since_reset"] = True
            _stream_stats["chunk_count"] += 1
            _stream_stats["char_count"] += len(text)
            try:
                thread_queue.put(text)
            except Exception:
                pass

        def _on_step(_iteration: int, prev_tools: list) -> None:
            if not prev_tools:
                return
            try:
                key = json.dumps(prev_tools, sort_keys=True, ensure_ascii=False, default=str)
            except Exception:
                key = repr(prev_tools)
            if key == _stream_state["last_tool_key"]:
                return
            _stream_state["last_tool_key"] = key
            _stream_state["streamed_since_reset"] = False
            _tool_names = [
                t.get("name", "?") if isinstance(t, dict) else str(t)
                for t in prev_tools
            ]
            _stream_stats["tool_calls"].extend(_tool_names)
            _iteration_count[0] += 1
            # 简洁的工具调用日志
            logger.debug(f"调用工具 [{', '.join(_tool_names)}]")
            if thread_queue is not None:
                try:
                    thread_queue.put(HERMES_STREAM_RESET)
                except Exception:
                    pass

        # loop.run_in_executor 底层用的是 concurrent.futures 线程池，
        # ThreadPoolExecutor.submit() 不会像 asyncio 的 Task/call_soon 那样自动
        # 把当前 contextvars.Context 带进工作线程（新线程默认拿到的是空 Context）。
        # 所以这里必须显式 copy_context() 后用 ctx.run(...) 提交，否则
        # _THREAD_ID_CTX 等 ContextVar 在工作线程里读到的永远是默认值 None。
        _THREAD_ID_CTX.set(self.thread_id)
        # 用户身份上下文：工具调用（skill_manage 等）在工作线程中执行，
        # 必须显式设置才能在 copy_context() 后传递到工作线程。
        if self.user_id:
            _CURRENT_USER_ID_CTX.set(int(self.user_id))
        if self.username:
            _CURRENT_USERNAME_CTX.set(self.username)
        # 任务规划实时推送：把 thread_queue 注入 context var，
        # 让 todo_add/todo_update 工具执行后能直接把 tool_output SSE 事件塞进队列
        _TODO_QUEUE_CTX.set(thread_queue)
        # P0: 子 Agent 委派可视化 — 把 thread_queue 注入委派 ContextVar（兼容路径；
        # 生产热路径已改为在父 Agent 上挂 tool_progress_callback，见 build_subagent_progress_callback）
        try:
            from backend.service.delegation.sse_bridge import _DELEGATION_SSE_QUEUE_CTX
            _DELEGATION_SSE_QUEUE_CTX.set(thread_queue)
        except Exception:
            pass  # 委派不可用时静默跳过
        # 子 Agent 凭证继承 — 把系统 model_config 注入 ContextVar，
        # 让子 Agent 直接使用父 Agent 的显式凭证（来自 model_configs 表），
        # 不走 Hermes credential_pool（可能拿到不同/过期的 key）
        try:
            from backend.service.delegation.sse_bridge import _DELEGATION_MODEL_CONFIG_CTX
            _DELEGATION_MODEL_CONFIG_CTX.set(self.model_config or {})
        except Exception:
            pass
        # 权限指纹校验：角色/toolset 变更 → 重建 agent（防降级后旧工具集越权，微信/Web 同链路）
        try:
            if getattr(self, "_perm_fp_at_build", None) != self._perm_fingerprint():
                logger.warning(f"用户 {self.user_id} 权限已变更，重建 agent")
                self._agent = self._get_agent()
        except Exception:
            pass
        # 每用户技能视图：技能工具（skills_list/skill_view）在工作线程按此过滤
        try:
            from tools.skills_tool import SKILLS_SCOPE_CTX as _SKILLS_SCOPE_CTX
            _SKILLS_SCOPE_CTX.set(getattr(self, "_skills_scope", None))
        except Exception:
            pass
        # 技能 requires_toolsets 过滤：本 agent 实际启用的 toolset 集合
        try:
            from tools.skills_tool import _AGENTFORGE_AVAILABLE_TOOLSETS_CTX
            _AGENTFORGE_AVAILABLE_TOOLSETS_CTX.set(getattr(self, "_enabled_toolsets", None))
        except Exception:
            pass
        # 记忆引用映射：初始化空 dict，provider.prefetch() 填充，stream.py 读取
        _memory_refs: dict = {}
        try:
            from backend.memory.agentforge_provider import _MEMORY_REFS_CTX
            _MEMORY_REFS_CTX.set(_memory_refs)
        except Exception:
            pass
        # ── 本轮委派作用域（T3.2 / T3.3）──
        # 必须在 _mem_ctx = copy_context() **之前**设置：回调与派发包装都在
        # run_conversation 的线程里跑（该线程用 _mem_ctx.run 进入），
        # 只有先 set 才能被 contextvars 复制带过去。
        #   this_turn_ids：本轮派出去的子 Agent id（等待只看这些，不看跨轮累积集合）
        #   _turn_signal：{"dispatched": n} 本轮派发过几批（兜住 start 事件延迟的竞态）
        this_turn_ids: set = set()
        _turn_signal: dict = {"dispatched": 0}
        try:
            _TURN_DISPATCH_CTX.set(_turn_signal)
        except Exception:
            pass
        _mem_ctx = contextvars.copy_context()
        # Bind inside the copied worker context so concurrent requests cannot share
        # result scopes. Child workers inherit this binding with their own logical IDs.
        from backend.context.tool_results.runtime import bind_runtime
        from backend.context.task_state import get_task_state_maintainer
        _result_scope = bind_runtime(
            self._agent, user_id=self.user_id, thread_id=self.thread_id,
            semantic_state=get_task_state_maintainer().get_state(self.thread_id),
        )
        _mem_ctx.run(_result_scope.__enter__)
        loop = asyncio.get_event_loop()
        start_time = time.monotonic()
        # 本轮开始/结束时的 Hermes 会话 id：后台委派事件按会话归属判定，
        # 压缩可能在本轮内轮换 session_id，因此前后都收进来。
        _run_session_ids = self._subagent_owner_session_ids()
        # step_callback 是 agent 实例级属性（不像 stream_callback 那样由
        # run_conversation/turn_context 每轮自动清理），HermesRuntime 会跨多轮
        # 对话复用同一个 agent 实例，必须在每次 run() 前显式挂上本轮的闭包、
        # 跑完后清掉，避免下一轮或其它调用路径拿到本轮已经失效的 thread_queue。
        self._agent.step_callback = _on_step
        # ── 子 Agent 事件桥接（可视化 + 留痕）──
        # Hermes 会把子 Agent 的 subagent.* 事件转发到父 Agent 的 tool_progress_callback，
        # 宿主在这里拼 SSE 帧并入队。此前靠改 delegate_tool 源码埋点，现改为零侵入。
        self._agent.tool_progress_callback = build_subagent_progress_callback(
            thread_queue=thread_queue,
            thread_id=self.thread_id,
            user_id=self.user_id or 0,
            session_id_getter=lambda: getattr(self._agent, "session_id", None),
            active_ids=self._active_subagent_ids,
            turn_ids=this_turn_ids,
        )
        # ── 工具回合文字不丢失 ──
        # stream_callback（= _stream_callback）在工具调用出现后会被 Hermes 屏蔽。
        # 使用 stream_delta_callback 代替：它同时覆盖工具前（_fire_stream_delta
        # 内部两个 callback 都会触发）和工具后（工具屏蔽路径只触发
        # stream_delta_callback）两个阶段。只挂一个避免重复推送。
        self._agent.stream_delta_callback = _on_stream_delta
        # Qwen 等模型通过 reasoning_content 字段流式输出思考过程，
        # 走 _fire_reasoning_delta → reasoning_callback，不走 stream_delta_callback。
        # 设为同一个回调确保思考过程不丢失。
        self._agent.reasoning_callback = _on_stream_delta
        try:
            result = await loop.run_in_executor(
                None,
                _mem_ctx.run,
                functools.partial(
                    run_conversation, self._agent,
                    user_message=user_message,
                    system_message=self.system_prompt,
                    conversation_history=conv_history or None,
                    # stream_callback 不传：避免与 stream_delta_callback 重复推送
                    # stream_delta_callback 已在上方设为 _on_stream_delta，覆盖全路径
                ),
            )
            # ── 后台委派：先在同一个请求内等它们跑完（否则 SSE 关流，前端只能靠刷新）──
            # 只等**本轮**派出去的（T3.2）；本轮派发过批次也会触发等待（T3.3）
            await self._await_background_subagents(this_turn_ids, _turn_signal)
            # ── 后台委派结果回流（A1）──
            # 父轮可能"派完就答"，子 Agent 的结果稍后才到；这里在轮末把属于本会话的
            # 完成事件注入成新的一轮，Supervisor 才能真正拿到子任务的产出。
            await self._inject_delegation_followups(
                loop=loop,
                ctx=_mem_ctx,
                run_conversation=run_conversation,
                result=result,
                session_ids=_run_session_ids,
            )
        except Exception as e:
            logger.error(f"❌ Hermes 运行失败: {e}")
            return {"final_response": "", "completed": False, "error": f"处理出错: {e}"}
        finally:
            _mem_ctx.run(_result_scope.__exit__, None, None, None)
            self._agent.step_callback = None
            self._agent.stream_delta_callback = None
            self._agent.reasoning_callback = None
            # 注意：已构建的子 Agent 在构建时就捕获了回调引用，这里置空只是防止
            # 后续调用路径拿到本轮已失效的 thread_queue，不影响在跑的后台子 Agent。
            self._agent.tool_progress_callback = None
            self._last_session_id = getattr(self._agent, "session_id", None)
        elapsed = time.monotonic() - start_time

        # 将记忆引用映射挂到 result，供 stream.py 解析 LLM 回答中的 [M1] 引用
        result["_memory_refs"] = _memory_refs

        final = result.get("final_response") or ""
        api_calls = result.get("api_calls", 0)
        _tool_calls = _stream_stats["tool_calls"]
        
        # ── 对话完成日志（简洁版）──
        _answer_preview = final[:80] + "..." if len(final) > 80 else final
        _answer_preview = _answer_preview.replace("\n", " ")
        logger.debug(f"AI 回答: {_answer_preview}")
        
        # Token 统计
        a = self._agent
        prompt_t = int(getattr(a, "session_prompt_tokens", 0) or 0)
        completion_t = int(getattr(a, "session_completion_tokens", 0) or 0)
        total_t = int(getattr(a, "session_total_tokens", 0) or (prompt_t + completion_t))
        cost = getattr(a, "session_estimated_cost_usd", 0) or 0
        logger.debug(f"Token: {total_t:,} (输入 {prompt_t:,} / 输出 {completion_t:,}) | 耗时 {elapsed:.1f}s | API {api_calls}次 | ${cost:.4f}")

        # 只有在"最终这一轮完全没有走通流式路径"时才整段兜底推送一次
        if thread_queue is not None and final and not _stream_state["streamed_since_reset"]:
            thread_queue.put(final)

        # 收集工具调用信息（用于 process_log）
        all_messages = result.get("messages", [])

        # ── task_state 异步更新 ─────────────────────────────────
        # run_conversation 完成后，all_messages 已包含本轮完整的 user + assistant 链。
        # 取最后一条 assistant（最终回复）+ 本轮 user_message 提交异步更新。
        # 失败降级：任何异常都不影响主流程（task_state.update 内部也有兜底）。
        try:
            from backend.context.task_state import get_task_state_maintainer

            _ts_maintainer = get_task_state_maintainer()
            _ts_last_assistant = ""
            for _m in reversed(all_messages):
                if isinstance(_m, dict) and _m.get("role") == "assistant":
                    _ts_last_assistant = _m.get("content") or ""
                    break
            # user_message 可能是多模态 content_blocks（list）——task_state 只吃纯文本，
            # 直接 .strip() 会 AttributeError 并把整块更新静默跳过（历史 bug）。
            _ts_user_text = user_message
            if isinstance(_ts_user_text, list):
                _ts_user_text = " ".join(
                    _b.get("text", "") for _b in _ts_user_text
                    if isinstance(_b, dict) and _b.get("type") == "text"
                )
            _ts_user_text = str(_ts_user_text or "")

            if _ts_user_text.strip() or _ts_last_assistant.strip():
                # 用 hermes 自带的 user_turn_count 作为轮次号（单调递增，跨 run 持久）
                _ts_turn = int(getattr(self._agent, "_user_turn_count", 1) or 1)

                # ⚠️ 必须用 self.thread_id：run() 没有 thread_id 形参，
                # 旧代码写裸 `thread_id` → NameError 被下面的 except 吞掉 →
                # task_state.update() **从未成功执行过**，整个会话级任务状态层恒为空。
                _ts_thread_id = self.thread_id

                def _update_ts():
                    try:
                        _ts_maintainer.update(
                            _ts_thread_id, _ts_user_text, _ts_last_assistant, _ts_turn
                        )
                    except Exception as _e:
                        logger.warning(f"task_state async update failed (degraded): {_e}")

                # 模块级共享线程池（懒加载，max_workers=2 足够）
                global _TS_POOL
                if _TS_POOL is None:
                    with _TS_POOL_LOCK:
                        if _TS_POOL is None:
                            import concurrent.futures
                            _TS_POOL = concurrent.futures.ThreadPoolExecutor(
                                max_workers=2, thread_name_prefix="task_state"
                            )
                try:
                    _TS_POOL.submit(_update_ts)
                except Exception as _e:
                    logger.debug(f"task_state submit failed (degraded): {_e}")
        except Exception as _e:
            logger.debug(f"task_state integration skipped: {_e}")
        tool_names = set()
        for msg in all_messages:
            if isinstance(msg, dict):
                for tc in (msg.get("tool_calls") or []):
                    fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                    tn = fn.get("name", "") if isinstance(fn, dict) else ""
                    if tn == "tool_call":
                        raw_args = fn.get("arguments")
                        try:
                            parsed = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                            tn = str(parsed.get("name") or "").strip()
                        except Exception:
                            tn = ""
                    if tn:
                        tool_names.add(tn)

        # ── 截取当前回合的消息 ──
        # all_messages 包含全部历史，_build_process_log 只需要本回合新增的。
        # 从后往前找到最后一个 role == "user" 的消息，它前面的都是历史。
        _turn_start = 0
        for _i in range(len(all_messages) - 1, -1, -1):
            if all_messages[_i].get("role") == "user":
                _turn_start = _i
                break
        _turn_msgs = all_messages[_turn_start:]
        process_log = _build_process_log(_turn_msgs, final)

        return {
            "final_response": final,
            "completed": result.get("completed", True),
            "process_log": process_log,
        }

    def cancel(self, message: Optional[str] = None) -> None:
        """用户主动暂停/停止：协作式中断当前正在跑的 run_conversation()。

        run() 里真正的 Hermes 决策跑在 loop.run_in_executor 起的线程池工作线程里
        （见 run() 内注释）——asyncio 层面对包这层的 Task 调 .cancel() 只能打断
        "await 等待它返回"这一步，CPython 线程无法被强行打断，工作线程会继续
        跑同一个 run_conversation 到自然结束（继续调 LLM/工具）。这正是
        "点了暂停、前端复位成已停止，Hermes 后台其实还在跑完整个回合"的根因——
        外层 asyncio 取消对它完全不生效。

        Hermes 自带 AIAgent.interrupt() 是专门为这种跨线程取消场景设计的协作式
        机制（backend/hermes/run_agent.py）：置 _interrupt_requested 标志、按
        当前执行线程 id 广播 tools.interrupt.set_interrupt(True, tid)（工具循环
        在下一轮迭代/下一次 tool 调用前检查该标志并退出，正在跑的并发工具线程
        也会被广播到）、并尝试中止当前正在进行的模型 HTTP 请求 socket（流式响应
        立即断开，不必等它读完这一个 chunk）。调用方（chat_controller 的
        token_stream_events）应在捕获到 SSE 生成器自身的 CancelledError 时立即
        调用本方法，让 Hermes 真正停下来，而不只是停止等待它的结果。
        best-effort：agent 尚未创建 / interrupt 内部异常都不应该阻断前端已经
        展示的"已取消"状态，只记警告。"""
        try:
            self._agent.interrupt(message)
            logger.info(f"🛑 已向 Hermes 发送取消信号 - user={self.user_id} thread={self.thread_id}")
        except Exception as exc:
            logger.warning(f"Hermes 取消信号发送失败（不影响前端已展示的取消状态）: {exc}")

        # ── 取消传导到子 Agent（B4）──
        # 顶层委派是后台执行的（daemon 线程池），agent.interrupt() 只作用于父 Agent 自己
        # 的工具循环；子 Agent 已被 Hermes 从父的 _active_children 摘掉，父的中断到不了它们。
        # 这里用 Hermes 现成的 interrupt_subagent() 按 subagent_id 逐个传导。
        self.interrupt_active_subagents()

    def interrupt_active_subagents(self) -> int:
        """中断本运行时派出去、且仍在跑的子 Agent。返回成功中断的数量。

        subagent_id 由子 Agent 事件回调（build_subagent_progress_callback）维护，
        complete 事件到达时移除；后台子 Agent 的 complete 可能晚于父轮结束，
        因此集合挂在 runtime 实例上（runtime 按 user+thread 缓存），跨轮仍可用。
        """
        ids = list(getattr(self, "_active_subagent_ids", ()) or ())
        if not ids:
            return 0
        hit = 0
        try:
            from tools.delegate_tool import interrupt_subagent
        except Exception as e:
            logger.debug(f"取消传导不可用（delegate_tool 未加载）: {e}")
            return 0
        for sid in ids:
            try:
                if interrupt_subagent(sid):
                    hit += 1
                    self._active_subagent_ids.discard(sid)
            except Exception as e:
                logger.debug(f"中断子 Agent {sid} 失败: {e}")
        if hit:
            logger.info(f"已向 {hit} 个后台子 Agent 传导取消 - thread={self.thread_id}")
        return hit


# ── 全局运行时缓存（LRU 淘汰，防内存泄漏） ──
_RUNTIME_CACHE_MAX = 100
_runtime_cache: OrderedDict = OrderedDict()
_runtime_cache_lock = threading.Lock()  # runtime 缓存读写锁（多线程安全）


def get_runtime(user_id: int, model_config: dict, system_prompt: str,
                 thread_id: Optional[str] = None, username: Optional[str] = None,
                 disabled_toolsets: Optional[set] = None) -> HermesRuntime:
    """按 (user_id, thread_id) 取 Hermes 运行时——thread_id 对齐应用的会话粒度
    （一个前端聊天窗口/一次定时任务执行），不传时退化为该用户的固定默认会话，
    避免同一用户不同 thread 的 Hermes 记忆互相串。

    disabled_toolsets：禁用的工具集（如微信端传 {"terminal"}，杜绝无审批 UI
    下的危险命令），参与缓存 key 判定，避免同 thread 先 web 后微信串用实例。

    缓存策略：OrderedDict LRU，超过 _RUNTIME_CACHE_MAX 时淘汰最久未使用的。"""
    resolved_thread_id = thread_id or f"user-{user_id}-default"
    key = f"{user_id}:{resolved_thread_id}:__rt__"
    _disabled = set(disabled_toolsets or ())

    # ── 加锁检查缓存 ──
    with _runtime_cache_lock:
        # 命中缓存 → 移到末尾（最近使用）
        if key in _runtime_cache:
            rt = _runtime_cache[key]
            if (rt.model_config == model_config and rt.system_prompt == system_prompt
                    and rt.disabled_toolsets == _disabled):
                _runtime_cache.move_to_end(key)
                # 更新 username 到 ContextVar（即使缓存命中也要更新）
                if username:
                    _CURRENT_USERNAME_CTX.set(username)
                if user_id:
                    _CURRENT_USER_ID_CTX.set(int(user_id))
                return rt

    # 缓存未命中 → 创建新实例（锁外创建，避免长时间持锁）
    rt = HermesRuntime(user_id, model_config, system_prompt, thread_id=resolved_thread_id,
                       username=username, disabled_toolsets=_disabled)

    # ── 加锁插入缓存 + LRU 淘汰 ──
    with _runtime_cache_lock:
        _runtime_cache[key] = rt
        # LRU 淘汰：超过上限时移除最久未使用的
        while len(_runtime_cache) > _RUNTIME_CACHE_MAX:
            evicted_key, evicted_rt = _runtime_cache.popitem(last=False)
            logger.debug(f"LRU 淘汰 HermesRuntime: {evicted_key}")

    return rt


# ── Terminal 主机白名单守卫（AgentForge-PATCH，借鉴 Eyes host_whitelist）──
_HOST_GUARDED_TOOLS: set = set()


def _patch_terminal_host_guard():
    """包装 Hermes terminal 工具 handler：ssh/scp 目标主机不在白名单 → 拦截。
    白名单为空时远程执行一律拒绝（secure-by-default）。幂等，可重复调用。"""
    try:
        from tools.registry import registry
        if "terminal" in _HOST_GUARDED_TOOLS:
            return
        entry = registry.get_entry("terminal")
        if entry is None:
            return
        _HOST_GUARDED_TOOLS.add("terminal")
        orig_handler = entry.handler

        def _guarded_handler(args, **_kw):
            cmd = ""
            if isinstance(args, dict):
                cmd = str(args.get("command") or args.get("cmd") or "")
            if cmd:
                try:
                    from backend.service.host_whitelist_service import extract_ssh_targets, is_host_allowed
                    from backend.service.agent_operation_log_service import record_operation as _log_op
                    from backend.service.command_blacklist_service import check_command_blacklist
                    
                    # ① 命令黑名单检查（优先于白名单检查）
                    blacklist_reason = check_command_blacklist(cmd)
                    if blacklist_reason:
                        uid = _CURRENT_USER_ID_CTX.get()
                        uname = _CURRENT_USERNAME_CTX.get() or ""
                        session_key = _THREAD_ID_CTX.get() or "unknown"
                        logger.warning(f"命令黑名单拦截: {cmd[:80]}（原因: {blacklist_reason}）")
                        # 审计留痕：拦截
                        _log_op(
                            thread_id=session_key, user_id=uid, username=uname,
                            tool_name="terminal", operation_type="blocked",
                            command=cmd, status=0,
                            error_message=f"命令黑名单拦截：{blacklist_reason}",
                        )
                        return (
                            f"[安全拦截] 该命令命中黑名单规则「{blacklist_reason}」，执行已被阻止。"
                            "如需执行，请联系管理员在系统管理-命令黑名单中调整规则。"
                        )
                    
                    targets = extract_ssh_targets(cmd)
                    if targets:
                        uid = _CURRENT_USER_ID_CTX.get()
                        uname = _CURRENT_USERNAME_CTX.get() or ""
                        session_key = _THREAD_ID_CTX.get() or "unknown"
                        for host in targets:
                            # ② 白名单 + 用户免密权限（system.manage）
                            if not is_host_allowed(host, uid):
                                logger.warning(f"主机白名单拦截: {host}（user={uid} 无权限或不在白名单）")
                                # 审计留痕：拦截
                                _log_op(
                                    thread_id=session_key, user_id=uid, username=uname,
                                    tool_name="terminal", operation_type="blocked",
                                    command=cmd, target_host=host, status=0,
                                    error_message=f"主机白名单拦截：{host} 不在白名单或用户无权限",
                                )
                                return (
                                    f"[安全拦截] 目标主机 {host} 不在白名单或当前用户无免密权限，远程执行已被阻止。"
                                    "请联系管理员在系统管理-主机白名单中配置。"
                                )
                            # ③ 免密放行但每条命令仍需人工审批（阻塞等待决议）
                            approval_id = register_pending_approval(
                                session_key, cmd, "远程主机执行命令需要人工审批", allow_permanent=False,
                            )
                            entry = _exec_approval_pending.get(approval_id)
                            if entry is not None:
                                entry["event"].wait(timeout=300)
                            decision = entry.get("decision") if entry else None
                            if decision in ("allow-once", "allow-session", "allow-always"):
                                # 审计留痕：审批通过 → 即将执行
                                _log_op(
                                    thread_id=session_key, user_id=uid, username=uname,
                                    tool_name="terminal", operation_type="ssh_remote",
                                    command=cmd, target_host=host, status=2,
                                    args_summary=f"approval={decision}",
                                )
                                # ④ 获批 → 用 paramiko 直接执行 SSH 命令（跨平台，密码不暴露）
                                # 直接返回结果字符串，不再放行到原始 handler（避免 Hermes 内部危险命令检测重复审批）
                                try:
                                    from backend.service.host_whitelist_service import execute_ssh_via_paramiko
                                    result = execute_ssh_via_paramiko(cmd, host)
                                    if result is not None:
                                        # 审计留痕：执行完成
                                        _log_op(
                                            thread_id=session_key, user_id=uid, username=uname,
                                            tool_name="terminal", operation_type="ssh_remote",
                                            command=cmd, target_host=host, status=1,
                                            args_summary=f"exit_code={result.get('exit_code', '?')}",
                                        )
                                        # 返回字符串格式（Hermes terminal 工具期望字符串）
                                        output = result.get("output", "")
                                        exit_code = result.get("exit_code", 0)
                                        if exit_code != 0:
                                            return f"执行失败（退出码 {exit_code}）:\n{output}"
                                        return output or "(命令无输出)"
                                    # paramiko 执行失败，返回错误信息
                                    return "[安全拦截] SSH 命令执行失败，请检查连接信息"
                                except Exception as e:
                                    logger.warning(f"SSH paramiko 执行异常: {e}")
                                    return f"[安全拦截] SSH 执行异常: {e}"
                            # 审计留痕：审批拒绝/超时
                            _log_op(
                                thread_id=session_key, user_id=uid, username=uname,
                                tool_name="terminal", operation_type="blocked",
                                command=cmd, target_host=host, status=0,
                                error_message=f"远程命令审批未通过: decision={decision}",
                            )
                            logger.warning(f"远程命令审批未通过: {cmd[:80]}")
                            return "[安全拦截] 远程主机命令未获审批或审批超时，已阻止执行。"
                except Exception:
                    logger.opt(exception=True).error("主机安全校验异常，已阻止执行")
                    return "[安全拦截] 安全校验异常，命令已阻止执行，请检查服务日志"
            return orig_handler(args, **_kw)

        entry.handler = _guarded_handler
        logger.info("🔒 terminal 主机白名单守卫已启用（白名单+免密权限+逐条审批）")
    except Exception as e:
        logger.debug(f"terminal 主机白名单包装失败: {e}")


# ── Exec 审批：危险命令统一审批协议 ──
#
# 复用 Hermes 自带的危险命令检测 + 审批机制（tools/approval.py
# check_all_command_guards）——所有执行工具（terminal、ssh_exec 等）最终都会调
# 同一个 check_all_command_guards()，所以一份接线就能同时盖住多条执行通道。
#
# 会话粒度：把 Hermes 的 session_key 钉死为 thread_id——一个前端聊天窗口就是
# 一次"会话"；同一个 thread_id 的多轮往返共享同一个 session_key，选"本会话内
# 始终允许"后，后续同一 pattern_key 的命令会被 Hermes 自带的 approve_session()/
# is_approved() 直接放行。
_EXEC_APPROVAL_DISPLAY_TTL_SECONDS = 300.0  # 仅用于兜底清理展示用 store，跟 Hermes 侧真实超时对齐
_exec_approval_lock = threading.Lock()
_exec_approval_pending: Dict[str, Dict[str, Any]] = {}   # approval_id -> entry
_exec_approval_by_session: Dict[str, str] = {}            # session_key -> 当前待审批的 approval_id


def register_pending_approval(session_key: str, command: str, description: str = "",
                               allow_permanent: bool = True) -> str:
    """登记一条待人工审批的命令，返回 approval_id。"""
    approval_id = uuid.uuid4().hex
    entry = {
        "approval_id": approval_id,
        "session_key": session_key,
        "command": command,
        "description": description,
        "allow_permanent": allow_permanent,
        "event": threading.Event(),
        "decision": None,
        "created_at": time.monotonic(),
    }
    with _exec_approval_lock:
        _exec_approval_pending[approval_id] = entry
        _exec_approval_by_session[session_key] = approval_id
    logger.info(f"⏸️ exec 待审批 session={session_key} id={approval_id} 命令: {command[:120]}")
    return approval_id


def get_pending_approval(session_key: str) -> Optional[Dict[str, Any]]:
    """取当前 session 尚未决议的待审批命令（没有则 None）。

    惰性过期：Hermes 内部 _await_gateway_decision() 有自己的超时（config
    approvals.timeout_seconds，默认 300s），超时后会自行放弃阻塞并让命令失败，
    但不会回头通知我们清理这份仅供展示用的登记——这里按 created_at 兜底过期，
    避免前端一直显示一张实际上早已失效的审批卡片，也避免 dict 无限增长。
    """
    with _exec_approval_lock:
        approval_id = _exec_approval_by_session.get(session_key)
        if not approval_id:
            return None
        entry = _exec_approval_pending.get(approval_id)
        if not entry or entry["decision"] is not None:
            return None
        if time.monotonic() - entry["created_at"] > _EXEC_APPROVAL_DISPLAY_TTL_SECONDS:
            _exec_approval_by_session.pop(session_key, None)
            _exec_approval_pending.pop(approval_id, None)
            return None
        return {
            "approval_id": entry["approval_id"],
            "command": entry["command"],
            "description": entry["description"],
            "allow_permanent": entry["allow_permanent"],
        }


def resolve_pending_approval(approval_id: str, decision: str,
                             confirmed_by_user_id=None,
                             confirmed_by_name: str = None) -> bool:
    """前端点击按钮后调用：decision 取值 allow-once / allow-session / deny。

    除了标记我们自己这份登记（供 SSE 展示用）外，必须显式唤醒被 Hermes
    tools.approval._await_gateway_decision() 阻塞的执行线程——那才是真正
    放行/拒绝命令执行的地方，我们这份 store 只是镜像出来给前端渲染卡片。

    confirmed_by_user_id / confirmed_by_name: 审核人信息（审计留痕）。
    """
    with _exec_approval_lock:
        entry = _exec_approval_pending.get(approval_id)
        if not entry or entry["decision"] is not None:
            return False
        entry["decision"] = decision
        # AgentForge-PATCH: 唤醒主机白名单审批等待线程（守卫 wrapper 阻塞于此 event）
        try:
            entry["event"].set()
        except Exception:
            pass
        session_key = entry["session_key"]
        if _exec_approval_by_session.get(session_key) == approval_id:
            _exec_approval_by_session.pop(session_key, None)
        _exec_approval_pending.pop(approval_id, None)

    # AgentForge-PATCH: 决议登记到审批记录器（会话落库时写入 exec_approval_logs 审计表）
    try:
        from backend.utils.exec_approval_recorder import record as _record_approval
        _record_approval(
            thread_id=session_key,
            command=entry.get("command", ""),
            decision=decision,
            allow_permanent=bool(entry.get("allow_permanent", False)),
            description=entry.get("description", ""),
            confirmed_by_user_id=confirmed_by_user_id,
            confirmed_by_name=confirmed_by_name,
        )
    except Exception:
        pass

    try:
        from tools.approval import resolve_gateway_approval
        hermes_choice = {
            "allow-once": "once",
            "allow-session": "session",
            "allow-always": "always",
        }.get(decision, "deny")
        resolve_gateway_approval(session_key, hermes_choice)
    except Exception as exc:
        logger.warning(f"唤醒 Hermes 审批等待线程失败 id={approval_id}: {exc}")

    logger.info(f"✅ exec 审批已决议 id={approval_id} 决定={decision}")
    return True


def get_approval_decision(approval_id: str) -> Dict[str, Any]:
    """查询审批决议状态。"""
    with _exec_approval_lock:
        entry = _exec_approval_pending.get(approval_id)
        if not entry:
            return {"status": "unknown"}
        if entry["decision"] is None:
            return {"status": "pending"}
        return {"status": "resolved", "decision": entry["decision"]}
