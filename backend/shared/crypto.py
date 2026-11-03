"""部署密钥保护的共享加解密（模型密钥与渠道凭证共用）。

沿用现有机制：AES-256-GCM，密钥由部署密钥 PBKDF2 派生（盐与旧实现一致，
保证存量密文可解）。数据库只存密文，对外只出掩码；明文不得进日志。
"""
from __future__ import annotations

import base64
import functools
import hashlib
import os

_ENCRYPTED_PREFIX = "enc:v1:"


@functools.lru_cache(maxsize=4)
def _derive_key(secret: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), b"agentforge_salt", 100000, dklen=32)


def encrypt_secret(plaintext: str, secret: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aesgcm = AESGCM(_derive_key(secret))
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return _ENCRYPTED_PREFIX + base64.b64encode(nonce + ciphertext).decode()


def decrypt_secret(encrypted: str, secret: str) -> str:
    """解密；明文兼容（旧数据/测试未加密时原样返回）。"""
    if not encrypted.startswith(_ENCRYPTED_PREFIX):
        return encrypted
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    data = base64.b64decode(encrypted[len(_ENCRYPTED_PREFIX):])
    nonce, ciphertext = data[:12], data[12:]
    aesgcm = AESGCM(_derive_key(secret))
    return aesgcm.decrypt(nonce, ciphertext, None).decode()


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]
