"""微信消息长轮询监听器 - 入口模块

持续轮询 iLink getupdates API，收到消息后：
1. 查 user_bindings 找到对应的 AgentForge 用户
2. 写入 conversations 表（source='wechat'）
3. 调用 LLM 生成回复
4. 通过 iLink sendmessage API 发回微信

支持微信内命令：
  /new /新对话 — 开启新会话
  /history /历史 /list /会话列表 — 列出最近会话
  /1 /2 … — 切换到指定序号会话
  /status /当前 — 查看当前会话
"""
import asyncio
import json
import time
import threading
import ssl

from backend.controller.wechat.config import (
    _get_wechat_config, _listener_state, ILINK_BASE_URL
)
from backend.controller.wechat.handler import _handle_message
from backend.utils.log_utils import log as logger

# 启动锁，防止并发启动
_listener_lock = threading.Lock()


async def _poll_loop(config: dict):
    """主轮询循环"""
    import aiohttp
    import os as _os
    import threading as _threading
    
    token, account_id = config["token"], config["account_id"]
    base_url = config.get("base_url", ILINK_BASE_URL).rstrip("/")
    _pid = _os.getpid()  # 当前进程 PID，用于日志追踪
    
    try:
        import certifi
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ssl_ctx = ssl._create_unverified_context()
    
    connector = aiohttp.TCPConnector(ssl=ssl_ctx, keepalive_timeout=2, enable_cleanup_closed=True)
    sync_buf = ""
    
    async with aiohttp.ClientSession(connector=connector) as session:
        h = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Authorization": f"Bearer {token}",
            "iLink-App-Id": "bot",
            "iLink-App-ClientVersion": str((2 << 16) | (2 << 8) | 0),
            "X-WECHAT-UIN": str(int(time.time()))[:10]
        }
        consecutive_failures = 0
        
        while _listener_state["running"]:
            try:
                body = json.dumps({
                    "get_updates_buf": sync_buf,
                    "base_info": {"channel_version": "2.2.0"}
                }, ensure_ascii=False)
                
                async with session.post(f"{base_url}/ilink/bot/getupdates", data=body, headers=h) as resp:
                    data = json.loads(await resp.text())
                
                ret, errcode = data.get("ret", 0), data.get("errcode", 0)
                if ret not in (0, None) or errcode not in (0, None):
                    if errcode == -14:
                        await asyncio.sleep(600)
                        continue
                    consecutive_failures += 1
                    await asyncio.sleep(30 if consecutive_failures >= 3 else 2)
                    if consecutive_failures >= 3:
                        consecutive_failures = 0
                    continue
                
                consecutive_failures = 0
                if buf := str(data.get("get_updates_buf") or ""):
                    sync_buf = buf
                
                for msg in data.get("msgs") or []:
                    await _handle_message(msg, token, account_id, base_url, session)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"微信轮询错误: {e}")
                await asyncio.sleep(5)
    
    logger.info(f"[微信轮询] 已停止 PID={_pid}")


def _start_listener_async():
    """异步启动监听器"""
    config = _get_wechat_config()
    if not config:
        return logger.info("微信监听器: 无可用配置，跳过启动")
    
    if _listener_state["running"]:
        return logger.info("微信监听器已在运行")
    
    _listener_state["running"] = True
    _listener_state["task"] = asyncio.get_event_loop().create_task(_poll_loop(config))
    logger.info("微信消息监听器已启动 (account=%s)", config.get("account_id", "")[:12])


def restart_wechat_listener():
    """重启微信监听器"""
    logger.info("微信监听器: 收到重启请求")
    _listener_state["running"] = False
    
    task = _listener_state.get("task")
    if task and not task.done():
        task.cancel()
    
    time.sleep(1)
    
    config = _get_wechat_config()
    if not config:
        return logger.info("微信监听器: 无可用配置，已停止")
    
    _listener_state["running"] = True
    _listener_state["task"] = asyncio.get_event_loop().create_task(_poll_loop(config))
    logger.info("微信消息监听器已重启 (account=%s)", config.get("account_id", "")[:12])


def start_wechat_listener():
    """启动微信监听器（线程安全）"""
    with _listener_lock:
        config = _get_wechat_config()
        if not config:
            return logger.info("微信监听器: 未配置，跳过")
        try:
            _start_listener_async()
        except Exception as e:
            logger.error(f"微信监听器启动失败: {e}")