"""pytest 根配置。

默认离线：不加载任何 .env（旧的真实联调测试按 integration 标记隔离，
随旧业务退役由 Task 15 清理）。真实网络/外部服务的测试必须显式标记
`integration`；目标镜像资源测量标记 `resources`。
"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中（`from backend... import` 依赖它）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# hermes 内核的顶层 `tools` 包必须先于全局 Python 里其它项目的 editable 安装
# （site-packages 的 *.pth 会把第三方仓库目录注入 sys.path，其同名 `tools`
# 抢先绑定后 `from tools.registry import registry` 顺序相关地失败）。
# conftest 阶段清除可能的抢绑并把内核目录置于最前，保证绑定确定性。
_HERMES_DIR = Path(__file__).resolve().parent.parent / "backend" / "hermes"
sys.path.insert(0, str(_HERMES_DIR))
sys.modules.pop("tools", None)

import pytest

from tests.support.rig import TestRig, make_rig

# AgentForge 旧架构（backend.service / 旧 SSE / 旧 KB）已经移除；这些根目录测试
# 没有迁移到模块化架构，保留文件仅作历史参考。默认收集时跳过，避免 `pytest`
# 在 import 阶段整体中断，导致维护中套件也无法运行。
collect_ignore_glob = ["test_*.py"]
collect_ignore = [
    "test_adaptive_retrieval.py",
    "test_auth_service.py",
    "test_context_enrichment.py",
    "test_delegation_integration.py",
    "test_host_whitelist.py",
    "test_kb_metadata_global.py",
    "test_kb_topic_marker.py",
    "test_llm_gateway.py",
    "test_memory_consistency.py",
    "test_paper_reproduction.py",
    "test_report_quality.py",
    "test_run_registry.py",
    "test_session_title.py",
    "test_skill_service.py",
    "test_skill_tool_permissions.py",
    "test_sse_contract.py",
    "test_ssh_auth_inject.py",
]


@pytest.fixture
async def rig(tmp_path):
    """独立 TestRig：临时目录 + 假Runtime，测试结束自动关闭。"""
    r: TestRig = make_rig(tmp_path)
    yield r
    await r.aclose()
