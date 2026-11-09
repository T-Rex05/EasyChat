# EasyChat Docker 部署

单容器：应用 + SQLite + 进程内 worker；不依赖 MySQL/Redis/Neo4j/Milvus。

## 快速启动

```powershell
cd docker
Copy-Item .env.example .env
# 编辑 .env：至少设置 EASYCHAT_JWT_SECRET（>=32 位随机串）
docker compose up --build -d
```

打开 `http://127.0.0.1:8001/`；健康检查：

```powershell
docker compose ps
Invoke-RestMethod http://127.0.0.1:8001/healthz   # {"status":"ok"}
Invoke-RestMethod http://127.0.0.1:8001/readyz    # {"status":"ready"}
```

停止 / 查看日志：

```powershell
docker compose logs -f easychat
docker compose down
```

数据保存在命名卷 `easychat_data`（`/app/data`）；普通 `down` 不删卷，`down -v` 才会删除业务数据。

## 配置

`.env.example` 已列出端口、JWT、加密密钥和能力开关。默认全部能力关闭，适合只验证 Web 启动、SQLite 迁移和基础 API：

- `EASYCHAT_HERMES_ENABLED=false`：不启动真实 Hermes/LLM；
- `EASYCHAT_WECHAT_ENABLED=false`：不启动微信监听；
- `EASYCHAT_ENCRYPTION_SECRET`：启用微信或邮件时必须设置，否则对应能力保持关闭；
- 微信/模型/SMTP 凭证不要写进镜像或 `.env.example`，运行时录入或由部署环境提供。

## 已验证的启动路径

- 镜像内前端静态资源由 `agent_frontend` 构建阶段生成，挂载到 `/app/static`；
- 启动执行 SQLite 迁移至当前最新版本；
- `/healthz` 只表示进程存活，`/readyz` 才表示 lifespan 装配完成；
- 容器健康检查使用镜像内 `curl` 请求 `/healthz`；
- `python-multipart` 是文件上传路由的必需依赖，已列入 `requirements-core.txt`。

## 构建注意

默认构建从 PyPI/Docker Hub 拉取依赖；在受限网络中可能遇到 registry 超时或 wheel hash mismatch。此时先确认网络/镜像源可达，再执行 `docker compose build --pull`。本机冒烟时曾用可达 PyPI 镜像构建临时测试镜像；临时 Dockerfile 不进入仓库，不能替代默认 Dockerfile 在可靠网络下的复跑。
