# WP-D/E 记录:记忆×提醒共用终态链路 + 微信提醒闭环(2026-11-13)

> 本文档描述 b5a96e9/a093931 交付时的状态；独立验收复核
> (`WP-D-E-acceptance-review.md`) 发现的 5 项缺陷已在本轮（round 2，见文末
> "整改轮记录"）修复，正文中相关失实表述已就地标注。

## WP-D(提交 b5a96e9)

**问题**:①"记住XX"类显式记忆依赖模型自由发挥,常静默丢失;②run 失败/取消/中断时微信端无任何回执,用户只见"没回音";③记忆确认与终态回执缺"发给谁"的统一通道。

**修改清单**
- `backend/modules/memory/worker.py`：
  - 显式捕获走确定路径：`generator is None` 降级态仅认旧触发词(`should_capture`)，命中即 `remember_explicit` 直写——**不再猜测新触发词**(fail-closed)；〔round 2 修正：该"仅在无生成器时"的限制正是复核缺陷①，现明确请求无条件先走确定性提取〕
  - `_extract` 返回 7 类终态分类(`captured_deterministic`/`captured_model`/`no_explicit`/`no_candidate`/`model_unavailable`/`empty_output`/`invalid_output`)，`extraction_status_counts()` 聚合可观测——"记忆没写入"从黑盒变为可查状态；〔round 2：`no_explicit`→`model_unconfigured`，新增 `write_failed`，共 8 类；模型不可用/空输出/写入失败改为有界重试而非记成功〕
  - `__init__` 新增 `confirm_writer=None`；写入成功后 `_confirm` 经通道回"已记住：…"(≤120 字符)，异常仅日志不阻塞 worker。〔round 2 修正：同步外呼+吞异常正是复核缺陷④，现 `_confirm` 改为入队持久 `memory.confirm` job，异常上抛交队列重试〕
- `backend/modules/channels/api.py`：`make_session_target_provider(db)`——按 sessions 表 owner+channel_account_id+external_chat_id 三重校验，产出 `ChannelTarget(kind="wechat", …)`，查不到返回 None。〔round 2 修正：external_chat_id 实为 `account_id:chat_id` 隔离键而非收件人，且"绑定活跃"校验当时并未实现——正是复核缺陷③；现复用 `channel_session_cursors` 真实路由解析 external_user_id + 账号活跃 + 绑定有效 + 绑定归属=owner〕
- `backend/bootstrap.py` `_make_run_finished`：run 终态可读回执四类——failed(含 error 摘要)/cancelled/interrupted/completed 空回复；run 级 dedup(`run:{id}:finished`)防重发。〔round 2 修正：四类文案当时只接在 completed 分支——dispatcher 的 failed/cancelled/queued-cancel/启动中断不经过该回调，即复核缺陷②；现经 `repository.finish_terminal` 全部接入〕
- 测试：`tests/memory/test_explicit_capture.py` +4(确定写入、确认回发、降级态不猜新词、状态计数)；`tests/delivery/test_delivery.py` +`test_terminal_state_feedback_without_reply`(失败无回复仍送达回执)。〔round 2：该测试直调回调，不覆盖真实 dispatcher——已补 `tests/delivery/test_run_terminal_feedback.py` 走真实受理/推进〕

**评审发现(调试中确认的非缺陷)**
- 断言"回执未出现"初值失败系**事务提交前**读 `list_for_owner` 的时序问题——行为本正确，测试改为提交后断言。
- 回执写入在 `db.transaction()` 提交后外发，符合"事务体内禁外呼"硬约束。

## WP-E(本次提交)

**问题**:微信提醒"创建→到点→收到"整链从未在一个测试里串起来验证过；用户实报"提醒没收到"无法定位是创建、调度还是投递环节。

**核查结论**
- 幂等：`scheduling/api.py::create` 已有 `find_recent_duplicate` **签名匹配**去重(非"10 分钟窗口"——该表述为早期方案记录的误导,以此更正)。
- 可读创建返回(✅ 已设置+触发时间+ID)、到期投递 dedup(`schedule:{id}:{at}`)、无绑定不建孤儿——均已有实现与专测。
- **缺口在端到端串链**：tick 只入队，发送由 `DeliveryService.process_next()` 消费——此前无测试覆盖"创建→未到期→到期→消费→sender 收到原文"全链。

**修改清单**
- `tests/tools/test_reminder_tools.py`：新增 `test_reminder_e2e_create_due_delivers`——工具创建提醒→NOW=12:00 tick 不触发不投递→时钟拨到 14:31 tick 触发入队→`process_next` 泵空→FakeSender 收到含原文本"喝水"的投递。逐段断言使断链可定位。
- 曾尝试提取 `_created_reply` 单用 helper(snooze 措辞不同未复用)，按 laziness-protocol 回退，代码零改动。

## 验证退出码（round 1 实测，保留为历史证据）

| 命令 | 结果 | 退出码 |
| --- | --- | --- |
| `pytest tests/tools -q` | 7 passed | 0 |
| `pytest tests/tools tests/scheduling tests/delivery tests/memory -q` | 124 passed | 0 |
| `pytest tests -q -m "not integration and not resources"` | 1178 passed, 2 skipped, 3 deselected | 0 |

## 未验证项（round 1 登记）

- 真机微信全链(到期→iLink 出站→手机收到)：FakeSender 只验证链路逻辑，出站通道未实测。（round 2 仍未做，见文末续作步骤）
- ~~提醒触发时账号恰好被 errcode=-14 暂停的场景行为~~：round 2 已补
  `test_stale_token_pauses_account_and_retry_is_bounded`（真实 WeChatTextSender
  + 假 transport），真机实单未做。

## 回滚

revert 本提交(WP-E,仅测试文件)与 b5a96e9(WP-D)即可；两包均无迁移、无数据 schema 变更，`confirm_writer`/`make_session_target_provider` 为附加参数/附加工厂，回退后 bootstrap 不引用。round 2 回滚见文末。

---

# Round 2：独立验收 5 缺陷整改（2026-11-13 复核 `WP-D-E-acceptance-review.md` 后）

3 项 P1 + 2 项 P2。每项先写复现红测试、对证失败，再最小修复复验绿。

## 缺陷①（P1）明确"记住"在生产配置下仍可能空跑

- `memory/worker.py::_extract`：`should_capture` 命中即无条件先走确定性提取
  （`candidate_from_user_message`→`remember_explicit`→确认意图入队），
  覆盖生成器异常/空输出/未配置；自然表达才用模型；`generator is None` 时
  自然表达返回新状态 `model_unconfigured`（fail-closed 不猜）。
- `enqueue_capture_tx`：failed/interrupted run 也入队显式记忆（主回答失败
  不再阻断"记住"）；cancelled 尊重用户意图仍不入队；completed 保持全触发词。
- 状态分类 8 类（新增 `write_failed`，`no_explicit`→`model_unconfigured`）；
  `model_unavailable`/`empty_output`/`write_failed` 由"记成功"改为**有界重试**
  （JobQueue max_attempts=5、60s 退避），`invalid_output`/`no_candidate` 等
  确定性结果仍不重试。重放幂等靠 `remember` 的内容去重 + SourceRef(run_id)
  稳定来源身份。
- 红→绿：`tests/memory/test_explicit_capture.py`
  `test_explicit_remember_never_depends_on_generator`、
  `test_explicit_remember_enqueued_on_failed_and_interrupted_run`（修复前
  model_unavailable+零记忆+job 成功 / failed run 拒绝入队）。

## 缺陷②（P1）失败/取消/中断回执未接生产路径

- `assistant/repository.py` 新增 `finish_terminal`：failed/cancelled/interrupted
  状态推进与 `on_finish` 回调**同事务**（与 completed 的
  `finish_run_with_projection` 对称，不投影 assistant 消息）；条件 UPDATE 以
  合法旧状态为界——重复终态回调不触发（幂等），回执本身另有 run 级 dedup。
- `request_cancel` queued 分支同样经 `finish_terminal` 通知（排队取消有回执）。
- `dispatcher.py` 五处接线：启动中断对账、构建请求失败、流后 cancelled、
  流后 failed、`_fail_stuck_run`——不再是"只有 completed 调回调"。
- 红→绿：新增 `tests/delivery/test_run_terminal_feedback.py` 5 例（真实渠道
  受理 handle_inbound → dispatcher → 真 `_make_run_finished` → delivery 账本）；
  对证=暂存本修复后同测试 4 failed（failed/重复终态/排队取消/重启中断零回执），
  completed 空回复 1 例两态皆绿（对照分支）。

## 缺陷③（P1）微信确认把会话隔离键当收件人

- `channels/api.py::make_session_target_provider` 重写：不再读
  `sessions.external_chat_id`（实为 `account_id:chat_id`，/new 还追加时间戳）；
  复用 `delivery_target_for_run` 同一套真实路由——`find_session_route`
  (channel_session_cursors) 取 `external_user_id`+context_token，并核验会话
  source=wechat、会话 owner、账号 ACTIVE、绑定 ACTIVE、**绑定 user_id=owner**
  （解绑/换绑/禁用即失效，fail-closed）。
- 红→绿：新增 `tests/channels/test_session_target_provider.py` 6 例——普通
  会话（修复前 ref=`bot_1:wx_ext_1` 拼接键）、/new、解绑、换绑、多账号隔离、
  越权 owner；修复前 5 failed。

## 缺陷④（P2）确认失败缺少可靠恢复

- 确认改为**持久意图**：`_confirm` 在记忆写入成功后入队 `memory.confirm` job
  （dedup `memory-confirm:{run_id}`），worker tick 消费并经 confirm_writer
  （bootstrap `make_memory_confirm`，独立小事务、事务体内无外呼）落会话消息+
  渠道回执入队；异常 → job 有界重试，不再"吞异常后 job 成功"。extract job 若
  在确认入队前崩溃：租约恢复→写入幂等→确认按 dedup 复用。
- 红→绿：`test_confirm_intent_is_durable_and_recovers`（注入确认失败：修复前
  确认丢失、job 记成功；修复后 retry_wait→退避到期→成功，恰好一次）、
  `test_confirm_intent_survives_extract_retry`（extract 重放不产生第二条确认）。

## 缺陷⑤（P2）会话确认缺少持久幂等

- `bootstrap.py::make_memory_confirm`：会话确认插入前按稳定操作身份
  `(session_id, run_id, role='assistant', source='system', content)` 查重，
  已存在即视为已提交（幂等重放）；与 confirm job dedup、delivery
  `memory-confirm:{run_id}` 构成同一 run 级身份链。
- 红→绿：`test_session_confirmation_idempotent_within_run`（修复前同 run 两次
  调用落 2 条相同 assistant 消息）。

## 提醒生命周期补测（复核建议表）

`tests/tools/test_reminder_tools.py` 新增 4 例：
- 暂停/取消后到期不投递→`test_cancelled_schedule_delivers_nothing`；
- 重复 tick+服务重启仅一次逻辑投递→
  `test_due_occurrence_single_delivery_across_repeat_tick_and_restart`；
- 凭据失效 -14→`test_stale_token_pauses_account_and_retry_is_bounded`
  （真实 WeChatTextSender：report_stale_token 暂停上报、账本 retry_wait 不丢、
  恢复后重投成功只发一次）；
- 到期前解绑→`test_unbound_before_due_rejects_with_reason`（零真实外发、
  可读拒投原因）；解绑/换绑路由层另见缺陷③ 6 例；重复入站/工具重试幂等由
  既有签名匹配用例覆盖。
- 微信入站自然语言→模型实际调用 reminder_create 的真机实单仍未验证（见下）。

## 评审发现并修复的测试缺陷

jobs 表 id 为随机 uuid，新测试以 `ORDER BY id` 首/末位定位"本次 job"存在
非确定性（全量运行曾因此翻面一次）；改为按 `dedup_key=memory:{run_id}`
精确过滤——测试基建修正，非行为变更。

## Round 2 验证退出码（实测）

| 命令 | 结果 | 退出码 |
| --- | --- | --- |
| `pytest tests/tools tests/scheduling tests/delivery tests/memory -q` | 138 passed（基线 124+14） | 0 |
| `pytest tests/contracts tests/channels -q` | 184 passed（含 provider 6 新例） | 0 |
| `pytest tests -q -m "not integration and not resources"` | **1198 passed, 2 skipped, 3 deselected** | 0 |
| `pytest tests/memory/test_explicit_capture.py` ×3 连跑 | 18 passed 稳定 | 0 |
| `ruff check`（本轮改动文件） | All checks passed（唯一新违规已修） | 0 |

## 真实微信验收

**未执行**——外部条件缺失：本轮会话无 admin 登录凭据（纪律：凭据不入对话/
文件，前轮凭据未持久化），真机收信还需用户手机侧确认。续作步骤（预计 5 分钟）：
1. 重启本地服务加载本轮代码（当前 8001 进程仍以旧提交代码运行）。
2. 微信发"记住：验收R2咖啡少糖"→应收到"已记住：…"回执；面板记忆页核对同
   owner 恰好一条记录。
3. 微信发"三分钟后提醒我验收R2喝水"→模型应调用 reminder_create 并回执 ID+
   触发时间；到点手机收到含"验收R2喝水"的提醒。
4. 关联脱敏记录：event_id→session_id→run_id→jobs(memory.extract/confirm)→
   memory id→schedule id→delivery id 逐段取自 API/DB，不记录内容原文。
5. 发取消类语句验证 reminder_cancel 后不再到期投递。

## Round 2 回滚

revert 本轮提交即可（涉及 `memory/worker.py`、`assistant/dispatcher.py`、
`assistant/repository.py`、`channels/api.py`、`bootstrap.py` 与测试）；无迁移、
无 schema 变更。注意：回滚后已入队未消费的 `memory.confirm` job 不再被认领，
行为等同旧版"确认可能丢失"，无数据损坏风险（jobs 为旁路账本）。
