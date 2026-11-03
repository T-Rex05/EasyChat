"""
认证服务单元测试
"""
import pytest
import time
from backend.service.auth.auth_service import (
    hash_password,
    verify_password,
    create_token,
    verify_token,
    JWT_SECRET,
    TOKEN_EXPIRY
)


class TestPasswordHashing:
    """密码哈希测试"""

    def test_hash_password_returns_string(self):
        """密码哈希返回字符串"""
        hashed = hash_password("test_password")
        assert isinstance(hashed, str)
        assert ":" in hashed

    def test_hash_password_different_each_time(self):
        """相同密码哈希结果不同（盐值不同）"""
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """验证正确密码"""
        password = "correct_password"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """验证错误密码"""
        password = "correct_password"
        hashed = hash_password(password)
        assert verify_password("wrong_password", hashed) is False

    def test_verify_password_invalid_format(self):
        """验证无效格式的哈希"""
        assert verify_password("password", "invalid_format") is False
        assert verify_password("password", "") is False


class TestTokenManagement:
    """Token 管理测试"""

    def test_create_token_returns_string(self):
        """创建 Token 返回字符串"""
        token = create_token(user_id=1, username="test_user", role="user")
        assert isinstance(token, str)
        assert token.count(".") == 2  # JWT 格式：header.payload.signature

    def test_verify_token_valid(self):
        """验证有效 Token"""
        token = create_token(user_id=1, username="test_user", role="user")
        payload = verify_token(token)
        
        assert payload is not None
        assert payload["user_id"] == 1
        assert payload["username"] == "test_user"
        assert payload["role"] == "user"

    def test_verify_token_expired(self):
        """验证过期 Token"""
        # 创建一个已过期的 Token（手动设置 exp 为过去时间）
        import json
        from backend.service.auth.auth_service import _base64url_encode
        
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "uid": 1,
            "name": "test_user",
            "role": "user",
            "iat": int(time.time()) - 3600,
            "exp": int(time.time()) - 1800,  # 30 分钟前过期
        }
        
        h = _base64url_encode(json.dumps(header).encode())
        p = _base64url_encode(json.dumps(payload).encode())
        
        import hashlib
        import hmac
        sig = _base64url_encode(
            hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        )
        
        expired_token = f"{h}.{p}.{sig}"
        result = verify_token(expired_token)
        assert result is None

    def test_verify_token_invalid_signature(self):
        """验证无效签名的 Token"""
        token = create_token(user_id=1, username="test_user", role="user")
        # 篡改签名
        parts = token.split(".")
        parts[2] = "invalid_signature"
        tampered_token = ".".join(parts)
        
        result = verify_token(tampered_token)
        assert result is None

    def test_verify_token_malformed(self):
        """验证格式错误的 Token"""
        assert verify_token("not.a.valid.token") is None
        assert verify_token("invalid") is None
        assert verify_token("") is None

    def test_token_expiry_config(self):
        """Token 过期时间配置"""
        assert TOKEN_EXPIRY > 0
        assert isinstance(TOKEN_EXPIRY, int)


class TestTokenPayload:
    """Token 载荷测试"""

    def test_token_contains_required_fields(self):
        """Token 包含必需字段"""
        token = create_token(user_id=123, username="admin", role="admin")
        payload = verify_token(token)
        
        assert "user_id" in payload
        assert "username" in payload
        assert "role" in payload

    def test_token_user_id_correct(self):
        """Token 中的 user_id 正确"""
        token = create_token(user_id=456, username="test_user", role="user")
        payload = verify_token(token)
        assert payload["user_id"] == 456

    def test_token_username_correct(self):
        """Token 中的 username 正确"""
        token = create_token(user_id=1, username="john_doe", role="user")
        payload = verify_token(token)
        assert payload["username"] == "john_doe"

    def test_token_role_correct(self):
        """Token 中的 role 正确"""
        for role in ["user", "admin", "super_admin"]:
            token = create_token(user_id=1, username="test", role=role)
            payload = verify_token(token)
            assert payload["role"] == role
