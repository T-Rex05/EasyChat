# backend/hermes/plugins/memory/__init__.py
"""
Hermes Memory Provider Plugin - AgentForge Integration

这个模块实现 Hermes 的 memory provider 插件接口，
将 AgentForge 的向量记忆系统连接到 Hermes Agent。
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Provider 发现结果缓存
_providers: Dict[str, Any] = {}


def discover_memory_providers() -> List[Tuple[str, str, bool]]:
    """
    发现所有可用的 memory providers
    
    Returns:
        [(name, description, is_available), ...]
    """
    providers = []
    
    # AgentForge Provider
    try:
        from backend.memory.agentforge_provider import AgentForgeMemoryProvider
        provider = AgentForgeMemoryProvider()
        providers.append((
            "agentforge",
            "AgentForge 向量记忆系统（MySQL + Milvus/ChromaDB）",
            provider.is_available()
        ))
        _providers["agentforge"] = provider
    except Exception as e:
        logger.debug(f"AgentForge provider discovery failed: {e}")
        providers.append(("agentforge", "AgentForge 向量记忆系统", False))
    
    # Honcho Provider (如果安装)
    try:
        from plugins.memory.honcho.provider import HonchoMemoryProvider
        provider = HonchoMemoryProvider()
        providers.append((
            "honcho",
            "Honcho 云端记忆服务",
            provider.is_available()
        ))
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Honcho provider discovery failed: {e}")
    
    # Mem0 Provider (如果安装)
    try:
        from plugins.memory.mem0.provider import Mem0MemoryProvider
        provider = Mem0MemoryProvider()
        providers.append((
            "mem0",
            "Mem0 智能记忆服务",
            provider.is_available()
        ))
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Mem0 provider discovery failed: {e}")
    
    return providers


def load_memory_provider(name: str) -> Optional[Any]:
    """
    加载指定的 memory provider
    
    Args:
        name: provider 名称（如 "agentforge", "honcho", "mem0"）
        
    Returns:
        provider 实例，不存在或不可用返回 None
    """
    # 检查缓存
    if name in _providers:
        return _providers[name]
    
    # AgentForge Provider
    if name == "agentforge":
        try:
            from backend.memory.agentforge_provider import AgentForgeMemoryProvider
            provider = AgentForgeMemoryProvider()
            if provider.is_available():
                _providers[name] = provider
                return provider
        except Exception as e:
            logger.warning(f"Failed to load agentforge provider: {e}")
    
    # Honcho Provider
    if name == "honcho":
        try:
            from plugins.memory.honcho.provider import HonchoMemoryProvider
            provider = HonchoMemoryProvider()
            if provider.is_available():
                _providers[name] = provider
                return provider
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to load honcho provider: {e}")
    
    # Mem0 Provider
    if name == "mem0":
        try:
            from plugins.memory.mem0.provider import Mem0MemoryProvider
            provider = Mem0MemoryProvider()
            if provider.is_available():
                _providers[name] = provider
                return provider
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to load mem0 provider: {e}")
    
    return None


def list_memory_provider_names() -> List[str]:
    """
    列出所有已知的 memory provider 名称
    
    Returns:
        provider 名称列表
    """
    return [name for name, _, _ in discover_memory_providers()]


def _get_active_memory_provider() -> Optional[Any]:
    """
    获取当前激活的 memory provider
    
    Returns:
        当前 provider 实例，没有返回 None
    """
    # 从 Hermes 配置读取
    try:
        from hermes_constants import get_hermes_home
        import yaml
        
        config_path = get_hermes_home() / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
            provider_name = (config.get("memory") or {}).get("provider", "")
            if provider_name:
                return load_memory_provider(provider_name)
    except Exception:
        pass
    
    return None


def _is_memory_provider_dir(path: str) -> bool:
    """
    检查路径是否是有效的 memory provider 目录
    
    Args:
        path: 目录路径
        
    Returns:
        是否是有效的 provider 目录
    """
    import os
    if not os.path.isdir(path):
        return False
    
    # 必须有 provider.py 或 __init__.py
    has_provider = os.path.exists(os.path.join(path, "provider.py"))
    has_init = os.path.exists(os.path.join(path, "__init__.py"))
    
    return has_provider or has_init


__all__ = [
    "discover_memory_providers",
    "load_memory_provider",
    "list_memory_provider_names",
    "_get_active_memory_provider",
    "_is_memory_provider_dir",
]