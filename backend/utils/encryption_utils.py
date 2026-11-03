"""
加密工具类

用于敏感信息（如 API Key）的加密存储和解密读取
"""
import os
import base64
import hashlib
from typing import Optional

# 加密密钥（从环境变量获取，或使用默认值）
# 生产环境应设置环境变量 ENCRYPTION_KEY
_DEFAULT_KEY = "agentforge-default-encryption-key-2024"


def _get_key() -> bytes:
    """获取加密密钥"""
    key = os.getenv("ENCRYPTION_KEY", _DEFAULT_KEY)
    # 将密钥转换为 32 字节的 key
    return hashlib.sha256(key.encode()).digest()


class EncryptionUtils:
    """加密工具类"""
    
    def __init__(self, key: Optional[str] = None):
        """
        初始化加密工具
        
        Args:
            key: 加密密钥（可选，默认从环境变量获取）
        """
        if key:
            self._key = hashlib.sha256(key.encode()).digest()
        else:
            self._key = _get_key()
    
    def encrypt(self, plain_text: str) -> str:
        """
        加密字符串
        
        Args:
            plain_text: 明文
            
        Returns:
            Base64 编码的密文
        """
        if not plain_text:
            return ""
        
        try:
            # 简单的 XOR 加密（生产环境应使用 cryptography 库）
            key_bytes = self._key
            plain_bytes = plain_text.encode('utf-8')
            
            # 扩展密钥以匹配明文长度
            key_extended = (key_bytes * ((len(plain_bytes) // len(key_bytes)) + 1))[:len(plain_bytes)]
            
            # XOR 加密
            cipher_bytes = bytes([p ^ k for p, k in zip(plain_bytes, key_extended)])
            
            # Base64 编码
            return base64.b64encode(cipher_bytes).decode('utf-8')
        except Exception:
            # 加密失败时返回原值（非生产环境兼容）
            return plain_text
    
    def decrypt(self, cipher_text: str) -> str:
        """
        解密字符串
        
        Args:
            cipher_text: Base64 编码的密文
            
        Returns:
            明文
        """
        if not cipher_text:
            return ""
        
        try:
            # Base64 解码
            cipher_bytes = base64.b64decode(cipher_text.encode('utf-8'))
            
            # XOR 解密（与加密相同）
            key_bytes = self._key
            key_extended = (key_bytes * ((len(cipher_bytes) // len(key_bytes)) + 1))[:len(cipher_bytes)]
            
            plain_bytes = bytes([c ^ k for c, k in zip(cipher_bytes, key_extended)])
            
            return plain_bytes.decode('utf-8')
        except Exception:
            # 解密失败时返回原值（兼容未加密数据）
            return cipher_text
    
    @staticmethod
    def is_encrypted(value: str) -> bool:
        """
        判断字符串是否已加密
        
        Args:
            value: 待判断的字符串
            
        Returns:
            是否已加密
        """
        if not value:
            return False
        
        try:
            # 尝试 Base64 解码
            decoded = base64.b64decode(value.encode('utf-8'))
            # 如果解码成功且长度合理，可能是加密的
            return len(decoded) > 0
        except Exception:
            return False


# 默认实例
_default_utils: Optional[EncryptionUtils] = None


def get_encryption_utils() -> EncryptionUtils:
    """获取加密工具实例（单例）"""
    global _default_utils
    if _default_utils is None:
        _default_utils = EncryptionUtils()
    return _default_utils