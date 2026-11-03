"""
论文解析工具

解析学术论文，提取标题、摘要、方法、实验结果和主张
支持 PDF 文件和 arXiv URL
"""

import json
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import requests
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from backend.utils.log_utils import log
from .common_utils import (
    get_config,
    get_llm_instance,
    retry_on_failure,
    PerformanceMonitor,
    create_retry_session,
    validate_url,
    truncate_text
)

logger = log


def _get_llm():
    """
    获取 LLM 实例（使用场景路由）

    Returns:
        ChatOpenAI: LLM 实例

    Raises:
        ValueError: 如果 LLM 配置不可用
    """
    try:
        return get_llm_instance(scene="paper_parse")
    except ValueError as e:
        # 配置缺失，记录错误并重新抛出
        logger.error(f"LLM 配置缺失: {e}")
        raise
    except Exception as e:
        # 其他错误（网络、认证等）
        logger.error(f"LLM 初始化失败: {type(e).__name__}: {e}")
        raise RuntimeError(f"LLM 初始化失败: {e}") from e


class PaperParseInput(BaseModel):
    """论文解析工具输入"""
    paper_url: Optional[str] = Field(None, description="论文 URL (arXiv/PDF)")
    paper_file: Optional[str] = Field(None, description="上传的论文文件 ID")
    extract_claims: bool = Field(True, description="是否提取主张")


@tool(args_schema=PaperParseInput)
def parse_paper(
    paper_url: Optional[str] = None,
    paper_file: Optional[str] = None,
    extract_claims: bool = True
) -> str:
    """
    解析学术论文，提取标题、摘要、方法、实验结果和主张。

    使用场景：
    - 论文复现的第一步
    - 需要理解论文内容
    - 需要提取论文主张

    返回：
    - 论文标题、作者、摘要
    - 方法描述
    - 实验结果表格
    - 主张列表（可选）
    """
    with PerformanceMonitor("论文解析") as monitor:
        try:
            config = get_config()

            # 1. 验证输入
            if not paper_url and not paper_file:
                return json.dumps({
                    "error": "必须提供 paper_url 或 paper_file",
                    "version": "paper.parsed/v1"
                }, ensure_ascii=False)

            if paper_url and not validate_url(paper_url):
                return json.dumps({
                    "error": f"无效的 URL: {paper_url}",
                    "version": "paper.parsed/v1"
                }, ensure_ascii=False)

            # 2. 获取论文内容
            monitor.add_stage("获取论文", 10)
            if paper_file:
                paper_path = _get_uploaded_file(paper_file)
                logger.info(f"📂 使用上传文件: {paper_path}")
            elif paper_url:
                paper_path = _download_paper(paper_url)
                logger.info(f"⬇️ 下载论文: {paper_url}")

            # 3. 提取文本
            monitor.add_stage("提取文本", 30)
            text = _extract_text(paper_path)
            logger.info(f"📄 提取文本: {len(text)} 字符")

            # 4. 使用 GraphRAG 提取实体和关系
            monitor.add_stage("提取实体", 50)
            entities, relations = _extract_with_graphrag(text)
            logger.info(f"🔍 提取实体: {len(entities)} 个, 关系: {len(relations)} 条")

            # 5. 构建结构化输出
            monitor.add_stage("构建输出", 80)
            parsed_paper = {
                "version": "paper.parsed/v1",
                "title": _find_entity(entities, "title"),
                "authors": _find_entities(entities, "author"),
                "abstract": _find_entity(entities, "abstract"),
                "methods": _find_entity(entities, "method"),
                "experiments": _find_entities(entities, "experiment"),
                "claims": _find_entities(entities, "claim") if extract_claims else [],
                "entities_count": len(entities),
                "relations_count": len(relations),
                "text_length": len(text),
            }

            # 6. 存储到知识图谱
            _store_to_graphrag(entities, relations)

            monitor.add_stage("完成", 100)
            logger.info(f"✅ 论文解析完成: {parsed_paper['title']}")
            return json.dumps(parsed_paper, ensure_ascii=False, indent=2)

        except Exception as e:
            # 增强错误信息，包含错误类型和上下文
            import traceback
            error_type = type(e).__name__
            error_msg = str(e)
            stack_trace = traceback.format_exc()

            logger.error(f"❌ 论文解析失败: {error_type}: {error_msg}", exc_info=True)

            # 返回详细错误信息（生产环境可配置是否返回堆栈）
            return json.dumps({
                "error": error_msg,
                "error_type": error_type,
                "error_context": "论文解析流程",
                "version": "paper.parsed/v1",
                # 开发环境可包含堆栈
                # "stack_trace": stack_trace if DEBUG else None
            }, ensure_ascii=False)


def _get_uploaded_file(file_id: str) -> Path:
    """获取上传的文件"""
    # 🔒 安全检查：验证 file_id 合法性
    from .security_utils import validate_file_id
    is_valid, error = validate_file_id(file_id)
    if not is_valid:
        raise ValueError(f"非法的 file_id: {error}")

    try:
        from backend.db.uploads import get_upload_path
        return get_upload_path(file_id)
    except ImportError:
        # 如果没有上传模块，使用安全的临时路径
        logger.warning("未找到上传模块，使用安全的临时路径")
        from .security_utils import sanitize_path
        safe_path = sanitize_path("/tmp/uploads", file_id)
        return Path(safe_path)


@retry_on_failure(max_retries=3, exceptions=(ConnectionError, TimeoutError))
def _download_paper(url: str) -> Path:
    """
    下载论文（带重试）

    Args:
        url: 论文 URL

    Returns:
        Path: 本地文件路径

    Raises:
        ConnectionError: 网络连接错误
        TimeoutError: 下载超时
    """
    config = get_config()

    # 支持 arXiv URL
    if "arxiv.org" in url:
        arxiv_id = url.split("/")[-1]
        if "abs" in url:
            arxiv_id = url.split("abs/")[-1]
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        logger.info(f"📄 arXiv PDF: {pdf_url}")
    else:
        pdf_url = url

    # 使用带重试的 session
    session = create_retry_session(
        total_retries=config.request_max_retries,
        backoff_factor=config.request_retry_delay
    )

    try:
        response = session.get(pdf_url, timeout=config.request_timeout)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"❌ 下载论文失败: {e}")
        raise

    # 保存到临时文件（使用 with 语句确保资源释放）
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(response.content)
        logger.info(f"✅ 论文已下载: {len(response.content)} 字节")
        return Path(temp_file.name)


def _extract_text(paper_path: Path) -> str:
    """提取论文文本"""
    if not paper_path.exists():
        raise FileNotFoundError(f"论文文件不存在: {paper_path}")

    if paper_path.suffix.lower() == ".pdf":
        return _extract_pdf_text(paper_path)
    else:
        return paper_path.read_text(encoding="utf-8")


def _extract_pdf_text(pdf_path: Path) -> str:
    """
    从 PDF 提取文本（带进度）

    Args:
        pdf_path: PDF 文件路径

    Returns:
        str: 提取的文本内容

    Raises:
        ImportError: 如果没有安装 PDF 处理库
        Exception: PDF 提取失败
    """
    config = get_config()

    try:
        # 优先使用 pypdf（新版本，requirements.txt 中已安装）
        import pypdf

        text_parts = []
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            total_pages = len(reader.pages)

            logger.info(f"📖 开始提取 PDF: {total_pages} 页")

            for i, page in enumerate(reader.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

                    # 每处理 10 页记录一次进度
                    if i % 10 == 0 or i == total_pages:
                        progress = int(i / total_pages * 100)
                        logger.info(f"📄 PDF 提取进度: {i}/{total_pages} 页 ({progress}%)")

                except Exception as e:
                    logger.warning(f"提取第 {i} 页失败: {e}")

        text = "\n\n".join(text_parts)
        logger.info(f"✅ PDF 提取完成: {total_pages} 页, {len(text)} 字符")
        return text

    except ImportError as e:
        logger.error(f"❌ pypdf 导入失败: {e}")
        logger.warning("尝试使用 PyPDF2（旧版本）...")
        try:
            # 回退到 PyPDF2（旧版本）
            import PyPDF2

            text_parts = []
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                total_pages = len(reader.pages)

                logger.info(f"📖 开始提取 PDF (PyPDF2): {total_pages} 页")

                for i, page in enumerate(reader.pages, 1):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)

                        # 每处理 10 页记录一次进度
                        if i % 10 == 0 or i == total_pages:
                            progress = int(i / total_pages * 100)
                            logger.info(f"📄 PDF 提取进度: {i}/{total_pages} 页 ({progress}%)")

                    except Exception as e:
                        logger.warning(f"提取第 {i} 页失败: {e}")

            text = "\n\n".join(text_parts)
            logger.info(f"✅ PDF 提取完成 (PyPDF2): {len(text)} 字符")
            return text

        except ImportError:
            logger.warning("PyPDF2 也不可用，尝试 pdfplumber...")
            try:
                import pdfplumber

                text_parts = []
                with pdfplumber.open(pdf_path) as pdf:
                    total_pages = len(pdf.pages)
                    logger.info(f"📖 开始提取 PDF (pdfplumber): {total_pages} 页")

                    for i, page in enumerate(pdf.pages, 1):
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)

                        # 每处理 10 页记录一次进度
                        if i % 10 == 0 or i == total_pages:
                            progress = int(i / total_pages * 100)
                            logger.info(f"📄 PDF 提取进度: {i}/{total_pages} 页 ({progress}%)")

                text = "\n\n".join(text_parts)
                logger.info(f"✅ PDF 提取完成 (pdfplumber): {len(text)} 字符")
                return text

            except ImportError:
                error_msg = "请安装 pypdf 或 PyPDF2 或 pdfplumber: pip install pypdf 或 pip install PyPDF2 或 pip install pdfplumber"
                logger.error(f"❌ {error_msg}")
                raise ImportError(error_msg)

    except Exception as e:
        logger.error(f"❌ PDF 提取失败: {e}", exc_info=True)
        raise


def _extract_with_graphrag(text: str) -> tuple:
    """
    使用 GraphRAG 提取实体和关系

    Args:
        text: 论文文本

    Returns:
        tuple: (entities, relations)
    """
    try:
        from backend.graphrag.extractor import GraphRAGExtractor

        extractor = GraphRAGExtractor()
        entities, relations = extractor.extract(text)

        return entities, relations

    except ImportError:
        logger.warning("未找到 GraphRAG 模块，使用 LLM 提取")
        return _extract_with_llm(text)
    except Exception as e:
        logger.error(f"GraphRAG 提取失败: {type(e).__name__}: {e}")
        # 回退到 LLM 提取
        logger.info("回退到 LLM 提取...")
        return _extract_with_llm(text)


def _extract_with_llm(text: str) -> tuple:
    """
    使用 LLM 提取实体和关系

    Args:
        text: 论文文本

    Returns:
        tuple: (entities, relations)

    Raises:
        ValueError: 如果 LLM 配置不可用
        RuntimeError: 如果 LLM 调用失败
    """
    config = get_config()

    try:
        # 使用场景路由获取 LLM（可能抛出 ValueError 或 RuntimeError）
        model = get_llm_instance(scene="paper_parse")
    except (ValueError, RuntimeError) as e:
        logger.error(str(e))
        raise

    # 截断文本（避免超过 token 限制）
    if len(text) > config.max_text_length:
        text = text[:config.max_text_length]
        logger.warning(f"文本截断到 {config.max_text_length} 字符")

    prompt = f"""
你是一个学术论文研究助手。请从以下论文文本中提取关键信息。

论文文本：
{text}

请按以下 JSON 格式输出：

{{
  "entities": [
    {{
      "type": "title/author/abstract/method/experiment/claim",
      "name": "实体名称",
      "description": "实体描述"
    }}
  ],
  "relations": [
    {{
      "source": "源实体名称",
      "target": "目标实体名称",
      "type": "关系类型",
      "description": "关系描述"
    }}
  ]
}}

要求：
1. 提取论文标题、作者、摘要、方法、实验结果
2. 识别论文的主要主张（claims）
3. 建立实体之间的关系
4. 每个实体都有类型、名称和描述
"""

    response = model.invoke(prompt)

    try:
        data = json.loads(response.content)
        return data.get("entities", []), data.get("relations", [])
    except json.JSONDecodeError:
        logger.error("LLM 输出不是有效的 JSON")
        return [], []


def _find_entity(entities: list, entity_type: str) -> Optional[str]:
    """查找特定类型的实体"""
    for entity in entities:
        if isinstance(entity, dict) and entity.get("type") == entity_type:
            return entity.get("name") or entity.get("description")
    return None


def _find_entities(entities: list, entity_type: str) -> List[str]:
    """查找所有特定类型的实体"""
    result = []
    for entity in entities:
        if isinstance(entity, dict) and entity.get("type") == entity_type:
            name = entity.get("name") or entity.get("description")
            if name:
                result.append(name)
    return result


def _store_to_graphrag(entities: list, relations: list, user_id: Optional[int] = None):
    """
    存储到知识图谱（论文实体暂时不存储）

    ⚠️ 设计决策：
    论文解析产生的实体与知识库文档、用户记忆性质不同：
    - 知识库文档：企业级知识，多人可见（source_document_id）
    - 用户记忆：个人上下文，仅自己可见（user_id）
    - 论文实体：论文复现专用，不应在正常对话中检索

    如果存储到知识图谱，会污染对话检索结果：
    - 用户 A 解析论文 → 存储 entity(user_id=A)
    - 用户 A 对话时，GraphRAG 会检索到论文实体
    - 这会干扰正常的对话上下文

    TODO: 未来可考虑：
    1. 创建独立的论文知识库（source_paper_id）
    2. 或在可见性规则中添加 artifact 类型过滤
    3. 或仅在论文复现流程中使用，不持久化

    当前方案：不存储到知识图谱，仅返回给前端使用
    """
    if not entities:
        logger.info("没有实体需要存储")
        return

    # 🔒 论文实体不存储到知识图谱，避免污染对话检索
    logger.info(f"📊 论文实体不存储到知识图谱（避免对话检索污染）")
    logger.info(f"   提取了 {len(entities)} 个实体, {len(relations)} 条关系")
    logger.info(f"   实体将通过返回值传递给后续工具使用")

    # 仍然记录统计信息
    return {
        "entities_count": len(entities),
        "relations_count": len(relations),
        "stored": False,
        "reason": "论文实体不应污染对话检索"
    }


def _map_entity_type(type_str: str) -> "EntityType":
    """映射实体类型字符串到 EntityType 枚举"""
    from backend.graphrag.types import EntityType

    type_map = {
        "title": EntityType.FACT,
        "author": EntityType.PERSON,
        "abstract": EntityType.FACT,
        "method": EntityType.CONCEPT,
        "experiment": EntityType.EVENT,
        "claim": EntityType.FACT,
        "concept": EntityType.CONCEPT,
        "person": EntityType.PERSON,
        "organization": EntityType.ORGANIZATION,
        "location": EntityType.LOCATION,
        "event": EntityType.EVENT,
        "fact": EntityType.FACT,
    }

    return type_map.get(type_str.lower(), EntityType.OTHER)


def _map_relation_type(type_str: str) -> "RelationType":
    """
    映射关系类型字符串到 RelationType 枚举

    Args:
        type_str: 关系类型字符串

    Returns:
        RelationType: 关系类型枚举值
    """
    from backend.graphrag.types import RelationType

    type_map = {
        # 论文相关
        "authored_by": RelationType.RELATED_TO,      # 作者关系（用 RELATED_TO 代替）
        "uses": RelationType.USES,                    # 使用
        "produces": RelationType.RELATED_TO,         # 产出（用 RELATED_TO 代替）
        "related_to": RelationType.RELATED_TO,       # 相关
        "part_of": RelationType.PART_OF,             # 部分属于
        "depends_on": RelationType.DEPENDS_ON,       # 依赖

        # 人物关系
        "knows": RelationType.KNOWS,                 # 认识
        "works_with": RelationType.WORKS_WITH,       # 共事
        "reports_to": RelationType.REPORTS_TO,       # 汇报

        # 组织关系
        "works_at": RelationType.WORKS_AT,           # 在...工作
        "member_of": RelationType.MEMBER_OF,         # 成员
        "founded": RelationType.FOUNDED,             # 创立

        # 项目关系
        "works_on": RelationType.WORKS_ON,           # 参与
        "owns": RelationType.OWNS,                   # 负责

        # 知识关系
        "knows_about": RelationType.KNOWS_ABOUT,     # 了解
        "expert_in": RelationType.EXPERT_IN,         # 专家
        "learned": RelationType.LEARNED,             # 学到

        # 因果关系
        "caused": RelationType.CAUSED,               # 导致

        # 时间关系
        "happened_after": RelationType.HAPPENED_AFTER,   # 发生在...之后
        "happened_before": RelationType.HAPPENED_BEFORE, # 发生在...之前
    }

    return type_map.get(type_str.lower(), RelationType.RELATED_TO)


# 注册到 Hermes 工具系统
def register_paper_tools():
    """注册论文工具到 Hermes"""
    from backend.tools.tools_decorator import get_project_tools

    tools = get_project_tools()
    if parse_paper not in tools:
        parse_paper._toolset = "paper_repro"  # 论文复现工具集
        tools.append(parse_paper)
        logger.info("✅ 注册 parse_paper 工具")


# 自动注册
try:
    register_paper_tools()
except Exception as e:
    logger.warning(f"自动注册工具失败: {e}")