"""pytest 根配置。

默认离线：不加载任何 .env（旧的真实联调测试按 integration 标记隔离，
随旧业务退役由 Task 15 清理）。真实网络/外部服务的测试必须显式标记
`integration`；目标镜像资源测量标记 `resources`。
"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中（`from backend... import` 依赖它）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from tests.support.rig import TestRig, make_rig


@pytest.fixture
async def rig(tmp_path):
    """独立 TestRig：临时目录 + 假Runtime，测试结束自动关闭。"""
    r: TestRig = make_rig(tmp_path)
    yield r
    await r.aclose()
