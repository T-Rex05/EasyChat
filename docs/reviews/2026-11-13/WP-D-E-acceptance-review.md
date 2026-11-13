# WP-D/E 独立验收复核

日期为 2026-11-13。核查对象为 `WP-D-E-memory-reminder.md`、WP-D提交 `b5a96e9`、WP-E提交 `a093931`，比较基线采用WP-D父提交 `0e77820`，核查当前HEAD `b50ec9b`。（本轮Git核查）

需求依据为 `docs/superpowers/plans/2026-11-13-five-issues-remediation.md` 工作包D/E。检查源码、生产装配与调用路径，并使用临时SQLite、真实业务服务和替身外部依赖验证，真实账号及消息内容未纳入本次读取。（验收方法）

## 结论

WP-D尚需返工，明确记忆、失败终态回执及微信确认目标仍有P1缺口。WP-E新增的内部提醒链路回归通过，实际微信受理和真机送达仍需实单证据。（源码核查与隔离实测）

## 1. 需求符合性

### P1 明确“记住”在生产常用配置下仍可能空跑

`backend/modules/memory/worker.py:169` 仅在 `generator is None` 时调用确定性提取，存在生成器时进入模型路径。`backend/bootstrap.py:195` 在models服务存在时创建生成器，辅助模型不可用可返回空文本。（源码核查）

使用真实临时SQLite、MemoryWorker和JobQueue，输入人工文本“记住：我喜欢少糖咖啡”，空生成器实验结果为 `empty_output=1, memories=0, jobs=[('memory.extract','succeeded')], confirmations=0`。（隔离实测）

新增 `test_empty_generator_output_is_diagnosable` 将零记忆作为预期结果。当前改动增加了状态区分，用户要求的明确记忆可靠写入仍需实现。（源码与用例核查）

完善要求为明确命令优先使用现有可信确定性提取，区分无候选与模型不可用，避免依赖主回答成功才处理明确记忆。写入时机及与后台抽取的去重按工作包D实施并评审。（修复建议）

### P1 失败、取消和启动中断的回执分支缺少生产调用

`backend/bootstrap.py:660` 增加失败/取消/中断文案，但 `backend/modules/assistant/dispatcher.py:243`、`:247` 仍只做状态迁移与事件结束，只有完成分支 `:253` 调用带 `on_finish` 的完成事务。启动中断恢复 `:95` 也直接迁移状态。（源码核查）

临时真实AssistantService、FakeRuntime、真实 `_make_run_finished` 和DeliveryService实验得到 `failed → deliveries=0`，对照 `completed空回复 → deliveries=1`。（隔离实测）

新增 `tests/delivery/test_delivery.py:261` 直接调用终态回调，证明文案映射与入队去重，实际dispatcher失败路径仍缺覆盖。（测试核查）

完善要求为把各终态与对应通知持久入队接入实际状态推进，保持原子性和run级去重，覆盖运行失败、执行取消、排队取消与重启中断，独立保留记忆/情绪等完成专属作业的条件。（修复建议）

## 2. 代码规范与可靠性

### P1 微信确认将会话隔离键当作收件人

`backend/modules/channels/api.py:348` 至`:352` 直接使用 `sessions.external_chat_id` 作为投递ref。实际入站在`:714` 将它存成 `account_id:external_chat_id`，新会话命令还追加时间戳。（源码核查）

临时session使用 `bot-account:real-openid` 时，新provider的 `target.ref` 同样为该拼接值。`backend/modules/delivery/wechat.py:99` 使用ref查真实external_user_id绑定，正常绑定使用 `real-openid`，因而形成确定的拒投路径。（临时目标解析实测与源码追踪）

另一个临时实验在没有账号及绑定的情况下仅填session字段，provider仍返回目标。原报告的“绑定仍活跃”“查不到不建孤儿投递”与该provider实际检查范围存在差异。（隔离实测）

完善要求为复用现有真实session route解析，取得external_user_id、账号及有效上下文，并核验当前有效绑定和owner。避免解析或拼拆sessions隔离键。（修复建议）

实际发送器仍检查活跃绑定，本轮发现的直接后果为目标错误、拒投与不必要的待处理记录，解绑后的实际数据外发绕过尚缺证据。（证据边界）

### P2 记忆确认入队失败后缺少恢复机会

记忆写入、会话确认与delivery入队分处不同事务。`make_memory_confirm` 先提交会话消息，再查询目标和入队，`worker.py:226` 的确认异常只记日志，随后 `tick` 仍完成job。（源码核查）

注入target provider异常后，会话确认已留下1条，微信确认入队失败。确认错误被吞掉，当前任务成功后无法通过原任务重试恢复该确认。（隔离实测与调用链核查）

完善要求为建立持久可恢复的确认意图，或在适当同一事务内写入带稳定身份的会话确认与outbox。通知失败应保留可恢复状态，记忆写入与通知重试分别去重。（修复建议）

### P2 会话确认缺少持久幂等身份

`backend/bootstrap.py:515` 至`:527` 每次回调分配新seq并插入确认，只有后面的delivery使用run级dedup。对同一run调用两次真实确认函数，临时数据库出现2条相同assistant确认。（隔离实测）

在确认提交后、job完成前退出，租约恢复再次执行可触发上述重复路径。完善要求为给会话确认定义稳定操作身份，并与确认意图、投递去重保持一致。（源码推断与修复建议）

## 3. WP-E已覆盖与需补充的场景

新增用例通过真实工具创建、临时时钟推进、Scheduler tick、DeliveryService.process_next和FakeSender，覆盖“未到期不发、到期入队、消费后含原提醒文本”。该内部链路回归有实际价值。（源码与本轮回归核查）

补充验收应包括以下场景。（建议）

| 场景 | 必须断言 |
|---|---|
| 微信入站创建提醒 | 可信身份、工具调用、schedule记录、创建确认均关联同一请求 |
| 重复入站和工具重试 | 不重复建计划，不重复发确认 |
| 暂停与删除 | 后续到期行为符合计划状态，历史记录可解释 |
| 服务重启与重复tick | 该occurrence仅形成一次逻辑投递 |
| 账号凭据失效/暂停 | 保留正确状态，等待恢复且重试有界 |
| 解绑与换绑 | 原任务目标重新校验，拒投有可读原因 |
| 真实iLink出站 | 在已授权测试目标验证手机收到，记录脱敏关联证据 |

报告已披露真机和暂停场景未验证，应据此限定WP-E完成范围。（报告核查）

## 4. 本轮验证

- `python -m pytest tests/tools tests/scheduling tests/delivery tests/memory -q` → `124 passed in 43.93s`，退出码0。（本轮实测）
- `python -m pytest tests -q -m "not integration and not resources"` → `1178 passed, 2 skipped, 3 deselected in 341.67s`，退出码0，与原报告数量一致。（本轮实测）
- 独立临时实验确认空生成器落空、实际失败run零delivery、错误目标解析、重复会话确认和确认异常后丢失恢复机会。（本轮隔离实测）

已有用例通过与上述缺口并存，补充回归须穿过实际dispatcher/渠道入口，不能仅直接调用新helper。（验收要求）

## 5. 续作与复验清单

1. 修正provider，使用真实渠道route及owner/绑定核验，测试普通微信会话、`/new`、解绑和换绑。（建议）
2. 实现明确记忆的确定性处理与持久幂等，验证生产形态的models存在但辅助模型不可用。（建议）
3. 接通失败、取消和启动中断的实际终态通知事务，验证同run重复终态只产生一次确认。（建议）
4. 为会话确认与通知建立持久恢复，故障注入覆盖每个提交边界和job租约恢复。（建议）
5. 补齐上述提醒生命周期与微信实单，复跑定向、契约和维护全集，再更新原交付报告。（建议）

实现涉及runtime、delivery、scheduling、存储或公共契约时按AGENTS.md及已有人工授权执行。本轮保留原报告并新增独立复核记录。（仓库约束与本轮交付）
