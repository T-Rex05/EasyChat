# 论文复现系统 Docker 沙箱与错误处理修复报告

**修复时间**: 2026-10-01 23:05
**严重程度**: 🟡 中等
**影响范围**: Docker 沙箱、证据图谱构建、错误处理

---

## 🔴 问题分析

### 问题 1：Docker 沙箱超时

```
Command '['docker', 'run', '-d', ...]' timed out after 30 seconds
```

**原因**：
1. `docker --version` 检查通过，但 Docker Desktop 未真正运行
2. 创建容器超时时间过短（30 秒）
3. 镜像 `python:3.10-slim` 可能需要拉取

### 问题 2：证据图谱构建失败

```
Cannot read properties of undefined (reading 'overall')
```

**原因**：
1. Docker 失败后，`execution_results` 包含错误
2. 证据图谱构建工具没有正确处理错误状态
3. 返回的 JSON 缺少 `confidence.overall` 字段

---

## ✅ 修复方案

### 修复 1：增强 Docker 可用性检查

**文件**: `docker_sandbox.py`

```python
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
```

**改进**：
- 不仅检查 `docker --version`，还检查 `docker ps`
- 确保 Docker Desktop 真正运行

### 修复 2：增加容器创建超时

**文件**: `docker_sandbox.py`

```python
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
```

**改进**：
- 超时从 30 秒增加到 120 秒
- 提供详细的错误信息和建议

### 修复 3：增强证据图谱错误处理

**文件**: `build_evidence_graph.py`

```python
# 检查执行结果是否包含错误
if execution_results.get("error"):
    error_msg = execution_results.get("error", "未知错误")
    logger.warning(f"⚠️ 执行结果包含错误: {error_msg}")
    # 即使执行失败，也构建一个空的证据图谱
    result = {
        "version": "evidence.graph/v1",
        "graph": { ... },
        "confidence": {
            "overall": 0.0,
            "verified": 0,
            "failed": 0,
            "inconclusive": 0,
            "total": 0
        },
        "summary": {
            "status": "failed",
            "message": f"代码执行失败: {error_msg}",
            "recommendation": "请检查代码是否正确，或查看 Docker 日志"
        },
        "execution_error": error_msg,
        "created_at": datetime.now().isoformat()
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
```

**改进**：
- 即使 Docker 失败，也返回标准格式的 JSON
- 确保 `confidence.overall` 字段存在
- 提供错误信息和建议

---

## 📊 修复对比

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| **Docker 检查** | 只检查命令是否存在 | 检查守护进程是否运行 |
| **容器创建超时** | 30 秒 | 120 秒 |
| **超时错误信息** | 简单超时提示 | 详细原因和建议 |
| **证据图谱错误处理** | 直接抛出异常 | 返回标准错误格式 |
| **confidence.overall** | 可能缺失 | 始终存在 |

---

## 🚀 使用建议

### 1. 确保 Docker Desktop 已启动

```bash
# Windows: 启动 Docker Desktop
# 等待 Docker Desktop 完全启动（托盘图标稳定）

# 验证 Docker 是否运行
docker ps
```

### 2. 预拉取镜像（可选，加速后续使用）

```bash
docker pull python:3.10-slim
```

### 3. 重新测试

```bash
# 重启后端
python main.py

# 或使用重启脚本
E:\PythonCode\AgentForge\restart-all.bat
```

---

## ✨ 技术亮点

```
✶ Insight ─────────────────────────────────────
1. **渐进式可用性检查**：从命令存在到守护进程运行，层层深入
2. **防御性错误处理**：即使上游失败，下游也能优雅降级
3. **用户友好错误**：提供详细原因和建议，而非简单错误码
4. **超时时间权衡**：120 秒足够拉取镜像，又不会让用户等太久
─────────────────────────────────────────────────
```

---

## 📝 相关代码

- [docker_sandbox.py:98](docker_sandbox.py#L98) - Docker 可用性检查
- [docker_sandbox.py:181](docker_sandbox.py#L181) - 容器创建超时
- [build_evidence_graph.py:50](build_evidence_graph.py#L50) - 错误处理增强

---

## 🔄 后续行动

- [x] 增强 Docker 可用性检查
- [x] 增加容器创建超时
- [x] 增强证据图谱错误处理
- [ ] 添加 Docker Desktop 自动启动检测（Windows）
- [ ] 考虑提供"跳过 Docker"选项（直接在宿主机执行）

---

**修复人**: Claude Fable 5
**验证状态**: 待用户测试