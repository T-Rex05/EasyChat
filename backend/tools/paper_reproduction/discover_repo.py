"""
GitHub 仓库发现工具

搜索与论文匹配的 GitHub 仓库，评估相关度
"""

import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from backend.utils.log_utils import log

logger = log


def _get_llm():
    """获取 LLM 实例"""
    try:
        from langchain_openai import ChatOpenAI
        import os

        return ChatOpenAI(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("LLM_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL"),
            temperature=0.7
        )
    except Exception as e:
        logger.warning(f"LLM 初始化失败: {e}")
        return None


class DiscoverRepoInput(BaseModel):
    """仓库发现工具输入"""
    parsed_paper: Dict[str, Any] = Field(description="解析后的论文")
    claim_rubric: Dict[str, Any] = Field(description="冻结的 Claim Rubric")
    max_repos: int = Field(5, description="最多返回的仓库数")
    language: Optional[str] = Field(None, description="编程语言过滤（如 python, pytorch）")


@tool(args_schema=DiscoverRepoInput)
def discover_repo(
    parsed_paper: Dict[str, Any],
    claim_rubric: Dict[str, Any],
    max_repos: int = 5,
    language: Optional[str] = None
) -> str:
    """
    搜索与论文匹配的 GitHub 仓库，评估相关度。

    使用场景：
    - 论文解析后的第三步
    - 需要找到论文代码实现
    - 需要评估仓库质量

    返回：
    - 匹配的仓库列表
    - 每个仓库包含相关度分数、星数、README 摘要
    - 推荐的最佳仓库
    """
    try:
        # 1. 验证输入
        if not parsed_paper or not isinstance(parsed_paper, dict):
            return json.dumps({
                "error": "parsed_paper 必须是字典",
                "version": "repo.discovered/v1"
            }, ensure_ascii=False)

        if not claim_rubric or not isinstance(claim_rubric, dict):
            return json.dumps({
                "error": "claim_rubric 必须是字典",
                "version": "repo.discovered/v1"
            }, ensure_ascii=False)

        # 2. 构建搜索查询
        queries = _build_search_queries(parsed_paper, claim_rubric, language)
        logger.info(f"🔍 搜索查询: {queries}")

        # 3. 搜索 GitHub
        all_repos = []
        for query in queries:
            repos = _search_github(query, max_repos * 2)
            all_repos.extend(repos)

        # 4. 去重
        unique_repos = _deduplicate_repos(all_repos)
        logger.info(f"📊 找到 {len(unique_repos)} 个唯一仓库")

        # 5. 评估相关度
        scored_repos = []
        for repo in unique_repos[:max_repos * 3]:  # 评估前 max_repos * 3 个
            score = _evaluate_relevance(repo, parsed_paper, claim_rubric)
            repo["relevance_score"] = score
            scored_repos.append(repo)

        # 6. 排序并取前 N 个
        scored_repos.sort(key=lambda r: r["relevance_score"], reverse=True)
        top_repos = scored_repos[:max_repos]

        # 7. 获取 README 摘要
        for repo in top_repos:
            repo["readme_summary"] = _get_readme_summary(repo["full_name"])

        # 8. 构建结果
        result = {
            "version": "repo.discovered/v1",
            "paper_title": parsed_paper.get("title", ""),
            "search_queries": queries,
            "total_found": len(unique_repos),
            "repos": top_repos,
            "recommended": top_repos[0] if top_repos else None,
            "created_at": datetime.now().isoformat()
        }

        # 9. 检查是否找到仓库
        if not top_repos:
            logger.warning(f"⚠️ 未找到匹配的仓库，建议：")
            logger.warning(f"   1. 论文可能没有公开的代码实现")
            logger.warning(f"   2. 尝试使用更通用的搜索词")
            logger.warning(f"   3. 手动提供仓库 URL")
            result["warning"] = "未找到匹配的仓库，可以尝试手动提供仓库 URL 或使用代码生成模式"
            result["suggestions"] = [
                "在 GitHub 上搜索论文标题",
                "查看论文是否提供了代码链接",
                "使用 '代码生成' 模式而非 '仓库复现' 模式"
            ]
        else:
            logger.info(f"✅ 仓库发现完成: 推荐 {top_repos[0]['full_name']}")

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"❌ 仓库发现失败: {e}", exc_info=True)
        return json.dumps({
            "error": str(e),
            "version": "repo.discovered/v1"
        }, ensure_ascii=False)


def _build_search_queries(parsed_paper: Dict, claim_rubric: Dict, language: Optional[str] = None) -> List[str]:
    """构建 GitHub 搜索查询"""
    queries = []

    # 1. 从标题提取关键词
    title = parsed_paper.get("title", "")
    if title:
        # 移除常见停用词
        keywords = _extract_keywords(title)
        if keywords:
            query = " ".join(keywords[:5])
            if language:
                query += f" language:{language}"
            queries.append(query)

    # 2. 从方法中提取
    methods = parsed_paper.get("methods", "")
    if methods:
        method_keywords = _extract_keywords(methods)
        if method_keywords:
            query = " ".join(method_keywords[:3])
            if language:
                query += f" language:{language}"
            queries.append(query)

    # 3. 从主张中提取指标
    claims = claim_rubric.get("claims", [])
    for claim in claims[:3]:  # 前 3 个主张
        criteria = claim.get("criteria", [])
        for criterion in criteria:
            metric = criterion.get("metric_name", "")
            if metric and len(metric) > 2:
                queries.append(f"{metric} implementation")

    return queries[:5]  # 最多 5 个查询


def _extract_keywords(text: str) -> List[str]:
    """从文本中提取关键词"""
    # 简单的关键词提取（实际可使用 NLP）
    stopwords = {"the", "a", "an", "for", "and", "or", "of", "in", "on", "to", "with", "by"}

    # 分词
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())

    # 过滤停用词
    keywords = [w for w in words if w not in stopwords]

    # 去重并保持顺序
    seen = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)

    return unique


def _search_github(query: str, max_results: int = 10) -> List[Dict]:
    """搜索 GitHub 仓库"""
    try:
        import requests

        # GitHub Search API
        url = "https://api.github.com/search/repositories"
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": max_results
        }

        headers = {
            "Accept": "application/vnd.github.v3+json",
            # 如果有 token，可以提高速率限制
            # "Authorization": f"token {GITHUB_TOKEN}"
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])

        # 提取关键字段
        repos = []
        for item in items:
            repo = {
                "full_name": item.get("full_name", ""),
                "description": item.get("description", ""),
                "html_url": item.get("html_url", ""),
                "stargazers_count": item.get("stargazers_count", 0),
                "forks_count": item.get("forks_count", 0),
                "language": item.get("language", ""),
                "updated_at": item.get("updated_at", ""),
                "topics": item.get("topics", []),
            }
            repos.append(repo)

        logger.info(f"🔍 GitHub 搜索 '{query}': {len(repos)} 个结果")
        return repos

    except Exception as e:
        logger.warning(f"GitHub 搜索失败: {e}")
        return []


def _deduplicate_repos(repos: List[Dict]) -> List[Dict]:
    """去重仓库"""
    seen = set()
    unique = []

    for repo in repos:
        full_name = repo.get("full_name", "")
        if full_name and full_name not in seen:
            seen.add(full_name)
            unique.append(repo)

    return unique


def _evaluate_relevance(repo: Dict, parsed_paper: Dict, claim_rubric: Dict) -> float:
    """评估仓库与论文的相关度"""
    score = 0.0

    # 1. 星数权重 (0-30 分)
    stars = repo.get("stargazers_count", 0)
    if stars > 1000:
        score += 30
    elif stars > 500:
        score += 20
    elif stars > 100:
        score += 10
    elif stars > 10:
        score += 5

    # 2. 描述匹配度 (0-40 分)
    # 🔒 安全处理：确保字段不为 None
    description = (repo.get("description") or "").lower()
    title = (parsed_paper.get("title") or "").lower()

    # 提取标题关键词
    title_keywords = set(_extract_keywords(title))
    desc_keywords = set(_extract_keywords(description))

    overlap = title_keywords & desc_keywords
    if overlap:
        score += min(40, len(overlap) * 10)

    # 3. 主张指标匹配 (0-30 分)
    claims = claim_rubric.get("claims", [])
    for claim in claims:
        criteria = claim.get("criteria", [])
        for criterion in criteria:
            metric = (criterion.get("metric_name") or "").lower()
            full_name = (repo.get("full_name") or "").lower()
            if metric in description or metric in full_name:
                score += 10

    # 4. 语言匹配加分
    repo_lang = (repo.get("language") or "").lower()
    if repo_lang in ["python", "pytorch", "tensorflow", "jupyter notebook"]:
        score += 10

    # 5. Topics 匹配
    topics = repo.get("topics") or []
    if topics:
        topics_lower = [t.lower() for t in topics if t]
        for kw in title_keywords:
            if kw in topics_lower:
                score += 5

    return min(100, score)


def _get_readme_summary(full_name: str) -> str:
    """获取 README 摘要"""
    try:
        import requests

        # GitHub README API
        url = f"https://api.github.com/repos/{full_name}/readme"
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            content = data.get("content", "")

            # Base64 解码
            import base64
            decoded = base64.b64decode(content).decode("utf-8")

            # 提取前 500 字符
            summary = decoded[:500].replace("\n", " ").strip()

            # 如果太长，截断
            if len(decoded) > 500:
                summary += "..."

            return summary

        return "README 不可用"

    except Exception as e:
        logger.warning(f"获取 README 失败: {e}")
        return "README 获取失败"


# 注册到 Hermes 工具系统
def register_discover_repo_tool():
    """注册仓库发现工具到 Hermes"""
    from backend.tools.tools_decorator import get_project_tools

    tools = get_project_tools()
    if discover_repo not in tools:
        discover_repo._toolset = "paper_repro"  # 论文复现工具集
        tools.append(discover_repo)
        logger.info("✅ 注册 discover_repo 工具")


# 自动注册
try:
    register_discover_repo_tool()
except Exception as e:
    logger.warning(f"自动注册工具失败: {e}")