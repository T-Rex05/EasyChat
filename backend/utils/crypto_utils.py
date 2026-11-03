"""API Key 加密工具 — AES-256-GCM，密钥从 JWT_SECRET 派生"""
import os
import base64
import functools
import hashlib
import logging

logger = logging.getLogger(__name__)

# 记忆加密标记前缀（用于识别已加密的内容）
ENCRYPTED_PREFIX = "ENC:"


@functools.lru_cache(maxsize=1)
def _derive_key():
    """从 JWT_SECRET 派生 32 字节加密密钥（结果缓存：PBKDF2 10 万轮，逐行解密时不能重算）。"""
    from backend.service.auth.auth_service import JWT_SECRET
    return hashlib.pbkdf2_hmac("sha256", JWT_SECRET.encode(), b"agentforge_salt", 100000, dklen=32)


def encrypt(plaintext: str) -> str:
    """AES-256-GCM 加密，返回 base64 编码的密文。"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _derive_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt(encrypted: str) -> str:
    """解密 AES-256-GCM 密文。"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _derive_key()
    data = base64.b64decode(encrypted)
    nonce, ciphertext = data[:12], data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()


# ========== 记忆内容加密 ==========

def encrypt_memory_content(content: str) -> str:
    """
    加密记忆内容

    返回带 ENC: 前缀的密文，用于区分明文和密文。
    如果内容已经加密，直接返回。
    """
    if not content:
        return content
    if content.startswith(ENCRYPTED_PREFIX):
        return content  # 已加密
    try:
        encrypted = encrypt(content)
        return ENCRYPTED_PREFIX + encrypted
    except Exception as e:
        logger.warning(f"Failed to encrypt memory content: {e}")
        return content  # 加密失败，返回明文


def decrypt_memory_content(content: str) -> str:
    """
    解密记忆内容

    如果内容未加密（无 ENC: 前缀），直接返回原文。
    """
    if not content:
        return content
    if not content.startswith(ENCRYPTED_PREFIX):
        return content  # 未加密
    try:
        encrypted = content[len(ENCRYPTED_PREFIX):]
        return decrypt(encrypted)
    except Exception as e:
        logger.warning(f"Failed to decrypt memory content: {e}")
        return content  # 解密失败，返回原文


def is_memory_encrypted(content: str) -> bool:
    """检查记忆内容是否已加密"""
    return bool(content and content.startswith(ENCRYPTED_PREFIX))
