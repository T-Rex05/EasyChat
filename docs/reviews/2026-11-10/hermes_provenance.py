"""P3-1 内核来源记录:AgentForge HEAD ↔ EasyChat 基线复制 ↔ EasyChat 后续补丁 三层比对。

用法: python docs/reviews/2026-11-10/hermes_provenance.py [输出json路径]
只读比对 git 对象(不触碰 AgentForge 工作区文件内容,不读取业务数据)。
"""
import hashlib, json, subprocess, sys
from pathlib import Path

EASY = Path(r"E:\PythonCode\EasyChat")
FORGE = Path(r"E:\PythonCode\AgentForge")
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else EASY / "docs/reviews/2026-11-10/hermes-provenance.json"

def ls_tree(repo: Path, rev: str, prefix: str) -> dict[str, str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", rev, "--", prefix],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    m = {}
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        _mode, _type, blob = meta.split()
        m[path.removeprefix("backend/hermes/")] = blob
    return m

forge_head = ls_tree(FORGE, "23fdb99", "backend/hermes")
base = ls_tree(EASY, "1d41c2a", "backend/hermes")
head = ls_tree(EASY, "HEAD", "backend/hermes")

copy_vs_forge = sorted(k for k in base if k not in forge_head or forge_head[k] != base[k])
forged_only = sorted(k for k in forge_head if k not in base)
easychat_patches = sorted(k for k in head if k in base and base[k] != head[k])
removed = sorted(k for k in base if k not in head)
added = sorted(k for k in head if k not in base)

record = {
    "generated_utc": "2026-11-10",
    "layers": {
        "agentforge_head": {"repo": str(FORGE), "commit": "23fdb99",
                            "note": "AgentForge 工作区在复制时含未提交修改(实测 git status 有 backend/hermes/*.py dirty),故基线不等同于该 commit"},
        "easychat_import": {"commit": "1d41c2a", "files": len(base)},
        "easychat_head": {"branch": "feature/permission-remediation",
                          "commit": subprocess.run(["git", "-C", str(EASY), "rev-parse", "HEAD"],
                                                    capture_output=True, text=True).stdout.strip(),
                          "files": len(head)},
    },
    "counts": {
        "kernel_files_at_head": len(head),
        "copy_differs_from_forge_head": len(copy_vs_forge),
        "in_forge_not_in_copy": len(forged_only),
        "easychat_product_patches": len(easychat_patches),
        "removed_since_import": len(removed),
        "added_since_import": len(added),
    },
    "copy_differs_from_forge_head": copy_vs_forge,
    "in_forge_not_in_copy": forged_only,
    "easychat_product_patches": easychat_patches,
    "removed_since_import": removed,
    "added_since_import": added,
    "tree_hash": {
        "forge_head_backend_hermes": hashlib.sha256(
            "\n".join(f"{k}:{forge_head[k]}" for k in sorted(forge_head)).encode()).hexdigest(),
        "easychat_head_backend_hermes": hashlib.sha256(
            "\n".join(f"{k}:{head[k]}" for k in sorted(head)).encode()).hexdigest(),
    },
    "upstream_commit_confirmed": False,
    "upstream_note": "无法把基线绑定到 AgentForge 单一 commit(复制自脏工作区);本地源码树本身作为重建依据(计划 §0.3 允许的口径)",
}
OUT.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"written: {OUT}")
print(json.dumps(record["counts"], ensure_ascii=False, indent=2))
