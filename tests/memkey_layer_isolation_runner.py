"""验证"层级维度"修复：同一个 mem_id 在不同层级 = 两个独立节点，互不覆盖、互不串门。

对照：旧实现 `MERGE (m:Memory {mem_id: $id})` 会把它们合并成一个节点。
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from backend.infrastructure.neo4j_client import get_neo4j_client  # noqa: E402
from backend.memory.graph_memory import get_graph_memory  # noqa: E402

UID_A, UID_B = 26, 29
MID = 999999          # 两层共用同一个 mem_id
MID_A2, MID_B2 = 999998, 999997
checks, failures = 0, []


def check(name, cond, extra=""):
    global checks
    checks += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


c = get_neo4j_client()
gm = get_graph_memory()

# 先确认迁移后所有 Memory 节点都带 mem_key/layer
r = c.run_query("MATCH (m:Memory) RETURN count(m) AS n, "
                "sum(CASE WHEN m.mem_key IS NULL THEN 1 ELSE 0 END) AS nokey, "
                "sum(CASE WHEN m.layer IS NULL THEN 1 ELSE 0 END) AS nolayer")
print(f"迁移后：{r[0]['n']} 个 Memory 节点，缺 mem_key {r[0]['nokey']}，缺 layer {r[0]['nolayer']}")
check("所有 Memory 节点都有 mem_key", r[0]["nokey"] == 0)
check("所有 Memory 节点都有 layer", r[0]["nolayer"] == 0)

print("\n=== 构造：A 的 episodic#999999 与 B 的 semantic#999999（故意同号）===")
gm._upsert_memory_node(MID, "A的内容-episodic", 0.8, "preference", UID_A, "episodic")
gm._upsert_memory_node(MID, "B的内容-semantic", 0.8, "fact", UID_B, "semantic")
gm._upsert_memory_node(MID_A2, "A的第二条", 0.5, "general", UID_A, "episodic")
gm._upsert_memory_node(MID_B2, "B的第二条", 0.5, "general", UID_B, "semantic")

n = c.run_query("MATCH (m:Memory) WHERE m.mem_id = $id RETURN m.mem_key AS k, m.content AS c, m.user_id AS u",
                {"id": MID})
print(f"   mem_id={MID} 对应的节点数 = {len(n)}: {[(x['k'], x['c'], x['u']) for x in n]}")
check("同号记忆是两个独立节点（不再被合并）", len(n) == 2, f"got {len(n)}")
check("A 的节点内容/归属正确",
      any(x["k"] == "episodic:999999" and x["c"] == "A的内容-episodic" and x["u"] == UID_A for x in n))
check("B 的节点内容/归属正确",
      any(x["k"] == "semantic:999999" and x["c"] == "B的内容-semantic" and x["u"] == UID_B for x in n))

print("\n=== 邻接不应串门：A 的链只连到 A 的第二条 ===")
gm._add_memory_edge(MID, MID_A2, gm.EDGE_FOLLOWS, 1.0, from_layer="episodic", to_layer="episodic")
gm._add_memory_edge(MID, MID_B2, gm.EDGE_FOLLOWS, 1.0, from_layer="semantic", to_layer="semantic")
r = c.run_query(
    """MATCH (a:Memory) WHERE a.mem_key = 'episodic:999999'
       MATCH (a)-[rel:FOLLOWS]->(b:Memory)
       RETURN b.mem_key AS k, rel.user_id AS ru"""
)
print(f"   A(episodic:999999) 的 FOLLOWS → {[(x['k'], x['ru']) for x in r]}")
check("A 的边只连 episodic 那条", len(r) == 1 and r[0]["k"] == "episodic:999998")
check("边上带了 user_id（否则对所有用户不可见）", r and r[0]["ru"] == UID_A)

rel_a = gm.find_related(MID, user_id=UID_A, layer="episodic")
rel_b = gm.find_related(MID, user_id=UID_B, layer="semantic")
print(f"   find_related(A, episodic) = {rel_a}   find_related(B, semantic) = {rel_b}")
check("按层级扩展：A 只拿到自己的链", MID_A2 in rel_a and MID_B2 not in rel_a, f"got {rel_a}")
check("按层级扩展：B 只拿到自己的链", MID_B2 in rel_b and MID_A2 not in rel_b, f"got {rel_b}")

print("\n=== 清理测试节点 ===")
for k in ("episodic:999999", "semantic:999999", "episodic:999998", "semantic:999997"):
    c.run_query("MATCH (m:Memory {mem_key: $k}) DETACH DELETE m", {"k": k})
r = c.run_query("MATCH (m:Memory) WHERE m.mem_key IN $ks RETURN count(m) AS n",
                {"ks": ["episodic:999999", "semantic:999999", "episodic:999998", "semantic:999997"]})
print(f"   剩余测试节点 = {r[0]['n']}")
check("测试节点已清理", r[0]["n"] == 0)

print(f"\n===== 结果: {checks - len(failures)}/{checks} 通过 =====")
for f in failures:
    print(f"   - {f}")
sys.exit(1 if failures else 0)
