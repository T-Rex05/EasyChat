"""
数据层级服务 — 层级 CRUD + 引用检查 + 用户/KB 层级分配。

数据层级（data_layer）控制知识库内容的可见范围：
- 每个 chunk 属于一个层级（scope_layer_id），NULL 表示继承 KB 的层级
- 每个 KB 可关联多个层级（kb_data_layers 多对多）
- 每个用户可关联多个层级（user_data_layers 多对多）
- 检索时只返回用户层级与 chunk 层级匹配的条目
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# 层级 CRUD
# ════════════════════════════════════════════════════════════


def list_layers() -> List[dict]:
    """
    列出所有数据层级，附带引用计数（kb_count / user_count）。
    """
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            SELECT dl.id, dl.name, dl.description, dl.sort_order, dl.is_system,
                   dl.created_at,
                   COUNT(DISTINCT kdl.kb_id) AS kb_count,
                   COUNT(DISTINCT udl.user_id) AS user_count
            FROM data_layers dl
            LEFT JOIN kb_data_layers kdl ON kdl.layer_id = dl.id
            LEFT JOIN user_data_layers udl ON udl.layer_id = dl.id
            GROUP BY dl.id
            ORDER BY dl.sort_order ASC, dl.id ASC
            """
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_layer(name: str, description: str = "", sort_order: int = 0) -> dict:
    """
    创建新数据层级。

    Raises:
        ValueError: 名称为空或已存在
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("层级名称不能为空")

    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        # 检查重名
        cur = conn.execute("SELECT id FROM data_layers WHERE name = %s", (name,))
        if cur.fetchone():
            raise ValueError(f"层级名称已存在: {name}")

        cur = conn.execute(
            "INSERT INTO data_layers (name, description, sort_order) VALUES (%s, %s, %s)",
            (name, description, sort_order),
        )
        conn.commit()
        layer_id = cur.lastrowid
        logger.info(f"[DataLayer] 创建层级: id={layer_id}, name={name}")
        return {"id": layer_id, "name": name, "description": description, "sort_order": sort_order, "is_system": 0}
    except ValueError:
        raise
    except Exception as e:
        conn.rollback()
        raise ValueError(f"创建层级失败: {e}")
    finally:
        conn.close()


def update_layer(layer_id: int, name: Optional[str] = None, description: Optional[str] = None,
                 sort_order: Optional[int] = None) -> dict:
    """
    更新层级信息（名称/描述/排序）。

    Raises:
        ValueError: 层级不存在或名称冲突
    """
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM data_layers WHERE id = %s", (layer_id,))
        layer = cur.fetchone()
        if not layer:
            raise ValueError(f"层级不存在: id={layer_id}")

        updates = []
        params = []
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("层级名称不能为空")
            # 检查重名（排除自己）
            cur2 = conn.execute("SELECT id FROM data_layers WHERE name = %s AND id != %s", (name, layer_id))
            if cur2.fetchone():
                raise ValueError(f"层级名称已存在: {name}")
            updates.append("name = %s")
            params.append(name)
        if description is not None:
            updates.append("description = %s")
            params.append(description)
        if sort_order is not None:
            updates.append("sort_order = %s")
            params.append(sort_order)

        if not updates:
            return dict(layer)

        params.append(layer_id)
        conn.execute(f"UPDATE data_layers SET {', '.join(updates)} WHERE id = %s", params)
        conn.commit()
        logger.info(f"[DataLayer] 更新层级: id={layer_id}")

        cur = conn.execute("SELECT * FROM data_layers WHERE id = %s", (layer_id,))
        return dict(cur.fetchone())
    except ValueError:
        raise
    except Exception as e:
        conn.rollback()
        raise ValueError(f"更新层级失败: {e}")
    finally:
        conn.close()


def delete_layer(layer_id: int) -> dict:
    """
    删除数据层级。有引用时拒绝删除并返回引用计数。

    Returns:
        {"deleted": True} 或抛出 ValueError

    Raises:
        ValueError: 层级不存在 / 系统内置不可删除 / 有引用
    """
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM data_layers WHERE id = %s", (layer_id,))
        layer = cur.fetchone()
        if not layer:
            raise ValueError(f"层级不存在: id={layer_id}")
        if layer.get("is_system"):
            raise ValueError(f"系统内置层级不可删除: {layer.get('name')}")

        # 检查引用
        ref = _count_references(conn, layer_id)
        if ref["kb_count"] > 0 or ref["user_count"] > 0 or ref["chunk_count"] > 0:
            raise ValueError(
                f"该层级正在被使用，无法删除。"
                f"{ref['kb_count']} 个知识库、{ref['chunk_count']} 个分片、{ref['user_count']} 个用户正在使用。"
                f"请先解除关联后再删除。",
            )

        conn.execute("DELETE FROM data_layers WHERE id = %s", (layer_id,))
        conn.commit()
        logger.info(f"[DataLayer] 删除层级: id={layer_id}, name={layer.get('name')}")
        return {"deleted": True}
    except ValueError:
        raise
    except Exception as e:
        conn.rollback()
        raise ValueError(f"删除层级失败: {e}")
    finally:
        conn.close()


def _count_references(conn, layer_id: int) -> dict:
    """统计层级引用数（KB / chunk / 用户）。"""
    cur = conn.execute("SELECT COUNT(*) AS cnt FROM kb_data_layers WHERE layer_id = %s", (layer_id,))
    kb_count = (cur.fetchone() or {}).get("cnt", 0)

    cur = conn.execute("SELECT COUNT(*) AS cnt FROM kb_chunks WHERE scope_layer_id = %s", (layer_id,))
    chunk_count = (cur.fetchone() or {}).get("cnt", 0)

    cur = conn.execute("SELECT COUNT(*) AS cnt FROM user_data_layers WHERE layer_id = %s", (layer_id,))
    user_count = (cur.fetchone() or {}).get("cnt", 0)

    return {"kb_count": kb_count, "chunk_count": chunk_count, "user_count": user_count}


def get_delete_info(layer_id: int) -> dict:
    """获取层级删除前的引用信息（前端弹窗展示用）。"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM data_layers WHERE id = %s", (layer_id,))
        layer = cur.fetchone()
        if not layer:
            raise ValueError(f"层级不存在: id={layer_id}")
        ref = _count_references(conn, layer_id)
        return {
            "id": layer_id,
            "name": layer.get("name"),
            "is_system": bool(layer.get("is_system")),
            "kb_count": ref["kb_count"],
            "chunk_count": ref["chunk_count"],
            "user_count": ref["user_count"],
            "can_delete": ref["kb_count"] == 0 and ref["chunk_count"] == 0 and ref["user_count"] == 0 and not layer.get("is_system"),
        }
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════
# 用户层级分配
# ════════════════════════════════════════════════════════════


def get_user_layers(user_id: int) -> List[int]:
    """获取用户可见的数据层级 ID 列表。无记录时返回 [0]（全员）。"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        cur = conn.execute("SELECT layer_id FROM user_data_layers WHERE user_id = %s", (user_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        layer_ids = [r["layer_id"] for r in rows]
        return layer_ids if layer_ids else [0]  # 默认全员可见
    finally:
        conn.close()


def _invalidate_visibility_caches() -> None:
    """（内部别名，保留以兼容既有调用）→ 见 notify_visibility_changed。"""
    notify_visibility_changed(reason="层级分配变更")


def notify_visibility_changed(reason: str = "") -> dict:
    """**可见性相关变更后的统一收口** —— 清掉所有"已按层级过滤过"的派生缓存。

    为什么需要这个函数（也是本模块最重要的设计前提）：
      可见性**不会**被写进任何派生系统。`get_visible_document_ids()` 每次都实时查
      MySQL（`kb_chunks.scope_layer_id` / `kb_data_layers`），知识图谱实体上**没有**
      冗余的层级字段。因此：
        · 在「知识库管理」里把文档移到另一个知识库（= 另一个部门）后，
          **知识图谱不需要改任何实体属性** —— 下一次查询自动按新部门过滤；
        · 反过来，如果把部门"同步写进"图谱节点，才会重新引入陈旧问题
          （就像缓存漂移那样：改了部门但节点上还是旧值）。
      所以这里要清的不是数据，而是**把过滤结果缓存下来的那些地方**：
        1. BM25 内存索引（key=(查询者 user_id, kb_id)，且移动/改层级**不改变**
           signature → 不清就一直是旧结果）
        2. KG 时间线缓存（按 (entity, user_id) 缓存**最终结果**，TTL 300s）
      RAG 语义缓存**无需**处理：它在命中时会重新过一遍 `_filter_by_scope_layer`。

    调用场景：KB/用户层级分配变更、文档跨知识库移动、文档重解析、文档删除。

    Returns:
        {"bm25_cleared": int, "kg_timeline": bool}
    """
    out = {"bm25_cleared": 0, "kg_timeline": False}
    # 1. BM25 内存索引：必须全清（见 invalidate_all_bm25_cache 的说明）
    try:
        from backend.service.kb.kb_retriever import invalidate_all_bm25_cache

        out["bm25_cleared"] = invalidate_all_bm25_cache(reason)
    except Exception as e:  # pragma: no cover - 只为清缓存，失败不阻断
        logger.debug(f"[DataLayer] 清 BM25 缓存失败（不阻断）: {e}")
    # 2. KG 时间线缓存：它缓存的是"按用户过滤后的最终结果"
    try:
        from backend.graphrag.kg_store import get_kg_store

        get_kg_store().invalidate_timeline_cache(None)
        out["kg_timeline"] = True
    except Exception as e:  # pragma: no cover
        logger.debug(f"[DataLayer] 清 KG 时间线缓存失败（不阻断）: {e}")
    if reason:
        logger.debug(f"[DataLayer] 可见性缓存已刷新（{reason}）: {out}")
    return out


def set_user_layers(user_id: int, layer_ids: List[int]) -> dict:
    """
    设置用户可见的数据层级（替换所有）。
    layer_ids 必须包含 0（全员），否则自动补充。
    """
    if 0 not in layer_ids:
        layer_ids = [0] + list(layer_ids)

    # 校验所有 layer_id 存在
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        placeholders = ",".join(["%s"] * len(layer_ids))
        cur = conn.execute(f"SELECT id FROM data_layers WHERE id IN ({placeholders})", layer_ids)
        valid_ids = {r["id"] for r in (cur.fetchall() if hasattr(cur, "fetchall") else [])}
        invalid = set(layer_ids) - valid_ids
        if invalid:
            raise ValueError(f"层级 ID 不存在: {invalid}")

        conn.execute("DELETE FROM user_data_layers WHERE user_id = %s", (user_id,))
        for lid in layer_ids:
            conn.execute("INSERT INTO user_data_layers (user_id, layer_id) VALUES (%s, %s)", (user_id, lid))
        conn.commit()
        logger.info(f"[DataLayer] 用户 {user_id} 层级设为: {layer_ids}")
        _invalidate_visibility_caches()
        return {"user_id": user_id, "layer_ids": layer_ids}
    except ValueError:
        raise
    except Exception as e:
        conn.rollback()
        raise ValueError(f"设置用户层级失败: {e}")
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════
# KB 层级分配
# ════════════════════════════════════════════════════════════


def get_kb_layers(kb_id: int) -> List[int]:
    """获取 KB 关联的数据层级 ID 列表。无记录时返回 [0]（全员）。"""
    from backend.db.schema import get_conn
    conn = get_conn()
    try:
        cur = conn.execute("SELECT layer_id FROM kb_data_layers WHERE kb_id = %s", (kb_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        layer_ids = [r["layer_id"] for r in rows]
        return layer_ids if layer_ids else [0]
    finally:
        conn.close()


def set_kb_layers(kb_id: int, layer_ids: List[int]) -> dict:
    """设置 KB 关联的数据层级（替换所有）。"""
    from backend.db.schema import get_conn

    if not layer_ids:
        layer_ids = [0]

    conn = get_conn()
    try:
        # 校验 layer_ids 存在
        placeholders = ",".join(["%s"] * len(layer_ids))
        cur = conn.execute(f"SELECT id FROM data_layers WHERE id IN ({placeholders})", layer_ids)
        valid_ids = {r["id"] for r in (cur.fetchall() if hasattr(cur, "fetchall") else [])}
        invalid = set(layer_ids) - valid_ids
        if invalid:
            raise ValueError(f"层级 ID 不存在: {invalid}")

        conn.execute("DELETE FROM kb_data_layers WHERE kb_id = %s", (kb_id,))
        for lid in layer_ids:
            conn.execute("INSERT INTO kb_data_layers (kb_id, layer_id) VALUES (%s, %s)", (kb_id, lid))
        conn.commit()
        logger.info(f"[DataLayer] KB {kb_id} 层级设为: {layer_ids}")
        _invalidate_visibility_caches()
        return {"kb_id": kb_id, "layer_ids": layer_ids}
    except ValueError:
        raise
    except Exception as e:
        conn.rollback()
        raise ValueError(f"设置 KB 层级失败: {e}")
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════
# 检索辅助
# ════════════════════════════════════════════════════════════


def get_visible_layer_filter(user_id: int) -> List[int]:
    """
    获取用户可见的层级 ID 列表（用于检索过滤）。

    返回的列表用于：
    - Milvus filter: scope_layer_id in [...] OR scope_layer_id IS NULL
    - BM25 SQL WHERE: scope_layer_id IN (...) OR scope_layer_id IS NULL
    """
    return get_user_layers(user_id)


def get_visible_document_ids(user_id: int) -> List[int]:
    """返回该用户**有权看到**的知识库文档 ID 列表（按数据层级 / 部门隔离）。

    语义与 `kb_retriever._filter_by_scope_layer` **严格对齐**（同一套层级规则，
    两处不能各写一套，否则知识库正文与知识图谱会出现可见性不一致）：

      - `chunk.scope_layer_id` 非 NULL → 用 chunk 自己的层级
      - `chunk.scope_layer_id` 为 NULL，或该文档一个 chunk 都没有 → 继承 KB 层级
        （`kb_data_layers`）；KB 无任何层级记录 → 默认 `[0]`（全员）
      - 文档可见 ⇔ 存在某个 chunk 的有效层级 ∈ 用户层级
      - `layer_id = 0` 是特殊层级"全员"，而每个用户的层级集合**必定含 0**
        （见 `get_user_layers` / `set_user_layers`），所以未分配的 KB 仍然全员可见
      - 文档的 `kb_id` 为 NULL 且 chunk 的 `kb_id` 也为 NULL → 视作"KB 无层级记录"
        → 全员可见（与 `_filter_by_scope_layer` 对 `effective_kb_id=None` 的处理一致）

    ⚠️ **fail-closed**：查询失败返回 `[]`，即"什么都看不见"，绝不 fail-open。
    调用方把结果作为 Cypher 参数 `$visible_doc_ids` 使用，空列表时 `IN []` 恒为 false。

    ⚠️ **刻意不缓存**：部门归属随时可能在「数据层级」页面被改，缓存会让"收紧可见
    范围"在一段时间内不生效。安全边界优先于这点查询开销。
    """
    layers = get_user_layers(user_id)  # 无记录时返回 [0]
    if not layers:
        return []

    from backend.db.schema import get_conn

    conn = None
    try:
        conn = get_conn()
        placeholders = ",".join(["%s"] * len(layers))
        # 注意：本 SQL 里只有 %s 占位符，没有字面 %（`_MySQLAdapter` 传空元组时
        # 会对 SQL 做 `query % ()`，任何裸 % 都会抛 TypeError）
        cur = conn.execute(
            f"""
            SELECT DISTINCT d.id AS doc_id
            FROM kb_documents d
            LEFT JOIN kb_chunks c ON c.document_id = d.id
            LEFT JOIN kb_data_layers kdl ON kdl.kb_id = COALESCE(c.kb_id, d.kb_id)
            WHERE c.scope_layer_id IN ({placeholders})
               OR (
                    (c.id IS NULL OR c.scope_layer_id IS NULL)
                    AND (
                         kdl.layer_id IN ({placeholders})
                         OR (kdl.layer_id IS NULL AND 0 IN ({placeholders}))
                    )
                  )
            """,
            tuple(layers) * 3,
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        out: List[int] = []
        for r in rows:
            try:
                out.append(int(r["doc_id"]))
            except (TypeError, ValueError, KeyError):
                continue
        return out
    except Exception as e:
        logger.warning(
            f"[DataLayer] 计算可见文档集合失败 → fail-closed（KB 实体对本用户不可见）: {e}"
        )
        return []
    finally:
        if conn is not None:
            conn.close()
