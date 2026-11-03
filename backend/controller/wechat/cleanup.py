"""微信监听器 - 缓存清理"""
import asyncio
import time
import logging

from backend.controller.wechat.config import (
    _dedup, _dedup_ttl,
    _pending_images, _pending_files, _session_files, _PENDING_TIMEOUT,
    _wx_active_session, _wx_session_titles
)

logger = logging.getLogger("agentforge.wechat_listener")


async def cleanup_wechat_caches():
    """定期清理微信监听器的内存缓存
    
    清理策略：
    - _dedup: 清理超过 _dedup_ttl 秒的消息ID
    - _pending_images/_pending_files: 清理超过 _PENDING_TIMEOUT 秒的缓存
    - _session_files: 清理超过 1 小时的会话文件注册（防止无限增长）
    - _wx_active_session: 清理超过 24 小时未活跃的会话
    - _wx_session_titles: 清理超过 24 小时未活跃的会话标题
    
    每 5 分钟执行一次清理。
    """
    SESSION_TIMEOUT = 3600  # 1 小时
    ACTIVE_TIMEOUT = 86400  # 24 小时
    
    while True:
        await asyncio.sleep(300)  # 5 分钟
        try:
            now = time.time()
            
            # 清理 _dedup
            expired_dedup = [k for k, v in _dedup.items() if now - v > _dedup_ttl]
            for k in expired_dedup:
                _dedup.pop(k, None)
            if expired_dedup:
                logger.debug(f"清理 _dedup: {len(expired_dedup)} 条")
            
            # 清理 _pending_images
            expired_images = [k for k, v in _pending_images.items() 
                            if now - v.get("timestamp", 0) > _PENDING_TIMEOUT]
            for k in expired_images:
                _pending_images.pop(k, None)
            if expired_images:
                logger.debug(f"清理 _pending_images: {len(expired_images)} 条")
            
            # 清理 _pending_files
            expired_files = [k for k, v in _pending_files.items() 
                           if now - v.get("timestamp", 0) > _PENDING_TIMEOUT]
            for k in expired_files:
                _pending_files.pop(k, None)
            if expired_files:
                logger.debug(f"清理 _pending_files: {len(expired_files)} 条")
            
            # 清理 _session_files（超过 1 小时的会话文件注册）
            expired_sessions = [k for k, v in _session_files.items() 
                              if now - v.get("last_access", 0) > SESSION_TIMEOUT]
            for k in expired_sessions:
                _session_files.pop(k, None)
            if expired_sessions:
                logger.debug(f"清理 _session_files: {len(expired_sessions)} 条")
            
            # 清理 _wx_active_session（超过 24 小时未活跃）
            expired_active = [k for k, v in _wx_active_session.items() 
                            if now - v.get("last_active", 0) > ACTIVE_TIMEOUT]
            for k in expired_active:
                _wx_active_session.pop(k, None)
            if expired_active:
                logger.debug(f"清理 _wx_active_session: {len(expired_active)} 条")
            
            # 清理 _wx_session_titles（超过 24 小时未活跃）
            expired_titles = [k for k, v in _wx_session_titles.items() 
                            if now - v.get("last_active", 0) > ACTIVE_TIMEOUT]
            for k in expired_titles:
                _wx_session_titles.pop(k, None)
            if expired_titles:
                logger.debug(f"清理 _wx_session_titles: {len(expired_titles)} 条")
                
        except Exception as e:
            logger.error(f"微信缓存清理失败: {e}", exc_info=True)
