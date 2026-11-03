"""
多路查询改写（Multi-path Query Rewrite）

用 LLM 对用户问题做多路改写，提升检索召回质量：

| 改写类型 | 作用 |
|---------|------|
| 主改写 | 补全语义，规范表达，纠错 |
| 子查询改写 | 复杂问题拆成多个子问题（并行检索后合并） |
| 同义改写 | 生成同义表达，扩大召回范围 |

设计原则（参考守护之眼 RAG 测评文档）：
- 改写结果回归纯净语义（不注入业务上下文）
- 「谁需要谁拼接」：改写器只做语义增强，不混入用户/时间等字段
- 改写后的 query 用于向量/BM25/混合检索

使用方式：
    rewriter = QueryRewriter()
    
    # 单路改写（原有逻辑）
    rewritten = rewriter.rewrite(query)
    
    # 多路改写（子查询 + 同义）
    result = rewriter.multi_rewrite(query, enable_sub=True, enable_synonym=True)
    # result = {
    #     "main": "改写后的主查询",
    #     "sub_queries": ["子问题1", "子问题2"],
    #     "synonyms": ["同义表达1", "同义表达2"]
    # }
"""
from typing import List, Optional, Dict
from dataclasses import dataclass

from backend.utils.log_utils import log, rag

logger = log

# ════════════════════════════════════════════════════════════
# Prompt 模板
# ════════════════════════════════════════════════════════════

# 主改写：语义压缩 + 纠错
_REWRITE_PROMPT = """你是一个查询重写助手。请对用户问题进行以下处理：
1. 简洁化：去除冗余词汇，保留核心语义
2. 错别字纠正：修正明显的拼写/输入错误
3. 语义压缩：用更精确的术语替换模糊表达
4. 上下文补全：如果问题中有代词（如"它"、"这个"），根据语义补全指代对象
5. 保持原意：不要改变问题的核心意图

规则：
- 只输出重写后的问题，不要任何解释
- 如果原始问题已经足够清晰，直接返回原文
- 不要添加任何原始问题中没有的信息

示例：
原问题：Redis 怎么存数据？
重写后：Redis 如何存储数据？String 类型的常用命令有哪些？

原问题：查看 traces 表结构
重写后：traces 表的字段结构是什么？

用户问题：{query}

重写后的问题："""

# 子查询生成：复杂问题拆解
_SUB_QUERY_PROMPT = """你是一个问题拆解助手。请分析用户问题，如果这是一个复杂或多维度的问题，将其拆解为 2-4 个独立的子问题。

拆解规则：
1. 每个子问题应该是独立的、可单独检索的
2. 子问题之间不应有依赖关系
3. 子问题的答案组合起来应该能回答原问题
4. 如果原问题已经足够简单，返回空数组 []

输出格式（JSON 数组）：
["子问题1", "子问题2"]

示例：
原问题：Redis 的持久化机制有哪些？它们有什么区别？
输出：["Redis 的持久化机制有哪些", "RDB 和 AOF 持久化的区别是什么"]

原问题：如何查看最近一周的 Token 消耗？
输出：[]

用户问题：{query}

输出："""

# 同义改写：生成同义表达
_SYNONYM_PROMPT = """你是一个同义改写助手。请为用户问题生成 1-3 个语义相同但表达不同的改写版本，用于扩大检索召回范围。

改写规则：
1. 保持核心语义完全不变
2. 使用同义词替换关键词（如"持久化"→"数据保存"，"查询"→"检索"）
3. 可以调整句式结构
4. 如果问题过于简单或没有合适的同义表达，返回空数组 []

输出格式（JSON 数组）：
["同义表达1", "同义表达2"]

示例：
原问题：Redis 的 RDB 持久化是怎么工作的？
输出：["Redis RDB 快照机制原理", "Redis 如何通过 RDB 保存数据"]

原问题：如何查询用户列表？
输出：["怎么获取用户列表", "查看 users 表的方法"]

用户问题：{query}

输出："""


@dataclass
class MultiRewriteResult:
    """多路改写结果。"""
    main: str                      # 主改写结果
    sub_queries: List[str]         # 子查询列表
    synonyms: List[str]            # 同义改写列表
    
    def all_queries(self) -> List[str]:
        """获取所有查询（主查询 + 子查询 + 同义）。"""
        queries = [self.main] if self.main else []
        queries.extend(self.sub_queries)
        queries.extend(self.synonyms)
        return queries
    
    def to_dict(self) -> Dict:
        return {
            "main": self.main,
            "sub_queries": self.sub_queries,
            "synonyms": self.synonyms,
        }


class QueryRewriter:
    """LLM 多路查询重写器（使用 TracedLLMClient，自动记录 trace）。"""

    def __init__(self, model_cfg: dict = None):
        """
        Args:
            model_cfg: 已废弃，保留用于向后兼容。内部统一使用 traced_llm 场景路由。
        """
        self.model_cfg = model_cfg  # 保留兼容，不再使用

    def _call_llm(self, prompt: str) -> Optional[str]:
        """调用 LLM 并返回文本结果（通过 traced_llm，自动 trace）。"""
        try:
            from backend.utils.traced_llm import traced_llm
            
            # 尝试从上下文获取 user_id
            try:
                from backend.hermes_adapter import _CURRENT_USER_ID_CTX
                uid = int(_CURRENT_USER_ID_CTX.get() or 0)
            except Exception:
                uid = 0

            resp = traced_llm.invoke(
                messages=[{"role": "user", "content": prompt}],
                scene="rag_rewrite",
                user_id=uid,
                source="rag",
                temperature=0,
                max_tokens=512,
            )
            return (resp.content or "").strip()
        except Exception as e:
            logger.warning(f"[QueryRewriter] LLM 调用失败: {e}")
            return None

    def _parse_json_list(self, text: str) -> List[str]:
        """解析 JSON 数组，容错处理。"""
        import json
        text = (text or "").strip()
        if not text:
            return []
        
        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return [str(item).strip() for item in result if item and str(item).strip()]
        except json.JSONDecodeError:
            pass
        
        # 尝试提取数组部分
        import re
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return [str(item).strip() for item in result if item and str(item).strip()]
            except json.JSONDecodeError:
                pass
        
        return []

    def rewrite(self, query: str) -> str:
        """
        单路重写用户查询（原有接口，保持兼容）。

        Args:
            query: 原始用户问题

        Returns:
            重写后的问题（失败时返回原文）
        """
        query = (query or "").strip()
        if not query:
            return query

        # 短问题不重写（信息量已足够）
        if len(query) <= 10:
            return query

        try:
            prompt = _REWRITE_PROMPT.format(query=query)
            rewritten = self._call_llm(prompt)
            if rewritten and rewritten != query and len(rewritten) > 3:
                logger.debug(f"[QueryRewriter] 主改写: '{query}' → '{rewritten}'")
                return rewritten
        except Exception as e:
            logger.warning(f"[QueryRewriter] 重写失败: {e}")

        return query

    def generate_sub_queries(self, query: str) -> List[str]:
        """
        生成子查询（复杂问题拆解）。

        Args:
            query: 原始用户问题

        Returns:
            子查询列表
        """
        query = (query or "").strip()
        if not query or len(query) < 15:  # 太短的问题不需要拆解
            return []

        try:
            prompt = _SUB_QUERY_PROMPT.format(query=query)
            text = self._call_llm(prompt)
            sub_queries = self._parse_json_list(text)
            
            if sub_queries:
                logger.debug(f"[QueryRewriter] 子查询: '{query}' → {sub_queries}")
            return sub_queries
        except Exception as e:
            logger.warning(f"[QueryRewriter] 子查询生成失败: {e}")
            return []

    def generate_synonyms(self, query: str) -> List[str]:
        """
        生成同义改写（扩大召回范围）。

        Args:
            query: 原始用户问题

        Returns:
            同义改写列表
        """
        query = (query or "").strip()
        if not query or len(query) < 8:  # 太短的问题没有足够的同义空间
            return []

        try:
            prompt = _SYNONYM_PROMPT.format(query=query)
            text = self._call_llm(prompt)
            synonyms = self._parse_json_list(text)
            
            if synonyms:
                logger.debug(f"[QueryRewriter] 同义改写: '{query}' → {synonyms}")
            return synonyms
        except Exception as e:
            logger.warning(f"[QueryRewriter] 同义改写失败: {e}")
            return []

    def multi_rewrite(
        self,
        query: str,
        enable_main: bool = True,
        enable_sub: bool = False,
        enable_synonym: bool = False,
    ) -> MultiRewriteResult:
        """
        多路查询改写（主改写 + 子查询 + 同义改写）。

        Args:
            query: 原始用户问题
            enable_main: 是否启用主改写
            enable_sub: 是否启用子查询生成
            enable_synonym: 是否启用同义改写

        Returns:
            MultiRewriteResult 包含所有改写结果
        """
        query = (query or "").strip()
        if not query:
            return MultiRewriteResult(main=query, sub_queries=[], synonyms=[])

        # 主改写
        main_query = self.rewrite(query) if enable_main else query

        # 子查询（基于主改写结果）
        sub_queries = []
        if enable_sub and len(main_query) >= 15:
            sub_queries = self.generate_sub_queries(main_query)

        # 同义改写（基于主改写结果）
        synonyms = []
        if enable_synonym and len(main_query) >= 8:
            synonyms = self.generate_synonyms(main_query)

        return MultiRewriteResult(
            main=main_query,
            sub_queries=sub_queries,
            synonyms=synonyms,
        )


# ════════════════════════════════════════════════════════════
# 工厂函数
# ════════════════════════════════════════════════════════════

def get_query_rewriter(user_id: int = 0) -> Optional[QueryRewriter]:
    """
    获取 QueryRewriter 实例。

    内部统一使用 traced_llm 场景路由，user_id 参数保留兼容。
    """
    return QueryRewriter()


def should_rewrite_query(query: str) -> tuple[bool, bool, bool]:
    """
    根据查询特征自动判断是否需要改写。

    设计原则：宁可多触发（LLM 改写成本低），不可漏触发。
    技术查询（如"Redis 持久化"）即使没有疑问词也应触发主改写。

    Args:
        query: 用户查询

    Returns:
        (enable_main, enable_sub, enable_synonym) 三元组
    """
    query = (query or "").strip()
    if not query:
        return (False, False, False)
    
    # ── 特征分析 ──
    length = len(query)
    
    # 疑问词检测
    question_words = {"怎么", "如何", "什么", "为什么", "哪些", "怎样", "是否", "能否", "怎么查", "怎么看"}
    has_question_word = any(w in query for w in question_words)
    
    # 代词检测（可能需要上下文补全）
    pronouns = {"它", "这", "那个", "这个", "他", "她", "其"}
    has_pronoun = any(p in query for p in pronouns)
    
    # 复杂度检测（多关键词、多主题）
    import re
    connectors = ["和", "与", "以及", "并且", "同时", "还要", "再", "又", "区别", "对比"]
    has_connector = any(c in query for c in connectors)
    
    # 技术术语检测（AgentForge 场景）
    tech_terms = {
        "Redis", "SQL", "Token", "trace", "API", "LLM", "Hermes", "RAG",
        "向量", "持久化", "查询", "表结构", "Neo4j", "Milvus", "MySQL",
        "知识图谱", "embedding", "chunk", "rerank", "BM25", "RRF",
        "图检索", "语义", "召回", "评测", "检索", "模型",
    }
    has_tech_term = any(t.lower() in query.lower() for t in tech_terms)
    
    # 术语密度（长词比例）
    long_words = [w for w in re.findall(r'[\u4e00-\u9fa5]+', query) if len(w) >= 3]
    term_density = len("".join(long_words)) / length if length > 0 else 0
    
    # ── 决策逻辑（放宽触发条件）──

    # 主改写：中等长度（6~200）
    # 满足以下任一条件：有代词/疑问词/技术术语/术语密度高
    # 技术查询即使没有疑问词也触发（如"Redis 持久化"应补全语义）
    enable_main = (
        length >= 6 and length <= 200 and  # 放宽：10->6, 100->200
        (has_pronoun or has_question_word or has_tech_term or term_density >= 0.4)
    )
    
    # 子查询：复杂问题 + 多主题
    # 放宽：20->15，去掉"必须有疑问词"约束（有连接词说明是多主题）
    enable_sub = (
        length >= 15 and  # 放宽：20->15
        has_connector  # 有连接词即说明多维度
    )
    
    # 同义改写：简洁查询 + 不太复杂
    # 放宽：8->5，去掉"必须有疑问词"约束（技术名词也需要同义扩展）
    enable_synonym = (
        5 <= length <= 80 and  # 放宽：8->5, 50->80
        not has_connector  # 不太复杂
    )
    
    return (enable_main, enable_sub, enable_synonym)