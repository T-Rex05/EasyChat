"""
聊天历史缓存清理模块

定期清理内存中的聊天历史和取消标记，防止内存泄漏。
"""
import asyncio
import time
from typing import Dict, Any, List, Set
from collections import defaultdict
from backend.utils.log_utils import log

logger = log

# 清理配置
CLEANUP_INTERVAL = 300  # 5分钟执行一次
MAX_IDLE_TIME = 3600  # 1小时未活跃则清理
MAX_CANCELLED_TIME = 1800  # 30分钟后清理取消标记
MAX_COMPLETED_TIME = 1800  # 30分钟后清理已完成标记

# 活跃时间追踪
_last_activity: Dict[str, float] = {}
_cancelled_time: Dict[str, float] = {}
_completed_time: Dict[str, float] = {}


def update_activity(thread_id: str):
    """更新 thread 的最后活跃时间"""
    _last_activity[thread_id] = time.time()


def mark_cancelled_time(thread_id: str):
    """记录取消时间"""
    _cancelled_time[thread_id] = time.time()


def mark_completed_time(thread_id: str):
    """记录完成时间"""
    _completed_time[thread_id] = time.time()


async def cleanup_chat_caches(
    chat_histories: Dict[str, List[Dict[str, Any]]],
    cancelled_threads: Set[str],
    completed_threads: Set[str],
):
    """
    清理聊天历史缓存
    
    清理策略：
    1. chat_histories: 清理超过1小时未活跃的 thread
    2. cancelled_threads: 清理超过30分钟的取消标记
    3. completed_threads: 清理超过30分钟的完成标记
    """
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        
        try:
            now = time.time()
            cleaned_histories = 0
            cleaned_cancelled = 0
            cleaned_completed = 0
            
            # 清理聊天历史
            idle_threads = [
                tid for tid, last_time in _last_activity.items()
                if now - last_time > MAX_IDLE_TIME
            ]
            
            for tid in idle_threads:
                if tid in chat_histories:
                    del chat_histories[tid]
                    del _last_activity[tid]
                    cleaned_histories += 1
            
            # 清理取消标记
            old_cancelled = [
                tid for tid, cancel_time in _cancelled_time.items()
                if now - cancel_time > MAX_CANCELLED_TIME
            ]
            
            for tid in old_cancelled:
                cancelled_threads.discard(tid)
                del _cancelled_time[tid]
                cleaned_cancelled += 1
            
            # 清理完成标记
            old_completed = [
                tid for tid, complete_time in _completed_time.items()
                if now - complete_time > MAX_COMPLETED_TIME
            ]
            
            for tid in old_completed:
                completed_threads.discard(tid)
                del _completed_time[tid]
                cleaned_completed += 1
            
            if cleaned_histories > 0 or cleaned_cancelled > 0 or cleaned_completed > 0:
                logger.info(
                    f"🧹 聊天缓存清理完成: "
                    f"清理 {cleaned_histories} 个历史, "
                    f"{cleaned_cancelled} 个取消标记, "
                    f"{cleaned_completed} 个完成标记"
                )
        
        except Exception as e:
            logger.opt(exception=True).error(f"聊天缓存清理失败: {e}")


# ── 上传附件 TTL 清理（新旧路径兼容） ──
UPLOAD_TTL_DAYS = 7
UPLOAD_CLEANUP_INTERVAL = 6 * 3600  # 每 6 小时扫一次


async def cleanup_upload_files(interval_s: int = UPLOAD_CLEANUP_INTERVAL, ttl_days: int = UPLOAD_TTL_DAYS):
    """周期清理聊天上传附件目录中超过 TTL 的文件。"""
    from pathlib import Path
    from backend.config.paths import DATA_ROOT
    
    # 新路径（docker/volumes/）+ 旧路径（data/）兼容
    upload_dirs = [
        DATA_ROOT / "uploads",
        DATA_ROOT / "chat_uploads",
        Path(__file__).resolve().parents[2] / "data" / "uploads",
        Path(__file__).resolve().parents[2] / "data" / "chat_uploads",
    ]
    while True:
        await asyncio.sleep(interval_s)
        try:
            now = time.time()
            removed = 0
            for d in upload_dirs:
                if not d.exists() or not d.is_dir():
                    continue
                for f in d.iterdir():
                    if not f.is_file():
                        continue
                    try:
                        if now - f.stat().st_mtime > ttl_days * 86400:
                            f.unlink(missing_ok=True)
                            removed += 1
                    except OSError:
                        pass
            if removed:
                logger.info(f"上传附件 TTL 清理: 删除 {removed} 个超过 {ttl_days} 天的文件")
        except Exception as e:
            logger.opt(exception=True).error(f"上传附件清理失败: {e}")
