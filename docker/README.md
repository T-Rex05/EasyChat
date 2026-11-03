# AgentForge Docker 部署指南

## 快速启动

### 1. 首次启动

```powershell
cd docker

# 1. 复制配置文件
copy .env.example .env

# 2. 编辑 .env，填入 LLM API Key 等配置
notepad .env

# 3. 启动所有服务
.\start.ps1 start
```

### 2. 迁移现有数据（如果有本地 MySQL 数据）

```powershell
# 先确保 Docker MySQL 已启动
.\start.ps1 start

# 执行迁移
.\start.ps1 migrate
# 按提示输入本地 MySQL 密码
```

---

## 服务地址

| 服务 | 地址 | 用户名/密码 |
|------|------|------------|
| **MySQL** | localhost:3306 | root / agentforge123 |
| **Neo4j Web UI** | http://localhost:7474 | neo4j / agentforge123 |
| **Milvus gRPC** | localhost:19530 | - |

---

## 常用命令

```powershell
.\start.ps1 start     # 启动所有服务
.\start.ps1 stop      # 停止所有服务
.\start.ps1 restart   # 重启所有服务
.\start.ps1 status    # 查看服务状态
.\start.ps1 logs      # 查看所有日志
.\start.ps1 logs mysql    # 查看 MySQL 日志
.\start.ps1 logs neo4j    # 查看 Neo4j 日志
.\start.ps1 migrate   # 迁移 MySQL 数据
.\start.ps1 reset     # 重置所有数据（危险！）
```

---

## 配置说明

### .env 文件

```env
# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=agentforge123
MYSQL_DATABASE=agentforge

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=agentforge123

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530

# LLM
LLM_API_KEY=your_openai_api_key
LLM_MODEL=gpt-4o-mini

# Embedding
RAG_EMBEDDING_API_KEY=your_openai_api_key
RAG_EMBEDDING_MODEL=text-embedding-3-small
```

---

## 启动顺序

```
1. MySQL (健康检查通过)
   ↓
2. Neo4j (健康检查通过)
   ↓
3. Milvus (依赖 etcd + minio)
   ↓
4. AgentForge 应用
```

---

## 数据持久化

数据存储在 `docker/volumes/` 目录：

```
volumes/
├── mysql/data/      # MySQL 数据
├── neo4j/data/      # Neo4j 图数据
├── neo4j/logs/      # Neo4j 日志
├── etcd/            # Milvus 元数据
├── minio/           # Milvus 对象存储
└── milvus/          # Milvus 数据
```

---

## 故障排查

### MySQL 连接失败
```powershell
# 检查容器状态
docker ps | findstr mysql

# 查看日志
docker logs agentforge-mysql
```

### Neo4j 连接失败
```powershell
# 检查是否需要 APOC 插件
docker exec -it agentforge-neo4j cypher-shell -u neo4j -p agentforge123 "RETURN 1"
```

### Milvus 连接失败
```powershell
# 检查健康状态
curl http://localhost:9091/healthz

# 查看 etcd 状态
docker logs milvus-etcd
```

---

## 与 AgentForge 应用集成

启动 Docker 服务后，运行 AgentForge：

```powershell
cd ..  # 回到项目根目录

# 方式1: 直接运行（推荐开发时使用）
python main.py

# 方式2: 也用 Docker 运行
# 取消 docker-compose.yml 中 agentforge 服务的注释
docker-compose up -d agentforge
```

---

## 生产环境建议

1. **修改默认密码**
   - 修改 `.env` 中的所有密码
   - 特别是 `MYSQL_ROOT_PASSWORD` 和 `NEO4J_PASSWORD`

2. **配置持久化**
   - 数据已挂载到 `volumes/` 目录
   - 建议定期备份此目录

3. **资源限制**
   - 在 `docker-compose.yml` 中添加资源限制：
   ```yaml
   deploy:
     resources:
       limits:
         memory: 2G
   ```

4. **安全加固**
   - 不要暴露不必要的端口
   - 使用 Docker 网络隔离