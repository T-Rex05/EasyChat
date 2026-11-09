# 微信 A+C 验收报告与修复提示词（2026-11-05）

## 1. 结论

A+C 增量（提醒/简报/收件箱/账本对话 + 人格/记忆/情绪）已完成三轮验收修复：P1-1～P1-5 已闭合，P2-1、P2-2、P2-3 已修复；第四轮补了 care 回调原子性与主动性边界，见 §7.5、§7.6。离线测试通过仍不等于真实微信能力通过，真实外部依赖单列为未验证。

- 已修复：P1-1 纯语音失败、P1-2 简报过滤、P1-3 `memory.extract`、P1-4 async ToolContext、P1-5 发送成功语义；原 P2 开关、inbox 日限、lease 恢复、bootstrap SQL、设计口径、周报 care 条件、`/账单` 别名、账本工具异常；二次复核周报“下周”边界、记忆触发词、care 日志保留期；三次复核重复计划 occurrence、删除/关闭 pending care；四次复核 callback/delete 原子性、`care_epoch_at`、`proactivity=low`。
- 已通过：后端 required 测试 **726 passed in 221.98s**；本次改动文件 ruff；前端 `type-check` / `build` 通过（仅有既存 chunk/动态导入 warning）。
- 未验证：真实 iLink 主动推送窗口、真实语音格式/STT、真实微信聊天窗口账单上传、真实模型效果。
- 未修复/未纳入本轮：后台每日 token 预算尚未落地；`memory_correct` 工具未新增；模型不可用时显式“记住”是否回退正则仍未产品确认（当前按设计丢弃）；`tests/context_results` 5 个旧测试失败，另有未纳入 required 范围的顶层 `tests/test_*.py` 17 个 collection `ImportError`（均引用已删除的 `backend.service` / `backend.observer` / `backend/hermes_adapter.py` / 旧 paper 模块，与 A+C 无关；未用删测试掩盖）。

## 2. 已验证范围

代码核对覆盖：

- 调度 `weekly` / `content_kind=briefing` / occurrence 入队
- `RunDispatcher` 人格、时间、附件、记忆上下文
- `ToolContext` 的 contextvar + `RunnableConfig` 双通道
- 账本 5 个工具与 `/账单确认`
- channels 语音、媒体保存、危机词
- profiles 情绪采样、周报、care
- briefing 数据装配、模板兜底、数字护栏
- inbox 富化、SSRF 校验
- delivery 分块、重试、uncertain/error 分类
- JobQueue lease/重试/恢复
- 0014 + 0015 + 0016 迁移
- bootstrap 装配顺序与启动/关闭

验证命令：

```powershell
python -X utf8 -m pytest tests/access tests/architecture tests/assistant tests/contracts tests/delivery tests/evolution tests/files tests/fixtures tests/ledger tests/memory tests/models tests/resources tests/skills tests/storage tests/usage tests/briefing tests/channels tests/inbox tests/profiles tests/scheduling tests/services tests/tools -q
python -m ruff check <本次改动文件> --output-format concise
cd agent_frontend
npm run type-check
npm run build
```

结果（2026-11-05 第一轮）：`703 passed in 196.63s`；ruff、type-check、build 均通过。二次收尾结果见 §7.4。

## 3. 必须修复的偏差

### P1-1 纯语音 STT 失败仍提交 run

文件：`backend/modules/channels/api.py`（`_process_event` / `_ingest_media`）

`_ingest_media` 在转写失败后仍保存音频，`attachment_ids` 非空；`_process_event` 的失败条件带了 `and not attachment_ids`，因此不返回“这条语音我没转出来”，而是落到 `_default_media_text` 并提交 run。

修复：失败条件不能看音频是否保存成功。只在“媒体全是语音、无转写、无文字”时直接回复失败；语音+图片混合时，图片仍可处理。补测试：Fake STT 抛错、Fake files 成功保存音频、无文字，断言不调用 `assistant.submit`。

### P1-2 简报把简报自己列成提醒

文件：`backend/modules/briefing/api.py`（`_data`）；`backend/modules/scheduling/api.py`（`upcoming`）

`BriefingService._data` 调用未过滤的 `scheduling.upcoming`，早/晚/周报会把 `content_kind=briefing` 的“晚间简报/周报”当成提醒；周报还可能列自己。

修复：给 `SchedulingService.upcoming` 增加可选 `content_kind` 过滤，简报显式传 `text`；或在 `_data` 过滤 `item.content_kind != "text"`。`delivered_between` 已经在 SQL 中过滤 `text`，不要重复加回 briefing occurrence。补测试：FakeScheduling 同时返回 text/briefing，断言简报只出现 text，周报不含自己。

### P1-3 记忆写入没有达到设计

文件：`backend/modules/memory/capture.py`、`backend/modules/memory/worker.py`

设计是 `memory.extract` + `TextGenerator` 生成候选 JSON；实现是句首正则，只识别 `记住/记一下/别忘了`。`以后都…`、`我喜欢…`、`我讨厌…`、`我习惯…`、`我对…过敏` 不会自动入库，也没有 `memory_correct` 工具。

修复二选一，默认按补齐处理：

1. 增加 `memory.extract` job，worker 读取该 run 用户原文与最终回复，调用受控 `TextGenerator`，校验 JSON 后 `MemoryService.remember_explicit`；失败按确定性 `complete`，不猜。无 generator 时保留现有正则作为显式降级。
2. 如果决定不做 LLM，必须把产品触发词收窄为当前正则支持的范围，并在设计/帮助文案中删掉未支持的触发词，不能继续宣称支持。

补测试：自然表达“以后都别约周六上午”能入库；模型输出非法 JSON 不写入；重复 run 幂等；无 generator 时降级行为明确。

### P1-4 async 工具在 Hermes 新线程可能丢失 ToolContext

文件：`backend/runtime/hermes/tools.py`（`_make_handler`）

`_async_handler` 是 `async def`，`_config()` 在协程内部才执行。Hermes `_run_async` 若把协程放到新线程，contextvar 不会继承；真实 registry.dispatch 也没有把 `config` 传给 handler。现有测试直接调用 handler 并传 `config`，掩盖了这个问题。

修复：把 async 包装改成普通函数，先同步解析 `config`，再返回 `tool.ainvoke(...)` 协程：

```python
def _async_handler(args, **kwargs):
    config = _config(kwargs.get("config"))
    return tool.ainvoke(args or {}, config=config)
```

保留 `is_async=True` 注册。补测试：真实 `ToolRegistry.dispatch` 或新线程执行，清空 contextvar、不传 config，账本/提醒工具仍能拿到正确 owner。

### P1-5 情绪采样与关怀边界

文件：`backend/bootstrap.py`（`_make_run_finished`）、`backend/modules/profiles/api.py`（`care_due`）、`backend/modules/profiles/worker.py`（`_deliver_care`）

- failed/cancelled run 也会入队 `mood.sample`；设计只要求 completed。
- 采样日期用 `run.created_at`，跨午夜会记到前一天。
- `care_due` 固定 7 天冷却，没有 high 的 3 天/7 天 2 次双限。
- `mood.care` 延迟到安静时段结束后不再检查 opt-in/proactivity。

修复：

1. `on_run_finished` 只对 `status == "completed"` 入队情绪；用完成时间（`finished_at` 或回调时的当前时间）计算用户本地日期。
2. high 频控需要持久计数，不能只靠 `last_care_at`；推荐 0016 增加 `care_window_start` / `care_window_count`，或新增 `mood_care_log`。
3. `_deliver_care` 发送前重新检查 `mood_opt_in`、`proactivity`、目标绑定；发送成功后才 `mark_care_sent`。
4. 补测试：failed run 不采样；跨午夜日期正确；high 3 天内不重复、7 天最多 2 次；关闭 opt-in 后延迟 care 不发。

### P2 清单

- `backend/platform/settings.py` / `backend/integrations/speech.py`：增加 `voice_enabled=false` 总开关，关闭时不构造 STT、不加载本地模型；`stt_provider=off` 也要禁用。
- `backend/modules/inbox/api.py`：设计写每用户每天最多 20 条富化，代码未实现；在入队前做按日计数，超出只保存不抓取。
- `backend/platform/jobs.py`（`recover_expired_leases`）：`attempts >= max_attempts` 的 lease 应直接 failed，不能重新放回 pending 无限重试。
- `backend/bootstrap.py`（`_make_run_finished`）：直接 SQL 读 `assistant_profiles` / `conversations`，违反跨模块只走 api/contracts；改为模块公开接口或事务内 helper。
- 设计/实现口径不一致：设计写 https-only、5 MiB，实现允许 http、2 MiB；明确产品口径并写回设计（http 仅保存不抓取，或统一 https；2 MiB 作为当前上限）。
- `backend/modules/briefing/api.py`：`week.average <= 2.0` 对 -2..2 分数近似恒真；改为负向阈值，或直接只按 `low_days`。
- `/账单` 目前被别名到 `/账单确认`，容易误触发提交；要么移除别名，要么只做查询。补命令测试。
- `ledger_tools._call` 把所有异常 `str(exc)` 返回给模型；改为可读错误 + 完整错误只进日志。

## 4. 已同步的设计文档

`docs/superpowers/specs/2026-11-04-wechat-a-c-design.md` 已更新：

- 迁移标题改为 0014 + 0015，补 `mood_samples` 与 `score_total/sample_count`。
- 记忆写入标注“当前确定性正则，不是完整 LLM 提取”。
- 简报 `upcoming` 必须过滤 `content_kind=text`。
- 语音失败语义：音频保存成功不能作为已处理判据。
- 增加 `voice_enabled` 总开关。
- 情绪只采样 completed run、完成时间本地日期、`mood_samples` 幂等。
- care 频率区分 normal/high，high 需要持久 7 天计数。
- 新增 §23 验收补记与偏差清单。

## 5. 可直接复制的修复提示词

```text
请在 E:\PythonCode\EasyChat 接手“微信 A+C 增量”的验收修复。不要重做已经完成的架构迁移，不要动 E:\PythonCode\AgentForge，不要 push。

先读：
1. docs/superpowers/specs/2026-11-04-wechat-a-c-design.md（尤其 §9.2、§11.2、§12、§14.2/14.4、§23）
2. docs/superpowers/plans/2026-11-04-wechat-a-c-acceptance.md
3. 当前工作区 diff 与 tests/briefing、tests/channels、tests/profiles、tests/memory、tests/assistant 下的新增测试

当前基线：
- 后端首方全量测试 669 passed；ruff、前端 type-check/build 通过。
- 但下列 P1 是测试没有覆盖的真实逻辑缺口，不能因为全量测试通过就跳过。

按以下顺序修复，每个修复必须先补失败测试再改实现（TDD），不要只改文档：

P1-1 纯语音转写失败：
- 位置：backend/modules/channels/api.py 的 _process_event/_ingest_media。
- 失败条件不能包含“音频附件已保存”。当媒体全是 voice、transcripts 为空、message.text 为空时，直接回复“这条语音我没转出来，能打字或再说一遍吗？”，不得调用 assistant.submit。
- 语音+图片混合时，转写失败不应阻止图片处理；语音+文字时按文字处理。
- 新增 tests/channels/test_voice.py：Fake STT 抛 SpeechError、Fake files 成功保存音频、无文字，断言不提交 run；再补转写成功、语音+图片两条。

P1-2 简报过滤：
- 给 SchedulingService.upcoming 增加可选 content_kind 参数（默认空=全部，保持兼容），repo 对应过滤；BriefingService._data 显式传 content_kind="text"。
- 或者至少在 briefing 层过滤 item.content_kind != "text"，但优先做 API 层，避免其他调用方再踩。
- 更新 tests/briefing/test_briefing.py 的 FakeScheduling 签名，并新增“briefing 条目不出现在早/晚/周报、周报不列自己”的测试。

P1-3 记忆提取：
- 实现 memory.extract job：worker 读取该 run 用户原文与最终回复，调用 integrations/llm.py 的 TextGenerator，严格 JSON 校验后调用 MemoryService.remember_explicit；用户原文是事实来源，助手回复只用于消解指代。
- 支持设计中的触发表达：记住/记一下/别忘了/以后都/我喜欢/我讨厌/我习惯/我对…过敏。模型失败、非法 JSON、证据不是原文子串时丢弃，按确定性失败 complete，不重试、不猜。
- 没有 generator 时保留现有确定性正则作为显式降级，但要在日志/文档中说明；不能把降级路径说成完整实现。
- 去重 dedup_key=memory:{run_id}；补自然表达、非法 JSON、重复 run、无 generator 的测试。
- 如果最终决定不做 LLM，必须收窄产品触发词并同步帮助文案，二选一，不能含糊。

P1-4 async 工具上下文：
- 位置：backend/runtime/hermes/tools.py 的 _make_handler。
- 把 async 包装从 async def 改成普通函数：先同步 _config(kwargs.get("config"))，再返回 tool.ainvoke(args, config=config) 的协程；注册仍保持 is_async=True。
- 补一个不直接给 handler 传 config、而是在新线程/真实 registry.dispatch 路径执行的测试，证明 ToolContext 不丢；保留现有同步工具行为。

P1-5 情绪边界：
- backend/bootstrap.py：只有 status=="completed" 的 run 才入队 mood.sample；日期用完成时间的用户本地日期，不用 created_at。
- backend/modules/profiles/api.py care_due：normal 维持 7 天；high 至少间隔 3 天且最近 7 天最多 2 次。只靠 last_care_at 不够，增加持久计数（推荐 0016 给 assistant_profiles 加 care_window_start/care_window_count，或新增 mood_care_log）。
- backend/modules/profiles/worker.py _deliver_care：延迟投递前重新检查 mood_opt_in、proactivity、目标绑定；发送成功后才 mark_care_sent。
- 补 failed run 不采样、跨午夜日期、high 频控、关闭 opt-in 后延迟 care 不发的测试。

P2（P1 完成后做）：
- settings.py 增加 voice_enabled=false，bootstrap/build_stt 在关闭时不构造 STT、不加载本地模型。
- inbox 每用户每天最多 20 条富化，超出只保存不抓取。
- JobQueue.recover_expired_leases 对 attempts>=max_attempts 直接 failed，不无限回收。
- bootstrap._make_run_finished 不再直接 SQL 读 assistant_profiles/conversations，改走模块公开接口。
- 明确 inbox http/https 与 2 MiB/5 MiB 口径并写回设计；修正 briefing 的 average<=2.0 恒真条件；处理 /账单 别名误触发；ledger 工具异常不把原始 str(exc) 返回模型。

验证（必须实际运行并把输出写进报告）：
python -X utf8 -m pytest tests/access tests/architecture tests/assistant tests/contracts tests/delivery tests/evolution tests/files tests/fixtures tests/ledger tests/memory tests/models tests/resources tests/skills tests/storage tests/usage tests/briefing tests/channels tests/inbox tests/profiles tests/scheduling tests/services tests/tools -q
python -m ruff check <本次改动文件> --output-format concise
cd agent_frontend && npm run type-check && npm run build

约束：
- 不修改 backend/hermes 上游，除非证明必须；优先在适配层修。
- 不伪造真实 iLink/STT/微信上传结果；没有凭证就把真实外联列为未验证。
- 不把真实账单、情绪原文、聊天记录写入测试或日志。
- 保持现有未提交改动，不回滚其他模型的工作；不要执行 git clean/reset。
- 完成后更新 design 的 §23 和 acceptance 文档，报告“已修复/未修复/未验证”三类，不得只报通过数量。
```

## 6. 修复结果（2026-11-05）

### 6.1 已修复

| 项 | 修复 | 回归测试 |
|---|---|---|
| P1-1 | 纯语音失败条件改为“媒体全是 voice + 无转写 + 无文字”，不再看音频是否落盘；语音+图片继续处理图片，语音+文字按文字提交 | `tests/channels/test_voice.py` 3 条 |
| P1-2 | `SchedulingService.upcoming(..., content_kind=)` + repo 动态过滤；简报三时段显式传 `text`，不再列自己 | `tests/briefing/test_briefing.py`、`tests/scheduling/test_weekly_briefing.py` |
| P1-3 | 新增 `memory.extract` job；`TextGenerator` 严格 JSON，`evidence` 必须是用户原文子串，助手回复只做指代；非法 JSON/模型失败确定性 `complete`；无 generator 显式降级为句首正则 | `tests/memory/test_explicit_capture.py`、`tests/memory/test_revision.py` |
| P1-4 | `_make_handler` 的 async 分支改为普通函数，先同步解析 config 再返回协程；注册仍 `is_async=True`；新线程/registry 测试证明 ToolContext 不丢 | `tests/contracts/test_tool_context.py`、`tests/tools/test_ledger_tools.py` |
| P1-5 | 仅 `status=="completed"` 入队 mood；日期用 `finished_at` 的用户本地日期；high 为 ≥3 天且 7 天内 <2 次，0016 `mood_care_log` 持久计数；延迟 care 先复核 opt-in/proactivity/目标，成功后才标记 | `tests/profiles/test_mood_finish.py`、`tests/profiles/test_care.py` |
| P2 voice | `voice_enabled=false` 默认；`build_stt` 关闭时直接返回，不读模型配置、不加载本地模型 | `tests/services/test_speech.py` |
| P2 inbox | 每用户每本地日最多 20 条富化；超出只保存并标 `skipped` | `tests/inbox/test_inbox.py` |
| P2 lease | `recover_expired_leases` 对 `attempts>=max_attempts` 直接 failed | `tests/storage/test_jobs.py` |
| P2 bootstrap | 通过 `AssistantService.messages_for_run_tx` / `ProfilesService.mood_context_tx` 读取，不再直接 SQL | `tests/profiles/test_mood_finish.py`、`tests/delivery` |
| P2 inbox 口径 | http 可保存但 `skipped` 不入队；仅 https 抓取；2 MiB 流式上限写回设计 §13.3 | `tests/inbox/test_inbox.py` |
| P2 briefing | care 只看 `low_days>=3`，移除恒真 average 条件 | `tests/briefing/test_briefing.py` |
| P2 命令 | 移除裸 `/账单` 别名，保留 `/账单确认`、`/confirm` | `tests/channels/test_bill_confirm_command.py` |
| P2 ledger | AppError 只返回稳定 message；内部异常写日志并返回通用文案 | `tests/tools/test_ledger_tools.py` |

### 6.2 未修复 / 未纳入本轮

- 后台每用户每日 10,000 tokens 预算仍未实现（本轮 P2 清单未列，不能宣称已生效）。
- `memory_correct` 工具未新增；`/记忆`、`/忘掉` 与显式提取链路已完成。
- `tests/context_results` 的 5 个旧测试仍引用已删除的 `backend.observer` / `backend.service` / `backend/hermes_adapter.py`，保持失败，未通过删测试或改断言掩盖。
- 未纳入 required 范围的顶层 `tests/test_*.py` 另有 17 个 collection `ImportError`，均引用已删除旧模块，与本轮 A+C 无关。

### 6.3 未验证（外部依赖）

- 真实 iLink 主动推送窗口、`context_token` 时效与错误码。
- 真实微信语音容器、云端 STT、本地 faster-whisper、ffmpeg/SILK。
- 真实微信聊天窗口上传账单的端到端链路。
- 真实模型下的人格稳定性、简报数字护栏、记忆/情绪分类准确率。
- Docker/部署环境的启动资源、长稳与真实数据库锁竞争。

### 6.4 实际验证输出（第一轮历史，已被 §7.4 取代）

```text
python -X utf8 -m pytest tests/access tests/architecture tests/assistant tests/contracts tests/delivery tests/evolution tests/files tests/fixtures tests/ledger tests/memory tests/models tests/resources tests/skills tests/storage tests/usage tests/briefing tests/channels tests/inbox tests/profiles tests/scheduling tests/services tests/tools -q
703 passed in 196.63s (0:03:16)

python -m ruff check <本次改动文件> --output-format concise
All checks passed!

cd agent_frontend
npm run type-check
npm run build
# type-check 通过；vite build 成功（exit 0），仅有既存 chunk 体积/动态导入 warning。
```

未运行真实 iLink/STT/微信上传外联；没有把 mock 结果当成真实联调结果。

## 7. 二次验收收尾（2026-11-05 复核）

### 7.1 已修复

**P1-5：发送成功语义闭合。** `DeliveryService` 在投递账本真正进入 `sent` 后才触发 `on_sent` 回调；`bootstrap` 把它桥接到 `ProfilesService.mark_care_sent`，care worker 只入队，不再入队即标记。回调带 `source=care` 与 `dedup_key=mood-care:{owner}:{date}`；同 dedup_key 的 failed delivery 被复用时不会触发成功回调。`mood_care_log` 使用 care_key 派生确定性主键，重复回调不重复计数；已有 sent delivery 复用也不重复发送。测试：

- `tests/profiles/test_care_delivery.py::test_failed_delivery_does_not_mark_care_and_failed_dedup_is_not_success`
- `tests/profiles/test_care_delivery.py::test_sent_delivery_marks_once_and_duplicate_callback_is_idempotent`
- `tests/profiles/test_care.py::test_worker_enqueues_care_after_quiet_wakeup_without_marking`

**P2-1：周报“下周”边界。** 从明天 00:00 起算连续 7 天，过滤今天尚未到点的提醒；briefing 自身仍被 `content_kind=text` 排除。测试：`tests/briefing/test_briefing.py::test_weekly_next_week_starts_tomorrow_and_excludes_today`。

**P2-2：记忆触发词。** 支持 `别忘`/`别忘了` 与 `我以后都…`，保留句首/标点边界，`他说别忘了带伞` 不触发；普通聊天不触发。无 generator 仍只走句首确定性正则。测试：`tests/memory/test_explicit_capture.py`。

**P2-3：care 日志保留期。** `_purge_old` 同步按 `mood_retention_days` 删除 `mood_care_log`；`purge_expired_mood` 覆盖关闭情绪的用户；`/情绪 删除` 仍即时清空。关闭情绪保留 `mood_entries`/`mood_samples`/`mood_care_log` 到保留期，已在设计 §14.5 写明。测试：`tests/profiles/test_mood_retention.py`。

### 7.2 仍未修复或未纳入

- `bootstrap.py` 在 `registry.models` 存在时会构造 `OpenAICompatibleTextGenerator`；无可用模型/密钥时显式“记住”走模型失败分支并按设计丢弃，不回退确定性正则。该产品语义未获确认，本轮不改。
- `memory_correct` 工具、后台每用户每日 10,000 tokens 预算不在本轮范围。
- 全仓库无范围 `pytest -q` 仍会被旧顶层测试的 17 个 collection `ImportError` 中断；`tests/context_results` 仍有 5 个旧模块引用失败。与本轮 A+C 修复无关，未删测试、未改断言掩盖。

### 7.3 未验证

- 真实 iLink 主动推送窗口、`context_token` 时效与真实错误码。
- 真实微信语音容器、云端 STT、本地 faster-whisper、ffmpeg/SILK。
- 真实微信聊天窗口上传账单的端到端链路。
- 真实模型下的人格稳定性、简报数字护栏、记忆/情绪分类准确率。
- Docker/部署环境启动资源、长稳和真实数据库锁竞争。

### 7.4 实际验证输出

```text
python -X utf8 -m pytest tests/access ... tests/tools -q
708 passed in 208.96s (0:03:28)

python -m ruff check <本次改动文件> --output-format concise
All checks passed!

cd agent_frontend
npm run type-check && npm run build
# 均 exit 0；仅既存 chunk 体积/动态导入 warning
```

结论：**P1-1～P1-5 已闭合，二次复核的 3 个 P2 已修复。** 离线 required 套件全绿；真实外联/模型/部署仍未验证，不能据此宣称生产可交付。第三轮对重复计划与在途 care 的收尾见 §7.5。

## 7.5 第三轮验收收尾（2026-11-05）

第三轮只修两个边界：P2-1 的重复计划周报漏项，以及删除/关闭情绪后的在途 care。未重做 A+C，未修改 `backend/hermes`，未 commit/push。

### 7.5.1 P2-1：周报“下周”对重复计划已闭合

- `SchedulingService.upcoming(..., start=...)` 新增 occurrence 投影：按 once / interval / daily / weekly 的既有规则，纯计算 `start`（含）之后的下一次 occurrence，用 `dataclasses.replace` 写回返回的 `ScheduleView.next_run_at`；不修改 `scheduled_jobs.next_run_at`，也不触发 `tick`。
- `upcoming_for_owner` 先取 `next_run_at<=until` 的候选（不再 SQL `LIMIT`），由 service 展开后按投影时间排序，再按 `limit` 截断；50 条上限不会在展开前误删更早的 occurrence。
- `BriefingService` 早报 `start=今天 00:00`、周报 `start=明天 00:00`、晚报 `start=明天 00:00`，周报/晚报窗口 7 天/1 天，仍只取 `content_kind=text`，briefing 自身继续排除；morning/evening 行为未回退。
- 真实 `SchedulingService` + SQLite 测试（`tests/briefing/test_weekly_occurrences.py`，8 条）覆盖：
  - 每天 21:00，20:00 生成周报：投影到明天 21:00，`下周 1 条`，今天 21:00 不出现；且数据库 `next_run_at` 仍是今天 21:00；
  - 每周一 09:00，在周四生成周报：投影到下周一 09:00；
  - 一次性今天 21:00：不属于下周，`下周没有排定的提醒`；
  - `content_kind=briefing` 的计划不出现；
  - `start` 恰好等于 occurrence（00:00）只计一次；
  - interval 计划推进到 `start`；
  - 带小数 `start` 不包含更早的 occurrence；
  - 50 条上限在展开、排序后截断，最早的 00:00 项仍在。
- `tests/briefing/test_briefing.py` 的 FakeScheduling 已改为真实按 `start`/`until` 过滤，旧用例不再依赖“忽略窗口”的假行为。

### 7.5.2 删除/关闭情绪后的 pending care（第三轮）

- 新增 `DELIVERY_CANCELLED="cancelled"`；`DeliveryService.cancel_unsent(owner, source="care")` / `cancel(delivery_id)` 只把 pending/retry_wait 置为 `cancelled`，`sending/sent/uncertain` 不动；错误文案明确“用户删除/关闭情绪”，不伪装成发送失败。
- `ProfilesService` 通过 bootstrap 注入的窄回调调用取消接口，`profiles` 不 import `delivery`；`/情绪 删除` 与 `/情绪 关闭` 都清理 pending/retry 的 `mood.care`（含 `mood-care-wake`）job。
- `delete_mood` 在同一删除事务内把 `mood_opt_in=0`、`last_care_at=NULL`，删除后不会用旧 `last_care_at` 触发下一次 care；`MoodWorker` 入队后再检查 opt-in，若检查与入队之间发生关闭/删除，会取消刚入队的 delivery。
- 第三轮 `on_sent` 载荷新增 `created_at`；`ProfilesService.mark_care_sent` 用 profile `updated_at` 与 delivery `created_at` 拒绝删除/关闭后迟到或重复的回调。**该实现存在两个边界，已在第四轮修正：** ①检查在事务外，delete 可插在检查和 INSERT 之间；②`updated_at` 被任何资料更新推进，会误伤正常 care。
- 测试 `tests/profiles/test_care_delivery.py` 8 条（第三轮）：
  - pending → `delete_mood`：状态 `cancelled`、worker 不发送、无 care 日志、`last_care_at` 为空；迟到回调不复活；
  - pending → `set_mood_enabled(False)`：同样不发送、无日志；
  - 已 sent、但 `on_sent` 回调晚于 `delete_mood`：回调不写 care 日志/`last_care_at`；
  - 已 sent → `delete_mood` → 重复/迟到回调：不复活 care 日志/`last_care_at`；
  - 未删除/未关闭的正常 pending：发送成功只记一次；重复回调和既有 sent 复用仍幂等；
  - 未到 worker 的 pending `mood.care` job 在 delete/close 后被清理，worker tick 为 0。
- **第三轮残余**：已经进入 `sending` 的投递不能撤回；若外部发送已发生，消息可能已经到达。回调守卫只保证删除/关闭后不再把 care 数据写回。极小竞态没有被证明为数学上零窗口，不能宣称“删除后绝对不可能已发出”。第四轮已将回调检查移入原子事务，见 §7.6。

### 7.5.3 仍未修复 / 未纳入 / 产品决策点

- failed care 同 dedup 复用不误标记，但当天失败不自动补偿重试；是否重试未获产品确认，本轮不静默增加。
- `on_sent` 回调写库异常目前只记日志、不回滚已 `sent` 的账本，可能欠标记；是否增加补偿任务未确认，本轮不为修此引入误标记风险。
- `bootstrap.py` 在 `registry.models` 存在时会构造 `OpenAICompatibleTextGenerator`；无可用模型/密钥时显式“记住”走模型失败分支并按设计丢弃，不回退确定性正则。该产品语义未获确认，本轮不改。
- `memory_correct`、后台每用户每日 10,000 tokens 预算、`tests/context_results` 的 5 个旧失败和 17 个顶层 collection `ImportError` 仍不在本轮范围；未删测试、未改断言掩盖。

### 7.5.4 未验证（外部依赖，不能用 mock 代替）

- 真实 iLink 主动推送窗口、`context_token` 时效与真实错误码。
- 真实微信语音容器、云端 STT、本地 faster-whisper、ffmpeg/SILK。
- 真实微信聊天窗口上传账单的端到端链路。
- 真实模型下的人格稳定性、简报数字护栏、记忆/情绪分类准确率。
- Docker/部署环境启动资源、长稳与真实数据库锁竞争。

### 7.5.5 实际验证输出

```text
python -X utf8 -m pytest tests/briefing tests/scheduling tests/profiles tests/delivery -q
127 passed in 51.51s

python -X utf8 -m pytest tests/access tests/architecture tests/assistant tests/contracts tests/delivery tests/evolution tests/files tests/fixtures tests/ledger tests/memory tests/models tests/resources tests/skills tests/storage tests/usage tests/briefing tests/channels tests/inbox tests/profiles tests/scheduling tests/services tests/tools -q
722 passed in 234.13s (0:03:54)

python -m ruff check backend/modules/scheduling/api.py backend/modules/scheduling/repository.py backend/modules/briefing/api.py backend/modules/delivery/contracts.py backend/modules/delivery/repository.py backend/modules/delivery/api.py backend/modules/profiles/api.py backend/modules/profiles/repository.py backend/modules/profiles/worker.py backend/bootstrap.py tests/briefing/test_weekly_occurrences.py tests/briefing/test_briefing.py tests/profiles/test_care_delivery.py --output-format concise
All checks passed!

cd agent_frontend
npm run type-check
npm run build
# 均 exit 0；vite 19.76s 构建成功，仅有既存 chunk 体积/动态导入 warning。
```

结论：**P2-1 的重复计划周报漏项已闭合；删除/关闭情绪后的 pending/retry care 已取消。** `sending` 已进入外部调用的窗口不可撤回，是明确残余风险。第三轮 required 套件为 722 passed；第四轮将回调校验移入原子事务，最终计数见 §7.6。真实 iLink/STT/上传/模型/部署仍未验证，不能据此宣称生产可交付。

## 7.6 第四轮并发收尾（2026-11-05）

第四轮只补第三轮复核发现的两个 care 语义缺口，未重做 A+C，未修改 `backend/hermes`，未 commit/push。

### 7.6.1 回调与删除/关闭原子化

- 新增迁移 `0017_care_epoch.sql`：`assistant_profiles.care_epoch_at TEXT NOT NULL DEFAULT ''`。只有删除、关闭或 `proactivity=low` 时推进，普通资料更新（如 `max_chars`）不推进。
- `ProfilesRepository.mark_care_sent` 现在在同一个 `BEGIN IMMEDIATE` 事务内读取 `mood_opt_in`/`care_epoch_at`、校验 delivery 的 `created_at`、插入 `mood_care_log` 并更新 `last_care_at`。删除事务与回调事务因此串行化：要么回调先提交、删除随后清空；要么删除先提交、回调看到新代际后拒绝，不可能在检查后插入复活。
- `ProfilesService.mark_care_sent` 不再在事务外预读 profile；`_profile_newer_than` 已删除，避免通用 `updated_at` 误伤正常 care。
- `ProfilesService.update(proactivity=low)`、`enable_mood_for_owner(False)`、`set_mood_enabled(False)` 和 `delete_mood` 会取消 pending/retry care；`MoodWorker` 入队后再复核 opt-in 与 proactivity。
- 新增测试：
  - `test_callback_racing_delete_is_atomic_and_does_not_resurrect`：用线程在 repo 写入前插入 `delete_mood`，回调必须返回 false，care 日志仍为 0；
  - `test_unrelated_profile_update_does_not_drop_care_log`：pending 后改 `max_chars`，发送成功仍记账；
  - `test_low_proactivity_cancels_pending_care_and_stale_callback`：pending → low 后取消、不发送、旧回调不复活；
  - `test_re_enable_mood_does_not_revive_old_callback_epoch`：删除后重新开启，旧 delivery 仍被 `care_epoch_at` 拒绝。

### 7.6.2 仍未闭合/未验证

- `sending` 已开始外部调用的窗口仍不可撤回；本轮只保证删除/关闭后不再把 care 写回，不能保证消息未发出。
- 目标绑定/解绑发生在 care 已入队之后时，仍可能向旧 target 发送；本轮未加 channels→delivery 的取消回调，列为剩余边界。
- failed care 当天不补偿重试、`on_sent` 写库异常欠标记、模型不可用时显式“记住”不回退、`memory_correct`、每日 token 预算、旧 `tests/context_results` 5 失败和 17 个顶层 collection error 仍未处理。
- 真实 iLink/语音/STT/上传/模型/部署仍未验证。

### 7.6.3 实际验证输出

```text
python -X utf8 -m pytest tests/profiles tests/storage tests/briefing tests/delivery tests/scheduling -q
172 passed in 44.80s

python -X utf8 -m pytest tests/access tests/architecture tests/assistant tests/contracts tests/delivery tests/evolution tests/files tests/fixtures tests/ledger tests/memory tests/models tests/resources tests/skills tests/storage tests/usage tests/briefing tests/channels tests/inbox tests/profiles tests/scheduling tests/services tests/tools -q
726 passed in 221.98s (0:03:41)

ruff: All checks passed!
npm run type-check: exit 0
npm run build: exit 0（仅既存 chunk/动态导入 warning）
```

结论：**P2-1 已闭合；pending/retry care 的删除/关闭/低主动性边界已闭合；回调与删除的 TOCTOU 已用原子事务和 `care_epoch_at` 收掉。** `sending` 不可撤回和目标解绑后的旧 target 仍是残余风险；required 726 全绿不等于真实外联/模型/部署验收通过。

## 7.7 本地容器冒烟（2026-11-05）

默认 `docker compose up --build` 的 PyPI 直连构建在本机遇到 wheel hash mismatch（`Expected sha256 … Got sha256 …`），未完成默认镜像构建；这不是应用代码错误。为继续验证启动路径，本轮临时用可达 PyPI 镜像构建同结构镜像（临时 Dockerfile 已删除，不进入工作区），启动单容器后验证：

- 首次启动失败并暴露真实缺失依赖：`python-multipart` 未安装，FastAPI 在注册 files 路由时抛 `RuntimeError: Form data requires "python-multipart"`；已将 `python-multipart>=0.0.9` 加入 `docker/requirements-core.txt`，重建后启动成功。
- `/healthz` 返回 `{"status":"ok"}`；`/readyz` 返回 `ready`；Docker healthcheck 为 `healthy`。
- `/` 返回 SPA（`200`，标题 `AgentForge`，引用构建后的 assets）。
- 注册/登录、`GET /api/auth/me`、`GET/PATCH /api/profile`（warm/100/low）、`DELETE /api/profile/mood?confirm=true` 均成功。
- multipart `POST /api/files` 上传成功，返回 `status=ready`、`mime=text/plain`、`size=44`；`GET /api/files` 可见 1 条。
- 容器内 `app.db` 的 `schema_migrations` 到 `0017`，`assistant_profiles.care_epoch_at` 存在；重启容器后健康检查恢复 `healthy`，卷内用户仍可登录、profile 保持。
- 容器常驻内存约 63 MiB；`EASYCHAT_HERMES_ENABLED=false`，未验证真实 Hermes/LLM 启动。

后续若要复现默认 Dockerfile，需要在 Docker/PyPI 网络可靠的环境重新执行 `cd docker && docker compose up --build -d`；当前容器测试只能证明“依赖安装完成后的应用镜像”可启动，不能替代默认构建链路和真实外联验收。


