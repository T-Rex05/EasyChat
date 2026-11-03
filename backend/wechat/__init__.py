"""
AgentForge 微信文件收发工具模块

基于 iLink Bot API 的 AES-128-ECB 加密 + CDN 上传/下载链路。
从 Hermes weixin.py 提取核心逻辑，适配 AgentForge 架构。

功能：
  - AES-128-ECB 加解密（PKCS7 填充）
  - 文件发送：PDF / Markdown / 纯文本 / 任意格式
  - 文件接收：下载 CDN 加密文件并解密

iLink 消息 item_type：
  ITEM_TEXT=1  文本消息
  ITEM_IMAGE=2 图片消息
  ITEM_VOICE=3 语音消息
  ITEM_FILE=4  文件消息
  ITEM_VIDEO=5 视频消息
"""

import asyncio
import base64
import hashlib
import json
import logging
import secrets
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("agentforge.wechat")

# ── iLink 常量 ──
ITEM_TEXT  = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE  = 4
ITEM_VIDEO = 5

MEDIA_IMAGE = 1
MEDIA_VIDEO = 2
MEDIA_FILE  = 3
MEDIA_VOICE = 4

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
CDN_BASE_URL   = "https://novac2c.cdn.weixin.qq.com/c2c"

EP_SEND_MESSAGE   = "ilink/bot/sendmessage"
EP_GET_UPLOAD_URL = "ilink/bot/getuploadurl"

# 接收文件白名单扩展名
ALLOWED_FILE_EXTENSIONS = frozenset({
    ".pdf", ".md", ".txt", ".docx", ".xlsx", ".pptx",
    ".zip", ".json", ".csv", ".py", ".js", ".html", ".css",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
})

# 文件大小上限
# 上传：iLink CDN 有 8MB 硬限制
# 下载：无硬限制，这里设 50MB 防内存爆炸
MAX_UPLOAD_SIZE = 8 * 1024 * 1024
MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024


# ══════════════════════════════════════════════════════════════
# AES-128-ECB 加解密（pycryptodome）
# ══════════════════════════════════════════════════════════════

def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(padded: bytes) -> bytes:
    pad_len = padded[-1]
    if pad_len < 1 or pad_len > 16:
        return padded
    if padded.endswith(bytes([pad_len]) * pad_len):
        return padded[:-pad_len]
    return padded


def aes128_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-128-ECB 加密 + PKCS7 填充。"""
    from Crypto.Cipher import AES
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher.encrypt(_pkcs7_pad(plaintext))


def aes128_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """AES-128-ECB 解密 + 自动去 PKCS7 填充。"""
    from Crypto.Cipher import AES
    cipher = AES.new(key, AES.MODE_ECB)
    padded = cipher.decrypt(ciphertext)
    return _pkcs7_unpad(padded)


def aes_padded_size(size: int) -> int:
    """计算 AES 加密后的大小（含 PKCS7 填充）。"""
    return ((size + 1 + 15) // 16) * 16


def _parse_aes_key(aes_key_b64: str) -> bytes:
    """解析 AES 密钥（复刻 Hermes weixin.py L362-369）。

    iLink API 的 aes_key 始终是 base64 编码的：
      - Case 1: base64(raw_16_bytes_key) → decode 得 16 bytes → 直接用作 AES-128 密钥
      - Case 2: base64(hex_string_32_chars) → decode 得 32 bytes ASCII → fromhex → 16 bytes 密钥
    """
    if not aes_key_b64:
        raise ValueError("aes_key 为空")
    decoded = base64.b64decode(aes_key_b64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32:
        text = decoded.decode("ascii", errors="ignore")
        if all(ch in "0123456789abcdefABCDEF" for ch in text):
            return bytes.fromhex(text)
    # 兜底：直接当作 raw bytes 密钥
    return decoded


# ══════════════════════════════════════════════════════════════
# iLink API 公共 helpers
# ══════════════════════════════════════════════════════════════

def ilink_headers(token: str, body_len: int = 0) -> Dict[str, str]:
    """构建 iLink Bot API 请求头。"""
    import time
    h = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": str((2 << 16) | (2 << 8) | 0),
        "X-WECHAT-UIN": str(int(time.time()))[:10],
    }
    if body_len:
        h["Content-Length"] = str(body_len)
    return h


async def ilink_post(session, base_url: str, endpoint: str,
                     payload: dict, token: str, timeout: int = 15) -> dict:
    """POST 到 iLink API，返回 JSON 响应。"""
    import aiohttp
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = ilink_headers(token, len(body))
    url = f"{base_url.rstrip('/')}/{endpoint}"
    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    async with session.post(url, data=body, headers=headers, timeout=timeout_obj) as resp:
        return json.loads(await resp.text())


# ══════════════════════════════════════════════════════════════
# 微信消息发送
# ══════════════════════════════════════════════════════════════

async def send_text(session, base_url: str, token: str,
                    to_user_id: str, text: str,
                    context_token: str = "") -> Optional[str]:
    """发送文本消息到微信用户。返回 client_id。"""
    import time as _time
    client_id = hashlib.md5(f"{to_user_id}{_time.time()}".encode()).hexdigest()[:16]
    msg = {
        "from_user_id": "",
        "to_user_id": to_user_id,
        "client_id": client_id,
        "message_type": 2,
        "message_state": 2,
        "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
    }
    if context_token:
        msg["context_token"] = context_token
    data = await ilink_post(session, base_url, EP_SEND_MESSAGE,
                            {"msg": msg, "base_info": {"channel_version": "2.2.0"}},
                            token)
    ret = data.get("ret", 0)
    if ret not in (0, None):
        logger.warning(f"[wechat] 发送文本失败: ret={ret}, errcode={data.get('errcode')}")
        return None
    return client_id


# ══════════════════════════════════════════════════════════════
# CDN 上传 + 文件发送
# ══════════════════════════════════════════════════════════════

async def _get_upload_url(session, base_url: str, token: str,
                          to_user_id: str, media_type: int,
                          filekey: str, rawsize: int, rawfilemd5: str,
                          filesize: int, aeskey_hex: str) -> dict:
    """请求 iLink 获取 CDN 上传凭证。"""
    return await ilink_post(session, base_url, EP_GET_UPLOAD_URL, {
        "filekey": filekey,
        "media_type": media_type,
        "to_user_id": to_user_id,
        "rawsize": rawsize,
        "rawfilemd5": rawfilemd5,
        "filesize": filesize,
        "no_need_thumb": True,
        "aeskey": aeskey_hex,
    }, token)


async def _upload_ciphertext_to_cdn(session, upload_url: str,
                                     ciphertext: bytes) -> str:
    """POST 密文到 CDN，返回 x-encrypted-param 响应头。"""
    import aiohttp

    async def _do() -> str:
        headers = {"Content-Type": "application/octet-stream"}
        async with session.post(upload_url, data=ciphertext, headers=headers) as resp:
            if resp.status == 200:
                enc_param = resp.headers.get("x-encrypted-param")
                if enc_param:
                    await resp.read()
                    return enc_param
                raw = await resp.text()
                raise RuntimeError(f"CDN upload missing x-encrypted-param: {raw[:200]}")
            raw = await resp.text()
            raise RuntimeError(f"CDN upload HTTP {resp.status}: {raw[:200]}")
    return await asyncio.wait_for(_do(), timeout=120)


async def send_file_to_wechat(
    session,
    *,
    file_path: str,
    to_user_id: str,
    token: str,
    base_url: str = ILINK_BASE_URL,
    caption: str = "",
    file_name: str = "",
) -> bool:
    """发送文件到微信用户（PDF / Markdown / 任意格式）。

    完整流程：
      1. 读取文件
      2. 生成 AES 密钥
      3. 请求 CDN 上传凭证
      4. AES-128-ECB 加密
      5. 上传密文到 CDN
      6. 下发 type=4 文件消息（+ 可选文本 caption）

    Args:
        session: aiohttp.ClientSession
        file_path: 本地文件路径
        to_user_id: 微信用户 open_id
        token: iLink bot token
        base_url: iLink API 基础地址
        caption: 文件附带的文字说明（可选）
        file_name: 显示的文件名（默认取 file_path 的 basename）

    Returns:
        (bool, str) — (是否成功, 失败原因)。成功时第二个元素为空字符串。
    """
    plaintext = Path(file_path).read_bytes()

    if len(plaintext) > MAX_UPLOAD_SIZE:
        logger.error(f"[wechat] 文件超过 8MB 上传限制: {len(plaintext)} bytes, path={file_path}")
        return False, f"文件超过 8MB 上传限制（{len(plaintext)} bytes）"

    if not file_name:
        file_name = Path(file_path).name

    # 1. 生成密钥
    aes_key = secrets.token_bytes(16)
    filekey = secrets.token_hex(16)
    rawsize = len(plaintext)
    rawfilemd5 = hashlib.md5(plaintext).hexdigest()
    filesize = aes_padded_size(rawsize)
    aeskey_hex = aes_key.hex()

    # 2. 获取 CDN 上传凭证
    upload_resp = await _get_upload_url(
        session, base_url=base_url, token=token,
        to_user_id=to_user_id, media_type=MEDIA_FILE,
        filekey=filekey, rawsize=rawsize,
        rawfilemd5=rawfilemd5, filesize=filesize,
        aeskey_hex=aeskey_hex,
    )
    upload_param = str(upload_resp.get("upload_param") or "")
    upload_full_url = str(upload_resp.get("upload_full_url") or "")

    if upload_full_url:
        upload_url = upload_full_url
    elif upload_param:
        upload_url = f"{CDN_BASE_URL.rstrip('/')}/upload?upload_param={upload_param}&filekey={filekey}"
    else:
        logger.error(
            f"[wechat] getUploadUrl 未返回有效凭证: "
            f"ret={upload_resp.get('ret')} errcode={upload_resp.get('errcode')} "
            f"errmsg={upload_resp.get('errmsg')} "
            f"完整响应={json.dumps(upload_resp, ensure_ascii=False)[:500]}"
        )
        return False, "获取 CDN 上传凭证失败"

    # 3. 加密
    ciphertext = aes128_ecb_encrypt(plaintext, aes_key)

    # 4. 上传到 CDN
    try:
        encrypted_query_param = await _upload_ciphertext_to_cdn(
            session, upload_url, ciphertext,
        )
    except Exception as e:
        logger.error(f"[wechat] CDN 上传失败: {e}")
        return False, f"CDN 上传失败: {e}"

    # 5. aes_key 编码: base64(hex_string) — iLink API 要求
    aes_key_for_api = base64.b64encode(aes_key.hex().encode("ascii")).decode("ascii")

    # 6. 构造 type=4 file_item
    file_item = {
        "type": ITEM_FILE,
        "file_item": {
            "media": {
                "encrypt_query_param": encrypted_query_param,
                "aes_key": aes_key_for_api,
                "encrypt_type": 1,
            },
            "file_name": file_name,
            "len": str(rawsize),
        },
    }

    # 7. 先发 caption（如果有）
    import time as _time
    if caption:
        cl_id = hashlib.md5(f"{to_user_id}{_time.time()}".encode()).hexdigest()[:16]
        await ilink_post(session, base_url, EP_SEND_MESSAGE, {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": cl_id,
                "message_type": 2,
                "message_state": 2,
                "item_list": [{"type": ITEM_TEXT, "text_item": {"text": caption}}],
            },
            "base_info": {"channel_version": "2.2.0"},
        }, token)

    # 8. 下发文件消息
    cl_id = hashlib.md5(f"{to_user_id}{_time.time()}".encode()).hexdigest()[:16]
    send_resp = await ilink_post(session, base_url, EP_SEND_MESSAGE, {
        "msg": {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": cl_id,
            "message_type": 2,
            "message_state": 2,
            "item_list": [file_item],
        },
        "base_info": {"channel_version": "2.2.0"},
    }, token)

    ret = send_resp.get("ret", 0)
    if ret not in (0, None):
        errmsg = send_resp.get("errmsg") or ""
        logger.warning(
            f"[wechat] 发送文件失败: ret={ret} "
            f"errcode={send_resp.get('errcode')} errmsg={errmsg} "
            f"完整响应={json.dumps(send_resp, ensure_ascii=False)[:500]}"
        )
        # prepare failed = iLink 会话过期（24 小时窗口），给出可操作的提示
        if "prepare failed" in errmsg.lower() or (ret == -2 and not send_resp.get("errcode")):
            return False, "微信会话已过期（24 小时未互动），请给 bot 发一条消息激活后再试"
        return False, f"微信发送失败: ret={ret} errmsg={errmsg}"

    logger.info(f"[wechat] 文件已发送: {file_name} ({rawsize} bytes) → {to_user_id[:12]}...")
    return True, ""


# ══════════════════════════════════════════════════════════════
# 文件接收（CDN 下载 + AES 解密）
# ══════════════════════════════════════════════════════════════

async def download_and_decrypt_file(
    session,
    file_item: dict,
    output_dir: str,
) -> Tuple[bool, str, Optional[bytes]]:
    """下载并解密微信 CDN 文件（复刻 Hermes weixin.py _download_file + _download_and_decrypt_media）。

    支持两种下载路径：
      1. encrypt_query_param → 构建 CDN 下载 URL
      2. full_url / cdn_url → 直接下载

    密钥来源（按优先级）：
      media.aes_key → file_item.aeskey → media.aeskey

    Returns:
        (success, saved_path_or_error, decrypted_bytes_or_None)
    """
    import aiohttp as _aiohttp
    from urllib.parse import quote

    fd = file_item or {}
    filename = fd.get("file_name") or "unnamed.bin"
    media = fd.get("media") or {}

    # ── 1. 确定下载 URL（对齐 weixin.py _download_and_decrypt_media L652-664）──
    encrypt_query_param = media.get("encrypt_query_param")
    full_url = (media.get("full_url") or fd.get("cdn_url") or
                fd.get("url") or fd.get("full_url") or "")

    if encrypt_query_param:
        url = f"{CDN_BASE_URL.rstrip('/')}/download?encrypted_query_param={quote(encrypt_query_param, safe='')}"
    elif full_url:
        url = full_url
    else:
        logger.warning(f"[wechat] 文件无可用下载 URL: filename={filename}, "
                       f"file_keys={list(fd.keys())[:8]}, media_keys={list(media.keys())[:8]}")
        return (False, filename, None)

    # ── 2. 文件类型白名单 ──
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_FILE_EXTENSIONS and ext:
        logger.warning(f"[wechat] 文件类型不允许接收: {filename}")
        return (False, filename, None)

    # ── 3. 下载 ──
    timeout = _aiohttp.ClientTimeout(total=60)
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                logger.warning(f"[wechat] 下载文件失败 HTTP {resp.status}: {url[:100]}")
                return (False, filename, None)
            data = await resp.read()
    except Exception as e:
        logger.error(f"[wechat] 下载文件异常: {e}")
        return (False, filename, None)

    # ── 4. AES-128-ECB 解密（对齐 weixin.py L663-664）──
    aes_key_b64 = (media.get("aes_key") or fd.get("aeskey") or
                   media.get("aeskey") or "")
    if aes_key_b64:
        try:
            key = _parse_aes_key(aes_key_b64)
            data = aes128_ecb_decrypt(data, key)
            logger.debug(f"[wechat] 文件解密成功: filename={filename}, "
                         f"key_source={'media.aes_key' if media.get('aes_key') else 'fd.aeskey'}, "
                         f"decoded_key_len={len(key)}")
        except Exception as e:
            logger.error(f"[wechat] 文件 AES 解密失败: {e}, "
                         f"url_type={'encrypt_query_param' if encrypt_query_param else 'direct'}, "
                         f"aes_key_b64_len={len(aes_key_b64)}, "
                         f"fd_keys={list(fd.keys())[:10]}, "
                         f"media_keys={list(media.keys())[:10]}")
            return (False, filename, None)

    # ── 5. 大小检查 ──
    if len(data) > MAX_DOWNLOAD_SIZE:
        logger.warning(f"[wechat] 解密后文件超过 50MB: {len(data)} bytes")
        return (False, filename, None)

    # ── 6. 存储到本地 ──
    output_path = Path(output_dir) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    counter = 1
    stem, suffix = output_path.stem, output_path.suffix
    while output_path.exists():
        output_path = output_path.parent / f"{stem}_{counter}{suffix}"
        counter += 1
    output_path.write_bytes(data)

    logger.info(f"[wechat] 文件已接收: {filename} ({len(data)} bytes) → {output_path}")
    return (True, str(output_path), data)
