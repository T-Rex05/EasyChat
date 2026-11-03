"""
上下文压缩策略配置

当前设计：全局配置（.env）。
未来扩展口子：如需按用户切换，只需在 get_context_strategy() 里加一个前置查询
user_configs 表的步骤，本模块其它代码不用改。

可用策略：
  - default       : Hermes 原配阈值+语义摘要（稳定、通用）
  - fact_anchor   : 压缩前先抽关键事实作为只读片段注入，防止"执行事实丢失"
  - none          : 不做任何压缩（仅适合超长上下文模型或测试）
"""

import os
import logging

logger = logging.getLogger(__name__)


# 合法策略白名单
VALID_STRATEGIES = {"default", "fact_anchor", "none"}

# 默认策略
DEFAULT_STRATEGY = "default"


def get_context_strategy() -> str:
    """读取当前上下文压缩策略。

    优先级：
      1. 环境变量 CONTEXT_STRATEGY
      2. 默认值 'default'
    """
    raw = (os.environ.get("CONTEXT_STRATEGY") or DEFAULT_STRATEGY).strip().lower()
    if raw not in VALID_STRATEGIES:
        logger.warning(
            f"⚠️ CONTEXT_STRATEGY='{raw}' 不合法，回退为 '{DEFAULT_STRATEGY}'。"
            f"合法值：{sorted(VALID_STRATEGIES)}"
        )
        return DEFAULT_STRATEGY
    return raw


def get_fact_anchor_max_facts() -> int:
    """事实锚定策略：最多提取几条关键事实。默认 20。"""
    try:
        return max(1, int(os.environ.get("FACT_ANCHOR_MAX_FACTS") or "20"))
    except (TypeError, ValueError):
        return 20


def get_fact_anchor_enabled() -> bool:
    """事实锚定策略总开关。默认 True（策略切到 fact_anchor 时生效）。

    设为 False 可在不修改 CONTEXT_STRATEGY 的情况下临时禁用事实提取，
    退化为 Hermes 原配压缩。用于快速排查/对比。
    """
    raw = (os.environ.get("FACT_ANCHOR_ENABLED") or "").strip().lower()
    if raw == "":
        return True  # 未配置 → 默认开启
    return raw in ("1", "true", "yes", "on")
