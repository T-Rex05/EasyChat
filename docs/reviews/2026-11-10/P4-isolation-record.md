# P4 记录:执行隔离、取消、进程回收与预算(2026-11-10)

按包纪律:核查已有 → 复现缺口 → 最小修复 → 定向回归 → 评审 → 记录。

## 1. 已有行为核查(逐项状态与证据)

| 验收项 | 状态 | 证据 |
|---|---|---|
| session/run/工作区/缓存隔离(两用户/同用户两任务/重试) | **已有且验证通过** | test_cache_key_isolates_owner_model_policy_skills、test_cross_user_access_rules、test_workspace_key_is_hosted_per_repo_and_task、test_push_failure_then_retry_reconciles_pr、test_notification_dedup_across_attempts(tests/superagent,73 passed 本轮实测) |
| 取消-排队/编码中/push 后竞态/晚到结果/重启恢复 | **已有且验证通过** | test_worker_disabled_gate_and_queued_cancel、test_cancel_during_coding_lands_cancelled_without_pr、test_cancel_after_push_records_race_and_finishes、test_claim_creates_attempt_and_late_result_is_rejected、test_startup_recovery_marks_interrupted |
| 工作区根逃逸防护(符号链接/相对路径) | **已有且验证通过**(限服务生成路径) | workspaces.py:37-41 resolve 后校验;test_workspace_path_rejects_escape(参数化)、test_workspace_key_rejects_bad_task_id |
| git 命令超时与进程树回收 | **win32 已有实证;POSIX 缺口本轮修复** | 见 §2/§3 |
| 预算:attempt 墙钟 4h(runner.py:28 RUN_TIMEOUT_SECONDS)、git 每命令 timeout、验证条数 MAX_VERIFY_COMMANDS | **已有** | worker.py:292-297 wait_for+超时消息;本轮新增集成级实测(§4) |
| 预算:模型调用/token 硬上限 | **不存在,口径如实** | usage_bridge 仅记账(内核无 per-request 回调,源码自述);重试由人工 /retry 触发无次数帽(语义保持,登记设计待决) |

## 2. 越界探测——实际可访问范围报告(计划 P4 第 2 条交付物)

**结论(实测源码 + 行为推断标注)**:编码会话的**实际可访问范围 = 同 OS 用户全文件系统**。依据链:

1. `allowed_tools` 默认 `{terminal, file, web}`(runner.py:66,实测);
2. 工作区锚定是 **CWD-only**:`register_task_env_overrides(session_id, {"cwd": ...})`(adapter.py:105-117,文档自述"共享 default 容器,不触发沙箱隔离",实测);
3. 内核本地后端 = `_LocalEnvironment(cwd, timeout)`(terminal_tool.py:1518),命令以调用者 OS 权限执行;
4. 因此绝对路径/相对跳转可读取 `data/app.db`、`~/.dsh` 凭据文件、源码树等——**读类越界不受任何运行时防护约束**(推断,基于 1-3 的源码事实;真实内核会话中的端到端探测需模型授权,列入未验证);
5. 唯一运行时守卫 = tirith + 危险命令执行前 guard(无人值守 fail-closed,CLAUDE.md 硬约束 4):拦截破坏性/外发型"危险"命令,**不拦截普通读操作**——不能把该守卫宣称为数据隔离。

**处置**:OS 级隔离(独立执行进程/容器)按计划 P4 第 3 条属**设计待决**,本轮不擅自实施(部署语义变化+AGENTS.md 受保护路径人工闸)。设计输入已就绪:可信输入(run_id、workspace、allowed_tools、预算)、失联/退出/回收语义(现有 CAS attempt 拒绝晚到回写可复用)、三个候选形态——①内核已有 `env_type=docker` 后端(需 Docker Desktop,改动最小);②独立非特权 OS 账号;③WSL 专用发行版。选型需人拍板(成本/运维/开发机差异)。

## 3. 确认缺口与最小修复(本轮唯一代码改动)

**缺口**:POSIX 分支 `_terminate_tree` 仅 `process.terminate()`——只杀 git 直接子进程,派生的孙进程(credential helper 等)残留。win32 分支 taskkill /T /F 本已覆盖树。

**修复**(worker.py,两处最小改动):
1. `_run_git` 起进程在 POSIX 加 `start_new_session=True`(子进程即组长);
2. `_terminate_tree` POSIX 分支:组长→`os.killpg(pgid, SIGTERM)` 组信号覆盖孙进程;**非组长退回单进程 terminate,绝不波及外部进程组**(防护:同文件其他调用方/测试直接 spawn 的情形)。

**新回归** `tests/superagent/test_git_process_tree.py`:
- 真实进程 + marker 副作用法证"停止证据"(回收后 30s 晚写 marker 不出现):win32 分支本轮实测通过;POSIX 分支将在 CI(ubuntu)以同一测试真实执行(待首轮 CI 结果确认,标注);
- `_run_git` 对 RFC5737 不可达地址超时挂起 → 1s 内"已终止"抛错:<5s 实测通过(标记 integration,维护全集默认排除,显式运行验证过)。

**评审要点**:killpg 参数直接用 pid(组长 pgid==pid 已由分支前置条件保证);信号值 15 以常量+注释表达,避免 Windows 侧 `import signal` 兼容噪声;异常路径保留原 logger。回滚=revert 本笔(Windows 行为完全不变)。

## 4. 验证记录(实测)

```
python -m pytest tests/superagent/test_git_process_tree.py -q           → 2 passed(含显式 integration)
python -m pytest tests/contracts/test_runtime.py tests/contracts/test_tool_context.py
       tests/superagent/test_workspaces.py tests/superagent/test_credentials.py -q → 49 passed(修复前后一致)
python -m pytest tests/superagent tests/contracts/test_runtime.py -q -m "not ..."  → 73 passed, 1 deselected
```

## 5. 未验证项与续作条件

- 真实内核长工具调用的中断(SIGINT 传播到 AIAgent 线程)需真实模型+运行环境:续作条件=模型密钥与测试预算授权(计划 P9 阶段 F)。
- POSIX killpg 的真实 CI 执行:续作条件=推送后 Actions 首轮结果(P1 已入库工作流)。
- 独立执行环境选型:设计待决,见 §2 处置。
- token 硬预算:内核无 per-request 回调,当前口径=墙钟+事件上限+验证条数;替代方案(用量超限停止认领新任务)待产品确认是否引入。
