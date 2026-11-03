"""
论文复现系统单元测试

测试核心功能和安全性
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# 导入被测试的模块
from backend.tools.paper_reproduction import (
    parse_paper,
    extract_claim_rubric,
    discover_repo,
    docker_sandbox,
    debug_paper_code,
    build_evidence_graph
)
from backend.tools.paper_reproduction.security_utils import (
    validate_command,
    validate_file_id,
    sanitize_path
)
from backend.tools.paper_reproduction.common_utils import (
    PaperReproductionConfig,
    get_config,
    truncate_text,
    validate_url,
    PerformanceMonitor
)


# ==================== 配置测试 ====================

class TestConfig:
    """配置管理测试"""

    def test_default_config(self):
        """测试默认配置"""
        config = PaperReproductionConfig()

        assert config.llm_model == "gpt-4o-mini"
        assert config.llm_temperature == 0.7
        assert config.docker_timeout == 300
        assert config.max_claims == 10

    def test_config_singleton(self):
        """测试配置单例"""
        config1 = get_config()
        config2 = get_config()

        assert config1 is config2


# ==================== 安全验证测试 ====================

class TestSecurity:
    """安全验证测试"""

    def test_validate_command_safe(self):
        """测试安全命令验证"""
        safe_commands = [
            "python main.py",
            "pip install numpy",
            "pytest",
            "ls -la",
            "make test"
        ]

        for cmd in safe_commands:
            is_safe, error = validate_command(cmd)
            assert is_safe, f"命令应该被允许: {cmd} - {error}"

    def test_validate_command_dangerous(self):
        """测试危险命令拒绝"""
        dangerous_commands = [
            "rm -rf /",
            "cat /etc/passwd; ls",
            "python main.py && rm -rf /",
            "$(whoami)",
            "`id`",
            "ls > /etc/passwd",
        ]

        for cmd in dangerous_commands:
            is_safe, error = validate_command(cmd)
            assert not is_safe, f"命令应该被拒绝: {cmd}"
            assert error, f"应该有错误信息: {cmd}"

    def test_validate_file_id_safe(self):
        """测试安全文件 ID 验证"""
        safe_ids = [
            "abc123",
            "file-123",
            "test_file",
            "UPPERCASE"
        ]

        for file_id in safe_ids:
            is_valid, error = validate_file_id(file_id)
            assert is_valid, f"文件 ID 应该合法: {file_id} - {error}"

    def test_validate_file_id_dangerous(self):
        """测试危险文件 ID 拒绝"""
        dangerous_ids = [
            "../../../etc/passwd",
            "file;rm -rf",
            "file$(whoami)",
            "/etc/passwd",
            "..\\..\\windows",
        ]

        for file_id in dangerous_ids:
            is_valid, error = validate_file_id(file_id)
            assert not is_valid, f"文件 ID 应该被拒绝: {file_id}"
            assert error, f"应该有错误信息: {file_id}"

    def test_sanitize_path(self):
        """测试路径安全化"""
        # 合法路径
        safe_path = sanitize_path("/tmp/uploads", "file.txt")
        # Windows 路径会转换，所以只检查文件名
        assert "file.txt" in safe_path

        # 路径遍历攻击
        with pytest.raises(ValueError, match="路径遍历"):
            sanitize_path("/tmp/uploads", "../../../etc/passwd")


# ==================== 工具函数测试 ====================

class TestUtilities:
    """工具函数测试"""

    def test_truncate_text(self):
        """测试文本截断"""
        text = "a" * 100
        truncated = truncate_text(text, max_length=10)

        assert len(truncated) == 10
        assert truncated.endswith("...")

    def test_validate_url(self):
        """测试 URL 验证"""
        valid_urls = [
            "https://arxiv.org/abs/1706.03762",
            "http://example.com/paper.pdf",
            "https://github.com/user/repo"
        ]

        for url in valid_urls:
            assert validate_url(url), f"URL 应该合法: {url}"

        invalid_urls = [
            "not-a-url",
            "ftp://invalid",
            ""
        ]

        for url in invalid_urls:
            assert not validate_url(url), f"URL 应该非法: {url}"

    def test_performance_monitor(self):
        """测试性能监控器"""
        with PerformanceMonitor("测试任务") as monitor:
            monitor.add_stage("步骤 1", 50)
            monitor.add_stage("步骤 2", 100)

        summary = monitor.get_summary()
        assert summary["name"] == "测试任务"
        assert len(summary["stages"]) == 2
        assert summary["total_duration"] > 0


# ==================== 论文解析工具测试 ====================

class TestParsePaper:
    """论文解析工具测试"""

    def test_parse_paper_missing_input(self):
        """测试缺少输入参数"""
        result = parse_paper.invoke({})
        data = json.loads(result)

        assert "error" in data
        assert "必须提供" in data["error"]

    def test_parse_paper_invalid_url(self):
        """测试无效 URL"""
        result = parse_paper.invoke({
            "paper_url": "not-a-valid-url"
        })
        data = json.loads(result)

        assert "error" in data

    @patch('backend.tools.paper_reproduction.parse_paper._download_paper')
    @patch('backend.tools.paper_reproduction.parse_paper._extract_text')
    @patch('backend.tools.paper_reproduction.parse_paper._extract_with_graphrag')
    def test_parse_paper_success(self, mock_graphrag, mock_extract, mock_download):
        """测试成功解析论文"""
        # Mock 返回数据
        mock_download.return_value = Path("/tmp/test.pdf")
        mock_extract.return_value = "Test paper content"
        mock_graphrag.return_value = (
            [{"type": "title", "name": "Test Paper"}],
            []
        )

        result = parse_paper.invoke({
            "paper_url": "https://arxiv.org/abs/1234.5678"
        })
        data = json.loads(result)

        assert "version" in data
        assert data["version"] == "paper.parsed/v1"


# ==================== 主张提取工具测试 ====================

class TestExtractClaimRubric:
    """主张提取工具测试"""

    def test_extract_claim_rubric_invalid_input(self):
        """测试无效输入"""
        result = extract_claim_rubric.invoke({
            "parsed_paper": "not-a-dict"
        })
        data = json.loads(result)

        assert "error" in data

    def test_extract_claim_rubric_empty_input(self):
        """测试空输入"""
        result = extract_claim_rubric.invoke({
            "parsed_paper": {}
        })
        # 应该调用 LLM，但这里会失败
        data = json.loads(result)

        # 检查是否有错误或结果
        assert "version" in data


# ==================== 仓库发现工具测试 ====================

class TestDiscoverRepo:
    """仓库发现工具测试"""

    def test_discover_repo_missing_input(self):
        """测试缺少输入"""
        result = discover_repo.invoke({})
        data = json.loads(result)

        assert "error" in data


# ==================== Docker 沙箱工具测试 ====================

class TestDockerSandbox:
    """Docker 沙箱工具测试"""

    def test_docker_sandbox_invalid_action(self):
        """测试无效操作"""
        result = docker_sandbox.invoke({
            "action": "invalid_action"
        })
        data = json.loads(result)

        assert "error" in data
        assert "未知操作" in data["error"]

    def test_docker_sandbox_execute_missing_container(self):
        """测试缺少容器 ID"""
        result = docker_sandbox.invoke({
            "action": "execute",
            "command": "ls"
        })
        data = json.loads(result)

        assert "error" in data
        assert "container_id" in data["error"]

    def test_docker_sandbox_execute_dangerous_command(self):
        """测试危险命令拒绝"""
        result = docker_sandbox.invoke({
            "action": "execute",
            "container_id": "test-container",
            "command": "rm -rf /"
        })
        data = json.loads(result)

        assert "error" in data
        assert "不安全" in data["error"] or "危险" in data["error"]


# ==================== 证据图谱工具测试 ====================

class TestBuildEvidenceGraph:
    """证据图谱工具测试"""

    def test_build_evidence_graph_invalid_rubric(self):
        """测试无效 Rubric"""
        result = build_evidence_graph.invoke({
            "rubric": "not-a-dict",
            "execution_results": {}
        })
        data = json.loads(result)

        assert "error" in data

    def test_build_evidence_graph_empty(self):
        """测试空输入"""
        result = build_evidence_graph.invoke({
            "rubric": {},
            "execution_results": {}
        })
        data = json.loads(result)

        assert "version" in data
        assert "graph" in data
        assert "confidence" in data


# ==================== 集成测试 ====================

class TestIntegration:
    """集成测试"""

    def test_full_workflow_simulation(self):
        """测试完整工作流程模拟"""
        # 模拟数据
        parsed_paper = {
            "version": "paper.parsed/v1",
            "title": "Test Paper",
            "authors": ["Author 1"],
            "abstract": "Test abstract",
            "methods": "Test methods",
            "experiments": ["Exp 1"],
            "claims": []
        }

        rubric = {
            "version": "claim.rubric/v1",
            "paper_title": "Test Paper",
            "claims": [
                {
                    "id": "claim-001",
                    "title": "Test Claim",
                    "statement": "Test statement",
                    "claim_type": "quantitative",
                    "importance": 0.9,
                    "criteria": [
                        {
                            "id": "claim-001.criterion-01",
                            "description": "Test criterion",
                            "metric_name": "Accuracy",
                            "expected_value": 0.9,
                            "tolerance": 0.1,
                            "required_evidence": ["run"]
                        }
                    ]
                }
            ]
        }

        # 测试证据图谱构建
        result = build_evidence_graph.invoke({
            "rubric": rubric,
            "execution_results": {"success": True}
        })
        data = json.loads(result)

        assert "graph" in data
        assert "confidence" in data
        assert "summary" in data


# ==================== 运行测试 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])