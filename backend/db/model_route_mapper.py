"""模型路由配置数据访问层

管理 model_route_settings 表的读写，提供降级链和场景路由配置的存取接口。
使用与 model_config_controller.py 一致的直连模式（connection_pool）。
"""
import json
from typing import Any, Dict, List, Optional

from backend.utils.log_utils import log

logger = log


def _get_conn():
    from backend.db.connection_pool import get_pool_connection
    return get_pool_connection()


class ModelRouteMapper:
    """模型路由配置的 CRUD 操作。"""

    # ── 降级链 ──

    def get_fallback_chain(self) -> List[int]:
        """获取降级链配置（model_config ID 有序列表）。"""
        raw = self._get_setting("fallback_chain")
        if isinstance(raw, dict):
            return raw.get("model_ids", [])
        if isinstance(raw, list):
            return raw
        return []

    def save_fallback_chain(self, model_ids: List[int]) -> None:
        """保存降级链配置。"""
        self._set_setting("fallback_chain", {"model_ids": model_ids}, "降级链")

    # ── 场景路由 ──

    def get_scene_routing(self) -> Dict[str, int]:
        """获取场景路由配置 {scene_name: model_config_id}。"""
        raw = self._get_setting("scene_routing")
        if isinstance(raw, dict):
            # JSON key 可能存储为字符串，转为 int
            return {str(k): int(v) for k, v in raw.items() if v}
        return {}

    def save_scene_routing(self, routing: Dict[str, int]) -> None:
        """保存场景路由配置。"""
        self._set_setting("scene_routing", routing, "场景路由")

    # ── 通用 KV 操作 ──

    def _get_setting(self, key: str) -> Any:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT setting_value FROM model_route_settings WHERE setting_key = %s",
                (key,),
            )
            row = cur.fetchone()
            if not row:
                return None
            val = row.get("setting_value")
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return val
            return val
        except Exception as e:
            logger.debug(f"[ModelRouteMapper] 读取 {key} 失败（表可能不存在）: {e}")
            return None
        finally:
            conn.close()

    def _set_setting(self, key: str, value: Any, description: str = "") -> None:
        conn = _get_conn()
        try:
            cur = conn.cursor()
            json_val = json.dumps(value, ensure_ascii=False)
            cur.execute(
                "INSERT INTO model_route_settings (setting_key, setting_value, description) "
                "VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE setting_value = %s, description = %s, updated_at = NOW()",
                (key, json_val, description, json_val, description),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"[ModelRouteMapper] 保存 {key} 失败: {e}")
            raise
        finally:
            conn.close()


# 模块级单例
route_mapper = ModelRouteMapper()
