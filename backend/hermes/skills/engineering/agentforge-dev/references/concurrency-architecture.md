# AgentForge 并发架构分析

## 关键组件与瓶颈

| 组件 | 文件 | 并发策略 | 瓶颈 |
|------|------|----------|------|
| uvicorn | `main.py:291` | 单 worker，`reload=False`，无 `--workers` | Python GIL |
| RunRegistry | `backend/service/run_registry.py:43` | `MAX_RUNS=200`, `RUN_TTL=300s` | 内存上限 |
| 同线程串行 | `run_registry.py:74-78` | 同一 `thread_id` 只允许一个活跃 run → `ThreadBusyError` | 同一会话不能并发 |
| 跨线程并发 | 同上 | 不同 `thread_id` 可以并发，无显式限制 | — |
| MySQL | `backend/db/mysql_impl.py:39` | `_get_conn()` 每次新建连接，无连接池 | MySQL 默认 max_connections=151 |
| LLM 调用 | `chat_controller.py` + `hermes_adapter.py` | 无信号量/节流，直调 | DeepSeek API QPS 限额 |
| 心跳保活 | `chat_controller.py:45-72` | SSE 8 秒间隔空 data 事件 | 保持代理/浏览器不掐断连接 |

## 并发用户估算

```
瓶颈链：DeepSeek API QPS → asyncio 调度 → 单 worker CPU/GIL → MySQL 连接数
保守估计：10~30 个活跃并发用户
IO 密集场景（等 LLM/网络）下单 worker 可支撑更多，但：
- DeepSeek 免费 tier QPS 极低（1~5），付费可提升
- MySQL 无连接池，每请求建连开销在高并发下致命
```

## 架构限制点

### 1. 同会话串行（刻意设计）
同一用户/会话不能同时问两个问题。`RunRegistry.get_or_create()` 检测到同名 `thread_id` 下有 `status=RUNNING` 的 run 时抛出 `ThreadBusyError`，防止对话上下文被并发请求搞乱。

### 2. 数据库无连接池
`MySQLMapper._get_conn()` 注释原文："每次新建，生产环境可换连接池"。建议升级为 `DBUtils.PooledDB` 或迁移到 `SQLAlchemy`。

### 3. 单 worker 与 RunRegistry
`RunRegistry` 是进程内存单例（`_REGISTRY = RunRegistry()`）。若改为 `uvicorn.run(app, workers=N)`，每个 worker 有独立注册表，断线续传和幂等去重将失效——需引入 Redis 等外部存储。

### 4. 无请求级节流
没有全局并发信号量、LLM API 速率限制器或请求队列。高负载时所有请求直接打到 DeepSeek，可能触发 HTTP 429。

## 提升并发的优先级

1. **MySQL 连接池** — 改 `_get_conn()` 用 `DBUtils.PooledDB`，立竿见影
2. **评估 LLM API tier** — 确认 DeepSeek 账户 QPS 上限，必要时加限流
3. **必要时加 workers** — 需配套 Redis 化 RunRegistry（或接受多 worker 时同 thread 并发不安全）
