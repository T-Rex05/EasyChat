# EasyChat 运行与交付说明

最后更新：2026-11-06。适用于新架构入口 `backend.server:app`。

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

## 4. AI 前沿日报与联网搜索

- 定时任务页的“AI 前沿日报（最多 10 条）”走既有 `content_kind=briefing` / `briefing_kind=ai_news` 路径，可在页面创建每天 08:00 的计划并发到已绑定微信；无需新表/迁移。计划里显式选择邮箱时，worker 会按计划目标投递，不再强制回落到微信。
- 新闻源：OpenAI、Google DeepMind、TechCrunch AI、The Verge AI、MIT Technology Review AI、arXiv cs.AI。并发抓取 RSS/Atom，按发布时间和来源权重排序，每源最多 2 条，去重后取 10 条。
- 摘要：一次批量 LLM 调用生成中文一句话；模型不可用、超时或输出不合法时保留原始标题/摘要，不阻塞日报。
- 二维码：`docker/requirements-core.txt` 需包含 `qrcode[pil]`；前端在 `qr_image` 为空时展示 `qr_content` 链接，不再无限转圈。
- 联网搜索：`docker/requirements-hermes.txt` 包含 `ddgs` 与 `lxml`；启动时显式注册 Hermes 的 ddgs Provider（该内置插件缺 `plugin.yaml`）。DuckDuckGo 不可达时，Bing HTML 兜底返回结果。
- 审计：当前只有 `data/logs/audit.log` 日志基础设施（`audit_log()` 写入），没有审计查询 API/页面；侧边栏的 `/audit-log` 死链已移除，避免误以为有可用审计台。

## 5. 单 worker 与资源

- 必须 `--workers 1`：SQLite 写、投递 worker、提醒调度器、记忆/学习 worker 都在进程内；多副本会重复认领/重复调度。
- 目标：常态主进程 RSS < 1 GiB（初始容量：runtime cache 8、run 队列 32、事件缓存 256 帧/256KiB）。
- 资源测量：`python -m pytest tests/resources -m resources -q`（启动真实 uvicorn 子进程，psutil 采样）。
- PDF/脚本等重任务与前台互斥；Renderer 超时会 kill 子进程。

## 6. 备份与恢复

- 备份：停写后复制 `data/app.db`、`data/state.db`、`data/artifacts/`；SQLite WAL 版本守卫可能回退 DELETE，按实际 journal 文件一并复制。
- 恢复：先恢复文件，再启动；启动会执行迁移 checksum 校验、遗留 `running` run 标 interrupted、lease 过期任务退回。
- 不自动重跑有副作用工具；投递 `sending` 重启后转 uncertain，不假装必达。
- 删除/遗忘：记忆墓碑不保留原文；技能版本不可变，回滚用 active 指针切换。

## 7. 已验证 / 未验证

已验证（离线）：新架构全量测试（`1003 passed, 3 skipped`）、前端 type-check/build、显式路由装配、SQLite 迁移/恢复、投递账本/提醒/记忆/技能/进化/邮件 PDF 能力、假 Runner 契约。
容器冒烟（2026-11-05）：本机用临时镜像源构建并启动单容器，`/healthz`/`/readyz`、SPA 静态页、注册/登录、profile 读写、情绪删除、multipart 上传均 200；容器内迁移到 `0017`，`care_epoch_at` 存在；重启后卷数据仍可登录。首次启动暴露并修复了 `python-multipart` 缺失（已加入 `docker/requirements-core.txt`）。
AI 日报/搜索容器验证（2026-11-05）：新镜像内 `qrcode 8.2`、`ddgs 9.16.1`、`Pillow 13.0.0` 可导入；QR start 返回 `data:image/png;base64,...`（1038 字符）；实时抓取 6 个源、10 条资讯；`web_search_tool` 在 DuckDuckGo 超时后由 Bing 兜底返回结果。
用量/排行容器验证（2026-11-06）：旧 `llm_calls` 明细与 `daily_user_stats` 的 input/output 别名一致；rank 返回 `input_tokens=120/output_tokens=30/total_tokens=150/call_count=1`，daily 行按日聚合为同一组数字。
最终镜像冒烟（2026-11-06）：`llm_calls` 与 `daily_user_stats` 的新口径、QR PNG、AI 日报计划创建/删除、实时资讯 10 条均通过；Bing 兜底在同一镜像内返回 3 条。
未验证：真实 LLM 中文摘要（本机容器未配置模型，已验证假生成器与回退）；真实微信扫码确认与主动推送（需真实 iLink 环境）；真实 Linux Runner 隔离；默认 PyPI 直连下的完整 Docker build（本机遇到 wheel hash mismatch，需换可达镜像源/网络后复跑）。

## 8. 架构债清偿（2026-11-06 第二轮）

本轮把复核中可安全重构的架构债直接修掉，行为契约由测试锁定：

- 提醒送达计数归 delivery：删除 scheduling repository 对 `deliveries` 的跨模块 JOIN，新增 `DeliveryService.count_sent_reminders()`；scheduling 只问 delivery 要数字，care/简报不会被误算成提醒。
- 渠道目标改为 `ChannelTarget` 值对象；所有 `DeliveryTarget(**dict)` 调用点改为 `target_from_channel()` 单一适配点，渠道模块不再返回无约束 dict。
- 计划创建统一为 `ScheduleSpec`；repository 的 `create` / `find_recent_duplicate` 不再接收十几个散参数。
- 微信错误分类改用结构化 `ChannelTransportError(status/ret/retryable)`，不再按类名或中文文案猜测；投递先解析一次 sender 并复用，避免 `can_deliver` + `send_text` 双探测。
- bootstrap 改为构造期注入：assistant 的 profiles/memory/on_run_finished、mood worker 的 delivery/channels、delivery 的 sender/email 校验、channels 的 commands 均不再事后赋值；渠道 sender 使用零参 provider 解决“delivery 先于 ChannelService”的装配环。
- 记忆读取走 `assistant.transcript.load_run_messages()` 只读函数，不再把 assistant repository 传给 memory；命令层只接收 `CommandServices` 的窄协议与 `target_for_owner` 函数，不再持有 ChannelService。
- 提交语义错误改为 `LedgerControlMismatch` / `LedgerAlreadyCommitted`，不再匹配“控制总额/已提交”字符串。
- 清理了重复时间解析、daily/weekly 推进、`_chunk_chars_for` 嵌套、`find_recent_duplicate` 长参数和 memory 消息二次扫描。

验证：全量 `1003 passed, 3 skipped`；ruff 对上述改动文件通过。

容器复测（2026-11-06，重构镜像）：本机 Docker Hub 不可达，用缓存的 `python:3.12-slim-bookworm` / `node:24-bookworm-slim` 构建等价临时镜像（未改生产 Dockerfile）。容器 `healthy`/`ready`，SPA 返回 200；注册/登录、AI 日报计划创建/查询/删除均 200，迁移到 `0017`。管理员账号 QR start 返回 200，`qr_image` 为 990 字符的 `data:image/png;base64,...`；`NewsService` 实时抓取 10 条、5 个源、1 个源错误；Hermes `web_search_tool` 在 DDGS 超时后由 Bing 兜底返回 3 条；`UsageService` 写入后 ranking 返回 `input_tokens=120/output_tokens=30/total_tokens=150/call_count=1`，daily 为同一组数字。
