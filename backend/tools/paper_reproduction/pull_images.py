"""
论文复现系统镜像预拉取脚本

自动拉取常用 Docker 镜像，避免运行时等待
"""

import subprocess
import sys
import os
from typing import List, Tuple

# 设置控制台编码
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")

# 预定义镜像列表（按使用频率排序）
IMAGES = [
    # 基础镜像（必拉）
    ("python:3.10-slim", "基础 Python 环境", True),

    # 深度学习（常用）
    ("pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime", "PyTorch 2.0 + CUDA 11.7 (GPU)", False),
    ("pytorch/pytorch:2.0.1-cpu", "PyTorch 2.0 CPU", False),
    ("tensorflow/tensorflow:2.13.0-gpu", "TensorFlow 2.13 GPU", False),
    ("tensorflow/tensorflow:2.13.0", "TensorFlow 2.13 CPU", False),

    # 科学计算
    ("jupyter/scipy-notebook:latest", "SciPy Notebook (NumPy/Pandas/Matplotlib)", False),
    ("astropy/astropy:latest", "AstroPy 天文学", False),

    # NLP
    ("huggingface/transformers-pytorch-gpu:latest", "HuggingFace Transformers + PyTorch GPU", False),
]


def check_docker() -> bool:
    """检查 Docker 是否可用"""
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def pull_image(image: str) -> Tuple[bool, str]:
    """
    拉取镜像

    Args:
        image: 镜像名称

    Returns:
        Tuple[bool, str]: (是否成功, 错误信息)
    """
    try:
        print(f"[PULL] Pulling image: {image}")
        result = subprocess.run(
            ["docker", "pull", image],
            capture_output=True,
            # 使用二进制模式避免编码问题
            timeout=600  # 10 分钟超时
        )

        if result.returncode == 0:
            print(f"[OK] Success: {image}")
            return True, ""
        else:
            # 尝试解码错误信息
            try:
                error = result.stderr.decode('utf-8', errors='ignore').strip()
            except:
                error = "Unknown error"
            print(f"[FAIL] Failed: {image}\n   Error: {error}")
            return False, error

    except subprocess.TimeoutExpired:
        error = "Pull timeout (10 minutes)"
        print(f"[FAIL] Failed: {image}\n   Error: {error}")
        return False, error
    except Exception as e:
        error = str(e)
        print(f"[FAIL] Failed: {image}\n   Error: {error}")
        return False, error


def check_image_exists(image: str) -> bool:
    """检查镜像是否已存在"""
    try:
        result = subprocess.run(
            ["docker", "images", "-q", image],
            capture_output=True,
            text=True,
            timeout=10
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def main():
    """主函数"""
    print("=" * 70)
    print("Paper Reproduction System - Docker Image Pull Tool")
    print("=" * 70)
    print()

    # 检查 Docker
    if not check_docker():
        print("[ERROR] Docker not available, please start Docker Desktop")
        sys.exit(1)

    print("[OK] Docker is ready")
    print()

    # 统计
    total = 0
    success = 0
    skipped = 0
    failed = 0

    # 拉取镜像
    for image, desc, required in IMAGES:
        total += 1

        # 检查是否已存在
        if check_image_exists(image):
            print(f"[SKIP] Already exists: {image} - {desc}")
            skipped += 1
            continue

        # 拉取
        ok, error = pull_image(image)
        if ok:
            success += 1
        else:
            failed += 1
            if required:
                print(f"[WARN] Required image pull failed, basic functions may be affected")

        print()

    # 总结
    print("=" * 70)
    print("Pull Complete")
    print("=" * 70)
    print(f"Total: {total} images")
    print(f"  [OK] Success: {success}")
    print(f"  [SKIP] Skipped: {skipped}")
    print(f"  [FAIL] Failed: {failed}")
    print()

    if failed > 0:
        print("[WARN] Some images failed to pull. Suggestions:")
        print("  1. Check network connection")
        print("  2. Configure Docker mirror acceleration")
        print("  3. Manually pull failed images: docker pull <image>")
        sys.exit(1)
    else:
        print("[OK] All images are ready!")
        print()
        print("Next steps:")
        print("  1. Configure SANDBOX_DEFAULT_IMAGE in .env file")
        print("  2. Restart backend: restart-all.bat")


if __name__ == "__main__":
    main()