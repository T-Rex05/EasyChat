"""
论文复现工具包

提供论文解析、主张提取、仓库发现、代码调试、证据图谱构建等工具
"""

from .parse_paper import parse_paper, PaperParseInput
from .extract_claim_rubric import extract_claim_rubric, ClaimRubricInput
from .discover_repo import discover_repo, DiscoverRepoInput
from .docker_sandbox import docker_sandbox, DockerSandboxInput
from .debug_paper_code import debug_paper_code, DebugPaperCodeInput
from .build_evidence_graph import build_evidence_graph, BuildEvidenceGraphInput

__all__ = [
    # 论文解析
    'parse_paper',
    'PaperParseInput',

    # 主张提取
    'extract_claim_rubric',
    'ClaimRubricInput',

    # 仓库发现
    'discover_repo',
    'DiscoverRepoInput',

    # Docker 沙箱
    'docker_sandbox',
    'DockerSandboxInput',

    # 代码调试
    'debug_paper_code',
    'DebugPaperCodeInput',

    # 证据图谱
    'build_evidence_graph',
    'BuildEvidenceGraphInput',
]


def get_paper_reproduction_tools():
    """获取所有论文复现工具"""
    return [
        parse_paper,
        extract_claim_rubric,
        discover_repo,
        docker_sandbox,
        debug_paper_code,
        build_evidence_graph,
    ]