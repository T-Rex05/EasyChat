"""
模型管理器 - 从数据库加载模型配置并构建LLM
"""
from typing import Optional, Dict, Any
from langchain_openai import ChatOpenAI

from backend.db.model_config_mapper_impl import ModelConfigMapperImpl
from backend.utils.log_utils import log

logger = log


class ModelManager:
    """模型管理器"""

    def __init__(self, model_config_mapper: ModelConfigMapperImpl):
        self.model_config_mapper = model_config_mapper

    def build_llm_from_config(self, config: Dict[str, Any]):
        """
        根据配置构建LLM实例

        Args:
            config: 模型配置字典（已解密）

        Returns:
            ChatOpenAI: LLM实例

        Raises:
            Exception: 配置无效或构建失败
        """
        config_type = config.get('config_type', '').upper()

        try:
            if config_type == 'URL':
                # URL类型：使用API URL和Key
                return self._build_url_llm(config)
            elif config_type == 'OLLAMA':
                # Ollama类型
                return self._build_ollama_llm(config)
            elif config_type == 'LOCAL':
                # 本地类型（私有化部署）
                return self._build_local_llm(config)
            else:
                raise ValueError(f"不支持的配置类型: {config_type}")
        except Exception as e:
            logger.error(f"构建LLM失败: {e}")
            raise e

    def _build_url_llm(self, config: Dict[str, Any]):
        """构建URL类型的LLM（OpenAI兼容）"""
        api_url = config.get('api_url')
        api_key = config.get('api_key')
        model_name = config.get('model_name')

        if not api_url or not api_key or not model_name:
            raise ValueError("URL类型配置缺少必要参数: api_url, api_key, model_name")

        logger.info(f"构建URL类型LLM - model: {model_name}, url: {api_url}")

        # 使用ChatOpenAI兼容OpenAI API
        return ChatOpenAI(
            base_url=api_url,
            api_key=api_key,
            model=model_name,
            temperature=0.1,  # 默认温度
            streaming=True,  # 启用流式输出
            max_tokens=8192  # 设置最大输出token数，确保长内容不被截断
        )

    def _build_ollama_llm(self, config: Dict[str, Any]):
        """构建Ollama类型的LLM"""
        ip_address = config.get('ip_address')
        port = config.get('port')
        model_name = config.get('model_name')

        if not ip_address or not model_name:
            raise ValueError("Ollama类型配置缺少必要参数: ip_address, model_name")

        # 构建Ollama API URL
        base_url = f"http://{ip_address}:{port if port else 11434}"
        logger.info(f"构建Ollama类型LLM - model: {model_name}, url: {base_url}")

        # Ollama兼容OpenAI API
        return ChatOpenAI(
            base_url=f"{base_url}/v1",
            api_key="ollama",  # Ollama不需要真实的key
            model=model_name,
            temperature=0.1,
            streaming=True,  # 启用流式输出
            max_tokens=8192  # 设置最大输出token数，确保长内容不被截断
        )

    def _build_local_llm(self, config: Dict[str, Any]):
        """构建本地私有化部署的LLM（兼容vLLM等）"""
        model_path = config.get('model_path') or config.get('api_url')
        model_name = config.get('model_name')

        if not model_name:
            raise ValueError("本地类型配置缺少必要参数: model_name")

        # 如果有完整URL，直接使用
        if model_path and model_path.startswith('http'):
            base_url = model_path
        else:
            # 默认localhost
            base_url = "http://localhost:11434/v1"

        logger.info(f"构建本地类型LLM（私有化部署） - model: {model_name}, url: {base_url}")

        # 兼容vLLM等私有化部署（通常兼容OpenAI API）
        return ChatOpenAI(
            base_url=base_url,
            api_key="local",  # 本地部署不需要真实的key
            model=model_name,
            temperature=0.1,
            streaming=True,  # 启用流式输出
            max_tokens=8192  # 设置最大输出token数，确保长内容不被截断
        )

    def get_active_llm(self, user_id: int = 1):
        """
        获取用户的激活LLM

        Args:
            user_id: 用户ID，默认为1

        Returns:
            ChatOpenAI: LLM实例

        Raises:
            Exception: 未找到配置或构建失败
        """
        # 从数据库获取用户激活的模型配置
        config = self.model_config_mapper.get_active_model_config(user_id)

        if not config:
            # 没有配置则抛出异常，提示用户配置
            raise Exception(
                f"用户 {user_id} 未配置模型，"
                f"请先在前端模型配置页面配置模型"
            )

        # 根据配置构建LLM
        return self.build_llm_from_config(config)


# 全局模型管理器实例
_model_manager: Optional[ModelManager] = None
_model_config_mapper = None


def get_model_manager() -> ModelManager:
    """获取全局模型管理器实例"""
    global _model_manager
    return _model_manager


def get_user_specific_model_manager(user_id: int) -> ModelManager:
    """根据用户ID获取特定的模型管理器"""
    global _model_manager, _model_config_mapper
    
    if not _model_config_mapper:
        return _model_manager
    
    try:
        # 获取用户的当前模型配置
        current_config = _model_config_mapper.get_active_model_config(user_id)
        if not current_config:
            return _model_manager
        
        # 根据配置类型创建或获取对应的模型管理器
        if current_config.get('config_type') == 'URL':
            # URL类型配置，可能需要根据模型类型返回不同的管理器
            # 这里可以根据实际需求实现更复杂的逻辑
            return _model_manager
        elif current_config.get('config_type') == 'Ollama':
            # Ollama配置
            return _model_manager
        elif current_config.get('config_type') == 'LOCAL':
            # 本地配置
            return _model_manager
        
        return _model_manager
    except Exception:
        return _model_manager


def set_model_manager(manager: ModelManager):
    """设置全局模型管理器实例"""
    global _model_manager
    _model_manager = manager
