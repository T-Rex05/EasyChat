# TaskState 同步工具证据

启用现有 rules 结果管理后，每个结果都会先保存原文和最终模型视图，再同步其关键字段证据。
不会为此调用任何模型；原有语义TaskState的目标/下一步维护机制继续独立工作。

## 状态组成

TaskStateMaintainer.get_task_snapshot(scope, semantic_state=...)返回两部分：

- semantic_state：宿主显式提供的已认证根会话语义快照。不会根据未认证的thread字符串
  读取旧缓存；子Agent只使用自己的_subagent_goal，不继承根任务的私有参数。
- tool_evidence：按user/thread/logical-agent隔离的确定性证据账本。每条包含工具名、
  call/attempt、时间、artifact ID、source hash、view ID、原文完整性、有效期、
  JSON Pointer/行定位及精确值。

证据不写入key_params，异步语义更新、话题重置、陈旧结果都不能覆盖它。多个来源观察到
同名不同值时同时保留并给出multiple_observed_values，表示需要核验，不自动判定矛盾或
选择“最后完成的值”。执行失败的错误/状态字段也作为观测保存，不推断操作成功。

完整证据从原始捕获内容中提取，不局限于模型视图中放得下的字段。单字段超过4KiB或
记录字段总量超过12KiB时不截断精确值，而是省略并计数；仍有原文引用可供恢复。
扫描达到结构/字段上限时标记extraction_partial。

## 并行与提交

Hermes完整工具batch开始时读取固定快照，整个batch内读取同一证据版本。各完成事件按
tool_call_id暂存，结束时按照原调用顺序在一个SQLite事务中提交，版本只增加一次。
子Agent有独立runtime/batch/作用域，不能修改根或兄弟Agent的账本。
scope包含逻辑Agent身份；物理session轮换不改变隔离键。重启后根会话证据可恢复；
子Agent要延续原逻辑身份必须由宿主恢复该身份，创建新child默认无旧child访问权限。

相同batch重复完成幂等，保留最近128个batch标识；保留记录的run/call/attempt也用于去重。
不承诺无限历史事件的全局exactly-once。恢复工具不产生新的业务证据。
提交失败保留业务执行结果，不重跑工具，snapshot暴露evidence_sync_error。

## 模型可见性

下一次API请求构建前，附加最长4000字符的assistant数据投影，明确标记
untrusted_task_evidence。内容不提升为system/user指令；精确字段值不在投影中静默截短。
省略记录/字段会计数，原文引用仍然保留。调用/结果未配对完成时不插入。
相同投影不重复追加，也不改写已经封存的tool消息。投影通过现有会话flush保存。
这是同步状态注入，不是判断模型、语义摘要或主动历史折叠。

2026-11-03 增加 `AGENTFORGE_TASK_STATE_PROJECTION=full|delta|off`，默认full。
off仅关闭模型投影，账本提交、隔离和原文恢复不变。delta只在当前保留的同作用域
history中存在full锚点和连续base_version链时跳过完整投影过的观测；省略字段的记录
不能算完整发送。丢锚/损坏链、版本回退或账本代次改变时回到full，精确值仍不截短。
源过期、淘汰数量和同步错误变化可以产生新投影。

账本JSON增加generation，clear后重建产生新代次，避免版本号复用串接旧history。
旧分区首次后续写入时补代次，不需要SQL表迁移。full原内容格式保持，代次只在delta
策略投影中出现；所有模式使用相同证据维护逻辑。

`conservative-v1` 的other_fields只属于当前结果视图，不自动进入protected证据账本。
它们没有经过语义相关性或正确性判断，不能因被额外保留就当作任务结论。

## 存储与清理

task-evidence.sqlite3位于现有私有原文目录，沿用该目录的访问边界。
每个user/thread/agent默认最多64条结果、64KiB记录、24小时证据TTL；
整个账本最多500个活跃分区。批次标识也有数量上限。
原文失效时保留source_expired标志，不把历史观测当作仍可恢复的原文。

EvidenceLedger.clear(scope)只清指定逻辑Agent分区。现有不带租户信息的语义clear(thread_id)
不会隐式删除其他Agent/用户的证据；会话删除流程的证据立即级联清理尚未接入，
目前通过上述TTL/配额回收。共享原文grant不会隐式共享TaskState。

验证覆盖并行批次、根/子/兄弟隔离、冲突、事务回滚、重复事件、重启、TTL、
超限、恶意字段文本、异步语义重置及投影去重；均使用临时数据库和假工具。
