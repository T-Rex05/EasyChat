"""End-to-end check: knowledge-graph department (data-layer) isolation.

⚠️ 这是**手动运行的集成脚本**，不是 pytest 用例（文件名刻意不含 `test_` 前缀，
   避免被 pytest 自动收集 —— 它需要真实的 MySQL(3308) + Neo4j(7687)）。

它会在库里创建临时夹具（部门层 / KB / 文档 / chunk / 图谱节点），以两个用户
（一个在部门内、一个在部门外）跑遍所有 KG 读路径，最后**按前缀清理并自检残留**。

同时包含一个**灵敏度对照**：把谓词换回旧版，断言上述检查确实会失败 ——
用来证明这套测试真的能发现问题，而不是恒真。

用法:
    python tests/kg_dept_isolation_runner.py
"""
import io
import sys
import time
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from backend.db.schema import get_conn  # noqa: E402
from backend.graphrag.kg_store import get_kg_store  # noqa: E402
from backend.graphrag.types import Entity, EntityType, Relation, RelationType  # noqa: E402
from backend.infrastructure.neo4j_client import get_neo4j_client  # noqa: E402
from backend.service.auth.data_layer_service import (  # noqa: E402
    get_user_layers, get_visible_document_ids,
)

TS = str(int(time.time()))
U_IN, U_OUT = 26, 29          # 26=eval_user2(将临时授予部门层)  29=eval_user3(仅全员)
L = None                      # 测试部门层 id
KB1 = KB2 = KB3 = None
DOC_A = DOC_B = DOC_C = None
E_A = f"kgtestA{TS}"
E_B = f"kgtestB{TS}"
E_C = f"kgtestC{TS}"
E_M = f"kgtestM{TS}"          # 记忆实体（无 source_document_id），归属 U_OUT
rel_ids = []
failures = []
checks = 0


def check(name, cond, extra=""):
    global checks
    checks += 1
    if cond:
        print(f"  [PASS] {name}")
    else:
        print(f"  [FAIL] {name}  {extra}")
        failures.append(name)


def cols(table):
    c = get_conn()
    try:
        return [r["Field"] for r in c.execute(f"SHOW COLUMNS FROM {table}").fetchall()]
    finally:
        c.close()


def ins(table, data):
    """Insert only columns that exist. Returns lastrowid."""
    existing = set(cols(table))
    use = {k: v for k, v in data.items() if k in existing}
    c = get_conn()
    try:
        keys = ",".join(use)
        ph = ",".join(["%s"] * len(use))
        cur = c.execute(f"INSERT INTO {table} ({keys}) VALUES ({ph})", tuple(use.values()))
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def setup():
    global L, KB1, KB2, KB3, DOC_A, DOC_B, DOC_C
    # 1. 测试部门层
    L = ins("data_layers", {"name": f"_kg_dept_test_{TS}", "description": "temporary",
                            "sort_order": 999, "is_system": 0})
    # 2. 用户 26 临时获得该层（并保留"全员"0）
    ins("user_data_layers", {"user_id": U_IN, "layer_id": 0})
    ins("user_data_layers", {"user_id": U_IN, "layer_id": L})
    # 3. 三个 KB：KB1 挂到 L；KB2/KB3 不挂（全员）
    KB1 = ins("kb_knowledge_base", {"kb_name": f"_kgtest_kb1_{TS}", "kb_type": "normal",
                                    "description": "t", "user_id": 1, "is_enabled": 1, "is_system": 0})
    KB2 = ins("kb_knowledge_base", {"kb_name": f"_kgtest_kb2_{TS}", "kb_type": "normal",
                                    "description": "t", "user_id": 1, "is_enabled": 1, "is_system": 0})
    KB3 = ins("kb_knowledge_base", {"kb_name": f"_kgtest_kb3_{TS}", "kb_type": "normal",
                                    "description": "t", "user_id": 1, "is_enabled": 1, "is_system": 0})
    ins("kb_data_layers", {"kb_id": KB1, "layer_id": L})
    # 4. 三个文档
    DOC_A = ins("kb_documents", {"kb_id": KB1, "user_id": 1, "original_name": f"a_{TS}.md",
                                 "stored_name": f"a_{TS}.md", "ext": ".md", "size_bytes": 1,
                                 "sha256": TS, "status": "parsed", "vectorized": 0})
    DOC_B = ins("kb_documents", {"kb_id": KB2, "user_id": 1, "original_name": f"b_{TS}.md",
                                 "stored_name": f"b_{TS}.md", "ext": ".md", "size_bytes": 1,
                                 "sha256": TS, "status": "parsed", "vectorized": 0})
    DOC_C = ins("kb_documents", {"kb_id": KB3, "user_id": 1, "original_name": f"c_{TS}.md",
                                 "stored_name": f"c_{TS}.md", "ext": ".md", "size_bytes": 1,
                                 "sha256": TS, "status": "parsed", "vectorized": 0})
    # 5. chunk：A 继承 KB 层（scope NULL）；B 显式 L；C 全员（scope NULL 且 KB 无层）
    ins("kb_chunks", {"document_id": DOC_A, "kb_id": KB1, "chunk_index": 0,
                      "content": f"chunkA {TS}", "kind": "base", "scope_layer_id": None})
    ins("kb_chunks", {"document_id": DOC_B, "kb_id": KB2, "chunk_index": 0,
                      "content": f"chunkB {TS}", "kind": "base", "scope_layer_id": L})
    ins("kb_chunks", {"document_id": DOC_C, "kb_id": KB3, "chunk_index": 0,
                      "content": f"chunkC {TS}", "kind": "base", "scope_layer_id": None})

    # 6. Neo4j 实体与关系
    ks = get_kg_store()
    ks.create_entity(Entity(id=E_A, name=f"部门实体A{TS}", entity_type=EntityType.OTHER,
                            description="restricted-by-kb-layer", source_document_id=DOC_A),
                     user_id=1)
    ks.create_entity(Entity(id=E_B, name=f"部门实体B{TS}", entity_type=EntityType.OTHER,
                            description="restricted-by-chunk-layer", source_document_id=DOC_B),
                     user_id=1)
    ks.create_entity(Entity(id=E_C, name=f"全员实体C{TS}", entity_type=EntityType.OTHER,
                            description="visible-to-all", source_document_id=DOC_C),
                     user_id=1)
    ks.create_entity(Entity(id=E_M, name=f"记忆实体M{TS}", entity_type=EntityType.OTHER,
                            description="memory-owned-by-U_OUT"), user_id=U_OUT)
    # C -> A -> M ：A 对 U_OUT 不可见，验证"中间节点"不会被带出来
    ks.create_relation(Relation(id=f"rel_ca_{TS}", source_id=E_C, target_id=E_A,
                                relation_type=RelationType.RELATED_TO,
                                description="c->a", source_document_id=DOC_C), user_id=1)
    ks.create_relation(Relation(id=f"rel_am_{TS}", source_id=E_A, target_id=E_M,
                                relation_type=RelationType.RELATED_TO,
                                description="a->m"), user_id=U_OUT)
    rel_ids.extend([f"rel_ca_{TS}", f"rel_am_{TS}"])


def teardown():
    """按**前缀**兜底清理，不依赖 setup 走到了哪一步；清完自检并打印残留数。

    ⚠️ 之前按捕获到的 id 清理，一旦某次运行中途异常就可能留下残留
    （实测发生过一次：Neo4j 剩 4 个节点、MySQL 剩 1 层 3 库 3 文档）。
    所以这里改成按前缀清理 + 用 consume() 确保写入提交 + 事后自检。
    """
    print("\n--- 清理测试数据 ---")
    # ── Neo4j：按 id 前缀 ──
    try:
        client = get_neo4j_client()
        if client and client.is_available():
            with client._get_session() as s:
                s.run(
                    "MATCH (n) WHERE n.id STARTS WITH $p DETACH DELETE n",
                    p="kgtest",
                ).consume()
            res = client.run_query(
                "MATCH (n) WHERE n.id STARTS WITH 'kgtest' RETURN count(n) as c"
            )
            print(f"   Neo4j: kgtest* 剩余节点 = {res[0]['c'] if res else '?'}")
    except Exception as e:
        print(f"   !! Neo4j 清理失败: {e}")

    # ── MySQL：按名字前缀（LIKE 含字面 % → 必须用原生 cursor，不能用 _MySQLAdapter）──
    try:
        from backend.db.connection_pool import get_pool_connection

        pc = get_pool_connection()
        cur = pc.cursor()
        try:
            def q(sql, args=None):
                cur.execute(sql, args)
                return cur.fetchall()

            kbs = [r["id"] for r in q(
                "SELECT id FROM kb_knowledge_base WHERE kb_name LIKE '\\_kgtest\\_%'")]
            docs = [r["id"] for r in q(
                "SELECT id FROM kb_documents WHERE original_name REGEXP '^[abc]_[0-9]+\\\\.md$'")]
            layers = [r["id"] for r in q(
                "SELECT id FROM data_layers WHERE name LIKE '\\_kg\\_dept\\_test\\_%'")]
            if docs:
                ph = ",".join(["%s"] * len(docs))
                cur.execute(f"DELETE FROM kb_chunks WHERE document_id IN ({ph})", tuple(docs))
                cur.execute(f"DELETE FROM kb_documents WHERE id IN ({ph})", tuple(docs))
            if kbs:
                ph = ",".join(["%s"] * len(kbs))
                cur.execute(f"DELETE FROM kb_data_layers WHERE kb_id IN ({ph})", tuple(kbs))
                cur.execute(f"DELETE FROM kb_knowledge_base WHERE id IN ({ph})", tuple(kbs))
            if layers:
                ph = ",".join(["%s"] * len(layers))
                cur.execute(f"DELETE FROM user_data_layers WHERE layer_id IN ({ph})", tuple(layers))
                cur.execute(f"DELETE FROM data_layers WHERE id IN ({ph})", tuple(layers))
            # 用户 26 恢复成"没有层级行"
            cur.execute("DELETE FROM user_data_layers WHERE user_id = %s", (U_IN,))
            pc.commit()

            left = sum([
                q("SELECT COUNT(*) n FROM kb_knowledge_base WHERE kb_name LIKE '\\_kgtest\\_%'")[0]["n"],
                q("SELECT COUNT(*) n FROM kb_documents WHERE original_name REGEXP '^[abc]_[0-9]+\\\\.md$'")[0]["n"],
                q("SELECT COUNT(*) n FROM data_layers WHERE name LIKE '\\_kg\\_dept\\_test\\_%'")[0]["n"],
                q("SELECT COUNT(*) n FROM user_data_layers WHERE user_id = %s", (U_IN,))[0]["n"],
            ])
            print(f"   MySQL: 测试残留（库+文档+层+用户授权）= {left}")
            print(f"   data_layers 现有 = {[(r['id'], r['name']) for r in q('SELECT id, name FROM data_layers ORDER BY id')]}")
        finally:
            cur.close()
            pc.close()
    except Exception as e:
        print(f"   !! MySQL 清理失败: {e}")


def names(items):
    """兼容三种返回形状：Entity 对象 / {"name":...} / {"entity": {...}|Entity}"""
    out = set()
    for it in items or []:
        if not it:
            continue
        inner = it
        if isinstance(it, dict):
            inner = it.get("entity") or it.get("related_entity") or it
        if isinstance(inner, dict):
            nm = inner.get("name")
        else:
            nm = getattr(inner, "name", None)
        if nm:
            out.add(nm)
    return out


def main():
    setup()
    print(f"fixtures: layer L={L} KB1={KB1} KB2={KB2} KB3={KB3} docs={DOC_A},{DOC_B},{DOC_C}")
    print(f"users: U_IN={U_IN} layers={sorted(get_user_layers(U_IN))}   "
          f"U_OUT={U_OUT} layers={sorted(get_user_layers(U_OUT))}")
    print(f"visible docs U_IN={sorted(get_visible_document_ids(U_IN))}")
    print(f"visible docs U_OUT={sorted(get_visible_document_ids(U_OUT))}")

    ks = get_kg_store()
    nA, nB, nC, nM = (f"部门实体A{TS}", f"部门实体B{TS}", f"全员实体C{TS}", f"记忆实体M{TS}")

    print("\n=== 1. search_entities（KB 实体按部门、记忆实体按用户）===")
    for uid, tag, want in ((U_IN, "U_IN", {nA, nB, nC}), (U_OUT, "U_OUT", {nC, nM})):
        got = set()
        for nm in (nA, nB, nC, nM):
            got |= names(ks.search_entities(nm, user_id=uid, limit=5))
        # search 是模糊匹配，逐个核对更准确
        res = {nm: bool(ks.search_entities(nm, user_id=uid, limit=5)) for nm in (nA, nB, nC, nM)}
        print(f"   {tag}: {res}")
        check(f"search A 可见性 {tag}", res[nA] == (uid == U_IN))
        check(f"search B 可见性 {tag}", res[nB] == (uid == U_IN))
        check(f"search C 双方可见 {tag}", res[nC] is True)
        check(f"search M 归属 {tag}", res[nM] == (uid == U_OUT))

    print("\n=== 2. get_entity ===")
    check("U_IN 能取到 A", ks.get_entity(E_A, user_id=U_IN) is not None)
    check("U_OUT 取不到 A", ks.get_entity(E_A, user_id=U_OUT) is None)
    check("U_OUT 能取到 M", ks.get_entity(E_M, user_id=U_OUT) is not None)
    check("U_IN 取不到 M", ks.get_entity(E_M, user_id=U_IN) is None)

    print("\n=== 3. count_entities / count_relations ===")
    c_in, c_out = ks.count_entities(U_IN), ks.count_entities(U_OUT)
    r_in, r_out = ks.count_relations(U_IN), ks.count_relations(U_OUT)
    print(f"   entities: U_IN={c_in} U_OUT={c_out} | relations: U_IN={r_in} U_OUT={r_out}")
    check("U_OUT 的实体数严格少于 U_IN", c_out < c_in, f"{c_out} vs {c_in}")

    print("\n=== 4. get_subgraph（深度2，验证中间节点不被带出）===")
    sg_in = ks.get_subgraph(E_C, depth=2, user_id=U_IN)
    sg_out = ks.get_subgraph(E_C, depth=2, user_id=U_OUT)
    ids_in = {e.id for e in sg_in.nodes}
    ids_out = {e.id for e in sg_out.nodes}
    print(f"   U_IN  nodes={sorted(ids_in)}")
    print(f"   U_OUT nodes={sorted(ids_out)}")
    check("U_IN 子图含 A", E_A in ids_in)
    check("U_OUT 子图不含 A（中间节点泄露）", E_A not in ids_out, f"got {ids_out}")
    check("U_OUT 不能经 A 抵达 M", E_M not in ids_out, f"got {ids_out}")
    check("U_OUT 子图仍含 C", E_C in ids_out)

    print("\n=== 5. find_paths_between（路径上所有节点/关系都要可见）===")
    p_in = ks.find_paths_between(E_C, E_A, max_hops=3, user_id=U_IN)
    p_out = ks.find_paths_between(E_C, E_A, max_hops=3, user_id=U_OUT)
    print(f"   C->A: U_IN={len(p_in)} 条  U_OUT={len(p_out)} 条")
    check("U_IN 能查到 C->A 路径", len(p_in) >= 1)
    check("U_OUT 查不到 C->A 路径", len(p_out) == 0)
    p_out_m = ks.find_paths_between(E_C, E_M, max_hops=3, user_id=U_OUT)
    check("U_OUT 查不到 C->(A)->M 路径（被不可见中间节点阻断）", len(p_out_m) == 0,
          f"got {len(p_out_m)}")

    print("\n=== 6. find_reachable_entities ===")
    rch_out = {e["id"] for e in ks.find_reachable_entities(E_C, user_id=U_OUT, max_hops=3)}
    rch_in = {e["id"] for e in ks.find_reachable_entities(E_C, user_id=U_IN, max_hops=3)}
    print(f"   U_IN={sorted(rch_in)}  U_OUT={sorted(rch_out)}")
    check("U_OUT 不可达 A", E_A not in rch_out)
    check("U_IN 可达 A", E_A in rch_in)

    print("\n=== 7. get_related_entities ===")
    rel_out = names(ks.get_related_entities(E_C, user_id=U_OUT, limit=20))
    rel_in = names(ks.get_related_entities(E_C, user_id=U_IN, limit=20))
    check("U_OUT 的邻居不含 A", nA not in rel_out, f"got {rel_out}")
    check("U_IN 的邻居含 A", nA in rel_in, f"got {rel_in}")

    print("\n=== 8. get_entity_timeline ===")
    tl_out = ks.get_entity_timeline(E_A, user_id=U_OUT)
    tl_in = ks.get_entity_timeline(E_A, user_id=U_IN)
    print(f"   A 的时间线: U_IN={len(tl_in)}  U_OUT={len(tl_out)}")
    check("U_OUT 看不到 A 的时间线", len(tl_out) == 0)

    print("\n=== 9. get_user_graph ===")
    # limit 必须足够大：库里有近 2000 个实体，limit=500 时返回的是任意 500 个，
    # 测试实体可能压根不在里面（这不是缺陷，是抽样）
    ug_out = {e.id for e in ks.get_user_graph(U_OUT, limit=5000).nodes}
    check("U_OUT 图谱不含 A", E_A not in ug_out)
    check("U_OUT 图谱含 M", E_M in ug_out, f"nodes={len(ug_out)}")
    check("U_OUT 图谱含 C", E_C in ug_out, f"nodes={len(ug_out)}")
    ug_in = {e.id for e in ks.get_user_graph(U_IN, limit=5000).nodes}
    check("U_IN 图谱含 A", E_A in ug_in)
    check("U_IN 图谱不含 M", E_M not in ug_in)

    print("\n=== 10. get_quality_stats / get_confidence_distribution 一致性 ===")
    q = ks.get_quality_stats(U_OUT)
    cd = ks.get_confidence_distribution(U_OUT)
    print(f"   quality: entity_count={q.get('entity_count')} relation_count={q.get('relation_count')} "
          f"type_distribution={q.get('type_distribution')}")
    print(f"   confidence: {cd}")
    td_total = sum((q.get("type_distribution") or {}).values())
    check("quality 的 type_distribution 与 entity_count 一致",
          td_total == q.get("entity_count"), f"{td_total} vs {q.get('entity_count')}")
    check("confidence 分布总数与 entity_count 一致",
          sum(cd.values()) == q.get("entity_count"), f"{sum(cd.values())} vs {q.get('entity_count')}")

    print("\n=== 11. fail-closed：可见文档集合算不出来时，KB 实体必须不可见 ===")
    import backend.service.auth.data_layer_service as dls

    orig = dls.get_visible_document_ids

    def boom(uid):
        raise RuntimeError("simulated MySQL failure")

    dls.get_visible_document_ids = boom
    try:
        check("fail-closed: U_IN 取不到 A", ks.get_entity(E_A, user_id=U_IN) is None)
        check("fail-closed: U_IN 搜不到 A",
              not ks.search_entities(nA, user_id=U_IN, limit=5))
        check("fail-closed: 记忆实体不受影响（仍可见）",
              ks.get_entity(E_M, user_id=U_OUT) is not None)
    finally:
        dls.get_visible_document_ids = orig

    print("\n=== 12. 灵敏度对照：把谓词换回旧版，上面这些断言必须失败 ===")
    # 目的：证明这套测试真的能发现问题，而不是恒真。
    # 旧谓词 = `source_document_id IS NOT NULL OR user_id = $user_id`
    #   → 任何 KB 文档实体对所有人可见（无部门概念）
    from backend.graphrag.kg_store import KGStore

    _orig_pred = KGStore._vis_pred
    KGStore._vis_pred = staticmethod(
        lambda var: (f"({var}.source_document_id IS NOT NULL "
                     f"OR {var}.user_id = $user_id)")
    )
    try:
        leaked = ks.get_entity(E_A, user_id=U_OUT) is not None
        leaked_search = bool(ks.search_entities(nA, user_id=U_OUT, limit=5))
        sg = ks.get_subgraph(E_C, depth=2, user_id=U_OUT)
        leaked_intermediate = E_A in {e.id for e in sg.nodes}
        print(f"   旧谓词下: get_entity(A) 泄露={leaked}  search(A) 泄露={leaked_search}  "
              f"子图中间节点泄露={leaked_intermediate}")
        check("旧谓词确实会泄露（证明测试有效）", leaked and leaked_search)
        check("旧谓词确实会带出不可见中间节点（证明测试有效）", leaked_intermediate)
    finally:
        KGStore._vis_pred = _orig_pred

    print(f"\n===== 结果: {checks - len(failures)}/{checks} 通过 =====")
    if failures:
        print("失败项:")
        for f in failures:
            print(f"   - {f}")
    return len(failures)


if __name__ == "__main__":
    rc = 1
    try:
        rc = main()
    except Exception:
        traceback.print_exc()
        rc = 2
    finally:
        try:
            teardown()
        except Exception:
            traceback.print_exc()
    sys.exit(1 if rc else 0)
