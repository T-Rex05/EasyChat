"""
证据图谱构建工具

构建 Claim-Evidence 证据图谱，支持四层验证
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from backend.utils.log_utils import log

logger = log


class BuildEvidenceGraphInput(BaseModel):
    """证据图谱构建工具输入"""
    rubric: Dict[str, Any] = Field(description="冻结的 Claim Rubric")
    execution_results: Dict[str, Any] = Field(description="代码执行结果")
    metrics_data: Optional[Dict[str, Any]] = Field(None, description="指标数据")


@tool(args_schema=BuildEvidenceGraphInput)
def build_evidence_graph(
    rubric: Dict[str, Any],
    execution_results: Dict[str, Any],
    metrics_data: Optional[Dict[str, Any]] = None
) -> str:
    """
    构建 Claim-Evidence 证据图谱，支持四层验证。

    使用场景：
    - 论文复现最后一步
    - 需要验证主张是否得到证据支持
    - 生成验证报告

    四层验证结构：
    - Layer 1: Claim（主张）
    - Layer 2: Criterion（准则）
    - Layer 3: Evidence（证据）
    - Layer 4: Judgment（判定）

    返回：
    - 证据图谱 JSON
    - 验证状态
    - 置信度分数
    """
    try:
        # 1. 验证输入
        if not rubric or not isinstance(rubric, dict):
            return json.dumps({
                "error": "rubric 必须是字典",
                "version": "evidence.graph/v1"
            }, ensure_ascii=False)

        if not execution_results or not isinstance(execution_results, dict):
            return json.dumps({
                "error": "execution_results 必须是字典",
                "version": "evidence.graph/v1"
            }, ensure_ascii=False)

        # 检查执行结果是否包含错误
        execution_error = None
        if execution_results.get("error"):
            execution_error = execution_results.get("error", "未知错误")
            logger.warning(f"⚠️ 执行结果包含错误: {execution_error}")
            # 不返回空图谱，而是继续构建，状态会标记为 pending

        # 2. 构建证据图谱
        graph = _build_graph(rubric, execution_results, metrics_data or {})

        # 3. 计算置信度
        confidence = _calculate_confidence(graph)

        # 4. 生成摘要
        summary = _generate_summary(graph, confidence)

        result = {
            "version": "evidence.graph/v1",
            "graph": graph,
            "confidence": confidence,
            "summary": summary,
            "created_at": datetime.now().isoformat()
        }

        # 如果有执行错误，添加到结果中
        if execution_error:
            result["execution_error"] = execution_error
            result["summary"]["execution_status"] = "failed"
            logger.info(f"✅ 证据图谱构建完成（含执行错误）: 置信度 {confidence['overall']:.2%}")
        else:
            logger.info(f"✅ 证据图谱构建完成: 置信度 {confidence['overall']:.2%}")

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"❌ 证据图谱构建失败: {e}", exc_info=True)
        # 返回标准错误格式，确保前端能正确解析
        return json.dumps({
            "error": str(e),
            "error_type": type(e).__name__,
            "version": "evidence.graph/v1",
            "confidence": {
                "overall": 0.0,
                "verified": 0,
                "failed": 0,
                "inconclusive": 0,
                "total": 0
            },
            "summary": {
                "status": "error",
                "message": f"证据图谱构建失败: {e}",
                "recommendation": "请查看后端日志获取详细错误信息"
            }
        }, ensure_ascii=False)


def _build_graph(
    rubric: Dict[str, Any],
    execution_results: Dict[str, Any],
    metrics_data: Dict[str, Any]
) -> Dict[str, Any]:
    """构建证据图谱"""
    graph = {
        "nodes": [],
        "edges": [],
        "layers": {
            "claims": [],
            "criteria": [],
            "evidence": [],
            "judgments": []
        }
    }

    claims = rubric.get("claims", [])

    for claim in claims:
        # Layer 1: Claim
        claim_node = {
            "id": claim.get("id"),
            "type": "claim",
            "title": claim.get("title"),
            "statement": claim.get("statement"),
            "source_locator": claim.get("source_locator"),
            "claim_type": claim.get("claim_type"),
            "importance": claim.get("importance", 0.5),
            "status": "pending"
        }
        graph["nodes"].append(claim_node)
        graph["layers"]["claims"].append(claim_node["id"])

        # Layer 2: Criteria
        criteria = claim.get("criteria", [])
        for criterion in criteria:
            criterion_node = {
                "id": criterion.get("id"),
                "type": "criterion",
                "description": criterion.get("description"),
                "metric_name": criterion.get("metric_name"),
                "expected_value": criterion.get("expected_value"),
                "tolerance": criterion.get("tolerance"),
                "required_evidence": criterion.get("required_evidence", []),
                "verification_method": criterion.get("verification_method"),
                "status": "pending"
            }
            graph["nodes"].append(criterion_node)
            graph["layers"]["criteria"].append(criterion_node["id"])

            # Edge: Claim -> Criterion
            graph["edges"].append({
                "source": claim_node["id"],
                "target": criterion_node["id"],
                "type": "has_criterion"
            })

            # Layer 3: Evidence
            evidence_node = _collect_evidence(
                criterion,
                execution_results,
                metrics_data
            )

            if evidence_node:
                graph["nodes"].append(evidence_node)
                graph["layers"]["evidence"].append(evidence_node["id"])

                # Edge: Criterion -> Evidence
                graph["edges"].append({
                    "source": criterion_node["id"],
                    "target": evidence_node["id"],
                    "type": "supported_by"
                })

                # Layer 4: Judgment
                judgment_node = _make_judgment(criterion_node, evidence_node)

                graph["nodes"].append(judgment_node)
                graph["layers"]["judgments"].append(judgment_node["id"])

                # Edge: Evidence -> Judgment
                graph["edges"].append({
                    "source": evidence_node["id"],
                    "target": judgment_node["id"],
                    "type": "judged_as"
                })

                # 更新状态
                criterion_node["status"] = judgment_node["status"]
                if judgment_node["status"] == "verified":
                    claim_node["status"] = "partially_verified"

    # 更新 Claim 最终状态
    _update_claim_status(graph)

    return graph


def _collect_evidence(
    criterion: Dict[str, Any],
    execution_results: Dict[str, Any],
    metrics_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """收集证据"""
    required = criterion.get("required_evidence", [])
    metric_name = criterion.get("metric_name", "")

    evidence = {
        "id": f"{criterion['id']}.evidence",
        "type": "evidence",
        "collected_at": datetime.now().isoformat(),
        "sources": []
    }

    # 检查是否有实际执行结果
    has_execution = execution_results and (
        execution_results.get("results") or
        execution_results.get("metrics") or
        execution_results.get("output") or
        execution_results.get("status") not in [None, "no_execution", "skipped"]
    )

    if has_execution:
        # 1. 从执行结果收集
        if "run" in required:
            run_evidence = _extract_run_evidence(execution_results)
            if run_evidence:
                evidence["sources"].append(run_evidence)

        # 2. 从指标数据收集
        if "metrics" in required and metric_name:
            metric_evidence = _extract_metric_evidence(metrics_data, metric_name)
            if metric_evidence:
                evidence["sources"].append(metric_evidence)

        # 3. 从执行日志收集
        if "benchmark" in required:
            benchmark_evidence = _extract_benchmark_evidence(execution_results)
            if benchmark_evidence:
                evidence["sources"].append(benchmark_evidence)

        # 如果没有收集到任何证据
        if not evidence["sources"]:
            evidence["status"] = "missing"
            evidence["value"] = None
        else:
            evidence["status"] = "collected"
            # 提取主要值
            evidence["value"] = _extract_primary_value(evidence["sources"], metric_name)
    else:
        # 没有实际执行结果，创建待定状态的证据
        evidence["status"] = "pending"
        evidence["value"] = None
        evidence["required_evidence"] = required
        evidence["metric_name"] = metric_name
        evidence["message"] = "等待代码执行以收集证据"

    return evidence


def _extract_run_evidence(execution_results: Dict) -> Optional[Dict]:
    """提取运行证据"""
    if execution_results.get("success"):
        return {
            "type": "run",
            "status": "success",
            "output": execution_results.get("output", "")[:500],
            "timestamp": execution_results.get("timestamp", datetime.now().isoformat())
        }
    return None


def _extract_metric_evidence(metrics_data: Dict, metric_name: str) -> Optional[Dict]:
    """提取指标证据"""
    if metric_name in metrics_data:
        return {
            "type": "metrics",
            "metric_name": metric_name,
            "value": metrics_data[metric_name],
            "timestamp": datetime.now().isoformat()
        }
    return None


def _extract_benchmark_evidence(execution_results: Dict) -> Optional[Dict]:
    """提取 Benchmark 证据"""
    output = execution_results.get("output", "")

    # 简单提取（实际可使用正则或 LLM）
    if "benchmark" in output.lower() or "score" in output.lower():
        return {
            "type": "benchmark",
            "raw_output": output[:500],
            "timestamp": datetime.now().isoformat()
        }
    return None


def _extract_primary_value(sources: List[Dict], metric_name: str) -> Optional[Any]:
    """提取主要值"""
    # 优先从指标数据提取
    for source in sources:
        if source.get("type") == "metrics" and source.get("metric_name") == metric_name:
            return source.get("value")

    # 否则从其他来源提取
    for source in sources:
        if source.get("value") is not None:
            return source.get("value")

    return None


def _make_judgment(criterion: Dict, evidence: Dict) -> Dict:
    """判定证据是否满足准则"""
    expected_value = criterion.get("expected_value")
    tolerance = criterion.get("tolerance")
    actual_value = evidence.get("value")

    judgment = {
        "id": f"{evidence['id']}.judgment",
        "type": "judgment",
        "criterion_id": criterion["id"],
        "evidence_id": evidence["id"],
        "judged_at": datetime.now().isoformat()
    }

    # 如果证据待定（等待执行）
    if evidence.get("status") == "pending":
        judgment["status"] = "pending"
        judgment["reason"] = "等待代码执行以收集证据"
        return judgment

    # 如果缺少证据
    if evidence.get("status") == "missing":
        judgment["status"] = "inconclusive"
        judgment["reason"] = "缺少证据"
        return judgment

    # 如果没有期望值（定性主张）
    if expected_value is None:
        judgment["status"] = "manual_review_required"
        judgment["reason"] = "定性主张需要人工审查"
        return judgment

    # 如果没有实际值
    if actual_value is None:
        judgment["status"] = "inconclusive"
        judgment["reason"] = "无法从证据中提取值"
        return judgment

    # 量化判定
    try:
        expected = float(expected_value)
        actual = float(actual_value)

        # 计算容差
        if isinstance(tolerance, (int, float)):
            tolerance_value = float(tolerance)
        elif isinstance(tolerance, str) and "%" in tolerance:
            # 百分比容差
            tolerance_value = expected * float(tolerance.replace("%", "")) / 100
        else:
            tolerance_value = 0

        # 判断
        if abs(actual - expected) <= tolerance_value:
            judgment["status"] = "verified"
            judgment["reason"] = f"实际值 {actual} 在容差范围内（期望 {expected} ± {tolerance_value}）"
        else:
            judgment["status"] = "failed"
            judgment["reason"] = f"实际值 {actual} 超出容差范围（期望 {expected} ± {tolerance_value}）"

        judgment["expected_value"] = expected
        judgment["actual_value"] = actual
        judgment["tolerance"] = tolerance_value
        judgment["deviation"] = abs(actual - expected)

    except (ValueError, TypeError) as e:
        judgment["status"] = "error"
        judgment["reason"] = f"值比较失败: {e}"

    return judgment


def _update_claim_status(graph: Dict):
    """更新 Claim 最终状态"""
    claim_nodes = [n for n in graph["nodes"] if n.get("type") == "claim"]

    for claim in claim_nodes:
        # 找到该 Claim 的所有 Criterion
        criterion_edges = [e for e in graph["edges"] if e["source"] == claim["id"] and e["type"] == "has_criterion"]
        criterion_ids = [e["target"] for e in criterion_edges]

        # 统计状态
        criteria = [n for n in graph["nodes"] if n.get("id") in criterion_ids]

        if not criteria:
            claim["status"] = "no_criteria"
            continue

        verified_count = sum(1 for c in criteria if c.get("status") == "verified")
        pending_count = sum(1 for c in criteria if c.get("status") == "pending")
        total_count = len(criteria)

        if verified_count == total_count:
            claim["status"] = "fully_verified"
        elif pending_count == total_count:
            claim["status"] = "pending"
        elif verified_count > 0:
            claim["status"] = "partially_verified"
        elif pending_count > 0:
            claim["status"] = "partially_pending"
        else:
            claim["status"] = "failed"


def _calculate_confidence(graph: Dict) -> Dict[str, Any]:
    """计算置信度"""
    judgments = [n for n in graph["nodes"] if n.get("type") == "judgment"]

    if not judgments:
        return {
            "overall": 0.0,
            "verified": 0,
            "failed": 0,
            "inconclusive": 0,
            "pending": 0,
            "total": 0
        }

    verified = sum(1 for j in judgments if j.get("status") == "verified")
    failed = sum(1 for j in judgments if j.get("status") == "failed")
    inconclusive = sum(1 for j in judgments if j.get("status") in ["inconclusive", "manual_review_required"])
    pending = sum(1 for j in judgments if j.get("status") == "pending")
    total = len(judgments)

    overall = verified / total if total > 0 else 0

    return {
        "overall": overall,
        "verified": verified,
        "failed": failed,
        "inconclusive": inconclusive,
        "pending": pending,
        "total": total
    }


def _generate_summary(graph: Dict, confidence: Dict) -> Dict[str, Any]:
    """生成摘要"""
    claims = [n for n in graph["nodes"] if n.get("type") == "claim"]

    fully_verified = sum(1 for c in claims if c.get("status") == "fully_verified")
    partially_verified = sum(1 for c in claims if c.get("status") == "partially_verified")
    pending = sum(1 for c in claims if c.get("status") in ["pending", "partially_pending"])
    failed = sum(1 for c in claims if c.get("status") == "failed")

    return {
        "total_claims": len(claims),
        "fully_verified": fully_verified,
        "partially_verified": partially_verified,
        "pending": pending,
        "failed": failed,
        "confidence_score": confidence["overall"],
        "grade": _calculate_grade(confidence["overall"]),
        "recommendation": _generate_recommendation(confidence["overall"])
    }


def _calculate_grade(confidence: float) -> str:
    """计算等级"""
    if confidence >= 0.9:
        return "A+"
    elif confidence >= 0.8:
        return "A"
    elif confidence >= 0.7:
        return "B"
    elif confidence >= 0.6:
        return "C"
    else:
        return "D"


def _generate_recommendation(confidence: float) -> str:
    """生成建议"""
    if confidence >= 0.9:
        return "论文复现成功，结果高度可信"
    elif confidence >= 0.8:
        return "论文复现基本成功，建议关注少数未验证项"
    elif confidence >= 0.7:
        return "论文复现部分成功，需要进一步调试"
    elif confidence >= 0.6:
        return "论文复现存在较多问题，建议重新审查"
    else:
        return "论文复现失败，建议从其他来源寻找代码"


# 注册到 Hermes 工具系统
def register_build_evidence_graph_tool():
    """注册证据图谱构建工具到 Hermes"""
    from backend.tools.tools_decorator import get_project_tools

    tools = get_project_tools()
    if build_evidence_graph not in tools:
        build_evidence_graph._toolset = "paper_repro"  # 论文复现工具集
        tools.append(build_evidence_graph)
        logger.info("✅ 注册 build_evidence_graph 工具")


# 自动注册
try:
    register_build_evidence_graph_tool()
except Exception as e:
    logger.warning(f"自动注册工具失败: {e}")