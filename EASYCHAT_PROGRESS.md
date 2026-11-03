# EasyChat 实施进度交接（2026-11-03）

给接手实施的模型：**从这里开始**，然后按顺序读 `EASYCHAT_HANDOFF.md` → 架构规范 → 实施计划 → `docs/superpowers/plans/easychat-execution-log.md`（每个任务的完整证据记录）。

## 一、当前状态

| 项 | 值 |
|---|---|
| 分支 | `main`（未推送，origin=gitee，遵约束不自动 push） |
| 工作树 | 干净（本文档提交后 `git status --short` 为空） |
| 提交数 | 32（基线起每任务一个提交 + 加固/日志提交 + 本进度文档更新） |
| 已完成 | **Task 0–14 完成；Task 15 后端装配部分完成（前端/旧模块删除未做）** |
| 下一任务 | **Task 15 剩余：前端页面/API 收敛、旧模块删除、main.py 切换；之后 Task 16** |
| 未开始 | Task 15 剩余、Task 16 |
| 测试 | `python -m pytest tests/architecture tests/contracts tests/access tests/assistant tests/models tests/storage tests/usage tests/delivery tests/memory tests/skills tests/evolution -q` —— **299 passed**；**旧 tests/ 下大量遗留测试仍引用已删依赖/MySQL，不能整体跑** |

最近提交：`986c5d3`(Task 15 装配) `cfd8a41`(Task 14 docs) `10ffc03`(Task 14) `24c6f77`(Task 13 docs) `5044c61`(Task 13) `6ee4973`(Task 12) `401ba91`(Task 11) `ce3eaf4`(Task 10) `bebd4cd`(Task 9) `ba1c79f`(Task 8) `08a4bd7`(Task 7) `72aa14c`(Task 7) `1105e38`(Task 6) `47dbcd6`(Task 5) `09fe0db`(Task 4) `ba8964e`(Task 3) `ee8f903`(Task 2) `6f418e5`(Task 1) `1d41c2a`(基线)

## 二、已完成模块（新架构，全部有测试）

```
backend/
  app.py / bootstrap.py           无副作用工厂；lifespan 显式启动
  shared/{context,errors,identifiers,crypto}.py
  platform/{sqlite,settings,jobs}.py + migrations/0001..0010
  modules/access/     RBAC、users/roles、Principal、token（35测试）
  modules/usage/      唯一计量入口 usage.begin_call/complete_call/report_usage（12测试）
  modules/models/     模型配置、AES-GCM密钥、选择链（9测试）
  modules/assistant/  统一run入口 + 事件总线 + 调度器 + Web兼容路由（21+测试）
  modules/channels/   账号/绑定/事件去重 + wechat/{parser,account,listener,media}（33测试）
  modules/delivery/   投递账本/分块/重试 + 微信文本 + SMTP/PDF 报告（27测试）
  modules/scheduling/ once/interval/daily 提醒 + 唯一调度器（7测试）
  modules/memory/     事实/事件/经验、版本、召回、遗忘、幂等信号（29测试）
  modules/skills/     不可变版本、CAS 激活/回滚、pin/归档、内容 hash（25测试）
  modules/evolution/  唯一学习调度、证据、每日/单次预算、候选验证/采用（22测试）
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
21. **生成与投递分离**：投递只保存/重发已确定内容；run 完成回调必须在 assistant 终态事务内写 `deliveries`（同事务），失败重试不得再次调用 Runtime。
22. **分块续发**：`delivery_parts` 的 `(delivery_id, seq)` 唯一，已发送块重试时跳过；进程重启时 `sending` 记录转 `uncertain`，不能盲目重发。
23. **提醒只补最新实例**：`scheduled_occurrences` 的 `(schedule_id, scheduled_at)` 唯一；错过多个周期只处理最新一个并记 `missed`，不补发无限历史。
24. **记忆写入必须带来源**：`source_refs` 为空直接拒绝（服务层校验，不依赖路由）；模型推断与用户确认分列 `source_type`，假设/转述不得写成用户事实。
25. **遗忘是墓碑而非只删一行**：清空正文并删除全部 revisions，`forget_rules` 只存 sha256；按 memory_id 遗忘时同时登记 content/source_ref 哈希，阻止旧消息重提取。
26. **召回有硬上限**：候选 80、top5、2000 token；archived 只有查询含“上次/以前/之前/还记得”等旧事提示时才进入候选；0 条明确无结果，不调用模型编造。
27. **技能内容路径只由模块 ID 决定**：`skl_/skv_` 决定 `skill_id/version_id.md`，用户 name 不参与路径；写入先临时文件+fsync+replace，已存在版本拒绝覆盖，读取必须校验 sha256。
28. **激活必须 CAS**：`expected_active_version_id` 条件更新；坏版本（文件缺失/hash 不符）在改指针前拒绝，失败保留旧 active。pin 技能只允许用户显式写入，background/evolution 一律拒绝。
29. **学习不学自己**：`source=evolution` 直接拒绝；学习任务单 worker、暂停前不认领；预算先预留，未知 usage 保留预留不返还。
30. **预算按项目时区日切**：`evolution_budgets(stat_date,user_id)`；每日 20k/单次 5k 默认可配；超预算任务标 paused，不发下一次 LLM。
31. **验证先于采用**：无 baseline 不能证明无回归；pin 技能自动采用一律保留原版；采用只 CAS 切 active 指针并写证据，回滚也是 CAS。
32. **回放必须零副作用**：验证 replayer 由注入替身提供，测试断言不产生 deliveries/runs；真实执行必须等 Task 13 Runner 隔离验收。
33. **Runner 默认 disabled**：没有通过真实 Linux 隔离验收前，任何脚本执行请求都返回 denied；子进程+参数过滤不等于安全隔离，自动执行保持关闭。
34. **邮件/PDF 先 artifact 后投递**：PDF 未启用/缺依赖时明确失败且不建 artifact；SMTP 未启用不建连；密码只存 AES-GCM 密文，发送失败只重试同一文件。

## 四、Task 15 剩余实施要点

后端显式装配已完成（`986c5d3`）：新 app 已挂载 access/usage/assistant/channels/memory/skills/evolution，未就绪返回 503；启动自动构造 access/usage。剩余：

- **前端**：`agent_frontend/node_modules` 不存在，先在可联网环境安装锁定依赖，再收敛聊天/历史、RBAC、Token 榜、邮件/PDF、技能、提醒、记忆、运行/进化页面与菜单；删除 KB/图谱/论文/社区/SQL 页面与请求；执行 `npm run type-check`、`npm run build`。
- **旧模块删除**：迁移保留路由（cron/skills/email/platform-config 等）到新模块后，切换 main.py 到 `backend.app.create_app`；删除 backend/controller|service|db 的旧 mapper/provider/MySQL 启动与 KB/图谱/论文/社区/SQL 专用路由；删对应旧测试/样本；保持旧库不作为运行时依赖。
- **契约核对**：新 app OpenAPI 与 144 条保留路由逐条比对；`tests/architecture/test_removed_dependencies.py` 扩展为实际目录不存在/无 import；默认全量测试不得残留已删模块 import。
- **Task 16**：单 worker Docker/持久卷、资源采样、干净环境启动、恢复验收与最终交付文档。

## 五、已知未验证项（不要声称已完成）

- 真实 LLM 对话、真实 WeKnora MCP：integration，未联调。
- 真实微信 iLink 扫码/getupdates/sendmessage/CDN 下载解密、真实 SMTP：integration，未联调；渠道/投递测试全部用 FakeTransport/FakeSender。
- 渠道附件只到 `RuntimeRequest.attachment_ids`；Hermes Adapter 尚未把 attachment 还原为图片 content blocks，真实多模态对话未验收。
- 微信 run 最终答案已接入投递账本（Task 8），但真实发送未联调；队列满（Busy）当前只记 rejected，没有持久重试队列。
- 记忆只接受显式信号/remember；真实 LLM 自动提取未联调，MemoryBridge 尚未注入 Hermes Adapter。
- 技能：File/Terminal/CodeMode/Runner 的受保护路径 guard 尚未接线；Hermes skill_manage/后台 review 仍走旧写路径；`skill_usage` 旧侧写未迁移；SkillsBridge 尚未注入 Runtime。
- 学习：真实 LLM 学习/候选生成是 Task 12；paused（暂停/超预算）任务不会自动重新入队。
- 渠道/提醒/投递/记忆/技能/进化 HTTP 路由尚未挂载，Task 15 显式装配后提供入口；旧 main.py 的 cron 仍在旧进程，未自动迁移。
- 指纹窗口桶边界：重投恰好跨过 5s 桶边界时可能再执行一次；完全消除需滑动窗口查询，列为后续改进。
- 新工厂 OpenAPI 与 144 条保留路由的比对：Task 15 显式装配后做。
- `tool_finished` 事件尚未桥接（Hermes step 回调语义所限）。
- 脚本 Runner 契约完成但真实 Linux 隔离未验收（Task 13）——自动执行继续保持关闭。
- 邮件/PDF 已实现离线能力（Task 14），真实 SMTP 发信与真实 PDF 渲染未联调。
- 新 app 显式路由已装配，但生产启动仍需设置 JWT/Hermes/模型配置；未配置 Runtime 时聊天返回 503（预期）。
- 前端未迁移，`agent_frontend/node_modules` 不存在，无法离线 type-check/build；旧 KB/图谱/论文/社区/SQL 模块、旧 mapper/provider、旧 main.py 路由仍存在，Task 15 未完成。
- `AgentForge` 源目录未动；未使用任何旧生产凭证；未推送。
