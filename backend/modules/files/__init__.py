"""files 模块：唯一文件持久保存/读取/下载/生命周期入口（设计 §3–§5）。

跨模块只允许使用 `api.py` / `contracts.py`。
"""
from backend.modules.files.api import FileService

__all__ = ["FileService"]
