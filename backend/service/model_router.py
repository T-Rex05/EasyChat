"""模型路由器 — 场景路由 + 降级链引擎

核心职责：
1. 场景路由：根据 scene 参数匹配不同模型（如 code→Claude, summary→GPT-4o-mini）
2. 降级链：主模型不可用时，按配置顺序自动切换备用模型
3. 熔断集成：复用现有 ModelGateway 的熔断器，跳过已熔断的配置

调用方：agent_controller.get_current_model_config()、chat/stream.py

设计原则：
- 不引入新依赖，复用现有 ModelGateway (CircuitBreaker)
- 配置存储在 model_route_settings 表（JSON KV）
- 选模型优先级：用户手动指定 > 场景路由 > is_current > 降级链 > fail-open
- Redis 缓存：模型配置缓存 5 分钟，减少数据库查询
"""
import json
from typing import Any, Dict, List, Optional

from backend.utils.log_utils import log
from backend.utils.crypto_utils import decrypt
from backend.service.scene_registry import scenes
from backend.infrastructure import get_cache, get_key_builder

logger = log


class ModelRouter:
    """模型路由器：根据场景、降级链、熔断状态选择最优模型配置。"""

    def __init__(self):
        self._gateway = None  # 延迟初始化，避免循环导入
        self._route_mapper = None

    @property
    def gateway(self):
        if self._gateway is None:
            from backend.service.llm_gateway import gateway
            self._gateway = gateway
        return self._gateway

    @property
    def route_mapper(self):
        if self._route_mapper is None:
            from backend.db.model_route_mapper import route_mapper
            self._route_mapper = route_mapper
        return self._route_mapper

    def select_model(
        self,
        category: str = "chat",
        scene: str = "",
        model_id: int = None,
        user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """选择模型配置。

        优先级：
        1. 用户手动指定 model_id → 直接用（跳过路由逻辑）
        2. 场景路由：scene 非空 && 有匹配 → 使用该模型
        3. 默认 is_current：经熔断器检查
        4. 降级链：按配置顺序逐个尝试
        5. fail-open：全部熔断时返回 is_current（避免彻底断流）

        Args:
            category: 配置分类（chat/embedding/rerank）
            scene: 场景标识（code/summary/chat 等）
            model_id: 用户手动指定的 model_config ID

        Returns:
            模型配置字典（已解密 api_key），或 None（完全无配置）
        """
        category = (category or "chat").strip().lower()

        # ── 1. 用户手动指定 ──
        if model_id:
            config = self._get_config_by_id(model_id)
            if config:
                self._decrypt_config(config)
                logger.info(f"[ModelRouter] 用户手动指定模型: id={model_id}, model={config.get('model_name')}")
                return config

        # ── 2. 场景路由 ──
        if scene:
            scene_routing = self.route_mapper.get_scene_routing()
            scene_config_id = scene_routing.get(scene)
            if scene_config_id:
                config = self._get_config_by_id(scene_config_id)
                if config and self.gateway.report_is_available(config.get("model_name", "")):
                    self._decrypt_config(config)
                    scene_def = scenes.get(scene)
                    scene_label = f"{scene}({scene_def.name})" if scene_def else scene
                    logger.info(f"[ModelRouter] 场景路由命中: scene={scene_label} → model={config.get('model_name')}")
                    return config
                elif config:
                    scene_def = scenes.get(scene)
                    scene_label = f"{scene}({scene_def.name})" if scene_def else scene
                    logger.info(f"[ModelRouter] 场景路由模型已熔断: scene={scene_label}, model={config.get('model_name')}，继续降级")

        # ── 3. 默认 is_current（经熔断器选择）──
        configs = self._get_configs_by_category(category, user_id)
        if configs:
            selected = self.gateway.select_config(configs)
            if selected:
                self._decrypt_config(selected)
                logger.info(
                    f"[ModelRouter] 默认模型: model={selected.get('model_name')}, "
                    f"config={selected.get('config_name')}, category={category}"
                )
                return selected

        # ── 4. 降级链 ──
        fallback_ids = self.route_mapper.get_fallback_chain()
        for fid in fallback_ids:
            config = self._get_config_by_id(fid)
            if config and self.gateway.report_is_available(config.get("model_name", "")):
                self._decrypt_config(config)
                logger.info(f"[ModelRouter] 降级链命中: id={fid}, model={config.get('model_name')}")
                return config

        # ── 5. fail-open ──
        if configs:
            config = configs[0]
            self._decrypt_config(config)
            logger.warning(f"[ModelRouter] fail-open: 全部熔断，强制使用 is_current 配置")
            return config

        return None

    def get_fallback_chain_configs(self, category: str = "chat", mask_keys: bool = True) -> List[Dict[str, Any]]:
        """获取降级链中的完整模型配置列表。

        Args:
            category: 配置分类（仅用于签名兼容，当前未使用）
            mask_keys: 是否脱敏 api_key。前端展示=True，内部传递给 Hermes=False
        """
        fallback_ids = self.route_mapper.get_fallback_chain()
        configs = []
        for fid in fallback_ids:
            config = self._get_config_by_id(fid)
            if config:
                if mask_keys:
                    # 脱敏 api_key（供前端展示）
                    if config.get("api_key"):
                        config["api_key"] = "***已配置***"
                else:
                    # 解密 api_key（供 Hermes AIAgent 使用）
                    self._decrypt_config(config)
                # 附加熔断状态
                config["circuit_state"] = self.gateway.breaker_state(config.get("model_name", ""))
                configs.append(config)
        return configs

    def evaluate_route(self, category: str = "chat", scene: str = "") -> Dict[str, Any]:
        """预览当前路由规则会选中哪个模型（供前端调试）。"""
        result = {
            "scene": scene,
            "category": category,
            "selected_model": None,
            "route_path": "",
            "fallback_chain": [],
        }

        # 获取降级链信息
        fallback_ids = self.route_mapper.get_fallback_chain()
        result["fallback_chain"] = fallback_ids

        # 获取场景路由信息
        scene_routing = self.route_mapper.get_scene_routing()
        result["scene_routing"] = scene_routing

        # 模拟选模型
        if scene and scene_routing.get(scene):
            config = self._get_config_by_id(scene_routing[scene])
            if config:
                result["selected_model"] = {
                    "id": config.get("id"),
                    "model_name": config.get("model_name"),
                    "config_name": config.get("config_name"),
                }
                result["route_path"] = f"scene({scene}) → model#{scene_routing[scene]}"
                return result

        configs = self._get_configs_by_category(category)
        if configs:
            selected = self.gateway.select_config(configs)
            if selected:
                result["selected_model"] = {
                    "id": selected.get("id"),
                    "model_name": selected.get("model_name"),
                    "config_name": selected.get("config_name"),
                }
                result["route_path"] = "is_current → selected"
                return result

        # 降级链
        for fid in fallback_ids:
            config = self._get_config_by_id(fid)
            if config and self.gateway.report_is_available(config.get("model_name", "")):
                result["selected_model"] = {
                    "id": config.get("id"),
                    "model_name": config.get("model_name"),
                    "config_name": config.get("config_name"),
                }
                result["route_path"] = f"fallback_chain → model#{fid}"
                return result

        result["route_path"] = "no_config"
        return result

    # ── 内部方法 ──

    def _get_configs_by_category(self, category: str, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """从数据库获取某分类的全部启用配置（带 Redis 缓存）。

        Args:
            category: 配置分类
            user_id: 用户ID（用于租户隔离，返回用户自己的配置或系统默认配置 user_id=1）
        """
        cache = get_cache()
        kb = get_key_builder()
        # 缓存键包含 user_id 维度，实现租户隔离
        cache_key = kb.model_configs_by_category(f"{category}:{user_id or 0}")

        # 尝试从缓存获取
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # 缓存 miss，查询数据库
        try:
            from backend.db.connection_pool import get_pool_connection
            conn = get_pool_connection()
            try:
                cur = conn.cursor()
                # 租户隔离：返回用户自己的配置或系统默认配置（user_id=1）
                if user_id is not None and user_id != 1:
                    cur.execute(
                        "SELECT id, config_name, config_type, api_url, api_key, model_name, "
                        "provider, category, is_current, enabled "
                        "FROM model_configs WHERE category = %s AND enabled = 1 "
                        "AND (user_id = %s OR user_id = 1) "
                        "ORDER BY is_current DESC, id ASC",
                        (category, user_id),
                    )
                else:
                    # user_id 为空或为 1 时，只返回**系统默认配置**（user_id = 1）。
                    # ⚠️ 必须带 user_id = 1：否则会返回"全局第一条激活配置"，
                    # 而那条可能属于**别的用户** → 拿他人凭证发请求（跨租户凭证泄漏）。
                    cur.execute(
                        "SELECT id, config_name, config_type, api_url, api_key, model_name, "
                        "provider, category, is_current, enabled "
                        "FROM model_configs WHERE category = %s AND enabled = 1 "
                        "AND user_id = 1 "
                        "ORDER BY is_current DESC, id ASC",
                        (category,),
                    )
                rows = cur.fetchall()
                configs = [
                    {
                        "id": r.get("id"),
                        "config_name": r.get("config_name") or "",
                        "config_type": (r.get("config_type") or "URL").upper(),
                        "api_url": r.get("api_url") or "",
                        "api_key": r.get("api_key") or "",
                        "model_name": r.get("model_name") or "",
                        "provider": r.get("provider") or "",
                        "category": category,
                        "is_current": int(r.get("is_current") or 0),
                    }
                    for r in rows
                ]

                # 写入缓存（5 分钟 TTL）
                cache.set_with_jitter(cache_key, configs, base_ttl=300, jitter_range=30)

                return configs
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"[ModelRouter] 查询配置失败: {e}")
            return []

    def _get_config_by_id(self, config_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 获取单条配置（带 Redis 缓存）。"""
        if not config_id:
            return None

        cache = get_cache()
        kb = get_key_builder()
        cache_key = kb.model_config(config_id)
        empty_key = kb.build("model", "config", config_id, "empty")

        # 检查空值标记
        if cache.get(empty_key) is not None:
            return None

        # 尝试从缓存获取
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # 缓存 miss，查询数据库
        try:
            from backend.db.connection_pool import get_pool_connection
            conn = get_pool_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, config_name, config_type, api_url, api_key, model_name, "
                    "provider, category, is_current, enabled "
                    "FROM model_configs WHERE id = %s AND enabled = 1",
                    (config_id,),
                )
                r = cur.fetchone()
                if not r:
                    # 缓存空结果（避免重复查库，TTL 较短）
                    cache.set_with_jitter(empty_key, True, base_ttl=60, jitter_range=10)
                    return None

                config = {
                    "id": r.get("id"),
                    "config_name": r.get("config_name") or "",
                    "config_type": (r.get("config_type") or "URL").upper(),
                    "api_url": r.get("api_url") or "",
                    "api_key": r.get("api_key") or "",
                    "model_name": r.get("model_name") or "",
                    "provider": r.get("provider") or "",
                    "category": r.get("category") or "chat",
                    "is_current": int(r.get("is_current") or 0),
                }

                # 写入缓存（5 分钟 TTL）
                cache.set_with_jitter(cache_key, config, base_ttl=300, jitter_range=30)

                return config
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"[ModelRouter] 查询配置 id={config_id} 失败: {e}")
            return None

    def _decrypt_config(self, config: Dict[str, Any]) -> None:
        """原地解密 api_key。"""
        api_key = config.get("api_key") or ""
        if api_key:
            try:
                config["api_key"] = decrypt(api_key)
            except Exception:
                pass  # 明文兼容
        config["config_id"] = config.get("id")


def invalidate_model_config_cache(config_id: int = None, category: str = None):
    """主动失效模型配置缓存（配置变更时调用）。

    Args:
        config_id: 指定配置 ID（可选）
        category: 指定分类（可选）
    """
    cache = get_cache()
    kb = get_key_builder()

    if config_id:
        cache.delete(kb.model_config(config_id))
        cache.delete(kb.build("model", "config", config_id, "empty"))

    if category:
        # 按前缀删除该分类下所有用户的缓存（key 形如 agentforge:model:configs:chat:1）
        cache.delete_pattern(kb.model_configs_by_category(category) + ":*")
    else:
        # 删除所有分类缓存 + 单条配置缓存 + 空值标记
        cache.delete_pattern(kb.pattern("model", "configs"))
        cache.delete_pattern(kb.pattern("model", "config"))

    # 同时失效场景路由和降级链缓存
    cache.delete(kb.build("model", "scene_routing"))
    cache.delete(kb.build("model", "fallback_chain"))

    logger.info(f"[ModelRouter] 缓存失效: config_id={config_id}, category={category}")


# 模块级单例
router = ModelRouter()
