# P5 记录:任务恢复、验证与 Draft PR 发布(2026-11-10)

## 1. 操作矩阵(源码实测,contracts.py:18-27 + api.py:296-344)

状态:`queued / running / waiting_input / blocked / failed / cancelled / succeeded / awaiting_review / interrupted / cancel_requested`

| 操作 | 前置(有效 from) | 语义与保护 | 现有回归 |
|---|---|---|---|
| 受理(create_task) | enabled+repo 可解析+superagent.create | 快照仓库/token 存在性;幂等键=来源事件 | test_create_task_snapshots_repo_and_is_idempotent、test_settings_change_after_creation_does_not_affect_accepted_task |
| 认领(claim) | queued | queued→running+建 attempt **同事务**(BEGIN IMMEDIATE);并发第二认领空转;session=`sagexec_{task}_{n}` 按 attempt 单调 | **本轮新增** test_concurrent_claim_single_owner_and_retry_session_monotonic(21 passed) |
| 追问→补充 | running→waiting_input(协议前缀);waiting_input→queued | 输入归属校验(短号限本人);REACTIVABLE={waiting_input,blocked,failed} | test_question_protocol_enters_waiting_input_and_input_resumes |
| 取消 | 非终态且非 cancel_requested | 执行前:直接 cancelled;运行中:CAS→cancel_requested→协作中断(中断失败 worker 兜底);push 后到达:记录 cancelled_after_publication+按远端事实完成 | test_cancel_during_coding_lands_cancelled_without_pr、test_cancel_after_push_records_race_and_finishes、test_worker_disabled_gate_and_queued_cancel |
| 重试 | failed/blocked/interrupted/cancelled 且**非 legacy 无快照** | legacy 明确拒绝提示重新提交;requeue CAS;重试=新 attempt 新 session,发布边界先对账 | test_legacy_task_without_snapshot_cannot_retry、test_push_failure_then_retry_reconciles_pr |
| 发布 | 见 checkpoint 链 | push_intent→pushed(remote_head_sha)→pr_intent→pr_created(先查后建复用);每边界 `_assert_live` 重验 attempt 归属+取消+权限 | test_permission_revoked_blocks_execution、test_worker_runs_task_and_creates_draft_pr、(复用 PR)reconciled 事件断言 |
| 启动恢复 | running 遗留 | 标 interrupted(可重试,先对账) | test_startup_recovery_marks_interrupted |

checkpoint 链:`prepared→coded→verified→push_intent→pushed→pr_intent→pr_created→notified`(worker.py:13 自述+常量实测)。

## 2. 故障注入验收(已有实现的实测覆盖)

| 注入场景(计划 P5) | 现状 | 证据 |
|---|---|---|
| push 成功后崩溃(PR 未建) | 重试走 diff base...HEAD 非空→push 幂等→PR 新建 | test_push_failure_then_retry_reconciles_pr 前半段(push 失败)+head 复用假件 |
| PR 创建成功但**响应丢失** | `find_pr_for_head` 先查后建→复用 ghost PR,created==[] | 同名测试(reconciled 事件断言,实测) |
| 结果保存后回执失败 | 通知入 delivery 账本,dedup 键=task/attempt/report/target,**只重试投递不重跑编码** | test_notification_dedup_across_attempts |
| 取消/发布竞态 | cancelled_after_publication 事件+回执文案说明远端事实 | test_cancel_after_push_records_race_and_finishes |
| 旧 attempt 晚到覆盖 | active_attempt_id CAS 拒绝 | test_claim_creates_attempt_and_late_result_is_rejected |
| 双 worker 认领 | 单事务认领,第二个 None | **本轮新增回归** |

## 3. 验证证据与 SHA 绑定(核查结论)

- 提交序列:verify 在 coded 后、控制端统一 commit 前执行;**verify 与 publish 之间代理不再写树**,内容一致性由时序保持(实测 worker.py:334-342→426-434);终态记录 `head_sha`(控制 commit 后 rev-parse,即最终发布 SHA)+`verification_ref`(工件目录)。
- **改进项(非缺陷,登记)**:验证工件未戳 tree hash,若未来放开 verify 与 publish 之间的任何写树操作(如自动修复轮)需先补该绑定——列入 P7 自动修复的前置检查。
- PR 描述含需求/代理摘要/验证(未配置时显式 ⚠️ 未验证)/任务-attempt-分支-`head[:12]`/`EasyChat-Superagent-Task` 对账标记/_「Draft,合并由维护者决定」(实测 `_pr_body`);满足"描述关联验收结果、最终 SHA、缺失证据与人工待决"要求。**高风险升级简报**语义属 DSH 分层系统职责,EasyChat 侧对应物=未配置验证时的显式警示+blocked 原因事件,已具备。
- 用户可编辑仓库内容不提升发布权限:token/base/branch 全部来自 settings 快照与控制端 plan 构造,agent 无渠道改远端配置(推断自 `_wire`/plan 数据流;真实端到端待 P9 实单)。旧任务遗留 remote 含凭证的清洗有回归(test_worker_sanitizes_legacy_workspace_remotes)。

## 4. 缺口处置与状态

- 本轮唯一新增:双认领并发回归(安全区测试)。其余 P5 验收项**全部已有且验证通过**(73+21+2 实测)。
- 未验证(环境阻塞,续作条件同 P4 §5):真实远端(非假件)的 push/PR 对账、真模型长任务、webhook 真实投递(P7)。
