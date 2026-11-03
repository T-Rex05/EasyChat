"""EasyChat 启动入口（新架构）。

`python main.py` 等同于 `uvicorn backend.server:app`：显式读取环境配置，
由 `backend.app.create_app` 装配新模块，不扫描旧 controller、不启动 MySQL。
"""
from __future__ import annotations

import os

import uvicorn

from backend.app import create_app
from backend.bootstrap import settings_from_environment

app = create_app(settings_from_environment())


def main() -> None:
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run(
        "backend.server:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=port,
        workers=1,
    )


if __name__ == "__main__":
    main()
