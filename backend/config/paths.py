"""
AgentForge 路径配置模块

统一管理所有数据存储路径，支持用户隔离。
所有路径基于 AGENTFORGE_DATA_DIR 环境变量，默认为项目根目录下的 docker/volumes/。

目录结构：
  docker/volumes/
  ├── uploads/{user_id}/          # Web 聊天上传附件
  ├── chat_uploads/{user_id}/     # 微信上传文件
  ├── cron_reports/{username}/    # 定时任务报告
  ├── kb/{user_id}/               # 知识库文件
  ├── charts/{user_id}/           # 图表文件
  ├── reports/{user_id}/          # PDF 报告
  ├── kb_sources/                 # 知识库数据源
  ├── logs/                       # 应用日志
  └── hermes/                     # Hermes 数据（技能/记忆/会话）
"""
import os
import re
from pathlib import Path
from typing import Optional


def get_data_root() -> Path:
    """
    获取数据根目录。
    
    优先级：
    1. AGENTFORGE_DATA_DIR 环境变量
    2. 项目根目录/docker/volumes/
    """
    env_dir = os.environ.get("AGENTFORGE_DATA_DIR", "").strip()
    if env_dir:
        return Path(env_dir).resolve()
    
    # 默认：项目根目录/docker/volumes/
    # 从本文件位置向上到项目根目录
    # paths.py 位于 backend/config/paths.py，所以需要 parents[2]
    current_file = Path(__file__).resolve()
    project_root = current_file.parents[2]  # AgentForge 目录
    return project_root / "docker" / "volumes"


# ── 全局路径常量 ──

DATA_ROOT = get_data_root()


def _ensure_dir(path: Path) -> Path:
    """确保目录存在，返回路径。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── 用户隔离路径 ──

def get_uploads_dir(user_id: Optional[int] = None) -> Path:
    """
    获取 Web 聊天上传附件目录。
    
    Args:
        user_id: 用户 ID，如果提供则创建用户隔离目录
    
    Returns:
        uploads/ 或 uploads/{user_id}/
    """
    if user_id:
        return _ensure_dir(DATA_ROOT / "uploads" / str(user_id))
    return _ensure_dir(DATA_ROOT / "uploads")


def get_chat_uploads_dir(user_id: Optional[int] = None) -> Path:
    """
    获取微信上传文件目录。
    
    Args:
        user_id: 用户 ID，如果提供则创建用户隔离目录
    
    Returns:
        chat_uploads/ 或 chat_uploads/{user_id}/
    """
    if user_id:
        return _ensure_dir(DATA_ROOT / "chat_uploads" / str(user_id))
    return _ensure_dir(DATA_ROOT / "chat_uploads")


def get_cron_reports_dir(username: str) -> Path:
    """
    获取定时任务报告目录（按用户名隔离）。

    Args:
        username: 用户名

    Returns:
        cron_reports/{username}/
    """
    # 安全校验：只允许字母、数字、下划线、中划线、中文
    if not username or not re.match(r'^[\w一-鿿-]+$', username):
        raise ValueError(f"非法用户名: {username!r}")
    return _ensure_dir(DATA_ROOT / "cron_reports" / username)


def get_kb_dir(user_id: int) -> Path:
    """
    获取知识库文件目录（按用户 ID 隔离）。
    
    Args:
        user_id: 用户 ID
    
    Returns:
        kb/{user_id}/
    """
    return _ensure_dir(DATA_ROOT / "kb" / str(user_id))


def get_kb_sources_dir() -> Path:
    """
    获取知识库数据源目录（全局共享）。
    
    Returns:
        kb_sources/
    """
    return _ensure_dir(DATA_ROOT / "kb_sources")


def get_charts_dir(user_id: Optional[int] = None) -> Path:
    """
    获取图表文件目录。
    
    Args:
        user_id: 用户 ID，如果提供则创建用户隔离目录
    
    Returns:
        charts/ 或 charts/{user_id}/
    
    注意：
        为了向后兼容，如果 user_id 为 None，返回旧路径 static/charts/
        这样现有代码可以继续工作，新代码可以传入 user_id 实现隔离
    """
    if user_id:
        return _ensure_dir(DATA_ROOT / "charts" / str(user_id))
    # 向后兼容：返回 static/charts/
    project_root = Path(__file__).resolve().parents[2]
    return _ensure_dir(project_root / "static" / "charts")


def get_reports_dir(user_id: Optional[int] = None) -> Path:
    """
    获取 PDF 报告目录。
    
    Args:
        user_id: 用户 ID，如果提供则创建用户隔离目录
    
    Returns:
        reports/ 或 reports/{user_id}/
    """
    if user_id:
        return _ensure_dir(DATA_ROOT / "reports" / str(user_id))
    # 向后兼容：返回 static/reports/
    project_root = Path(__file__).resolve().parents[2]
    return _ensure_dir(project_root / "static" / "reports")


def get_logs_dir() -> Path:
    """
    获取日志目录。
    
    Returns:
        logs/
    """
    return _ensure_dir(DATA_ROOT / "logs")


def get_hermes_dir() -> Path:
    """
    获取 Hermes 数据目录（技能/记忆/会话）。
    
    Returns:
        hermes/
    """
    return _ensure_dir(DATA_ROOT / "hermes")


# ── 工具函数 ──

def get_user_data_summary(user_id: int) -> dict:
    """
    获取用户数据目录概览。
    
    Args:
        user_id: 用户 ID
    
    Returns:
        {path_type: path_str} 字典
    """
    return {
        "uploads": str(get_uploads_dir(user_id)),
        "chat_uploads": str(get_chat_uploads_dir(user_id)),
        "cron_reports": str(get_cron_reports_dir(f"user_{user_id}")),
        "kb": str(get_kb_dir(user_id)),
        "charts": str(get_charts_dir(user_id)),
        "reports": str(get_reports_dir(user_id)),
    }


def init_data_directories() -> None:
    """
    初始化所有数据目录。
    在应用启动时调用。
    """
    # 创建全局目录
    get_uploads_dir()
    get_chat_uploads_dir()
    get_kb_sources_dir()
    get_charts_dir()
    get_reports_dir()
    get_logs_dir()
    get_hermes_dir()
    
    # 创建兼容目录（确保静态文件服务可用）
    project_root = Path(__file__).resolve().parents[2]
    _ensure_dir(project_root / "static" / "charts")
    _ensure_dir(project_root / "static" / "reports")
    _ensure_dir(project_root / "data" / "uploads")
    _ensure_dir(project_root / "data" / "chat_uploads")
    _ensure_dir(project_root / "data" / "kb")
    _ensure_dir(project_root / "data" / "cron_reports")


# 初始化时打印数据根目录
if __name__ != "__main__":
    # 模块导入时自动创建根目录
    _ensure_dir(DATA_ROOT)