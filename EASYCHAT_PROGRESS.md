# EasyChat 实施进度交接（2026-11-03）

给接手实施的模型：**从这里开始**，然后按顺序读 `EASYCHAT_HANDOFF.md` → 架构规范 → 实施计划 → `docs/superpowers/plans/easychat-execution-log.md`（每个任务的完整证据记录）。

## 一、当前状态

| 项 | 值 |
|---|---|
| 分支 | `main`（未推送，origin=gitee，遵约束不自动 push） |
| 工作树 | 干净（本文档提交后 `git status --short` 为空） |
| 提交数 | 17（基线起每任务一个提交 + 加固/日志提交 + 本进度文档更新） |
| 已完成 | **Task 0–7**（里程碑一全部完成，含微信渠道离线链路） |
| 下一任务 | **Task 8：投递账本、文本提醒与持久调度** |
| 未开始 | Task 8–16 |
| 测试 | `python -m pytest tests/architecture tests/contracts tests/access tests/assistant tests/models tests/storage tests/usage -q` —— **185 passed**；**旧 tests/ 下大量遗留测试仍引用已删依赖/MySQL，不能整体跑，Task 15 才清理** |

最近提交：`08a4bd7`(Task 7 安全加固) `5cce711`(Task 7 加固) `72aa14c`(Task 7) `1105e38`(Task 6) `47dbcd6`(Task 5) `09fe0db`(Task 4) `ba8964e`(Task 3) `ee8f903`(Task 2) `6f418e5`(Task 1) `1d41c2a`(基线)

## 二、已完成模块（新架构，全部有测试）

```
backend/
  app.py / bootstrap.py           无副作用工厂；lifespan 显式启动
  shared/{context,errors,identifiers,crypto}.py
  platform/{sqlite,settings,jobs}.py + migrations/0001..0004
  modules/access/     RBAC、users/roles、Principal、token（35测试）
  modules/usage/      唯一计量入口 usage.begin_call/complete_call/report_usage（12测试）
  modules/models/     模型配置、AES-GCM密钥、选择链（9测试）
  modules/assistant/  统一run入口 + 事件总线 + 调度器 + Web兼容路由（21+测试）
  modules/channels/   账号/绑定/事件去重 + wechat/{parser,account,listener,media}（33测试）
  runtime/contracts.py + runtime/hermes/{paths,tools,sessions,usage_bridge,adapter,agent_factory}.py
  integrations/mcp.py WeKnora等MCP窄适配（9测试）
```
旧代码（`backend/controller|service|db|hermes_adapter.py|rag|graphrag` 等）**原样保留**，旧 `main.py` 仍能启动旧系统——新旧并存是计划内状态，Task 15 才删除旧桥接。

## 三、必须知道的坑（都是实测踩出来的）

1. **SQLite WAL 版本守卫**：本机 SQLite 3.45.3 在 WAL-reset 损坏区间（3.45.0–3.51.2）。`platform/sqlite.py` 已按 Hermes 同规则回退 `journal_mode=DELETE`（修复版 3.51.3+/回移 3.50.7/3.44.6 才启用 WAL）。不要"修"成无条件 WAL。
2. **迁移不能用 `executescript`**：它会隐式 COMMIT 破坏原子性。已用 `sqlite3.complete_statement` 拆语句逐条执行。迁移文件带 checksum，**已提交的 0001–0004 不可改**，改 schema 一律新增 `0005_*.sql`。
3. **Hermes 导入顺序**：Hermes 包内互用顶层模块名。必须先 `ensure_hermes_environment()`（插入 `backend/hermes` 到 sys.path + 设 `HERMES_HOME`）再 import；业务代码**只允许** `backend/runtime/hermes/*` 接触 Hermes 内部（架构测试强制）。测试机 PYTHONPATH 里有另一个 `tools` 命名空间包（`E:\JavaCode\...`），无条件 `import tools.*` 会把它缓存进 `sys.modules`，之后 state.db 恢复报 `No module named 'tools.registry'`；`adapter.cancel` 已按此修复，别改回去。
4. **禁止绕过 `run_conversation` 直接 `registry.dispatch`**：dispatch 无 toolset/权限闸门，隔离只存在于 conversation_loop 的 valid_tool_names 校验。
5. **取消 = `agent.interrupt()`** 协作式；禁止 asyncio task.cancel 强杀。取消后 run 落 `cancelled`，即使 runtime 随后发出 completed 也不得覆盖。
6. **Runtime 协议约定**：`execute()` 的事件流必须以 `completed|failed|cancelled|interrupted` 终态事件结束，否则 dispatcher 判 failed。写 FakeRuntime 脚本时别忘终态帧。
7. **命名坑**：`AssistantService.events` 是 EventBus 属性，公开订阅方法是 `iter_events()`（早期同名方法被属性遮蔽，已修）。
8. **测试事件循环**：路由测试用 `httpx.AsyncClient + ASGITransport` 在 pytest 单循环内跑。**不要用 fastapi TestClient**（portal 线程另起事件循环，与 rig 的调度器跨循环死锁）。
9. **测试设施**：`make_rig(tmp_path, seed_access=True)` → `rig.attach_assistant()` → `await rig.start_assistant()` → `await rig.drain_runs()`；`rig.seed_user(role, grants, revokes)` 走真实 access 写入；`rig.runtime` 是 FakeRuntime。渠道用 `tests/support/wechat.py` 的 `make_channel_rig`（FakeTransport/FakeMediaFetcher）。绝不让测试写仓库根 `data/`（已有教训）。
10. **架构测试是双向名单**：`tests/architecture/test_imports.py` 的 legacy 豁免名单（20 个禁用依赖文件 + 23 个 Hermes 直引文件）会双向校验——新增违规要登记，修好的要从名单删除，否则测试失败。这是故意的。
11. **新旧 main.py**：Task 6 计划里的"切换 main.py 到新工厂"**已推迟到 Task 15**（旧 main.py 还承载 cron/skills/email 等 100+ 未迁移保留路由，现在切换会切断这些入口，违反 A10）。Task 7 的 channels 路由构造器也未挂载，Task 15 一起显式装配。
12. **Windows 提交**：`git -c core.safecrlf=false commit`（避免 CRLF 噪声）；部分旧文件带 BOM，AST 读取用 `utf-8-sig`。
13. **权限口径**：保留 12 个旧权限键 + 新增 `evolution.view/manage`；已删 kb/graph/paper/community 键在服务层入口被拒。super_admin=运行时全注册集（revoke 对它无效）。部门：旧库无 departments 表，本版不增不减。
14. **计量纪律**：只有 `usage.begin_call/complete_call/report_usage` 可写 `llm_calls`+`daily_user_stats`。旧 `trace_observer`/`update_trace` 的 daily_user_stats 累加**不得**在新链路复用（Task 15 随旧模块删除）。
15. **渠道去重必须落 `channel_events` 唯一键**，不能用进程内 dict；稳定 `message_id` → `msg:<id>`，没有时用 `fp:<sha256>:<int(now/5s)>` 窗口桶——窗口内去重、窗口过后相同文本可再次处理，不能永久吞。
16. **渠道身份只查 `channel_bindings`**（platform+account_id+external_user_id）；昵称/单一 openid 不决定 owner。会话 `external_chat_id` 必须带 bot account 前缀（`<account_id>:<chat_id>`），两个机器人账号下同一 openid 不得共享会话；`channel_session_cursors` 保存 /new、/N 的当前会话，且 /N 只列当前账号会话。绑定创建/重新启用一律要 `system.manage`，扫码路径用 iLink 返回的 `ilink_user_id`。
17. **监听游标在消息处理完成后才推进**：失败最多重复投递，由事件唯一键去重；反过来（先推游标）会静默丢消息。事件插入后的未预期异常必须删除事件行（允许重投），不能留成永久 `received`。
18. **媒体只存引用**：解析器不下载、不保留字节；单条消息最多 10 个引用，下载流式落盘并限 50MB；`attachments` 元信息经 `assistant.register_attachment` 写入。不要再加 `_pending_images` 之类的无界全局缓存。
19. **媒体下载防 SSRF**：只允许 `weixin.qq.com`/`wechat.com`/`qpic.cn` 的 https 地址或固定 CDN 下载地址；入站消息里的任意 URL 不得直接抓取。
20. **稳定消息 ID 带发送者作用域**（`msg:<from_user>:<id>`），账号维度另由唯一键覆盖；否则平台 ID 若只在聊天内唯一，会把另一个用户的同 ID 消息吞掉。

## 四、下一个任务（Task 8）的实施要点

按实施计划原文：`backend/modules/delivery/{api,contracts,repository,worker}.py`、`backend/modules/scheduling/{api,repository,scheduler,routes}.py`，测试 `tests/delivery/test_delivery.py`、`tests/delivery/test_schedule.py`。

- 先建目标/不可变产物引用/delivery+parts 状态；应用最终结果保存后再投递，失败只重试同一结果，不重跑 Runtime。
- `deliveries` 状态机 pending→sending→sent/retry_wait/uncertain/failed；job lease 不等于外部 exactly-once；确认丢失且无幂等键 → uncertain，不能假装必达。
- 调度：到期写唯一 occurrence（每计划 scheduled_at 唯一），重启不重复生成；错过默认只处理最新未完成实例并记录，不无限补发。
- 微信文本 Adapter 复用 Task 7 的 `IlinkTransport`/`send_text`；Task 7 只发送了命令回复，**run 最终答案投递尚未接**，Task 8 补上（不要在 assistant 或 channels 里再写一套发送）。
- 把旧 cron 调用迁到统一 Assistant/Delivery，删重叠后台任务启动；调度器只有一个生命周期入口（bootstrap 显式启动）。
- 必须测试：发送成功、有限失败、uncertain、分块失败恢复、解绑后不继续发、投递失败时 Runtime 执行次数不增加。
- 运行 `python -m pytest tests/delivery -q` 后提交；真实 SMTP/微信发送仍单列 integration。

## 五、已知未验证项（不要声称已完成）

- 真实 LLM 对话、真实 WeKnora MCP：integration，未联调。
- 真实微信 iLink 扫码/getupdates/sendmessage/CDN 下载解密：integration，未联调；`tests/contracts/test_wechat.py` 全部是 FakeTransport。
- 渠道附件只到 `RuntimeRequest.attachment_ids`；Hermes Adapter 尚未把 attachment 还原为图片 content blocks，真实多模态对话未验收。
- 微信 run 最终答案投递、提醒、失败重试：Task 8。队列满（Busy）当前只记 rejected，没有持久重试队列。
- 指纹窗口桶边界：重投恰好跨过 5s 桶边界时可能再执行一次；完全消除需滑动窗口查询，列为后续改进。
- 新工厂 OpenAPI 与 144 条保留路由的比对、channels 路由挂载：Task 15 显式装配后做。
- `tool_finished` 事件尚未桥接（Hermes step 回调语义所限）。
- 脚本 Runner 真实隔离验收（Task 13）未做——在此之前脚本"自动执行"必须保持关闭。
- 前端完全未改动。
- `AgentForge` 源目录未动；未使用任何旧生产凭证；未推送。
