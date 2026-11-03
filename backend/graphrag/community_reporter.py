"""
知识图谱社区报告生成

使用 LLM 为每个社区生成摘要报告，包括：
- 标题：概括社区主题
- 摘要：50-100字概述
- 完整报告：详细描述
- 重要性评分：1-10
- 关键发现：列表

报告用于 Global Search 和 DRIFT Search
"""

import json
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.utils.log_utils import log

logger = log


# ── 全局进度追踪 ──
_generation_progress: Dict[str, Dict[str, Any]] = {}
_progress_lock = threading.Lock()


# 社区报告生成提示词
COMMUNITY_REPORT_PROMPT = """你是一个知识图谱分析专家。请根据以下社区信息生成一份结构化报告。

【社区信息】
社区ID: {community_id}
层级: Level {level} ({level_desc})
包含实体: {entities}
内部关系数: {relationship_count}
实体描述:
{entity_descriptions}

【关系信息】
{relationships}

【输出要求】
请以 JSON 格式输出，包含以下字段：
{{
    "title": "简洁的社区标题（10字以内）",
    "summary": "50-100字的摘要，概括社区核心内容",
    "full_content": "200-500字的完整报告，包含关键发现和主题分析",
    "rating": 8,
    "findings": ["关键发现1", "关键发现2", "关键发现3"]
}}

【评分标准】
- 9-10: 核心主题社区（如主要人物集团、重大事件）
- 7-8: 重要但次要的社区
- 5-6: 一般社区
- 1-4: 边缘或琐碎社区

【注意事项】
1. 只返回 JSON，不要其他文字
2. 使用中文
3. 标题要简洁有吸引力
4. 摘要要概括核心内容
5. findings 列出具体的关键信息点
6. full_content 如需换行请使用 \\n 转义，不要在 JSON 字符串中使用真实换行符
7. 确保 JSON 格式正确，所有字符串用双引号包围
"""


@dataclass
class CommunityReport:
    """社区报告数据结构"""
    community_id: str
    title: str
    summary: str
    full_content: str
    rating: int
    findings: List[str]
    top_entities: List[str]
    summary_embedding: Optional[List[float]] = None


class CommunityReporter:
    """
    社区报告生成器

    为每个社区调用 LLM 生成摘要报告
    """

    def __init__(self, user_id: int):
        self.user_id = user_id
        self._kg_store = None

    def _get_kg_store(self):
        """获取 KGStore"""
        if self._kg_store is None:
            from backend.graphrag.kg_store import get_kg_store
            self._kg_store = get_kg_store()
        return self._kg_store

    def _get_community_data(self, community_id: str) -> Dict[str, Any]:
        """获取社区的实体和关系数据"""
        from backend.db.schema import get_conn

        conn = get_conn()
        try:
            # 获取社区信息
            cur = conn.execute(
                "SELECT id, level, entity_ids FROM kg_communities WHERE id = %s AND user_id = %s",
                (community_id, self.user_id)
            )
            row = cur.fetchone() if hasattr(cur, 'fetchone') else None
            if not row:
                return {}

            entity_ids = json.loads(row['entity_ids']) if isinstance(row['entity_ids'], str) else row['entity_ids']
            level = row['level']

            # 从 Neo4j 获取实体详情
            kg_store = self._get_kg_store()
            client = kg_store._get_graph_client()

            entities = []
            entity_descriptions = []
            relationships = []

            if client and entity_ids:
                # 获取实体信息
                placeholders = ','.join([f"'{eid}'" for eid in entity_ids[:50]])  # 限制数量
                result = client.run_query(f"""
                    MATCH (n)
                    WHERE n.id IN [{placeholders}]
                    RETURN n.id as id, n.name as name, n.description as desc, labels(n)[0] as type
                """)

                for r in result:
                    name = r.get('name', '')
                    desc = r.get('desc', '')[:100]
                    etype = r.get('type', '')
                    entities.append(name)
                    entity_descriptions.append(f"- {name} ({etype}): {desc}")

                # 获取内部关系
                result = client.run_query(f"""
                    MATCH (a)-[r]->(b)
                    WHERE a.id IN [{placeholders}] AND b.id IN [{placeholders}]
                    RETURN a.name as source, type(r) as type, b.name as target
                    LIMIT 30
                """)

                for r in result:
                    relationships.append(f"- {r['source']} -[{r['type']}]-> {r['target']}")

            return {
                "community_id": community_id,
                "level": level,
                "entities": entities[:20],  # 限制显示数量
                "entity_descriptions": "\n".join(entity_descriptions[:15]),
                "relationships": "\n".join(relationships[:20]),
                "relationship_count": len(relationships)
            }

        finally:
            conn.close()

    def _generate_report(self, community_data: Dict[str, Any]) -> Optional[CommunityReport]:
        """调用 LLM 生成社区报告"""
        # 预计算层级描述（避免 .format() 无法解析内嵌表达式）
        data = dict(community_data)
        level = data.get('level', 0)
        if level == 0:
            data['level_desc'] = '最细粒度，具体实体组'
        else:
            data['level_desc'] = f'{level}=较粗粒度，主题级汇总'

        prompt = COMMUNITY_REPORT_PROMPT.format(**data)
        content = ""

        try:
            from backend.utils.traced_llm import traced_llm
            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="graph_community",
                user_id=self.user_id,
                source="graphrag",
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            content = resp.content or ""
            # WARNING 级别以便在日志中可见（调试用，后续可改回 DEBUG）
            logger.warning(f"[Reporter] LLM 原始响应: {content[:500]}...")

            # 解析 JSON（多层回退策略）
            parsed = self._extract_json(content)

            return CommunityReport(
                community_id=community_data['community_id'],
                title=parsed.get('title', ''),
                summary=parsed.get('summary', ''),
                full_content=parsed.get('full_content', ''),
                rating=int(parsed.get('rating', 5)),
                findings=parsed.get('findings', []),
                top_entities=community_data.get('entities', [])[:10]
            )

        except Exception as e:
            logger.error(f"[Reporter] 生成报告失败: {e}")
            logger.error(f"[Reporter] LLM 完整响应:\n{content[:2000]}")
            return None

    def _extract_json(self, content: str) -> Dict[str, Any]:
        """
        从 LLM 响应中提取 JSON（鲁棒解析）

        支持：
        - 直接 JSON
        - Markdown 代码块 ```json ... ```
        - 字符串字段中的未转义换行符
        - LangChain JsonOutputParser 回退
        """
        import re

        # 策略 1: 从 markdown 代码块提取
        code_block = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', content)
        if code_block:
            json_str = code_block.group(1).strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # 尝试修复代码块内的 JSON
                try:
                    fixed = self._fix_json_string(json_str)
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        # 策略 2: 提取最外层平衡的 {} 块
        json_str = self._extract_balanced_braces(content)
        if json_str:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # 尝试修复常见 JSON 问题
                fixed = self._fix_json_string(json_str)
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        # 策略 3: 直接解析整个内容
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 策略 4: 先清理 markdown，再修复，再提取平衡括号
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', content.strip())
        cleaned = re.sub(r'\n?```\s*$', '', cleaned.strip())
        json_str = self._extract_balanced_braces(cleaned)
        if json_str:
            fixed = self._fix_json_string(json_str)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

        # 策略 5: LangChain JsonOutputParser
        try:
            from langchain_core.output_parsers import JsonOutputParser
            parser = JsonOutputParser()
            result = parser.parse(content)
            if isinstance(result, dict):
                return result
        except Exception:
            pass

        # 策略 6: 直接修复整个内容后解析
        fixed = self._fix_json_string(content)
        return json.loads(fixed)  # 最后尝试，失败则抛出异常

    def _extract_balanced_braces(self, text: str) -> Optional[str]:
        """提取最外层平衡的 {} 块"""
        start = text.find('{')
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i in range(start, len(text)):
            ch = text[i]

            if escape_next:
                escape_next = False
                continue

            if ch == '\\':
                escape_next = True
                continue

            if ch == '"' and not escape_next:
                in_string = not in_string
                continue

            if not in_string:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return text[start:i+1]

        return None

    def _fix_json_string(self, json_str: str) -> str:
        """
        修复常见的 JSON 问题

        - 字符串字段中的未转义换行符（用状态机逐字符处理）
        - 末尾多余的逗号
        - 移除 markdown 代码块标记
        """
        import re

        # 移除 markdown 代码块标记
        json_str = re.sub(r'^```(?:json)?\s*\n?', '', json_str.strip())
        json_str = re.sub(r'\n?```\s*$', '', json_str.strip())

        # 用状态机修复字符串内的控制字符
        result = []
        in_string = False
        i = 0

        while i < len(json_str):
            ch = json_str[i]

            if not in_string:
                result.append(ch)
                if ch == '"':
                    in_string = True
            else:
                # 在字符串内部
                if ch == '\\':
                    # 转义序列：保留原样
                    result.append(ch)
                    if i + 1 < len(json_str):
                        i += 1
                        result.append(json_str[i])
                elif ch == '"':
                    # 字符串结束
                    result.append(ch)
                    in_string = False
                elif ch == '\n':
                    # 未转义的换行符 → 替换为 \n
                    result.append('\\n')
                elif ch == '\r':
                    result.append('\\r')
                elif ch == '\t':
                    result.append('\\t')
                elif ord(ch) < 0x20:
                    # 其他控制字符 → 转义
                    result.append(f'\\u{ord(ch):04x}')
                else:
                    result.append(ch)
            i += 1

        fixed = ''.join(result)

        # 移除末尾多余逗号（在 } 或 ] 前）
        fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)

        return fixed.strip()

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """生成文本的向量表示"""
        try:
            from backend.rag.embeddings import get_embedding_function
            embed_fn = get_embedding_function()
            if embed_fn:
                return embed_fn.embed_query(text)
        except Exception as e:
            logger.debug(f"[Reporter] 生成 embedding 失败: {e}")
        return None

    def _store_report(self, report: CommunityReport) -> bool:
        """存储报告到 MySQL"""
        from backend.db.schema import get_conn

        conn = get_conn()
        try:
            # 检查是否已存在
            cur = conn.execute(
                "SELECT id FROM kg_community_reports WHERE community_id = %s",
                (report.community_id,)
            )
            existing = cur.fetchone() if hasattr(cur, 'fetchone') else None

            if existing:
                # 更新
                conn.execute(
                    """UPDATE kg_community_reports
                       SET title = %s, summary = %s, full_content = %s,
                           rating = %s, findings = %s, top_entities = %s,
                           summary_embedding = %s, status = 'completed',
                           updated_at = NOW()
                       WHERE community_id = %s""",
                    (
                        report.title,
                        report.summary,
                        report.full_content,
                        report.rating,
                        json.dumps(report.findings, ensure_ascii=False),
                        json.dumps(report.top_entities, ensure_ascii=False),
                        json.dumps(report.summary_embedding) if report.summary_embedding else None,
                        report.community_id
                    )
                )
            else:
                # 插入
                conn.execute(
                    """INSERT INTO kg_community_reports
                       (community_id, title, summary, full_content, rating,
                        findings, top_entities, summary_embedding, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'completed')""",
                    (
                        report.community_id,
                        report.title,
                        report.summary,
                        report.full_content,
                        report.rating,
                        json.dumps(report.findings, ensure_ascii=False),
                        json.dumps(report.top_entities, ensure_ascii=False),
                        json.dumps(report.summary_embedding) if report.summary_embedding else None
                    )
                )

            conn.commit()
            return True

        except Exception as e:
            logger.error(f"[Reporter] 存储报告失败: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def generate_all_reports(self, level: Optional[int] = None, task_id: Optional[str] = None) -> Dict[str, Any]:
        """
        为所有社区生成报告

        Args:
            level: 指定层级，None 表示全部
            task_id: 任务 ID（用于进度追踪）

        Returns:
            {"generated": int, "failed": int, "total": int}
        """
        from backend.graphrag.community_detector import get_communities

        communities = get_communities(self.user_id, level)

        if not communities:
            logger.warning("[Reporter] 没有找到社区，请先运行社区检测")
            return {"generated": 0, "failed": 0, "total": 0}

        total = len(communities)
        logger.info(f"[Reporter] 开始生成 {total} 个社区报告")

        # 初始化进度
        if task_id:
            with _progress_lock:
                _generation_progress[task_id] = {
                    "status": "running",
                    "total": total,
                    "generated": 0,
                    "failed": 0,
                    "current": 0,
                }

        generated = 0
        failed = 0

        for idx, comm in enumerate(communities):
            community_id = comm['id']

            # 更新进度
            if task_id:
                with _progress_lock:
                    _generation_progress[task_id]["current"] = idx + 1

            # 检查是否已有报告
            existing = self._get_existing_report(community_id)
            if existing and existing.get('status') == 'completed':
                logger.debug(f"[Reporter] 跳过已生成: {community_id}")
                generated += 1
                if task_id:
                    with _progress_lock:
                        _generation_progress[task_id]["generated"] = generated
                continue

            # 获取社区数据
            data = self._get_community_data(community_id)
            if not data:
                failed += 1
                if task_id:
                    with _progress_lock:
                        _generation_progress[task_id]["failed"] = failed
                continue

            # 生成报告
            report = self._generate_report(data)
            if not report:
                failed += 1
                if task_id:
                    with _progress_lock:
                        _generation_progress[task_id]["failed"] = failed
                continue

            # 生成 embedding
            if report.summary:
                report.summary_embedding = self._generate_embedding(report.summary)

            # 存储报告
            if self._store_report(report):
                generated += 1
                logger.debug(f"[Reporter] 已生成: {report.title}")
            else:
                failed += 1

            # 更新进度
            if task_id:
                with _progress_lock:
                    _generation_progress[task_id]["generated"] = generated
                    _generation_progress[task_id]["failed"] = failed

        logger.info(f"[Reporter] 报告生成完成: {generated} 成功, {failed} 失败")

        # 标记任务完成
        if task_id:
            with _progress_lock:
                _generation_progress[task_id]["status"] = "completed"

        return {
            "generated": generated,
            "failed": failed,
            "total": total
        }

    def _get_existing_report(self, community_id: str) -> Optional[Dict[str, Any]]:
        """获取已存在的报告"""
        from backend.db.schema import get_conn

        conn = get_conn()
        try:
            cur = conn.execute(
                "SELECT community_id, status FROM kg_community_reports WHERE community_id = %s",
                (community_id,)
            )
            return cur.fetchone() if hasattr(cur, 'fetchone') else None
        finally:
            conn.close()

    def get_reports(self, level: Optional[int] = None, limit: int = 100, include_embedding: bool = False) -> List[Dict[str, Any]]:
        """
        获取社区报告列表

        Args:
            level: 指定层级
            limit: 最大返回数量
            include_embedding: 是否包含摘要向量

        Returns:
            报告列表
        """
        from backend.db.schema import get_conn

        conn = get_conn()
        try:
            # 根据是否需要 embedding 选择查询字段
            if include_embedding:
                select_fields = """r.community_id, r.title, r.summary, r.rating,
                          r.findings, r.top_entities, c.level, r.summary_embedding"""
            else:
                select_fields = """r.community_id, r.title, r.summary, r.rating,
                          r.findings, r.top_entities, c.level"""

            if level is not None:
                cur = conn.execute(
                    f"""SELECT {select_fields}
                       FROM kg_community_reports r
                       JOIN kg_communities c ON r.community_id = c.id
                       WHERE c.user_id = %s AND c.level = %s AND r.status = 'completed'
                       ORDER BY r.rating DESC
                       LIMIT %s""",
                    (self.user_id, level, limit)
                )
            else:
                cur = conn.execute(
                    f"""SELECT {select_fields}
                       FROM kg_community_reports r
                       JOIN kg_communities c ON r.community_id = c.id
                       WHERE c.user_id = %s AND r.status = 'completed'
                       ORDER BY c.level, r.rating DESC
                       LIMIT %s""",
                    (self.user_id, limit)
                )

            rows = cur.fetchall() if hasattr(cur, 'fetchall') else []
            result = []
            for row in rows:
                findings = row.get('findings', '[]')
                top_entities = row.get('top_entities', '[]')
                if isinstance(findings, str):
                    findings = json.loads(findings)
                if isinstance(top_entities, str):
                    top_entities = json.loads(top_entities)

                report = {
                    "community_id": row['community_id'],
                    "level": row['level'],
                    "title": row['title'],
                    "summary": row['summary'],
                    "rating": row['rating'],
                    "findings": findings,
                    "top_entities": top_entities
                }

                # 解析 embedding
                if include_embedding and row.get('summary_embedding'):
                    try:
                        embedding = row['summary_embedding']
                        if isinstance(embedding, str):
                            embedding = json.loads(embedding)
                        report["summary_embedding"] = embedding
                    except Exception as e:
                        logger.debug(f"Failed to parse embedding: {e}")

                result.append(report)
            return result

        finally:
            conn.close()


# 便捷函数
def generate_community_reports(user_id: int, level: Optional[int] = None) -> Dict[str, Any]:
    """生成社区报告"""
    reporter = CommunityReporter(user_id)
    return reporter.generate_all_reports(level)


def get_community_reports(user_id: int, level: Optional[int] = None, limit: int = 100, include_embedding: bool = False) -> List[Dict[str, Any]]:
    """获取社区报告"""
    reporter = CommunityReporter(user_id)
    return reporter.get_reports(level, limit, include_embedding)


# ── 异步后台生成（避免 HTTP 超时）──

def start_report_generation(user_id: int, level: Optional[int] = None) -> str:
    """
    启动后台报告生成任务

    Returns:
        task_id: 任务 ID（用于查询进度）
    """
    import uuid

    task_id = f"report_gen_{uuid.uuid4().hex[:8]}"

    with _progress_lock:
        _generation_progress[task_id] = {
            "status": "starting",
            "total": 0,
            "generated": 0,
            "failed": 0,
            "current": 0,
        }

    def _run():
        try:
            reporter = CommunityReporter(user_id)
            reporter.generate_all_reports(level, task_id=task_id)
        except Exception as e:
            logger.error(f"[Reporter] 后台任务异常: {e}")
            with _progress_lock:
                _generation_progress[task_id]["status"] = "failed"
                _generation_progress[task_id]["error"] = str(e)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return task_id


def get_report_generation_progress(task_id: str) -> Optional[Dict[str, Any]]:
    """
    查询报告生成进度

    Args:
        task_id: 任务 ID

    Returns:
        进度信息，或 None（任务不存在）
    """
    with _progress_lock:
        progress = _generation_progress.get(task_id)
        if progress is None:
            return None
        return dict(progress)  # 返回副本

