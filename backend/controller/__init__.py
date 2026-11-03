"""
控制器自动注册模块

自动扫描 backend/controller/ 目录，发现并注册所有 APIRouter
"""
import importlib
import pkgutil
from pathlib import Path
from typing import List, Dict, Any

from fastapi import FastAPI, APIRouter
from backend.utils.log_utils import log

logger = log


def discover_routers() -> List[Dict[str, Any]]:
    """
    发现所有控制器中的 APIRouter
    
    Returns:
        List[Dict]: 包含 controller 名称和 router 对象的列表
    """
    controller_dir = Path(__file__).parent
    routers = []
    
    # 遍历 controller 目录下的所有 *_controller.py 文件
    for module_info in pkgutil.iter_modules([str(controller_dir)]):
        if not module_info.name.endswith('_controller'):
            continue
            
        # 跳过特殊处理的控制器
        if module_info.name in ['chat_controller', 'data_controller']:
            continue
            
        try:
            # 动态导入模块
            module = importlib.import_module(f'backend.controller.{module_info.name}')
            
            # 查找 router 对象
            if hasattr(module, 'router'):
                router = getattr(module, 'router')
                if isinstance(router, APIRouter):
                    routers.append({
                        'name': module_info.name,
                        'router': router,
                        'prefix': router.prefix if hasattr(router, 'prefix') else None
                    })
                    logger.debug(f"发现控制器: {module_info.name} (prefix={router.prefix})")
        except Exception as e:
            logger.warning(f"加载控制器 {module_info.name} 失败: {e}")
    
    return routers


def register_all_routers(app: FastAPI) -> int:
    """
    自动注册所有发现的控制器
    
    Args:
        app: FastAPI 应用实例
        
    Returns:
        int: 成功注册的控制器数量
    """
    routers = discover_routers()
    count = 0
    
    for router_info in routers:
        try:
            app.include_router(router_info['router'])
            name = router_info['name']
            prefix = router_info['prefix']
            logger.info(f"{name} 已注册 (prefix={prefix})")
            count += 1
        except Exception as e:
            logger.error(f"注册控制器 {router_info['name']} 失败: {e}")
    
    return count
