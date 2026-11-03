"""
论文复现系统公共工具函数

提供 LLM 初始化、重试机制、配置管理等公共功能
"""

import time
import logging
from typing import Callable, Optional, TypeVar, Any
from functools import wraps
from pathlib import Path

logger = logging.getLogger(__name__)

T = TypeVar('T')


# ==================== 配置管理 ====================

class PaperReproductionConfig:
    """论文复现配置类"""

    # LLM 配置
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.7
    llm_max_retries: int = 3
    llm_timeout: int = 60

    # Docker 配置
    docker_timeout: int = 300
    docker_image: str = "python:3.10-slim"
    docker_max_patches: int = 3

    # GitHub 配置
    github_timeout: int = 10
    github_max_repos: int = 5
    github_rate_limit_wait: int = 60

    # 论文配置
    max_claims: int = 10
    max_text_length: int = 8000
    pdf_extract_timeout: int = 120

    # 网络配置
    request_timeout: int = 60
    request_max_retries: int = 3
    request_retry_delay: float = 1.0

    # 输出配置
    max_output_length: int = 5000

    @classmethod
    def from_env(cls) -> 'PaperReproductionConfig':
        """从环境变量加载配置"""
        import os

        config = cls()

        # LLM 配置
        config.llm_model = os.getenv("LLM_MODEL", config.llm_model)
        config.llm_temperature = float(os.getenv("LLM_TEMPERATURE", config.llm_temperature))

        # Docker 配置
        config.docker_timeout = int(os.getenv("PAPER_DOCKER_TIMEOUT", config.docker_timeout))
        config.docker_image = os.getenv("PAPER_DOCKER_IMAGE", config.docker_image)

        # GitHub 配置
        config.github_timeout = int(os.getenv("PAPER_GITHUB_TIMEOUT", config.github_timeout))
        config.github_max_repos = int(os.getenv("PAPER_MAX_REPOS", config.github_max_repos))

        # 论文配置
        config.max_claims = int(os.getenv("PAPER_MAX_CLAIMS", config.max_claims))
        config.max_text_length = int(os.getenv("PAPER_MAX_TEXT", config.max_text_length))

        return config


# 全局配置实例
_config: Optional[PaperReproductionConfig] = None


def get_config() -> PaperReproductionConfig:
    """获取配置实例（单例）"""
    global _config
    if _config is None:
        _config = PaperReproductionConfig.from_env()
    return _config


# ==================== LLM 初始化 ====================

def get_llm_instance(scene: str = "paper_parse"):
    """
    获取 LLM 实例（统一入口，使用场景路由）

    Args:
        scene: 场景标识（paper_parse / paper_claim / paper_debug）

    Returns:
        ChatOpenAI: LLM 实例

    Raises:
        ValueError: 如果没有可用的模型配置
    """
    from langchain_openai import ChatOpenAI
    from backend.service.model_router import ModelRouter

    # 使用模型路由器获取配置
    router = ModelRouter()
    config = router.select_model(category="chat", scene=scene)

    if not config:
        logger.error("没有可用的 LLM 模型配置")
        raise ValueError("缺少 LLM 配置，请在「模型配置」中添加模型")

    logger.info(f"使用模型: {config.get('model_name')} (场景: {scene})")

    # 论文解析场景需要更长的超时时间（默认 180 秒）
    # 如果数据库配置中有 timeout，使用配置值；否则使用默认值
    config_timeout = config.get("timeout")
    if config_timeout and config_timeout > 0:
        timeout = config_timeout
    else:
        # 根据场景设置不同的默认超时
        timeout = 180 if scene.startswith("paper") else 60

    logger.info(f"LLM 超时设置: {timeout} 秒 (场景: {scene})")

    # 注意：数据库字段名是 api_url，不是 base_url
    api_url = config.get("api_url") or config.get("base_url")

    return ChatOpenAI(
        model=config.get("model_name"),
        api_key=config.get("api_key"),
        base_url=api_url,
        temperature=config.get("temperature") or 0.7,
        request_timeout=timeout
    )


# ==================== 重试机制 ====================

def retry_on_failure(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    重试装饰器

    Args:
        max_retries: 最大重试次数
        delay: 初始延迟（秒）
        backoff: 延迟增长因子
        exceptions: 需要重试的异常类型

    Example:
        @retry_on_failure(max_retries=3, exceptions=(ConnectionError,))
        def fetch_data():
            return requests.get("https://api.example.com")
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"⚠️ {func.__name__} 失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}"
                        )
                        logger.info(f"等待 {current_delay:.1f} 秒后重试...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"❌ {func.__name__} 最终失败: {e}")

            raise last_exception

        return wrapper
    return decorator


# ==================== 性能监控 ====================

class PerformanceMonitor:
    """性能监控器"""

    def __init__(self, name: str):
        self.name = name
        self.start_time = None
        self.end_time = None
        self.stages = []

    def __enter__(self):
        self.start_time = time.time()
        logger.info(f"⏱️ 开始 {self.name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        logger.info(f"✅ 完成 {self.name}: 耗时 {duration:.2f} 秒")

    def add_stage(self, stage_name: str, progress: Optional[int] = None):
        """添加阶段标记"""
        elapsed = time.time() - self.start_time
        self.stages.append({
            "name": stage_name,
            "elapsed": elapsed,
            "progress": progress
        })

        if progress is not None:
            logger.info(f"📊 {self.name} - {stage_name}: {progress}% 完成 ({elapsed:.2f}s)")
        else:
            logger.info(f"📊 {self.name} - {stage_name} ({elapsed:.2f}s)")

    def get_summary(self) -> dict:
        """获取性能摘要"""
        return {
            "name": self.name,
            "total_duration": self.end_time - self.start_time if self.end_time else None,
            "stages": self.stages
        }


# ==================== 文件操作 ====================

def safe_write_file(file_path: Path, content: bytes, max_size: int = 100 * 1024 * 1024):
    """
    安全写入文件

    Args:
        file_path: 文件路径
        content: 文件内容
        max_size: 最大文件大小（字节）

    Raises:
        ValueError: 如果文件过大
    """
    # 检查文件大小
    if len(content) > max_size:
        raise ValueError(f"文件过大: {len(content)} 字节 (最大 {max_size} 字节)")

    # 确保目录存在
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 使用临时文件 + 原子重命名
    temp_path = file_path.with_suffix(file_path.suffix + '.tmp')

    try:
        with open(temp_path, 'wb') as f:
            f.write(content)

        # 原子重命名
        temp_path.rename(file_path)
        logger.info(f"✅ 文件已保存: {file_path}")

    except Exception as e:
        # 清理临时文件
        if temp_path.exists():
            temp_path.unlink()
        raise


def safe_read_file(file_path: Path, max_size: int = 100 * 1024 * 1024) -> bytes:
    """
    安全读取文件

    Args:
        file_path: 文件路径
        max_size: 最大文件大小（字节）

    Returns:
        bytes: 文件内容

    Raises:
        FileNotFoundError: 如果文件不存在
        ValueError: 如果文件过大
    """
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    file_size = file_path.stat().st_size
    if file_size > max_size:
        raise ValueError(f"文件过大: {file_size} 字节 (最大 {max_size} 字节)")

    with open(file_path, 'rb') as f:
        return f.read()


# ==================== 网络请求 ====================

def create_retry_session(
    total_retries: int = 3,
    backoff_factor: float = 1.0,
    status_forcelist: tuple = (429, 500, 502, 503, 504)
):
    """
    创建带重试机制的 requests Session

    Args:
        total_retries: 总重试次数
        backoff_factor: 退避因子
        status_forcelist: 需要重试的状态码

    Returns:
        requests.Session: 配置好的 Session
    """
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()

    retry_strategy = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE", "PATCH"]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


# ==================== 验证函数 ====================

def validate_url(url: str) -> bool:
    """
    验证 URL 格式

    Args:
        url: URL 字符串

    Returns:
        bool: 是否合法
    """
    import re

    # 简单的 URL 验证
    pattern = re.compile(
        r'^https?://'  # http:// 或 https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # 域名
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP 地址
        r'(?::\d+)?'  # 可选端口
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return bool(pattern.match(url))


def truncate_text(text: str, max_length: int = 5000, suffix: str = "...") -> str:
    """
    截断文本到指定长度

    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 截断后缀

    Returns:
        str: 截断后的文本
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


# ==================== 导出 ====================

__all__ = [
    'PaperReproductionConfig',
    'get_config',
    'get_llm_instance',
    'retry_on_failure',
    'PerformanceMonitor',
    'safe_write_file',
    'safe_read_file',
    'create_retry_session',
    'validate_url',
    'truncate_text',
]