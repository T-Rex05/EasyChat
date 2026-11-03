"""
GraphRAG 实体提取器

使用 LLM 从文本中提取实体和关系
"""

import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.graphrag.types import (
    Entity,
    EntityType,
    Relation,
    RelationType,
    ExtractionResult
)
from backend.utils.log_utils import log

logger = log


class ExtractionLLMError(RuntimeError):
    """LLM 调用失败导致的提取异常（如 429/500），调用方应让事件重试而非标记成功。"""
    pass


# 实体类型映射（中文 -> 英文枚举）
ENTITY_TYPE_MAP = {
    "人物": EntityType.PERSON,
    "人": EntityType.PERSON,
    "人名": EntityType.PERSON,
    "组织": EntityType.ORGANIZATION,
    "公司": EntityType.ORGANIZATION,
    "机构": EntityType.ORGANIZATION,
    "地点": EntityType.LOCATION,
    "位置": EntityType.LOCATION,
    "地方": EntityType.LOCATION,
    "概念": EntityType.CONCEPT,
    "主题": EntityType.CONCEPT,
    "话题": EntityType.CONCEPT,
    "事件": EntityType.EVENT,
    "技能": EntityType.SKILL,
    "能力": EntityType.SKILL,
    "偏好": EntityType.PREFERENCE,
    "喜好": EntityType.PREFERENCE,
    "事实": EntityType.FACT,
    "信息": EntityType.FACT,
    "项目": EntityType.PROJECT,
    "工程": EntityType.PROJECT,
    "工具": EntityType.TOOL,
    "软件": EntityType.TOOL,
    # 英文映射
    "person": EntityType.PERSON,
    "organization": EntityType.ORGANIZATION,
    "org": EntityType.ORGANIZATION,
    "location": EntityType.LOCATION,
    "concept": EntityType.CONCEPT,
    "event": EntityType.EVENT,
    "skill": EntityType.SKILL,
    "preference": EntityType.PREFERENCE,
    "fact": EntityType.FACT,
    "project": EntityType.PROJECT,
    "tool": EntityType.TOOL,
}

# 实体停用词列表（无意义实体，应被过滤）
ENTITY_STOPWORDS = frozenset([
    # 时间词
    "今天", "昨天", "明天", "前天", "后天", "现在", "之前", "之后", "最近", "目前",
    "上午", "下午", "晚上", "早上", "中午", "傍晚",
    "今年", "去年", "明年", "本月", "上月", "下月",
    "今天", "今日", "昨日", "明日", "当日",
    # 代词
    "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "它们",
    "自己", "大家", "别人", "他人", "各位",
    "这", "那", "这个", "那个", "这些", "那些",
    "什么", "哪里", "哪里", "谁", "多少", "几",
    # 量词
    "个", "只", "条", "张", "件", "本", "辆", "台", "套", "盒",
    # 形容词/副词
    "很多", "一些", "所有", "部分", "大部分", "少数", "多数",
    "新的", "旧的", "好的", "坏的", "大的", "小的",
    "非常", "很", "太", "更", "最", "特别", "尤其",
    # 动词
    "是", "有", "做", "说", "看", "想", "用", "来", "去", "能", "会", "要",
    # 通用词
    "东西", "事情", "问题", "情况", "内容", "方面", "地方", "办法",
    "结果", "原因", "过程", "方式", "方法", "意义", "目的",
    # 常见虚词
    "的", "了", "在", "和", "与", "或", "等", "及", "但", "而", "却",
    # 英文停用词
    "today", "yesterday", "tomorrow", "now", "recently", "currently",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "this", "that", "these", "those", "what", "where", "who", "which", "when", "how",
    "some", "many", "all", "most", "few", "several", "other", "another",
    "new", "old", "good", "bad", "big", "small", "large",
    "very", "too", "more", "most", "really", "quite",
    "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "when", "where",
])

# 关系类型映射
RELATION_TYPE_MAP = {
    # 中文
    "认识": RelationType.KNOWS,
    "同事": RelationType.WORKS_WITH,
    "汇报": RelationType.REPORTS_TO,
    "工作于": RelationType.WORKS_AT,
    "就职于": RelationType.WORKS_AT,
    "成员": RelationType.MEMBER_OF,
    "创立": RelationType.FOUNDED,
    "参与": RelationType.WORKS_ON,
    "参与事件": RelationType.WORKS_ON,  # participates_in 映射到 WORKS_ON
    "负责": RelationType.OWNS,
    "使用": RelationType.USES,
    "了解": RelationType.KNOWS_ABOUT,
    "专家": RelationType.EXPERT_IN,
    "学到": RelationType.LEARNED,
    "偏好": RelationType.PREFERS,
    "喜欢": RelationType.PREFERS,
    "不喜欢": RelationType.DISLIKES,
    "导致": RelationType.CAUSED,
    "依赖": RelationType.DEPENDS_ON,
    "相关": RelationType.RELATED_TO,
    "属于": RelationType.PART_OF,
    "对抗": RelationType.RELATED_TO,  # opposes 映射到 RELATED_TO
    "对手": RelationType.RELATED_TO,
    # 英文
    "knows": RelationType.KNOWS,
    "works_with": RelationType.WORKS_WITH,
    "works_at": RelationType.WORKS_AT,
    "member_of": RelationType.MEMBER_OF,
    "works_on": RelationType.WORKS_ON,
    "participates_in": RelationType.WORKS_ON,  # 参与事件
    "uses": RelationType.USES,
    "prefers": RelationType.PREFERS,
    "opposes": RelationType.RELATED_TO,  # 对抗
    "related_to": RelationType.RELATED_TO,
}


class EntityExtractor:
    """
    实体提取器
    
    使用 LLM 从文本中提取实体和关系
    """
    
    # 提取提示词模板（带 Few-Shot 示例和置信度）
    EXTRACTION_PROMPT = """你是一个知识图谱实体提取专家。请从以下文本中提取实体、关系和事实陈述（Claim）。

【输出格式】
以 JSON 格式返回：
{{
  "entities": [
    {{
      "name": "实体名称",
      "aliases": ["别名1", "别名2"],
      "type": "实体类型",
      "description": "简要描述",
      "confidence": 0.95
    }}
  ],
  "relations": [
    {{
      "source": "源实体名称",
      "target": "目标实体名称",
      "type": "关系类型",
      "description": "关系描述",
      "confidence": 0.85,
      "valid_from": "2018-01-01",
      "valid_until": "2020-12-31",
      "is_current": false
    }}
  ],
  "claims": [
    {{
      "claim_text": "事实陈述文本",
      "claim_type": "fact",
      "subject": "主体实体",
      "object": "客体实体",
      "claim_value": "陈述值",
      "time": "时间属性",
      "confidence": 0.90
    }}
  ],
  "coverage_check": [
    {{
      "entity": "实体名称",
      "connected": true
    }}
  ]
}}

**Claim 说明**：从文本中提取重要的事实陈述，不同于实体和关系。
- Entity: 人/物/概念
- Relation: 实体间关系
- Claim: 事实陈述（如"关羽在公元 219 年败走麦城"）

**Claim 类型**：
- fact: 事实 — 有明确时间/地点/数据支撑
- opinion: 观点 — 人物评价或主观判断
- inference: 推论 — 从上下文推断

**coverage_check 说明**：在输出 entities 和 relations 之后，对 entities 中的**每一个**实体逐条检查：该实体是否在 relations 中至少出现了一次（作为 source 或 target）？如果是则 `"connected": true`；如果该实体没有任何关系，则 `"connected": false` 并补充 `"missing_reason"` 字段说明原因（如"仅被列举提及，无具体互动"）。

**这一步非常重要** — 它帮助你发现遗漏。如果你在检查某个实体时发现它没有关系但应该有，请**立即回到 relations 数组补充**该关系，然后再继续检查下一个实体。

【实体类型】
person（人物）、org（组织/公司）、location（地点）、concept（概念）、event（事件）、skill（技能）、preference（偏好）、fact（事实）、project（项目）、tool（工具）

【关系类型】
knows（认识）、works_with（共事）、works_at（任职于）、member_of（成员）、founded（创立）、works_on（参与）、owns（负责）、uses（使用）、knows_about（了解）、expert_in（精通）、prefers（偏好）、dislikes（不喜欢）、caused（导致）、depends_on（依赖）、related_to（相关）、part_of（属于）、participates_in（参与事件）、opposes（对抗）

【事件关系提取规则 — 非常重要！】
**事件必须与参与者建立关系，避免成为孤立节点！**
当提取到事件（event）类型实体时，必须同时提取事件与参与者之间的关系：
- 人物参与事件 → 使用 `participates_in` 关系（source=人物, target=事件）
- 事件中的对手/对抗方 → 使用 `opposes` 关系（source=事件, target=对手）

示例：
文本："刘备、关羽、张飞三英战吕布"
正确提取：
- 实体：刘备(person)、关羽(person)、张飞(person)、吕布(person)、三英战吕布(event)
- 关系：
  - 刘备 → 三英战吕布 (participates_in, "刘备参与三英战吕布")
  - 关羽 → 三英战吕布 (participates_in, "关羽参与三英战吕布")
  - 张飞 → 三英战吕布 (participates_in, "张飞参与三英战吕布")
  - 三英战吕布 → 吕布 (opposes, "三英战吕布的对手")

【置信度标准】
- 0.9-1.0：非常确定（文本中有明确表述）
- 0.7-0.9：较确定（有合理推断但非直接表述）
- 0.5-0.7：不太确定（隐含信息或需要推断）
- <0.5：不确定，不要提取

【时间信息提取】
如果文本中包含时间信息，请在 relations 中提取以下字段：
- valid_from: 生效时间（ISO 8601 格式，如 "2018-01-01"）
- valid_until: 失效时间（ISO 8601 格式，如 "2020-12-31"，null 表示当前有效）
- is_current: 是否当前有效（true/false）

时间判断规则：
- "目前在..."、"现任..." → is_current=true, valid_until=null
- "曾任职..."、"之前..."、"曾任..." → is_current=false
- 有明确时间范围（如"2018-2020年"） → valid_from="2018-01-01", valid_until="2020-12-31", is_current=false
- 没有时间信息 → valid_from=null, valid_until=null, is_current=true（默认当前有效）

【示例】
输入文本："张三在阿里巴巴担任技术总监，他精通 Python 和 Java，之前曾在腾讯工作过（2018-2020年）。"
输出：
{{
  "entities": [
    {{"name": "张三", "aliases": [], "type": "person", "description": "技术总监", "confidence": 0.95}},
    {{"name": "阿里巴巴", "aliases": ["阿里", "Alibaba"], "type": "org", "description": "科技公司", "confidence": 0.95}},
    {{"name": "腾讯", "aliases": ["Tencent"], "type": "org", "description": "科技公司", "confidence": 0.95}},
    {{"name": "Python", "aliases": [], "type": "skill", "description": "编程语言", "confidence": 0.95}},
    {{"name": "Java", "aliases": [], "type": "skill", "description": "编程语言", "confidence": 0.95}}
  ],
  "relations": [
    {{"source": "张三", "target": "阿里巴巴", "type": "works_at", "description": "张三目前在阿里巴巴工作", "confidence": 0.95, "valid_from": null, "valid_until": null, "is_current": true}},
    {{"source": "张三", "target": "Python", "type": "expert_in", "description": "张三精通Python", "confidence": 0.9, "valid_from": null, "valid_until": null, "is_current": true}},
    {{"source": "张三", "target": "Java", "type": "expert_in", "description": "张三精通Java", "confidence": 0.9, "valid_from": null, "valid_until": null, "is_current": true}},
    {{"source": "张三", "target": "腾讯", "type": "works_at", "description": "张三曾在腾讯工作（2018-2020）", "confidence": 0.85, "valid_from": "2018-01-01", "valid_until": "2020-12-31", "is_current": false}}
  ],
  "coverage_check": [
    {{"entity": "张三", "connected": true}},
    {{"entity": "阿里巴巴", "connected": true}},
    {{"entity": "腾讯", "connected": true}},
    {{"entity": "Python", "connected": true}},
    {{"entity": "Java", "connected": true}}
  ]
}}

【注意事项】
1. 每个实体和关系必须附带 confidence 字段（0-1之间的小数）
2. **别名只提取文本中有依据的**（不要凭想象编造）：
   - 仅当文本中明确出现了同一实体的其他称呼时才列为别名。例如文中写了"刘备，字玄德"→ aliases=["玄德"]；"阿里巴巴（以下简称阿里）"→ aliases=["阿里"]
   - 如果文本只出现了"玄德"二字，文中没有提到"刘备"，则 aliases 留空 []，不要自行补充
   - 别名的准确性直接影响实体去重，错误的别名会导致不同实体被错误合并
3. **description 必须包含足够的区分信息**：包含该实体的身份、职位、所属组织等关键上下文。例如"刘备"→ description="蜀汉开国皇帝，字玄德，三国时期蜀汉政权建立者"；不能只写"人物"。description 将用于跨实体的相似度对齐
4. 只提取明确的实体，不要推测不确定的信息
5. 关系类型用英文
6. 如果没有时间信息，valid_from 和 valid_until 设为 null，is_current 设为 true
7. 如果没有实体或关系，返回空数组
8. 只返回 JSON，不要其他文字
9. **关系方向必须准确**：source → target 表示主动方指向被动方。例如"张三任职于阿里巴巴"→ source="张三", target="阿里巴巴", type="works_at"，不能反过来；"甲收购乙"→ source="甲", target="乙", type="acquired"，方向反了语义完全不同
10. **关系完备性 — 同等重要！** 当文本中出现多个实体时，必须逐一检查每个实体与其他所有实体之间的关系，不能只提取最显著的一两条就停止。一句中提及 A 对 B、C、D 分别做了某事，则 A→B、A→C、A→D 三条关系都要提取。遗漏关系会导致图谱断裂，比多提一条低置信度关系的危害更大

【文本】
{text}"""

    def __init__(self, model: Optional[str] = None, min_confidence: float = 0.0):
        """
        初始化提取器

        Args:
            model: 使用的 LLM 模型名称
            min_confidence: 最低置信度阈值，低于此值的实体/关系会被过滤
        """
        self._model = model
        self._min_confidence = min_confidence
    
    def extract(
        self,
        text: str,
        source_memory_id: Optional[int] = None,
        source_document_id: Optional[int] = None,
        source_chunk_id: Optional[int] = None
    ) -> ExtractionResult:
        """
        从文本中提取实体和关系
        
        Args:
            text: 待提取的文本
            source_memory_id: 来源记忆ID（Memory 服务）
            source_document_id: 来源文档ID（KB 服务）
            source_chunk_id: 来源父片ID（KB 服务）
            
        Returns:
            ExtractionResult
        """
        start_time = time.time()

        try:
            # 构建提示词
            prompt = self.EXTRACTION_PROMPT.format(text=text[:2000])  # 限制长度

            # 调用 LLM（通过 traced_llm 自动记录 trace）
            from backend.utils.traced_llm import traced_llm
            logger.debug(f"[Extract] Calling LLM for text length={len(text[:2000])}")
            
            # 尝试从上下文获取 user_id
            try:
                from backend.hermes_adapter import _CURRENT_USER_ID_CTX
                uid = int(_CURRENT_USER_ID_CTX.get() or 0)
            except Exception:
                uid = 0

            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="graph_extract",
                user_id=uid,
                source="graphrag",
                temperature=0.1,
                max_tokens=8192,
            )

            # ── Bug fix: LLM 调用失败时抛异常，让 outbox 事件重试 ──
            if resp.is_error:
                raise ExtractionLLMError(
                    f"LLM call failed for memory {source_memory_id} (model={resp.model}, latency={resp.latency_ms}ms)"
                )

            content = resp.content
            logger.debug(f"[Extract] LLM response length={len(content)}, preview={content[:200]}...")

            # ── Bug fix: content 非空但无法提取 JSON → LLM 返回了非法格式，应重试 ──
            if content.strip() and not self._extract_json_string(content):
                raise ExtractionLLMError(
                    f"LLM returned non-JSON response for memory {source_memory_id} "
                    f"(model={resp.model}, content_length={len(content)})"
                )

            # 解析结果
            result = self._parse_response(content, text, source_memory_id, source_document_id, source_chunk_id)
            logger.info(f"[Extract] Extracted {len(result.entities)} entities, {len(result.relations)} relations, {len(result.claims)} claims")

            # 记录提取时间
            result.extraction_time = time.time() - start_time
            result.model = resp.model or self._model or "default"

            return result

        except ExtractionLLMError:
            # LLM 调用失败（429/500 等），向上抛出，让事件重试
            raise
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return ExtractionResult(
                source_text=text,
                source_memory_id=source_memory_id,
                source_document_id=source_document_id,
                source_chunk_id=source_chunk_id,
                extraction_time=time.time() - start_time
            )
    
    def _parse_response(
        self,
        response: str,
        source_text: str,
        source_memory_id: Optional[int],
        source_document_id: Optional[int] = None,
        source_chunk_id: Optional[int] = None
    ) -> ExtractionResult:
        """
        解析 LLM 响应
        
        Args:
            response: LLM 返回的文本
            source_text: 原始文本
            source_memory_id: 来源记忆ID
            source_document_id: 来源文档ID
            source_chunk_id: 来源父片ID
            
        Returns:
            ExtractionResult
        """
        # 尝试提取 JSON
        try:
            json_str = self._extract_json_string(response)
            if json_str:
                # 预处理 JSON 字符串
                json_str = self._preprocess_json(json_str)
                data = json.loads(json_str)

                entities = self._parse_entities(data.get("entities", []), source_memory_id, source_document_id, source_chunk_id)
                relations = self._parse_relations(data.get("relations", []), entities, source_memory_id, source_document_id, source_chunk_id)
                claims = self._parse_claims(data.get("claims", []), source_document_id, source_chunk_id)

                # 后处理：确保事件有关系（避免孤立节点）
                relations = self._ensure_event_relationships(entities, relations, source_text)

                # 关系完备性自检
                coverage_check = data.get("coverage_check", [])
                orphan_entities = self._analyze_coverage(entities, relations, coverage_check)
                if orphan_entities:
                    logger.info(f"[Extract] Coverage check found {len(orphan_entities)} orphans: {orphan_entities[:5]}...")

                return ExtractionResult(
                    entities=entities,
                    relations=relations,
                    claims=claims,
                    source_text=source_text,
                    source_memory_id=source_memory_id,
                    source_document_id=source_document_id,
                    source_chunk_id=source_chunk_id,
                    coverage_check=coverage_check,
                    orphan_entities=orphan_entities
                )
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}, response preview: {response[:200]}...")
            # 重试：尝试更激进的修复
            try:
                json_str = self._extract_json_string(response)
                if json_str:
                    json_str = self._aggressive_json_repair(json_str)
                    data = json.loads(json_str)
                    logger.info(f"JSON repaired successfully on retry")

                    entities = self._parse_entities(data.get("entities", []), source_memory_id, source_document_id, source_chunk_id)
                    relations = self._parse_relations(data.get("relations", []), entities, source_memory_id, source_document_id, source_chunk_id)
                    claims = self._parse_claims(data.get("claims", []), source_document_id, source_chunk_id)

                    # 后处理：确保事件有关系（避免孤立节点）
                    relations = self._ensure_event_relationships(entities, relations, source_text)

                    coverage_check = data.get("coverage_check", [])
                    orphan_entities = self._analyze_coverage(entities, relations, coverage_check)

                    return ExtractionResult(
                        entities=entities,
                        relations=relations,
                        claims=claims,
                        source_text=source_text,
                        source_memory_id=source_memory_id,
                        source_document_id=source_document_id,
                        source_chunk_id=source_chunk_id,
                        coverage_check=coverage_check,
                        orphan_entities=orphan_entities
                    )
            except Exception as retry_err:
                logger.warning(f"Aggressive JSON repair also failed: {retry_err}")
        except Exception as e:
            logger.warning(f"Failed to parse response: {e}")
        
        return ExtractionResult(
            source_text=source_text,
            source_memory_id=source_memory_id,
            source_document_id=source_document_id,
            source_chunk_id=source_chunk_id
        )
    
    def _extract_json_string(self, response: str) -> Optional[str]:
        """
        从响应中提取 JSON 字符串
        
        支持多种格式：
        1. markdown 代码块: ```json ... ``` 或 ``` ... ```
        2. 纯 JSON 对象
        3. 嵌套在其他文本中的 JSON
        """
        # 1. 尝试提取 markdown 代码块
        # 匹配 ```json ... ``` 或 ``` ... ```
        code_block_patterns = [
            r'```json\s*([\s\S]*?)\s*```',  # ```json ... ```
            r'```\s*([\s\S]*?)\s*```',       # ``` ... ```
        ]
        
        for pattern in code_block_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                json_str = match.group(1).strip()
                if json_str.startswith('{'):
                    return json_str
        
        # 2. 查找第一个完整的 JSON 对象
        start = response.find('{')
        if start < 0:
            return None
        
        # 使用括号匹配找到完整的 JSON 对象
        depth = 0
        in_string = False
        escape_next = False
        end = start
        
        for i, char in enumerate(response[start:], start):
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\' and in_string:
                escape_next = True
                continue
            
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            
            if in_string:
                continue
            
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        
        if end > start:
            return response[start:end]
        
        return None
    
    def _preprocess_json(self, json_str: str) -> str:
        """
        预处理 JSON 字符串，修复常见问题

        修复：
        1. 中文引号 → 英文引号
        2. 中文冒号 → 英文冒号
        3. 中文逗号 → 英文逗号
        4. 尾随逗号
        5. 未引用的键名（简单情况）
        6. 控制字符
        7. 数组中对象之间缺少逗号：`}{` → `},{`
        8. 缺少冒号的键值对（简单修复）
        """
        # 替换中文标点
        json_str = json_str.replace('"', '"').replace('"', '"')
        json_str = json_str.replace(''', "'").replace(''', "'")
        json_str = json_str.replace('：', ':')
        json_str = json_str.replace('，', ',')
        json_str = json_str.replace('、', ',')

        # 移除控制字符（除了 \n, \r, \t）
        json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)

        # 移除尾随逗号（在 } 或 ] 之前的逗号）
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

        # 修复数组中对象之间缺少逗号：`}{` → `},{`
        # 例如: {"name":"a"} {"name":"b"} → {"name":"a"}, {"name":"b"}
        json_str = re.sub(r'}\s*({)', r'}, \1', json_str)

        # 修复数组中值之间缺少逗号：`"value" "key"` → `"value", "key"`
        # 但要小心不要匹配到字符串内的内容
        # 匹配：字符串结尾的引号后面跟着空格和另一个引号开头
        json_str = re.sub(r'(")\s+("(?:\w+)"\s*:)', r'\1, \2', json_str)

        # 尝试修复未引用的键名（简单情况：行首或逗号后的裸单词）
        # 匹配: {name: 或 ,name: 等情况
        def fix_unquoted_key(match):
            key = match.group(1)
            if key.strip() and not key.startswith('"'):
                return f'"{key}":'
            return match.group(0)

        # 小心处理，只修复明显的未引用键
        json_str = re.sub(r'(\w+)\s*:', fix_unquoted_key, json_str)

        return json_str

    def _aggressive_json_repair(self, json_str: str) -> str:
        """
        激进的 JSON 修复策略（当常规预处理失败时使用）

        使用状态机逐字符扫描，修复：
        1. 缺少逗号（对象/值之间）
        2. 缺少冒号（键值之间）
        3. 截断的 JSON（补全缺失的括号）
        """
        # 先做基础预处理
        json_str = self._preprocess_json(json_str)

        result = []
        i = 0
        in_string = False
        escape_next = False
        depth = 0  # 嵌套深度
        last_token = None  # 上一个有意义的 token: '{', '[', '}', ']', ':', ',', 'value'

        while i < len(json_str):
            c = json_str[i]

            # 处理转义
            if escape_next:
                result.append(c)
                escape_next = False
                i += 1
                continue

            if c == '\\' and in_string:
                result.append(c)
                escape_next = True
                i += 1
                continue

            # 处理字符串
            if c == '"':
                in_string = not in_string
                result.append(c)
                if not in_string:
                    # 字符串结束，看看下一个是什么
                    last_token = 'value'
                else:
                    # 字符串开始，检查是否需要添加逗号或冒号
                    if last_token == 'value':
                        # 前一个值结束了，这里应该是逗号，但我们看到了新的字符串
                        # 检查 result 末尾是否已有逗号
                        stripped = ''.join(result).rstrip()
                        if not stripped.endswith(',') and not stripped.endswith('{') and not stripped.endswith('['):
                            result.append(',')
                    elif last_token in ('{', ','):
                        # 键开始，正常
                        pass
                i += 1
                continue

            if in_string:
                result.append(c)
                i += 1
                continue

            # 跳过空白
            if c in ' \t\n\r':
                result.append(c)
                i += 1
                continue

            # 处理结构字符
            if c == '{':
                if last_token == 'value':
                    # 前一个值结束了，需要逗号
                    stripped = ''.join(result).rstrip()
                    if not stripped.endswith(',') and not stripped.endswith('{') and not stripped.endswith('['):
                        result.append(',')
                result.append(c)
                depth += 1
                last_token = '{'
            elif c == '[':
                if last_token == 'value':
                    stripped = ''.join(result).rstrip()
                    if not stripped.endswith(',') and not stripped.endswith('{') and not stripped.endswith('['):
                        result.append(',')
                result.append(c)
                depth += 1
                last_token = '['
            elif c == '}':
                result.append(c)
                depth -= 1
                last_token = '}'
            elif c == ']':
                result.append(c)
                depth -= 1
                last_token = ']'
            elif c == ':':
                result.append(c)
                last_token = ':'
            elif c == ',':
                result.append(c)
                last_token = ','
            else:
                # 数字、true、false、null 等
                if last_token == 'value':
                    # 前一个值结束了，需要逗号
                    stripped = ''.join(result).rstrip()
                    if not stripped.endswith(',') and not stripped.endswith('{') and not stripped.endswith('['):
                        result.append(',')
                elif last_token in ('{', ','):
                    # 可能是键名但没有引号，或者键名后缺少冒号
                    # 尝试找到键名的结束位置
                    key_end = i
                    while key_end < len(json_str) and json_str[key_end] not in ':,}]\n\r ':
                        key_end += 1
                    potential_key = json_str[i:key_end]
                    # 检查键名后是否有冒号
                    rest = json_str[key_end:].lstrip()
                    if not rest.startswith(':') and potential_key:
                        # 缺少冒号，添加
                        result.append(f'"{potential_key}":')
                        i = key_end
                        last_token = ':'
                        continue
                result.append(c)
                # 检查这个 token 是否是完整值
                token_end = i
                while token_end < len(json_str) and json_str[token_end] not in ',}]\n\r ':
                    token_end += 1
                if token_end > i:
                    last_token = 'value'
                    i = token_end
                    continue

            i += 1

        json_str = ''.join(result)

        # 补全缺失的括号
        open_braces = json_str.count('{') - json_str.count('}')
        open_brackets = json_str.count('[') - json_str.count(']')
        if open_braces > 0:
            json_str += '}' * open_braces
        if open_brackets > 0:
            json_str += ']' * open_brackets

        return json_str

    def _parse_entities(
        self,
        entity_list: List[dict],
        source_memory_id: Optional[int],
        source_document_id: Optional[int] = None,
        source_chunk_id: Optional[int] = None
    ) -> List[Entity]:
        """
        解析实体列表
        
        Args:
            entity_list: 实体字典列表
            source_memory_id: 来源记忆ID
            source_document_id: 来源文档ID
            source_chunk_id: 来源父片ID
            
        Returns:
            Entity 列表
        """
        entities = []

        for item in entity_list:
            name = item.get("name", "").strip()
            if not name:
                continue

            # 解析实体类型
            type_str = item.get("type", "other").lower()
            entity_type = ENTITY_TYPE_MAP.get(type_str, EntityType.OTHER)

            # 解析置信度
            confidence = item.get("confidence", 1.0)
            # 确保置信度在有效范围内
            if not isinstance(confidence, (int, float)):
                confidence = 1.0
            confidence = max(0.0, min(1.0, float(confidence)))

            # 解析别名列表
            aliases = item.get("aliases", [])
            if not isinstance(aliases, list):
                aliases = []
            aliases = [str(a).strip() for a in aliases if a and str(a).strip()]

            # 创建实体
            entity = Entity(
                id=self._generate_entity_id(name, entity_type),
                name=name,
                entity_type=entity_type,
                description=item.get("description", ""),
                aliases=aliases,
                source_memory_id=source_memory_id,
                source_document_id=source_document_id,
                source_chunk_id=source_chunk_id,
                confidence=confidence
            )

            entities.append(entity)

        # 过滤停用词实体（无意义实体）
        entities = [e for e in entities if e.name.lower() not in ENTITY_STOPWORDS]

        # 过滤低置信度实体
        if self._min_confidence > 0:
            entities = [e for e in entities if e.confidence >= self._min_confidence]

        if len(entities) < len(entity_list):
            filtered_count = len(entity_list) - len(entities)
            logger.debug(f"[Extract] Filtered {filtered_count} low-quality entities (stopwords or low confidence)")

        return entities
    
    def _parse_relations(
        self,
        relation_list: List[dict],
        entities: List[Entity],
        source_memory_id: Optional[int],
        source_document_id: Optional[int] = None,
        source_chunk_id: Optional[int] = None
    ) -> List[Relation]:
        """
        解析关系列表
        
        Args:
            relation_list: 关系字典列表
            entities: 已解析的实体列表
            source_memory_id: 来源记忆ID
            source_document_id: 来源文档ID
            source_chunk_id: 来源父片ID
            
        Returns:
            Relation 列表
        """
        relations = []
        
        # 创建实体名称到ID的映射
        entity_map = {e.name.lower(): e for e in entities}
        
        for item in relation_list:
            source_name = item.get("source", "").strip()
            target_name = item.get("target", "").strip()
            
            if not source_name or not target_name:
                continue
            
            # 查找实体
            source_entity = entity_map.get(source_name.lower())
            target_entity = entity_map.get(target_name.lower())
            
            # 如果实体不存在，创建临时实体
            if not source_entity:
                source_entity = Entity(
                    id=self._generate_entity_id(source_name, EntityType.OTHER),
                    name=source_name,
                    entity_type=EntityType.OTHER,
                    source_memory_id=source_memory_id,
                    source_document_id=source_document_id,
                    source_chunk_id=source_chunk_id
                )
                entities.append(source_entity)
                entity_map[source_name.lower()] = source_entity
            
            if not target_entity:
                target_entity = Entity(
                    id=self._generate_entity_id(target_name, EntityType.OTHER),
                    name=target_name,
                    entity_type=EntityType.OTHER,
                    source_memory_id=source_memory_id,
                    source_document_id=source_document_id,
                    source_chunk_id=source_chunk_id
                )
                entities.append(target_entity)
                entity_map[target_name.lower()] = target_entity
            
            # 解析关系类型
            type_str = item.get("type", "related_to").lower()
            relation_type = RELATION_TYPE_MAP.get(type_str, RelationType.RELATED_TO)

            # 解析置信度
            confidence = item.get("confidence", 1.0)
            if not isinstance(confidence, (int, float)):
                confidence = 1.0
            confidence = max(0.0, min(1.0, float(confidence)))

            # 解析时间属性（P2+ 优化：区分"曾任职"和"任职"）
            valid_from = item.get("valid_from")  # ISO 8601 格式或 null
            valid_until = item.get("valid_until")  # ISO 8601 格式或 null
            is_current = item.get("is_current", True)  # 默认当前有效
            if not isinstance(is_current, bool):
                is_current = True

            # 创建关系
            relation = Relation(
                id=self._generate_relation_id(source_entity.id, target_entity.id, relation_type),
                source_id=source_entity.id,
                target_id=target_entity.id,
                relation_type=relation_type,
                description=item.get("description", ""),
                source_memory_id=source_memory_id,
                source_document_id=source_document_id,
                source_chunk_id=source_chunk_id,
                confidence=confidence,
                valid_from=valid_from,
                valid_until=valid_until,
                is_current=is_current
            )

            relations.append(relation)

        # 过滤低置信度关系
        if self._min_confidence > 0:
            relations = [r for r in relations if r.confidence >= self._min_confidence]

        return relations

    def _ensure_event_relationships(
        self,
        entities: List[Entity],
        relations: List[Relation],
        source_text: str
    ) -> List[Relation]:
        """
        后处理：确保事件实体有关系，避免成为孤立节点

        对于没有关系的 event 类型实体，尝试从描述和原文中找到参与者，
        自动添加 participates_in 关系。

        Args:
            entities: 已提取的实体列表
            relations: 已提取的关系列表
            source_text: 原文文本

        Returns:
            更新后的关系列表
        """
        # 找出所有事件实体
        event_entities = [e for e in entities if e.entity_type == EntityType.EVENT]
        if not event_entities:
            return relations

        # 找出所有人物实体
        person_entities = [e for e in entities if e.entity_type == EntityType.PERSON]
        if not person_entities:
            return relations

        # 找出已经有关系的事件 ID
        events_with_relations = set()
        for r in relations:
            for e in event_entities:
                if r.source_id == e.id or r.target_id == e.id:
                    events_with_relations.add(e.id)

        # 对于没有关系的事件，尝试从描述中找参与者
        new_relations = []
        for event in event_entities:
            if event.id in events_with_relations:
                continue

            # 检查事件描述中提到了哪些人物
            desc = (event.description or "").lower()
            event_name = event.name.lower()

            for person in person_entities:
                person_name = person.name.lower()
                # 检查人物名字是否出现在事件描述或事件名称中
                if person_name in desc or person_name in event_name:
                    # 检查是否已存在关系
                    existing = any(
                        (r.source_id == person.id and r.target_id == event.id) or
                        (r.source_id == event.id and r.target_id == person.id)
                        for r in relations
                    )
                    if not existing:
                        # 创建 participates_in 关系
                        new_rel = Relation(
                            id=self._generate_relation_id(
                                person.id, event.id, RelationType.WORKS_ON
                            ),
                            source_id=person.id,
                            target_id=event.id,
                            relation_type=RelationType.WORKS_ON,
                            description=f"{person.name}参与{event.name}",
                            source_memory_id=event.source_memory_id,
                            source_document_id=event.source_document_id,
                            source_chunk_id=event.source_chunk_id,
                            confidence=0.7  # 较低置信度，因为是推断的
                        )
                        new_relations.append(new_rel)
                        logger.debug(
                            f"[EventLink] Auto-linked {person.name} -> {event.name}"
                        )

        if new_relations:
            logger.info(
                f"[EventLink] Auto-linked {len(new_relations)} event-participant relations"
            )
            relations.extend(new_relations)

        return relations

    def _analyze_coverage(
        self,
        entities: List[Entity],
        relations: List[Relation],
        coverage_check: List[dict]
    ) -> List[str]:
        """
        分析关系完备性自检结果

        对比 LLM 的 coverage_check 和实际关系，找出：
        1. LLM 标记为 connected=false 的实体 → 确认为孤立实体
        2. LLM 标记为 connected=true 但实际没有关系的 → 自检矛盾（LLM 以为自己建了关系实际没有）

        Args:
            entities: 提取的实体列表
            relations: 提取的关系列表
            coverage_check: LLM 输出的完备性检查

        Returns:
            孤立实体名称列表（可能需要补边的候选）
        """
        if not entities:
            return []

        # 建立实体名 -> 是否有关联的映射
        entity_names_with_relations = set()
        for r in relations:
            # 找到 source_id 和 target_id 对应的实体名
            for e in entities:
                if e.id == r.source_id or e.id == r.target_id:
                    entity_names_with_relations.add(e.name.lower())

        # 解析 coverage_check
        coverage_map = {}  # entity_name_lower -> {connected, missing_reason}
        for item in coverage_check:
            name = (item.get("entity") or "").strip().lower()
            if name:
                coverage_map[name] = {
                    "connected": item.get("connected", True),
                    "reason": item.get("missing_reason", "")
                }

        orphans = []
        mismatches = []

        for e in entities:
            ename = e.name.lower()
            has_relation = ename in entity_names_with_relations
            check = coverage_map.get(ename)

            if check:
                # LLM 提供了自检结果
                if not check["connected"] and has_relation:
                    # LLM 说没有关系，但实际有 → 正常（LLM 可能没注意到）
                    pass
                elif check["connected"] and not has_relation:
                    # LLM 说有关系，但实际没有 → 自检矛盾，可能是 JSON 生成时遗漏
                    mismatches.append(e.name)
                elif not check["connected"] and not has_relation:
                    # LLM 说没有关系，实际也没有 → 确认孤立
                    orphans.append(e.name)
            else:
                # LLM 没有提供该实体的自检（coverage_check 不完整）
                if not has_relation:
                    orphans.append(e.name)

        if mismatches:
            logger.warning(
                f"[Coverage] Self-check mismatch for {len(mismatches)} entities "
                f"(LLM said connected but no relations found): {mismatches[:5]}"
            )

        return orphans

    @staticmethod
    def _generate_entity_id(name: str, entity_type: EntityType) -> str:
        """生成实体ID"""
        # 使用名称和类型的哈希
        hash_input = f"{entity_type.value}:{name}".lower()
        hash_val = uuid.uuid5(uuid.NAMESPACE_DNS, hash_input)
        return f"entity_{hash_val.hex[:12]}"
    
    def _parse_claims(
        self,
        claims_data: List[Dict[str, Any]],
        source_document_id: Optional[int] = None,
        source_chunk_id: Optional[int] = None
    ) -> List["Claim"]:
        """
        解析 Claim 列表

        Args:
            claims_data: LLM 返回的 Claim 数据列表
            source_document_id: 来源文档 ID
            source_chunk_id: 来源文本块 ID

        Returns:
            Claim 列表
        """
        from backend.graphrag.types import Claim, ClaimType, ClaimStatus

        claims = []

        for item in claims_data:
            try:
                # 解析 Claim 类型
                claim_type_str = item.get("claim_type", "fact").lower()
                if claim_type_str in ("fact", "事实"):
                    claim_type = ClaimType.FACT
                elif claim_type_str in ("opinion", "观点"):
                    claim_type = ClaimType.OPINION
                elif claim_type_str in ("inference", "推论"):
                    claim_type = ClaimType.INFERENCE
                else:
                    claim_type = ClaimType.FACT

                # 解析置信度（健壮处理）
                try:
                    confidence = float(item.get("confidence", 0.8))
                except (ValueError, TypeError):
                    confidence = 0.8
                if confidence < self._min_confidence:
                    continue

                # 创建 Claim
                claim = Claim(
                    id=f"claim_{uuid.uuid4().hex[:8]}",
                    claim_type=claim_type,
                    claim_text=item.get("claim_text", ""),
                    subject=item.get("subject", ""),
                    object=item.get("object"),
                    claim_value=item.get("claim_value", ""),
                    time=item.get("time"),
                    confidence=confidence,
                    source_document_id=source_document_id,
                    source_chunk_id=source_chunk_id,
                    status=ClaimStatus.ACTIVE,
                )

                claims.append(claim)

            except Exception as e:
                logger.warning(f"[Extract] Failed to parse claim: {e}, item={item}")
                continue

        return claims

    @staticmethod
    def _generate_relation_id(source_id: str, target_id: str, relation_type: RelationType) -> str:
        """生成关系ID"""
        hash_input = f"{source_id}:{relation_type.value}:{target_id}"
        hash_val = uuid.uuid5(uuid.NAMESPACE_DNS, hash_input)
        return f"relation_{hash_val.hex[:12]}"
    
    def batch_extract(
        self,
        texts: List[str],
        source_memory_ids: Optional[List[int]] = None,
        source_document_ids: Optional[List[int]] = None,
        source_chunk_ids: Optional[List[int]] = None
    ) -> List[ExtractionResult]:
        """
        批量提取
        
        Args:
            texts: 文本列表
            source_memory_ids: 来源记忆ID列表
            source_document_ids: 来源文档ID列表
            source_chunk_ids: 来源父片ID列表
            
        Returns:
            ExtractionResult 列表
        """
        results = []
        
        for i, text in enumerate(texts):
            memory_id = source_memory_ids[i] if source_memory_ids else None
            doc_id = source_document_ids[i] if source_document_ids else None
            chunk_id = source_chunk_ids[i] if source_chunk_ids else None
            result = self.extract(text, memory_id, doc_id, chunk_id)
            results.append(result)
        
        return results


# 单例访问
_extractor: Optional[EntityExtractor] = None

# 默认置信度阈值（可通过环境变量覆盖）
import os
DEFAULT_MIN_CONFIDENCE = float(os.getenv("GRAPHRAG_MIN_CONFIDENCE", "0.7"))


def get_entity_extractor() -> EntityExtractor:
    """获取 EntityExtractor 单例

    默认使用 0.7 的置信度阈值，过滤低质量实体。
    可通过环境变量 GRAPHRAG_MIN_CONFIDENCE 调整（范围 0.0-1.0）。
    """
    global _extractor
    if _extractor is None:
        _extractor = EntityExtractor(min_confidence=DEFAULT_MIN_CONFIDENCE)
        logger.info(f"[EntityExtractor] Initialized with min_confidence={DEFAULT_MIN_CONFIDENCE}")
    return _extractor