# 论文复现环境选择机制设计（借鉴 AGI-OpenResearch）

**设计时间**: 2026-10-01 23:30
**参考项目**: AGI-OpenResearch

---

## 📊 AGI-OpenResearch 的实现

### 当前方案

```go
const defaultSandboxImage = "python:3.9-bullseye"

func configuredSandboxImage() string {
    // 环境变量覆盖
    if image := os.Getenv("SANDBOX_DEFAULT_IMAGE"); image != "" {
        return image
    }
    return defaultSandboxImage
}
```

### 关键发现

1. **硬编码默认镜像**：`python:3.9-bullseye`
2. **环境变量覆盖**：`SANDBOX_DEFAULT_IMAGE`
3. **预构建专用镜像**：`scholar-python-pytorch-smoke:2.0.1-cpu`
4. **检测依赖文件**：`requirements.txt`, `environment.yml` 等
5. **不会自动选择镜像**：依赖管理员配置

### 优化效果

> 首次运行因默认安装大型 PyTorch wheel 而超过测试总超时。
> 使用预装 torch 2.0.1+cpu 的 smoke 镜像后，完整 DAG 在 73.37 秒内通过。

**关键**：预装依赖可以大幅缩短执行时间！

---

## ✅ 我们可以借鉴的点

### 1. 环境变量配置

```python
# backend/tools/paper_reproduction/docker_sandbox.py
import os

def get_default_image() -> str:
    """获取默认 Docker 镜像（支持环境变量覆盖）"""
    # 环境变量优先
    if image := os.getenv("SANDBOX_DEFAULT_IMAGE"):
        return image

    # 默认镜像
    return "python:3.10-slim"
```

**使用方式**：

```bash
# .env 文件
SANDBOX_DEFAULT_IMAGE=pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

# 或命令行
export SANDBOX_DEFAULT_IMAGE=pytorch/pytorch:latest
```

### 2. 预构建专用镜像

**推荐镜像库**：

```python
IMAGE_PRESETS = {
    # 通用 Python
    "python-default": "python:3.10-slim",

    # 深度学习（预装框架）
    "pytorch-cpu": "pytorch/pytorch:2.0.1-cpu",
    "pytorch-gpu": "pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime",
    "tensorflow-cpu": "tensorflow/tensorflow:2.13.0-cpu",
    "tensorflow-gpu": "tensorflow/tensorflow:2.13.0-gpu",

    # 科学计算
    "scipy": "jupyter/scipy-notebook:latest",
    "astropy": "astropy/astropy:latest",  # 天文学

    # NLP
    "transformers": "huggingface/transformers-pytorch-gpu:latest",
}
```

### 3. 智能检测（增强）

**AGI-OpenResearch 没有的功能**：

```python
def detect_image_from_repo(repo_url: str) -> str:
    """从仓库检测合适的镜像"""

    # 1. 检查 Dockerfile
    if has_file(repo_url, "Dockerfile"):
        return build_from_dockerfile(repo_url)

    # 2. 检查 requirements.txt
    requirements = fetch_file(repo_url, "requirements.txt")
    if requirements:
        deps = parse_requirements(requirements)

        # 检测框架
        if "torch" in deps or "pytorch" in deps:
            return "pytorch/pytorch:latest"
        elif "tensorflow" in deps:
            return "tensorflow/tensorflow:latest"
        elif "astropy" in deps:
            return "astropy/astropy:latest"

    # 3. 默认镜像
    return get_default_image()
```

---

## 🚀 实现优先级

### P0（立即实现）

- [x] 环境变量 `SANDBOX_DEFAULT_IMAGE` 支持
- [ ] 文档说明如何配置镜像
- [ ] 预拉取常用镜像列表

### P1（重要）

- [ ] 从 `requirements.txt` 检测框架
- [ ] 自动选择预定义镜像
- [ ] 用户手动指定镜像参数

### P2（增强）

- [ ] 从 Dockerfile 构建镜像
- [ ] 从论文内容识别环境
- [ ] GPU/CUDA 版本匹配

---

## 📝 推荐配置

### 场景 1：机器学习论文（PyTorch）

```bash
# .env
SANDBOX_DEFAULT_IMAGE=pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime
```

### 场景 2：天文学论文（AstroPy）

```bash
# .env
SANDBOX_DEFAULT_IMAGE=astropy/astropy:latest
```

### 场景 3：通用 Python

```bash
# .env
SANDBOX_DEFAULT_IMAGE=python:3.10-slim
```

---

## 💡 最佳实践

1. **预拉取镜像**：提前拉取需要的镜像，避免运行时等待
   ```bash
   docker pull pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime
   ```

2. **环境变量配置**：不同环境使用不同配置文件
   ```bash
   # 开发环境
   cp .env.example .env.dev

   # 生产环境
   cp .env.example .env.prod
   ```

3. **镜像预构建**：如果常用依赖较多，构建自己的镜像
   ```dockerfile
   FROM python:3.10-slim
   RUN pip install numpy scipy pandas matplotlib
   ```

---

## 🔍 对比总结

| 特性 | AGI-OpenResearch | AgentForge（当前） | AgentForge（改进后） |
|------|------------------|-------------------|---------------------|
| 默认镜像 | `python:3.9-bullseye` | `python:3.10-slim` | `python:3.10-slim` |
| 环境变量 | ✅ `SANDBOX_DEFAULT_IMAGE` | ❌ 不支持 | ✅ 支持 |
| 预构建镜像 | ✅ 专用 smoke 镜像 | ❌ 无 | ✅ 预定义库 |
| 自动检测 | ❌ 不支持 | ❌ 不支持 | ✅ 从 requirements.txt |
| 用户指定 | ✅ API 参数 | ✅ API 参数 | ✅ API 参数 |

---

**设计人**: Claude Fable 5
**状态**: 设计完成，待实现