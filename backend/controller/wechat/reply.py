"""微信监听器 - 回复相关"""
import asyncio
import json
import time
import hashlib
import logging
import aiohttp

logger = logging.getLogger("agentforge.wechat_listener")


async def _send_typing_indicator(session, base_url: str, token: str, to_user_id: str,
                                 status: int, typing_ticket: str) -> None:
    """发送「正在输入…」(1) 或停止输入 (2)"""
    body = json.dumps({
        "ilink_user_id": to_user_id,
        "typing_ticket": typing_ticket,
        "status": status,
        "base_info": {"channel_version": "2.2.0"},
    }, ensure_ascii=False)
    h = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": str((2 << 16) | (2 << 8) | 0),
        "X-WECHAT-UIN": str(int(time.time()))[:10]
    }
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.post(f"{base_url}/ilink/bot/sendtyping", data=body, headers=h, timeout=timeout) as resp:
            text = await resp.text()
            logger.info(f"[微信输入状态] sendtyping status={status} resp={text[:100]}")
    except Exception as e:
        logger.info(f"[微信输入状态] sendtyping 失败: {e}")


async def _fetch_typing_ticket(session, base_url: str, token: str, user_id: str,
                               context_token: str = "") -> str:
    """从 getconfig 获取 typing_ticket（需要 context_token）"""
    body = json.dumps({
        "ilink_user_id": user_id,
        "context_token": context_token,
        "base_info": {"channel_version": "2.2.0"},
    }, ensure_ascii=False)
    h = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": str((2 << 16) | (2 << 8) | 0),
        "X-WECHAT-UIN": str(int(time.time()))[:10]
    }
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with session.post(f"{base_url}/ilink/bot/getconfig", data=body, headers=h, timeout=timeout) as resp:
            d = json.loads(await resp.text())
            ticket = str(d.get("typing_ticket") or "")
            if not ticket:
                logger.info(f"[微信输入状态] getconfig 无 ticket, keys={list(d.keys())[:6]}")
            return ticket
    except Exception as e:
        logger.info(f"[微信输入状态] getconfig 失败: {e}")
        return ""


async def _reply_wechat_chunks(chunks: list[str], token: str, account_id: str, base_url: str,
                               to_user_id: str, session, context_token: str = ""):
    """逐条发送分块消息，块间间隔 1.2 秒"""
    for i, chunk in enumerate(chunks):
        if i > 0:
            await asyncio.sleep(1.2)
        await _reply_wechat_text(chunk, token, account_id, base_url, to_user_id, session, context_token)


async def _reply_wechat_text(text: str, token: str, account_id: str, base_url: str,
                             to_user_id: str, session, context_token: str = ""):
    """发送单条微信消息"""
    logger.info(f"[微信发送] to={to_user_id[:12]}... text_len={len(text)} text_repr={repr(text[:500])}")
    reply_msg = {
        "from_user_id": account_id,
        "to_user_id": to_user_id,
        "client_id": hashlib.md5(f"{to_user_id}{time.time()}".encode()).hexdigest()[:16],
        "message_type": 2,
        "message_state": 2,
        "item_list": [{"type": 1, "text_item": {"text": text}}],
    }
    if context_token:
        reply_msg["context_token"] = context_token
    body = json.dumps({"msg": reply_msg, "base_info": {"channel_version": "2.2.0"}}, ensure_ascii=False)
    h = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": str((2 << 16) | (2 << 8) | 0),
        "X-WECHAT-UIN": str(int(time.time()))[:10]
    }
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with session.post(f"{base_url}/ilink/bot/sendmessage", data=body, headers=h, timeout=timeout) as resp:
            d = json.loads(await resp.text())
            if d.get("ret", 0) not in (0, None):
                logger.warning(f"微信回复失败: ret={d.get('ret')}, errcode={d.get('errcode')}")
    except Exception as e:
        logger.error(f"微信回复异常: {e}")
