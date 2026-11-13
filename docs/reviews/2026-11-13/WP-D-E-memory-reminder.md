# WP-D/E 记录:记忆×提醒共用终态链路 + 微信提醒闭环(2026-11-13)

## WP-D(提交 b5a96e9)

**问题**:①"记住XX"类显式记忆依赖模型自由发挥,常静默丢失;②run 失败/取消/中断时微信端无任何回执,用户只见"没回音";③记忆确认与终态回执缺"发给谁"的统一通道。

**修改清单**
- `backend/modules/memory/worker.py`：
  - 显式捕获走确定路径：`generator is None` 降级态仅认旧触发词(`should_capture`)，命中即 `remember_explicit` 直写——**不再猜测新触发词**(fail-closed)；
  - `_extract` 返回 7 类终态分类(`captured_deterministic`/`captured_model`/`no_explicit`/`no_candidate`/`model_unavailable`/`empty_output`/`invalid_output`)，`extraction_status_counts()` 聚合可观测——"记忆没写入"从黑盒变为可查状态；
  - `__init__` 新增 `confirm_writer=None`；写入成功后 `_confirm` 经通道回"已记住：…"(≤120 字符)，异常仅日志不阻塞 worker。
- `backend/modules/channels/api.py`：`make_session_target_provider(db)`——按 sessions 表 **owner+channel_account_id+external_chat_id 三重校验**产出 `ChannelTarget(kind="wechat", …)`；查不到返回 None(不建孤儿投递)。确认/回执与投递链路共用此目标解析。
- `backend/bootstrap.py` `_make_run_finished`：run 终态可读回执四类——failed(含 error 摘要)/cancelled/interrupted/completed 空回复；run 级 dedup(`run:{id}:finished`)防重发。
- 测试：`tests/memory/test_explicit_capture.py` +4(确定写入、确认回发、降级态不猜新词、状态计数)；`tests/delivery/test_delivery.py` +`test_terminal_state_feedback_without_reply`(失败无回复仍送达回执)。

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

## 验证退出码(实测)

| 命令 | 结果 | 退出码 |
| --- | --- | --- |
| `pytest tests/tools -q` | 7 passed | 0 |
| `pytest tests/tools tests/scheduling tests/delivery tests/memory -q` | 124 passed | 0 |
| `pytest tests -q -m "not integration and not resources"` | **1178 passed, 2 skipped, 3 deselected**(全量最终态) | 0 |

## 未验证项

- 真机微信全链(到期→iLink 出站→手机收到)：FakeSender 只验证链路逻辑，出站通道未实测。
- 提醒触发时账号恰好被 errcode=-14 暂停的场景行为：依赖 delivery 既有 retry/uncertain 路径，未针对该场景补测。

## 回滚

revert 本提交(WP-E,仅测试文件)与 b5a96e9(WP-D)即可；两包均无迁移、无数据 schema 变更，`confirm_writer`/`make_session_target_provider` 为附加参数/附加工厂，回退后 bootstrap 不引用。
