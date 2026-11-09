# 微信 A+C 能力实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `2026-11-04-wechat-a-c-design.md` 交付微信 A+C：人格/记忆、提醒/weekly、账本对话、简报、语音、收件箱、情绪关怀。

**Architecture:** 继续模块化单体：新增 `profiles`/`inbox`/`briefing`，扩展 `scheduling`/`delivery`/`channels`/`assistant`/runtime。所有跨模块调用只走 `api.py`/`contracts.py`，SQLite 迁移只追加 `0014`（情绪采样幂等追加 `0015_mood_samples`），外部服务全部经 Adapter 注入并在测试中使用 Fake。

**Tech Stack:** Python 3.12、SQLite、FastAPI、LangChain `@tool`、Hermes（vendored，只改 Runtime 接缝）、Vue 3 + Vite、pytest、ruff。

---

## 0. 基线与硬约束

### 0.1 真实基线（2026-11-04 实测）

- `git log -1 --oneline`：`fe862ac test(ledger): 覆盖 0012→0013 增量迁移与已发布迁移 checksum 稳定性`
- 工作区已有用户未提交文档与未跟踪 spec：全部保留，不清理、不 `git reset/checkout --/clean`。
- 模块测试：
  `python -m pytest tests/access tests/architecture tests/assistant tests/contracts tests/delivery tests/evolution tests/files tests/fixtures tests/ledger tests/memory tests/models tests/resources tests/skills tests/storage tests/usage -q`
  → `544 passed in 170.12s`
- `python -m ruff check backend tests` → 614 个既有错误（历史工具/测试），作为 baseline failure；每阶段只要求新增/修改文件 ruff 全绿。
- `cd agent_frontend; npm run type-check` → 通过；`npm run build` → 通过。
- 全量 `pytest -q` 的 `tests/test_*.py` 17 个历史收集失败为既有问题，不作为本方案回归项。

### 0.2 依赖顺序与装配顺序

```text
DB/access
  → files/ledger
  → profiles
  → runtime（注册基础工具；ToolContext 中间件）
  → assistant（先构造，不启动 worker）
  → JobQueue（单一实例，供 scheduling/memory/content 共用）
  → delivery + delivery worker
  → scheduling（注入 JobQueue）
  → inbox + enrich worker
  → briefing + ContentWorker
  → memory + MemoryWorker
  → channels（构造后 late-bind commands：profiles/inbox/briefing/ledger）
  → runtime.register_extra_tools(...)（提醒/账本/收件箱/人格/记忆工具）
  → assistant.start()（启动前台 worker）
  → channels.start_listeners()
  → scheduler.start()
```

关键不变式：

1. `SchedulingService` 构造前 `JobQueue` 已存在；若保留 late-bind，则 `tick()` 时缺失必须明确报错而不是静默跳简报。
2. `AssistantService.start()` 必须晚于工具注册、delivery、`on_run_finished` 安装。
3. `channels.start_listeners()` 必须晚于 delivery 与 `on_run_finished`。
4. 工具注册幂等，按工具名覆盖，重复启动不产生重复 handler。

### 0.3 Feature flags 默认值

| 配置 | 默认 | 说明 |
|---|---|---|
| `EASYCHAT_HERMES_ENABLED` | `false` | 保持现有默认 |
| `EASYCHAT_WECHAT_ENABLED` | `false` | 保持现有默认 |
| `voice_enabled` / `EASYCHAT_VOICE_ENABLED` | `false` | 语音输入总开关 |
| `stt_provider` | `auto` | `auto/openai/local/off`，语音关闭时不发生 STT |
| `voice_echo` | `false` | 是否回显转写 |
| `briefing_enabled_default` | `false` | 简报默认关闭 |
| `mood_opt_in_default` | `false` | 情绪记忆默认关闭 |
| `inbox_enrich_daily_limit` | `20` | 每用户每日链接富化上限 |
| `mood_retention_days` | `90` | 情绪保留 |
| `backend_daily_token_budget` | `10000` | 后台每用户每日 token 预算 |

### 0.4 每阶段统一 TDD 流程

1. 先写失败测试（空值、越权、重复、并发/重启、时间边界至少各一个，按能力取舍）。
2. 运行单测确认失败原因是“能力缺失”，不是测试写错。
3. 最小实现。
4. 运行该测试 → 该阶段全部测试 → 受影响模块测试。
5. 对新增/修改文件跑 ruff；前端改动跑 type-check/build。
6. 更新本文件“进度/偏差”与验收结论；不通过不进入下一阶段。
7. 每阶段一个本地 commit（只在验证通过后）；报告列出 commit。

### 0.5 回滚点

| 阶段 | 回滚方式 |
|---|---|
| P0.5 | 只写探针文档/适配器开关，无 schema；回滚代码即可 |
| P0 | 保留 `0014` 与数据，回滚代码路径；不回滚已成功迁移 |
| P1/P1.5 | 回滚提醒/账本工具注册与命令分发；数据保留 |
| P2 | 关闭 `briefing` 创建入口；已生成 job 可幂等重跑/完成 |
| P3 | `voice_enabled=false`；音频附件保留 |
| P4 | 停止 `inbox.enrich` 入队；已存条目只读保留 |
| P5 | `/情绪 关闭` 停采样与推送；历史保留，`/情绪 删除` 可清除 |

---

## P0.5 外部探针

**目标：** 记录真实 iLink 语音格式与主动推送窗口行为；无凭证时实现可替换 Adapter 与明确未验证标记。

**文件：**
- Create: `docs/superpowers/plans/2026-11-04-wechat-a-c-probes.md`
- Modify: `backend/modules/delivery/wechat.py`（错误分类钩子）
- Test: `tests/delivery/test_wechat_error_classification.py`

**步骤：**
- [ ] 探测脚本/手工记录模板：语音容器 magic、大小、时长、云端 STT 是否接受；`context_token` 缺失/过期/有效三种推送结果与错误码。
- [ ] 无凭证：不伪造结论，文档写“未验证”，代码提供 `classify_wechat_error()`。
- [ ] 可判定错误（鉴权、参数、窗口关闭、明确 4xx）→ `SendResult.failed`；网络超时/连接中断 → `uncertain`。
- [ ] 测试：4xx/窗口错误不重试，超时 uncertain；未知错误保守 uncertain。
- [ ] 验收：`python -m pytest tests/delivery/test_wechat_error_classification.py -q`。

**回滚：** 删除分类函数调用，恢复统一 uncertain（数据无变化）。

---

## P0 基础设施

### Task P0-1：迁移 0014

**Files:** Create `backend/platform/migrations/0014_wechat_ac.sql`; Test `tests/storage/test_migration_0014.py`.

- [ ] 写失败测试：空库迁移到 0014；0013 库升级；三张表/四列/索引存在；0012/0013 checksum 不变。
- [ ] 迁移只含 spec §7 DDL；`assistant_profiles` 外键 users，`inbox_items` 部分唯一 URL，`mood_entries` 唯一 owner+date，`scheduled_jobs` 三列，`scheduled_occurrences.job_id`。
- [ ] 验收：迁移测试 + `tests/storage` 全绿。

### Task P0-2：ToolContext 双通道

**Files:** Create `backend/shared/tool_context.py`; Test `tests/contracts/test_tool_context.py`.

- [ ] 失败测试：contextvar 读写/reset；从 `RunnableConfig.configurable["tool_context"]` 读取优先；缺失返回 None；跨线程 copy_context。
- [ ] 实现冻结 dataclass + contextvar + `from_config()` + `bind()` contextmanager。
- [ ] 验收：测试通过。

### Task P0-3：Principal 与旧工具身份

**Files:** Modify `assistant/dispatcher.py`, `tools/tools_decorator.py`, `runtime/hermes/tools.py`; Test `tests/assistant/test_dispatcher_principal.py`, `tests/contracts/test_tool_identity.py`.

- [ ] 失败测试：管理员/普通用户/禁用用户/新线程 contextvar 丢失时 `_build_request` 与工具身份正确；禁用用户拒绝；`_current_user_id` 不再导入已删除模块。
- [ ] `_build_request` 全路径 `snapshot_principal(owner_id)`；异常明确拒绝（抛 `ForbiddenError`/`NotFoundError`），不落默认 user 0。
- [ ] `_make_handler`：同步 `invoke`，异步 `ainvoke`；构造 config 同时带 `thread_id` 与 `tool_context`。
- [ ] `register_safe_project_tools(extra_tools=...)` 幂等覆盖。
- [ ] 验收：assistant/contracts/architecture 相关测试 + async handler 真实返回。

### Task P0-4：Runtime 注入与微信渲染

**Files:** Modify `runtime/contracts.py`, `runtime/hermes/adapter.py`, `delivery/api.py`, `delivery/contracts.py`, `delivery/wechat.py`; Create `shared/wechat_text.py`; Tests.

- [ ] 失败测试：`persona_context`→`ephemeral_system_prompt` 且 `system_message is None`；`context_prefix + text` 传给 runner、`persist_user_message=text`；Markdown→微信文本（标题/表格/任务列表/分隔线）；`wechat_chunk_chars=500`，邮件 1800。
- [ ] RuntimeRequest 追加默认字段 `persona_context/context_prefix/persist_user_message`。
- [ ] sender 发送前 `render_wechat_markdown()`；DeliveryService 按 target_kind 选分块大小，不改全局常量。
- [ ] 验收：runtime/delivery 测试全绿。

### Task P0-5：profiles 与人格

**Files:** Create `backend/modules/profiles/{__init__,contracts,repository,api,routes}.py`; Modify `bootstrap.py`, `app.py`; Tests.

- [ ] 失败测试：默认 warm；更新/读取；custom 500 字上限；quiet hours 跨午夜；configurable 时区；mood opt-in 默认 false；`render_persona("wechat"/"web")` 差异。
- [ ] `ProfilesService.get/update/render_persona/mood_enabled/record_mood/weekly_mood/delete_mood`；不读会话原文（采样在 ContentWorker）。
- [ ] 路由 `/api/profile` GET/PATCH；mood 查看/删除入口。
- [ ] 验收：profiles 测试 + 前端日后联调契约。

### Task P0-6：记忆召回与写入

**Files:** Modify `assistant/dispatcher.py`, `bootstrap.py`, `platform/jobs.py`; Create `backend/integrations/llm.py`, `backend/modules/memory/jobs.py`; Tests.

- [ ] 失败测试：仅 web/wechat 召回；top 3/budget 800；失败不阻塞；显式“记住”才入队；无渠道也能入队；`source_type` 服务端强制 user_confirmed；重复 run 不重复提取。
- [ ] `JobQueue.enqueue_tx(conn,...)`；dispatcher 组装 memory prefix 与 persona；post-run 同事务入队 `memory.extract`。
- [ ] worker 调 `TextGenerator`，JSON 校验后 remember；失败确定性完成不重试。
- [ ] 验收：memory/assistant/bootstrap 测试。

**P0 验收命令：**

```powershell
python -m pytest tests/storage tests/contracts tests/assistant tests/architecture tests/profiles tests/memory tests/delivery -q
python -m ruff check backend/shared backend/modules/profiles backend/modules/assistant backend/modules/delivery backend/runtime backend/platform/jobs.py tests/profiles tests/contracts tests/assistant
```

---

## P1 提醒 + weekly 调度

**Files:** Modify `scheduling/{contracts,repository,api,routes}.py`, `bootstrap.py`; Create `backend/tools/business/reminder_tools.py`; Tests `tests/scheduling/test_weekly.py`, `tests/tools/test_reminder_tools.py`.

- [ ] 失败测试：weekly 跨周、时区不漂移、重复 tick 不重复、无 `cron.create` 拒绝、四选一校验、过去时间/2 年上限、10 分钟内重复返回已有 ID。
- [ ] `SCHEDULE_WEEKLY`、`weekday`、`weekly_at`；`create(timezone="")`；`_parse_at/_next_daily/_next_weekly` 用传入时区。
- [ ] 视图新增字段；`tick` 对 `content_kind=briefing` 同事务入队 `briefing.build` 并写 `occurrence.job_id`。
- [ ] `upcoming` / `delivered_between`。
- [ ] 4 个提醒工具，`__always_available__`，服务层权限兜底；snooze 复用原 target。
- [ ] 验收：scheduling/tools 测试；重复 tick/并发 tick。

---

## P1.5 账本对话

**Files:** Create `backend/tools/business/ledger_tools.py`; Modify `bootstrap.py`, `channels/commands.py`; Tests `tests/tools/test_ledger_tools.py`, `tests/channels/test_ledger_confirm.py`.

- [ ] 失败测试：ToolContext 缺失拒绝；无 ledger.view 拒绝；plan 含 sql 被服务层拒；commit 不在工具名；async 经 `_make_handler` 返回真实 JSON；非 owner、重复 message_id、控制总额不一致、`强制`、只接受完整 import_id。
- [ ] 5 个 LangChain async 工具包装 `LedgerToolbox.call`；返回 `amount_minor` + `amount_text`，预览截断 20 行差异。
- [ ] `/账单确认 <id> [强制]` 直连 `commit_import(request_id=f"wechat:{message_id}")`。
- [ ] 微信文件 `context_prefix` 带 `file_id`；预览回执含控制总额/新增/更新/差异/完整 ID。
- [ ] 验收：重复微信消息不重复入账；负向权限/owner/总额测试。

---

## P2 简报

**Files:** Create `backend/modules/briefing/{__init__,contracts,api,routes}.py`, `backend/modules/content/worker.py`; Modify scheduling/delivery/bootstrap; Tests.

- [ ] 失败测试：无绑定不发；quiet hours 延迟；空数据 skip；模型失败模板；数字/时间幻觉拦截；weekly 周一/周日；连续 7 天不重复。
- [ ] deterministic snapshot 装配 → `TextGenerator` 一次 → 模板兜底。
- [ ] `briefing.build` handler：生成后 `delivery.enqueue_text(dedup_key=briefing:...)`。
- [ ] `/简报 早/晚/周/关` 命令；创建 schedule content_kind=briefing。
- [ ] 验收：7 天模拟 tick、模型故障、dedup。

---

## P3 语音输入

**Files:** Create `backend/integrations/speech.py`; Modify channels media/api/settings/bootstrap; Tests `tests/channels/test_voice.py`, `tests/contracts/test_speech.py`.

- [ ] 失败测试：音频白名单；SILK magic 明确失败；空转写不提交 run；失败保留附件；不把音频发给 Anthropic 配置；flag 关闭不触发。
- [ ] `_ingest_media` 返回 `MediaIngestResult(attachment_ids, transcripts)`；voice 分支先转写再保存；ffmpeg 转 WAV；20 MiB/5 分钟。
- [ ] `AutoSTT/OpenAICompatibleSTT/LocalFasterWhisper`（可选）。
- [ ] `/语音 on|off`；`voice_echo`。
- [ ] 验收：Fake STT 全覆盖；真实格式标记未验证。

---

## P4 转发即存

**Files:** Create `backend/modules/inbox/{__init__,contracts,repository,api,routes,enrich}.py`, `backend/tools/business/inbox_tools.py`; Tests.

- [ ] 失败测试：URL 去重/合并；LIKE `%/_` 转义；owner 隔离；归档；未读计数；SSRF（localhost/内网/重定向）；抓取失败保留 URL；每日上限。
- [ ] `save/search/list/archive/unread_count`；附件经 assistant 校验 owner → file_id。
- [ ] `inbox_save/search/list/archive` 工具；`/存 <链接>`。
- [ ] `inbox.enrich` job：HTTPS、SSRF、3 重定向、5MiB/10s、正文 20k、TextGenerator 摘要。
- [ ] 验收：SSRF 负向、富化失败不影响保存。

---

## P5 情绪记忆与关怀

**Files:** Modify `profiles/api.py`, `content/worker.py`, `channels/api.py`; Create `backend/modules/mood/` 或 profiles 内采样适配；Tests.

- [ ] 失败测试：未 opt-in 零采样；每天 10 条上限；标签固定；证据必须是原文子串且 ≤60 字；同日平均；缺失日断连续；90 天清理；删除后不召回/不推送；危机固定文案含 12356/120/110；频控/安静时段。
- [ ] `mood.sample` / `mood.care` jobs；`mood_weekly` 周日 20:30。
- [ ] 危机词扫描在入站确定性执行，回复末尾追加固定资源，不记录原文。
- [ ] `/情绪 on|查看|删除|关闭`；删除保留审计计数，不留正文。
- [ ] 验收：危机/删除/频控/安静时段测试。

---

## 前端与命令

- [ ] `channels/commands.py`：命令统一分发，晚绑定公开接口，不产生模型费用；未知 `/` 返回 None。
- [ ] `/人设`、`/简报`、`/情绪`、`/记忆`、`/忘掉`、`/存`、`/账单确认`、`/help`。
- [ ] Web 设置页补人格/简报/情绪开关；收件箱列表/详情；账本页已有上传/预览/提交补错误态与防重复点击。
- [ ] 不新增设计未要求的大屏/框架。
- [ ] 验收：`npm run type-check`、`npm run build`。

---

## 风险与未验证项

- 无真实 iLink 凭证：语音容器、主动推送窗口、真实 STT 均标记“未验证”，只保证 Adapter/Fake 测试。
- 微信发送端只有 `send_text`，账单报告不承诺文件回传。
- Hermes `_run_async` 的线程模型需用测试验证 ToolContext 双通道；若未来内核改变，配置通道仍应兜底。
- SQLite 单机并发以 `BEGIN IMMEDIATE` + 唯一键 + 条件更新为准；不做分布式队列。

## 进度 / 偏差

| 阶段 | 状态 | 验证 | 偏差 |
|---|---|---|---|
| 基线 | 完成 | 544 passed；ruff 614 既有；前端通过 | 无 |
| P0.5 | 完成 | migration 0014/0015 + ToolContext 测试通过 | 无 |
| P0 | 完成 | dispatcher/identity/persona/delivery 测试通过 | 无 |
| P1 | 完成 | weekly/reminder/时区/去重测试通过 | 无 |
| P1.5 | 完成 | 账本工具 + `/账单确认` 测试通过 | 账单确认只发文本，不回传文件 |
| P2 | 完成 | briefing 模板/模型失败回退/幂等测试通过 | 无 |
| P3 | 完成 | 语音 Adapter/Fake 测试通过 | 真实 iLink 音频容器与 STT 未验 |
| P4 | 完成 | 收件箱/SSRF/富化失败测试通过 | URL 富化存在 DNS rebinding 残余风险 |
| P5 | 完成 | 情绪模型 JSON 采样/词表回退/同日平均/`/情绪`/周报调度/连续低落 care/危机固定回复测试通过 | care 固定模板，不追问、不要求回复；模型失败/越界按规范跳过；危机回复即时且优先于安静时段 |
| 审查 | 完成 | 新/改文件 ruff 0；维护测试集 669 passed/1 skipped；全量 932 passed/1 skipped | 5 个既有失败（3 个引用已删除的 `backend.service`，2 个引用已删除的 `backend/hermes_adapter.py`）；已修复 cwd 污染、投递卡 sending、周报统计窗口、同日简报去重、邮箱开放中继等 24 项 |
