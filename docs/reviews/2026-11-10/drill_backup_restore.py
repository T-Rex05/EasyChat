"""P1 备份/恢复演练:真实数据备份 → 校验 → 隔离恢复 → 可读性核查。不修改任何生产数据。"""
import hashlib, sqlite3, sys, tempfile
from pathlib import Path

sys.path.insert(0, ".")
from backend.platform.backup import create_backup, restore_backup, verify_backup

DB = Path("data/app.db")
FILES = Path("data")
tmp = Path(tempfile.mkdtemp(prefix="ec-drill-"))
dest = tmp / "backup-1"

info = create_backup(db_path=DB, files_root=FILES, dest=dest)
print(f"backup ok: path={info.path} db_sha256={info.db_sha256[:16]}… files={info.files} bytes={info.bytes}")

v = verify_backup(dest)
print(f"verify: ok={v.ok} problems={v.problems} db_rows(stored_files)={v.db_rows} files={v.files}")
assert v.ok, "verify 失败"

# 隔离恢复到临时目录
restore_target_db = tmp / "restored" / "app.db"
restore_target_files = tmp / "restored" / "files"
r = restore_backup(dest, db_path=restore_target_db, files_root=restore_target_files)
print(f"restore: files_restored={r['files_restored']} preserved={r['preserved']}")

# 恢复后可读性:核心表逐个计数
con = sqlite3.connect(f"file:{restore_target_db}?mode=ro", uri=True)
con.execute("PRAGMA query_only=1")
tables = ["users", "roles", "superagent_tasks", "stored_files", "permissions", "runs", "sessions"]
counts = {}
for t in tables:
    try:
        counts[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    except sqlite3.Error as e:
        counts[t] = f"ERR:{e}"
con.close()
print("restored-db readability:", counts)

# 与源库行数对照
src = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
mismatch = []
for t, c in counts.items():
    try:
        sc = src.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        if sc != c:
            mismatch.append((t, sc, c))
    except sqlite3.Error:
        pass
src.close()
print("row-count mismatches vs source:", mismatch or "无")
print("DRILL_OK" if not mismatch else "DRILL_MISMATCH")
