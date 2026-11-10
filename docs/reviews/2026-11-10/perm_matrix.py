"""P2 权限入口矩阵:逐键映射 service / HTTP routes / 微信与工具 / 前端 消费点。

静态扫描本轮实测;消费点=出现该权限键字符串或经 requires_permission 装饰器引用。
用法: python docs/reviews/2026-11-10/perm_matrix.py
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, ".")
from backend.modules.access.contracts import ALL_PERMISSION_KEYS

ROOT = Path(".")
KEYS = sorted(ALL_PERMISSION_KEYS)
KEY_RE = re.compile("[\"'](" + "|".join(re.escape(k) for k in KEYS) + ")[\"']")

BUCKET_DEFS = [
    ("http-routes", lambda p: p.startswith("backend/modules/") and p.endswith("/routes.py")),
    ("service", lambda p: p.startswith("backend/modules/") and not p.endswith("/routes.py") and "/migrations/" not in p),
    ("backend-other", lambda p: p.startswith("backend/") and not p.startswith("backend/modules/")),
    ("wechat/channels", lambda p: p.startswith("backend/modules/channels/")),
    ("model-tools", lambda p: p.startswith("backend/tools/")),
    ("frontend", lambda p: p.startswith("agent_frontend/src/")),
    ("tests", lambda p: p.startswith("tests/")),
]
# channels 归入自身桶优先:调整判定顺序
def classify(rel: str) -> str:
    if rel.startswith("tests/"):
        return "tests"
    if rel.startswith("agent_frontend/src/"):
        return "frontend"
    if rel.startswith("backend/tools/"):
        return "model-tools"
    if rel.startswith("backend/modules/channels/"):
        return "wechat/channels"
    if rel.startswith("backend/modules/"):
        return "http-routes" if rel.endswith("/routes.py") else "service"
    if rel.startswith("backend/"):
        return "backend-other"
    return "other"

SCAN_DIRS = ["backend", "agent_frontend/src", "tests"]
EXTS = {".py", ".vue", ".ts", ".mjs"}

matrix = {k: defaultdict(set) for k in KEYS}
for d in SCAN_DIRS:
    base = ROOT / d
    if not base.is_dir():
        continue
    for path in base.rglob("*"):
        if path.suffix not in EXTS or not path.is_file():
            continue
        rel = path.as_posix()
        if "/__pycache__/" in rel or "/node_modules/" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            for m in KEY_RE.finditer(line):
                key = m.group(1)
                matrix[key][classify(rel)].add(rel)

hdr = ["key", "service", "http-routes", "wechat", "tools", "frontend", "tests", "backend-other"]
print("| 权限 | service | routes | channels | tools | 前端 | tests | 其他后端 |")
print("|---|---|---|---|---|---|---|---|")
for key in KEYS:
    b = matrix[key]
    def cell(name):
        files = b.get(name, set())
        return str(len(files)) if files else "0"
    print(f"| {key} | {cell('service')} | {cell('http-routes')} | {cell('wechat/channels')} | {cell('model-tools')} | {cell('frontend')} | {cell('tests')} | {cell('backend-other')} |")

print()
zero_test = [k for k in KEYS if not matrix[k].get("tests")]
zero_svc = [k for k in KEYS if not matrix[k].get("service")]
print("无测试消费点:", zero_test or "无")
print("无 service 消费点:", zero_svc or "无")
