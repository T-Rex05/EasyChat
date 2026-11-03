# 论文复现环境智能检测设计

**设计时间**: 2026-10-01 23:15
**目标**: 自动识别论文所需环境，选择合适的 Docker 镜像

---

## 🔍 环境检测来源

### 1. 论文内容识别

**论文解析时提取**：

| 信息类型 | 提取方式 | 示例 |
|---------|---------|------|
| **编程语言** | 关键词匹配 | "我们使用 Python 3.8"、"基于 MATLAB" |
| **框架** | 实体识别 | PyTorch, TensorFlow, JAX, AstroPy |
| **库** | 方法部分提取 | NumPy, SciPy, Pandas, Scikit-learn |
| **硬件要求** | 实验部分识别 | GPU, CUDA, 内存需求 |
| **数据集** | 数据部分识别 | ImageNet, 自有数据 |

**Prompt 示例**：

```python
PROMPT_EXTRACT_ENV = """
从以下论文中提取环境要求：

1. 编程语言及版本
2. 主要框架（深度学习框架等）
3. 关键依赖库
4. 硬件要求（GPU/CUDA 版本）
5. 数据集需求

论文文本：
{text}

输出 JSON 格式：
{
  "language": "python",
  "language_version": "3.8",
  "frameworks": ["pytorch", "astropy"],
  "libraries": ["numpy", "scipy"],
  "hardware": {
    "gpu": true,
    "cuda_version": "11.3",
    "memory_gb": 16
  },
  "datasets": ["Chandra X-ray data"]
}
"""
```

---

### 2. GitHub 仓库识别

**检测文件**：

```
优先级：
1. Dockerfile           → 直接使用（最准确）
2. docker-compose.yml   → 解析服务配置
3. requirements.txt     → Python 依赖列表
4. environment.yml      → Conda 环境
5. setup.py             → 解析 install_requires
6. pyproject.toml       → 现代 Python 项目
```

**检测逻辑**：

```python
def detect_environment_from_repo(repo_url: str) -> Dict:
    """从 GitHub 仓库检测环境要求"""

    # 1. 检查是否有 Dockerfile
    if has_file(repo_url, "Dockerfile"):
        return {
            "type": "dockerfile",
            "build_context": ".",
            "image": None  # 从 Dockerfile 构建
        }

    # 2. 检查 requirements.txt
    requirements = fetch_file(repo_url, "requirements.txt")
    if requirements:
        deps = parse_requirements(requirements)
        return {
            "type": "requirements",
            "base_image": select_base_image(deps),
            "install": ["pip install -r requirements.txt"]
        }

    # 3. 检查 environment.yml (Conda)
    environment_yml = fetch_file(repo_url, "environment.yml")
    if environment_yml:
        return {
            "type": "conda",
            "environment_yml": environment_yml
        }

    # 4. 没找到配置文件
    return {
        "type": "unknown",
        "base_image": "python:3.10-slim"  # 默认
    }
```

---

### 3. 镜像选择策略

**预定义镜像库**：

```python
IMAGE_REGISTRY = {
    # 通用 Python
    "python": {
        "3.8": "python:3.8-slim",
        "3.9": "python:3.9-slim",
        "3.10": "python:3.10-slim",
        "3.11": "python:3.11-slim",
    },

    # 深度学习
    "pytorch": {
        "cpu": "pytorch/pytorch:latest",
        "cuda11.3": "pytorch/pytorch:1.12.1-cuda11.3-cudnn8-runtime",
        "cuda11.8": "pytorch/pytorch:2.0.1-cuda11.8-cudnn8-runtime",
    },
    "tensorflow": {
        "cpu": "tensorflow/tensorflow:latest",
        "gpu": "tensorflow/tensorflow:latest-gpu",
    },

    # 科学计算
    "scipy": "jupyter/scipy-notebook:latest",
    "astropy": "astropy/astropy:latest",  # 天文学

    # 其他语言
    "r": "rocker/r-ver:4.3.0",
    "julia": "julia:1.9",
    "matlab": "mathworks/matlab:r2023b",  # 需要许可证
}
```

**选择逻辑**：

```python
def select_image(env_requirements: Dict) -> str:
    """根据环境要求选择最佳镜像"""

    # 1. 如果有 GPU 要求
    if env_requirements.get("hardware", {}).get("gpu"):
        cuda_version = env_requirements["hardware"]["cuda_version"]

        # 优先选择框架专用镜像
        if "pytorch" in env_requirements.get("frameworks", []):
            return f"pytorch/pytorch:latest-cuda{cuda_version}"
        elif "tensorflow" in env_requirements.get("frameworks", []):
            return "tensorflow/tensorflow:latest-gpu"

    # 2. 如果有特定框架
    frameworks = env_requirements.get("frameworks", [])
    if "pytorch" in frameworks:
        return "pytorch/pytorch:latest"
    elif "tensorflow" in frameworks:
        return "tensorflow/tensorflow:latest"
    elif "astropy" in frameworks:
        return "astropy/astropy:latest"  # 天文学专用

    # 3. 纯 Python 环境
    python_version = env_requirements.get("language_version", "3.10")
    return f"python:{python_version}-slim"
```

---

## 📊 工具调用流程

```
论文解析 (parse_paper)
    ↓
    提取环境要求
    {
      "language": "python",
      "frameworks": ["astropy"],
      "hardware": {"gpu": false}
    }
    ↓
仓库发现 (discover_repo)
    ↓
    检查仓库配置文件
    - requirements.txt: ["astropy", "numpy", "scipy"]
    - 无 Dockerfile
    ↓
环境匹配 (新工具：detect_environment)
    ↓
    选择镜像：astropy/astropy:latest
    或：python:3.10-slim + pip install astropy
    ↓
Docker 沙箱 (docker_sandbox)
    ↓
    使用匹配的镜像创建容器
```

---

## 🛠️ 实现优先级

### P0（立即实现）

- [ ] 从 GitHub 仓库检测 `requirements.txt`
- [ ] 根据依赖选择基础镜像
- [ ] 支持用户手动指定镜像

### P1（重要）

- [ ] 论文解析时提取环境要求
- [ ] 预定义常用镜像库
- [ ] 自动安装依赖

### P2（增强）

- [ ] 检测 Dockerfile 并构建
- [ ] GPU/CUDA 版本匹配
- [ ] 数据集自动下载

---

## 💡 用户体验

**用户视角**：

```
1. 用户提交论文
   ↓
2. 系统自动识别：
   "检测到论文使用 Python + AstroPy，需要约 2GB 依赖"
   ↓
3. 用户确认：
   [ ] 使用推荐环境（AstroPy 镜像）
   [ ] 使用自定义镜像：[输入框]
   ↓
4. 开始复现
```

**当前状态**：

```
1. 用户提交论文
   ↓
2. 系统使用默认镜像（python:3.10-slim）
   ↓
3. 可能缺少依赖 → 运行失败
```

---

**设计人**: Claude Fable 5
**状态**: 设计阶段，待实现