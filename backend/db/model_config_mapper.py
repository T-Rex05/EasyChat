"""
模型配置数据访问接口

定义模型配置的抽象接口，供实现类继承
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Protocol


class ModelConfigMapper(Protocol):
    """
    模型配置数据访问协议
    
    使用 Protocol 定义接口，支持结构化子类型（鸭子类型）
    """
    
    def get_all_configs(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取所有模型配置"""
        ...
    
    def get_config_by_id(self, config_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取配置"""
        ...
    
    def get_current_chat_config(self, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """获取当前激活的聊天模型配置"""
        ...
    
    def get_current_embedding_config(self, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """获取当前激活的嵌入模型配置"""
        ...
    
    def get_current_rerank_config(self, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """获取当前激活的重排模型配置"""
        ...
    
    def set_current_config(self, config_id: int, user_id: Optional[int] = None) -> bool:
        """设置当前激活的配置"""
        ...
    
    def create_config(self, config_data: Dict[str, Any]) -> int:
        """创建新配置"""
        ...
    
    def update_config(self, config_id: int, config_data: Dict[str, Any]) -> bool:
        """更新配置"""
        ...
    
    def delete_config(self, config_id: int) -> bool:
        """删除配置"""
        ...