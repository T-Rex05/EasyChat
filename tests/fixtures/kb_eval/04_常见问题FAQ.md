# AgentForge 常见问题 FAQ

本文档收集用户最常问的问题及其解答。

## 如何修改系统默认端口

AgentForge 默认使用 8001 端口。修改方法：

1. 编辑项目根目录的 `.env` 文件
2. 设置 `PORT=新端口号`（如 `PORT=9000`）
3. 重启服务：`python main.py` 或 `docker compose restart`

如果修改端口后前端无法连接，需要同步修改前端的 API 地址配置（`agent_frontend/vite.config.js` 中的 proxy target）。

Docker 部署时还需要修改 `docker-compose.yml` 的端口映射：`- "新端口:8001"`。

## 如何切换 LLM 模型

系统支持多种 LLM 模型切换，操作步骤：

1. 进入管理后台 → 模型配置页面
2. 添加新模型配置（填写 model_name、provider、api_key）
3. 将新模型的 `is_active` 设为 1
4. 系统会自动使用新激活的模型

当前支持的 provider 包括：openai、anthropic、volcengine（火山引擎/豆包）。
每个用户可以在个人设置中配置自己的默认模型，优先级高于系统默认。

模型配置存储在 `model_configs` 表中，字段包括 model_name、provider、model_type（llm/embedding/vision）、api_key、is_active。

## 知识库上传失败怎么办

文档上传失败的常见原因和解决方法：

**文件大小超限**: 单文件最大 50MB。超过限制请拆分文件或转换为更紧凑的格式。

**格式不支持**: 目前支持 md、txt、pdf、docx 四种格式。其他格式（如 xlsx、pptx）需要先转换为支持的格式。

**Chunk 数量超限**: 单个文档切分后最多 10000 个 chunk。如果文档过大，考虑拆分为多个文档上传。

**存储空间不足**: 检查 MySQL 磁盘空间和 Chroma 向量库存储空间。

上传后文档状态可通过 `kb_documents` 表查看，`vectorized` 字段表示是否已完成向量化。

## 如何查看 Token 消耗统计

Token 消耗统计有三个查看入口：

**个人统计**: 侧边栏 → 📊 可观测性 → 概览 Tab，显示自己的每日 token 消耗趋势图、模型分布、来源分布。

**排行榜**: 侧边栏 → 📊 可观测性 → 排行榜 Tab，显示所有用户的 token 消耗排名（需要 trace.ranking 权限）。

**API 查询**: `GET /api/traces/dashboard` 返回聚合统计数据，`GET /api/traces/ranking` 返回排行榜。

底层数据存储在 `daily_user_stats` 表（按日聚合）和 `traces` 表（每次调用明细）。

## 如何配置定时任务

定时任务通过管理后台配置，支持标准 5 段 cron 表达式。

配置步骤：
1. 进入管理后台 → 定时任务页面
2. 点击"新建任务"
3. 填写任务名称、cron 表达式、任务类型（report/cleanup/sync）
4. 保存后任务自动激活

常用 cron 表达式示例：
- `0 23 * * *`：每天 23:00 执行
- `0 */6 * * *`：每 6 小时执行
- `0 9 * * 1-5`：工作日 9:00 执行
- `0 0 1 * *`：每月 1 日 0:00 执行

任务执行记录在 `scheduled_task_runs` 表，可查看每次执行的状态、耗时和错误信息。
注意：时区为 Asia/Shanghai（UTC+8）。

## 如何实现多用户隔离

AgentForge 通过 contextvars 实现多用户记忆隔离。

**记忆隔离**: 每个用户的 Hermes MEMORY.md 和 USER.md 存储在独立目录（`{data_dir}/users/{user_id}/`），互不干扰。

**会话隔离**: 会话历史通过 `(user_id, thread_id)` 二元组定位，用户只能访问自己的会话。

**知识库隔离**: 知识库通过 `user_id` 字段隔离，检索时只搜索当前用户有权限的知识库。

**工具权限隔离**: 通过 `roles.hermes_tools` JSON 字段控制不同角色可见的工具组（terminal/file/web/memory 等 9 组）。

如果需要在同一角色内进一步隔离（如不同部门），可以通过自定义 Hook 在 `pre_process` 阶段添加额外的权限检查。

## 向量检索和 BM25 检索有什么区别

系统支持两种检索模式，可单独使用或混合使用：

**BM25 检索**: 基于关键词匹配的 tradisional 检索方法。
- 优点：零外部依赖、速度快（< 50ms）、对精确术语匹配效果好
- 缺点：无法理解语义同义词（如"用户"和"账号"）
- 适用场景：专业术语查询、表名/字段名精确匹配

**向量检索**: 基于 embedding 模型的语义检索。
- 优点：理解语义相似性、对同义词和近义表达鲁棒
- 缺点：需要 embedding API 调用、大语料下较慢
- 适用场景：自然语言问题、模糊查询

**混合检索**: 使用 RRF（Reciprocal Rank Fusion）融合两路结果，兼顾精确匹配和语义理解。配置方式：检索时设置 `retriever_mode="hybrid"`。

系统默认使用 `auto` 模式：如果用户已有向量化数据则用向量检索，否则降级为 BM25。
