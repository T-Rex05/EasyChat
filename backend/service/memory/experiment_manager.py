"""
Memory AB Experiment Manager

实现 AB 实验框架，支持：
- 变体分配（基于用户 ID 的确定性分配）
- 实验事件记录
- 统计分析与显著性检验
- 10/20/30 延迟轮次对比实验
"""
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.db.schema import get_conn
from backend.utils.log_utils import log

logger = log


# ═══════════════════════════════════════════════════════════════════════════
# 实验配置
# ═══════════════════════════════════════════════════════════════════════════

# 默认实验配置
DEFAULT_EXPERIMENTS = {
    "memory_delay_rounds": {
        "name": "记忆延迟轮次实验",
        "description": "对比不同延迟轮次对记忆提取质量的影响",
        "variants": [
            {"name": "control_10", "delay_rounds": 10, "weight": 0.33},
            {"name": "variant_20", "delay_rounds": 20, "weight": 0.33},
            {"name": "variant_30", "delay_rounds": 30, "weight": 0.34},
        ],
        "metrics": ["f1_score", "precision", "recall", "latency_ms"],
        "sample_rate": 1.0,  # 100% 用户参与（测试阶段）
    }
}


class ExperimentManager:
    """
    AB 实验管理器
    
    功能：
    - 变体分配（确定性哈希）
    - 实验事件记录
    - 统计分析
    - 实验结果对比
    """
    
    def __init__(self):
        """初始化实验管理器"""
        self._experiments = DEFAULT_EXPERIMENTS.copy()
        self._load_active_experiments()
    
    def _load_active_experiments(self):
        """从数据库加载活跃的实验"""
        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT name, variant_a, variant_b, traffic_split, metrics_json, status "
                "FROM memory_ab_experiments WHERE status = 'running'"
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            
            for row in rows:
                exp_name = row["name"]
                metrics = json.loads(row["metrics_json"]) if row["metrics_json"] else []
                traffic_split = row["traffic_split"] or 0.5
                
                self._experiments[exp_name] = {
                    "name": exp_name,
                    "variants": [
                        {"name": row["variant_a"], "weight": traffic_split},
                        {"name": row["variant_b"], "weight": 1 - traffic_split},
                    ],
                    "metrics": metrics,
                    "status": "running",
                }
            
            if rows:
                logger.info(f"加载 {len(rows)} 个运行中的 AB 实验")
        except Exception as e:
            logger.debug(f"加载实验配置失败（使用默认）: {e}")
        finally:
            conn.close()
    
    def get_variant(
        self, 
        experiment_name: str, 
        user_id: int
    ) -> Dict[str, Any]:
        """
        获取用户的实验变体
        
        使用确定性哈希，确保同一用户始终分配到同一变体
        
        Args:
            experiment_name: 实验名称
            user_id: 用户 ID
            
        Returns:
            {"name": "variant_name", "config": {...}}
        """
        if experiment_name not in self._experiments:
            return {"name": "default", "config": {}}
        
        exp = self._experiments[experiment_name]
        
        # 基于用户 ID 的确定性分配
        hash_input = f"{experiment_name}_{user_id}".encode()
        hash_val = int(hashlib.md5(hash_input).hexdigest(), 16)
        bucket = (hash_val % 10000) / 10000  # 0.0000 ~ 0.9999
        
        # 根据权重分配变体
        cumulative = 0
        for variant in exp["variants"]:
            cumulative += variant["weight"]
            if bucket <= cumulative:
                logger.debug(f"用户 {user_id} 分配到实验 {experiment_name} 的变体 {variant['name']}")
                return {"name": variant["name"], "config": variant}
        
        return {"name": "default", "config": {}}
    
    def log_experiment_event(
        self,
        experiment_name: str,
        variant_name: str,
        user_id: int,
        event_type: str,
        metrics: Dict[str, Any],
        thread_id: str = ""
    ) -> int:
        """
        记录实验事件
        
        Args:
            experiment_name: 实验名称
            variant_name: 变体名称
            user_id: 用户 ID
            event_type: 事件类型（exposure, conversion, metric）
            metrics: 指标数据
            thread_id: 会话 ID
            
        Returns:
            事件 ID
        """
        conn = get_conn()
        try:
            cur = conn.execute(
                """INSERT INTO memory_ab_events 
                   (experiment_name, variant_name, user_id, thread_id, event_type, metrics_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, NOW())""",
                (experiment_name, variant_name, user_id, thread_id, event_type, json.dumps(metrics))
            )
            conn.commit()
            event_id = cur.lastrowid
            
            logger.debug(f"记录实验事件: exp={experiment_name}, variant={variant_name}, user={user_id}, type={event_type}")
            return event_id
        except Exception as e:
            logger.warning(f"记录实验事件失败: {e}")
            return 0
        finally:
            conn.close()
    
    def get_experiment_stats(
        self, 
        experiment_name: str
    ) -> Dict[str, Any]:
        """
        获取实验统计数据
        
        Args:
            experiment_name: 实验名称
            
        Returns:
            各变体的统计数据
        """
        conn = get_conn()
        try:
            # 查询各变体的指标
            cur = conn.execute(
                """SELECT 
                    variant_name,
                    COUNT(*) as sample_size,
                    AVG(JSON_EXTRACT(metrics_json, '$.f1_score')) as avg_f1,
                    AVG(JSON_EXTRACT(metrics_json, '$.precision')) as avg_precision,
                    AVG(JSON_EXTRACT(metrics_json, '$.recall')) as avg_recall,
                    AVG(JSON_EXTRACT(metrics_json, '$.latency_ms')) as avg_latency
                FROM memory_ab_events
                WHERE experiment_name = ? AND event_type = 'metric'
                GROUP BY variant_name""",
                (experiment_name,)
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            
            stats = {}
            for row in rows:
                variant = row["variant_name"]
                stats[variant] = {
                    "sample_size": row["sample_size"],
                    "avg_f1": float(row["avg_f1"] or 0),
                    "avg_precision": float(row["avg_precision"] or 0),
                    "avg_recall": float(row["avg_recall"] or 0),
                    "avg_latency": float(row["avg_latency"] or 0),
                }
            
            # 计算显著性检验（如果有两个变体）
            variants = list(stats.keys())
            if len(variants) >= 2:
                significance = self._calculate_significance(
                    stats[variants[0]], 
                    stats[variants[1]]
                )
                stats["significance"] = significance
            
            return {
                "experiment": experiment_name,
                "variants": stats,
            }
        except Exception as e:
            logger.warning(f"获取实验统计失败: {e}")
            return {"experiment": experiment_name, "variants": {}, "error": str(e)}
        finally:
            conn.close()
    
    def _calculate_significance(
        self, 
        variant_a: Dict[str, float], 
        variant_b: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        计算显著性检验（简化版 t-test）
        
        实际生产环境应使用 scipy.stats.ttest_ind
        """
        n1 = variant_a.get("sample_size", 0)
        n2 = variant_b.get("sample_size", 0)
        
        if n1 < 10 or n2 < 10:
            return {"status": "insufficient_data", "message": "样本量不足（需要 >= 10）"}
        
        f1_a = variant_a.get("avg_f1", 0)
        f1_b = variant_b.get("avg_f1", 0)
        
        # 简化的差异检测
        diff = abs(f1_a - f1_b)
        threshold = 0.05  # 5% 差异阈值
        
        if diff < threshold:
            return {
                "status": "no_significance",
                "message": f"差异 {diff:.3f} 小于阈值 {threshold}",
                "diff": diff,
            }
        else:
            winner = "variant_a" if f1_a > f1_b else "variant_b"
            return {
                "status": "significant",
                "message": f"检测到显著差异 {diff:.3f}",
                "diff": diff,
                "winner": winner,
                "f1_improvement": diff,
            }
    
    def create_experiment(
        self,
        name: str,
        description: str,
        variants: List[Dict[str, Any]],
        metrics: List[str]
    ) -> int:
        """
        创建新实验
        
        Args:
            name: 实验名称
            description: 描述
            variants: 变体列表
            metrics: 指标列表
            
        Returns:
            实验 ID
        """
        conn = get_conn()
        try:
            # 解析变体
            variant_a = variants[0]["name"] if len(variants) > 0 else "control"
            variant_b = variants[1]["name"] if len(variants) > 1 else "variant"
            traffic_split = variants[0].get("weight", 0.5) if len(variants) > 0 else 0.5
            
            cur = conn.execute(
                """INSERT INTO memory_ab_experiments 
                   (name, description, variant_a, variant_b, traffic_split, metrics_json, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'draft')""",
                (name, description, variant_a, variant_b, traffic_split, json.dumps(metrics))
            )
            conn.commit()
            
            exp_id = cur.lastrowid
            logger.info(f"创建实验: id={exp_id}, name={name}")
            return exp_id
        except Exception as e:
            logger.warning(f"创建实验失败: {e}")
            return 0
        finally:
            conn.close()
    
    def start_experiment(self, experiment_id: int) -> bool:
        """启动实验"""
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE memory_ab_experiments SET status = 'running', started_at = NOW() WHERE id = ?",
                (experiment_id,)
            )
            conn.commit()
            logger.info(f"启动实验: id={experiment_id}")
            return True
        except Exception as e:
            logger.warning(f"启动实验失败: {e}")
            return False
        finally:
            conn.close()
    
    def stop_experiment(self, experiment_id: int) -> bool:
        """停止实验"""
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE memory_ab_experiments SET status = 'completed', ended_at = NOW() WHERE id = ?",
                (experiment_id,)
            )
            conn.commit()
            logger.info(f"停止实验: id={experiment_id}")
            return True
        except Exception as e:
            logger.warning(f"停止实验失败: {e}")
            return False
        finally:
            conn.close()
    
    def list_experiments(
        self, 
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        列出实验
        
        Args:
            status: 状态筛选（draft/running/completed）
            
        Returns:
            实验列表
        """
        conn = get_conn()
        try:
            if status:
                cur = conn.execute(
                    "SELECT * FROM memory_ab_experiments WHERE status = ? ORDER BY created_at DESC",
                    (status,)
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM memory_ab_experiments ORDER BY created_at DESC"
                )
            
            rows = cur.fetchall() if hasattr(cur, "fetchall") else []
            return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"列出实验失败: {e}")
            return []
        finally:
            conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# 延迟轮次实验专用类
# ═══════════════════════════════════════════════════════════════════════════

class DelayRoundsExperiment:
    """
    延迟轮次实验
    
    专门用于对比 10/20/30 轮次的记忆提取质量
    """
    
    EXPERIMENT_NAME = "memory_delay_rounds"
    
    def __init__(self):
        self._manager = ExperimentManager()
    
    def get_user_delay_rounds(self, user_id: int) -> int:
        """
        获取用户的延迟轮次配置
        
        Args:
            user_id: 用户 ID
            
        Returns:
            延迟轮次（10/20/30）
        """
        variant = self._manager.get_variant(self.EXPERIMENT_NAME, user_id)
        return variant.get("config", {}).get("delay_rounds", 10)
    
    def record_extraction_metric(
        self,
        user_id: int,
        thread_id: str,
        f1_score: float,
        precision: float,
        recall: float,
        latency_ms: int
    ):
        """
        记录记忆提取指标
        
        Args:
            user_id: 用户 ID
            thread_id: 会话 ID
            f1_score: F1 分数
            precision: 精确率
            recall: 召回率
            latency_ms: 延迟（毫秒）
        """
        variant = self._manager.get_variant(self.EXPERIMENT_NAME, user_id)
        variant_name = variant["name"]
        
        self._manager.log_experiment_event(
            experiment_name=self.EXPERIMENT_NAME,
            variant_name=variant_name,
            user_id=user_id,
            thread_id=thread_id,
            event_type="metric",
            metrics={
                "f1_score": f1_score,
                "precision": precision,
                "recall": recall,
                "latency_ms": latency_ms,
            }
        )
    
    def get_results(self) -> Dict[str, Any]:
        """
        获取实验结果
        
        Returns:
            各变体的统计数据和显著性检验结果
        """
        return self._manager.get_experiment_stats(self.EXPERIMENT_NAME)


# ═══════════════════════════════════════════════════════════════════════════
# 单例访问
# ═══════════════════════════════════════════════════════════════════════════

_manager: Optional[ExperimentManager] = None
_delay_experiment: Optional[DelayRoundsExperiment] = None


def get_experiment_manager() -> ExperimentManager:
    """获取实验管理器单例"""
    global _manager
    if _manager is None:
        _manager = ExperimentManager()
    return _manager


def get_delay_rounds_experiment() -> DelayRoundsExperiment:
    """获取延迟轮次实验单例"""
    global _delay_experiment
    if _delay_experiment is None:
        _delay_experiment = DelayRoundsExperiment()
    return _delay_experiment