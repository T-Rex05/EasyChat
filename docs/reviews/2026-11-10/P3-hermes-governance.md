# P3 记录:Hermes 来源、集成点与遗留导入追踪(2026-11-10)

## P3-1 来源记录(机器可验证)

`hermes-provenance.json`(由 `hermes_provenance.py` 生成,git 对象级比对,实测)：

| 层 | 值 | 证据 |
|---|---|---|
| 上游来源 | **未确认**(如实记录) | 基线 `1d41c2a` 复制自 AgentForge **脏工作区**(其 HEAD 23fdb99 仍有未提交的 backend/hermes/*.py 修改,实测 `git status`),复制时点无法绑定单一 commit |
| 复制基线 | 1,080 文件;与 AgentForge HEAD 差异=**恰好 5 个文件**(agent/conversation_loop、agent/result_finalizer、agent/tool_executor、model_tools、tools/delegate_tool);AgentForge 另有 120 文件未入复制(裁剪/后续新增,方向未核,记录为 in_forge_not_in_copy) | blob hash 全量比对 |
| EasyChat 产品补丁 | **0**(HEAD 与基线内核树完全一致,实测 count=0) | tree 比对 |
| 版本标识 | `hermes_cli.__version__="0.19.0"`,发布日期字段 2026.7.20(不可独立证明对应上游,计划 §0.1 判断仍成立) | 源码 |
| Python/平台 | 3.12.8 / win32(开发);CI ubuntu-latest py3.12;生产 docker(requirements-core+hermes) | 实测/文件 |
| 内核依赖组合 | `docker/requirements-hermes.txt` 15 项 pin(openai>=2.24<3、langchain-core>=1.4.9、tiktoken==0.12、loguru==0.7.0 等) | 文件实测 |
| 补丁集重放配方 | 检出 AgentForge@23fdb99 → 用 EasyChat@1d41c2a 的上述 5 文件覆盖 → 得等价基线(JSON 含全部 blob hash 可校验) | 推断自比对方法,标注:重放未实际演练 |

**治理结论(比方案预期更简)**：内核在产品侧零补丁、升级面收敛到 5 个复制期差异文件 + 120 个裁剪决策；“可重建相同候选产物”的 U1 通过标准在本地来源口径下成立(树哈希+配方),在**上游 commit 口径下不成立**——需产品决策候选上游(见 P3-5)。

## P3-2 集成点清单(adapter → 内核 API,源码实测;行为入口=对应测试)

| 内核 API | 消费位置 | 用途 | 行为验证入口 |
|---|---|---|---|
| `run_agent.AIAgent` | agent_factory.py:23 | 构造主 Agent(按请求+模型 profile,调用方缓存) | `tests/contracts/test_runtime.py`、`tests/superagent`(FakeRuntime 替身;真实内核冒烟待模型授权,列入未验证) |
| `hermes_state.SessionDB` | agent_factory | 会话持久化 | tests/assistant、tests/contracts |
| `agent.conversation_loop.run_conversation` | adapter.py | 运行主循环(5 文件补丁集内) | test_runtime、context_results 套件 |
| `tools.registry` | runtime/hermes/tools.py:60 | 项目工具注册/派发 | `tests/contracts/test_tool_context.py` |
| `tools.terminal_tool.register/clear_task_env_overrides` | adapter.py | 按 session 的 CWD/环境覆盖(编码工作区接缝) | tests/superagent/test_workspaces.py |
| `tools.approval.set/reset_hermes_interactive_context` | adapter.py | 无人值守审批 fail-closed 上下文 | tests/security、test_runtime 审批用例 |
| `tools.delegate_tool.interrupt_subagent` | adapter.py | 取消传播到子代理 | test_runtime cancel 用例(5 文件补丁集内) |
| `hermes_constants.parse_reasoning_effort` | agent_factory | 推理档位 | test_runtime |
| agent 实例 `raw_usage.api_calls` | usage_bridge.py | 用量累计关联(无 per-request 回调,文档口径) | tests/usage |

## P3-3 内核内 EasyChat 专用导入追踪(本轮结论)

1. **tool_results 接线(保留,属必要补丁集)**：`result_finalizer.py:33 from backend.context.tool_results.runtime import current_runtime`、`model_tools.py:1394 managed_results_active`(实测)。`backend/context/tool_results` 存在且被 tests/context_results 覆盖,两处在正常运行路径可达,是 5 文件复制期差异的核心内容。
2. **skill_manager_tool 历史遗留(待删除,先复现)**：18 处函数内惰性 import 指向 **4 个已从本产品移除的模块**(`backend.hermes_adapter`、`backend/permission`、`backend/db`、`backend/service`,实测均不存在)。模块级导入安全(惰性所以不炸);行为触发面=技能编辑/学习变异分支(`agent/display.py:756`、`learning_mutations.py:103/165` 及 gateway/hermes_cli 引用,后者 EasyChat 不使用)。当前 1,140 项测试无一触发这些函数 → 触发即 `ModuleNotFoundError` 的死路径候选。**处置**:不删(需先在技能编辑路径复现行为确认无调用方依赖,计划“先复现后决定”);登记为遗留删除清单首项。
3. 其余内核文件无 `backend.*` 产品导入(实测扫描仅上述 2 文件+skill_manager)。

## P3-4 架构约束核查:已有且验证通过

`tests/architecture/test_imports.py`：唯一允许 import 内核的位置 `HERMES_ADAPTER_DIRS=("runtime/hermes",)`;业务目录全量适用;豁免名单**双向校验**(豁免项必须确有违规、未登记违规必须失败,源码 :193)——防漂移机制已内建,无需增补。全量套件通过即回归证据(实测 1140 passed)。全仓扫描确认内核 API 字符串(`from agent.`/`from tools.`/`import hermes_`)只出现在 backend/hermes 自身与 runtime/hermes(实测)。

## P3-5 候选升级演练:**设计/环境阻塞**

阻塞原因：上游 commit 未确认(P3-1),无固定候选版本可演练;且 AgentForge 工作区仍在演进(其 HEAD 与复制基线已分叉 125 文件)。续作条件:产品决策其一——①绑定候选上游 Hermes 版本(需确认内核谱系对应 NousResearch hermes-agent 哪个 tag);②或宣布“本地树即权威”,升级=按需挑选上游 diff 做行为试验。演练配方与哈希校验点已在 provenance 就位。

## 未验证项汇总(P3)

- 真实内核(非 Fake)模型冒烟:待模型密钥/预算授权。
- 120 个 in_forge_not_in_copy 的方向(导入时裁剪 vs 复制后 AgentForge 新增):未核,不影响本地重建口径。
- 补丁重放配方:静态可验证,未实际跑一遍隔离重建(低成本可续作)。
