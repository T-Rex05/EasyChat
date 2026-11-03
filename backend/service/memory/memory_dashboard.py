"""
Memory Dashboard Service - 记忆专项监控看板

聚合记忆系统各项运行指标，供前端监控面板展示。

指标：
- memory_counts: 各层记忆数量统计
- consolidation_stats: 合并/去重/淘汰统计
- outbox_health: Outbox 事件队列健康状态
- vector_coverage: 向量化覆盖率
- graph_coverage: 图节点覆盖率（GraphMemory :Memory 节点）
- kg_store_stats: KGStore 知识图谱统计（实体/关系/质量/冲突）
- encryption_stats: 加密覆盖率
- version_stats: 版本历史统计
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from backend.db.memory_mapper import (
    get_episodic_mapper, get_semantic_mapper
)
from backend.db.schema import get_conn

logger = logging.getLogger(__name__)


class MemoryDashboardService:
    """记忆监控看板数据服务"""

    def __init__(self):
        self._episodic = get_episodic_mapper()
        self._semantic = get_semantic_mapper()

    def get_dashboard(self) -> Dict[str, Any]:
        """获取完整看板数据"""
        return {
            "memory_counts": self._get_memory_counts(),
            "consolidation_stats": self._get_consolidation_stats(),
            "outbox_health": self._get_outbox_health(),
            "vector_coverage": self._get_vector_coverage(),
            "graph_coverage": self._get_graph_coverage(),
            "kg_store_stats": self._get_kg_store_stats(),
            "encryption_stats": self._get_encryption_stats(),
            "version_stats": self._get_version_stats(),
            "ttl_expiry": self._get_ttl_expiry(),
        }

    # ========== 各层记忆数量 ==========

    def _get_memory_counts(self) -> dict:
        """统计各层记忆数量"""
        conn = None  # 先绑定：get_conn() 抛异常时 finally 不再 NameError
        try:
            conn = get_conn()

            # Episodic 表
            cur = conn.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN deleted_at IS NULL AND (expires_at IS NULL OR expires_at > NOW()) THEN 1 ELSE 0 END) as active, "
                "SUM(CASE WHEN deleted_at IS NOT NULL THEN 1 ELSE 0 END) as deleted, "
                "SUM(CASE WHEN deleted_at IS NULL AND expires_at IS NOT NULL AND expires_at < NOW() THEN 1 ELSE 0 END) as expired "
                "FROM memory_episodic"
            )
            episodic_row = cur.fetchone()
            episodic = dict(episodic_row) if episodic_row else {}

            # Semantic 表
            cur = conn.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN deleted_at IS NULL THEN 1 ELSE 0 END) as active, "
                "SUM(CASE WHEN deleted_at IS NOT NULL THEN 1 ELSE 0 END) as deleted "
                "FROM memory_semantic"
            )
            semantic_row = cur.fetchone()
            semantic = dict(semantic_row) if semantic_row else {}

            return {
                "episodic": {
                    "total": episodic.get("total", 0) or 0,
                    "active": episodic.get("active", 0) or 0,
                    "expired": episodic.get("expired", 0) or 0,
                    "deleted": episodic.get("deleted", 0) or 0,
                },
                "semantic": {
                    "total": semantic.get("total", 0) or 0,
                    "active": semantic.get("active", 0) or 0,
                    "deleted": semantic.get("deleted", 0) or 0,
                },
                "grand_total": (
                    (episodic.get("active", 0) or 0) +
                    (semantic.get("active", 0) or 0)
                ),
            }
        except Exception as e:
            logger.warning(f"Failed to get memory counts: {e}")
            return {"episodic": {}, "semantic": {}, "grand_total": 0}
        finally:
            if conn is not None:
                conn.close()

    # ========== 合并统计 ==========

    def _get_consolidation_stats(self) -> dict:
        """从 memory_versions 和 memory_consolidation_logs 获取合并统计"""
        conn = None  # 先绑定：get_conn() 抛异常时 finally 不再 NameError
        try:
            conn = get_conn()

            # 版本历史统计（按 change_reason 分组）
            cur = conn.execute(
                """SELECT change_reason, COUNT(*) as cnt
                   FROM memory_versions
                   GROUP BY change_reason"""
            )
            version_counts = {row["change_reason"]: row["cnt"] for row in cur.fetchall()}

            # 总版本数
            cur = conn.execute("SELECT COUNT(*) as cnt FROM memory_versions")
            total_versions = (cur.fetchone() or {}).get("cnt", 0)

            # consolidation_logs 统计（如果表存在）
            consolidation_logs = {}
            try:
                cur = conn.execute(
                    """SELECT consolidation_type, COUNT(*) as cnt
                       FROM memory_consolidation_logs
                       GROUP BY consolidation_type"""
                )
                consolidation_logs = {row["consolidation_type"]: row["cnt"] for row in cur.fetchall()}
            except Exception:
                pass  # 表可能不存在

            return {
                "total_versions": total_versions,
                "by_change_reason": version_counts,
                "by_consolidation_type": consolidation_logs,
            }
        except Exception as e:
            logger.warning(f"Failed to get consolidation stats: {e}")
            return {}
        finally:
            if conn is not None:
                conn.close()

    # ========== Outbox 健康 ==========

    def _get_outbox_health(self) -> dict:
        """Outbox 事件队列状态"""
        conn = None  # 先绑定：get_conn() 抛异常时 finally 不再 NameError
        try:
            conn = get_conn()
            cur = conn.execute(
                """SELECT status, COUNT(*) as cnt
                   FROM memory_outbox
                   GROUP BY status"""
            )
            status_counts = {row["status"]: row["cnt"] for row in cur.fetchall()}

            # 按层统计
            try:
                cur = conn.execute(
                    """SELECT memory_layer, status, COUNT(*) as cnt
                       FROM memory_outbox
                       GROUP BY memory_layer, status"""
                )
                layer_stats = {}
                for row in cur.fetchall():
                    layer = row.get("memory_layer", "legacy")
                    if layer not in layer_stats:
                        layer_stats[layer] = {}
                    layer_stats[layer][row["status"]] = row["cnt"]
            except Exception:
                layer_stats = {}

            return {
                "by_status": status_counts,
                "by_layer": layer_stats,
                "pending": status_counts.get("pending", 0),
                "processing": status_counts.get("processing", 0),
                "processed": status_counts.get("processed", 0),
                "dead": status_counts.get("dead", 0),
                # 向后兼容（旧前端可能还在用 completed/failed）
                "completed": status_counts.get("processed", 0),
                "failed": status_counts.get("dead", 0),
            }
        except Exception as e:
            logger.warning(f"Failed to get outbox health: {e}")
            return {}
        finally:
            if conn is not None:
                conn.close()

    # ========== 向量化覆盖率 ==========

    def _get_vector_coverage(self) -> dict:
        """检查向量化覆盖率（有 embedding_id 的比例）"""
        conn = None  # 先绑定：get_conn() 抛异常时 finally 不再 NameError
        try:
            conn = get_conn()
            stats = {}
            for table_name, mapper_name in [
                ("memory_episodic", "episodic"),
                ("memory_semantic", "semantic"),
            ]:
                try:
                    cur = conn.execute(
                        f"""SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN embedding_id IS NOT NULL AND embedding_id != '' THEN 1 ELSE 0 END) as vectorized
                           FROM {table_name}
                           WHERE deleted_at IS NULL"""
                    )
                    row = dict(cur.fetchone())
                    total = row.get("total", 0) or 0
                    vectorized = row.get("vectorized", 0) or 0
                    stats[mapper_name] = {
                        "total": total,
                        "vectorized": vectorized,
                        "coverage": round(vectorized / total * 100, 1) if total > 0 else 0,
                    }
                except Exception:
                    stats[mapper_name] = {}
            return stats
        except Exception as e:
            logger.warning(f"Failed to get vector coverage: {e}")
            return {}
        finally:
            if conn is not None:
                conn.close()

    # ========== 图覆盖率 ==========

    def _get_graph_coverage(self) -> dict:
        """检查图节点覆盖率"""
        conn = None  # 先绑定：get_conn() 抛异常时 finally 不再 NameError
        try:
            conn = get_conn()
            stats = {}
            # 只有 semantic 有图节点
            for table_name, mapper_name in [
                ("memory_semantic", "semantic"),
            ]:
                try:
                    cur = conn.execute(
                        f"""SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN graph_node_id IS NOT NULL AND graph_node_id != '' THEN 1 ELSE 0 END) as graphed
                           FROM {table_name}
                           WHERE deleted_at IS NULL"""
                    )
                    row = dict(cur.fetchone())
                    total = row.get("total", 0) or 0
                    graphed = row.get("graphed", 0) or 0
                    stats[mapper_name] = {
                        "total": total,
                        "graphed": graphed,
                        "coverage": round(graphed / total * 100, 1) if total > 0 else 0,
                    }
                except Exception:
                    stats[mapper_name] = {}
            return stats
        except Exception as e:
            logger.warning(f"Failed to get graph coverage: {e}")
            return {}
        finally:
            if conn is not None:
                conn.close()

    # ========== KGStore 知识图谱统计 ==========

    def _get_kg_store_stats(self) -> dict:
        """
        KGStore 知识图谱统计

        包含实体/关系数量、质量指标（置信度分布、孤立实体、矛盾检测）、归档统计。
        Neo4j 不可用时返回空字典（不影响其他模块）。
        """
        try:
            from backend.graphrag.kg_store import get_kg_store
            kg_store = get_kg_store()
            if not kg_store.is_available():
                return {"available": False}

            return {
                "available": True,
                "entity_count": kg_store.count_entities(),
                "relation_count": kg_store.count_relations(),
                "quality": kg_store.get_quality_stats(),
                "confidence_distribution": kg_store.get_confidence_distribution(),
                "conflicts": kg_store.detect_conflicts(),
                "archive": kg_store.get_archive_stats(),
            }
        except Exception as e:
            logger.warning(f"Failed to get KGStore stats: {e}")
            return {"available": False, "error": str(e)}

    # ========== 加密覆盖率 ==========

    def _get_encryption_stats(self) -> dict:
        """检查内容加密覆盖率"""
        conn = None  # 先绑定：get_conn() 抛异常时 finally 不再 NameError
        try:
            conn = get_conn()
            stats = {}
            for table_name, mapper_name in [
                ("memory_episodic", "episodic"),
                ("memory_semantic", "semantic"),
                ("memory_versions", "versions"),
            ]:
                try:
                    cur = conn.execute(
                        f"""SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN content LIKE 'ENC:%%' THEN 1 ELSE 0 END) as encrypted,
                            SUM(CASE WHEN content IS NOT NULL AND content != '' AND content NOT LIKE 'ENC:%%' THEN 1 ELSE 0 END) as plaintext
                           FROM {table_name}"""
                    )
                    row = dict(cur.fetchone())
                    total = row.get("total", 0) or 0
                    encrypted = row.get("encrypted", 0) or 0
                    plaintext = row.get("plaintext", 0) or 0
                    stats[mapper_name] = {
                        "total": total,
                        "encrypted": encrypted,
                        "plaintext": plaintext,
                        "coverage": round(encrypted / total * 100, 1) if total > 0 else 0,
                    }
                except Exception:
                    stats[mapper_name] = {}
            return stats
        except Exception as e:
            logger.warning(f"Failed to get encryption stats: {e}")
            return {}
        finally:
            if conn is not None:
                conn.close()

    # ========== 版本历史统计 ==========

    def _get_version_stats(self) -> dict:
        """版本历史相关统计"""
        conn = None  # 先绑定：get_conn() 抛异常时 finally 不再 NameError
        try:
            conn = get_conn()

            # 有版本历史的记忆数量
            cur = conn.execute(
                "SELECT COUNT(DISTINCT memory_id) as cnt FROM memory_versions"
            )
            memories_with_versions = (cur.fetchone() or {}).get("cnt", 0)

            # 平均版本数
            cur = conn.execute(
                "SELECT AVG(cnt) as avg_v FROM (SELECT memory_id, COUNT(*) as cnt FROM memory_versions GROUP BY memory_id) t"
            )
            avg_versions = round(float((cur.fetchone() or {}).get("avg_v") or 0), 2)

            # 最近 7 天版本写入趋势
            cur = conn.execute(
                """SELECT DATE(created_at) as day, COUNT(*) as cnt
                   FROM memory_versions
                   WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                   GROUP BY DATE(created_at)
                   ORDER BY day"""
            )
            trend = [{"date": str(row["day"]), "count": row["cnt"]} for row in cur.fetchall()]

            return {
                "memories_with_versions": memories_with_versions,
                "avg_versions_per_memory": avg_versions,
                "last_7_days_trend": trend,
            }
        except Exception as e:
            logger.warning(f"Failed to get version stats: {e}")
            return {}
        finally:
            if conn is not None:
                conn.close()

    # ========== TTL 到期预警 ==========

    def _get_ttl_expiry(self) -> dict:
        """即将到期的情景记忆统计"""
        conn = None  # 先绑定：get_conn() 抛异常时 finally 不再 NameError
        try:
            conn = get_conn()

            # 按到期时间分组
            cur = conn.execute(
                """SELECT
                    SUM(CASE WHEN expires_at <= DATE_ADD(NOW(), INTERVAL 1 DAY) THEN 1 ELSE 0 END) as within_1d,
                    SUM(CASE WHEN expires_at > DATE_ADD(NOW(), INTERVAL 1 DAY) AND expires_at <= DATE_ADD(NOW(), INTERVAL 7 DAY) THEN 1 ELSE 0 END) as within_7d,
                    SUM(CASE WHEN expires_at > DATE_ADD(NOW(), INTERVAL 7 DAY) AND expires_at <= DATE_ADD(NOW(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) as within_30d,
                    SUM(CASE WHEN expires_at > DATE_ADD(NOW(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) as after_30d
                   FROM memory_episodic
                   WHERE deleted_at IS NULL AND expires_at IS NOT NULL"""
            )
            ttl_row = cur.fetchone()
            row = dict(ttl_row) if ttl_row else {}

            return {
                "within_1_day": row.get("within_1d", 0) or 0,
                "within_7_days": row.get("within_7d", 0) or 0,
                "within_30_days": row.get("within_30d", 0) or 0,
                "after_30_days": row.get("after_30d", 0) or 0,
            }
        except Exception as e:
            logger.warning(f"Failed to get TTL expiry: {e}")
            return {}
        finally:
            if conn is not None:
                conn.close()


# 单例
_service: Optional[MemoryDashboardService] = None


def get_memory_dashboard_service() -> MemoryDashboardService:
    global _service
    if _service is None:
        _service = MemoryDashboardService()
    return _service
