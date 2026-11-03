"""
检索质量统计服务 — 基于 kb_retrieval_logs 聚合。

提供在线检索质量监控数据：空检索率、命中率、延迟分布、每日趋势等。
用于发现检索质量劣化（如 embedding 模型更换后、数据分布漂移等）。
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_retrieval_stats(user_id: int, days: int = 7) -> dict:
    """
    检索质量统计。

    Args:
        user_id: 用户 ID
        days: 统计天数（默认 7 天）

    Returns:
        {
            "total_queries": int,          # 总查询数
            "avg_hit_count": float,        # 平均命中数
            "empty_rate": float,           # 空检索率 (hit_count=0 的占比)
            "low_hit_rate": float,         # 低命中率 (hit_count=1 的占比)
            "avg_elapsed_ms": float,       # 平均耗时
            "p95_elapsed_ms": int,         # P95 耗时
            "daily": [                     # 每日趋势（按日期升序）
                {"date": "2026-09-14", "queries": 10, "avg_hits": 3.2, "empty_rate": 0.1, "avg_elapsed_ms": 150},
                ...
            ],
            "by_retriever": {              # 按检索器类型统计
                "dual_path": {"count": 50, "avg_hits": 4.1, "empty_rate": 0.05},
                "hybrid": {"count": 20, "avg_hits": 3.5, "empty_rate": 0.1},
            }
        }
    """
    from backend.db.schema import get_conn

    conn = get_conn()
    try:
        # ── 1. 总体统计 ──
        cur = conn.execute(
            """
            SELECT
                COUNT(*) AS total_queries,
                AVG(hit_count) AS avg_hit_count,
                AVG(elapsed_ms) AS avg_elapsed_ms,
                SUM(CASE WHEN hit_count = 0 THEN 1 ELSE 0 END) AS empty_count,
                SUM(CASE WHEN hit_count = 1 THEN 1 ELSE 0 END) AS low_count
            FROM kb_retrieval_logs
            WHERE user_id = ?
              AND created_at >= DATE_SUB(NOW(), INTERVAL ? DAY)
            """,
            (user_id, days),
        )
        row = cur.fetchone() if hasattr(cur, "fetchone") else None
        if not row or not row.get("total_queries"):
            return {
                "total_queries": 0,
                "avg_hit_count": 0,
                "empty_rate": 0,
                "low_hit_rate": 0,
                "avg_elapsed_ms": 0,
                "p95_elapsed_ms": 0,
                "daily": [],
                "by_retriever": {},
            }

        total = row["total_queries"]
        empty_count = row.get("empty_count", 0) or 0
        low_count = row.get("low_count", 0) or 0

        # ── 2. P95 延迟 ──
        cur = conn.execute(
            """
            SELECT elapsed_ms FROM kb_retrieval_logs
            WHERE user_id = ?
              AND created_at >= DATE_SUB(NOW(), INTERVAL ? DAY)
            ORDER BY elapsed_ms ASC
            """,
            (user_id, days),
        )
        all_elapsed = [r["elapsed_ms"] for r in cur.fetchall()] if hasattr(cur, "fetchall") else []
        p95_idx = max(0, int(len(all_elapsed) * 0.95) - 1)
        p95_elapsed = all_elapsed[p95_idx] if all_elapsed else 0

        # ── 3. 每日趋势 ──
        cur = conn.execute(
            """
            SELECT
                DATE(created_at) AS stat_date,
                COUNT(*) AS queries,
                AVG(hit_count) AS avg_hits,
                AVG(elapsed_ms) AS avg_elapsed,
                SUM(CASE WHEN hit_count = 0 THEN 1 ELSE 0 END) AS empties
            FROM kb_retrieval_logs
            WHERE user_id = ?
              AND created_at >= DATE_SUB(NOW(), INTERVAL ? DAY)
            GROUP BY DATE(created_at)
            ORDER BY stat_date ASC
            """,
            (user_id, days),
        )
        daily = []
        for r in (cur.fetchall() if hasattr(cur, "fetchall") else []):
            q = r.get("queries", 0) or 1
            daily.append({
                "date": str(r["stat_date"]),
                "queries": r.get("queries", 0),
                "avg_hits": round(float(r.get("avg_hits", 0) or 0), 2),
                "empty_rate": round(float(r.get("empties", 0) or 0) / q, 4),
                "avg_elapsed_ms": round(float(r.get("avg_elapsed", 0) or 0), 1),
            })

        # ── 4. 按检索器类型统计 ──
        cur = conn.execute(
            """
            SELECT
                retriever,
                COUNT(*) AS count,
                AVG(hit_count) AS avg_hits,
                SUM(CASE WHEN hit_count = 0 THEN 1 ELSE 0 END) AS empties
            FROM kb_retrieval_logs
            WHERE user_id = ?
              AND created_at >= DATE_SUB(NOW(), INTERVAL ? DAY)
              AND retriever != ''
            GROUP BY retriever
            """,
            (user_id, days),
        )
        by_retriever = {}
        for r in (cur.fetchall() if hasattr(cur, "fetchall") else []):
            name = r.get("retriever", "unknown")
            cnt = r.get("count", 0) or 1
            by_retriever[name] = {
                "count": r.get("count", 0),
                "avg_hits": round(float(r.get("avg_hits", 0) or 0), 2),
                "empty_rate": round(float(r.get("empties", 0) or 0) / cnt, 4),
            }

        return {
            "total_queries": total,
            "avg_hit_count": round(float(row.get("avg_hit_count", 0) or 0), 2),
            "empty_rate": round(empty_count / total, 4),
            "low_hit_rate": round(low_count / total, 4),
            "avg_elapsed_ms": round(float(row.get("avg_elapsed_ms", 0) or 0), 1),
            "p95_elapsed_ms": int(p95_elapsed),
            "daily": daily,
            "by_retriever": by_retriever,
        }
    except Exception as e:
        logger.warning(f"[RetrievalStats] 统计查询失败: {e}")
        return {
            "total_queries": 0,
            "avg_hit_count": 0,
            "empty_rate": 0,
            "low_hit_rate": 0,
            "avg_elapsed_ms": 0,
            "p95_elapsed_ms": 0,
            "daily": [],
            "by_retriever": {},
            "error": str(e),
        }
    finally:
        conn.close()
