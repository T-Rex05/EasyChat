"""移除依赖的机器验证（Task 15）：新装配路径不得引用已删业务/旧基础设施。"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
STRICT = ("app.py", "bootstrap.py")
STRICT_DIRS = ("modules", "platform", "runtime", "integrations", "shared")

FORBIDDEN = (
    "backend.rag", "backend.graphrag", "backend.service.kb", "backend.controller",
    "pymysql", "dbutils", "redis", "neo4j", "pymilvus", "chromadb",
)
REMOVED_ROUTE_PREFIXES = ("/api/kb", "/api/graph", "/api/paper", "/api/community", "/api/data-layers")


def _files():
    for name in STRICT:
        yield BACKEND / name
    for directory in STRICT_DIRS:
        yield from (BACKEND / directory).rglob("*.py")


def test_new_assembly_does_not_import_removed_modules():
    violations = []
    for path in _files():
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module]
            for module in modules:
                if any(module == bad or module.startswith(bad + ".") for bad in FORBIDDEN):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} imports {module}")
    assert not violations, "\n".join(violations)


def test_new_app_does_not_mount_removed_prefixes():
    from backend.app import create_app

    app = create_app()
    paths = set(app.openapi()["paths"])
    assert not [p for p in paths if p.startswith(REMOVED_ROUTE_PREFIXES)]
