"""
Claim Rubric 提取工具

从论文中提取主张和判定准则，生成冻结 Rubric
"""

import json
import hashlib
from typing import Dict, Any
from datetime import datetime
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from backend.utils.log_utils import log
from .common_utils import get_llm_instance

logger = log


def _get_llm():
    """获取 LLM 实例（使用场景路由）"""
    try:
        return get_llm_instance(scene="paper_claim")
    except Exception as e:
        logger.warning(f"LLM 初始化失败: {e}")
        return None


class ClaimRubricInput(BaseModel):
    """Claim Rubric 提取工具输入"""
    parsed_paper: Dict[str, Any] = Field(description="解析后的论文")
    max_claims: int = Field(10, description="最多提取的主张数")


@tool(args_schema=ClaimRubricInput)
def extract_claim_rubric(
    parsed_paper: Dict[str, Any],
    max_claims: int = 10
) -> str:
    """
    从解析后的论文中提取主张和判定准则，生成冻结 Rubric。

    使用场景：
    - 论文解析后的第二步
    - 需要定义验收标准
    - 需要冻结验收标准

    返回：
    - Frozen Claim Rubric (JSON)
    - 每个主张包含多个独立准则
    - 每个准则定义所需证据类型
    """
    try:
        # 1. 验证输入
        if not parsed_paper or not isinstance(parsed_paper, dict):
            return json.dumps({
                "error": "parsed_paper 必须是字典",
                "version": "claim.rubric/v1"
            }, ensure_ascii=False)

        # 2. 准备 LLM 提示词
        prompt = _build_extraction_prompt(parsed_paper, max_claims)

        # 3. 调用 LLM
        model = _get_llm()
        if not model:
            return json.dumps({
                "error": "LLM 不可用",
                "version": "claim.rubric/v1"
            }, ensure_ascii=False)

        response = model.invoke(prompt)

        # 尝试解析 JSON，处理转义字符问题
        try:
            raw_claims = json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败，尝试修复转义字符: {e}")
            # 尝试修复常见的转义字符问题
            fixed_content = response.content.replace("\\", "\\\\")
            try:
                raw_claims = json.loads(fixed_content)
            except json.JSONDecodeError:
                # 如果还是失败，尝试提取 JSON 块
                import re
                json_match = re.search(r'\{[\s\S]*\}', response.content)
                if json_match:
                    raw_claims = json.loads(json_match.group())
                else:
                    raise e

        # 4. 后端规范化
        rubric = _normalize_rubric(raw_claims, parsed_paper)

        # 5. 计算哈希（在添加 sha256 字段之前）
        rubric_copy = {k: v for k, v in rubric.items() if k != "sha256"}
        rubric_json = json.dumps(rubric_copy, sort_keys=True, ensure_ascii=False)
        rubric["sha256"] = hashlib.sha256(rubric_json.encode("utf-8")).hexdigest()

        # 6. 存储到记忆系统
        _store_rubric(rubric)

        logger.info(f"✅ Rubric 冻结完成: {len(rubric['claims'])} 个主张, SHA-256: {rubric['sha256'][:12]}...")
        return json.dumps(rubric, ensure_ascii=False, indent=2)

    except json.JSONDecodeError as e:
        logger.error(f"❌ LLM 输出解析失败: {e}")
        return json.dumps({
            "error": f"LLM 输出解析失败: {e}",
            "version": "claim.rubric/v1"
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ Rubric 提取失败: {e}", exc_info=True)
        return json.dumps({
            "error": str(e),
            "version": "claim.rubric/v1"
        }, ensure_ascii=False)


def _build_extraction_prompt(parsed_paper: Dict, max_claims: int) -> str:
    """构建 LLM 提取提示词"""
    title = parsed_paper.get("title", "")
    abstract = parsed_paper.get("abstract", "")
    methods = parsed_paper.get("methods", "")
    experiments = parsed_paper.get("experiments", [])
    claims = parsed_paper.get("claims", [])

    # 格式化实验结果
    experiments_text = "\n".join(experiments) if isinstance(experiments, list) else str(experiments)

    # 格式化主张
    claims_text = "\n".join(f"- {c}" for c in claims) if claims else "未识别"

    return f"""
你是一个学术论文研究助手。请从以下论文中提取可验证的主张和判定准则。

论文标题：{title}

摘要：
{abstract}

方法：
{methods}

实验结果：
{experiments_text}

已识别的主张：
{claims_text}

请按以下格式输出 JSON：

{{
  "claims": [
    {{
      "title": "主张标题（简短）",
      "statement": "主张陈述（原文）",
      "source_locator": "论文位置（如 Table 1, Section 3.2）",
      "claim_type": "quantitative 或 qualitative",
      "importance": 0.9,
      "criteria": [
        {{
          "description": "准则描述",
          "metric_name": "指标名称（如 BLEU, Accuracy）",
          "expected_value": 期望值（数值或字符串）,
          "tolerance": 容差范围（数值或百分比）,
          "required_evidence": ["run", "metrics", "benchmark"]
        }}
      ]
    }}
  ]
}}

要求：
1. 提取 {max_claims} 个最重要的主张
2. 每个主张至少有 1 个判定准则
3. 量化主张（quantitative）必须包含 expected_value 和 tolerance
4. 定性主张（qualitative）可以没有具体数值
5. importance 范围：0.0-1.0（越重要越接近 1.0）
6. required_evidence 可以是：
   - "run": 运行结果
   - "metrics": 指标数据
   - "benchmark": Benchmark 结果
   - "code": 代码实现
   - "config": 配置文件
7. 主张类型说明：
   - quantitative: 量化指标（如准确率、BLEU 分数）
   - qualitative: 定性结论（如方法优势、架构设计）

示例：
{{
  "claims": [
    {{
      "title": "Translation Quality",
      "statement": "The Transformer achieves 28.4 BLEU on WMT 2014.",
      "source_locator": "Table 1",
      "claim_type": "quantitative",
      "importance": 0.9,
      "criteria": [
        {{
          "description": "Evaluate BLEU score on WMT 2014 test set",
          "metric_name": "BLEU",
          "expected_value": 28.4,
          "tolerance": 1.0,
          "required_evidence": ["run", "metrics"]
        }}
      ]
    }}
  ]
}}
"""


def _normalize_rubric(raw_claims: Dict, parsed_paper: Dict) -> Dict:
    """后端规范化 Rubric"""
    rubric = {
        "version": "claim.rubric/v1",
        "paper_title": parsed_paper.get("title", ""),
        "source_artifact": "parsed_paper",
        "created_at": datetime.now().isoformat(),
        "claims": []
    }

    # 提取主张列表
    claims_list = raw_claims.get("claims", [])

    for i, raw_claim in enumerate(claims_list[:10]):  # 最多 10 个主张
        # 规范化每个主张
        claim = {
            "id": f"claim-{i+1:03d}",
            "title": str(raw_claim.get("title", "")).strip(),
            "statement": str(raw_claim.get("statement", "")).strip(),
            "source_locator": str(raw_claim.get("source_locator", "")).strip(),
            "claim_type": _normalize_claim_type(raw_claim.get("claim_type")),
            "importance": float(raw_claim.get("importance", 0.5)),
            "criteria": []
        }

        # 规范化每个准则
        criteria_list = raw_claim.get("criteria", [])
        for j, raw_crit in enumerate(criteria_list):
            criterion = {
                "id": f"claim-{i+1:03d}.criterion-{j+1:02d}",
                "description": str(raw_crit.get("description", "")).strip(),
                "metric_name": str(raw_crit.get("metric_name", "")).strip(),
                "expected_value": raw_crit.get("expected_value"),
                "tolerance": raw_crit.get("tolerance"),
                "required_evidence": raw_crit.get("required_evidence", []),
                "verification_method": "automatic" if raw_crit.get("expected_value") is not None else "manual"
            }
            claim["criteria"].append(criterion)

        rubric["claims"].append(claim)

    return rubric


def _normalize_claim_type(claim_type: Any) -> str:
    """规范化主张类型"""
    if not claim_type:
        return "quantitative"

    claim_type = str(claim_type).lower().strip()

    if claim_type in ["quantitative", "quantitative", "量化"]:
        return "quantitative"
    elif claim_type in ["qualitative", "定性"]:
        return "qualitative"
    else:
        return "quantitative"


def _store_rubric(rubric: Dict):
    """存储 Rubric 到记忆系统"""
    try:
        from backend.memory.artifact_store import ArtifactStore
        from backend.hooks import get_hook_context

        # 尝试获取用户和会话信息
        context = get_hook_context()
        if context and hasattr(context, 'user_id') and hasattr(context, 'thread_id'):
            store = ArtifactStore(context.user_id, context.thread_id)
            store.store_artifact("claim_rubric", rubric, {"type": "rubric"})
            logger.info(f"✅ Rubric 存储到记忆系统")
        else:
            logger.warning("无法获取上下文，跳过存储")

    except ImportError:
        logger.warning("未找到记忆系统模块，跳过存储")

    except Exception as e:
        logger.warning(f"存储 Rubric 失败: {e}")


def validate_rubric(rubric: Dict) -> bool:
    """验证 Rubric 完整性"""
    # 检查版本
    if rubric.get("version") != "claim.rubric/v1":
        return False

    # 检查哈希
    if not rubric.get("sha256"):
        return False

    # 检查主张
    claims = rubric.get("claims", [])
    if not claims:
        return False

    # 检查每个主张的结构
    for claim in claims:
        if not claim.get("id"):
            return False
        if not claim.get("title"):
            return False
        if not claim.get("statement"):
            return False

        # 检查每个准则
        for criterion in claim.get("criteria", []):
            if not criterion.get("id"):
                return False
            if not criterion.get("description"):
                return False

    return True


# 注册到 Hermes 工具系统
def register_claim_rubric_tool():
    """注册 Claim Rubric 工具到 Hermes"""
    from backend.tools.tools_decorator import get_project_tools

    tools = get_project_tools()
    if extract_claim_rubric not in tools:
        extract_claim_rubric._toolset = "paper_repro"  # 论文复现工具集
        tools.append(extract_claim_rubric)
        logger.info("✅ 注册 extract_claim_rubric 工具")


# 自动注册
try:
    register_claim_rubric_tool()
except Exception as e:
    logger.warning(f"自动注册工具失败: {e}")