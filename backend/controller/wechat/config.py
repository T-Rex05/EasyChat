"""微信监听器 - 配置管理"""
import os
import json
import time
from backend.db.connection_pool import get_pool_connection
from backend.utils.log_utils import log as logger

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"

# 全局状态（使用字典包装，避免模块导入的 global 陷阱）
_listener_state = {
    "task": None,
    "running": False,
}

# 去重缓存: msg_id -> timestamp
_dedup = {}
_dedup_ttl = 300

# 会话管理: key -> {"session_id": str, "last_active": float}
_wx_active_session = {}
# 会话标题: session_id -> {"title": str, "last_active": float}
_wx_session_titles = {}

# 图片和文件缓存: pending_key -> {"images"/"files": list, "timestamp": float, "session_id": str}
_pending_images = {}
_pending_files = {}
# 会话文件注册: session_id -> {"files": list, "last_access": float}
_session_files = {}
_PENDING_TIMEOUT = 30

# 系统进程管理: [(process, start_time, label), ...]
_system_processes = []


def _get_conn():
    """获取数据库连接"""
    return get_pool_connection()


def _get_wechat_config() -> dict | None:
    """获取微信配置"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT config_json, enabled FROM platform_config WHERE platform = 'wechat' AND enabled = 1")
        row = cur.fetchone()
        if not row:
            return None
        cfg = row["config_json"]
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        return cfg if cfg.get("token") and cfg.get("account_id") else None
    finally:
        conn.close()
