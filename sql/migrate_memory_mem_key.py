"""迁移：给图谱 Memory 节点补上 `mem_key`（= "{layer}:{id}"），并补建被吞掉的同号节点。

背景：Memory 节点身份原本只有 mem_id，而 memory_episodic / memory_semantic 的 id
各自从 1 自增（实测 218 条 semantic 全部与 episodic 重号），于是两条不同记忆
共用一个节点，后写的覆盖前一条。

本脚本：
  1. 对每个缺 mem_key 的 Memory 节点，用**内容比对**判定它属于哪一层（episodic/semantic），
     写成 mem_key / layer（判定不出来 → legacy）。
  2. 对 MySQL 里存在、但图谱里**没有对应 mem_key 节点**的记忆，补建节点
     （内容/重要性/分类/归属都从 MySQL 取，密文先解密）。
  3. 复核：每个 MySQL 记忆都有且仅有一个节点；不再有缺 mem_key 的 Memory 节点。

用法:
    python _migrate_memkey.py            # dry-run
    python _migrate_memkey.py --apply
"""
import io
import sys
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from backend.infrastructure.neo4j_client import get_neo4j_client  # noqa: E402
from backend.db.schema import get_conn  # noqa: E402
from backend.utils.crypto_utils import decrypt_memory_content  # noqa: E402
from backend.memory.graph_memory import GraphMemory  # noqa: E402

APPLY = "--apply" in sys.argv
c = get_neo4j_client()
conn = get_conn()


def norm(s):
    return " ".join(str(s or "").split()).strip()


def plain(raw):
    s = str(raw or "")
    if s.startswith("ENC:"):
        return norm(decrypt_memory_content(s))
    return norm(s)


try:
    # ── MySQL 侧全量记忆 ──
    # ⚠️ **不过滤 deleted_at**：图谱里的 Memory 节点是当时创建的镜像，而库里
    # 绝大多数记忆已在 2026-09-17 被软删（episodic 690→存活 1、semantic 218→存活 10）。
    # 判定层级必须用全量行，否则内容比对全部落空、只能退化成 legacy。
    rows = []
    for layer, table in (("episodic", "memory_episodic"), ("semantic", "memory_semantic")):
        for r in conn.execute(
            f"SELECT id, user_id, content, importance_score, memory_type, deleted_at FROM {table}"
        ).fetchall():
            rows.append({
                "layer": layer, "id": int(r["id"]), "uid": r["user_id"],
                "plain": plain(r["content"]),
                "raw": r["content"],
                "importance": float(r["importance_score"] or 0.5),
                "category": r["memory_type"] or "general",
                "key": f"{layer}:{int(r['id'])}",
                "deleted": r["deleted_at"] is not None,
            })
    alive = sum(1 for x in rows if not x["deleted"])
    print(f"MySQL: {len(rows)} 条记忆（其中存活 {alive} 条）")
    by_key = {x["key"]: x for x in rows}
    by_plain = {}
    for x in rows:
        if x["plain"]:
            by_plain.setdefault(x["plain"], []).append(x)
    print(f"MySQL: {len(rows)} 条记忆（episodic+semantic）")

    # ── 现有图谱 Memory 节点 ──
    nodes = c.run_query(
        "MATCH (m:Memory) RETURN elementId(m) AS eid, m.mem_id AS mid, m.mem_key AS key, "
        "m.user_id AS uid, m.content AS content"
    )
    print(f"Neo4j: {len(nodes)} 个 Memory 节点；其中缺 mem_key 的 = "
          f"{sum(1 for n in nodes if not n.get('key'))}")

    plan_setkey, plan_create, unresolved = [], [], []
    existing_keys = set()
    for n in nodes:
        if n.get("key"):
            existing_keys.add(n["key"])
            continue
        p = plain(n.get("content"))
        cands = by_plain.get(p, []) if p else []
        # 同内容可能多条：先用 owner 收窄（评测数据里有大量同内容不同用户的记忆）
        if len(cands) > 1 and n.get("uid") is not None:
            cands2 = [x for x in cands if x["uid"] == n["uid"]]
            if cands2:
                cands = cands2
        # 仍然多条 → 优先存活、再优先 episodic（多数记忆是 episodic；
        # 同用户同 id 同内容的两层记忆本就是重复，挑哪个都无害）
        if len(cands) > 1:
            alive_c = [x for x in cands if not x["deleted"]]
            if alive_c:
                cands = alive_c
        if len(cands) > 1:
            epi_c = [x for x in cands if x["layer"] == "episodic"]
            if epi_c:
                cands = epi_c
        if len(cands) == 1:
            plan_setkey.append({"eid": n["eid"], "key": cands[0]["key"],
                                "layer": cands[0]["layer"], "mid": n["mid"]})
            existing_keys.add(cands[0]["key"])
        else:
            # 判不出来 → 退回 legacy:<id>，至少保证键唯一且不与显式层级混
            if n.get("mid") is not None:
                lk = f"legacy:{int(n['mid'])}"
                plan_setkey.append({"eid": n["eid"], "key": lk, "layer": "legacy",
                                    "mid": n["mid"]})
                existing_keys.add(lk)
            unresolved.append({"eid": n["eid"], "mid": n.get("mid"),
                               "content": str(n.get("content"))[:60], "cands": len(cands)})

    # 需要补建的：**只补存活记忆**。
    # 不为已软删的记忆补节点 —— 那种节点本来就该被清掉，不是"被吞掉"。
    for x in rows:
        if not x["deleted"] and x["key"] not in existing_keys:
            plan_create.append(x)

    print(f"\n=== 计划 ===")
    print(f"  写 mem_key: {len(plan_setkey)} 个  按层级分布 "
          f"{dict(Counter(p['layer'] for p in plan_setkey))}")
    print(f"  判定不出来（退化为 legacy）: {len(unresolved)}")
    for u in unresolved[:8]:
        print(f"      mid={u['mid']} cands={u['cands']} content={u['content']!r}")
    print(f"  补建节点: {len(plan_create)} 个  按层级分布 "
          f"{dict(Counter(p['layer'] for p in plan_create))}")

    if not APPLY:
        print("\n[dry-run] 未改动。")
        sys.exit(0)

    print("\n=== 执行 ===")
    for p in plan_setkey:
        c.run_query(
            "MATCH (m) WHERE elementId(m) = $eid SET m.mem_key = $key, m.layer = $layer",
            {"eid": p["eid"], "key": p["key"], "layer": p["layer"]},
        )
    print(f"  已写 mem_key: {len(plan_setkey)}")

    made = 0
    for x in plan_create:
        c.run_query(
            """MERGE (m:Memory {mem_key: $key})
               SET m.mem_id = $id, m.layer = $layer, m.content = $content,
                   m.importance = $imp, m.category = $cat""",
            {"key": x["key"], "id": x["id"], "layer": x["layer"],
             "content": x["plain"] or "", "imp": x["importance"], "cat": x["category"]},
        )
        if x["uid"] is not None:
            c.run_query(
                """MATCH (m:Memory {mem_key: $key})
                   MERGE (u:User {user_id: $uid}) ON CREATE SET u.created_at = datetime()
                   MERGE (m)-[r:BELONGS_TO_USER]->(u)
                   SET m.user_id = $uid, r.user_id = $uid""",
                {"key": x["key"], "uid": x["uid"]},
            )
        made += 1
    print(f"  已补建节点: {made}")

    print("\n=== 复核 ===")
    r = c.run_query("MATCH (m:Memory) WHERE m.mem_key IS NULL RETURN count(m) AS n")
    print("   缺 mem_key 的 Memory 节点 =", r[0]["n"])
    r = c.run_query("MATCH (m:Memory) RETURN count(m) AS n")
    print("   Memory 节点总数 =", r[0]["n"])
    keys = c.run_query("MATCH (m:Memory) WHERE m.mem_key IS NOT NULL RETURN count(DISTINCT m.mem_key) AS n")
    print("   distinct mem_key =", keys[0]["n"])
    # 每条 MySQL 记忆都能对上节点
    have = {x["key"] for x in c.run_query("MATCH (m:Memory) WHERE m.mem_key IS NOT NULL RETURN m.mem_key AS k")}
    miss = [x["key"] for x in rows if x["key"] not in have]
    print(f"   MySQL 有但图谱仍缺的记忆 = {len(miss)} {miss[:5]}")
    # 重号的成对记忆现在应该各有节点
    pairs = [(k, f"semantic:{k.split(':')[1]}") for k in by_key if k.startswith("episodic:")
             and f"semantic:{k.split(':')[1]}" in by_key]
    both = [1 for a, b in pairs if a in have and b in have]
    print(f"   重号对(episodic:x 与 semantic:x 都存在) = {len(pairs)} 对，"
          f"其中两端都有节点的 = {len(both)}")
finally:
    conn.close()
