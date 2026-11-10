# P6 记录:微信受理、追问、补充与回执(2026-11-10)

计划命令实测：`tests/channels/test_development_commands + test_durable_intake + contracts/test_wechat + tools/test_superagent_tools + tests/delivery` = **91 passed**(修复前)+ tools 新增 2 项后 5 passed(该文件)。

## 1. 逐项核查

| 验收项 | 状态 | 证据 |
|---|---|---|
| /开发 与自然语言入口同 service | **已有且验证** | 两条路径都进 `SuperagentService.create_task`(api.py:176 签名实测;命令族回归在 test_development_commands,工具在 test_superagent_tools) |
| 信息充分自动执行 / 不足追问 | **已有且验证** | test_question_protocol_enters_waiting_input_and_input_resumes(追问→waiting_input→补充回队) |
| /任务 /补充 /取消 /重试 归属与短号 | **已有且验证** | T5 短号解析限本人+幂等键=平台事件 ID;命令回归(test_development_commands 91 passed 内) |
| 渠道事件唯一范围 | **已查明(实测)** | `UNIQUE(platform, account_id, external_event_id)` + `ON CONFLICT DO NOTHING`(channels/repository.py:315-318);工具受理把服务端操作键写入同一 external_event_id 字段(api.py:193) |
| 模型工具重试操作键 | **已有且验证** | `_operation_key = sha256(requirement)[:16] + session`,注释明确"不接受模型传入的键"(superagent_tools.py:86-90);同会话同需求幂等(含换标题无效)测试通过 |
| 模型改写文本 / 服务重启 / 用户再次发起 | **本轮钉语义** | 新增 test_tool_paraphrase_boundary_and_restart_idempotency:同会话换措辞=新任务(现状语义,未复现确定性误判不变更);同库新 service 实例(重启)幂等保持。5 passed |
| 重复事件重投只受理一次;明确重复=新任务 | **已有且验证** | 事件层 ON CONFLICT + durable intake 回放测试(test_internal_failure_keeps_event_and_envelope_then_replays、poison→dead、stale_pending_after_restart) |
| 回执目标服务端来源+fail-closed | **已有且验证** | `_source_target_of` 仅信 ToolContext.source_ref(服务端晚绑定);非微信来源返回 None(仅面板可见,test_rejects_missing_identity_and_web_source_has_no_target);解绑同事务(delivery 账本测试头自述) |
| 发送不确定 uncertain 与对账 | **已有且验证** | wechat.py 网络超时/未分类异常→`uncertain`(不假称必达、不盲目重发);test_uncertain_is_not_auto_resent;"本地仅入队一次 vs 远端仅展示一次"的区分正是 uncertain 语义(计划口径达成) |
| 机器人/转发/引用消息受理规则 | **无缺口证据,保持现状** | channels 入站未见 bot 回声显式过滤分支(实测 grep);iLink 入站协议以用户消息为主(推断);未复现"转发/引用误触发 /开发"的确定性误判——按纪律不改语义,列入阶段 F 实单观察 |

## 2. 缺口处置

- 唯一新增=语义护栏测试(paraphrase/重启幂等),防止未来静默漂移;受理语义本身零变更(符合"先复现确定性误判再改")。
- 真实微信外发/断连重投：**环境阻塞**(需已授权测试微信号;当前渠道默认关闭)。续作条件:测试账号绑定授权后按阶段 F 场景 1/2 实单。
