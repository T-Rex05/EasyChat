"""
上下文压缩策略包

策略实现统一放在 strategies/ 子目录。每个策略是一个模块，导出 build(**kwargs) 工厂函数。
factory.py 负责根据策略名查找并实例化。

新增策略的步骤：
  1. 在 strategies/ 下新建 my_strategy.py
  2. 导出 build(engine_kwargs, **runtime_kwargs) -> ContextEngine
  3. 在 factory.py 的 STRATEGIES 字典里登记
"""

from backend.context.config import get_context_strategy
from backend.context.factory import create_engine, STRATEGIES

__all__ = ["get_context_strategy", "create_engine", "STRATEGIES"]
