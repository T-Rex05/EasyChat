"""
Token 计算工具 - 使用 tiktoken 精确计算 token 数
"""
import tiktoken
from typing import Union


# 全局缓存 tokenizer，限制最大缓存数量防止内存泄漏
_tokenizer_cache = {}
_MAX_CACHE_SIZE = 10  # tiktoken 常用 encoding 不超过 10 种


def get_tokenizer(encoding_name: str = "cl100k_base"):
    """
    获取 tiktoken tokenizer（带缓存）

    Args:
        encoding_name: 编码名称，默认 cl100k_base（GPT-4）

    Returns:
        tiktoken.Encoding
    """
    # 如果缓存已满且不在缓存中，清理旧缓存
    if encoding_name not in _tokenizer_cache and len(_tokenizer_cache) >= _MAX_CACHE_SIZE:
        _tokenizer_cache.clear()
    
    if encoding_name not in _tokenizer_cache:
        _tokenizer_cache[encoding_name] = tiktoken.get_encoding(encoding_name)
    return _tokenizer_cache[encoding_name]


def count_tokens(text: Union[str, list], encoding_name: str = "cl100k_base") -> int:
    """
    计算文本的 token 数

    Args:
        text: 文本内容，可以是字符串或字符串列表
        encoding_name: 编码名称，默认 cl100k_base（GPT-4）

    Returns:
        int: token 数
    """
    tokenizer = get_tokenizer(encoding_name)

    if isinstance(text, list):
        # 如果是列表，合并后计算
        text = "\n".join(str(t) for t in text)

    return len(tokenizer.encode(text))


def count_messages_tokens(messages: list, encoding_name: str = "cl100k_base") -> int:
    """
    计算消息列表的 token 数（符合 OpenAI 消息格式）

    Args:
        messages: 消息列表，每条消息是 dict with "role" and "content"
        encoding_name: 编码名称

    Returns:
        int: 总 token 数
    """
    tokenizer = get_tokenizer(encoding_name)

    tokens_per_message = 3  # 每条消息的开销: <|start|>{role/name}\n{content}<|end|>
    tokens_per_name = 1  # 如果消息有 name 字段

    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(tokenizer.encode(value))
            if key == "name":
                num_tokens += tokens_per_name

    num_tokens += 3  # 每个回复的 assistant 开销
    return num_tokens


def format_tokens(num_tokens: int) -> str:
    """
    格式化 token 数显示

    Args:
        num_tokens: token 数

    Returns:
        str: 格式化后的字符串
    """
    if num_tokens < 1000:
        return f"{num_tokens:,}"
    elif num_tokens < 1000000:
        return f"{num_tokens/1000:.1f}K"
    else:
        return f"{num_tokens/1000000:.2f}M"
