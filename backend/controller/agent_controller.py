"""
AgentForge 模型配置读取器
"""
import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

from backend.utils.log_utils import log

logger = log


def get_current_model_config(user_id: int, category: str = "chat", scene: str = "", model_id: int = None) -> Optional[Dict[str, Any]]:
    """
    获取用户的 LLM 模型配置。

    选模型优先级：
    1. 用户手动指定 model_id → 直接用
    2. 场景路由（scene 非空且有配置）→ 使用对应模型
    3. 数据库 is_current 配置（经 ModelGateway 熔断器检查）
    4. 降级链（model_route_settings 中配置的备用模型序列）
    5. 环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL

    Args:
        user_id: 用户 ID
        category: 配置分类 chat（聊天模型，默认）| embedding（Embedding 模型）等
        scene: 场景标识（code/summary 等），用于场景路由
        model_id: 用户手动指定的 model_config ID

    返回:
        模型配置字典，格式与 HermesRuntime 期望一致
        如果完全无配置则返回 None
    """
    category = (category or "chat").strip().lower()

    # ── 最高优先级：通过 ModelRouter 选择（场景路由 + 熔断 + 降级链）──
    try:
        from backend.service.model_router import router as _model_router
        chosen = _model_router.select_model(category=category, scene=scene, model_id=model_id, user_id=user_id)
        if chosen:
            return chosen
    except Exception as e:
        logger.debug(f"[get_current_model_config] ModelRouter 不可用，回退到直连: {e}")

    # 尝试从数据库获取（生产环境）
    try:
        from backend.utils.mysql_db_manager import MySQLDBManager
        from backend.db.model_config_mapper_impl import ModelConfigMapperImpl

        db_mgr = MySQLDBManager()
        mapper = ModelConfigMapperImpl(db_mgr)
        config = mapper.get_active_model_config(user_id)
        if config:
            logger.debug(f"从数据库获取到用户 {user_id} 的模型配置")
            return config
    except Exception:
        pass  # DB 不可用（模块缺失/连接失败/表不存在），回退到环境变量

    # 回退：先查数据库 user_configs，再查环境变量
    try:
        from backend.db.connection_pool import get_pool_connection
        conn = get_pool_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT config_key, config_val FROM user_configs WHERE user_id = %s", (user_id,))
            db_config = {r["config_key"]: r["config_val"] for r in cur.fetchall()}
        finally:
            conn.close()
        if db_config.get("llm_base_url") and db_config.get("llm_api_key"):
            base_url = db_config["llm_base_url"]
            api_key = db_config["llm_api_key"]
            # api_key 解密（如果是加密存储的）
            try:
                from backend.utils.crypto_utils import decrypt
                api_key = decrypt(api_key)
            except Exception:
                pass  # 明文存储的兼容
            model = db_config.get("llm_model", "")
            logger.info(f"从数据库加载模型配置: {model}")
            return {
                "config_type": "URL",
                "api_url": base_url,
                "api_key": api_key,
                "model_name": model,
            }
    except Exception:
        pass

    # 环境变量
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()

    if not base_url or not api_key:
        logger.warning(f"用户 {user_id} 未配置 LLM")
        return None

    return {
        "config_type": "URL",
        "api_url": base_url,
        "api_key": api_key,
        "model_name": model,
    }
