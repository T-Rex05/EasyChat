"""
模型配置数据访问实现
"""
import os
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db.model_config_mapper import ModelConfigMapper
from backend.utils.mysql_db_manager import MySQLDBManager
from backend.utils.encryption_utils import EncryptionUtils
from backend.utils.log_utils import log

logger = log

ADMIN_ROLE_ID = "R001"
LOCAL_BGE_DEFAULT_BASE_URL = "http://eyes-embedding-bge:8002/v1"
DEFAULT_BGE_EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"
DEFAULT_EMBEDDING_CONFIG = {
    "id": 0,
    "config_name": "Embedding 默认配置",
    "provider_type": "OPENAI_COMPATIBLE",
    "base_url": "",
    "api_key": "",
    "model_name": "",
    "dimension": 1024,
    "batch_size": 8,
    "timeout_seconds": 180,
    "send_dimensions": False,
    "is_current": 1,
    "enabled": 1,
    "last_test_status": None,
    "last_test_message": None,
    "last_test_time": None,
}


def _env_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _env_flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_flag_disabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"0", "false", "no", "off"}


def _local_bge_default_enabled() -> bool:
    return not _env_flag_disabled("USE_LOCAL_BGE") and not _env_flag_enabled("RAG_EMBEDDING_DISABLED")


def _is_local_bge_default_url(base_url: str) -> bool:
    return (base_url or "").strip().rstrip("/").lower() == LOCAL_BGE_DEFAULT_BASE_URL.lower()


def _env_int(env_name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(env_name, "") or 0)
    except (TypeError, ValueError):
        return default
    return value if minimum <= value <= maximum else default


def _default_embedding_model_for_url(base_url: str) -> str:
    normalized = (base_url or "").lower()
    if not normalized:
        return ""
    if _is_local_bge_default_url(base_url) or "bge" in normalized:
        return DEFAULT_BGE_EMBEDDING_MODEL
    if "dashscope" in normalized or "aliyuncs" in normalized:
        return "text-embedding-v4"
    if "bigmodel" in normalized or "zhipu" in normalized:
        return "embedding-3"
    if "localhost" in normalized or "127.0.0.1" in normalized or ":11434" in normalized or "ollama" in normalized:
        return "qwen3-embedding:8b"
    return "text-embedding-3-small"


def _default_provider_type(base_url: str) -> str:
    normalized = (base_url or "").lower()
    if _is_local_bge_default_url(base_url) or "bge" in normalized:
        return "LOCAL_BGE"
    if "dashscope" in normalized or "aliyuncs" in normalized:
        return "DASHSCOPE"
    if "bigmodel" in normalized or "zhipu" in normalized:
        return "ZHIPU"
    return "OPENAI_COMPATIBLE"


def _resolved_default_embedding_config() -> Dict[str, Any]:
    base_url = _env_value("RAG_EMBEDDING_BASE_URL")
    if _is_local_bge_default_url(base_url) and not _local_bge_default_enabled():
        base_url = ""
    if not base_url and _local_bge_default_enabled():
        base_url = _env_value("RAG_BGE_EMBEDDING_BASE_URL", "BGE_EMBEDDING_BASE_URL") or LOCAL_BGE_DEFAULT_BASE_URL

    model_name = _env_value("RAG_EMBEDDING_MODEL") or _default_embedding_model_for_url(base_url)
    config_name = "Embedding 默认配置（未配置 Base URL）"
    if base_url:
        config_name = "本地 BGE-large 默认配置" if _is_local_bge_default_url(base_url) else "环境 Embedding 默认配置"

    return {
        "config_name": config_name,
        "provider_type": _default_provider_type(base_url),
        "base_url": base_url,
        "api_key": _env_value("RAG_EMBEDDING_API_KEY") or ("local" if base_url else ""),
        "model_name": model_name,
        "dimension": _env_int("RAG_EMBEDDING_DIMENSION", 1024, 32, 8192),
        "batch_size": _env_int("RAG_EMBEDDING_BATCH_SIZE", 8, 1, 128),
        "timeout_seconds": _env_int("RAG_EMBEDDING_TIMEOUT_SECONDS", _env_int("RAG_EMBEDDING_TIMEOUT", 180, 1, 600), 1, 600),
        "enabled": 1 if base_url else 0,
        "is_current": 1 if base_url else 0,
    }


class ModelConfigMapperImpl(ModelConfigMapper):
    """模型配置数据访问实现"""

    def __init__(self, db_manager: MySQLDBManager):
        self.db_manager = db_manager

    def is_admin_user(self, user_id: int) -> bool:
        """判断用户是否为系统管理员。"""
        result = self.get_admin_info(user_id)
        return result['is_admin']

    def get_admin_info(self, user_id: int) -> dict:
        """
        获取管理员信息。
        管理员标准：用户 roleId 为 R001。
        非管理员用户自动解析所有管理员的 userId 列表，以便获取全部管理员创建的模型配置。
        """
        session = self._get_session()
        try:
            current_user = session.execute(
                text("""
                    SELECT userId, roleId
                    FROM user_info
                    WHERE userId = :user_id
                    LIMIT 1
                """),
                {"user_id": user_id},
            ).fetchone()

            is_admin = False
            admin_user_id = None
            admin_user_ids = []
            if current_user:
                current_role_id = str(current_user[1] or "")
                if current_role_id == ADMIN_ROLE_ID:
                    is_admin = True
                    admin_user_id = int(current_user[0])
                    logger.info(f"管理员验证通过: userId={admin_user_id}, roleId={current_role_id}")

            # 查询所有 R001 管理员用户，全员共享同一套模型配置
            admin_rows = session.execute(
                text("""
                    SELECT userId FROM user_info
                    WHERE roleId = :admin_role
                """),
                {"admin_role": ADMIN_ROLE_ID},
            ).fetchall()
            admin_user_ids = [int(r[0]) for r in admin_rows]
            if admin_user_ids:
                admin_user_id = admin_user_id or admin_user_ids[0]
                logger.info(f"{'管理员' if is_admin else '非管理员用户 ' + str(user_id)}，使用所有管理员配置 admin_ids={admin_user_ids}")

            return {
                'is_admin': is_admin,
                'admin_user_id': admin_user_id,
                'admin_user_ids': admin_user_ids,
                'admin_reason': 'admin_role' if is_admin else 'resolved_admin'
            }
        except Exception as e:
            logger.error(f"查询管理员失败: {e}")
            return {'is_admin': False, 'admin_user_id': None, 'admin_user_ids': [], 'admin_reason': None}
        finally:
            session.close()
    
    def _get_session(self) -> Session:
        """获取数据库会话"""
        session = self.db_manager.get_session()
        # 验证 session 是否有效
        try:
            if session.get_bind() is None:
                # 如果 session 没有绑定，重新获取
                session.close()
                session = self.db_manager.get_session()
        except Exception as e:
            logger.warning(f"Session 验证失败，重新创建: {e}")
            session.close()
            session = self.db_manager.get_session()
        return session

    def _resolve_owner_user_id(self, user_id: int) -> int:
        admin_info = self.get_admin_info(user_id)
        return int(admin_info.get("admin_user_id") or user_id or 0)

    def _default_embedding_config(self, user_id: int, mask_key: bool = False) -> Dict[str, Any]:
        config = DEFAULT_EMBEDDING_CONFIG.copy()
        config.update(_resolved_default_embedding_config())
        config["user_id"] = self._resolve_owner_user_id(user_id)
        if mask_key and config.get("api_key"):
            config["api_key"] = "***已配置***"
        config["is_builtin_default"] = True
        return config

    def _normalize_embedding_row(self, row_dict: Dict[str, Any], mask_key: bool = True) -> Dict[str, Any]:
        config = dict(row_dict)
        if config.get("api_key"):
            if mask_key:
                config["api_key"] = "***已配置***"
            else:
                try:
                    # EncryptionUtils 是类，需要使用实例方法
                    encryption = EncryptionUtils()
                    config["api_key"] = encryption.decrypt(config["api_key"])
                except Exception as exc:
                    logger.warning(f"解密 embedding API key 失败: {exc}")
                    # 如果解密失败，尝试直接使用（可能是未加密的）
                    # config["api_key"] 保持原值
        else:
            config["api_key"] = None
        config["send_dimensions"] = bool(config.get("send_dimensions"))
        config["is_builtin_default"] = False
        return config

    def get_embedding_model_configs_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """获取当前可用的 Embedding 配置列表（非管理员返回所有 R001 管理员的配置）。"""
        admin_info = self.get_admin_info(user_id)
        admin_ids = admin_info.get('admin_user_ids', []) or [user_id]
        session = self._get_session()
        try:
            placeholders = ','.join([f':admin_id_{i}' for i in range(len(admin_ids))])
            params = {f'admin_id_{i}': admin_ids[i] for i in range(len(admin_ids))}
            result = session.execute(
                text(f"""
                    SELECT id, user_id, config_name, provider_type, base_url, api_key,
                           model_name, dimension, batch_size, timeout_seconds,
                           send_dimensions, is_current, enabled, last_test_status,
                           last_test_message, last_test_time, created_at, updated_at
                    FROM rag_embedding_configs
                    WHERE user_id IN ({placeholders})
                    ORDER BY is_current DESC, updated_at DESC
                """),
                params,
            )
            configs = [self._normalize_embedding_row(dict(zip(result.keys(), row)), mask_key=True) for row in result.fetchall()]
            return configs or [self._default_embedding_config(user_id, mask_key=True)]
        finally:
            session.close()

    def get_embedding_model_config(self, config_id: int, user_id: int = 0) -> Optional[Dict[str, Any]]:
        """根据 ID 获取 Embedding 配置。"""
        if int(config_id or 0) == 0:
            return self._default_embedding_config(user_id or 1, mask_key=False)
        session = self._get_session()
        try:
            result = session.execute(
                text("""
                    SELECT id, user_id, config_name, provider_type, base_url, api_key,
                           model_name, dimension, batch_size, timeout_seconds,
                           send_dimensions, is_current, enabled, last_test_status,
                           last_test_message, last_test_time, created_at, updated_at
                    FROM rag_embedding_configs
                    WHERE id = :config_id
                    LIMIT 1
                """),
                {"config_id": config_id},
            )
            row = result.fetchone()
            if not row:
                return None
            return self._normalize_embedding_row(dict(zip(result.keys(), row)), mask_key=False)
        finally:
            session.close()

    def get_active_embedding_model_config(self, user_id: int) -> Dict[str, Any]:
        """获取当前激活的 Embedding 配置；非管理员在所有 R001 管理员的配置中查找激活项。"""
        admin_info = self.get_admin_info(user_id)
        admin_ids = admin_info.get('admin_user_ids', []) or [user_id]
        session = self._get_session()
        try:
            placeholders = ','.join([f':admin_id_{i}' for i in range(len(admin_ids))])
            params = {f'admin_id_{i}': admin_ids[i] for i in range(len(admin_ids))}
            result = session.execute(
                text(f"""
                    SELECT id, user_id, config_name, provider_type, base_url, api_key,
                           model_name, dimension, batch_size, timeout_seconds,
                           send_dimensions, is_current, enabled, last_test_status,
                           last_test_message, last_test_time, created_at, updated_at
                    FROM rag_embedding_configs
                    WHERE user_id IN ({placeholders}) AND enabled = 1 AND is_current = 1
                    LIMIT 1
                """),
                params,
            )
            row = result.fetchone()
            if not row:
                return self._default_embedding_config(user_id, mask_key=False)
            return self._normalize_embedding_row(dict(zip(result.keys(), row)), mask_key=False)
        finally:
            session.close()

    def insert_embedding_model_config(
        self,
        user_id: int,
        config_name: str,
        provider_type: str,
        base_url: str,
        api_key: Optional[str],
        model_name: str,
        dimension: int = 1024,
        batch_size: Optional[int] = 8,
        timeout_seconds: Optional[int] = 180,
        send_dimensions: bool = False,
        enabled: bool = True,
    ) -> int:
        """新增 Embedding 配置，并设为当前配置（带 MySQL advisory lock 防并发）。"""
        if not self.is_admin_user(user_id):
            raise ValueError("只有系统管理员可以创建 Embedding 配置")
        actual_user_id = self._resolve_owner_user_id(user_id)
        encrypted_key = EncryptionUtils.encrypt_optional(api_key or "local")
        session = self._get_session()
        lock_name = 'rag_embedding_set_active'
        try:
            # 获取互斥锁，超时5秒
            lock_result = session.execute(
                text("SELECT GET_LOCK(:lock_name, 5)"), {"lock_name": lock_name}
            ).fetchone()[0]
            if not lock_result:
                raise Exception("操作超时，另一管理员正在修改 Embedding 配置，请稍后重试")

            # 全局：先将所有 Embedding 配置的 is_current 设置为 0
            session.execute(text("UPDATE rag_embedding_configs SET is_current = 0"))
            result = session.execute(
                text("""
                    INSERT INTO rag_embedding_configs
                      (user_id, config_name, provider_type, base_url, api_key, model_name,
                       dimension, batch_size, timeout_seconds, send_dimensions, is_current, enabled)
                    VALUES
                      (:user_id, :config_name, :provider_type, :base_url, :api_key, :model_name,
                       :dimension, :batch_size, :timeout_seconds, :send_dimensions, 1, :enabled)
                """),
                {
                    "user_id": actual_user_id,
                    "config_name": config_name or model_name,
                    "provider_type": provider_type or "OPENAI_COMPATIBLE",
                    "base_url": base_url,
                    "api_key": encrypted_key,
                    "model_name": model_name,
                    "dimension": int(dimension or 1024),
                    "batch_size": int(batch_size or 8),
                    "timeout_seconds": int(timeout_seconds or 180),
                    "send_dimensions": 1 if send_dimensions else 0,
                    "enabled": 1 if enabled else 0,
                },
            )
            session.commit()
            return int(result.lastrowid)
        except Exception:
            session.rollback()
            raise
        finally:
            session.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})
            session.close()

    def update_embedding_model_config(self, config_id: int, user_id: int, **kwargs) -> bool:
        """更新 Embedding 配置。"""
        if int(config_id or 0) == 0:
            raise ValueError("默认 Embedding 配置不能直接修改，请保存为新配置")
        if not self.is_admin_user(user_id):
            raise ValueError("只有系统管理员可以更新 Embedding 配置")
        valid_fields = {
            "config_name", "provider_type", "base_url", "api_key", "model_name",
            "dimension", "batch_size", "timeout_seconds", "send_dimensions", "enabled",
            "last_test_status", "last_test_message", "last_test_time",
        }
        update_fields = []
        params = {"config_id": config_id}
        for field, value in kwargs.items():
            if field not in valid_fields or value is None:
                continue
            if field == "api_key":
                params[field] = EncryptionUtils.encrypt_optional(value or "local")
            elif field in {"send_dimensions", "enabled"}:
                params[field] = 1 if value else 0
            else:
                params[field] = value
            update_fields.append(f"{field} = :{field}")
        if not update_fields:
            return False
        update_fields.append("updated_at = NOW()")
        session = self._get_session()
        try:
            result = session.execute(
                text(f"UPDATE rag_embedding_configs SET {', '.join(update_fields)} WHERE id = :config_id"),
                params,
            )
            session.commit()
            return result.rowcount > 0
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def set_active_embedding_model_config(self, user_id: int, config_id: int) -> bool:
        """设置当前 Embedding 配置（全局唯一，重置所有 is_current，带 MySQL advisory lock 防并发）。"""
        if int(config_id or 0) == 0:
            return True
        session = self._get_session()
        lock_name = 'rag_embedding_set_active'
        try:
            # 获取互斥锁，超时5秒
            lock_result = session.execute(
                text("SELECT GET_LOCK(:lock_name, 5)"), {"lock_name": lock_name}
            ).fetchone()[0]
            if not lock_result:
                raise Exception("操作超时，另一管理员正在修改 Embedding 配置，请稍后重试")

            # 全局：先将所有 Embedding 配置的 is_current 设置为 0
            session.execute(text("UPDATE rag_embedding_configs SET is_current = 0"))
            result = session.execute(
                text("""
                    UPDATE rag_embedding_configs
                    SET is_current = 1, updated_at = NOW()
                    WHERE id = :config_id AND enabled = 1
                """),
                {"config_id": config_id},
            )
            session.commit()
            return result.rowcount > 0
        except Exception:
            session.rollback()
            raise
        finally:
            session.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})
            session.close()

    def delete_embedding_model_config(self, config_id: int, user_id: int) -> bool:
        """删除 Embedding 配置。"""
        if int(config_id or 0) == 0:
            raise ValueError("默认 Embedding 配置不能删除")
        if not self.is_admin_user(user_id):
            raise ValueError("只有系统管理员可以删除 Embedding 配置")
        session = self._get_session()
        try:
            result = session.execute(
                text("DELETE FROM rag_embedding_configs WHERE id = :config_id"),
                {"config_id": config_id},
            )
            session.commit()
            return result.rowcount > 0
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def insert_model_config(
        self,
        user_id: int,
        model_type: int,
        config_type: str,
        api_key: Optional[str] = None,  # API Key可以为空（Ollama和LOCAL类型）
        api_url: Optional[str] = None,
        ip_address: Optional[str] = None,
        port: Optional[int] = None,
        model_name: str = "",
        model_path: Optional[str] = None
    ) -> int:
        """
        插入模型配置（自动加密API key，并设为激活配置）
        注意：只有系统管理员可以创建模型配置，使用 MySQL advisory lock 防并发
        """
        session = self._get_session()
        lock_name = 'model_config_set_active'
        try:
            # 检查是否为管理员
            if not self.is_admin_user(user_id):
                raise ValueError("只有系统管理员可以创建模型配置")

            # URL类型必须提供API Key
            if config_type.upper() == 'URL':
                if not api_key or api_key.strip() == "":
                    raise ValueError("URL类型的模型配置必须提供API Key")

            # 加密API key（Ollama和LOCAL类型可以为空）
            encrypted_key = EncryptionUtils.encrypt_optional(api_key)

            # 获取互斥锁，超时5秒
            lock_result = session.execute(
                text("SELECT GET_LOCK(:lock_name, 5)"), {"lock_name": lock_name}
            ).fetchone()[0]
            if not lock_result:
                raise Exception("操作超时，另一管理员正在修改模型配置，请稍后重试")

            # 全局：先将所有模型配置的 is_current 设置为 0（系统全局只允许一个激活配置）
            session.execute(text("UPDATE model_configs SET is_current = 0"))

            # 插入新配置，is_current 设置为 1
            query = text("""
                INSERT INTO model_configs
                (user_id, model_type, config_type, api_url, api_key, ip_address, port, model_name, model_path, is_current)
                VALUES (:user_id, :model_type, :config_type, :api_url, :api_key, :ip_address, :port, :model_name, :model_path, 1)
            """)
            result = session.execute(query, {
                'user_id': user_id,
                'model_type': model_type,
                'config_type': config_type,
                'api_url': api_url,
                'api_key': encrypted_key,
                'ip_address': ip_address,
                'port': port,
                'model_name': model_name,
                'model_path': model_path
            })
            session.commit()
            logger.info(f"模型配置已保存并激活（已加密） - user_id: {user_id}, model: {model_name}")
            return result.lastrowid
        except Exception as e:
            session.rollback()
            logger.error(f"保存模型配置失败: {e}")
            raise e
        finally:
            session.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})
            session.close()
    
    def get_model_configs_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """
        获取用户的所有模型配置（列表查询不解密API key，只返回是否已配置）
        非管理员返回所有 R001 管理员的模型配置
        """
        admin_info = self.get_admin_info(user_id)
        admin_ids = admin_info.get('admin_user_ids', []) or [user_id]

        logger.info(f"获取模型配置列表 - user_id: {user_id}, admin_ids: {admin_ids}")

        session = self._get_session()
        try:
            # 构建 IN 子句的占位符
            placeholders = ','.join([f':admin_id_{i}' for i in range(len(admin_ids))])
            params = {f'admin_id_{i}': admin_ids[i] for i in range(len(admin_ids))}

            query = text(f"""
                SELECT id, user_id, model_type, config_type, api_url, api_key,
                       ip_address, port, model_name, model_path, is_current, created_at, updated_at
                FROM model_configs
                WHERE user_id IN ({placeholders})
                ORDER BY is_current DESC, updated_at DESC
            """)
            result = session.execute(query, params)
            columns = result.keys()
            configs = []
            for row in result.fetchall():
                config_dict = dict(zip(columns, row))
                # 列表查询不解密API key，只返回是否已配置的标记
                if config_dict.get('api_key'):
                    config_dict['api_key'] = '***已配置***'
                configs.append(config_dict)
            return configs
        finally:
            session.close()
    
    def get_model_config(self, config_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取模型配置（自动解密API key）"""
        session = self._get_session()
        try:
            query = text("""
                SELECT id, user_id, model_type, config_type, api_url, api_key,
                       ip_address, port, model_name, model_path, created_at, updated_at
                FROM model_configs
                WHERE id = :config_id
            """)
            result = session.execute(query, {'config_id': config_id})
            row = result.fetchone()
            if row:
                columns = result.keys()
                config_dict = dict(zip(columns, row))
                # 解密API key
                if config_dict.get('api_key'):
                    try:
                        config_dict['api_key'] = EncryptionUtils.decrypt(config_dict['api_key'])
                    except Exception as e:
                        logger.warning(f"解密API key失败: {e}")
                        config_dict['api_key'] = None
                return config_dict
            return None
        finally:
            session.close()
    
    def get_active_model_config(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        获取用户激活的模型配置（is_current=1，已解密）
        非管理员用户在所有 R001 管理员的配置中查找激活项
        """
        admin_info = self.get_admin_info(user_id)
        is_admin = admin_info['is_admin']
        admin_ids = admin_info.get('admin_user_ids', []) or [user_id]

        logger.info(f"获取激活模型配置 - user_id: {user_id}, is_admin: {is_admin}, admin_ids: {admin_ids}")

        session = self._get_session()
        try:
            placeholders = ','.join([f':admin_id_{i}' for i in range(len(admin_ids))])
            params = {f'admin_id_{i}': admin_ids[i] for i in range(len(admin_ids))}

            query = text(f"""
                SELECT id, user_id, model_type, config_type, api_url, api_key,
                       ip_address, port, model_name, model_path, is_current, created_at, updated_at
                FROM model_configs
                WHERE user_id IN ({placeholders}) AND is_current = 1
                LIMIT 1
            """)
            result = session.execute(query, params)
            row = result.fetchone()
            if row:
                columns = result.keys()
                config_dict = dict(zip(columns, row))
                # 解密API key
                if config_dict.get('api_key'):
                    try:
                        config_dict['api_key'] = EncryptionUtils.decrypt(config_dict['api_key'])
                    except Exception as e:
                        logger.warning(f"解密API key失败: {e}")
                        config_dict['api_key'] = None
                logger.info(f"获取到激活模型配置 - model: {config_dict.get('model_name')}")
                return config_dict
            logger.warning(f"未找到激活模型配置")
            return None
        finally:
            session.close()
    
    def update_model_config(
        self,
        config_id: int,
        admin_user_id: int = 0,
        **kwargs
    ) -> bool:
        """
        更新模型配置（自动加密API key）
        只有系统管理员可以更新模型配置（需传入 admin_user_id 做校验）
        """
        if not admin_user_id or not self.is_admin_user(admin_user_id):
            raise ValueError("只有系统管理员可以更新模型配置")
        session = self._get_session()
        try:
            # 获取当前配置信息
            current_query = text("""
                SELECT config_type, user_id FROM model_configs WHERE id = :config_id
            """)
            current_result = session.execute(current_query, {'config_id': config_id})
            current_row = current_result.fetchone()
            if not current_row:
                raise ValueError("模型配置不存在")

            config_type = current_row[0]
            owner_user_id = current_row[1]

            # 检查是否为管理员
            # 注意：这里我们假设任何能更新配置的人都是管理员
            # 或者可以通过传入user_id参数来验证

            # 构建动态更新语句
            update_fields = []
            params = {'config_id': config_id}

            valid_fields = ['model_type', 'config_type', 'api_url', 'api_key',
                          'ip_address', 'port', 'model_name', 'model_path']

            for field in valid_fields:
                if field in kwargs and kwargs[field] is not None:
                    # 如果是api_key字段，需要加密
                    if field == 'api_key':
                        # URL类型必须提供API Key
                        if config_type and config_type.upper() == 'URL':
                            if not kwargs[field] or kwargs[field].strip() == "":
                                raise ValueError("URL类型的模型配置必须提供API Key")
                        # 加密API key
                        params[field] = EncryptionUtils.encrypt_optional(kwargs[field])
                    else:
                        params[field] = kwargs[field]
                    update_fields.append(f"{field} = :{field}")

            if not update_fields:
                return False

            # 添加更新时间
            update_fields.append("updated_at = NOW()")

            query = text(f"""
                UPDATE model_configs
                SET {', '.join(update_fields)}
                WHERE id = :config_id
            """)
            result = session.execute(query, params)
            session.commit()
            logger.info(f"模型配置已更新 - config_id: {config_id}")
            return result.rowcount > 0
        except Exception as e:
            session.rollback()
            logger.error(f"更新模型配置失败: {e}")
            raise e
        finally:
            session.close()

    def set_active_model_config(self, user_id: int, config_id: int) -> bool:
        """
        设置全局唯一的激活模型配置（带 MySQL advisory lock 防并发）
        系统全局只允许一个 is_current=1 的配置，切换时重置所有配置
        """
        session = self._get_session()
        lock_name = 'model_config_set_active'
        try:
            # 获取互斥锁，超时5秒
            lock_result = session.execute(
                text("SELECT GET_LOCK(:lock_name, 5)"), {"lock_name": lock_name}
            ).fetchone()[0]
            if not lock_result:
                raise Exception("操作超时，另一管理员正在修改模型配置，请稍后重试")

            # 全局：先将所有模型配置的 is_current 设置为 0
            session.execute(text("UPDATE model_configs SET is_current = 0"))

            # 然后将指定配置的 is_current 设置为 1
            result = session.execute(
                text("UPDATE model_configs SET is_current = 1, updated_at = NOW() WHERE id = :config_id"),
                {'config_id': config_id},
            )
            session.commit()

            if result.rowcount > 0:
                logger.info(f"激活模型配置 - user_id: {user_id}, config_id: {config_id}")
                return True
            else:
                logger.warning(f"激活模型配置失败 - user_id: {user_id}, config_id: {config_id}")
                return False
        except Exception as e:
            session.rollback()
            logger.error(f"激活模型配置失败: {e}")
            raise e
        finally:
            session.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})
            session.close()

    def delete_model_config(self, config_id: int, admin_user_id: int = 0) -> bool:
        """删除模型配置。只有系统管理员可以删除。"""
        if not admin_user_id or not self.is_admin_user(admin_user_id):
            raise ValueError("只有系统管理员可以删除模型配置")
        session = self._get_session()
        try:
            query = text("""
                DELETE FROM model_configs
                WHERE id = :config_id
            """)
            result = session.execute(query, {'config_id': config_id})
            session.commit()
            return result.rowcount > 0
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
