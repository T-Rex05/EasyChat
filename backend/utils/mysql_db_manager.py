"""
MySQL 数据库管理器

提供 SQLAlchemy 会话管理
"""

from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.utils.log_utils import log

logger = log

# 全局引擎和会话工厂
_engine = None
_session_factory = None


def _get_database_url() -> str:
    """构建数据库连接 URL"""
    import os
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3307")
    user = os.getenv("MYSQL_USER", "agentforge")
    password = os.getenv("MYSQL_PASSWORD", "agentforge123")
    database = os.getenv("MYSQL_DATABASE", "agentforge")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"


def _init_engine():
    """初始化引擎"""
    global _engine, _session_factory
    if _engine is None:
        url = _get_database_url()
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=5,
            max_overflow=10,
            echo=False
        )
        _session_factory = sessionmaker(bind=_engine)
        logger.info(f"MySQL DB Manager initialized")
    return _engine


class MySQLDBManager:
    """
    MySQL 数据库管理器
    
    提供 SQLAlchemy 会话管理
    """
    
    def __init__(self):
        """初始化管理器"""
        _init_engine()
    
    def get_session(self) -> Session:
        """获取数据库会话"""
        if _session_factory is None:
            _init_engine()
        return _session_factory()
    
    def close(self):
        """关闭所有连接"""
        global _engine, _session_factory
        if _engine:
            _engine.dispose()
            _engine = None
            _session_factory = None


# 单例
_db_manager: Optional[MySQLDBManager] = None


def get_db_manager() -> MySQLDBManager:
    """获取数据库管理器单例"""
    global _db_manager
    if _db_manager is None:
        _db_manager = MySQLDBManager()
    return _db_manager