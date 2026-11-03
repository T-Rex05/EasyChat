"""Hermes 运行环境引导。

必须在 import 任何 Hermes 内部模块之前调用 ensure_hermes_environment：
- backend/hermes 目录加入 sys.path（Hermes 包内互用顶层模块名）；
- 设置 HERMES_HOME（运行数据/技能/state.db 的根目录）。

顺序错了配置/技能/会话会落到用户家目录（旧 hermes_adapter.py 的教训）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_HERMES_DIR = Path(__file__).resolve().parents[2] / "hermes"  # backend/hermes


def ensure_hermes_environment(hermes_home: Path) -> Path:
    """幂等设置 sys.path 与 HERMES_HOME，返回 hermes 包目录。"""
    hermes_dir = str(_HERMES_DIR)
    if hermes_dir not in sys.path:
        sys.path.insert(0, hermes_dir)
    home = str(Path(hermes_home).resolve())
    if os.environ.get("HERMES_HOME") != home:
        os.environ["HERMES_HOME"] = home
    Path(home).mkdir(parents=True, exist_ok=True)
    return _HERMES_DIR
