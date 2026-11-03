"""
default 策略 —— 直接使用 Hermes 自带的 ContextCompressor

行为与 Hermes 默认完全一致：阈值触发 + 语义摘要。
作为所有策略的兜底，也用于"策略配置缺失 / 未知策略名"的回退场景。

工厂函数 build() 的参数对齐 fact_anchor 等其它策略，但实际忽略 ——
因为 default 策略复用 Hermes 自己创建的 ContextCompressor 实例即可。
hermes_adapter 看到返回 None 时会保留 Hermes 默认实例，不做替换。
"""

from typing import Any


def build(**kwargs: Any) -> None:
    """default 策略:不创建新 engine，由 hermes_adapter 保留 Hermes 默认实例。

    Returns:
        None —— 调用方收到 None 时保留 agent.context_compressor 现状。
    """
    return None
