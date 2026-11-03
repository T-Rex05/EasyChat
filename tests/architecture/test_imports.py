"""架构机器验证（架构 §12.10）：AST 检查禁用 import、模块私有跨引用、路由SQL与循环依赖。

规则严格适用于新目录（backend/shared|platform|modules|runtime|integrations 与
backend/app.py、backend/bootstrap.py）。存量旧代码（controller/service/db 等）
按任务逐步迁出，豁免名单固定为具体路径并附原因；新增路径不允许加入无说明的
豁免，每迁出一项从名单删除。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"

# 严格目录（相对 backend/）：新架构代码，规则全量适用
STRICT_DIRS = ("shared", "platform", "modules", "runtime", "integrations")
STRICT_FILES = ("app.py", "bootstrap.py")

# 唯一允许 import backend.hermes 的位置（Adapter 层）
HERMES_ADAPTER_DIRS = ("runtime/hermes",)

# 禁止进入业务层的旧基础设施依赖（架构 §12.10、R02/R03）
FORBIDDEN_TOP_MODULES = frozenset(
    {"pymysql", "redis", "dbutils", "neo4j", "pymilvus", "chromadb", "graphrag"}
)

# ---- 存量豁免名单（具体路径 + 原因；随迁移逐项删除） --------------------------
# 旧代码直接 import 禁用基础设施的文件（Task 15 移除对应模块后此名单清空）
LEGACY_FORBIDDEN_IMPORTS: dict[str, str] = {
    "db/connection_pool.py": "旧MySQL连接池；Task 15 删除",
    "db/schema.py": "旧MySQL schema入口；Task 15 删除",
    "tools/tools_decorator.py": "引用backend.rag；R03 移除",
}

# 旧代码绕过 runtime 直接 import backend.hermes 的文件（迁移后名单清空）
LEGACY_HERMES_IMPORTS: tuple[str, ...] = (
    "context/task_state.py",
    "context/strategies/fact_anchor.py",
    "service/cron/cron_service.py",
    "service/delegation/context_enrichment.py",
    "tools/code_executor.py",
    "tools/kg_tools.py",
    "tools/tools_decorator.py",
    "utils/traced_llm.py",
)

# 旧目录整体：仅受“路由不得直接 import pymysql/redis”约束，其余规则待迁移
LEGACY_DIRS_EXEMPT = (
    "agents", "config", "context", "db", "graphrag", "hooks",
    "infrastructure", "memory", "observer", "permission", "rag", "service",
    "templates", "tools", "utils", "wechat",
)
LEGACY_FILES_EXEMPT = ("build_info.py",)


def _iter_strict_py_files():
    yield BACKEND / "app.py"
    yield BACKEND / "bootstrap.py"
    for d in STRICT_DIRS:
        base = BACKEND / d
        if not base.exists():
            continue
        yield from base.rglob("*.py")


def _iter_all_backend_py_files():
    for p in BACKEND.rglob("*.py"):
        if "__pycache__" in p.parts or p.name.startswith("."):
            continue
        rel_parts = p.relative_to(BACKEND).parts
        if rel_parts[0] == "hermes":
            # 内嵌Hermes第三方代码不扫描（可选适配器不要求无字面引用）
            continue
        yield p


def _imports_of(tree: ast.AST) -> list[tuple[str, int]]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append((node.module, node.lineno))
    return out


def _rel(p: Path) -> str:
    return p.relative_to(BACKEND).as_posix()


def _parse(p: Path) -> ast.AST:
    # utf-8-sig 兼容个别带 BOM 的存量文件
    return ast.parse(p.read_text(encoding="utf-8-sig"))


# ---- 规则1：严格目录禁止旧基础设施依赖 ---------------------------------------


def test_strict_dirs_forbid_legacy_infra():
    violations = []
    for p in _iter_strict_py_files():
        tree = _parse(p)
        for mod, lineno in _imports_of(tree):
            top = mod.split(".")[0]
            if top in FORBIDDEN_TOP_MODULES:
                violations.append(f"{_rel(p)}:{lineno} imports {mod}")
            if mod.split(".")[0] == "backend" and mod.split(".")[1:2] == ["rag"]:
                violations.append(f"{_rel(p)}:{lineno} imports {mod}")
    assert not violations, "严格目录出现禁用依赖:\n" + "\n".join(violations)


def test_strict_dirs_confine_hermes_imports():
    violations = []
    for p in _iter_strict_py_files():
        rel = _rel(p)
        if any(rel.startswith(d) for d in HERMES_ADAPTER_DIRS):
            continue
        tree = _parse(p)
        for mod, lineno in _imports_of(tree):
            if mod == "backend.hermes" or mod.startswith("backend.hermes."):
                violations.append(f"{rel}:{lineno} imports {mod}")
    assert not violations, "业务/平台代码绕过runtime直接引用Hermes内部:\n" + "\n".join(violations)


# ---- 规则2：模块私有跨引用（只能导入 api.py / contracts.py） -----------------


def test_module_privacy_cross_imports():
    """modules/<X> 不得引用 modules/<Y> 的私有实现（repository/内部函数）。

    跨模块只允许 `backend.modules.<Y>.api` 或 `backend.modules.<Y>.contracts`。
    shared/platform/runtime 属公共层，不受此规则限制。
    """
    violations = []
    modules_base = BACKEND / "modules"
    if not modules_base.exists():
        return
    for p in modules_base.rglob("*.py"):
        owner = p.relative_to(modules_base).parts[0]
        if owner == "__pycache__":
            continue
        tree = _parse(p)
        for mod, lineno in _imports_of(tree):
            parts = mod.split(".")
            if len(parts) >= 3 and parts[0] == "backend" and parts[1] == "modules":
                target = parts[2]
                if target == owner:
                    continue
                allowed = {"api", "contracts"}
                sub = parts[3] if len(parts) > 3 else ""
                if sub not in allowed:
                    violations.append(
                        f"modules/{owner}/{p.name}:{lineno} 引用 modules/{target}/{sub or '<module>'}（只允许 api/contracts）"
                    )
    assert not violations, "模块私有跨引用:\n" + "\n".join(violations)


# ---- 规则3：路由不得执行SQL / 直接依赖数据库驱动 ------------------------------


def test_routes_have_no_sql():
    violations = []
    modules_base = BACKEND / "modules"
    if modules_base.exists():
        for p in modules_base.glob("*/routes.py"):
            tree = _parse(p)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name.split(".")[0] in {"sqlite3", "pymysql", "redis"}:
                            violations.append(f"modules/{p.parent.name}/routes.py:{node.lineno} imports {a.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in {"sqlite3", "pymysql", "redis"}:
                        violations.append(f"modules/{p.parent.name}/routes.py:{node.lineno} imports {node.module}")
    assert not violations


def test_route_files_do_not_import_db_drivers_anywhere():
    """全部路由文件（含旧controller）不得直接 import pymysql/redis（架构 §12.10）。"""
    violations = []
    for p in _iter_all_backend_py_files():
        rel = _rel(p)
        if rel.startswith(LEGACY_DIRS_EXEMPT) or rel in LEGACY_FILES_EXEMPT:
            # 旧目录里只有真正的路由文件仍需满足本规则
            if not rel.startswith("controller"):
                continue
        tree = _parse(p)
        for mod, lineno in _imports_of(tree):
            if mod.split(".")[0] in {"pymysql", "redis"}:
                violations.append(f"{rel}:{lineno} imports {mod}")
    assert not violations, "路由/控制器直接依赖数据库驱动:\n" + "\n".join(violations)


# ---- 规则4：存量名单核对（名单必须与实际一致，防止只加不删） ------------------


def test_legacy_forbidden_import_list_matches_reality():
    """豁免名单里的每个路径必须确实存在该违规；现实中出现但未登记的必须失败。"""
    actual = {}
    for p in BACKEND.rglob("*.py"):
        rel = _rel(p)
        if rel.startswith("hermes/") or "/hermes/" in rel:
            continue
        if rel.startswith(STRICT_DIRS) or rel in STRICT_FILES:
            continue  # 严格目录已有专门规则，不进豁免名单
        tree = _parse(p)
        found = set()
        for mod, _lineno in _imports_of(tree):
            top = mod.split(".")[0]
            if top in FORBIDDEN_TOP_MODULES or mod.startswith("backend.rag"):
                found.add(top if not mod.startswith("backend.rag") else "backend.rag")
        if found:
            actual[rel] = found
    listed = set(LEGACY_FORBIDDEN_IMPORTS)
    unlisted = set(actual) - listed
    stale = listed - set(actual)
    assert not unlisted, f"未登记的存量违规（禁止静默新增）: {sorted(unlisted)}"
    assert not stale, f"豁免名单已过时（文件已不含违规，请从名单删除）: {sorted(stale)}"


def test_legacy_hermes_import_list_matches_reality():
    actual = []
    for p in BACKEND.rglob("*.py"):
        rel = _rel(p)
        if rel.startswith("hermes/") or "/hermes/" in rel:
            continue
        if rel.startswith(HERMES_ADAPTER_DIRS):
            continue
        text = p.read_text(encoding="utf-8-sig")
        if re.search(r"(?:from|import)\s+backend\.hermes", text):
            actual.append(rel)
    listed = set(LEGACY_HERMES_IMPORTS)
    unlisted = set(actual) - listed
    stale = listed - set(actual)
    assert not unlisted, f"未登记的 backend.hermes 直接引用: {sorted(unlisted)}"
    assert not stale, f"Hermes豁免名单已过时: {sorted(stale)}"


# ---- 规则5：严格目录 import 图无环 -------------------------------------------


def test_no_circular_imports_in_strict_dirs():
    """以包粒度建 import 图（backend.shared / backend.modules.assistant 等），检测环。"""
    graph: dict[str, set[str]] = {}
    for p in _iter_strict_py_files():
        # 文件级图：以模块文件路径做节点
        node = p.relative_to(BACKEND).as_posix()
        tree = _parse(p)
        deps = set()
        for mod, _lineno in _imports_of(tree):
            if not mod.startswith("backend."):
                continue
            mod_path = mod.replace(".", "/")
            for cand in (mod_path + ".py", mod_path + "/__init__.py"):
                if (BACKEND / cand).exists() and _in_strict_scope(cand):
                    deps.add(cand)
            # `from backend.x.y import Z` 时 Z 可能是 x/y.py 里的类——父模块是依赖
            parent = mod_path.rsplit("/", 1)[0] + ".py"
            if "/" in mod_path and (BACKEND / parent).exists() and _in_strict_scope(parent):
                deps.add(parent)
        graph[node] = deps

    # Tarjan/Kahn 检测环
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    cycles = []

    def dfs(n: str, stack: list[str]) -> None:
        color[n] = GRAY
        stack.append(n)
        for d in graph.get(n, ()):
            if d not in color:
                continue
            if color[d] == GRAY:
                cycles.append(" -> ".join(stack[stack.index(d):] + [d]))
            elif color[d] == WHITE:
                dfs(d, stack)
        stack.pop()
        color[n] = BLACK

    for n in graph:
        if color[n] == WHITE:
            dfs(n, [])
    assert not cycles, "严格目录存在循环import:\n" + "\n".join(cycles)


def _in_strict_scope(rel_path: str) -> bool:
    top = rel_path.split("/")[0]
    return top in STRICT_DIRS or rel_path in STRICT_FILES
