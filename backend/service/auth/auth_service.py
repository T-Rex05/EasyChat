"""
认证服务 — 用户注册/登录/JWT Token/密码加密

安全机制：
  - 密码使用 scrypt 哈希（标准库，抗 GPU 爆破；存量 SHA256+salt 哈希登录时自动升级）
  - JWT Token 使用 HMAC-SHA256 签名
  - Token 有效期可配置（默认 30 天），滑动窗口自动续期（默认 7 天）

用法：
    from backend.service.auth.auth_service import AuthService

    auth = AuthService()
    # 注册
    user = auth.register("newuser", "password123")
    # 登录
    token = auth.login("admin", "admin123")
    # 验证 Token
    user = auth.verify_token(token)
    # 续期 Token（支持过期宽限期）
    new_token = auth.renew_token(expired_token)
"""
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional, Dict, Any

from dotenv import load_dotenv

# 确保先加载 .env 文件，再读取 JWT_SECRET
# 显式指定项目根目录的 .env，避免工作目录不同导致加载失败
_project_root = Path(__file__).resolve().parent.parent.parent.parent
_dotenv_path = _project_root / ".env"
if _dotenv_path.exists():
    load_dotenv(dotenv_path=str(_dotenv_path), override=False)
else:
    load_dotenv(override=False)

from backend.db.schema import get_conn
from backend.utils.log_utils import log

logger = log

# ── 配置 ──
# 已知的不安全占位值。**注意**：这里只做精确匹配是不够的 ——
# 曾经 docker/.env.example 公布的是 "your-secret-key-here"，它既不在精确集合里、
# 长度（20）也只是触发 warning，于是按 README `cp docker/.env.example .env`
# 部署出来的实例可以用仓库里公开的字符串签名，任何人都能伪造任意 uid/role。
# 因此这里同时做「精确匹配」+「占位族子串匹配」+「长度下限」三重判定。
_INSECURE_JWT_SECRETS = {
    "change-me-in-production", "changeme", "change_me", "change-me",
    "secret", "your-secret-key", "your-secret-key-here", "jwt-secret", "jwt_secret",
    "password", "test", "dev", "insecure", "default",
}
# 占位族子串：命中即拒（覆盖 "your-secret-key-anything" / "REPLACE_ME_xxx" 等变体）
_INSECURE_SUBSTRINGS = (
    "your-secret-key", "change-me", "changeme", "change_me",
    "replace_me", "replace-me", "placeholder", "insecure", "example",
)
_MIN_SECRET_LEN = 32
# 本地开发逃生阀：显式声明"我知道我在用弱密钥"，仅用于本机调试
_ALLOW_WEAK = (os.getenv("ALLOW_WEAK_JWT_SECRET") or "").strip().lower() in ("1", "true", "yes")

_JWT_SECRET_HINT = (
    "请在 .env 中设置一个随机密钥："
    "python -c \"import secrets;print(secrets.token_hex(32))\""
)


def _looks_like_placeholder(value: str) -> str:
    """返回命中的原因；未命中返回空串。"""
    low = value.lower()
    if low in _INSECURE_JWT_SECRETS:
        return "命中已知不安全占位值"
    for sub in _INSECURE_SUBSTRINGS:
        if sub in low:
            return f"包含占位族子串 {sub!r}"
    return ""


JWT_SECRET = (os.getenv("JWT_SECRET") or "").strip()
_reason = _looks_like_placeholder(JWT_SECRET)
if _reason and not _ALLOW_WEAK:
    # 占位符比"没配置"更危险：它让下面的随机兜底与告警都不触发，
    # 等于用仓库里公开的字符串签名，任何人都能伪造任意 uid/role。
    raise RuntimeError(
        f"JWT_SECRET 不安全（{_reason}），拒绝启动。" + _JWT_SECRET_HINT +
        " 若确实要用弱密钥（仅限本机调试），显式设置 ALLOW_WEAK_JWT_SECRET=1"
    )
if not JWT_SECRET:
    JWT_SECRET = secrets.token_hex(32)
    logger.warning(
        "⚠️  JWT_SECRET 未配置，已自动生成随机密钥（重启后所有用户 Token 将失效！）"
        " 请在 .env 中设置 JWT_SECRET=xxx"
    )
elif len(JWT_SECRET) < _MIN_SECRET_LEN and not _ALLOW_WEAK:
    # 长度不足的密钥可被离线暴力/字典破解，而这种部署在默认配置下完全可能，
    # 所以按"事前声明"原则直接拒绝，而不是留一条 warning 让人忽略。
    raise RuntimeError(
        f"JWT_SECRET 过短（{len(JWT_SECRET)} < {_MIN_SECRET_LEN}），拒绝启动。" + _JWT_SECRET_HINT +
        " 若确实要用弱密钥（仅限本机调试），显式设置 ALLOW_WEAK_JWT_SECRET=1"
    )

# Token 总有效期（默认 30 天 = 720 小时）
TOKEN_EXPIRY = int(os.getenv("TOKEN_EXPIRY_HOURS", "720")) * 3600

# 滑动窗口续期阈值：剩余有效期低于此值时自动续期（默认 7 天 = 604800 秒）
TOKEN_RENEW_THRESHOLD = int(os.getenv("TOKEN_RENEW_THRESHOLD_SECONDS", "604800"))

# Token 刷新宽限期：过期后仍允许刷新的时长（默认 7 天 = 604800 秒）
TOKEN_REFRESH_GRACE_PERIOD = int(os.getenv("TOKEN_REFRESH_GRACE_SECONDS", "604800"))


# ────────────────────────────────────────────────────────────
# 密码工具
# ────────────────────────────────────────────────────────────
# scrypt 参数（内存 ≈ 128*N*r = 16MB，单次 ~50ms，抗 GPU 爆破）
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_PREFIX = "scrypt$"


def hash_password(password: str) -> str:
    """scrypt 密码哈希。格式: scrypt$N$r$p$salt:dk_hex（含冒号，兼容旧解析）。"""
    salt = secrets.token_hex(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN,
    )
    return f"{_SCRYPT_PREFIX}{_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt}:{dk.hex()}"


def needs_rehash(hashed: str) -> bool:
    """判断存量哈希是否需要升级（旧格式 salt:sha256hex 需要）。"""
    return bool(hashed) and not hashed.startswith(_SCRYPT_PREFIX)


def verify_password(password: str, hashed: str) -> bool:
    """验证密码。兼容新格式（scrypt$...）与旧格式（salt:sha256hex）。"""
    if not hashed or not isinstance(hashed, str):
        return False
    if hashed.startswith(_SCRYPT_PREFIX):
        try:
            meta, _, dk_hex = hashed.partition(":")
            _, n_s, r_s, p_s, salt = meta.split("$")
            dk = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt.encode("utf-8"),
                n=int(n_s), r=int(r_s), p=int(p_s), dklen=_SCRYPT_DKLEN,
            )
            return hmac.compare_digest(dk.hex(), dk_hex)
        except (ValueError, KeyError, TypeError):
            return False
    # 旧格式：salt:sha256hex
    try:
        salt, expected = hashed.split(":", 1)
        actual = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# ────────────────────────────────────────────────────────────
# JWT Token
# ────────────────────────────────────────────────────────────

def _base64url_encode(data: bytes) -> str:
    """URL-safe base64 编码（无填充）。"""
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _base64url_decode(s: str) -> bytes:
    """URL-safe base64 解码。"""
    import base64
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_token(user_id: int, username: str, role: str) -> str:
    """创建 JWT Token。"""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "uid": user_id,
        "name": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_EXPIRY,
    }
    h = _base64url_encode(json.dumps(header).encode())
    p = _base64url_encode(json.dumps(payload).encode())
    sig = _base64url_encode(
        hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    )
    return f"{h}.{p}.{sig}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """验证 JWT Token，返回用户信息或 None。"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h, p, sig = parts

        # 验证签名
        expected_sig = _base64url_encode(
            hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected_sig):
            return None

        # 解码 payload
        payload = json.loads(_base64url_decode(p))

        # 检查过期
        if payload.get("exp", 0) < time.time():
            return None

        return {
            "user_id": payload["uid"],
            "username": payload["name"],
            "role": payload["role"],
        }
    except (ValueError, KeyError, json.JSONDecodeError, TypeError):
        return None


def check_token_renewal(token: str) -> Optional[str]:
    """检查 token 是否需要续期（滑动窗口）。

    当剩余有效期 < TOKEN_RENEW_THRESHOLD 时，签发新 token 返回。
    否则返回 None，表示无需续期。
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h, p, sig = parts

        # 验签：防止伪造 token 换取合法 token（不验签即等于免登录提权）
        expected_sig = _base64url_encode(
            hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected_sig):
            return None

        payload = json.loads(_base64url_decode(p))
        exp = payload.get("exp", 0)
        remaining = exp - time.time()

        if 0 < remaining < TOKEN_RENEW_THRESHOLD:
            return create_token(
                payload["uid"],
                payload["name"],
                payload["role"],
            )
        return None
    except (ValueError, KeyError, json.JSONDecodeError, TypeError):
        return None


def renew_token(token: str) -> Optional[str]:
    """为已过期但仍在宽限期内的 token 签发新 token。

    用于 /api/auth/refresh 端点：用户长时间未访问后回来，
    token 虽已过期，但无需重新登录。

    宽限期由 TOKEN_REFRESH_GRACE_PERIOD 控制（默认 7 天）。
    签名无效或超出宽限期的 token 返回 None。
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h, p, sig = parts

        # 验证签名（过期也验，防止伪造）
        expected_sig = _base64url_encode(
            hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected_sig):
            return None

        payload = json.loads(_base64url_decode(p))
        exp = payload.get("exp", 0)
        elapsed = time.time() - exp  # 正数 = 已过期

        # 在宽限期内才允许刷新
        if 0 <= elapsed < TOKEN_REFRESH_GRACE_PERIOD:
            return create_token(
                payload["uid"],
                payload["name"],
                payload["role"],
            )
        return None
    except (ValueError, KeyError, json.JSONDecodeError, TypeError):
        return None


# ────────────────────────────────────────────────────────────
# AuthService
# ────────────────────────────────────────────────────────────

class AuthService:
    """用户认证服务。"""

    def register(self, username: str, password: str, email: str = "") -> Dict[str, Any]:
        """
        注册新用户。

        返回: {"user_id": ..., "username": ..., "token": ...}
        异常: ValueError（用户名已存在/密码太短）
        """
        if len(username) < 2:
            raise ValueError("用户名至少 2 个字符")
        if len(password) < 6:
            raise ValueError("密码至少 6 个字符")

        conn = get_conn()
        try:
            # 检查用户名是否已存在
            existing = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if existing:
                raise ValueError(f"用户名 '{username}' 已存在")

            # 创建用户
            hashed = hash_password(password)
            cur = conn.execute(
                "INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)",
                (username, hashed, email, "user"),
            )
            conn.commit()
            user_id = cur.lastrowid

            # 生成 Token
            token = create_token(user_id, username, "user")

            logger.info(f"用户注册: {username} (id={user_id})")
            return {"user_id": user_id, "username": username, "token": token}

        finally:
            conn.close()

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        用户登录。

        返回: {"user_id": ..., "username": ..., "role": ..., "token": ...}
        异常: ValueError（用户名或密码错误）
        """
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT id, username, password, role, status FROM users WHERE username = ?",
                (username,),
            ).fetchone()

            if not row:
                raise ValueError("用户名或密码错误")

            if row["status"] != 1:
                raise ValueError("账号已被禁用")

            if not verify_password(password, row["password"]):
                raise ValueError("用户名或密码错误")

            # 存量旧哈希（SHA256+salt）登录成功后自动升级为 scrypt
            if needs_rehash(row["password"]):
                try:
                    conn.execute(
                        "UPDATE users SET password = ? WHERE id = ?",
                        (hash_password(password), row["id"]),
                    )
                    conn.commit()
                    logger.info(f"密码哈希已升级为 scrypt: {username} (id={row['id']})")
                except Exception as e:
                    logger.warning(f"密码哈希升级失败: {e}")

            token = create_token(row["id"], row["username"], row["role"])

            logger.info(f"用户登录: {username} (id={row['id']})")
            return {
                "user_id": row["id"],
                "username": row["username"],
                "role": row["role"],
                "token": token,
            }

        finally:
            conn.close()

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户信息。"""
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT id, username, email, role, avatar, status, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_users(self) -> list:
        """列出所有用户（管理员用）。"""
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT id, username, email, role, status, created_at FROM users ORDER BY id"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
