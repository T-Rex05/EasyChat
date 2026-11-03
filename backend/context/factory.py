"""
上下文压缩策略工厂

根据策略名实例化对应的 ContextEngine。策略模块放在 strategies/ 子目录，
通过 importlib 动态加载，新增策略只需加文件 + 在 STRATEGIES 里登记。
"""

import importlib
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


# 策略名 → 模块路径（相对于 backend.context.strategies）
# 新增策略时在此登记即可。
STRATEGIES: Dict[str, str] = {
    "default": "backend.context.strategies.default",
    "fact_anchor": "backend.context.strategies.fact_anchor",
}


def create_engine(strategy: str, engine_kwargs: Dict[str, Any]) -> Any:
    """根据策略名实例化 ContextEngine。

    Args:
        strategy: 策略名（default / fact_anchor / none）
        engine_kwargs: 传给策略 build() 的构造参数。
            通常包括 agent 的 model / base_url / api_key / provider / api_mode /
            context_length / max_tokens 等，以及 Hermes 配置里的压缩相关参数。

    Returns:
        ContextEngine 实例，可直接赋值给 agent.context_compressor。
        'none' 策略返回 None，由调用方决定如何处理（Hermes 会跳过压缩）。
    """
    if strategy == "none":
        logger.info("上下文策略: none（禁用压缩）")
        return None

    module_path = STRATEGIES.get(strategy)
    if not module_path:
        logger.warning(
            f"⚠️ 未知上下文策略 '{strategy}'，回退为 default。"
            f"可用策略: {sorted(STRATEGIES.keys())}"
        )
        module_path = STRATEGIES["default"]

    try:
        module = importlib.import_module(module_path)
        build = getattr(module, "build")
    except Exception as e:
        logger.error(
            f"❌ 加载策略模块 '{module_path}' 失败: {e}，回退为 default"
        )
        module = importlib.import_module(STRATEGIES["default"])
        build = getattr(module, "build")

    engine = build(**engine_kwargs)
    logger.info(f"上下文策略已加载: {strategy} → {type(engine).__name__}")
    return engine
