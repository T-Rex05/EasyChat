# 论文复现环境配置指南

**配置时间**: 2026-10-01 23:35
**配置方式**: 环境变量手动配置

---

## 🎯 快速开始

### 1. 选择镜像

根据论文类型选择合适的镜像：

| 论文类型 | 推荐镜像 | 说明 |
|---------|---------|------|
| **通用 Python** | `python:3.10-slim` | 默认，轻量级 |
| **深度学习 (PyTorch)** | `pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime` | GPU 支持 |
| **深度学习 (TensorFlow)** | `tensorflow/tensorflow:2.13.0-gpu` | GPU 支持 |
| **天文学** | `astropy/astropy:latest` | 预装 AstroPy |
| **科学计算** | `jupyter/scipy-notebook:latest` | NumPy/SciPy/Pandas |
| **NLP** | `huggingface/transformers-pytorch-gpu:latest` | Transformers |

### 2. 配置环境变量

编辑项目根目录的 `.env` 文件：

```bash
# 论文复现默认镜像
SANDBOX_DEFAULT_IMAGE=python:3.10-slim
```

### 3. 预拉取镜像

```bash
# 方式 1：使用提供的脚本
python backend/tools/paper_reproduction/pull_images.py

# 方式 2：手动拉取
docker pull python:3.10-slim
docker pull pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime
```

### 4. 重启后端

```bash
E:\PythonCode\AgentForge\restart-all.bat
```

---

## 📋 预定义镜像列表

### 基础镜像

```bash
# Python 3.10 (默认)
SANDBOX_DEFAULT_IMAGE=python:3.10-slim

# Python 3.11
SANDBOX_DEFAULT_IMAGE=python:3.11-slim

# Python 3.9 (AGI-OpenResearch 默认)
SANDBOX_DEFAULT_IMAGE=python:3.9-bullseye
```

### 深度学习镜像

```bash
# PyTorch 2.0 + CUDA 11.7 (GPU)
SANDBOX_DEFAULT_IMAGE=pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

# PyTorch 2.0 CPU
SANDBOX_DEFAULT_IMAGE=pytorch/pytorch:2.0.1-cpu

# PyTorch 最新版 (GPU)
SANDBOX_DEFAULT_IMAGE=pytorch/pytorch:latest

# TensorFlow 2.13 GPU
SANDBOX_DEFAULT_IMAGE=tensorflow/tensorflow:2.13.0-gpu

# TensorFlow 2.13 CPU
SANDBOX_DEFAULT_IMAGE=tensorflow/tensorflow:2.13.0
```

### 科学计算镜像

```bash
# SciPy Notebook (NumPy, SciPy, Pandas, Matplotlib)
SANDBOX_DEFAULT_IMAGE=jupyter/scipy-notebook:latest

# AstroPy (天文学)
SANDBOX_DEFAULT_IMAGE=astropy/astropy:latest
```

### NLP 镜像

```bash
# HuggingFace Transformers + PyTorch GPU
SANDBOX_DEFAULT_IMAGE=huggingface/transformers-pytorch-gpu:latest

# HuggingFace Transformers + PyTorch CPU
SANDBOX_DEFAULT_IMAGE=huggingface/transformers-pytorch-cpu:latest
```

---

## 🔧 高级配置

### 自定义镜像

如果预定义镜像不满足需求，可以构建自定义镜像：

**1. 创建 Dockerfile**

```dockerfile
# backend/tools/paper_reproduction/custom.Dockerfile
FROM python:3.10-slim

# 安装常用依赖
RUN pip install --no-cache-dir \
    numpy \
    scipy \
    pandas \
    matplotlib \
    scikit-learn

# 安装领域专用库
RUN pip install --no-cache-dir \
    astropy \
    photutils
```

**2. 构建镜像**

```bash
cd backend/tools/paper_reproduction
docker build -f custom.Dockerfile -t my-paper-env:latest .
```

**3. 配置使用**

```bash
# .env
SANDBOX_DEFAULT_IMAGE=my-paper-env:latest
```

---

## 🚀 性能优化建议

### 预拉取镜像

首次使用时，建议提前拉取镜像：

```bash
# 基础镜像（必拉）
docker pull python:3.10-slim

# 根据需求拉取
docker pull pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime  # 如果有 GPU
docker pull astropy/astropy:latest  # 如果是天文学论文
```

### 镜像大小参考

| 镜像 | 大小 | 拉取时间（100Mbps） |
|------|------|-------------------|
| `python:3.10-slim` | ~150MB | ~15 秒 |
| `pytorch/pytorch:2.0.1-cuda11.7` | ~4GB | ~7 分钟 |
| `tensorflow/tensorflow:2.13.0-gpu` | ~2GB | ~3 分钟 |
| `astropy/astropy:latest` | ~500MB | ~45 秒 |
| `jupyter/scipy-notebook` | ~2GB | ~3 分钟 |

---

## 📝 常见问题

### Q: 如何检查镜像是否已拉取？

```bash
docker images | grep python
docker images | grep pytorch
```

### Q: 如何查看当前配置的镜像？

```bash
# 查看环境变量
echo $SANDBOX_DEFAULT_IMAGE

# 或在 Python 中
import os
print(os.getenv("SANDBOX_DEFAULT_IMAGE", "python:3.10-slim"))
```

### Q: 镜像拉取失败怎么办？

```bash
# 使用国内镜像加速
docker pull python:3.10-slim --registry-mirror=https://registry.docker-cn.com

# 或配置 Docker Desktop 镜像加速
# Settings -> Docker Engine -> 添加 registry-mirrors
```

### Q: 没有 GPU 怎么办？

使用 CPU 版本镜像：

```bash
# PyTorch CPU
SANDBOX_DEFAULT_IMAGE=pytorch/pytorch:2.0.1-cpu

# TensorFlow CPU
SANDBOX_DEFAULT_IMAGE=tensorflow/tensorflow:2.13.0
```

---

## 🔄 切换镜像

根据不同论文类型，切换镜像：

```bash
# 场景 1：处理机器学习论文
export SANDBOX_DEFAULT_IMAGE=pytorch/pytorch:latest
python main.py

# 场景 2：处理天文学论文
export SANDBOX_DEFAULT_IMAGE=astropy/astropy:latest
python main.py

# 场景 3：通用 Python 论文
export SANDBOX_DEFAULT_IMAGE=python:3.10-slim
python main.py
```

---

**配置人**: Claude Fable 5
**状态**: 配置完成，待使用