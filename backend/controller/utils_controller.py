"""
工具控制器 - 提供通用的工具函数
"""
from typing import Any


def sanitize_for_json(obj: Any) -> Any:
    """将对象转换为可JSON序列化的格式"""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    if isinstance(obj, dict):
        return {key: sanitize_for_json(value) for key, value in obj.items()}
    if hasattr(obj, '__dict__'):
        return sanitize_for_json(obj.__dict__)
    return str(obj)


def safe_json_dumps(obj: Any) -> str:
    """安全的JSON序列化"""
    try:
        import json
        return json.dumps(sanitize_for_json(obj), ensure_ascii=False)
    except Exception:
        return json.dumps({"error": "Serialization failed"}, ensure_ascii=False)
