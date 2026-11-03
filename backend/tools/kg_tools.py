"""
知识图谱（Neo4j）查询工具集

提供 LLM 可调用的知识图谱查询工具，用于：
- 统计信息（节点/关系/社区数量）
- 实体搜索（按名称/类型模糊搜索）
- 实体详情（含关系和时间线）
- 社区查询（层级社区 + 社区报告）
- 质量分析（置信度分布、孤立实体等）

数据源：Neo4j 图数据库（不是 MySQL！）
"""
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.utils.log_utils import log

logger = log


# ==================== 参数 Schema ====================

class KGStatsInput(BaseModel):
    """知识图谱统计工具的参数"""
    stat_type: str = Field(
        default="all",
        description="统计类型: 'all'=全部统计, 'entities'=实体数量, 'relations'=关系数量, 'communities'=社区数量, 'quality'=质量统计（置信度分布/孤立实体等）"
    )


class KGSearchInput(BaseModel):
    """知识图谱实体搜索参数"""
    name: str = Field(
        description="实体名称（模糊匹配，支持中文）"
    )
    entity_type: str = Field(
        default="",
        description="实体类型过滤（可选）: Person/Organization/Location/Concept/Event/Project/Tool/Skill/Fact/Preference"
    )
    limit: int = Field(
        default=10,
        description="返回数量限制（默认 10，最大 50）"
    )


class KGEntityDetailInput(BaseModel):
    """知识图谱实体详情参数"""
    entity_id: str = Field(
        description="实体 ID（UUID 格式，如 'abc123-def456'）。可通过 kg_search 获取"
    )
    include_relations: bool = Field(
        default=True,
        description="是否包含关系信息（默认 True）"
    )
    include_timeline: bool = Field(
        default=False,
        description="是否包含时间线信息（默认 False，需要时设为 True）"
    )


class KGCommunitiesInput(BaseModel):
    """知识图谱社区查询参数"""
    level: int = Field(
        default=-1,
        description="社区层级（0=顶层社区，1=子社区，-1=全部层级）"
    )
    include_reports: bool = Field(
        default=False,
        description="是否包含社区报告内容（默认 False，报告可能很长）"
    )
    limit: int = Field(
        default=20,
        description="返回数量限制（默认 20）"
    )


class KGQualityInput(BaseModel):
    """知识图谱质量分析参数"""
    analysis_type: str = Field(
        default="all",
        description="分析类型: 'all'=全部, 'confidence'=置信度分布, 'orphans'=孤立实体, 'type_dist'=类型分布"
    )


# ==================== 辅助函数 ====================

def _get_kg_store():
    """获取 KGStore 实例，不可用时返回 None"""
    try:
        from backend.graphrag.kg_store import get_kg_store
        store = get_kg_store()
        if store.is_available():
            return store
        return None
    except Exception as e:
        logger.warning(f"[KG Tools] KGStore 不可用: {e}")
        return None


def _get_user_id() -> Optional[int]:
    """获取当前用户 ID，失败返回 None（而非 0，避免下游真值判断错误放行）"""
    try:
        from backend.hermes_adapter import _CURRENT_USER_ID_CTX
        uid = _CURRENT_USER_ID_CTX.get()
        return int(uid) if uid is not None else None
    except Exception:
        return None


def _entity_type_from_str(type_str: str):
    """字符串转 EntityType 枚举"""
    if not type_str:
        return None
    try:
        from backend.graphrag.types import EntityType
        type_map = {
            "person": EntityType.PERSON,
            "organization": EntityType.ORGANIZATION,
            "location": EntityType.LOCATION,
            "concept": EntityType.CONCEPT,
            "event": EntityType.EVENT,
            "project": EntityType.PROJECT,
            "tool": EntityType.TOOL,
            "skill": EntityType.SKILL,
            "fact": EntityType.FACT,
            "preference": EntityType.PREFERENCE,
        }
        return type_map.get(type_str.lower())
    except Exception:
        return None


# ==================== 工具定义 ====================

@tool(args_schema=KGStatsInput)
def kg_stats(stat_type: str = "all") -> str:
    """查询知识图谱（Neo4j）的统计信息：实体数量、关系数量、社区数量等。

    当用户询问"有多少知识图谱节点"、"图谱有多少实体"、"关系数量"、"社区数量"等问题时使用此工具。
    注意：知识图谱数据存储在 Neo4j 中，不在 MySQL 中，不能用 SQL 查询。

    Args:
        stat_type: 统计类型 - 'all'(全部), 'entities'(实体/节点数), 'relations'(关系数), 'communities'(社区数), 'quality'(质量统计)
    """
    user_id = _get_user_id()
    store = _get_kg_store()

    if not store:
        return "❌ 知识图谱（Neo4j）不可用，请检查 Neo4j 服务是否启动。"

    results = {}

    try:
        if stat_type in ("all", "entities"):
            results["实体(节点)数量"] = store.count_entities(user_id=user_id)

        if stat_type in ("all", "relations"):
            results["关系数量"] = store.count_relations(user_id=user_id)

        if stat_type in ("all", "communities"):
            from backend.db.schema import get_conn
            conn = None
            try:
                conn = get_conn()
                cur = conn.execute(
                    "SELECT COUNT(*) as cnt, MAX(level) as max_level FROM kg_communities WHERE user_id = %s",
                    (user_id,)
                )
                row = cur.fetchone() if hasattr(cur, "fetchone") else None
                if row:
                    results["社区数量"] = row.get("cnt", 0)
                    results["最大社区层级"] = row.get("max_level", 0)

                # 社区报告数
                cur2 = conn.execute(
                    "SELECT COUNT(*) as cnt FROM kg_community_reports r "
                    "JOIN kg_communities c ON r.community_id = c.id "
                    "WHERE c.user_id = %s AND r.status = 'completed'",
                    (user_id,)
                )
                row2 = cur2.fetchone() if hasattr(cur2, "fetchone") else None
                if row2:
                    results["已完成社区报告数"] = row2.get("cnt", 0)
            finally:
                if conn is not None:
                    conn.close()

        if stat_type in ("all", "quality"):
            quality = store.get_quality_stats(user_id=user_id)
            if quality:
                avg_conf = quality.get("avg_confidence")
                results["平均置信度"] = round(avg_conf, 2) if avg_conf is not None else "N/A"
                results["低置信度实体数(<0.7)"] = quality.get("low_confidence_count", "N/A")
                results["孤立实体数(无关系)"] = quality.get("orphan_entity_count", "N/A")
                results["已软删除实体数"] = quality.get("deleted_entity_count", "N/A")
                type_dist = quality.get("type_distribution", {})
                if type_dist:
                    results["类型分布"] = type_dist

    except Exception as e:
        logger.warning(f"[KG Stats] 统计失败: {e}")
        return f"❌ 知识图谱统计失败: {e}"

    if not results:
        return f"未找到 stat_type='{stat_type}' 对应的统计项。可选: all, entities, relations, communities, quality"

    lines = [f"📊 知识图谱统计 (user_id={user_id}):"]
    for k, v in results.items():
        lines.append(f"  • {k}: {v}")

    return "\n".join(lines)


@tool(args_schema=KGSearchInput)
def kg_search(name: str, entity_type: str = "", limit: int = 10) -> str:
    """搜索知识图谱中的实体（节点）。按名称模糊匹配，可按类型过滤。

    当用户询问"查找关于XX的实体"、"图谱中有没有XX"、"搜索XX相关的节点"等问题时使用此工具。
    搜索结果包含实体 ID，可用于 kg_entity_detail 查看详细信息。
    注意：数据在 Neo4j 中，不在 MySQL 中。

    Args:
        name: 实体名称（模糊匹配，支持中文）
        entity_type: 实体类型过滤（可选）: Person/Organization/Location/Concept/Event/Project/Tool/Skill/Fact/Preference
        limit: 返回数量限制（默认 10，最大 50）
    """
    user_id = _get_user_id()
    store = _get_kg_store()

    if not store:
        return "❌ 知识图谱（Neo4j）不可用。"

    limit = min(max(1, limit), 50)
    et = _entity_type_from_str(entity_type)

    try:
        entities = store.search_entities(
            name=name,
            entity_type=et,
            user_id=user_id,
            limit=limit,
        )

        if not entities:
            return f"🔍 未找到名称包含 '{name}' 的实体。"

        lines = [f"🔍 搜索 '{name}' 找到 {len(entities)} 个实体:"]
        for i, e in enumerate(entities, 1):
            etype = e.entity_type.value if hasattr(e, 'entity_type') and e.entity_type else "Unknown"
            desc = (e.description or "")[:80]
            lines.append(
                f"  {i}. [{etype}] {e.name} (id={e.id})"
                f"\n     置信度={round(e.confidence or 0, 2)}"
                f"{', 描述: ' + desc if desc else ''}"
            )

        lines.append(f"\n💡 使用 kg_entity_detail(entity_id='...') 查看详情")
        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"[KG Search] 搜索失败: {e}")
        return f"❌ 搜索失败: {e}"


@tool(args_schema=KGEntityDetailInput)
def kg_entity_detail(entity_id: str, include_relations: bool = True, include_timeline: bool = False) -> str:
    """获取知识图谱中某个实体的详细信息，包括描述、关系、时间线等。

    需要先通过 kg_search 获取实体 ID，再调用此工具查看详情。
    注意：数据在 Neo4j 中，不在 MySQL 中。

    Args:
        entity_id: 实体 ID（UUID 格式）
        include_relations: 是否包含关系信息（默认 True）
        include_timeline: 是否包含时间线信息（默认 False）
    """
    user_id = _get_user_id()
    store = _get_kg_store()

    if not store:
        return "❌ 知识图谱（Neo4j）不可用。"

    try:
        entity = store.get_entity(entity_id, user_id=user_id)
        if not entity:
            return f"❌ 未找到 ID={entity_id} 的实体。"

        lines = [
            f"📌 实体详情:",
            f"  • ID: {entity.id}",
            f"  • 名称: {entity.name}",
            f"  • 类型: {entity.entity_type.value if hasattr(entity, 'entity_type') and entity.entity_type else 'Unknown'}",
            f"  • 置信度: {round(entity.confidence or 0, 3)}",
            f"  • 描述: {entity.description or '(无)'}",
        ]

        if entity.source_document_id:
            lines.append(f"  • 来源文档 ID: {entity.source_document_id}")
        if entity.source_memory_id:
            lines.append(f"  • 来源记忆 ID: {entity.source_memory_id}")

        # 关系信息
        if include_relations:
            try:
                subgraph = store.get_subgraph(entity_id, depth=1, user_id=user_id)
                if subgraph and subgraph.edges:
                    lines.append(f"\n🔗 关系 ({len(subgraph.edges)} 条):")
                    # 建索引避免 O(n*m) 查找
                    node_names = {n.id: n.name for n in subgraph.nodes} if subgraph.nodes else {}
                    for edge in subgraph.edges[:20]:
                        rel_type = edge.relation_type.value if hasattr(edge, 'relation_type') and edge.relation_type else "RELATED_TO"
                        source_name = node_names.get(edge.source_id, edge.source_id[:8])
                        target_name = node_names.get(edge.target_id, edge.target_id[:8])
                        lines.append(f"  • {source_name} --[{rel_type}]--> {target_name}")
                    if len(subgraph.edges) > 20:
                        lines.append(f"  ... 还有 {len(subgraph.edges) - 20} 条关系")
                else:
                    lines.append(f"\n🔗 关系: 无（孤立实体）")
            except Exception as e:
                lines.append(f"\n🔗 关系查询失败: {e}")

        # 时间线信息
        if include_timeline:
            try:
                timeline = store.get_entity_timeline(entity_id, user_id=user_id)
                if timeline:
                    lines.append(f"\n📅 时间线 ({len(timeline)} 条):")
                    for item in timeline[:15]:
                        related = item.get("related_entity")
                        rel_name = related.name if related else "?"
                        rel_type = item.get("relation_type", "?")
                        valid_from = item.get("valid_from", "")
                        valid_until = item.get("valid_until", "")
                        is_current = item.get("is_current", True)
                        time_str = f"{valid_from or '?'} ~ {valid_until or '至今'}"
                        current_str = "" if is_current else " (已过期)"
                        lines.append(f"  • [{rel_type}] {rel_name}: {time_str}{current_str}")
                    if len(timeline) > 15:
                        lines.append(f"  ... 还有 {len(timeline) - 15} 条")
                else:
                    lines.append(f"\n📅 时间线: 无")
            except Exception as e:
                lines.append(f"\n📅 时间线查询失败: {e}")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"[KG Detail] 详情查询失败: {e}")
        return f"❌ 查询失败: {e}"


@tool(args_schema=KGCommunitiesInput)
def kg_communities(level: int = -1, include_reports: bool = False, limit: int = 20) -> str:
    """查询知识图谱的社区结构（社区检测的结果）。

    社区是图谱中紧密连接的实体群组。社区报告是 LLM 对每个社区的摘要。
    当用户询问"有哪些社区"、"社区报告"、"图谱的聚类情况"等问题时使用。
    注意：社区数据在 MySQL（kg_communities/kg_community_reports 表），实体数据在 Neo4j。

    Args:
        level: 社区层级（0=顶层社区，1=子社区，-1=全部层级）
        include_reports: 是否包含社区报告内容（默认 False，报告可能很长）
        limit: 返回数量限制（默认 20）
    """
    user_id = _get_user_id()
    conn = None

    try:
        from backend.db.schema import get_conn
        conn = get_conn()
        # 查询社区列表
        sql = (
            "SELECT c.id, c.level, c.parent_id, c.entity_count, c.relationship_count "
            "FROM kg_communities c WHERE c.user_id = %s"
        )
        params = [user_id]
        if level >= 0:
            sql += " AND c.level = %s"
            params.append(level)
        sql += " ORDER BY c.level, c.entity_count DESC LIMIT %s"
        params.append(limit)

        cur = conn.execute(sql, tuple(params))
        communities = cur.fetchall() if hasattr(cur, "fetchall") else []

        if not communities:
            return f"📦 未找到社区数据。可能尚未运行社区检测。"

        lines = [f"📦 知识图谱社区 (user_id={user_id}, 共 {len(communities)} 个):"]

        for i, c in enumerate(communities, 1):
            lines.append(
                f"  {i}. [Level {c['level']}] 社区 ID={c['id']}"
                f" | 实体数={c['entity_count']}"
                f" | 关系数={c['relationship_count']}"
                f"{' | 父社区=' + str(c['parent_id']) if c.get('parent_id') else ''}"
            )

        # 社区报告
        if include_reports:
            community_ids = [c["id"] for c in communities]
            if community_ids:
                placeholders = ",".join(["%s"] * len(community_ids))
                cur2 = conn.execute(
                    f"SELECT r.community_id, r.summary, r.findings, r.status "
                    f"FROM kg_community_reports r "
                    f"WHERE r.community_id IN ({placeholders}) AND r.status = 'completed'",
                    tuple(community_ids)
                )
                reports = cur2.fetchall() if hasattr(cur2, "fetchall") else []

                if reports:
                    lines.append(f"\n📝 社区报告 ({len(reports)} 份):")
                    for r in reports[:10]:
                        summary = (r.get("summary") or "")[:200]
                        lines.append(f"  • 社区 {r['community_id']}: {summary}...")
                else:
                    lines.append(f"\n📝 暂无已完成的社区报告。")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"[KG Communities] 查询失败: {e}")
        return f"❌ 查询失败: {e}"
    finally:
        if conn is not None:
            conn.close()


@tool(args_schema=KGQualityInput)
def kg_quality(analysis_type: str = "all") -> str:
    """分析知识图谱的质量：置信度分布、孤立实体、类型分布等。

    当用户询问"图谱质量如何"、"有多少低置信度实体"、"实体类型分布"等问题时使用。
    注意：数据在 Neo4j 中。

    Args:
        analysis_type: 分析类型 - 'all'(全部), 'confidence'(置信度分布), 'orphans'(孤立实体), 'type_dist'(类型分布)
    """
    user_id = _get_user_id()
    store = _get_kg_store()

    if not store:
        return "❌ 知识图谱（Neo4j）不可用。"

    try:
        results = []
        quality = None  # 缓存，避免重复查询

        if analysis_type in ("all", "confidence"):
            conf_dist = store.get_confidence_distribution(user_id=user_id)
            if conf_dist:
                results.append("📊 置信度分布:")
                results.append(f"  • 高 (≥0.9): {conf_dist.get('high', 0)} 个")
                results.append(f"  • 中 (0.7~0.9): {conf_dist.get('medium', 0)} 个")
                results.append(f"  • 低 (0.5~0.7): {conf_dist.get('low', 0)} 个")
                results.append(f"  • 极低 (<0.5): {conf_dist.get('very_low', 0)} 个")

        if analysis_type in ("all", "type_dist"):
            quality = quality or store.get_quality_stats(user_id=user_id)
            type_dist = quality.get("type_distribution", {})
            if type_dist:
                results.append(f"\n📋 实体类型分布:")
                for t, count in sorted(type_dist.items(), key=lambda x: x[1], reverse=True):
                    results.append(f"  • {t}: {count} 个")

        if analysis_type in ("all", "orphans"):
            quality = quality or store.get_quality_stats(user_id=user_id)
            orphan_count = quality.get("orphan_entity_count", 0)
            total = quality.get("entity_count", 0)
            results.append(f"\n🔍 孤立实体: {orphan_count} 个 (占总实体 {round(orphan_count / total * 100, 1) if total else 0}%)")
            results.append(f"  • 孤立实体 = 没有关系连接的实体，可能是提取不完整或已断开关联")

        if not results:
            return f"未找到 analysis_type='{analysis_type}' 对应的分析项。可选: all, confidence, orphans, type_dist"

        header = f"📈 知识图谱质量分析 (user_id={user_id}):"
        return header + "\n" + "\n".join(results)

    except Exception as e:
        logger.warning(f"[KG Quality] 分析失败: {e}")
        return f"❌ 分析失败: {e}"


# ==================== 工具集标记 ====================

kg_stats._toolset = "utility"
kg_search._toolset = "utility"
kg_entity_detail._toolset = "utility"
kg_communities._toolset = "utility"
kg_quality._toolset = "utility"
