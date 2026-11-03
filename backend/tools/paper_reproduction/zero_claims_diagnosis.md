# 论文复现系统"主张提取返回 0"问题诊断报告

**诊断时间**: 2026-10-02 01:50
**严重程度**: 🔴 高危
**影响范围**: 主张提取、证据图谱构建

---

## 🔴 问题现象

```
前端显示:
  主张提取完成: 0 个主张
  整体置信度: 0%
  已验证: 0 / 0
```

---

## 🔍 问题诊断过程

### 第 1 步：直接测试工具

```bash
python backend/tools/paper_reproduction/test_full_flow.py
```

**结果**：
```
✅ 论文解析: 成功 (2 个原始主张)
✅ 主张提取: 成功 (5 个结构化主张)
✅ 仓库发现: 成功 (6 个仓库)
```

**结论**：工具本身正常。

---

### 第 2 步：通过 API 测试

```bash
curl -X POST http://localhost:8001/api/tools/extract_claim_rubric \
  -H "Content-Type: application/json" \
  -d '{"parsed_paper": {...}, "max_claims": 5}'
```

**结果**：
```json
{
  "error": "LLM 不可用",
  "version": "claim.rubric/v1"
}
```

**结论**：LLM 初始化失败。

---

### 第 3 步：检查 LLM 配置

```bash
# 检查环境变量
python -c "import os; print(os.getenv('LLM_API_KEY'))"
# 输出: None

# 检查模型路由
python -c "from backend.service.model_router import ModelRouter; ..."
```

**结果**：
```
Redis: Connection closed by server
MySQL: Lost connection to MySQL server during query
```

**结论**：MySQL 和 Redis 连接失败。

---

## 📊 问题根因分析

### 因果链

```
MySQL/Redis 连接失败
    ↓
无法从数据库获取模型配置
    ↓
LLM 初始化失败 (返回 "LLM 不可用")
    ↓
主张提取返回空结果
    ↓
前端显示 0 个主张
```

### 为什么之前测试成功？

| 时间 | MySQL/Redis | 结果 |
|------|------------|------|
| **第一次测试** | ✅ 在线 | ✅ 成功 (5 个主张) |
| **后续测试** | ❌ 离线 | ❌ 失败 (0 个主张) |

**可能原因**：
1. Docker 容器重启
2. 连接池耗尽
3. 网络波动
4. 长时间运行导致连接断开

---

## ✅ 解决方案

### 方案 1：使用一键重启脚本

```bash
E:\PythonCode\AgentForge\restart-full.bat
```

### 方案 2：手动重启

```bash
# 1. 重启 Docker 容器
docker restart agentforge-mysql
docker restart agentforge-redis

# 2. 等待容器就绪（10 秒）
timeout 10

# 3. 重启后端
python main.py

# 4. 重启前端
cd agent_frontend
npm run dev
```

### 方案 3：检查并修复

```bash
# 检查容器状态
docker ps | grep agentforge

# 如果容器挂了
docker start agentforge-mysql
docker start agentforge-redis

# 检查端口
netstat -an | findstr "3308"
netstat -an | findstr "6379"
```

---

## 🚀 验证步骤

### 1. 检查服务健康

```bash
curl http://localhost:8001/health
```

### 2. 运行完整测试

```bash
python backend/tools/paper_reproduction/test_full_flow.py
```

**预期输出**：
```
✅ 论文解析: OK
✅ 主张提取: OK (5 claims)
✅ 仓库发现: OK
✅ 证据图谱: OK
```

### 3. 前端测试

访问 http://localhost:3000，使用 arXiv URL 测试：
```
https://arxiv.org/abs/2009.00031
```

**预期结果**：
```
主张提取完成: 5 个主张
```

---

## 🛡️ 预防措施

### 1. 健康检查脚本

创建定时健康检查：

```python
# health_check.py
import requests
import sys

try:
    response = requests.get('http://localhost:8001/health', timeout=5)
    if response.status_code != 200:
        print("Backend unhealthy, restarting...")
        sys.exit(1)
except:
    print("Backend unreachable, restarting...")
    sys.exit(1)
```

### 2. 自动重启

使用 PM2 或 Supervisor 管理进程，自动重启。

### 3. 连接池优化

在 `backend/db/connection_pool.py` 中增加：

```python
# 健康检查间隔
connection_timeout = 60
ping_interval = 30
```

---

## 📊 时间线

| 时间 | 事件 |
|------|------|
| **00:44** | 用户测试，显示 0 个主张 |
| **01:10** | 我修复前端错误处理 |
| **01:30** | 第一次测试成功（5 个主张） |
| **01:47** | MySQL/Redis 连接失败 |
| **01:50** | 诊断出根本原因 |

---

## ✨ 技术要点

```
✶ Insight ─────────────────────────────────────
1. **多层级诊断**：从前端 → API → 工具 → LLM → 数据库，逐层排查
2. **依赖链断裂**：一个基础设施故障（MySQL）会导致整个流程失败
3. **状态不一致**：工具代码正常，但运行环境异常
4. **健康检查重要性**：定期检查数据库连接状态，及时发现问题
─────────────────────────────────────────────────
```

---

## 📝 相关文件

- [restart-full.bat](restart-full.bat) - 完整重启脚本
- [test_full_flow.py](test_full_flow.py) - 完整测试脚本
- [connection_pool.py](../../db/connection_pool.py) - 连接池配置

---

**诊断人**: Claude Fable 5
**状态**: 根因已找到，待用户重启服务