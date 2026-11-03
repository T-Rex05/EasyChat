"""端到端验证：把文档移动到另一个知识库（=另一个部门）后，
知识图谱里的实体可见性是否**立即**跟着变（且不需要改任何实体属性）。

同时验证两件事：
  A. chunk 级 scope_layer_id 钉子会被移动操作清掉 —— 否则"移动"对带钉子的文档静默无效
     （灵敏度对照：把钉子重新钉回去，可见性必须**不**跟着变）
  B. 移动后会刷新 BM25 内存索引缓存

用法: python tests/kb_move_visibility_runner.py
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
from backend.graphrag.types import Entity, EntityType  # noqa: E402
from backend.infrastructure.neo4j_client import get_neo4j_client  # noqa: E402
from backend.service.auth.data_layer_service import (  # noqa: E402
    get_user_layers, get_visible_document_ids,
)
from backend.service.kb.kb_retriever import BM25Retriever  # noqa: E402
from backend.service.kb.kb_service import move_document_kb  # noqa: E402

TS = str(int(time.time()))
U_A, U_B = 26, 29          # 26 临时授予部门 A，29 临时授予部门 B
LA = LB = None
KB_A = KB_B = None
DOC1 = DOC2 = None
E1 = f"kbmove1{TS}"
E2 = f"kbmove2{TS}"
checks = 0
failures = []


def check(name, cond, extra=""):
    global checks
    checks += 1
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


def cols(table):
    c = get_conn()
    try:
        return [r["Field"] for r in c.execute(f"SHOW COLUMNS FROM {table}").fetchall()]
    finally:
        c.close()


def ins(table, data):
    existing = set(cols(table))
    use = {k: v for k, v in data.items() if k in existing}
    c = get_conn()
    try:
        cur = c.execute(
            f"INSERT INTO {table} ({','.join(use)}) VALUES ({','.join(['%s'] * len(use))})",
            tuple(use.values()),
        )
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def q1(sql, args):
    c = get_conn()
    try:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else {}
    finally:
        c.close()


def can_see(entity_id, uid):
    return get_kg_store().get_entity(entity_id, user_id=uid) is not None


def setup():
    global LA, LB, KB_A, KB_B, DOC1, DOC2
    LA = ins("data_layers", {"name": f"_kbmove_A_{TS}", "description": "t", "sort_order": 990, "is_system": 0})
    LB = ins("data_layers", {"name": f"_kbmove_B_{TS}", "description": "t", "sort_order": 991, "is_system": 0})
    for uid, layer in ((U_A, LA), (U_B, LB)):
        ins("user_data_layers", {"user_id": uid, "layer_id": 0})
        ins("user_data_layers", {"user_id": uid, "layer_id": layer})
    KB_A = ins("kb_knowledge_base", {"kb_name": f"_kbmove_kbA_{TS}", "kb_type": "normal",
                                     "description": "t", "user_id": 1, "is_enabled": 1, "is_system": 0})
    KB_B = ins("kb_knowledge_base", {"kb_name": f"_kbmove_kbB_{TS}", "kb_type": "normal",
                                     "description": "t", "user_id": 1, "is_enabled": 1, "is_system": 0})
    ins("kb_data_layers", {"kb_id": KB_A, "layer_id": LA})
    ins("kb_data_layers", {"kb_id": KB_B, "layer_id": LB})
    DOC1 = ins("kb_documents", {"kb_id": KB_A, "user_id": 1, "original_name": f"mv1_{TS}.md",
                                "stored_name": f"mv1_{TS}.md", "ext": ".md", "size_bytes": 1,
                                "sha256": TS, "status": "parsed", "vectorized": 0})
    DOC2 = ins("kb_documents", {"kb_id": KB_A, "user_id": 1, "original_name": f"mv2_{TS}.md",
                                "stored_name": f"mv2_{TS}.md", "ext": ".md", "size_bytes": 1,
                                "sha256": TS, "status": "parsed", "vectorized": 0})
    # 两个文档的 chunk 都**钉在部门 A** 的层级上（模拟"有人手工指定了 chunk 层级"）
    for d in (DOC1, DOC2):
        ins("kb_chunks", {"document_id": d, "kb_id": KB_A, "chunk_index": 0,
                          "content": f"movetest {TS}", "kind": "base", "scope_layer_id": LA})
    ks = get_kg_store()
    ks.create_entity(Entity(id=E1, name=f"移动实体1_{TS}", entity_type=EntityType.OTHER,
                            description="kb-move-test-1", source_document_id=DOC1), user_id=1)
    ks.create_entity(Entity(id=E2, name=f"移动实体2_{TS}", entity_type=EntityType.OTHER,
                            description="kb-move-test-2", source_document_id=DOC2), user_id=1)


def teardown():
    print("\n--- 清理 ---")
    try:
        client = get_neo4j_client()
        if client and client.is_available():
            with client._get_session() as s:
                s.run("MATCH (n) WHERE n.id STARTS WITH $p DETACH DELETE n", p="kbmove").consume()
            res = client.run_query("MATCH (n) WHERE n.id STARTS WITH 'kbmove' RETURN count(n) as c")
            print(f"   Neo4j: kbmove* 剩余 = {res[0]['c'] if res else '?'}")
    except Exception as e:
        print(f"   !! Neo4j 清理失败: {e}")
    try:
        from backend.db.connection_pool import get_pool_connection

        pc = get_pool_connection()
        cur = pc.cursor()
        try:
            def q(sql, args=None):
                cur.execute(sql, args)
                return cur.fetchall()

            docs = [r["id"] for r in q("SELECT id FROM kb_documents WHERE original_name REGEXP '^mv[0-9]+_[0-9]+\\\\.md$'")]
            kbs = [r["id"] for r in q("SELECT id FROM kb_knowledge_base WHERE kb_name LIKE '\\_kbmove\\_%'")]
            layers = [r["id"] for r in q("SELECT id FROM data_layers WHERE name LIKE '\\_kbmove\\_%'")]
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
            for uid in (U_A, U_B):
                cur.execute("DELETE FROM user_data_layers WHERE user_id = %s", (uid,))
            pc.commit()
            left = (q("SELECT COUNT(*) n FROM kb_documents WHERE original_name REGEXP '^mv[0-9]+_[0-9]+\\\\.md$'")[0]["n"]
                    + q("SELECT COUNT(*) n FROM kb_knowledge_base WHERE kb_name LIKE '\\_kbmove\\_%'")[0]["n"]
                    + q("SELECT COUNT(*) n FROM data_layers WHERE name LIKE '\\_kbmove\\_%'")[0]["n"]
                    + q("SELECT COUNT(*) n FROM user_data_layers WHERE user_id IN (%s,%s)", (U_A, U_B))[0]["n"])
            print(f"   MySQL: 残留 = {left}")
            print(f"   data_layers 现有 = {[(r['id'], r['name']) for r in q('SELECT id, name FROM data_layers ORDER BY id')]}")
        finally:
            cur.close()
            pc.close()
    except Exception as e:
        print(f"   !! MySQL 清理失败: {e}")


def main():
    setup()
    ks = get_kg_store()
    n1, n2 = f"移动实体1_{TS}", f"移动实体2_{TS}"
    print(f"fixtures: LA={LA} LB={LB} KB_A={KB_A} KB_B={KB_B} DOC1={DOC1} DOC2={DOC2}")
    print(f"U_A={U_A} layers={sorted(get_user_layers(U_A))}  U_B={U_B} layers={sorted(get_user_layers(U_B))}")

    print("\n=== 1. 移动前：两个实体只对部门 A 可见 ===")
    check("U_A 可见 E1", can_see(E1, U_A))
    check("U_B 不可见 E1", not can_see(E1, U_B))
    check("U_A 可见 E2", can_see(E2, U_A))
    check("U_B 不可见 E2", not can_see(E2, U_B))
    check("可见文档集合：U_A 含 DOC1", DOC1 in get_visible_document_ids(U_A))
    check("可见文档集合：U_B 不含 DOC1", DOC1 not in get_visible_document_ids(U_B))

    print("\n=== 2. 把 DOC1 从 KB_A 移到 KB_B（= 部门 A → 部门 B）===")
    BM25Retriever._cache[(U_B, KB_B)] = ("fake-signature", None, [], [], [], [])
    before_cache = len(BM25Retriever._cache)
    ok = move_document_kb(DOC1, KB_B)
    print(f"   move_document_kb -> {ok}；BM25 缓存 {before_cache} → {len(BM25Retriever._cache)}")
    check("移动成功", ok)
    check("移动后 BM25 缓存被刷新", len(BM25Retriever._cache) == 0, f"剩 {len(BM25Retriever._cache)}")
    pin = q1("SELECT COUNT(*) AS n FROM kb_chunks WHERE document_id = %s AND scope_layer_id IS NOT NULL", (DOC1,))
    check("DOC1 的 chunk 级层级钉子已被清掉", pin.get("n") == 0, f"剩 {pin.get('n')} 个")

    print("\n=== 3. 移动后：可见性立即跟着翻转（**没有改任何 KG 实体属性**）===")
    check("U_A 现在看不到 E1", not can_see(E1, U_A))
    check("U_B 现在能看到 E1", can_see(E1, U_B))
    check("可见文档集合：U_A 不再含 DOC1", DOC1 not in get_visible_document_ids(U_A))
    check("可见文档集合：U_B 含 DOC1", DOC1 in get_visible_document_ids(U_B))
    check("search 也跟着变（U_B）", bool(ks.search_entities(n1, user_id=U_B, limit=5)))
    check("search 也跟着变（U_A）", not ks.search_entities(n1, user_id=U_A, limit=5))
    e1_doc = q1("SELECT kb_id FROM kb_documents WHERE id = %s", (DOC1,)).get("kb_id")
    check("文档的 kb_id 已改到 KB_B", e1_doc == KB_B, f"kb_id={e1_doc}")

    print("\n=== 4. 灵敏度对照：不清理钉子时，移动对可见性**无效** ===")
    # DOC2 同样从 KB_A 移到 KB_B，但把钉子重新钉回部门 A（模拟旧实现的行为）
    ok2 = move_document_kb(DOC2, KB_B)
    get_conn().execute is not None  # noqa: B018  仅示意
    c = get_conn()
    try:
        c.execute("UPDATE kb_chunks SET scope_layer_id = %s WHERE document_id = %s", (LA, DOC2))
        c.commit()
    finally:
        c.close()
    check("对照：移动本身成功", ok2)
    check("对照：钉子重新钉回后，U_B 看不到 E2（证明清钉子这一步是必需的）",
          not can_see(E2, U_B))
    check("对照：此时仍只有 U_A 能看到 E2", can_see(E2, U_A))

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
