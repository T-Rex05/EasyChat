# EasyChat 运行与交付说明

最后更新：2026-11-03。适用于新架构入口 `backend.server:app`。

## 1. 组成与数据权威

- `app.db`：业务权威（用户/角色、会话、run、渠道、投递、记忆、技能元数据、提醒、用量）。
- `state.db`：Hermes 引擎历史权威；仅在启用 Hermes 时由 Runtime Adapter 打开。
- `data/artifacts/`：附件、技能不可变版本、报告 PDF 等文件产物；DB 只存引用/哈希。
- 没有 MySQL/Redis/Neo4j/Milvus 依赖；两个 SQLite 文件不可跨库原子提交，恢复按“投影对账、不重跑有副作用工具”处理。

## 2. 构建与启动

```bash
# 前端（生成 dist）
cd agent_frontend
npm ci
npm run build

# 镜像（单 worker）
docker build -f docker/Dockerfile -t easychat:local .

# 运行
docker run --rm -p 8001:8001 \
  -e EASYCHAT_JWT_SECRET=<32+ 位随机串> \
  -e EASYCHAT_ENCRYPTION_SECRET=<32+ 位随机串> \
  -v easychat_data:/app/data \
  easychat:local
```

或 `cd docker && cp .env.example .env`（填写 JWT/加密密钥）后 `docker compose up --build -d`。

健康检查：`GET /healthz`；就绪：`GET /readyz`（lifespan 完成后 200）。

## 3. 能力开关

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `EASYCHAT_HERMES_ENABLED` | false | 构造真实 Hermes Runtime；需要模型配置与 Hermes 依赖 |
| `EASYCHAT_WECHAT_ENABLED` | false | 启用微信监听；需 `EASYCHAT_ENCRYPTION_SECRET` |
| `EASYCHAT_MCP_ENABLED` | false | WeKnora 等 MCP 能力 |
| `EASYCHAT_EMAIL_ENABLED` | false | SMTP 邮件（配置仍需 system.config） |
| `EASYCHAT_PDF_ENABLED` | false | PDF 渲染；需镜像内安装 weasyprint/字体 |
| `EASYCHAT_RUNNER_ENABLED` | false | 脚本 Runner；无隔离验收前必须保持 false |

JWT 密钥未设置时进程会生成一次性随机密钥（重启后旧 token 失效），生产必须显式设置。
SMTP 密码/微信 token 只以 AES-GCM 密文落库，但部署密钥轮换会使旧密文不可解，需重新录入。

## 4. 单 worker 与资源

- 必须 `--workers 1`：SQLite 写、投递 worker、提醒调度器、记忆/学习 worker 都在进程内；多副本会重复认领/重复调度。
- 目标：常态主进程 RSS < 1 GiB（初始容量：runtime cache 8、run 队列 32、事件缓存 256 帧/256KiB）。
- 资源测量：`python -m pytest tests/resources -m resources -q`（启动真实 uvicorn 子进程，psutil 采样）。
- PDF/脚本等重任务与前台互斥；Renderer 超时会 kill 子进程。

## 5. 备份与恢复

- 备份：停写后复制 `data/app.db`、`data/state.db`、`data/artifacts/`；SQLite WAL 版本守卫可能回退 DELETE，按实际 journal 文件一并复制。
- 恢复：先恢复文件，再启动；启动会执行迁移 checksum 校验、遗留 `running` run 标 interrupted、lease 过期任务退回。
- 不自动重跑有副作用工具；投递 `sending` 重启后转 uncertain，不假装必达。
- 删除/遗忘：记忆墓碑不保留原文；技能版本不可变，回滚用 active 指针切换。

## 6. 已验证 / 未验证

已验证（离线）：新架构全量测试、前端 type-check/build、显式路由装配、SQLite 迁移/恢复、投递账本/提醒/记忆/技能/进化/邮件 PDF 能力、假 Runner 契约。
未验证：真实 LLM/微信/MCP/SMTP/PDF 联调；真实 Linux Runner 隔离；Docker 镜像实际构建/运行（本机未跑完整 build）；144 条旧路由迁移/删除完成度。
