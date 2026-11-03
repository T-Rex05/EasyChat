# EasyChat 实施进度交接（2026-11-03）

给接手实施的模型：**从这里开始**，然后按顺序读 `EASYCHAT_HANDOFF.md` → 架构规范 → 实施计划 → `docs/superpowers/plans/easychat-execution-log.md`（每个任务的完整证据记录）。

## 一、当前状态

| 项 | 值 |
|---|---|
| 分支 | `main`（未推送，origin=gitee，遵约束不自动 push） |
| 工作树 | 干净（`git status --short` 为空） |
| 提交数 | 13（基线起每任务一个提交 + 日志回填） |
| 已完成 | **Task 0–6**（里程碑一的全部任务除微信外，微信属 Task 7） |
| 下一任务 | **Task 7：微信与多端归一化、身份绑定和持久去重** |
| 未开始 | Task 7–16（Task 8–16 未动） |
| 测试 | `python -m pytest tests -m "not integration and not resources" -q` —— 新套件 152 passed；**旧 tests/ 下大量遗留测试仍引用已删依赖/MySQL，不能整体跑，Task 15 才清理** |

最近提交：`1105e38`(Task 6) `47dbcd6`(Task 5) `09fe0db`(Task 4) `ba8964e`(Task 3) `ee8f903`(Task 2) `6f418e5`(Task 1) `1d41c2a`(基线)

## 二、已完成模块（新架构，全部有测试）

```
backend/
  app.py / bootstrap.py           无副作用工厂；lifespan 显式启动
  shared/{context,errors,identifiers}.py
  platform/{sqlite,settings,jobs}.py + migrations/0001..0003
  modules/access/     RBAC、users/roles、Principal、token（35测试）
  modules/usage/      唯一计量入口 usage.begin_call/complete_call/report_usage（12测试）
  modules/models/     模型配置、AES-GCM密钥、选择链（9测试）
  modules/assistant/  统一run入口 + 事件总线 + 调度器 + Web兼容路由（21测试）
  runtime/contracts.py + runtime/hermes/{paths,tools,sessions,usage_bridge,adapter,agent_factory}.py
  integrations/mcp.py WeKnora等MCP窄适配（9测试）
```
旧代码（`backend/controller|service|db|hermes_adapter.py|rag|graphrag` 等）**原样保留**，旧 `main.py` 仍能启动旧系统——新旧并存是计划内状态，Task 15 才删除旧桥接。

## 三、必须知道的坑（都是实测踩出来的）

1. **SQLite WAL 版本守卫**：本机 SQLite 3.45.3 在 WAL-reset 损坏区间（3.45.0–3.51.2）。`platform/sqlite.py` 已按 Hermes 同规则回退 `journal_mode=DELETE`（修复版 3.51.3+/回移 3.50.7/3.44.6 才启用 WAL）。不要"修"成无条件 WAL。
2. **迁移不能用 `executescript`**：它会隐式 COMMIT 破坏原子性。已用 `sqlite3.complete_statement` 拆语句逐条执行。迁移文件带 checksum，**已提交的 0001/0002/0003 不可改**，改 schema 一律新增 `0004_*.sql`。
3. **Hermes 导入顺序**：Hermes 包内互用顶层模块名。必须先 `ensure_hermes_environment()`（插入 `backend/hermes` 到 sys.path + 设 `HERMES_HOME`）再 import；业务代码**只允许** `backend/runtime/hermes/*` 接触 Hermes 内部（架构测试强制）。
4. **禁止绕过 `run_conversation` 直接 `registry.dispatch`**：dispatch 无 toolset/权限闸门，隔离只存在于 conversation_loop 的 valid_tool_names 校验。
5. **取消 = `agent.interrupt()`** 协作式；禁止 asyncio task.cancel 强杀。取消后 run 落 `cancelled`，即使 runtime 随后发出 completed 也不得覆盖。
6. **Runtime 协议约定**：`execute()` 的事件流必须以 `completed|failed|cancelled|interrupted` 终态事件结束，否则 dispatcher 判 failed。写 FakeRuntime 脚本时别忘终态帧。
7. **命名坑**：`AssistantService.events` 是 EventBus 属性，公开订阅方法是 `iter_events()`（早期同名方法被属性遮蔽，已修）。
8. **测试事件循环**：路由测试用 `httpx.AsyncClient + ASGITransport` 在 pytest 单循环内跑。**不要用 fastapi TestClient**（portal 线程另起事件循环，与 rig 的调度器跨循环死锁）。
9. **测试设施**：`make_rig(tmp_path, seed_access=True)` → `rig.attach_assistant()` → `await rig.start_assistant()` → `await rig.drain_runs()`；`rig.seed_user(role, grants, revokes)` 走真实 access 写入；`rig.runtime` 是 FakeRuntime。绝不让测试写仓库根 `data/`（已有教训）。
10. **架构测试是双向名单**：`tests/architecture/test_imports.py` 的 legacy 豁免名单（20 个禁用依赖文件 + 23 个 Hermes 直引文件）会双向校验——新增违规要登记，修好的要从名单删除，否则测试失败。这是故意的。
11. **新旧 main.py**：Task 6 计划里的"切换 main.py 到新工厂"**已推迟到 Task 15**（旧 main.py 还承载 cron/skills/email 等 100+ 未迁移保留路由，现在切换会切断这些入口，违反 A10）。接手者不要提前切换。
12. **Windows 提交**：`git -c core.safecrlf=false commit`（避免 CRLF 噪声）；部分旧文件带 BOM，AST 读取用 `utf-8-sig`。
13. **权限口径**：保留 12 个旧权限键 + 新增 `evolution.view/manage`；已删 kb/graph/paper/community 键在服务层入口被拒。super_admin=运行时全注册集（revoke 对它无效）。部门：旧库无 departments 表，本版不增不减。
14. **计量纪律**：只有 `usage.begin_call/complete_call/report_usage` 可写 `llm_calls`+`daily_user_stats`。旧 `trace_observer`/`update_trace` 的 daily_user_stats 累加**不得**在新链路复用（Task 15 随旧模块删除）。

## 四、下一个任务（Task 7）的实施要点

按实施计划原文：`backend/modules/channels/{api,contracts,repository,routes}.py` + `channels/wechat/{listener,parser,account}.py`，测试 `tests/contracts/test_wechat.py`、`tests/assistant/test_channel_identity.py`。

- 表已就绪：`channel_accounts` / `channel_bindings`(UNIQUE(platform,account_id,external_user_id)) / `channel_events`(UNIQUE(platform,account_id,external_event_id))。
- 旧代码来源：`backend/controller/wechat/hermes.py`、`backend/wechat/`、`backend/controller/platform_config_controller.py`（扫码/长轮询/凭证）、`backend/controller/user_binding_controller.py`。
- 关键行为：绑定→owner 决定会话归属（不信昵称/openid）；微信与 Web 共用 `AssistantService.submit`（source='wechat'）；去重落 `channel_events`；无稳定消息 ID 时用近似指纹+短窗口，不能永久吞相同文本；解绑/禁用立即拒绝；两机器人账号同 message_id 不冲突；图片引用不无限进内存。
- `/chat/stream` 路由当前对 `wx_` 前缀 thread_id 显式拒绝——微信入口是独立 channels 路由，不走 Web SSE。

## 五、已知未验证项（不要声称已完成）

- 真实 LLM 对话、真实 WeKnora MCP、真实扫码/iLink 收发：均为 integration，未联调。
- 新工厂 OpenAPI 与 144 条保留路由的比对：Task 15 显式装配后做。
- `tool_finished` 事件尚未桥接（Hermes step 回调语义所限）。
- 脚本 Runner 真实隔离验收（Task 13）未做——在此之前脚本"自动执行"必须保持关闭。
- 前端完全未改动。
- `AgentForge` 源目录未动；未使用任何旧生产凭证；未推送。
