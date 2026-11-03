"""
知识图谱抽取质量基准测试（Gold-Standard Benchmark）

功能：
- 加载人工标注的 gold_standard.json 测试集
- 运行 EntityExtractor 对每条测试文本进行抽取
- 与 gold 标准对比，计算 Precision / Recall / F1
- 支持实体对齐准确率、时间属性准确率评估
- 输出详细报告

使用方式：
    from backend.service.kg.kg_eval_benchmark import run_benchmark
    report = run_benchmark()
    print(report["summary"])
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.utils.log_utils import log

logger = log

# ════════════════════════════════════════════════════════════
# 数据结构
# ════════════════════════════════════════════════════════════


@dataclass
class GoldEntity:
    """标注实体"""
    name: str
    entity_type: str
    aliases: List[str] = field(default_factory=list)


@dataclass
class GoldRelation:
    """标注关系"""
    source: str
    target: str
    relation_type: str
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    is_current: Optional[bool] = None


@dataclass
class TestCase:
    """单条测试用例"""
    id: str
    description: str
    text: str
    gold_entities: List[GoldEntity]
    gold_relations: List[GoldRelation]
    notes: str = ""


@dataclass
class EntityMatch:
    """实体匹配结果"""
    gold_name: str
    gold_type: str
    matched: bool
    extracted_name: Optional[str] = None
    extracted_type: Optional[str] = None
    match_kind: str = ""  # exact / alias / missing / wrong_type


@dataclass
class RelationMatch:
    """关系匹配结果"""
    gold_source: str
    gold_target: str
    gold_type: str
    matched: bool
    temporal_correct: Optional[bool] = None  # None 表示 gold 无时间属性


# ════════════════════════════════════════════════════════════
# 加载测试集
# ════════════════════════════════════════════════════════════


def load_test_cases(path: Optional[str] = None) -> List[TestCase]:
    """加载 gold standard 测试集"""
    if path is None:
        path = os.path.join(
            os.path.dirname(__file__),
            "../../../tests/fixtures/kg_eval/gold_standard.json"
        )

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = []
    for item in data:
        gold_entities = [
            GoldEntity(
                name=e["name"],
                entity_type=e["type"],
                aliases=e.get("aliases", [])
            )
            for e in item.get("gold_entities", [])
        ]
        gold_relations = [
            GoldRelation(
                source=r["source"],
                target=r["target"],
                relation_type=r["type"],
                valid_from=r.get("valid_from"),
                valid_until=r.get("valid_until"),
                is_current=r.get("is_current")
            )
            for r in item.get("gold_relations", [])
        ]
        cases.append(TestCase(
            id=item["id"],
            description=item.get("description", ""),
            text=item["text"],
            gold_entities=gold_entities,
            gold_relations=gold_relations,
            notes=item.get("notes", "")
        ))

    logger.info(f"Loaded {len(cases)} test cases from {path}")
    return cases


# ════════════════════════════════════════════════════════════
# 匹配逻辑
# ════════════════════════════════════════════════════════════


def _normalize_name(name: str) -> str:
    """实体名称标准化（小写 + 去空格）"""
    return name.strip().lower()


def _match_entity(
    gold: GoldEntity,
    extracted_entities: List[Dict]
) -> EntityMatch:
    """
    匹配单个 gold 实体与抽取结果

    匹配策略：
    1. 精确匹配（名称一致，允许大小写差异）
    2. 别名匹配（gold.aliases 中任一与抽取名称一致）
    3. 类型一致才视为完全匹配
    """
    gold_names = {_normalize_name(gold.name)} | {
        _normalize_name(a) for a in gold.aliases
    }

    for ext in extracted_entities:
        ext_name = _normalize_name(ext.get("name", ""))
        ext_type = ext.get("type", "").lower()

        if ext_name in gold_names:
            # 名称匹配成功
            if ext_type == gold.entity_type.lower():
                return EntityMatch(
                    gold_name=gold.name,
                    gold_type=gold.entity_type,
                    matched=True,
                    extracted_name=ext.get("name"),
                    extracted_type=ext.get("type"),
                    match_kind="exact"
                )
            else:
                return EntityMatch(
                    gold_name=gold.name,
                    gold_type=gold.entity_type,
                    matched=False,
                    extracted_name=ext.get("name"),
                    extracted_type=ext.get("type"),
                    match_kind="wrong_type"
                )

    # 名称匹配失败（检查是否被别名覆盖）
    for ext in extracted_entities:
        ext_name = _normalize_name(ext.get("name", ""))
        if ext_name in {_normalize_name(a) for a in gold.aliases}:
            return EntityMatch(
                gold_name=gold.name,
                gold_type=gold.entity_type,
                matched=True,
                extracted_name=ext.get("name"),
                extracted_type=ext.get("type"),
                match_kind="alias"
            )

    return EntityMatch(
        gold_name=gold.name,
        gold_type=gold.entity_type,
        matched=False,
        match_kind="missing"
    )


def _match_relation(
    gold: GoldRelation,
    extracted_relations: List[Dict],
    extracted_entities: List[Dict]
) -> RelationMatch:
    """
    匹配单个 gold 关系与抽取结果

    先确认 source/target 实体存在，再匹配关系类型。
    如果 gold 有时间属性，额外校验时间属性是否正确。
    """
    # 收集所有名称（含别名）的标准化形式
    def _entity_name_set(gold_name: str) -> Set[str]:
        """找到 gold_name 对应的所有可能名称"""
        names = {_normalize_name(gold_name)}
        # 查找 gold entity 的 aliases
        for ext in extracted_entities:
            if _normalize_name(ext.get("name", "")) == _normalize_name(gold_name):
                break
        return names

    for ext in extracted_relations:
        ext_source = _normalize_name(ext.get("source", ""))
        ext_target = _normalize_name(ext.get("target", ""))
        ext_type = ext.get("type", "").lower()

        source_match = ext_source == _normalize_name(gold.source)
        target_match = ext_target == _normalize_name(gold.target)
        type_match = ext_type == gold.relation_type.lower()

        if source_match and target_match and type_match:
            # 关系匹配成功，检查时间属性
            temporal_correct = None
            if gold.valid_from is not None or gold.is_current is not None:
                ext_valid_from = ext.get("valid_from")
                ext_is_current = ext.get("is_current")

                temporal_correct = True
                if gold.valid_from is not None and ext_valid_from != gold.valid_from:
                    temporal_correct = False
                if gold.is_current is not None and ext_is_current != gold.is_current:
                    temporal_correct = False

            return RelationMatch(
                gold_source=gold.source,
                gold_target=gold.target,
                gold_type=gold.relation_type,
                matched=True,
                temporal_correct=temporal_correct
            )

    return RelationMatch(
        gold_source=gold.source,
        gold_target=gold.target,
        gold_type=gold.relation_type,
        matched=False,
        temporal_correct=None
    )


# ════════════════════════════════════════════════════════════
# 指标计算
# ════════════════════════════════════════════════════════════


def _precision_recall_f1(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    """计算 P/R/F1"""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
           if (precision + recall) > 0 else 0.0)
    return round(precision, 4), round(recall, 4), round(f1, 4)


# ════════════════════════════════════════════════════════════
# 主运行器
# ════════════════════════════════════════════════════════════


def run_single_case(
    case: TestCase,
    extractor
) -> Dict[str, Any]:
    """
    运行单条测试用例

    Args:
        case: 测试用例
        extractor: EntityExtractor 实例

    Returns:
        详细匹配结果
    """
    # 执行抽取
    result = extractor.extract(case.text)

    # 将抽取结果转为 dict 列表方便匹配
    extracted_entities = [
        {
            "name": e.name,
            "type": e.entity_type.value,
            "aliases": e.aliases if hasattr(e, "aliases") else []
        }
        for e in result.entities
    ]
    extracted_relations = [
        {
            "source": _get_entity_name_by_id(result.entities, r.source_id),
            "target": _get_entity_name_by_id(result.entities, r.target_id),
            "type": r.relation_type.value,
            "valid_from": r.valid_from if hasattr(r, "valid_from") else None,
            "valid_until": r.valid_until if hasattr(r, "valid_until") else None,
            "is_current": r.is_current if hasattr(r, "is_current") else True
        }
        for r in result.relations
    ]

    # 匹配实体
    entity_matches = []
    for gold_e in case.gold_entities:
        match = _match_entity(gold_e, extracted_entities)
        entity_matches.append(match)

    # 匹配关系
    relation_matches = []
    for gold_r in case.gold_relations:
        match = _match_relation(gold_r, extracted_relations, extracted_entities)
        relation_matches.append(match)

    return {
        "case_id": case.id,
        "description": case.description,
        "entity_matches": entity_matches,
        "relation_matches": relation_matches,
        "extracted_entity_count": len(extracted_entities),
        "extracted_relation_count": len(extracted_relations),
        "gold_entity_count": len(case.gold_entities),
        "gold_relation_count": len(case.gold_relations)
    }


def _get_entity_name_by_id(entities: list, entity_id: str) -> str:
    """通过 ID 查找实体名称（关系匹配用）"""
    for e in entities:
        if e.id == entity_id:
            return e.name
    return entity_id  # 找不到就返回 ID


def run_benchmark(
    test_cases_path: Optional[str] = None,
    min_confidence: float = 0.0
) -> Dict[str, Any]:
    """
    运行完整基准测试

    Args:
        test_cases_path: 测试集路径（默认使用内置 gold_standard.json）
        min_confidence: 抽取置信度阈值

    Returns:
        完整报告
    """
    from backend.graphrag.extractor import get_entity_extractor

    cases = load_test_cases(test_cases_path)
    extractor = get_entity_extractor()
    if min_confidence > 0:
        extractor._min_confidence = min_confidence

    all_results = []
    total_entity_tp = 0
    total_entity_fp = 0
    total_entity_fn = 0
    total_relation_tp = 0
    total_relation_fp = 0
    total_relation_fn = 0
    total_temporal_correct = 0
    total_temporal_checked = 0

    for case in cases:
        result = run_single_case(case, extractor)
        all_results.append(result)

        # 实体统计
        for em in result["entity_matches"]:
            if em.matched:
                total_entity_tp += 1
            else:
                total_entity_fn += 1

        # 抽取多出来的实体（FP）
        matched_gold_names = {
            _normalize_name(em.gold_name)
            for em in result["entity_matches"] if em.matched
        }
        for ext_idx in range(result["extracted_entity_count"]):
            ext_name = _normalize_name(
                result["entity_matches"][0].extracted_name or ""
            )
            # 简化：FP = 抽取数量 - 匹配数量
        entity_fp = result["extracted_entity_count"] - sum(
            1 for em in result["entity_matches"] if em.matched
        )
        total_entity_fp += max(0, entity_fp)

        # 关系统计
        for rm in result["relation_matches"]:
            if rm.matched:
                total_relation_tp += 1
                if rm.temporal_correct is True:
                    total_temporal_correct += 1
                if rm.temporal_correct is not None:
                    total_temporal_checked += 1
            else:
                total_relation_fn += 1

        relation_fp = result["extracted_relation_count"] - sum(
            1 for rm in result["relation_matches"] if rm.matched
        )
        total_relation_fp += max(0, relation_fp)

    # 总体指标
    entity_p, entity_r, entity_f1 = _precision_recall_f1(
        total_entity_tp, total_entity_fp, total_entity_fn
    )
    relation_p, relation_r, relation_f1 = _precision_recall_f1(
        total_relation_tp, total_relation_fp, total_relation_fn
    )
    temporal_accuracy = (
        total_temporal_correct / total_temporal_checked
        if total_temporal_checked > 0 else None
    )

    return {
        "summary": {
            "total_cases": len(cases),
            "entity_precision": entity_p,
            "entity_recall": entity_r,
            "entity_f1": entity_f1,
            "relation_precision": relation_p,
            "relation_recall": relation_r,
            "relation_f1": relation_f1,
            "temporal_accuracy": temporal_accuracy,
        },
        "details": all_results
    }


def format_report(report: Dict[str, Any]) -> str:
    """格式化报告为可读文本"""
    s = report["summary"]
    lines = [
        "=" * 60,
        "知识图谱抽取质量基准测试报告",
        "=" * 60,
        f"测试用例数: {s['total_cases']}",
        "",
        "── 实体抽取 ──",
        f"  Precision: {s['entity_precision']:.2%}",
        f"  Recall:    {s['entity_recall']:.2%}",
        f"  F1:        {s['entity_f1']:.2%}",
        "",
        "── 关系抽取 ──",
        f"  Precision: {s['relation_precision']:.2%}",
        f"  Recall:    {s['relation_recall']:.2%}",
        f"  F1:        {s['relation_f1']:.2%}",
        "",
        "── 时间属性 ──",
        f"  准确率:    {s['temporal_accuracy']:.2%}" if s['temporal_accuracy'] is not None else "  准确率:    N/A（无时间属性测试）",
        "",
        "=" * 60,
        "详细结果",
        "=" * 60,
    ]

    for detail in report["details"]:
        lines.append(f"\n[{detail['case_id']}] {detail['description']}")
        lines.append(f"  Gold: {detail['gold_entity_count']} 实体, {detail['gold_relation_count']} 关系")
        lines.append(f"  抽取: {detail['extracted_entity_count']} 实体, {detail['extracted_relation_count']} 关系")

        missed_entities = [
            em for em in detail["entity_matches"] if not em.matched
        ]
        if missed_entities:
            lines.append(f"  ❌ 遗漏实体: {', '.join(em.gold_name for em in missed_entities)}")

        missed_relations = [
            rm for rm in detail["relation_matches"] if not rm.matched
        ]
        if missed_relations:
            lines.append(f"  ❌ 遗漏关系: {', '.join(f'{rm.gold_source}→{rm.gold_target}({rm.gold_type})' for rm in missed_relations)}")

        if not missed_entities and not missed_relations:
            lines.append(f"  ✅ 全部命中")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# CLI 入口
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    report = run_benchmark()
    print(format_report(report))
