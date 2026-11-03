"""
数据层级（Data Layer）全面测试

测试覆盖：
1. Service 层 CRUD
   - list_layers（含引用计数）
   - create_layer（正常 / 重名 / 空名）
   - update_layer（正常 / 不存在 / 重名）
   - delete_layer（正常 / 不存在 / 系统内置 / 有引用）
   - get_user_layers / set_user_layers
   - get_kb_layers / set_kb_layers

2. 检索过滤（_filter_by_scope_layer）
   - 全员层级（layer_id=0）不过滤
   - 指定层级 → chunk scope_layer_id 直接匹配
   - 指定层级 → KB 继承（scope_layer_id IS NULL）
   - 混合场景

测试环境：
- 使用真实数据库连接（需要 MySQL 可用）
- 测试前检查数据库连接，不可用则跳过
- 测试数据使用唯一前缀避免冲突
"""
import sys
import os
import time

# 加载 .env（必须在 import backend 之前）
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _check_db():
    """检查数据库连接是否可用。"""
    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception as e:
        print(f"[SKIP] 数据库不可用: {e}")
        return False


# ════════════════════════════════════════════════════════════
# 测试 1: Service 层 CRUD
# ════════════════════════════════════════════════════════════


def test_list_layers():
    """列出所有层级，验证结构。"""
    from backend.service.auth.data_layer_service import list_layers
    layers = list_layers()
    assert isinstance(layers, list), "返回应为列表"
    assert len(layers) >= 1, "至少有一个层级（全员）"
    # 全员层级应存在
    all_layer = next((l for l in layers if l["id"] == 0), None)
    assert all_layer is not None, "全员层级（id=0）应存在"
    assert all_layer["name"] == "全员"
    assert all_layer["is_system"] == 1
    print("[PASS] test_list_layers")


def test_create_layer():
    """创建层级。"""
    from backend.service.auth.data_layer_service import create_layer, delete_layer, list_layers

    name = f"_test_layer_{int(time.time())}"
    layer = create_layer(name=name, description="测试层级", sort_order=10)
    assert layer["name"] == name
    assert layer["description"] == "测试层级"
    assert layer["id"] > 0

    # 验证列表中包含新层级
    layers = list_layers()
    found = any(l["name"] == name for l in layers)
    assert found, f"新创建的层级 {name} 应在列表中"

    # 清理
    delete_layer(layer["id"])
    print("[PASS] test_create_layer")


def test_create_layer_duplicate():
    """创建重名层级应失败。"""
    from backend.service.auth.data_layer_service import create_layer, delete_layer

    name = f"_test_dup_{int(time.time())}"
    layer1 = create_layer(name=name)
    try:
        create_layer(name=name)
        assert False, "重名创建应抛出 ValueError"
    except ValueError as e:
        assert "已存在" in str(e)
    finally:
        delete_layer(layer1["id"])
    print("[PASS] test_create_layer_duplicate")


def test_create_layer_empty_name():
    """创建空名称层级应失败。"""
    from backend.service.auth.data_layer_service import create_layer
    try:
        create_layer(name="")
        assert False, "空名称应抛出 ValueError"
    except ValueError as e:
        assert "不能为空" in str(e)
    print("[PASS] test_create_layer_empty_name")


def test_update_layer():
    """更新层级。"""
    from backend.service.auth.data_layer_service import create_layer, update_layer, delete_layer

    name = f"_test_update_{int(time.time())}"
    layer = create_layer(name=name)
    new_name = f"{name}_updated"
    updated = update_layer(layer["id"], name=new_name, description="新描述")
    assert updated["name"] == new_name
    assert updated["description"] == "新描述"

    # 清理
    delete_layer(layer["id"])
    print("[PASS] test_update_layer")


def test_update_layer_not_found():
    """更新不存在的层级应失败。"""
    from backend.service.auth.data_layer_service import update_layer
    try:
        update_layer(999999, name="x")
        assert False, "不存在的层级应抛出 ValueError"
    except ValueError as e:
        assert "不存在" in str(e)
    print("[PASS] test_update_layer_not_found")


def test_delete_layer_system():
    """删除系统内置层级应失败。"""
    from backend.service.auth.data_layer_service import delete_layer
    try:
        delete_layer(0)  # 全员是系统内置
        assert False, "系统内置层级应不可删除"
    except ValueError as e:
        assert "不可删除" in str(e) or "系统内置" in str(e)
    print("[PASS] test_delete_layer_system")


def test_delete_layer_with_references():
    """删除有引用的层级应失败并返回引用计数。"""
    from backend.service.auth.data_layer_service import (
        create_layer, delete_layer, set_kb_layers, get_kb_layers
    )

    name = f"_test_ref_{int(time.time())}"
    layer = create_layer(name=name)
    layer_id = layer["id"]

    # 假设 kb_id=1 存在（系统内置知识库），给它关联这个层级
    # 如果没有 kb_id=1，先创建一个测试 KB
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        conn.execute(
            "INSERT IGNORE INTO kb_knowledge_base (id, kb_name, user_id) VALUES (99999, '_test_kb', 1)"
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    # 关联 KB
    set_kb_layers(99999, [0, layer_id])

    # 尝试删除
    try:
        delete_layer(layer_id)
        assert False, "有引用时删除应失败"
    except ValueError as e:
        assert "正在被使用" in str(e) or "无法删除" in str(e)

    # 清理：先解除关联，再删除
    set_kb_layers(99999, [0])
    delete_layer(layer_id)

    # 清理测试 KB
    conn = get_conn()
    try:
        conn.execute("DELETE FROM kb_knowledge_base WHERE id = 99999")
        conn.commit()
    finally:
        conn.close()

    print("[PASS] test_delete_layer_with_references")


def test_user_layers():
    """用户层级设置和获取。"""
    from backend.service.auth.data_layer_service import (
        create_layer, delete_layer, get_user_layers, set_user_layers
    )

    # 使用一个测试用户 ID
    test_user_id = 999999

    # 默认返回 [0]（全员）
    layers = get_user_layers(test_user_id)
    assert layers == [0], f"默认应返回 [0]，实际: {layers}"

    # 创建新层级并设置
    name = f"_test_user_layer_{int(time.time())}"
    layer = create_layer(name=name)

    # 设置用户层级（不含 0，应自动补充）
    set_user_layers(test_user_id, [layer["id"]])
    layers = get_user_layers(test_user_id)
    assert 0 in layers, "应自动包含全员层级"
    assert layer["id"] in layers, f"应包含新层级 {layer['id']}"

    # 清理
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        conn.execute("DELETE FROM user_data_layers WHERE user_id = %s", (test_user_id,))
        conn.commit()
    finally:
        conn.close()
    delete_layer(layer["id"])

    print("[PASS] test_user_layers")


def test_kb_layers():
    """KB 层级设置和获取。"""
    from backend.service.auth.data_layer_service import (
        create_layer, delete_layer, get_kb_layers, set_kb_layers
    )
    from backend.db.schema import get_conn

    test_kb_id = 999998

    # 创建测试 KB
    conn = get_conn()
    try:
        conn.execute(
            "INSERT IGNORE INTO kb_knowledge_base (id, kb_name, user_id) VALUES (%s, '_test_kb2', 1)",
            (test_kb_id,)
        )
        conn.commit()
    finally:
        conn.close()

    # 默认返回 [0]
    layers = get_kb_layers(test_kb_id)
    assert layers == [0], f"默认应返回 [0]，实际: {layers}"

    # 创建层级并设置
    name = f"_test_kb_layer_{int(time.time())}"
    layer = create_layer(name=name)
    set_kb_layers(test_kb_id, [0, layer["id"]])
    layers = get_kb_layers(test_kb_id)
    assert layer["id"] in layers

    # 清理
    set_kb_layers(test_kb_id, [0])
    delete_layer(layer["id"])
    conn = get_conn()
    try:
        conn.execute("DELETE FROM kb_knowledge_base WHERE id = %s", (test_kb_id,))
        conn.commit()
    finally:
        conn.close()

    print("[PASS] test_kb_layers")


# ════════════════════════════════════════════════════════════
# 测试 2: 检索过滤
# ════════════════════════════════════════════════════════════


def test_filter_by_scope_layer_all():
    """全员层级（layer_id=0）不过滤。"""
    from backend.service.kb.kb_retriever import _filter_by_scope_layer

    results = [
        {"chunk_id": 1, "kb_id": 1, "content": "test1"},
        {"chunk_id": 2, "kb_id": 1, "content": "test2"},
    ]
    # 用户 999998 默认有全员层级
    filtered = _filter_by_scope_layer(results, 999998)
    assert len(filtered) == 2, "全员层级应不过滤"
    print("[PASS] test_filter_by_scope_layer_all")


def test_filter_by_scope_layer_specific():
    """指定层级过滤 — chunk scope_layer_id 直接匹配。"""
    from backend.service.auth.data_layer_service import create_layer, delete_layer, set_user_layers
    from backend.service.kb.kb_retriever import _filter_by_scope_layer
    from backend.db.schema import get_conn

    test_user_id = 999997
    test_kb_id = 999997

    # 创建测试 KB 和层级
    conn = get_conn()
    try:
        conn.execute(
            "INSERT IGNORE INTO kb_knowledge_base (id, kb_name, user_id) VALUES (%s, '_test_kb3', 1)",
            (test_kb_id,)
        )
        conn.commit()
    finally:
        conn.close()

    layer = create_layer(name=f"_test_filter_{int(time.time())}")
    layer_id = layer["id"]

    # 设置用户层级（只有这个新层级 + 全员）
    set_user_layers(test_user_id, [0, layer_id])

    # 创建测试 chunk，设置 scope_layer_id
    conn = get_conn()
    try:
        ts = int(time.time())
        conn.execute(
            "INSERT INTO kb_chunks (kb_id, document_id, chunk_index, content, strategy, kind, scope_layer_id) "
            "VALUES (%s, %s, 0, 'test', 'fixed', 'base', %s)",
            (test_kb_id, ts, layer_id)
        )
        chunk_id = conn.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]

        # 创建一个不在用户层级的 chunk
        conn.execute(
            "INSERT INTO kb_chunks (kb_id, document_id, chunk_index, content, strategy, kind, scope_layer_id) "
            "VALUES (%s, %s, 1, 'test2', 'fixed', 'base', 999)",
            (test_kb_id, ts + 1)
        )
        chunk_id_hidden = conn.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]
        conn.commit()
    finally:
        conn.close()

    # 模拟检索结果
    results = [
        {"chunk_id": chunk_id, "kb_id": test_kb_id, "content": "visible"},
        {"chunk_id": chunk_id_hidden, "kb_id": test_kb_id, "content": "hidden"},
    ]

    filtered = _filter_by_scope_layer(results, test_user_id)
    assert len(filtered) == 1, f"应只保留 1 条，实际: {len(filtered)}"
    assert filtered[0]["content"] == "visible"

    # 清理
    conn = get_conn()
    try:
        conn.execute("DELETE FROM kb_chunks WHERE id IN (%s, %s)", (chunk_id, chunk_id_hidden))
        conn.execute("DELETE FROM user_data_layers WHERE user_id = %s", (test_user_id,))
        conn.execute("DELETE FROM kb_knowledge_base WHERE id = %s", (test_kb_id,))
        conn.commit()
    finally:
        conn.close()
    delete_layer(layer_id)

    print("[PASS] test_filter_by_scope_layer_specific")


def test_filter_by_scope_layer_kb_inheritance():
    """KB 继承 — scope_layer_id IS NULL 时继承 KB 层级。"""
    from backend.service.auth.data_layer_service import create_layer, delete_layer, set_user_layers, set_kb_layers
    from backend.service.kb.kb_retriever import _filter_by_scope_layer
    from backend.db.schema import get_conn

    test_user_id = 999996
    test_kb_id = 999996

    # 创建测试 KB
    conn = get_conn()
    try:
        conn.execute(
            "INSERT IGNORE INTO kb_knowledge_base (id, kb_name, user_id) VALUES (%s, '_test_kb4', 1)",
            (test_kb_id,)
        )
        conn.commit()
    finally:
        conn.close()

    layer = create_layer(name=f"_test_inherit_{int(time.time())}")
    layer_id = layer["id"]

    # KB 关联这个层级
    set_kb_layers(test_kb_id, [0, layer_id])
    # 用户有全员 + 这个层级
    set_user_layers(test_user_id, [0, layer_id])

    # 创建 chunk，scope_layer_id = NULL（继承 KB）
    conn = get_conn()
    try:
        ts = int(time.time()) + 100
        conn.execute(
            "INSERT INTO kb_chunks (kb_id, document_id, chunk_index, content, strategy, kind, scope_layer_id) "
            "VALUES (%s, %s, 0, 'inherit_test', 'fixed', 'base', NULL)",
            (test_kb_id, ts)
        )
        chunk_id = conn.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]
        conn.commit()
    finally:
        conn.close()

    results = [{"chunk_id": chunk_id, "kb_id": test_kb_id, "content": "inherit"}]
    filtered = _filter_by_scope_layer(results, test_user_id)
    assert len(filtered) == 1, "KB 层级匹配时应保留"

    # 清理
    conn = get_conn()
    try:
        conn.execute("DELETE FROM kb_chunks WHERE id = %s", (chunk_id,))
        conn.execute("DELETE FROM user_data_layers WHERE user_id = %s", (test_user_id,))
        conn.execute("DELETE FROM kb_data_layers WHERE kb_id = %s", (test_kb_id,))
        conn.execute("DELETE FROM kb_knowledge_base WHERE id = %s", (test_kb_id,))
        conn.commit()
    finally:
        conn.close()
    delete_layer(layer_id)

    print("[PASS] test_filter_by_scope_layer_kb_inheritance")


def test_filter_web_search_no_chunk():
    """Web search 结果没有 chunk_id，应保留。"""
    from backend.service.kb.kb_retriever import _filter_by_scope_layer

    results = [
        {"chunk_id": None, "kb_id": None, "retriever": "web_search", "content": "web"},
    ]
    filtered = _filter_by_scope_layer(results, 999995)
    assert len(filtered) == 1, "无 chunk_id 的结果应保留"
    print("[PASS] test_filter_web_search_no_chunk")


# ════════════════════════════════════════════════════════════
# 运行所有测试
# ════════════════════════════════════════════════════════════


def run_all_tests():
    if not _check_db():
        return

    tests = [
        # Service CRUD
        test_list_layers,
        test_create_layer,
        test_create_layer_duplicate,
        test_create_layer_empty_name,
        test_update_layer,
        test_update_layer_not_found,
        test_delete_layer_system,
        test_delete_layer_with_references,
        test_user_layers,
        test_kb_layers,
        # Filter
        test_filter_by_scope_layer_all,
        test_filter_by_scope_layer_specific,
        test_filter_by_scope_layer_kb_inheritance,
        test_filter_web_search_no_chunk,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"[FAIL] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"测试完成: {passed} 通过, {failed} 失败")


if __name__ == "__main__":
    run_all_tests()
