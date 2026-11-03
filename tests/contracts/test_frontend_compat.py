"""前端移除契约（Task 15）：不得再引用已删 KB/图谱/论文/社区页面或 API。"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "agent_frontend"
SRC = FRONTEND / "src"
REMOVED_API = ("/api/kb", "/api/graph", "/api/paper", "/api/community", "/api/memories",
               "/api/cron-jobs", "/api/traces", "/api/data-layers", "/api/admin/pool",
               "/api/data/sessions")
REMOVED_ROUTES = ("/knowledge", "/kb-eval", "/graph", "/kg-review", "/communities",
                  "/pool-review", "/paper-reproduction", "/memory-dashboard")
REMOVED_VIEW_FILES = ("KnowledgeView.vue", "KnowledgeEvalView.vue", "GraphView.vue",
                      "KgReviewView.vue", "CommunityView.vue", "PoolReviewView.vue",
                      "MemoryItemsView.vue", "MemoryDashboardView.vue", "SkillView.vue",
                      "TraceView.vue", "AuditLogView.vue")
REMOVED_PACKAGES = ("@vue-flow/core", "graphology", "sigma", "vis-network")


def test_frontend_sources_do_not_call_removed_apis():
    violations = []
    for path in SRC.rglob("*"):
        if path.suffix not in (".ts", ".vue", ".js"):
            continue
        text = path.read_text(encoding="utf-8")
        for prefix in REMOVED_API:
            if prefix in text:
                violations.append(f"{path.relative_to(REPO_ROOT)} 引用 {prefix}")
    assert not violations, "\n".join(violations)


def test_router_and_views_removed():
    router_text = (SRC / "router" / "index.ts").read_text(encoding="utf-8")
    for route in REMOVED_ROUTES:
        assert f"'{route}'" not in router_text, route
    for name in REMOVED_VIEW_FILES:
        assert not (SRC / "views" / name).exists(), name
    assert not (SRC / "views" / "paper-reproduction").exists()
    assert not (SRC / "api" / "memoryItems.ts").exists()
    assert not (SRC / "api" / "memory.ts").exists()
    assert not (SRC / "api" / "skills.ts").exists()
    assert not (SRC / "api" / "cron.ts").exists()
    assert not (SRC / "api" / "trace.ts").exists()
    for name in ("DepartmentPanel.vue", "HostWhitelistPanel.vue", "CommandBlacklistPanel.vue"):
        assert not (SRC / "views" / "admin" / name).exists(), name


def test_removed_graph_packages_gone():
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    deps = package.get("dependencies", {})
    for name in REMOVED_PACKAGES:
        assert name not in deps, name
