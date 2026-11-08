"""DDGS 搜索桥：安装 ddgs 包后必须真正注册为 Hermes Provider。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from backend.integrations.search import _bing_search, ensure_ddgs_provider


def test_ensure_ddgs_provider_registers_hermes_provider(monkeypatch) -> None:
    if importlib.util.find_spec("ddgs") is None:
        pytest.skip("ddgs not installed")
    hermes_root = Path(__file__).resolve().parents[2] / "backend" / "hermes"
    monkeypatch.syspath_prepend(str(hermes_root))
    from agent import web_search_registry

    assert ensure_ddgs_provider() is True
    provider = web_search_registry.get_provider("ddgs")
    assert provider is not None
    assert provider.supports_search() is True
    assert provider.is_available() is True


def test_bing_html_parser_returns_normalized_results(monkeypatch) -> None:
    class Response:
        url = "https://www.bing.com/search?q=test"
        text = """
        <html><body>
          <li class="b_algo">
            <h2><a href="https://example.com/a">Example A</a></h2>
            <p>First result</p>
          </li>
          <li class="b_algo">
            <h2><a href="https://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9i">Example B</a></h2>
            <p>Second result</p>
          </li>
        </body></html>
        """

        def raise_for_status(self):
            return None

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: Response())
    results = _bing_search("test", 2)
    assert [item["title"] for item in results] == ["Example A", "Example B"]
    assert results[0]["url"] == "https://example.com/a"
    assert results[1]["url"] == "https://example.com/b"
    assert results[0]["position"] == 1
