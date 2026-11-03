"""
日志系统 - loguru 单例封装

特性：
1. emoji 前缀分类规范（✅成功 ❌失败 ⚠️警告 🔄切换 📊统计）
2. 上海时区统一（跨平台）
3. 多日志文件分离（audit.log / warning.log / scan.log）
4. Hermes 框架噪音过滤（INFO 级高频输出不刷屏）
5. 审计事件标记（[AUDIT] 前缀，即使 INFO 级也保留）
6. 预轮转 + 压缩（避免 loguru 全时间戳文件名）
7. 进程重启文件锁重试
"""
import sys
import os
import time
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from loguru import logger
import pytz

# ============================================================================
# Windows 控制台 UTF-8 设置（必须在 loguru 初始化之前）
# ============================================================================

# Windows 默认使用 GBK 编码，无法显示 emoji。
# 强制设置 stdout/stderr 为 UTF-8，确保 emoji 日志正常输出。
# 参考：eyes-agent 的 hermes_bootstrap.py
if sys.platform == "win32":
    try:
        # 重新包装 stdout/stderr，强制 UTF-8 编码
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass  # 失败不影响程序运行

# ============================================================================
# 常量定义
# ============================================================================

# 强制使用上海时区（跨环境统一）
SHANGHAI_TZ = pytz.timezone('Asia/Shanghai')

# emoji 前缀分类规范（eyes-agent 同款）
# 用法：log.info(f"✅ 操作成功") / log.warning(f"⚠️ 配置缺失") / log.error(f"❌ 执行失败")
LOG_EMOJI = {
    "success": "✅",    # 成功
    "fail": "❌",       # 失败
    "warning": "⚠️",    # 警告
    "switch": "🔄",     # 切换
    "stats": "📊",      # 统计
    "info": "ℹ️",       # 信息
    "debug": "🔍",      # 调试
    "audit": "📝",      # 审计
}

# Hermes 框架内部 INFO 级高频噪音模式（eyes-agent 同款）
# 这些日志在 INFO 级别刷屏，但对调试无用，过滤掉
_HERMES_INFO_NOISE_PATTERNS = (
    # 工具搜索每次请求的 token 统计——只在 DEBUG 有用
    "tool_search activated",
    # 插件启动时逐个注册 provider——51 条无意义，汇总一条即可
    "registered provider",
    # 工具可用性 check_fn 启动探测逐个返回 False
    "returned False",
    # 终端输出进度帧（每几十帧一条）
    "run_to_buffer",
    "frames=",
    # 辅助客户端反复标记 provider 不可用（重复刷屏）
    "_mark_provider_unhealthy",
    # 会话恢复相关的 INFO 日志
    "Recovered session",
    "Session state loaded",
    # 工具调用完成（太多了）
    "Tool returned",
    "Tool execution completed",
)

# 需要记录到 audit.log 的关键事件标记（即使 INFO 级别也不过滤）
_AUDIT_EVENT_MARKERS = (
    "[AUDIT]",  # 压缩事件等关键审计日志
    "[CRITICAL]",  # 关键操作
)

# ============================================================================
# 日志目录初始化
# ============================================================================

# 获得当前项目的绝对路径
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后的环境：使用可执行文件所在目录
    log_dir = os.path.join(os.path.dirname(sys.executable), "logs")
else:
    # 开发环境：使用项目根目录下的 data/logs/
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    log_dir = os.environ.get("AGENTFORGE_LOG_DIR", os.path.join(root_dir, "data", "logs"))

# 如果日志目录不存在，则创建
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)

# ============================================================================
# 时间工具函数
# ============================================================================

def _get_shanghai_now() -> datetime:
    """获取上海时区的当前时间（跨环境统一）"""
    return datetime.now(SHANGHAI_TZ)


def _patch_shanghai_time(record):
    """给每条日志注入上海时区时间戳（跨平台统一，不依赖系统时区）。

    Windows 上 time.tzset() 不存在（Python 3.13 实测），
    无法通过 os.environ['TZ'] 改变 datetime.now() 的本地时区；
    而 loguru 的 {time} 只支持 !UTC 开关，不支持 +08:00 偏移。
    因此用 pytz 显式计算上海时间，注入 extra 字段供 format 使用。
    Linux / Windows / macOS 均适用。
    """
    record["extra"]["shanghai_time"] = datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")

# ============================================================================
# 文件锁重试机制
# ============================================================================

def _retry_on_lock(op: Callable, desc: str, retries: int = 5, delay: float = 0.2) -> bool:
    """
    Windows 下重启服务时，旧进程可能还没释放日志文件句柄，
    此时 os.rename/os.remove 会抛 PermissionError，短暂重试几次
    等旧进程退出释放锁，而不是直接放弃导致 loguru 自动触发难看的
    全时间戳过期轮转文件名。
    """
    last_err = None
    for attempt in range(retries):
        try:
            op()
            return True
        except (PermissionError, OSError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(delay)
    print(f"[日志轮转] {desc}失败（已重试{retries}次）: {last_err}")
    return False


def _append_and_remove(src: str, dst: str, desc: str) -> bool:
    """
    当天日期文件已存在时，把 src 的内容追加到 dst 末尾再删除 src，
    而不是直接删除 src——否则会静默丢失 src 里已经写入的日志内容。

    ⚠️ 重试必须只重试"还没成功的那一步"：
    `os.remove` 在 Windows 上常因旧进程仍持有句柄而失败，而**追加通常已经成功**。
    若把"读→追加→删除"整体放进重试闭包，每次重试都会再追加一遍，
    同一段日志会被写进去 N 次（实测：remove 失败 2 次 → 同一行出现 3 次）。
    因此这里先读一次数据，追加只做一次，重试只针对删除。
    """
    try:
        with open(src, 'rb') as fsrc:
            data = fsrc.read()
    except OSError as e:
        print(f"[日志轮转] {desc}失败（读取源文件）: {e}")
        return False

    state = {"appended": False}

    def op():
        if not state["appended"]:
            with open(dst, 'ab') as fdst:
                fdst.write(data)
            state["appended"] = True
        os.remove(src)

    return _retry_on_lock(op, desc)

# ============================================================================
# 日志轮转与清理
# ============================================================================

def _pre_rotate_if_overdue(file_path: str, rotation_time: str = "00:00") -> None:
    """
    预轮转：如果文件最后修改时间早于当天的 rotation 时间点，
    说明是上一轮遗留下来的"过期"文件，提前重命名，
    避免 loguru 的 add() 触发"过期轮转"导致每次重启多一个文件。

    优化：使用日期级时间戳（不含时分秒），同一天多次重启只生成一个轮转文件。
    """
    if not os.path.exists(file_path):
        return
    hour, minute = map(int, rotation_time.split(":"))
    now = _get_shanghai_now()
    rotation_point = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now <= rotation_point:
        return  # 还没到轮转点，不处理
    # 文件修改时间也转为上海时区比较
    file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path), tz=SHANGHAI_TZ)
    if file_mtime >= rotation_point:
        return  # 文件在轮转点之后修改过，说明已轮转，不处理

    # 检查是否已存在当天的轮转文件（避免同一天多次重启生成多个文件）
    stem, ext = os.path.splitext(file_path)
    today_str = now.strftime("%Y-%m-%d")
    rotated_path = f"{stem}.{today_str}{ext}"

    # 如果当天轮转文件已存在，把内容追加进去（避免重复轮转，同时不丢日志）
    if os.path.exists(rotated_path):
        if _append_and_remove(file_path, rotated_path, f"合并旧文件 {os.path.basename(file_path)}"):
            print(f"[日志轮转] 当天轮转文件已存在，已追加合并: {os.path.basename(file_path)}")
        return

    # 执行预轮转
    if _retry_on_lock(lambda: os.rename(file_path, rotated_path), f"轮转 {os.path.basename(file_path)}"):
        print(f"[日志轮转] 已轮转: {os.path.basename(file_path)} -> {os.path.basename(rotated_path)}")


def _compress_to_date_only(file_path: str) -> None:
    """
    loguru 真正触发轮转时（进程持续运行跨过午夜），生成的文件名固定带全时间戳
    （形如 xxx.2026-07-19_00-47-16_477766.log），没有公开参数可以覆盖这个格式。
    借助 compression 钩子在轮转完成后立刻把文件名精简成纯日期，和重启预轮转的命名保持一致。
    """
    dirname, filename = os.path.split(file_path)
    match = re.match(r'^(.*)\.(\d{4}-\d{2}-\d{2})_\d{2}-\d{2}-\d{2}_\d{6}(\.[^.]+)?$', filename)
    if not match:
        return
    stem, date_str, ext = match.group(1), match.group(2), (match.group(3) or '')
    target = os.path.join(dirname, f"{stem}.{date_str}{ext}")
    if os.path.exists(target):
        if _append_and_remove(file_path, target, f"合并轮转文件 {filename}"):
            print(f"[日志轮转] 当天轮转文件已存在，已追加合并: {filename}")
        return
    if _retry_on_lock(lambda: os.rename(file_path, target), f"精简轮转文件名 {filename}"):
        print(f"[日志轮转] 已精简轮转文件名: {filename} -> {os.path.basename(target)}")


def _cleanup_old_logs(log_dir: str, pattern: str, retention_days: int) -> None:
    """
    主动清理过期日志文件（弥补 loguru retention 只在轮转时检查的不足）
    
    优先从文件名解析时间（如 audit.2026-07-15_14-00-48_914806.log），
    如果解析失败则使用文件修改时间。
    
    Args:
        log_dir: 日志目录
        pattern: 文件名匹配模式（如 'audit.*.log'）
        retention_days: 保留天数
    """
    import fnmatch
    
    now = _get_shanghai_now()
    cutoff_time = now - timedelta(days=retention_days)
    
    # 文件名时间解析正则（支持两种格式）：
    # 旧格式: audit.2026-07-15_14-00-48_914806.log -> 2026-07-15
    # 新格式: audit.2026-07-19.log -> 2026-07-19
    date_pattern = re.compile(r'\.(\d{4}-\d{2}-\d{2})(?:_\d{2}-\d{2}-\d{2})?')
    
    deleted_count = 0
    try:
        for filename in os.listdir(log_dir):
            if not fnmatch.fnmatch(filename, pattern):
                continue
            file_path = os.path.join(log_dir, filename)
            if not os.path.isfile(file_path):
                continue
            try:
                # 优先从文件名解析日期
                match = date_pattern.search(filename)
                if match:
                    file_date_str = match.group(1)
                    file_date = datetime.strptime(file_date_str, "%Y-%m-%d").replace(tzinfo=SHANGHAI_TZ)
                    date_source = "文件名"
                else:
                    # 回退到文件修改时间
                    file_date = datetime.fromtimestamp(os.path.getmtime(file_path), tz=SHANGHAI_TZ)
                    date_source = "修改时间"
                
                if file_date < cutoff_time:
                    os.remove(file_path)
                    deleted_count += 1
                    print(f"[日志清理] 已删除过期日志: {filename}（{date_source}: {file_date.strftime('%Y-%m-%d')}，保留{retention_days}天）")
            except Exception as e:
                print(f"[日志清理] 删除日志文件失败: {filename}, error={e}")
    except Exception as e:
        print(f"[日志清理] 扫描日志目录失败: {log_dir}, error={e}")
    
    if deleted_count > 0:
        print(f"[日志清理] 完成：删除 {deleted_count} 个过期文件（保留 {retention_days} 天）")

# ============================================================================
# Hermes 日志噪音过滤器（eyes-agent 同款）
# ============================================================================

class _HermesNoiseFilter:
    """
    Hermes 框架内部 INFO 级高频噪音过滤器。
    
    过滤规则：
    1. INFO 级以下的噪音直接丢弃（不影响 WARNING/ERROR）
    2. 带有 [AUDIT]/[CRITICAL] 标记的日志即使 INFO 级也保留
    3. 匹配 _HERMES_INFO_NOISE_PATTERNS 的消息过滤掉
    """
    
    @staticmethod
    def should_filter(record: dict) -> bool:
        """返回 True 表示应该过滤掉这条日志"""
        # 审计事件标记：即使 INFO 级别也不过滤
        message = record.get("message", "")
        is_audit_event = any(marker in message for marker in _AUDIT_EVENT_MARKERS)
        if is_audit_event:
            return False
        
        # 只有 INFO 级及以下才过滤
        level_no = record["level"].no
        if level_no >= logging.WARNING:
            return False  # WARNING 及以上不过滤
        
        # 检查是否匹配噪音模式
        for pattern in _HERMES_INFO_NOISE_PATTERNS:
            if pattern in message:
                return True
        
        return False

# ============================================================================
# 日志处理器
# ============================================================================

class _HermesLoguruHandler(logging.Handler):
    """
    桥接标准 Python logging → loguru（eyes-agent 同款）。
    
    功能：
    1. 过滤 Hermes 内部高频 INFO 噪音
    2. 保留 [AUDIT] 标记的审计事件
    3. 移除 [AUDIT] 标记后记录（避免污染日志内容）
    """
    
    _level_map = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }
    
    def emit(self, record: logging.LogRecord) -> None:
        try:
            # 获取消息
            try:
                msg = record.getMessage()
            except Exception:
                msg = str(record.msg)
            
            # 检查是否是审计事件
            is_audit_event = any(marker in msg for marker in _AUDIT_EVENT_MARKERS)
            
            # INFO 及以下的高频噪音直接丢弃，但审计事件除外
            if record.levelno < logging.WARNING and not is_audit_event:
                if any(p in msg for p in _HERMES_INFO_NOISE_PATTERNS):
                    return  # 过滤掉
            
            level = self._level_map.get(record.levelno, "INFO")
            
            # 对于审计事件，移除 [AUDIT] 标记后再记录
            if is_audit_event and "[AUDIT] " in msg:
                msg = msg.replace("[AUDIT] ", "", 1)
            
            # depth=6 穿透到真实调用者
            logger.opt(depth=6, exception=record.exc_info).bind(
                logger_name=record.name
            ).log(level, msg)
        except Exception:
            pass  # 日志记录失败不阻断程序

# ============================================================================
# 主日志类
# ============================================================================

class MyLogger:
    """
    日志系统主类。
    
    日志文件：
    - audit.log: INFO 级，7 天，审计日志
    - warning.log: WARNING+，16 天，异常日志
    - scan.log: 后台扫描专用，3 天（按 scope="scan" 过滤）
    
    特性：
    - emoji 前缀分类规范
    - Hermes 噪音过滤
    - 上海时区统一
    - 预轮转 + 压缩
    """
    
    def __init__(self):
        self.logger = logger
        self.logger.remove()  # 清空所有默认设置

        # 注入上海时区时间戳（跨平台，见 _patch_shanghai_time 注释）
        self.logger = self.logger.patch(_patch_shanghai_time)

        # 控制台输出格式配置（使用注入的上海时区时间）
        console_format = (
            "{extra[shanghai_time]} | "  # 上海时区时间（跨平台统一）
            "{process.name} | "  # 进程名
            "{thread.name} | "  # 线程名
            "<cyan>{module}</cyan>.<cyan>{function}</cyan>:"
            "<cyan>{line}</cyan> | "  # 模块、函数、行号
            "<level>{level}</level>: "  # 日志等级
            "<level>{message}</level>"  # 日志内容
        )
        
        # 控制台过滤器：抑制 Hermes 每请求噪声模块的 INFO/DEBUG
        _QUIET_HERMES_PREFIXES = (
            "agent.conversation_loop",     # API call #N (每次请求 3+ 条)
            "agent.tool_executor",          # Tool X returned error/result
            "agent.turn_context",           # conversation turn
            "tools.web_tools",              # Web search via ddgs
            "agent.agent_runtime_helpers",  # OpenAI client created
        )
        
        def _console_filter(record):
            """控制台过滤：抑制 Hermes 每请求噪声模块的 INFO/DEBUG，WARNING+ 照常显示。"""
            # 审计事件不过滤
            message = record.get("message", "")
            if any(marker in message for marker in _AUDIT_EVENT_MARKERS):
                return True
            
            if record["level"].no < logging.WARNING:
                # 优先使用 InterceptHandler 绑定的 logger_name
                name = record["extra"].get("logger_name", "") or record["name"]
                mod = record["module"]
                for prefix in _QUIET_HERMES_PREFIXES:
                    # 匹配 logger name（如 "agent.conversation_loop"）
                    if name and (name == prefix or name.startswith(prefix + ".")):
                        return False
                    # 匹配 module 文件名（如 "conversation_loop"）
                    short = prefix.rsplit(".", 1)[-1]
                    if mod == short:
                        return False
            return True

        # 添加控制台输出 - INFO 级别，显示组件启动状态
        self.logger.add(sys.stdout, format=console_format, level="INFO", filter=_console_filter)

        # ===== 主日志：WARNING 级别（天然含 ERROR），保留 16 天 =====
        warning_file_path = os.path.join(log_dir, "warning.log")
        _pre_rotate_if_overdue(warning_file_path, "00:00")
        _cleanup_old_logs(log_dir, "warning.*.log", retention_days=16)
        self.logger.add(
            warning_file_path,
            level='WARNING',
            encoding='UTF-8',
            format='{extra[shanghai_time]} - '
                   '{process.name} | '
                   '{thread.name} | '
                   '{module}.{function}:{line} - {level} - {message}',
            rotation="00:00",  # 每天轮转
            retention="16 days",
            compression=_compress_to_date_only,
            enqueue=True,
            buffering=1,
        )

        # ===== 后台扫描日志：只收 scope="scan" 的日志 =====
        # 后台扫描任务是独立后台进程，日志密集，单独开一路避免混在主日志里
        scan_file_path = os.path.join(log_dir, "scan.log")
        _pre_rotate_if_overdue(scan_file_path, "00:00")
        _cleanup_old_logs(log_dir, "scan.*.log", retention_days=3)
        self.logger.add(
            scan_file_path,
            level='INFO',
            encoding='UTF-8',
            format='{extra[shanghai_time]} - '
                   '{process.name} | '
                   '{thread.name} | '
                   '{module}.{function}:{line} - {level} - {message}',
            rotation="00:00",  # 每天轮转
            retention="3 days",
            compression=_compress_to_date_only,
            enqueue=True,
            buffering=1,
            filter=lambda record: record["extra"].get("scope") == "scan",
        )

        # ===== RAG 检索日志：只收 scope="rag" 的日志 =====
        # RAG 检索链路日志密集，单独开一路便于分析和调试
        # 包含：查询重写、向量检索、BM25、Hybrid、Rerank、CRAG 等
        rag_file_path = os.path.join(log_dir, "rag.log")
        _pre_rotate_if_overdue(rag_file_path, "00:00")
        _cleanup_old_logs(log_dir, "rag.*.log", retention_days=7)
        self.logger.add(
            rag_file_path,
            level='DEBUG',  # RAG 日志包含调试信息
            encoding='UTF-8',
            format='{extra[shanghai_time]} - '
                   '{process.name} | '
                   '{thread.name} | '
                   '{module}.{function}:{line} - {level} - {message}',
            rotation="00:00",  # 每天轮转
            retention="7 days",  # 保留 7 天
            compression=_compress_to_date_only,
            enqueue=True,
            buffering=1,
            filter=lambda record: record["extra"].get("scope") == "rag",
        )

        # ===== 审计日志：INFO 级别，保留 7 天用于回溯排查 =====
        # 保留期说明：面向企业客户，审计日志需满足安全/合规留存要求
        audit_file_path = os.path.join(log_dir, "audit.log")
        _pre_rotate_if_overdue(audit_file_path, "00:00")
        _cleanup_old_logs(log_dir, "audit.*.log", retention_days=7)
        self.logger.add(
            audit_file_path,
            level='INFO',
            encoding='UTF-8',
            format='{extra[shanghai_time]} - '
                   '{process.name} | '
                   '{thread.name} | '
                   '{module}.{function}:{line} - {level} - {message}',
            rotation="00:00",  # 每天轮转
            retention="7 days",  # 保留 7 天
            compression=_compress_to_date_only,
            enqueue=False,
            # 隔离后台扫描日志和 RAG 日志
            filter=lambda record: record["extra"].get("scope") not in ("scan", "rag"),
        )

        # ===== 桥接标准 Python logging → loguru =====
        # 安装 Hermes 专用处理器（带噪音过滤）
        _root = logging.getLogger()
        _root.handlers.clear()
        _root.addHandler(_HermesLoguruHandler())
        _root.setLevel(logging.INFO)

        # 抑制高噪声第三方库
        for _noisy in ("openai", "httpx", "httpcore", "urllib3", "apscheduler", "requests"):
            logging.getLogger(_noisy).setLevel(logging.WARNING)

    def get_logger(self):
        return self.logger


# ============================================================================
# 实例化并对外提供 logger 对象
# ============================================================================

log = MyLogger().get_logger()
logger = log  # 别名，推荐使用此命名

# ============================================================================
# 便捷函数
# ============================================================================

def get_scan_logger():
    """
    获取后台扫描专用 logger。
    
    用法：
        from backend.utils.log_utils import get_scan_logger
        log = get_scan_logger()
        log.info("📊 扫描完成，处理了 100 条记录")
    """
    return log.bind(scope="scan")


def get_rag_logger():
    """
    获取 RAG 检索专用 logger。
    
    用法：
        from backend.utils.log_utils import get_rag_logger
        rag_log = get_rag_logger()
        rag_log.info("🔍 [RAG] 开始检索: query=xxx")
    """
    return log.bind(scope="rag")


def rag_log(message: str, level: str = "INFO"):
    """
    记录 RAG 日志（自动添加 [RAG] 标记）。
    
    用法：
        from backend.utils.log_utils import rag_log
        rag_log("🔍 检索开始: query=xxx")
        rag_log("✅ 检索完成: 10 条结果", level="INFO")
        rag_log("⚠️ 检索失败: timeout", level="WARNING")
    """
    rag_logger = log.bind(scope="rag")
    getattr(rag_logger, level.lower())(message)


# ============================================================================
# RAG 模块专用日志快捷函数
# ============================================================================

class RAGLogger:
    """
    RAG 模块专用日志器，带 emoji 前缀规范。
    
    用法：
        from backend.utils.log_utils import rag
        rag.query_start("用户查询内容", kb_id=1, user_id=2)
        rag.rewrite("原始查询", "改写后查询", ["子查询1", "子查询2"])
        rag.retrieval("vector", 10, latency_ms=50)
        rag.rerank(10, 5)
        rag.query_complete(5, total_ms=200)
    """
    
    # emoji 前缀
    EMOJI = {
        "query": "🔍",       # 查询
        "rewrite": "✏️",     # 改写
        "retrieval": "🔎",   # 检索
        "rerank": "📊",      # 重排
        "cache_hit": "⚡",   # 缓存命中
        "success": "✅",     # 成功
        "warning": "⚠️",     # 警告
        "error": "❌",       # 错误
        "fallback": "🔄",    # 降级
        "stats": "📈",       # 统计
    }
    
    def __init__(self):
        self._logger = log.bind(scope="rag")
    
    def _log(self, level: str, message: str):
        getattr(self._logger, level.lower())(message)
    
    # ========== 查询生命周期 ==========
    
    def query_start(self, query: str, kb_id: int = None, user_id: int = None, 
                    trace_id: str = None, mode: str = None):
        """记录查询开始"""
        parts = [f"query='{query[:50]}{'...' if len(query) > 50 else ''}'"]
        if kb_id is not None:
            parts.append(f"kb_id={kb_id}")
        if user_id is not None:
            parts.append(f"user_id={user_id}")
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        if mode:
            parts.append(f"mode={mode}")
        self._log("info", f"🔍 [RAG-Query] 开始检索: {', '.join(parts)}")
    
    def query_complete(self, result_count: int, total_ms: float = None, 
                       trace_id: str = None):
        """记录查询完成"""
        parts = [f"结果数={result_count}"]
        if total_ms is not None:
            parts.append(f"耗时={total_ms:.1f}ms")
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("info", f"✅ [RAG-Query] 检索完成: {', '.join(parts)}")
    
    def query_error(self, error: str, trace_id: str = None):
        """记录查询错误"""
        parts = [f"error={error}"]
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("error", f"❌ [RAG-Query] 检索失败: {', '.join(parts)}")
    
    # ========== 查询改写 ==========
    
    def rewrite(self, original: str, rewritten: str = None, 
                subqueries: list = None, trace_id: str = None):
        """记录查询改写"""
        parts = [f"原查询='{original[:30]}'"]
        if rewritten:
            parts.append(f"改写='{rewritten[:30]}'")
        if subqueries:
            parts.append(f"子查询数={len(subqueries)}")
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("info", f"✏️ [RAG-Rewrite] 查询改写: {', '.join(parts)}")
    
    def rewrite_skip(self, reason: str, trace_id: str = None):
        """记录跳过改写"""
        parts = [f"原因={reason}"]
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("debug", f"⏭️ [RAG-Rewrite] 跳过改写: {', '.join(parts)}")
    
    # ========== 检索 ==========
    
    def retrieval(self, method: str, count: int, latency_ms: float = None,
                  kb_id: int = None, trace_id: str = None):
        """记录检索结果"""
        parts = [f"方法={method}", f"结果数={count}"]
        if latency_ms is not None:
            parts.append(f"耗时={latency_ms:.1f}ms")
        if kb_id is not None:
            parts.append(f"kb_id={kb_id}")
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("info", f"🔎 [RAG-Retrieval] 检索完成: {', '.join(parts)}")
    
    def retrieval_fallback(self, from_method: str, to_method: str, reason: str,
                           trace_id: str = None):
        """记录检索降级"""
        parts = [f"{from_method}→{to_method}", f"原因={reason}"]
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("warning", f"🔄 [RAG-Retrieval] 降级: {', '.join(parts)}")
    
    # ========== 重排 ==========
    
    def rerank(self, input_count: int, output_count: int, method: str = None,
               latency_ms: float = None, trace_id: str = None):
        """记录重排"""
        parts = [f"输入={input_count}", f"输出={output_count}"]
        if method:
            parts.append(f"方法={method}")
        if latency_ms is not None:
            parts.append(f"耗时={latency_ms:.1f}ms")
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("info", f"📊 [RAG-Rerank] 重排完成: {', '.join(parts)}")
    
    def rerank_skip(self, reason: str, trace_id: str = None):
        """记录跳过重排"""
        parts = [f"原因={reason}"]
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("debug", f"⏭️ [RAG-Rerank] 跳过重排: {', '.join(parts)}")
    
    # ========== 缓存 ==========
    
    def cache_hit(self, query: str, cache_type: str = "semantic",
                  latency_ms: float = None, trace_id: str = None):
        """记录缓存命中"""
        parts = [f"query='{query[:30]}'", f"类型={cache_type}"]
        if latency_ms is not None:
            parts.append(f"耗时={latency_ms:.1f}ms")
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("info", f"⚡ [RAG-Cache] 缓存命中: {', '.join(parts)}")
    
    def cache_miss(self, query: str, cache_type: str = "semantic",
                   trace_id: str = None):
        """记录缓存未命中"""
        parts = [f"query='{query[:30]}'", f"类型={cache_type}"]
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("debug", f"💨 [RAG-Cache] 缓存未命中: {', '.join(parts)}")
    
    # ========== CRAG 自适应 ==========
    
    def adaptive(self, complexity: str, reason: str, trace_id: str = None):
        """记录自适应路由决策"""
        parts = [f"复杂度={complexity}", f"原因={reason}"]
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("info", f"🎯 [RAG-Adaptive] 路由决策: {', '.join(parts)}")
    
    def crag_action(self, action: str, reason: str, trace_id: str = None):
        """记录 CRAG 动作"""
        parts = [f"动作={action}", f"原因={reason}"]
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("info", f"🔧 [RAG-CRAG] 纠正动作: {', '.join(parts)}")
    
    # ========== 知识图谱 ==========
    
    def kg_query(self, entities: list, relations: list, result_count: int,
                 latency_ms: float = None, trace_id: str = None):
        """记录知识图谱查询"""
        parts = [f"实体数={len(entities)}", f"关系数={len(relations)}", f"结果数={result_count}"]
        if latency_ms is not None:
            parts.append(f"耗时={latency_ms:.1f}ms")
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("info", f"🕸️ [RAG-KG] 图谱查询: {', '.join(parts)}")
    
    # ========== 评测 ==========
    
    def eval_start(self, run_id: int, set_id: int, item_count: int):
        """记录评测开始"""
        self._log("info", f"📋 [RAG-Eval] 评测启动: run_id={run_id}, set_id={set_id}, 题目数={item_count}")
    
    def eval_item(self, item_id: int, faithfulness: float = None, 
                  relevance: float = None, trace_id: str = None):
        """记录单题评测结果"""
        parts = [f"item_id={item_id}"]
        if faithfulness is not None:
            parts.append(f"忠实度={faithfulness:.2f}")
        if relevance is not None:
            parts.append(f"相关性={relevance:.2f}")
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("info", f"📊 [RAG-Eval] 评测结果: {', '.join(parts)}")
    
    def eval_complete(self, run_id: int, avg_scores: dict, trace_id: str = None):
        """记录评测完成"""
        parts = [f"run_id={run_id}"]
        for k, v in (avg_scores or {}).items():
            parts.append(f"{k}={v:.2f}")
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        self._log("info", f"✅ [RAG-Eval] 评测完成: {', '.join(parts)}")
    
    # ========== 知识库操作 ==========
    
    def kb_parse(self, doc_id: int, chunk_count: int, parser: str,
                 latency_ms: float = None):
        """记录文档解析"""
        parts = [f"doc_id={doc_id}", f"切片数={chunk_count}", f"解析器={parser}"]
        if latency_ms is not None:
            parts.append(f"耗时={latency_ms:.1f}ms")
        self._log("info", f"📄 [RAG-KB] 文档解析: {', '.join(parts)}")
    
    def kb_vectorize(self, doc_id: int, chunk_count: int, 
                     latency_ms: float = None):
        """记录向量化"""
        parts = [f"doc_id={doc_id}", f"切片数={chunk_count}"]
        if latency_ms is not None:
            parts.append(f"耗时={latency_ms:.1f}ms")
        self._log("info", f"🔢 [RAG-KB] 向量化完成: {', '.join(parts)}")
    
    def kb_graph_extract(self, doc_id: int, entity_count: int, 
                         relation_count: int, latency_ms: float = None):
        """记录图谱提取"""
        parts = [f"doc_id={doc_id}", f"实体数={entity_count}", f"关系数={relation_count}"]
        if latency_ms is not None:
            parts.append(f"耗时={latency_ms:.1f}ms")
        self._log("info", f"🕸️ [RAG-KB] 图谱提取: {', '.join(parts)}")
    
    # ========== 通用 ==========
    
    def info(self, message: str):
        """记录 INFO 日志"""
        self._log("info", message)
    
    def warning(self, message: str):
        """记录 WARNING 日志"""
        self._log("warning", f"⚠️ {message}")
    
    def error(self, message: str):
        """记录 ERROR 日志"""
        self._log("error", f"❌ {message}")
    
    def debug(self, message: str):
        """记录 DEBUG 日志"""
        self._log("debug", message)


# 全局 RAG 日志器实例
rag = RAGLogger()


def audit_log(message: str, level: str = "INFO"):
    """
    记录审计日志（带 [AUDIT] 标记，即使 INFO 级也会保留）。
    
    用法：
        from backend.utils.log_utils import audit_log
        audit_log("用户登录成功: user_id=1")
        audit_log("配置变更: key=xxx, old=yyy, new=zzz", level="WARNING")
    """
    getattr(log, level.lower())(f"[AUDIT] {message}")


# ============================================================================
# 测试
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("日志系统测试")
    print("=" * 60)
    
    # 测试 emoji 前缀
    log.debug(f"🔍 调试信息")
    log.info(f"✅ 操作成功")
    log.info(f"ℹ️ 普通信息")
    log.warning(f"⚠️ 警告信息")
    log.error(f"❌ 错误信息")
    
    # 测试审计日志
    audit_log("用户登录成功: user_id=1")
    audit_log("配置变更: key=timeout, old=30, new=60", level="WARNING")
    
    # 测试后台扫描日志
    scan_log = get_scan_logger()
    scan_log.info(f"📊 扫描完成，处理了 100 条记录")
    
    # 测试切换
    log.info(f"🔄 模型切换: deepseek -> qwen")
    
    print("\n日志文件位置:", log_dir)
    print("日志文件列表:")
    for f in os.listdir(log_dir):
        print(f"  - {f}")