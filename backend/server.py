"""新架构启动入口：显式读取环境配置 → create_app（import 不连库/不迁移）。

部署使用：`uvicorn backend.server:app`。旧 main.py 暂保留用于未迁移入口，
Task 15 完成后再切换。
"""
from __future__ import annotations

from backend.app import create_app
from backend.bootstrap import settings_from_environment

app = create_app(settings_from_environment())
