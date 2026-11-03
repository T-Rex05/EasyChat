"""资源测量（Task 16，marker=resources，默认排除）。

启动真实 uvicorn 子进程（core 依赖、Hermes 关闭），等待 ready，再用 psutil 采样 RSS。
这是目标镜像的资源验收工具，不是精确容量结论。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

psutil = pytest.importorskip("psutil")

pytestmark = pytest.mark.resources

RSS_LIMIT_MIB = 1024


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_main_process_rss_under_target(tmp_path):
    port = _free_port()
    env = dict(os.environ)
    env.update({
        "EASYCHAT_DATA_DIR": str(tmp_path / "data"),
        "EASYCHAT_JWT_SECRET": "r" * 64,
        "EASYCHAT_ENCRYPTION_SECRET": "e" * 64,
        "EASYCHAT_HERMES_ENABLED": "false",
    })
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.server:app",
         "--host", "127.0.0.1", "--port", str(port), "--workers", "1"],
        cwd=Path(__file__).resolve().parents[2], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/readyz", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            pytest.fail("应用未在 30s 内就绪")

        rss_mib = psutil.Process(process.pid).memory_info().rss / (1024 * 1024)
        assert rss_mib < RSS_LIMIT_MIB, f"RSS {rss_mib:.1f} MiB 超过目标 {RSS_LIMIT_MIB} MiB"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
