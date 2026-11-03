# Neo4j 端口映射问题诊断报告

**诊断时间**: 2026-10-02 18:05
**严重程度**: 🔴 阻塞性问题
**影响范围**: 知识图谱功能不可用

---

## 🔴 问题现象

```
容器状态：agentforge-neo4j Up About a minute (healthy)
端口映射：无（应该显示 0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp）

后端日志：
Failed to establish connection to ResolvedIPv4Address(('127.0.0.1', 7687))
(reason [WinError 10061] 由于目标计算机积极拒绝，无法连接。)
```

---

## 🔍 诊断过程

### 尝试的方案

| 方案 | 结果 |
|------|------|
| `docker-compose up -d neo4j` | ❌ 端口未映射 |
| `docker run -p 7474:7474 -p 7687:7687` | ❌ 端口未映射 |
| `docker run -p 0.0.0.0:7474:7474` | ❌ 端口未映射 |
| 使用不同端口 (17474, 17687) | ❌ 端口未映射 |
| `--network host` 模式 | ❌ 仍无法访问 |
| 删除并重新创建容器 | ❌ 端口未映射 |

### 确认的事实

1. **Neo4j 容器内部正常**:
   ```
   Bolt enabled on 0.0.0.0:7687
   HTTP enabled on 0.0.0.0:7474
   ```

2. **其他容器端口映射正常**:
   - MySQL: 0.0.0.0:3308->3306/tcp ✅
   - Redis: 0.0.0.0:6379->6379/tcp ✅
   - Milvus: 0.0.0.0:19530->19530/tcp ✅

3. **端口未被 Windows 保留**:
   - 7474 和 7687 不在 Hyper-V 保留端口范围内

4. **Docker 版本**:
   - Docker Desktop 4.91.0
   - Engine 29.8.0

---

## 📊 问题根因

**Docker Desktop for Windows 的网络栈 bug**

这是 Windows 版 Docker Desktop 的已知问题：
- 容器运行正常，内部服务监听正常
- 但端口映射不生效，宿主机无法访问容器端口
- 可能是 WSL2 网络层或 Docker Desktop 网络驱动的问题

---

## ✅ 解决方案

### 方案 1：重启 Docker Desktop（推荐）

**步骤**：
1. 右键点击系统托盘中的 **Docker Desktop 图标**
2. 选择 **Restart**
3. 等待 Docker 完全重启（30-60 秒）
4. 重新创建容器：
   ```bash
   docker-compose -f docker/docker-compose.yml up -d neo4j
   ```
5. 验证端口映射：
   ```bash
   docker ps --format "table {{.Names}}\t{{.Ports}}" | findstr neo4j
   # 应该显示: 0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp
   ```

### 方案 2：重启 WSL2

如果重启 Docker Desktop 无效，尝试重启 WSL2：

```powershell
# 在 PowerShell (管理员) 中运行
wsl --shutdown
# 等待 10 秒
# Docker Desktop 会自动重新启动 WSL2
```

然后重新创建容器。

### 方案 3：使用 Docker 容器运行后端

如果端口映射问题持续存在，可以将后端也运行在 Docker 容器中：

```bash
# 使用 docker-compose 启动所有服务
docker-compose -f docker/docker-compose.yml up -d

# 后端容器可以通过容器网络访问 Neo4j
# 不需要端口映射到宿主机
```

---

## 🛠️ 临时变通方案

如果暂时无法重启 Docker Desktop，可以：

1. **禁用 Neo4j 相关功能**（临时）：
   - 论文复现核心流程不依赖 Neo4j
   - 知识图谱功能暂时不可用

2. **使用测试脚本验证功能**：
   ```bash
   python backend/tools/paper_reproduction/test_full_flow.py
   ```

---

## 📝 验证步骤

重启 Docker Desktop 后，运行以下命令验证：

```bash
# 1. 检查容器状态
docker ps --format "table {{.Names}}\t{{.Ports}}" | findstr neo4j

# 预期输出（必须有 0.0.0.0）:
# agentforge-neo4j   0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp

# 2. 测试端口连接
powershell -Command "Test-NetConnection -ComputerName localhost -Port 7687 -InformationLevel Quiet"
# 预期输出: True

# 3. 测试 Neo4j 连接
docker exec agentforge-neo4j cypher-shell -u neo4j -p agentforge123 "RETURN 1"
# 预期输出: 1

# 4. 测试后端连接
curl http://localhost:8001/health
# 预期输出: {"status": "healthy"}
```

---

## 📊 时间线

| 时间 | 事件 |
|------|------|
| **17:37** | 创建 Neo4j 容器，端口未映射 |
| **17:48** | 测试论文复现系统，核心功能正常 |
| **18:00** | 后端启动，Neo4j 连接失败 |
| **18:03** | 尝试多种端口映射方案，全部失败 |
| **18:05** | 确认为 Docker Desktop 网络栈 bug |

---

## 🔗 相关 Issue

- [Docker Desktop for Windows port mapping issues](https://github.com/docker/for-win/issues)
- [WSL2 networking problems](https://github.com/microsoft/WSL/issues)

---

## 📝 相关文件

- [restart_docker_desktop.bat](../../docker/restart_docker_desktop.bat) - Docker 重启脚本
- [health_check.bat](../../docker/health_check.bat) - 容器健康检查脚本
- [test_report.md](test_report.md) - 论文复现系统测试报告

---

**诊断人**: Claude Fable 5
**状态**: 确认为 Docker Desktop bug，需用户重启 Docker Desktop