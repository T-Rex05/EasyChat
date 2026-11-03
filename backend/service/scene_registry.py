"""场景注册表 — 统一管理所有 LLM 使用场景

设计原则：
1. 代码级预定义：内置常用场景，提供类型提示和文档
2. 动态扩展：支持运行时注册自定义场景（从数据库加载）
3. 前端友好：按分类组织，提供描述和推荐模型类型

使用方式：
    # 方式1：使用预定义常量（推荐，有类型提示）
    from backend.service.scene_registry import scenes
    config = get_current_model_config(user_id, scene=scenes.MEMORY_EXTRACT)

    # 方式2：使用字符串（兼容旧代码）
    config = get_current_model_config(user_id, scene="memory_extract")

    # 方式3：动态注册自定义场景
    scenes.register("custom_scene", "自定义场景", category="custom", description="...")
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import threading


@dataclass
class SceneDefinition:
    """场景定义"""
    key: str                    # 场景标识（如 "memory_extract"）
    name: str                   # 显示名称（如 "记忆提取"）
    category: str               # 分类（memory/rag/context/graph/utility/custom）
    description: str = ""       # 场景描述
    recommended_model: str = "" # 推荐模型类型提示（如 "便宜模型"、"中等模型"）
    is_builtin: bool = True     # 是否为内置场景


class SceneRegistry:
    """场景注册表 — 管理所有可用的 LLM 使用场景"""

    # ── 预定义场景常量（供类型提示和 IDE 自动补全）──
    # 记忆系统
    MEMORY_EXTRACT = "memory_extract"           # 记忆提取（从对话中提取事实）
    MEMORY_MERGE = "memory_merge"               # 记忆合并（LLM 融合相似记忆）
    MEMORY_KEYWORDS = "memory_keywords"         # 关键词生成（BM25 检索用）
    MEMORY_EVAL = "memory_eval"                 # 记忆质量评估（LLM-as-Judge）
    MEMORY_DREAMING = "memory_dreaming"         # 记忆整理（矛盾检测、晋升分析）

    # RAG / 知识库
    RAG_REWRITE = "rag_rewrite"                 # Query 改写
    RAG_RERANK = "rag_rerank"                   # LLM Rerank（专业 API 不可用时）
    RAG_ROUTER = "rag_router"                   # KB 路由选择
    KB_EVAL = "kb_eval"                         # 知识库评测
    KB_EVAL_ANALYSIS = "kb_eval_analysis"       # 评测失败分析

    # 上下文压缩
    CONTEXT_FACT_EXTRACT = "context_fact_extract"   # 事实锚点提取
    CONTEXT_TASK_STATE = "context_task_state"       # 任务状态更新

    # GraphRAG
    GRAPH_EXTRACT = "graph_extract"             # 实体/关系提取
    GRAPH_COMMUNITY = "graph_community"         # 社区报告生成
    GRAPH_GLOBAL_SEARCH = "graph_global_search" # 全局搜索 Map 阶段

    # 工具类
    TITLE = "title"                             # 会话标题生成
    COMMAND_BLACKLIST = "command_blacklist"     # 命令黑名单模式生成
    CRON = "cron"                               # 定时任务

    # 论文复现
    PAPER_PARSE = "paper_parse"                 # 论文解析
    PAPER_CLAIM = "paper_claim"                 # 主张提取
    PAPER_DEBUG = "paper_debug"                 # 代码调试

    # 入口层（已有，保留向后兼容）
    WECHAT = "wechat"                           # 微信消息
    CHAT = "chat"                               # 主聊天（默认）

    # ── 分类定义（前端展示用）──
    CATEGORIES = {
        "memory": {"name": "记忆系统", "icon": "🧠", "order": 1},
        "rag": {"name": "RAG / 知识库", "icon": "📚", "order": 2},
        "context": {"name": "上下文压缩", "icon": "🗜️", "order": 3},
        "graph": {"name": "GraphRAG", "icon": "🕸️", "order": 4},
        "paper": {"name": "论文复现", "icon": "📄", "order": 5},
        "utility": {"name": "工具类", "icon": "🔧", "order": 6},
        "entry": {"name": "入口层", "icon": "🚪", "order": 7},
        "custom": {"name": "自定义", "icon": "⚙️", "order": 99},
    }

    def __init__(self):
        self._scenes: Dict[str, SceneDefinition] = {}
        self._lock = threading.Lock()
        self._initialized = False

    def _ensure_initialized(self):
        """延迟初始化，注册所有内置场景"""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._register_builtin_scenes()
            self._initialized = True

    def _register_builtin_scenes(self):
        """注册所有内置场景"""
        # 记忆系统
        self._register(SceneDefinition(
            key=self.MEMORY_EXTRACT,
            name="记忆提取",
            category="memory",
            description="从对话中提取结构化事实，写入情景记忆",
            recommended_model="中等模型（JSON 模式）",
        ))
        self._register(SceneDefinition(
            key=self.MEMORY_MERGE,
            name="记忆合并",
            category="memory",
            description="LLM 融合两条相似记忆为一条",
            recommended_model="便宜模型",
        ))
        self._register(SceneDefinition(
            key=self.MEMORY_KEYWORDS,
            name="关键词生成",
            category="memory",
            description="为记忆条目生成 BM25 检索关键词",
            recommended_model="便宜模型",
        ))
        self._register(SceneDefinition(
            key=self.MEMORY_EVAL,
            name="记忆质量评估",
            category="memory",
            description="LLM-as-Judge 评估检索到的记忆质量",
            recommended_model="中等模型",
        ))
        self._register(SceneDefinition(
            key=self.MEMORY_DREAMING,
            name="记忆整理",
            category="memory",
            description="后台整理：矛盾检测、重复识别、晋升分析",
            recommended_model="中等模型",
        ))

        # RAG / 知识库
        self._register(SceneDefinition(
            key=self.RAG_REWRITE,
            name="Query 改写",
            category="rag",
            description="改写用户查询以提升检索效果（语义补全、纠错、子查询拆解）",
            recommended_model="便宜模型",
        ))
        self._register(SceneDefinition(
            key=self.RAG_RERANK,
            name="LLM Rerank",
            category="rag",
            description="专业 Rerank API 不可用时，用 LLM 对检索结果打分排序",
            recommended_model="中等模型",
        ))
        self._register(SceneDefinition(
            key=self.RAG_ROUTER,
            name="KB 路由",
            category="rag",
            description="根据用户问题选择最相关的知识库",
            recommended_model="便宜模型",
        ))
        self._register(SceneDefinition(
            key=self.KB_EVAL,
            name="知识库评测",
            category="rag",
            description="知识库检索质量评测（生成答案、对比参考答案）",
            recommended_model="中等模型",
        ))
        self._register(SceneDefinition(
            key=self.KB_EVAL_ANALYSIS,
            name="评测失败分析",
            category="rag",
            description="分析评测失败原因，生成改进建议",
            recommended_model="中等模型",
        ))

        # 上下文压缩
        self._register(SceneDefinition(
            key=self.CONTEXT_FACT_EXTRACT,
            name="事实锚点提取",
            category="context",
            description="从对话中提取关键事实，用于上下文压缩后的锚点恢复",
            recommended_model="便宜模型",
        ))
        self._register(SceneDefinition(
            key=self.CONTEXT_TASK_STATE,
            name="任务状态追踪",
            category="context",
            description="提取对话中的任务状态变更（待办、进度等）",
            recommended_model="便宜模型",
        ))

        # GraphRAG
        self._register(SceneDefinition(
            key=self.GRAPH_EXTRACT,
            name="实体/关系提取",
            category="graph",
            description="从文本中提取实体和关系，构建知识图谱",
            recommended_model="中等模型（JSON 模式）",
        ))
        self._register(SceneDefinition(
            key=self.GRAPH_COMMUNITY,
            name="社区报告",
            category="graph",
            description="基于社区检测结果生成摘要报告",
            recommended_model="中等模型",
        ))
        self._register(SceneDefinition(
            key=self.GRAPH_GLOBAL_SEARCH,
            name="全局搜索 Map",
            category="graph",
            description="GraphRAG 全局搜索的 Map 阶段，从社区报告中提取答案片段",
            recommended_model="中等模型",
        ))

        # 工具类
        self._register(SceneDefinition(
            key=self.TITLE,
            name="会话标题",
            category="utility",
            description="根据首条消息自动生成会话标题（max_tokens=30）",
            recommended_model="最便宜模型",
        ))
        self._register(SceneDefinition(
            key=self.COMMAND_BLACKLIST,
            name="命令黑名单",
            category="utility",
            description="AI 生成命令黑名单的正则模式",
            recommended_model="便宜模型",
        ))
        self._register(SceneDefinition(
            key=self.CRON,
            name="定时任务",
            category="utility",
            description="定时任务执行（报告生成、数据汇总等）",
            recommended_model="根据任务复杂度选择",
        ))

        # 论文复现
        self._register(SceneDefinition(
            key=self.PAPER_PARSE,
            name="论文解析",
            category="paper",
            description="解析学术论文，提取标题、摘要、方法、实验结果",
            recommended_model="中等模型（长上下文）",
        ))
        self._register(SceneDefinition(
            key=self.PAPER_CLAIM,
            name="主张提取",
            category="paper",
            description="提取论文主张并生成验证标准（Rubric）",
            recommended_model="中等模型（JSON 模式）",
        ))
        self._register(SceneDefinition(
            key=self.PAPER_DEBUG,
            name="代码调试",
            category="paper",
            description="分析执行错误并生成修复补丁",
            recommended_model="代码模型（Claude/GPT-4）",
        ))

        # 入口层
        self._register(SceneDefinition(
            key=self.WECHAT,
            name="微信消息",
            category="entry",
            description="微信端用户消息处理",
            recommended_model="主聊天模型",
        ))
        self._register(SceneDefinition(
            key=self.CHAT,
            name="主聊天",
            category="entry",
            description="Web 端主聊天（默认场景）",
            recommended_model="主聊天模型",
        ))

    def _register(self, scene: SceneDefinition):
        """注册单个场景（内部方法）"""
        self._scenes[scene.key] = scene

    def register(
        self,
        key: str,
        name: str,
        category: str = "custom",
        description: str = "",
        recommended_model: str = "",
    ) -> SceneDefinition:
        """动态注册自定义场景（供二次开发使用）

        Args:
            key: 场景标识（如 "my_custom_scene"）
            name: 显示名称（如 "我的自定义场景"）
            category: 分类，可选 "custom" 或已有分类
            description: 场景描述
            recommended_model: 推荐模型类型提示

        Returns:
            注册的场景定义
        """
        self._ensure_initialized()
        with self._lock:
            scene = SceneDefinition(
                key=key,
                name=name,
                category=category,
                description=description,
                recommended_model=recommended_model,
                is_builtin=False,
            )
            self._scenes[key] = scene
            return scene

    def get(self, key: str) -> Optional[SceneDefinition]:
        """获取场景定义"""
        self._ensure_initialized()
        return self._scenes.get(key)

    def get_all(self) -> List[SceneDefinition]:
        """获取所有场景（按分类排序）"""
        self._ensure_initialized()
        scenes = list(self._scenes.values())
        # 按分类 order 排序，同分类内按 key 排序
        def sort_key(s: SceneDefinition):
            cat = self.CATEGORIES.get(s.category, {})
            return (cat.get("order", 99), s.key)
        return sorted(scenes, key=sort_key)

    def get_by_category(self, category: str) -> List[SceneDefinition]:
        """获取指定分类下的所有场景"""
        self._ensure_initialized()
        return [s for s in self._scenes.values() if s.category == category]

    def get_categories(self) -> Dict[str, Dict[str, Any]]:
        """获取所有分类定义"""
        self._ensure_initialized()
        # 只返回有场景的分类
        used_cats = set(s.category for s in self._scenes.values())
        return {k: v for k, v in self.CATEGORIES.items() if k in used_cats}

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典（供 API 返回）"""
        self._ensure_initialized()
        return {
            "categories": self.get_categories(),
            "scenes": [
                {
                    "key": s.key,
                    "name": s.name,
                    "category": s.category,
                    "description": s.description,
                    "recommended_model": s.recommended_model,
                    "is_builtin": s.is_builtin,
                }
                for s in self.get_all()
            ],
        }

    def is_valid(self, key: str) -> bool:
        """检查场景是否已注册"""
        self._ensure_initialized()
        return key in self._scenes


# 模块级单例
scenes = SceneRegistry()
