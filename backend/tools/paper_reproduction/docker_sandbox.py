"""
Docker 沙箱执行工具

提供隔离的代码执行环境，支持论文代码调试
"""

import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from backend.utils.log_utils import log

logger = log


class DockerSandboxInput(BaseModel):
    """Docker 沙箱输入"""
    action: str = Field(description="操作类型: create/execute/destroy/status")
    container_id: Optional[str] = Field(None, description="容器 ID")
    image: Optional[str] = Field(None, description="Docker 镜像名称")
    repo_url: Optional[str] = Field(None, description="Git 仓库 URL")
    repo_path: Optional[str] = Field(None, description="仓库本地路径")
    command: Optional[str] = Field(None, description="要执行的命令")
    timeout: int = Field(300, description="执行超时（秒）")
    environment: Optional[Dict[str, str]] = Field(None, description="环境变量")
    volumes: Optional[Dict[str, str]] = Field(None, description="卷挂载 {宿主机路径: 容器路径}")


@tool(args_schema=DockerSandboxInput)
def docker_sandbox(
    action: str,
    container_id: Optional[str] = None,
    image: Optional[str] = None,
    repo_url: Optional[str] = None,
    repo_path: Optional[str] = None,
    command: Optional[str] = None,
    timeout: int = 300,
    environment: Optional[Dict[str, str]] = None,
    volumes: Optional[Dict[str, str]] = None
) -> str:
    """
    Docker 沙箱执行工具，提供隔离的代码执行环境。

    使用场景：
    - 论文代码调试
    - 运行实验代码
    - 隔离环境执行

    支持的操作：
    - create: 创建新容器
    - execute: 在容器中执行命令
    - destroy: 销毁容器
    - status: 查看容器状态

    返回：
    - 容器信息或执行结果
    """
    try:
        # 验证 Docker 是否可用
        if not _check_docker_available():
            return json.dumps({
                "error": "Docker 不可用，请确保已安装并启动 Docker",
                "version": "docker.sandbox/v1"
            }, ensure_ascii=False)

        # 分发操作
        if action == "create":
            return _create_container(image, repo_url, repo_path, environment, volumes)

        elif action == "execute":
            return _execute_in_container(container_id, command, timeout)

        elif action == "destroy":
            return _destroy_container(container_id)

        elif action == "status":
            return _get_container_status(container_id)

        else:
            return json.dumps({
                "error": f"未知操作: {action}",
                "version": "docker.sandbox/v1"
            }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"❌ Docker 沙箱操作失败: {e}", exc_info=True)
        return json.dumps({
            "error": str(e),
            "version": "docker.sandbox/v1"
        }, ensure_ascii=False)


def _check_docker_available() -> bool:
    """检查 Docker 是否可用（包括 Docker Desktop 是否运行）"""
    try:
        # 检查 docker 命令
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return False

        # 检查 Docker 是否真正运行（docker ps 需要守护进程）
        result = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_default_image() -> str:
    """
    获取默认 Docker 镜像（支持环境变量覆盖）

    优先级：
    1. 环境变量 SANDBOX_DEFAULT_IMAGE
    2. 默认值 python:3.10-slim

    Returns:
        str: Docker 镜像名称
    """
    import os

    # 环境变量优先
    env_image = os.getenv("SANDBOX_DEFAULT_IMAGE", "").strip()
    if env_image:
        logger.info(f"📌 使用环境变量镜像: {env_image}")
        return env_image

    # 默认镜像
    return "python:3.10-slim"


def _create_container(
    image: Optional[str],
    repo_url: Optional[str],
    repo_path: Optional[str],
    environment: Optional[Dict[str, str]],
    volumes: Optional[Dict[str, str]]
) -> str:
    """创建 Docker 容器"""
    # 获取镜像（优先级：参数 > 环境变量 > 默认值）
    if not image:
        image = _get_default_image()

    logger.info(f"🐳 使用镜像: {image}")

    # 构建命令
    cmd = ["docker", "run", "-d"]

    # 环境变量
    if environment:
        for key, value in environment.items():
            cmd.extend(["-e", f"{key}={value}"])

    # 卷挂载
    if volumes:
        for host_path, container_path in volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}"])

    # 克隆仓库到容器
    if repo_url:
        # 创建临时目录克隆仓库
        temp_dir = tempfile.mkdtemp()
        try:
            logger.info(f"📥 克隆仓库: {repo_url}")

            # 尝试不同的克隆方式
            clone_success = False
            clone_errors = []

            # 方式 1: 直接克隆
            clone_result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, temp_dir],
                capture_output=True,
                text=True,
                timeout=60
            )

            if clone_result.returncode == 0:
                clone_success = True
            else:
                clone_errors.append(f"直接克隆失败: {clone_result.stderr}")
                logger.warning(f"直接克隆失败，尝试使用镜像...")

                # 方式 2: 使用 GitHub 代理（中国大陆常见方案）
                proxy_urls = [
                    f"https://ghproxy.com/{repo_url}",
                    f"https://mirror.ghproxy.com/{repo_url}",
                ]

                for proxy_url in proxy_urls:
                    logger.info(f"尝试代理: {proxy_url}")
                    clone_result = subprocess.run(
                        ["git", "clone", "--depth", "1", proxy_url, temp_dir],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )

                    if clone_result.returncode == 0:
                        clone_success = True
                        logger.info(f"✅ 使用代理克隆成功")
                        break
                    else:
                        clone_errors.append(f"代理 {proxy_url} 失败: {clone_result.stderr}")

            if not clone_success:
                # 所有方式都失败了
                error_msg = "克隆仓库失败，尝试了以下方式：\n" + "\n".join(clone_errors)
                error_msg += "\n\n建议：\n"
                error_msg += "1. 检查网络连接\n"
                error_msg += "2. 使用 VPN 或代理\n"
                error_msg += "3. 手动下载仓库并使用本地路径"

                return json.dumps({
                    "error": error_msg,
                    "version": "docker.sandbox/v1"
                }, ensure_ascii=False)

            # 挂载仓库
            cmd.extend(["-v", f"{temp_dir}:/workspace/repo"])
            cmd.extend(["-w", "/workspace/repo"])

        except subprocess.TimeoutExpired:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return json.dumps({
                "error": "克隆仓库超时（60 秒），请检查网络连接",
                "version": "docker.sandbox/v1"
            }, ensure_ascii=False)

    elif repo_path:
        # 挂载本地仓库
        cmd.extend(["-v", f"{repo_path}:/workspace/repo"])
        cmd.extend(["-w", "/workspace/repo"])

    # 镜像名称
    cmd.append(image)

    # 启动命令（保持运行）
    cmd.extend(["tail", "-f", "/dev/null"])

    logger.info(f"🐳 创建容器: {' '.join(cmd)}")

    # 执行（增加超时到 120 秒，因为可能需要拉取镜像）
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 从 30 秒增加到 120 秒
        )
    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": "创建容器超时（120 秒），可能原因：\n"
                     "1. Docker Desktop 未启动\n"
                     "2. 镜像正在拉取中（python:3.10-slim）\n"
                     "3. Docker Desktop 启动缓慢\n\n"
                     "建议：\n"
                     "- 等待镜像拉取完成后重试\n"
                     "- 或使用已拉取的镜像",
            "version": "docker.sandbox/v1"
        }, ensure_ascii=False)

    if result.returncode != 0:
        return json.dumps({
            "error": f"创建容器失败: {result.stderr}",
            "version": "docker.sandbox/v1"
        }, ensure_ascii=False)

    container_id = result.stdout.strip()

    return json.dumps({
        "version": "docker.sandbox/v1",
        "status": "created",
        "container_id": container_id,
        "image": image,
        "created_at": datetime.now().isoformat()
    }, ensure_ascii=False, indent=2)


def _execute_in_container(
    container_id: Optional[str],
    command: Optional[str],
    timeout: int
) -> str:
    """在容器中执行命令"""
    if not container_id:
        return json.dumps({
            "error": "必须提供 container_id",
            "version": "docker.sandbox/v1"
        }, ensure_ascii=False)

    if not command:
        return json.dumps({
            "error": "必须提供 command",
            "version": "docker.sandbox/v1"
        }, ensure_ascii=False)

    # 🔒 安全检查：验证命令合法性
    from .security_utils import validate_command
    is_safe, error = validate_command(command)
    if not is_safe:
        logger.warning(f"⚠️ 拒绝执行危险命令: {command}")
        return json.dumps({
            "error": f"不安全的命令: {error}",
            "version": "docker.sandbox/v1"
        }, ensure_ascii=False)

    # 构建命令
    cmd = ["docker", "exec", container_id, "sh", "-c", command]

    logger.info(f"⚡ 执行命令: {command}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return json.dumps({
            "version": "docker.sandbox/v1",
            "status": "executed",
            "container_id": container_id,
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout[:5000],  # 截断
            "stderr": result.stderr[:5000],
            "executed_at": datetime.now().isoformat()
        }, ensure_ascii=False, indent=2)

    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": f"命令执行超时（{timeout}秒）",
            "version": "docker.sandbox/v1"
        }, ensure_ascii=False)


def _destroy_container(container_id: Optional[str]) -> str:
    """销毁容器"""
    if not container_id:
        return json.dumps({
            "error": "必须提供 container_id",
            "version": "docker.sandbox/v1"
        }, ensure_ascii=False)

    # 停止容器
    stop_cmd = ["docker", "stop", container_id]
    subprocess.run(stop_cmd, capture_output=True, timeout=30)

    # 删除容器
    rm_cmd = ["docker", "rm", container_id]
    result = subprocess.run(rm_cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        return json.dumps({
            "error": f"销毁容器失败: {result.stderr}",
            "version": "docker.sandbox/v1"
        }, ensure_ascii=False)

    return json.dumps({
        "version": "docker.sandbox/v1",
        "status": "destroyed",
        "container_id": container_id,
        "destroyed_at": datetime.now().isoformat()
    }, ensure_ascii=False)


def _get_container_status(container_id: Optional[str]) -> str:
    """获取容器状态"""
    if not container_id:
        # 列出所有容器
        cmd = ["docker", "ps", "-a", "--format", "json"]
    else:
        # 查看特定容器
        cmd = ["docker", "inspect", container_id]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=10
    )

    if result.returncode != 0:
        return json.dumps({
            "error": f"获取状态失败: {result.stderr}",
            "version": "docker.sandbox/v1"
        }, ensure_ascii=False)

    return json.dumps({
        "version": "docker.sandbox/v1",
        "status": "success",
        "container_id": container_id,
        "data": result.stdout
    }, ensure_ascii=False, indent=2)


class PaperDebugHarness:
    """
    论文代码调试工具

    专门用于论文复现的调试工具，支持：
    - 约束补丁
    - 自动回滚
    - 执行状态机
    """

    def __init__(
        self,
        container_id: str,
        repo_path: str,
        rubric: Dict[str, Any]
    ):
        self.container_id = container_id
        self.repo_path = Path(repo_path)
        self.rubric = rubric
        self.backup_dir = Path(tempfile.mkdtemp())
        self.max_patches = 3

    def execute(self) -> Dict[str, Any]:
        """执行调试流程"""
        state = {
            "status": "initialized",
            "attempts": 0,
            "patches": [],
            "results": []
        }

        # 1. 验证入口
        if not self._validate_entry():
            state["status"] = "entry_validation_failed"
            return state

        # 2. 执行基线
        baseline_result = self._execute_baseline()
        state["results"].append(baseline_result)

        if baseline_result.get("success"):
            state["status"] = "baseline_passed"
            return state

        # 3. 修复并重试
        for attempt in range(self.max_patches):
            state["attempts"] = attempt + 1

            # 生成补丁
            patch = self._generate_patch(baseline_result)
            if not patch:
                break

            # 应用补丁
            if not self._apply_patch(patch):
                break

            state["patches"].append(patch)

            # 重新执行
            retry_result = self._execute_baseline()
            state["results"].append(retry_result)

            if retry_result.get("success"):
                state["status"] = "fixed"
                return state

        # 4. 回滚
        self._rollback()
        state["status"] = "failed_after_max_attempts"
        return state

    def _validate_entry(self) -> bool:
        """验证入口文件是否存在"""
        # 检查关键文件
        entry_files = ["main.py", "train.py", "run.py", "setup.py"]
        for f in entry_files:
            if (self.repo_path / f).exists():
                logger.info(f"✅ 找到入口文件: {f}")
                return True

        logger.warning("❌ 未找到入口文件")
        return False

    def _execute_baseline(self) -> Dict[str, Any]:
        """执行基线命令"""
        # 尝试常见的运行命令
        commands = [
            "python main.py",
            "python train.py",
            "python run.py",
            "python setup.py install",
            "pytest",
        ]

        for cmd in commands:
            result = self._run_command(cmd)
            if result.get("exit_code") == 0:
                return {
                    "success": True,
                    "command": cmd,
                    "output": result.get("stdout", "")
                }

        # 都失败了，返回第一个失败的详细信息
        return {
            "success": False,
            "error": "所有基线命令都失败",
            "attempts": [self._run_command(c) for c in commands[:3]]
        }

    def _run_command(self, command: str, timeout: int = 60) -> Dict[str, Any]:
        """在容器中运行命令"""
        cmd = ["docker", "exec", self.container_id, "bash", "-c", command]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            return {
                "command": command,
                "exit_code": result.returncode,
                "stdout": result.stdout[:1000],
                "stderr": result.stderr[:1000]
            }

        except subprocess.TimeoutExpired:
            return {
                "command": command,
                "exit_code": -1,
                "error": "timeout"
            }

    def _generate_patch(self, error_result: Dict) -> Optional[Dict]:
        """根据错误生成补丁"""
        # 简单的错误分析（实际可使用 LLM）
        error_msg = error_result.get("stderr", "") or error_result.get("error", "")

        # 常见错误修复
        patches = {
            "ModuleNotFoundError": {
                "action": "install",
                "package": self._extract_missing_package(error_msg)
            },
            "FileNotFoundError": {
                "action": "create",
                "file": self._extract_missing_file(error_msg)
            },
            "TypeError": {
                "action": "fix_code",
                "details": error_msg
            }
        }

        for error_type, patch in patches.items():
            if error_type in error_msg:
                logger.info(f"🔧 生成补丁: {patch}")
                return patch

        return None

    def _extract_missing_package(self, error_msg: str) -> Optional[str]:
        """从错误消息中提取缺失的包名"""
        import re
        match = re.search(r"No module named '(\w+)'", error_msg)
        if match:
            return match.group(1)
        return None

    def _extract_missing_file(self, error_msg: str) -> Optional[str]:
        """从错误消息中提取缺失的文件名"""
        import re
        match = re.search(r"\[Errno 2\] No such file or directory: '([^']+)'", error_msg)
        if match:
            return match.group(1)
        return None

    def _apply_patch(self, patch: Dict) -> bool:
        """应用补丁"""
        action = patch.get("action")

        if action == "install":
            package = patch.get("package")
            if package:
                result = self._run_command(f"pip install {package}")
                return result.get("exit_code") == 0

        elif action == "create":
            # 创建缺失文件
            file_path = patch.get("file")
            if file_path:
                # 创建空文件或从模板创建
                result = self._run_command(f"touch {file_path}")
                return result.get("exit_code") == 0

        return False

    def _rollback(self):
        """回滚所有更改"""
        logger.info(f"⏪ 回滚更改")
        # 恢复备份
        if self.backup_dir.exists():
            shutil.rmtree(self.repo_path, ignore_errors=True)
            shutil.copytree(self.backup_dir, self.repo_path)


# 注册到 Hermes 工具系统
def register_docker_sandbox_tool():
    """注册 Docker 沙箱工具到 Hermes"""
    from backend.tools.tools_decorator import get_project_tools

    tools = get_project_tools()
    if docker_sandbox not in tools:
        docker_sandbox._toolset = "paper_repro"  # 论文复现工具集
        tools.append(docker_sandbox)
        logger.info("✅ 注册 docker_sandbox 工具")


# 自动注册
try:
    register_docker_sandbox_tool()
except Exception as e:
    logger.warning(f"自动注册工具失败: {e}")