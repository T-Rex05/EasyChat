"""
Claim 提取器

从文本中提取事实陈述（Claim）

Claim 是不同于实体和关系的信息单元：
- Entity: 人/物/概念
- Relation: 实体间关系
- Claim: 事实陈述

示例：
    文本: "关羽在公元 219 年败走麦城"
    Entity: 关羽(person)、麦城(location)
    Relation: 关羽 → 败走 → 麦城
    Claim: "关羽在公元 219 年败走麦城" (fact)

用途：
- 支持事实性问答
- 支持推理链
- 支持时间旅行查询
"""

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.graphrag.types import (
    Claim,
    ClaimType,
    ClaimStatus,
    ClaimExtractionResult,
)
from backend.utils.log_utils import log

logger = log


class ClaimExtractor:
    """
    Claim 提取器

    使用 LLM 从文本中提取 Claim
    """

    # Claim 提取提示词
    CLAIM_PROMPT = """你是一个知识图谱专家。请从以下文本中提取事实陈述（Claim）。

【输出格式】
以 JSON 格式返回：
{{
  "claims": [
    {{
      "claim_text": "Claim 文本",
      "claim_type": "fact",
      "subject": "主体实体",
      "object": "客体实体",
      "claim_value": "Claim 值",
      "time": "时间属性",
      "confidence": 0.95
    }}
  ]
}}

【Claim 类型】
- fact: 事实 — 有明确时间/地点/数据支撑的客观陈述
- opinion: 观点 — 人物观点、评价或主观判断
- inference: 推论 — 从上下文推断出的结论

【提取规则】
1. **只提取重要陈述**：跳过琐碎的描述，提取对理解故事/主题有意义的信息
2. **保留原始表述**：claim_text 尽量保留原文表述
3. **主体客体明确**：subject 和 object 必须是文本中提到的实体
4. **时间属性提取**：如果文本包含时间信息（日期、年份、朝代），必须提取
5. **置信度评分**：根据文本明确程度打分

【置信度标准】
- 0.9-1.0: 文本明确陈述
- 0.7-0.9: 有合理推断
- 0.5-0.7: 隐含信息
- <0.5: 不确定，不提取

【示例】
输入文本："关羽在公元 219 年败走麦城，最终被东吴擒杀。"
输出：
{{
  "claims": [
    {{
      "claim_text": "关羽在公元 219 年败走麦城",
      "claim_type": "fact",
      "subject": "关羽",
      "object": "麦城",
      "claim_value": "败走",
      "time": "公元 219 年",
      "confidence": 0.95
    }},
    {{
      "claim_text": "关羽被东吴擒杀",
      "claim_type": "fact",
      "subject": "关羽",
      "object": "东吴",
      "claim_value": "擒杀",
      "time": null,
      "confidence": 0.90
    }}
  ]
}}

【注意事项】
1. 每个 Claim 必须有明确的 subject
2. object 可以为空（如"刘备建立了蜀汉" → subject=刘备, object=蜀汉；"天下大乱" → subject=天下, object=null）
3. claim_value 描述主体对客体的作用
4. 如果没有时间信息，time 设为 null
5. 只返回 JSON，不要其他文字

【文本】
{text}"""

    def __init__(self, model: Optional[str] = None, min_confidence: float = 0.5):
        """
        初始化 Claim 提取器

        Args:
            model: 使用的 LLM 模型名称
            min_confidence: 最低置信度阈值
        """
        self._model = model
        self._min_confidence = min_confidence

    def extract(
        self,
        text: str,
        source_chunk_id: Optional[int] = None,
        source_document_id: Optional[int] = None,
    ) -> ClaimExtractionResult:
        """
        从文本中提取 Claim

        Args:
            text: 待提取的文本
            source_chunk_id: 来源文本块 ID
            source_document_id: 来源文档 ID

        Returns:
            ClaimExtractionResult
        """
        start_time = time.time()

        try:
            # 构建提示词
            prompt = self.CLAIM_PROMPT.format(text=text[:2000])

            # 调用 LLM
            from backend.utils.traced_llm import traced_llm
            logger.debug(f"[ClaimExtract] Calling LLM for text length={len(text[:2000])}")

            # 尝试从上下文获取 user_id
            try:
                from backend.hermes_adapter import _CURRENT_USER_ID_CTX
                uid = int(_CURRENT_USER_ID_CTX.get() or 0)
            except Exception:
                uid = 0

            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="graph_claim_extract",
                user_id=uid,
                source="graphrag",
                temperature=0.1,
                max_tokens=4096,
            )

            # 解析响应
            content = resp.content or ""
            claims = self._parse_claims(content)

            # 过滤低置信度
            claims = [c for c in claims if c.confidence >= self._min_confidence]

            # 设置来源信息
            for claim in claims:
                claim.source_chunk_id = source_chunk_id
                claim.source_document_id = source_document_id

            extraction_time = time.time() - start_time

            return ClaimExtractionResult(
                claims=claims,
                source_text=text[:500],
                source_chunk_id=source_chunk_id,
                source_document_id=source_document_id,
                extraction_time=extraction_time,
                model=resp.model or "",
            )

        except Exception as e:
            logger.error(f"[ClaimExtract] 提取失败: {e}")
            return ClaimExtractionResult(
                source_text=text[:500],
                source_chunk_id=source_chunk_id,
                source_document_id=source_document_id,
            )

    def _parse_claims(self, content: str) -> List[Claim]:
        """
        解析 LLM 响应中的 Claim

        Args:
            content: LLM 响应内容

        Returns:
            Claim 列表
        """
        claims = []

        try:
            # 提取 JSON
            json_str = self._extract_json(content)
            if not json_str:
                return claims

            data = json.loads(json_str)
            claim_list = data.get("claims", [])

            for item in claim_list:
                try:
                    claim = Claim(
                        id=f"claim_{uuid.uuid4().hex[:8]}",
                        claim_type=self._parse_claim_type(item.get("claim_type", "fact")),
                        claim_text=item.get("claim_text", ""),
                        subject=item.get("subject", ""),
                        object=item.get("object"),
                        claim_value=item.get("claim_value", ""),
                        time=item.get("time"),
                        confidence=float(item.get("confidence", 0.8)),
                        status=ClaimStatus.ACTIVE,
                    )
                    claims.append(claim)
                except Exception as e:
                    logger.warning(f"[ClaimExtract] 解析 Claim 失败: {e}, item={item}")
                    continue

        except json.JSONDecodeError as e:
            logger.warning(f"[ClaimExtract] JSON 解析失败: {e}")
        except Exception as e:
            logger.error(f"[ClaimExtract] 解析异常: {e}")

        return claims

    def _extract_json(self, content: str) -> Optional[str]:
        """
        从内容中提取 JSON 字符串

        Args:
            content: 原始内容

        Returns:
            JSON 字符串
        """
        # 尝试直接解析
        content = content.strip()
        if content.startswith("{"):
            # 找到最后一个 }
            last_brace = content.rfind("}")
            if last_brace != -1:
                return content[:last_brace + 1]

        # 尝试找 ```json ... ``` 块
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if match:
            return match.group(1).strip()

        return None

    def _parse_claim_type(self, type_str: str) -> ClaimType:
        """
        解析 Claim 类型

        Args:
            type_str: 类型字符串

        Returns:
            ClaimType
        """
        type_str = type_str.lower().strip()
        if type_str in ("fact", "事实"):
            return ClaimType.FACT
        elif type_str in ("opinion", "观点"):
            return ClaimType.OPINION
        elif type_str in ("inference", "推论"):
            return ClaimType.INFERENCE
        else:
            return ClaimType.FACT  # 默认为事实