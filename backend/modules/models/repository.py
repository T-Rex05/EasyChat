"""models 模块 SQLite 数据访问与密钥保护。

密钥保护沿用现有机制：AES-256-GCM，密钥从部署密钥派生（PBKDF2 10万轮）。
数据库中只存密文；对外只出掩码。派生盐与旧实现一致，保证存量密文可解。
"""
from __future__ import annotations

import base64
import functools
import hashlib
import json
import os
from typing import Any

from backend.platform.sqlite import Database, utc_now_iso
from backend.shared.errors import InvalidInputError, NotFoundError

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
    """解密；明文兼容（旧数据未加密时原样返回）。"""
    if not encrypted.startswith(_ENCRYPTED_PREFIX):
        return encrypted
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    data = base64.b64decode(encrypted[len(_ENCRYPTED_PREFIX):])
    nonce, ciphertext = data[:12], data[12:]
    aesgcm = AESGCM(_derive_key(secret))
    return aesgcm.decrypt(nonce, ciphertext, None).decode()


def mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]


class ModelsRepository:
    def __init__(self, db: Database, *, encryption_secret: str) -> None:
        self.db = db
        self._secret = encryption_secret

    def _row_to_profile(self, row: Any) -> dict[str, Any]:
        d = dict(row)
        encrypted = d.pop("api_key_encrypted", "") or ""
        d["has_api_key"] = bool(encrypted)
        d["api_key_masked"] = ""
        try:
            d["api_key_masked"] = mask_key(decrypt_secret(encrypted, self._secret)) if encrypted else ""
        except Exception:
            d["api_key_masked"] = "****"  # 解密失败不泄露任何内容
        return d

    def _profile_snapshot(self, row: Any):
        from backend.modules.models.contracts import ModelProfile

        d = self._row_to_profile(row)
        return ModelProfile(
            config_id=int(d["id"]),
            name=str(d["name"]),
            provider=str(d["provider"]),
            model=str(d["model"]),
            base_url=str(d["base_url"] or ""),
            api_key_masked=str(d["api_key_masked"]),
            has_api_key=bool(d["has_api_key"]),
            is_active=bool(d["is_active"]),
            is_multimodal=bool(d["is_multimodal"]),
            reasoning_effort=str(d["reasoning_effort"] or ""),
            config_version=int(d["config_version"]),
            created_at=str(d["created_at"]),
            updated_at=str(d["updated_at"]),
        )

    def list_configs(self) -> list:
        conn = self.db.connect()
        try:
            rows = conn.execute("SELECT * FROM model_configs ORDER BY id").fetchall()
            return [self._profile_snapshot(r) for r in rows]
        finally:
            conn.close()

    def get_config(self, config_id: int):
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM model_configs WHERE id=?", (config_id,)).fetchone()
            return self._profile_snapshot(row) if row else None
        finally:
            conn.close()

    def get_active_chat(self):
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM model_configs WHERE is_active=1 ORDER BY id LIMIT 1"
            ).fetchone()
            return self._profile_snapshot(row) if row else None
        finally:
            conn.close()

    def decrypt_api_key(self, config_id: int) -> str:
        """runtime 专用解密；仅受信任的 runtime Adapter 层调用，不得进日志。"""
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT api_key_encrypted FROM model_configs WHERE id=?", (config_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise NotFoundError(f"模型配置不存在: {config_id}")
        encrypted = row["api_key_encrypted"] or ""
        return decrypt_secret(encrypted, self._secret) if encrypted else ""

    def create_config(
        self,
        *,
        name: str,
        provider: str,
        model: str,
        api_key: str,
        base_url: str = "",
        is_multimodal: bool = False,
        reasoning_effort: str = "",
    ) -> int:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO model_configs(name, provider, model, api_key_encrypted, base_url, "
                "is_multimodal, reasoning_effort, config_version, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,1,?,?)",
                (
                    name, provider, model,
                    encrypt_secret(api_key, self._secret) if api_key else "",
                    base_url, 1 if is_multimodal else 0, reasoning_effort, now, now,
                ),
            )
            return int(cur.lastrowid)

    def update_config(self, config_id: int, **fields: Any) -> None:
        mapping = {
            "name": "name", "provider": "provider", "model": "model",
            "base_url": "base_url", "is_multimodal": "is_multimodal",
            "reasoning_effort": "reasoning_effort",
        }
        now = utc_now_iso()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT id FROM model_configs WHERE id=?", (config_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"模型配置不存在: {config_id}")
            sets, params = [], []
            for key, column in mapping.items():
                if key in fields and fields[key] is not None:
                    sets.append(f"{column}=?")
                    value = fields[key]
                    if key == "is_multimodal":
                        value = 1 if value else 0
                    params.append(value)
            if "api_key" in fields and fields["api_key"]:
                sets.append("api_key_encrypted=?")
                params.append(encrypt_secret(fields["api_key"], self._secret))
            sets.append("config_version=config_version+1")
            sets.append("updated_at=?")
            params.extend([now, config_id])
            conn.execute(f"UPDATE model_configs SET {', '.join(sets)} WHERE id=?", params)

    def set_active(self, config_id: int) -> None:
        """激活为当前聊天主模型（单激活指针；原子条件切换）。"""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT id FROM model_configs WHERE id=?", (config_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"模型配置不存在: {config_id}")
            conn.execute("UPDATE model_configs SET is_active=CASE WHEN id=? THEN 1 ELSE 0 END, updated_at=?", (config_id, utc_now_iso()))

    def delete_config(self, config_id: int) -> None:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM model_configs WHERE id=?", (config_id,))
            if cur.rowcount != 1:
                raise NotFoundError(f"模型配置不存在: {config_id}")

    # ---- fallback chain（JSON 存 app_settings）---------------------------------

    def get_fallback_chain(self) -> list[int]:
        return self._get_json_setting("model_fallback_chain", [])

    def save_fallback_chain(self, config_ids: list[int]) -> None:
        for cid in config_ids:
            if self.get_config(cid) is None:
                raise InvalidInputError(f"模型配置不存在: {cid}")
        self._set_json_setting("model_fallback_chain", list(config_ids))

    def _get_json_setting(self, key: str, default: Any) -> Any:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
            return json.loads(row["value"]) if row else default
        finally:
            conn.close()

    def _set_json_setting(self, key: str, value: Any) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO app_settings(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value), utc_now_iso()),
            )
