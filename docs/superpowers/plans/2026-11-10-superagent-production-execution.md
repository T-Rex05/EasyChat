# EasyChat 架构选型与整改执行方案

> 执行模型逐项采用 `executing-plans` 工作流，有该技能时先读取。使用下列复选框跟踪交付。受保护路径遵循仓库 `AGENTS.md` 的草稿与人工续作规则。（交接约定）

**目标**　在现有 Hermes 执行链上完成可验证的权限修复、微信明确任务到 Draft PR、升级治理与故障恢复，形成后续引擎复评依据。（方案）

**架构**　EasyChat 管理身份、授权、任务、记忆、验证、发布和投递，引擎通过既有 ExecutionRuntime 与 CodingRunner 接口接入。近期生产路线沿用 Hermes，Harness 进入隔离选型试验。（拟定设计）

**技术栈**　当前后端采用 Python、SQLite 和 Hermes，前端采用 Vue/Vite，验证使用 pytest 与前端现有测试脚本。（源码核查，`CLAUDE.md`、`agent_frontend/package.json`）

**文档状态**　本文件是执行与验收计划，复选框未完成项须由执行模型重新核查后推进。既有测试记录保留日期与覆盖范围，作为历史证据。（交接约定）

## 架构选型结论与适用前提

用户允许改变执行内核，优先考虑以后更新迭代。本版建议近期沿用 Hermes，优先治理嵌入源码与上游的差异，再用隔离试验决定是否引入 Harness。保留 Hermes 是本次评估建议，可依据试验结果复评。（用户最新要求与方案）

此前从独立 DSH/pstack RUNBOOK 直接推导产品迁移方案，遗漏了 EasyChat 已有的 Hermes 与 superagent 执行链。本版结合两份上游代码和本地代码重新评估。（评估范围更正）

当前 bootstrap 构造 HermesRuntimeAdapter 并把 runtime 注入 SuperagentWorker，ExecutionRuntime 是业务层唯一执行接缝。整改在现有接缝和模块内推进。（源码核查，backend/bootstrap.py、backend/runtime/contracts.py）

目标链路如下，普通助手与后台编码共用 Hermes 适配能力，拥有各自的任务生命周期和资源预算。（方案）

```text
微信 / Web
  → channels 身份绑定、消息持久化与去重
  → 普通对话由 assistant 调度到 HermesRuntimeAdapter
  → 明确编码请求由 superagent service 受理
      → tasks / attempts / inputs / reports
      → SuperagentWorker
      → CodingRunner → HermesRuntimeAdapter → Hermes
      → 验证 → Git 分支 → Draft PR
  → delivery 账本 → 原微信会话回执
```

superagent 的任务编排、权限、验证与 PR 发布属于 EasyChat 业务层，Hermes 提供模型推理和工具执行。上游研究原型的任务/恢复设计可以借鉴，执行链按本项目代码实现。（方案及源码核查）

当前生产整改按下述推荐路线推进。已有 DSH/pstack 独立运行，后续接入须先经过选型试验与设计评审。（方案）

## 0. 选型依据与升级治理

### 0.1 已核查事实

- 本地 `backend/hermes` 有 1,080 个受 Git 跟踪的文件，其路径历史从 EasyChat 源码基线提交 `1d41c2a` 开始。本地 CLI 标识为 `0.19.0`，发布日期字段为 `2026.7.20`，这些字段无法独立证明对应上游的精确 commit。（本轮源码与 Git 核查，`backend/hermes/hermes_cli/__init__.py`）
- 适配层直接调用 `AIAgent`、`SessionDB`、工具 registry 和 terminal 环境覆盖，并读取实例用量属性。版本变化会触及这些集成点，需用实际内核验证。（源码核查及推断，`backend/runtime/hermes/agent_factory.py`、`adapter.py`、`tools.py`、`usage_bridge.py`）
- 嵌入内核中存在 EasyChat 专用导入，例如 `model_tools.py`、`agent/result_finalizer.py` 依赖 `backend.context.tool_results`，`tools/skill_manager_tool.py` 中仍存在旧权限和服务导入。导入存在可由静态搜索确认，是否可达、是否损坏必须另做行为核查。（源码核查，`backend/hermes`）
- 当前 `ExecutionRuntime` 提供 `execute/cancel/aclose`，`CodingRunner` 提供编码任务入口。现有 worker 已拥有验证、发布检查点和 PR 对账，可围绕既有接口开展替换试验。（源码核查，`backend/runtime/contracts.py`、`backend/modules/superagent/runner.py`、`worker.py`）
- DSH Superagent 上游自述为研究原型，当前提供 GitHub 和可选飞书接入，其执行器使用 Harness Session。接入微信需要新增适配与验证。（上游文档与源码核查）[README](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/README.md)、[执行器源码](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/src/executor/dsh.ts)
- 原型的 `package.json` 依赖多项 `0.2.1-alpha.2` Harness 包，部署文档提供升级流程，并说明新版本迁移的数据库需依靠升级前备份回滚。其插件分发有利于减少直接修改 Harness 的需求，但仍要验证原型、插件与 Harness 的组合兼容。（上游核查及推断）[依赖清单](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/package.json)、[部署与升级](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/006-deployment.md)
- Hermes 官方提供独立安装的更新流程。EasyChat 当前使用嵌入源码和自有依赖清单，不能据此推断执行官方更新命令即可升级本项目。（上游说明与本地结构推断）[官方更新文档](https://hermes-agent.nousresearch.com/docs/getting-started/updating)

### 0.2 三条路线

下表是根据源码结构与当前需求作出的工程判断，尚无同模型、同任务的两引擎实测。（推断）

| 路线 | 后续升级影响 | 现有业务适配 | 适用判断 |
|---|---|---|---|
| Hermes 加升级治理，按需求吸收任务编排设计 | 需管理内核补丁与内部接口，但可逐步将变动集中于 adapter | 复用已有微信、身份、记忆、任务与发布链 | 当前推荐，改动范围最集中 |
| Hermes 普通聊天加 Harness 编码执行 | 两套运行环境与适配要验证，可独立升级编码执行 | 可保留 EasyChat 任务账本，新增 runner 适配 | 适合隔离试验，须证明收益足以覆盖维护成本 |
| 全面改用 Harness 与 DSH Superagent 编排 | 将同时跟踪 Harness、原型与微信插件，迁移两套状态与权限语义 | 涉及会话、工具身份、记忆、权限、任务、回执和 UI 的重新验收 | 当前证据不足，未来产品目标转向团队仓库协作时复评 |

Harness 的插件架构提供扩展方向，其官方页面当前标为 public preview。全量迁移的长期收益需要通过本项目适配试验确认。（上游说明及推断）[Harness 官方说明](https://www.deepseek.com/en/harness/)

### 0.3 近期执行包 U1 记录可重复基线

1. 记录当前产品 commit、内核文件哈希、Python 与运行平台、依赖解析版本。核实上游 commit，找不到精确来源时记录“未确认”，保留当前完整基线。（方案）
2. 对照候选上游版本提取本地差异，区分产品必要扩展、客观缺陷修复和历史遗留导入。每项记录调用入口、行为证据和负责的测试。（方案）
3. 审核可达后逐项删除遗留路径，将可外置的扩展移到 Hermes adapter 或上游支持的 hook。无法外置的必要补丁保留可重放 patch 和原因，避免一次清空全部内核改动。（方案）
4. 发布记录固定内核 commit、补丁集哈希和依赖组合。升级在隔离检出中完成候选构建、回归、真实模型冒烟，再由应用发布替换整套产物。（方案）

U1 通过标准是从记录的基线与补丁可重建相同候选产物，所有必要集成点均有行为验证入口。运行中实例不自动跟随 upstream main。（方案）

### 0.4 近期执行包 U2 明确状态与升级责任

- EasyChat 负责 owner 身份、能力检查、渠道绑定、业务记忆、任务状态、验证与 Draft PR 发布和回执。引擎接收已授权的请求与工具集合，执行细节由 adapter 管理。（拟定设计，沿用现有模块）
- 产品任务标识与引擎会话标识分开记录，页面使用产品状态。核查已有映射后仅补缺口，避免引擎版本字段扩散到业务模块。（方案）
- 同进程 Hermes 适配仍使用进程级环境与全局工具注册，独立会话不能证明系统级隔离。编码任务的进程、文件、凭据和终止能力需分别验证，必要时先为现有 Hermes runner 增加独立执行进程。（源码核查及方案，`backend/runtime/hermes/paths.py`、`tools.py`）
- 独立进程解决崩溃和环境生命周期问题，OS 账号、容器权限与挂载才承担相应资源访问控制。若引入独立执行进程，应一并设计失联、取消和晚到结果处理。（方案）
- 每次内核升级先跑既有 runtime、ToolContext、微信与 superagent 契约回归，再使用实际内核验证工具限制、会话恢复、取消、计量和一次低风险编码任务。以 StubAgent 为主的契约测试只能覆盖其模拟行为。（测试代码核查与方案，`tests/contracts/test_runtime.py`）

### 0.5 试验包 U3 用实际任务决定是否引入 Harness

1. 锁定两边引擎、依赖、模型、推理档位、仓库基线和运行预算，准备覆盖 UI 修改、后端缺陷、测试修复、长任务与人工追问的同一任务集。将权限越界、取消、断网、重启与重复输入作为额外故障场景。（方案）
2. 先离线检查 Harness 可用的会话控制接口和身份传递方式。确有可用接口后，在隔离原型中适配现有 `CodingRunner`，复用 EasyChat 控制侧验证和发布，初次试验仅产出工作区与差异。（方案）
3. 若采用完整 DSH Superagent，单独设计任务状态、权限、发布和回执的唯一写入方，以及故障对账方式，再进入集成试验。原型自带的编排与 EasyChat worker 同时驱动一个任务会带来重复副作用风险。（方案及推断）
4. 每类任务至少重复两次，记录测试通过率、独立评审缺陷、恢复结果、耗时、用量和适配改动。小样本只作筛选，候选通过后再增加重复与升级演练。（方案）
5. 必须通过身份隔离、禁止工具、取消、重启和重复 PR 检查，业务验收不得退步。随后再比较维护人时、任务质量与运行成本，只有收益明确且可以回滚时才提出生产切换。（方案）
6. 候选通过试验后，固定受信任仓库的低风险任务试运行，记录每个任务的引擎版本且任务中途不切换。切回旧 runner 前停止接收新任务，并对账在途运行与外部副作用。（方案）

本轮完成静态比较与上游资料核查，尚未运行 Hermes 与 Harness 的同条件性能或成本对比，未据此判断哪一方编码成功率更高。（验证范围）

本轮执行 `python -m pytest tests/contracts/test_runtime.py tests/superagent -q`，结果为 `72 passed in 42.25s`，覆盖当前 runtime 契约与 superagent 离线回归。该结果作为当前实现的局部基线。（2026-11-10 实测）

## 1. 分阶段交付

下表为拟实施工作，每阶段根据当前代码验证已有能力，只有确认存在缺口时才修改。（方案）

| 阶段 | 交付 | 完成标准 |
|---|---|---|
| A 基线与发布门禁 | 代码/数据快照、GitHub main 规则、CI 接线 | 可恢复且未经人工评审的改动不能合并 |
| B 已确认权限缺陷 | 四项后端补丁与两项前端修复 | 定向回归、维护全集及独立评审通过 |
| C Hermes 编码执行 | 会话/工作区隔离、取消、预算、执行边界 | 普通聊天与编码互不污染，越界和超时受控 |
| D 微信任务闭环 | 提交、补充、查询、取消、重试和回执 | 重复/断连/重启不产生重复执行和 PR |
| E 前端与运维 | 准确能力与状态、部署版本、可观测与恢复 | 页面、接口、worker 状态一致 |
| F 实单验收 | 真实微信到 Hermes 到 Draft PR | 低风险实单成功，高风险实单按规则停草稿 |

## 2. 阶段 A 基线、CI 与仓库门禁

### A1 固定可恢复基线

- [ ] 记录 EasyChat 分支、HEAD、工作区修改、部署版本和当前活跃编码任务。保留已完成的前端修复及 docs/reviews/2026-11-10 产物。（方案）
- [ ] 使用现有 backup.py 的 create_backup/verify_backup 备份 app.db 和受其管理的文件，对 Hermes 会话库、superagent 工作区和 Git refs 单独核对恢复范围。使用 SQLite 一致性快照，避免复制正在写入的数据库文件。（方案，依据 backend/platform/backup.py）
- [ ] 做一次隔离恢复，确认历史会话、任务、报告和文件可读取，记录备份 hash。（验收要求）

### A2 GitHub main 规则

此前核验 main.protected=false、有效规则为空，执行时先重新读取再配置。（既有实测，REVIEW-2026-11-10.md）

- [ ] 拥有者配置 active ruleset，要求 PR、人工审批、必需 CI、解决对话，开启陈旧审批失效，禁止删除和非快进推送，agent 不进入 bypass。（方案）
- [ ] 为 AGENTS.md 的保护路径及 .github/** 建立 CODEOWNERS，启用相应审核要求。测试 PR 的作者与人工审批人满足规则约束。（方案）
- [ ] required checks 使用实际产生的稳定 job 名称和预期 App 来源，先让新检查运行成功再纳入必需列表。（方案）
- [ ] 修改 .github/workflows/ci.yml，在前端 type-check/build 前运行 npm test，将权限边界、Hermes 适配与 superagent 回归纳入现有测试流程。（方案）
- [ ] 验证无审批、CI 失败、新 head 使旧审批失效时均无法合并，破坏性推送试验使用一次性测试仓库。（验收要求）

```bash
gh api repos/T-Rex05/EasyChat/branches/main
gh api repos/T-Rex05/EasyChat/rules/branches/main
```

GitHub 的必需审批、状态检查与陈旧审批规则以当前官方配置及真实 PR 状态为准。[GitHub 规则说明](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)

## 3. 阶段 B 已确认权限修复

### B1 后端四项草稿

- [ ] 人工评审 docs/reviews/2026-11-10/escalation-brief.md 与 access-fixes.draft.patch，按 AGENTS.md 记录受保护路径续作许可。（仓库约束及方案）
- [ ] 核验基线指纹，在隔离分支应用补丁，将新增行为回归整理进入 tests/access/。（方案）
- [ ] 最后拥有者的检查与降权/禁用在同一短写事务内完成，两个并发操作后至少保留一位活动拥有者。（验收要求）
- [ ] 角色改名与 users.role 引用原子同步，名称冲突时整体回滚。（验收要求）
- [ ] 未注册权限不进入有效权限，撤销优先，历史记录保留供审计。（验收要求）
- [ ] memory capability 对应实际 service 检查，已有部分授权不会被扩大。（验收要求）

```powershell
python docs/reviews/2026-11-10/replay_access_draft.py --apply-draft --existing-tests
git apply --check docs/reviews/2026-11-10/access-fixes.draft.patch
```

此前隔离补丁验证为 62 passed，执行时重新验证指纹和实际输出。（既有实测，draft-green.txt）

### B2 前端与委派决策

- [ ] 纳入 RoleEditDialog.vue 与 role-modes.test.mjs 的既有修复，验证完整账单模式识别、缺依赖保持 custom、降档保留共享文件授权。（方案，已有行为回归）
- [ ] 委派上限单独形成授权矩阵。建议普通管理员受显式委派上限约束，拥有者身份及高风险能力由拥有者控制，经确认后再实施。（拟定产品决策）
- [ ] 后端修复、权限模型新设计和普通前端修复分别提交，按风险独立评审和回滚。（方案）

## 4. 阶段 C 完善 Hermes 编码执行

当前 worker 已实现 attempt、分阶段执行、验证和发布对账，本阶段先对照回归确认，避免重复实现已完成部分。（源码核查，backend/modules/superagent/worker.py）

### C1 保持唯一执行接缝

- [ ] 继续通过 backend/runtime/contracts.py 的 ExecutionRuntime 调用 Hermes，业务模块只依赖该接缝。（仓库约束）
- [ ] 在 superagent/CodingRunner 与 runtime/hermes/adapter.py 之间明确会话工作区、工具集、模型配置版本、取消、超时及事件的契约。（方案）
- [ ] 核验普通聊天与编码任务使用独立 session/run，Agent 缓存按 owner、session、模型版本、权限和工具策略区分。（验收要求）
- [ ] 限制编码任务对聊天响应资源的占用，先保留当前真实串行编码，再按测量结果考虑并发。（方案）

### C2 工作区与凭据

- [ ] 每任务独立工作区与分支，attempt 重试保留任务工作区和检查点，根目录之外的路径明确拒绝。（方案）
- [ ] Git 代理与认证通过任务局部配置或受控 wrapper 注入，remote URL、argv、日志和工件中不含凭据。（方案）
- [ ] 明确 runtime 的 cwd 绑定和 OS 隔离之间的边界。采用独立非特权执行环境限制挂载、网络、CPU、内存、进程和磁盘，应用数据库、微信密钥与发布凭据由控制端持有。（方案）
- [ ] 对符号链接、绝对路径、后台进程、超时、跨任务访问和服务重启进行验证，取消确认进程树已停止。（验收要求）

### C3 发布门禁与恢复

- [ ] 验证最终 head SHA 对应的测试证据，缺验证条件与验证失败依仓库明确策略进入 blocked 或带缺失证据的 Draft，界面准确显示。（方案）
- [ ] 每个发布边界核验任务/attempt、当前权限与取消状态，已发出的动作通过远端查询对账。（方案）
- [ ] 注入 push 成功后崩溃、PR 创建后响应丢失、结果保存后回执失败，验证恢复复用分支/PR且只重试所需阶段。（验收要求）

该阶段修改 runtime/superagent/契约及部署时遵守 AGENTS.md 的受保护路径评审要求，执行内核继续使用 Hermes。（执行约束）

## 5. 阶段 D 微信任务闭环

### D1 沿用现有入口

- [ ] 复用 channels/commands.py 的确定性命令、backend/tools/business/superagent_tools.py 的自然语言入口和 superagent/api.py 的服务，所有编码请求进入同一任务受理流程。（方案）
- [ ] /开发、/任务、/补充、/取消、/重试 共用 Principal/ToolContext 身份，actor、仓库与回执目标由服务端来源解析。（方案）
- [ ] 需求不完整先追问，补充内容写 inputs，沿用原任务和分支，按既有 attempt/session 规则恢复任务上下文，任务指代不清时列出可选择的任务号。（方案，当前 repository 为不同 attempt 生成独立 session_id）

### D2 幂等与状态

- [ ] 渠道消息先持久化后推进游标，以稳定 source event ID 和受理操作键去重，事务内不执行外呼。（方案及仓库约束）
- [ ] tasks/attempts/inputs/reports 继续作为本项目编码任务账本，前端显示 queued、running、waiting_input、blocked、cancel_requested、awaiting_review 等准确状态。（方案）
- [ ] 回执进入现有 delivery 账本，关联原账号、会话和上下文，唯一键包含 task/attempt/report/target，发送失败不重新执行 Hermes 编码。（方案）
- [ ] 重复微信消息、重复工具调用、受理后断连、回信失败、两次重启和取消/发布竞态均不产生第二个逻辑任务或重复 PR。（验收要求）

### D3 GitHub 反馈

- [ ] 复用现有 superagent webhook 接口，核验签名、delivery ID 去重、仓库白名单和 PR/head 关联。（方案）
- [ ] CI 与评审意见转为本地 task input/report，后续仍由 Hermes 处理同一个任务，旧 SHA 反馈不能覆盖新状态。（方案）
- [ ] 自动修复轮数、token 和耗时有预算，批准与合并由人工完成，bot 不解除明确人工暂停。（方案及仓库约束）

## 6. 阶段 E 页面、部署和可观测

- [ ] 页面 capability、菜单/按钮和后端实际校验一致，展示执行阶段、验证证据、PR、回执状态和具体阻塞原因。（方案）
- [ ] 运维面板补充队列等待、编码耗时、Hermes 模型失败、token、验证失败与回信 uncertain，所有记录关联 task/attempt/run。（方案）
- [ ] 部署记录固定 EasyChat 源版本、Hermes 内嵌版本、策略 revision、前端构建与数据备份版本，并验证冷启动和恢复。（方案）
- [ ] 对已修改的 UI 按 AGENTS.md 保存同场景 Before/After。纯逻辑修复提供相同输入的行为对照，注明没有视觉改动。（验收要求）

## 7. 阶段 F 真实验收与回滚

使用测试仓库和明确标记的微信测试消息，逐项保存真实证据。（方案）

1. 微信明确发出文档修复请求，经现有 SuperagentWorker/CodingRunner/Hermes 执行，只创建一个 Draft PR并回到原会话。（验收要求）
2. 模糊请求先追问，微信补充后继续同一任务和分支。（验收要求）
3. UI 间距修复有同场景 Before/After，测试和构建对应最终 head。（验收要求）
4. 受保护权限任务按规则停草稿并生成升级简报，人工在原任务答复后才进入批准范围。（验收要求）
5. 取消、重复消息、模型失败、Git 超时、发布响应丢失与服务重启后，任务、PR和通知可对账。（验收要求）

回滚时先停止新编码派发并对账活跃任务，保留提交、工作区和回执账本，使用验证过的代码与一致性数据快照恢复。外部已创建 PR 不通过重跑任务处理。（回滚要求）

## 8. 独立开发工具的运维事项

DSH/pstack 的下列整改属于独立工具维护，可单独安排，不构成 EasyChat 使用 Hermes 的前置条件。（范围更正）

- 面板令牌轮换与危险 delivery 指令下发，执行前保存配置 revision，使用选择性 CAS 更新，保留未选字段。（方案）
- 将分散的一次性修复脚本归档，正式运维入口统一配置来源、差异预览、失败退出码和回滚记录。（方案）
- 如果继续运行该独立工具，将其 11 项运维回归纳入自己的版本管理与 CI，避免把该工具的 executor 状态误作 EasyChat Hermes 的运行状态。（方案及既有测试记录）
- 若独立工具继续启用 Gitee 同步，人工合并后的同步仅使用已确认分支快进，分叉时拒绝并记录原因。（独立工具验收要求）

## 9. 验证命令与交付

```powershell
python -m pytest tests/access tests/security -q -m "not integration and not resources"
python -m pytest tests/superagent tests/contracts -q
python -m pytest tests -q -m "not integration and not resources"
cd agent_frontend
npm test
npm run type-check
npm run build
```

每阶段交付代码差异、失败与通过用例、实际命令输出、评审结果、配置差异、备份与回滚，以及明确未验证项。历史测试数量仅作参考，以本轮实际验证为准。（交付要求）

## 10. 可独立验收的工作包

本节将 A–F 和 U1–U3 拆成可交付工作包。每包按“核查已有行为 → 复现具体缺口 → 最小修改 → 定向验证 → 评审 → 记录结果”推进，已满足验收的能力只记录证据。（执行约定）

### P0 接管与许可盘点

**输入文件**　`E:\PythonCode\EasyChat\AGENTS.md`、`CLAUDE.md`、`EASYCHAT_HANDOFF.md`、本计划、`docs/reviews/2026-11-10/escalation-brief.md`。（交接输入）

- [ ] 在当前 checkout 记录分支、HEAD、工作区差异和现有部署目标，逐一保留其他任务修改。需要隔离检出时使用环境提供的 worktree 管理工具。（步骤）
- [ ] 记录 protected paths 对应的现有人工许可范围，许可不足的工作包生成可评审草稿与升级简报，继续推进其余安全区任务。（步骤，依据 `AGENTS.md`）
- [ ] 为各包标注 `已有且验证通过 / 已有待验证 / 确认缺口 / 设计待决 / 人工或环境阻塞`，附源码、命令或决策依据。（步骤）
- [ ] 真实微信外发与 GitHub 产物测试记录授权测试账号、会话和仓库。缺少已授权目标或密钥时完成隔离验证并列出剩余实单验收。（步骤）

```powershell
Set-Location E:\PythonCode\EasyChat
git status --short
git branch --show-current
git rev-parse HEAD
git diff --stat
```

**交付**　一份接管记录，列出起点、待保留修改、工作包状态与许可范围。（验收要求）

### P1 基线、备份与 CI

**对应阶段**　A、U1。（任务映射）

**核查文件**　`E:\PythonCode\EasyChat\backend\platform\backup.py`、`.github\workflows\ci.yml`、`docker\requirements-hermes.txt`、`agent_frontend\package.json`。（文件范围）

- [ ] 先执行维护全集及前端检查，记录失败项的具体断言，区分本次改动与既有问题。（步骤）
- [ ] 使用现有一致性备份机制，在隔离目录演练恢复应用库、Hermes 会话库、文件引用和必要工作区。加密密钥通过既有受控渠道保存恢复能力，备份日志仅记录引用与校验结果。（步骤）
- [ ] 在 `frontend-build` 的 Install 步骤后加入下面的前端测试步骤，继续保留 type-check 与 build。（拟定 CI 修改）

```yaml
      - name: Frontend tests
        working-directory: agent_frontend
        run: npm test
```

- [ ] 从 GitHub 重新读取分支规则，以实际成功的 job 名配置 required checks。需要拥有者权限的配置输出可执行操作清单和读取证据，记录人工完成状态。（步骤）

**通过标准**　基线结果可复查，隔离恢复成功，前端测试进入 CI，规则验证覆盖未审批和失败检查两个场景。（验收要求）

### P2 权限草稿与模块化权限界面

**对应阶段**　B。（任务映射）

**核查文件**　`E:\PythonCode\EasyChat\backend\modules\access\api.py`、`repository.py`、`policy.py`、`agent_frontend\src\views\admin\RoleEditDialog.vue`、`RoleListPanel.vue`、`agent_frontend\src\utils\permissionGroups.ts`，以及 `docs\superpowers\plans\2026-11-09-permission-remediation.md`。（文件范围）

- [ ] 首先重放已有 access 草稿，在指纹不匹配时重新复现并生成针对当前源码的最小补丁。（步骤）
- [ ] 分别验收最后拥有者并发保护、角色改名成员同步、未知权限不生效、memory capability 与 service 校验一致。每项保留实际失败与通过证据。（步骤）
- [ ] 从注册权限逐项追踪 service、HTTP、微信命令、模型工具、菜单和按钮，确认旧键的实际使用与新功能覆盖。旧计划中的权限数量按当前注册表重新统计。（步骤）
- [ ] 普通界面按现有模块模式展示，原子权限进入高级配置。加载后未修改直接保存必须保持原有效权限，历史部分授权显示自定义，缺依赖时准确提示。（拟定界面行为）
- [ ] 降低某模块模式时保留其他模块仍使用的文件能力，回归 `agent_frontend/tests/role-modes.test.mjs` 中的既定行为。（步骤）
- [ ] 委派上限使用显式矩阵描述谁可授予哪些权限与数据范围。产品确认后再实施权限语义变化，将确定性缺陷修复与授权新设计分别交付。（步骤）

```powershell
python docs/reviews/2026-11-10/replay_access_draft.py
python docs/reviews/2026-11-10/replay_access_draft.py --apply-draft --existing-tests
python -m pytest tests/access tests/security tests/contracts/test_tool_context.py -q
```

**通过标准**　权限矩阵每行有入口和拒绝用例，角色保存保持原授权语义，拥有者保护通过并发回归，既有许可之外的修改保留草稿状态。（验收要求）

### P3 Hermes 来源、补丁与升级流程

**对应阶段**　U1、U2。（任务映射）

**核查文件**　`E:\PythonCode\EasyChat\backend\hermes\`、`backend\runtime\hermes\`、`docker\requirements-hermes.txt`、`tests\architecture\test_imports.py`、`tests\architecture\test_removed_dependencies.py`。（文件范围）

- [ ] 生成内核来源记录，包含本地基线 commit、可确认的 upstream commit、内核文件哈希、必要补丁清单、Python/平台和实际依赖版本。上游来源未确认时以本地源码基线作为重建依据。（步骤）
- [ ] 为 `AIAgent` 构造、SessionDB、registry、terminal overrides、审批、技能与用量桥接逐项列出依赖的接口及行为验证入口。（步骤）
- [ ] 对内核专用导入逐项追踪真实调用，先复现行为，再决定保留补丁、移动到 adapter 或删除遗留路径。采用上游 hook 前核实目标版本确实提供该接口。（步骤）
- [ ] 增补架构检查，约束新业务模块经既有 runtime 接口调用引擎。历史豁免逐项记录用途和退出条件，新增导入不能扩大豁免。（拟定检查）
- [ ] 在隔离检出中演练一次候选升级，固定上游版本、重放必要补丁、解析依赖、执行契约和真实内核冒烟，形成升级差异与回滚记录。（步骤）

**通过标准**　可重建当前版本，必要补丁均有归属和行为证据，升级失败保留原运行版本，应用库与引擎会话库的版本组合有记录。（验收要求）

### P4 编码执行隔离、取消与预算

**对应阶段**　C1、C2。（任务映射）

**核查文件**　`E:\PythonCode\EasyChat\backend\runtime\contracts.py`、`backend\runtime\hermes\adapter.py`、`paths.py`、`tools.py`、`backend\modules\superagent\runner.py`、`workspaces.py`、`credentials.py`、`worker.py`。（文件范围）

- [ ] 普通对话与编码任务分别验证 session/run、工作区、缓存和工具策略，覆盖两个用户、同一用户两个任务、任务重试三个组合。（步骤）
- [ ] 对编码工具做越界探测，覆盖相邻任务目录、符号链接、应用数据库、渠道密钥和发布凭据。报告实际可访问范围，再形成执行进程或容器方案。（步骤）
- [ ] 独立执行环境若确有必要，设计先写清输入的可信身份、工作区、工具授权、预算和结果事件，以及进程失联、退出与回收语义，再按保护路径要求提交草稿。（设计步骤）
- [ ] 控制端持有发布凭据，编码环境使用确有需要的受限读取凭据。构建和验证同样按不可信仓库代码处理，设置独立权限、挂载与资源限制。（拟定设计）
- [ ] 预算覆盖墙钟时间、工具执行、模型调用及重试。用量不可精确获取时记录限制的实际口径，避免声明无法执行的硬 token 上限。（步骤）
- [ ] 验证排队取消、编码取消、长工具调用取消、忽略中断和后台子进程残留。只有得到停止证据后进入已取消，晚到结果按 attempt/version 拒绝回写。（验收步骤）

```powershell
python -m pytest tests/contracts/test_runtime.py tests/contracts/test_tool_context.py tests/superagent/test_workspaces.py tests/superagent/test_credentials.py -q
```

**通过标准**　身份和工作区互不串用，禁止资源无法访问，取消可验证，编码任务的资源上限生效，现有聊天回归通过。（验收要求）

### P5 任务恢复、验证与 Draft PR 发布

**对应阶段**　C3。（任务映射）

**核查文件**　`E:\PythonCode\EasyChat\backend\modules\superagent\api.py`、`repository.py`、`worker.py`、`verification.py`、`github.py`、`contracts.py`。（文件范围）

- [ ] 核对当前状态常量和检查点，按现有语义建立操作矩阵，写明受理、追问、补充、取消、重试、发布和人工暂停的前置条件。（步骤）
- [ ] 针对租约失效、旧 attempt 返回和两个 worker 认领做并发回归。仓库配置快照、原始受理身份与发布时有效授权分别核验。（步骤）
- [ ] 验证最终 head/tree 对应测试证据，测试后代码或分支发生变化时使原证据失效。用户可编辑的仓库内容不能提高控制端发布权限。（拟定门禁）
- [ ] 注入 `push_intent` 前后、push 成功后、`pr_intent` 后、PR 创建成功但响应丢失、终态事务提交后等故障，恢复时先查询远端状态。（验收步骤）
- [ ] 已发布动作与本地取消冲突时保留远端事实，记录取消竞态。旧版任务缺少必要快照时执行现有明确拒绝或受控恢复规则。（步骤）
- [ ] 自动创建的 PR 保持 Draft，PR 描述关联验收结果、最终 SHA、缺失证据与人工待决事项。高风险任务在发布草稿中保留升级简报。（拟定交付）

```powershell
python -m pytest tests/superagent tests/contracts/test_superagent_api.py -q
```

**通过标准**　故障恢复复用原分支和 PR，旧 attempt 无法覆盖新结果，缺失或过期验证证据按既定策略阻塞或明确标记，发布结果可对账。（验收要求）

### P6 微信受理、追问与回执

**对应阶段**　D1、D2。（任务映射）

**核查文件**　`E:\PythonCode\EasyChat\backend\modules\channels\commands.py`、`wechat\listener.py`、`repository.py`、`backend\modules\superagent\intake.py`、`backend\tools\business\superagent_tools.py`、`backend\modules\delivery\api.py`、`repository.py`、`wechat.py`。（文件范围）

- [ ] `/开发` 与明确自然语言开发指令走同一 service，普通讨论、转发内容、引用文字与机器人消息通过受理规则验证。已明确下达的任务按策略自动执行并创建 Draft PR。（拟定行为）
- [ ] 明确信息充分条件为目标、验收标准与作用范围可识别。先利用仓库上下文消除歧义，涉及业务决策或多任务指代时再追问。（拟定行为）
- [ ] `/任务`、`/补充`、`/取消`、`/重试` 复用现有入口，核验任务号归属与短号歧义。补充输入进入原任务，按生命周期创建必要的新 attempt，保留任务上下文和分支关联。（步骤）
- [ ] 查明当前渠道 event ID 的唯一范围，以账号、会话与上游 event 的稳定组合验证去重。相同事件重投只受理一次，不同事件明确重复执行时可以建立新任务。（验收步骤）
- [ ] 模型工具重试沿用服务端受理操作键，模型改写文本、服务重启与用户再次发起分别测试。修改现有去重语义前先复现确定性误判。（步骤）
- [ ] 回执地址由持久化来源解析，验证绑定撤销、原会话失效和 owner 变化时 fail-closed，发送失败只推进 delivery 重试。（步骤）
- [ ] 微信发送成功但响应丢失时，按渠道实际幂等与查询能力处理。无法判定结果时保留 uncertain 与对账入口，测试明确区分“本地仅入队一次”和“远端仅展示一次”。（拟定投递语义）

```powershell
python -m pytest tests/channels/test_development_commands.py tests/channels/test_durable_intake.py tests/contracts/test_wechat.py tests/tools/test_superagent_tools.py tests/delivery -q
```

**通过标准**　明确任务可受理，追问与补充可继续原任务，跨用户操作被拒绝，重复事件不重复编码，回执失败不重复发布，投递不确定性在面板可见。（验收要求）

### P7 GitHub 反馈与有限自动修复

**对应阶段**　D3。（任务映射）

**核查文件**　`E:\PythonCode\EasyChat\backend\modules\superagent\webhooks.py`、`routes.py`、`api.py`，以及 `tests\superagent\test_webhooks.py`。（文件范围）

- [ ] 核验签名、delivery ID、事件类型、仓库、PR、head SHA 与输入长度，伪造事件和不相关仓库均拒绝。（步骤）
- [ ] CI 和评审意见仅在原任务授权范围内作为输入，去重后关联原任务。机器人、自身回执和旧 SHA 反馈不能循环触发新任务。（拟定反馈规则）
- [ ] 自动修复预算覆盖轮数、耗时、模型调用和总用量，预算耗尽进入明确阻塞状态。受保护任务的人工暂停仅由符合仓库规则的人类续作指令解除。（拟定门禁）
- [ ] 通过测试仓库演练失败检查触发一次修复，再重复投递和追加旧 head 事件，确认修复轮次及 PR 数符合预期。（验收步骤）

```powershell
python -m pytest tests/superagent/test_webhooks.py tests/contracts/test_superagent_api.py -q
```

**通过标准**　反馈归属准确，修复有界，暂停状态有效，重复通知和过期反馈不造成重复副作用。（验收要求）

### P8 全功能前端验收与状态展示

**对应阶段**　E，覆盖此前用户报告的 UI 场景。（任务映射）

**核查文件**　`E:\PythonCode\EasyChat\agent_frontend\src\views\ChatView.vue`、`components\chat\ChatSidebar.vue`、`views\SuperagentView.vue`、`views\AdminView.vue`、`views\admin\RoleListPanel.vue`、`RoleEditDialog.vue`、`router\index.ts`、`stores\auth.ts`。（文件范围）

- [ ] Chat 三列在 1440、950、679 CSS 像素宽场景核查左右拖动、最小宽度、折叠、刷新恢复、滚动、清理事件监听与触摸或键盘替代操作。窄屏按既有响应式设计核验，旧持久化宽度需钳制到当前可用范围。（验收步骤）
- [ ] Superagent 核查卡片内边距、表单间距、按钮换行、长错误文案、任务分页和断线重连，加载失败与未配置原因准确显示。（验收步骤）
- [ ] Admin 核查整张角色卡和编辑入口可操作、键盘聚焦、弹窗滚动、保存失败保持输入，以及拥有者的完整授权文案与实际有效权限一致。（验收步骤）
- [ ] 对路由中的聊天、技能、微信、提醒、账单、超级代理、记忆、用量、管理、配置分别完成允许、只读或部分授权、拒绝、接口失败四类场景，按照实际功能适用性记录结果。（验收步骤）
- [ ] 用真实浏览器操作验证，不以源码字符串断言替代交互测试。每个实际 UI 修改保存相同账号、数据、窗口尺寸和主题的 Before/After。（验收步骤）
- [ ] 状态数据继续由后端 capability 与任务账本提供，界面分开展示执行完成、验证结果、PR 待评审和投递状态，核查状态操作矩阵后只呈现可用动作。（拟定界面规则）

```powershell
Push-Location E:\PythonCode\EasyChat\agent_frontend
npm test
npm run type-check
npm run build
Pop-Location
```

**通过标准**　原报告场景均有可复查操作证据，全路由矩阵有结果，修改后的交互和授权一致，前端三项检查通过。（验收要求）

### P9 代码评审、实单与回滚演练

**对应阶段**　F。（任务映射）

- [ ] 按固定 baseline 比较完整差异，分别评审授权、并发、资源回收、异常传播、事务范围、迁移兼容和外部副作用。（评审步骤）
- [ ] 记录每项问题的严重程度、可复现输入、文件位置和修复验证。客观缺陷先修复再重跑相应回归，产品决策与 protected paths 按既有许可处理。（步骤）
- [ ] 运行维护全集、superagent/contracts 及前端三项检查。跳过、取消或环境失败单列，验收清单逐项保留命令退出码。（步骤）
- [ ] 使用已授权测试目标完成阶段 F 的实单场景，核对微信 event、task、attempt、run、最终 SHA、PR 和 delivery 的关联。（验收步骤）
- [ ] 演练暂停受理、排空或终止在途任务、远端副作用对账、恢复旧代码与匹配数据快照、保持渠道默认关闭、人工核验后重新启用。（回滚步骤）
- [ ] 回滚后保留 PR、Git refs、来源事件、投递记录与恢复游标的对账结果。恢复旧快照可能重放已消费事件，重新启用前必须处理该窗口。（验收步骤）

**通过标准**　影响授权、数据一致性、重复发布或运行隔离的高严重度问题已修复或明确阻止发布，功能与恢复证据完整，剩余项有负责人及续作条件。（验收要求）

### P10 Harness 隔离试验与迁移决策

**对应阶段**　U3，完成生产整改后单独排期。（任务映射）

- [ ] 选取 UI 修复、后端缺陷、测试修复、长任务、人工追问五类任务，每类两组配对，每组由两套引擎各执行一次，共 10 组、20 次运行。每组从相同基线开始，模型、预算和验收一致。（拟定试验）
- [ ] 记录功能验收、评审缺陷、耗时、实际或估算用量、恢复结果和适配人时，另做权限、取消、重启与重复事件故障测试。（拟定试验）
- [ ] 演练候选引擎的小版本升级，记录接口变化和补丁维护成本。结果覆盖任务能力与升级能力两部分。（拟定试验）
- [ ] 试验前固定选型门槛。硬门槛为身份隔离、禁止工具、取消恢复和重复发布测试全部通过，既有功能验收保持通过。成本、质量与维护收益按基线数据提出目标，经产品确认后用于最终决策。（拟定评估规则）
- [ ] 输出继续 Hermes、仅替换编码执行、或进一步评估全量迁移三种结论之一，附原始结果与回滚方案，再提出生产切换工作包。（拟定交付）

## 11. 依赖顺序与交付记录

推荐顺序为 `P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8 → P9`，`P10` 在生产整改验收后单独实施。安全区的测试补齐、前端已定义行为修复与资料核查可在依赖满足后推进。（方案）

### 11.1 功能覆盖矩阵

执行模型先核对当前注册路由、公开 service、微信命令和业务工具，以当前实际入口填写下表。每项标注自动回归、浏览器操作、真实渠道或环境阻塞，已退役入口记录证据后从有效功能清单移除。（验收约定）

| 范围 | 必须核对的行为 | 现有回归入口 |
|---|---|---|
| 登录与权限 | 登录失效、角色修改、跨 owner 拒绝、部分授权、最后拥有者 | `tests/access`、`tests/security`、`tests/contracts/test_tool_context.py` |
| 普通聊天 | 创建与恢复会话、流式输出、附件授权、取消、断连、模型异常 | `tests/assistant`、`tests/contracts/test_web_chat.py`、`tests/contracts/test_sse.py` |
| 模型配置与用量 | 模型选择、密钥脱敏、失败回退、用量归属与统计 | `tests/models`、`tests/usage` |
| 技能 | 本人操作、管理范围、版本激活、工具可用性 | `tests/skills` |
| 记忆与个人偏好 | 本人读取与修改、遗忘、偏好与情绪开关、越权拒绝 | `tests/memory`、`tests/profiles` |
| 微信接入 | 绑定和解绑、持久化受理、命令、媒体入口、重复事件、失效绑定 | `tests/channels`、`tests/contracts/test_wechat.py` |
| 编码任务 | 受理、追问、补充、取消、重试、恢复、Draft PR、反馈 | `tests/superagent`、`tests/contracts/test_superagent_api.py`、`tests/tools/test_superagent_tools.py` |
| 提醒与调度 | 本人查询与启停、时区和静默窗口、重复触发、重启恢复 | `tests/scheduling`、`tests/profiles` |
| 简报与收藏 | 已启用的生成、保存、查询与来源范围，失败重试 | `tests/briefing`、`tests/inbox` |
| 账单 | 文件导入、候选确认、重复导入、金额解析、修改、导出、只读模式 | `tests/ledger` |
| 文件 | 上传、引用、读取、删除与 owner 检查，路径和大小限制 | `tests/files` |
| 投递 | 微信与邮件目标校验、失败分类、重试、静默策略、uncertain | `tests/delivery` |
| 演进与后台维护 | 当前实际启用入口的授权、默认关闭、失败恢复与资源清理 | `tests/evolution`、`tests/architecture` |
| 存储与配置 | 旧数据、追加迁移、WAL 守卫、备份恢复、密钥可用性 | `tests/storage`、`tests/architecture` |

表中行为逐项核对已有断言是否覆盖，缺失的关键回归写入所属工作包，测试目录存在只代表可复用入口。（验收约定）

### 11.2 交付格式

每包采用以下记录结构，所有结论同句带命令、源码、截图或“推断”标记。（交付约定，依据 `AGENTS.md`）

```text
工作包与状态
基线 commit 与修改文件
复现输入、预期和实际行为
采用的修改与理由
授权或设计决策依据
验证命令、退出码与产物位置
评审发现和复验结果
部署、回滚与副作用对账
未验证项、阻塞原因和续作条件
```

## 12. 执行模型提示词

```text
你负责接管 EasyChat 的实现与验收，工作目录为 E:\PythonCode\EasyChat。

首先完整读取以下文件，结合当前磁盘代码核实后执行。
1. E:\PythonCode\EasyChat\AGENTS.md
2. E:\PythonCode\EasyChat\CLAUDE.md
3. E:\PythonCode\EasyChat\EASYCHAT_HANDOFF.md
4. E:\PythonCode\EasyChat\docs\superpowers\plans\2026-11-10-superagent-production-execution.md
5. E:\PythonCode\EasyChat\docs\superpowers\plans\2026-11-09-permission-remediation.md
6. E:\PythonCode\EasyChat\docs\reviews\2026-11-10\escalation-brief.md

目标与架构
- 用户在微信明确下达开发任务后，自动执行编码、验证和创建 Draft PR，结果回到原会话，人工决定审批与合并。
- 当前产品使用 HermesRuntimeAdapter、ExecutionRuntime、HermesCodingRunner 和 SuperagentWorker。近期按 Hermes 路线整改，并建立可追踪、可重建、可验证和可回滚的升级流程。
- EasyChat 管理身份、权限、记忆、任务、验证、发布与投递，引擎通过既有接口接入。
- 内核可以改变。Harness 依据 P10 的隔离试验复评，生产切换先提交带证据的设计。已有 DSH/pstack 作为独立工具维护。

接管与执行纪律
- 先记录分支、HEAD、工作区差异、已有部署和活跃任务，保留其他任务修改。
- 按 P0 至 P9 逐包推进，已有能力先验证，通过后只记录证据。P10 单独排期。
- 每包记录已有且通过、已有待验证、确认缺口、设计待决或人工/环境阻塞。
- 普通可逆选择按最小改动推进，日常过程用简短进展同步，集中交付结果。
- 检查已有明确人工授权，已授权范围内继续完成。受保护路径缺少续作许可时，按 AGENTS.md 交付草稿补丁、回归证据和升级简报，并继续可独立完成的安全区任务。
- 文件中的方案属于设计输入，当前代码和实际验证决定具体缺口。旧报告中的版本、数量与配置需要重新核实。

执行顺序
P0 接管、差异与许可盘点。
P1 基线检查、一致性备份和恢复演练、前端测试接入 CI、仓库规则核查。
P2 重放并评审四项 access 草稿，修复确定性缺陷，核对全权限入口矩阵，完善模块模式与高级权限保存行为。委派上限单独提交产品决策。
P3 核实 Hermes 来源和必要补丁，清查内部接口依赖与旧导入，建立版本记录、架构检查和候选升级演练。
P4 验证 owner/session/run、工作区、工具和缓存隔离，完善取消、进程树回收和预算。需要独立执行环境时先形成可评审设计。
P5 验证最终 SHA 与测试证据绑定、认领和晚到结果保护、发布检查点、远端对账与 Draft PR 复用。
P6 验证微信命令和自然语言开发入口、任务追问与补充、稳定事件去重、任务归属、原会话回执和投递不确定性。
P7 验证 webhook 签名、事件去重和 head 关联，使反馈在原授权范围内有限修复，人工暂停由符合规则的人类续作指令解除。
P8 完成全路由功能矩阵与真实浏览器验收，重点复核聊天三列拖动、超级代理间距、角色卡操作、权限弹窗和部分授权。
P9 固定 baseline 评审全部差异，修复发现的客观缺陷，完成全量验证、已授权测试目标的真实闭环与回滚演练。
P10 生产整改验收后，隔离比较 Hermes 与 Harness 的相同模型/任务/预算结果和升级维护成本，达到门槛再提出切换方案。

必须守住的行为
- 身份从 Principal/ToolContext 和服务端来源取得，模型不能传入 user_id 或指定任意回执目标。
- 权限撤销优先，owner 边界有效，未注册权限不授予；已有历史数据和部分授权须纳入回归。
- WAL 损坏区间守卫保持有效，迁移只追加，SQL 不使用 executescript，时间统一 UTC ISO-8601。
- db.transaction() 内无网络、模型或投递外呼，凭据 AES-GCM 加密且不进入日志、argv、remote URL 或工件。
- 能力默认关闭，无人值守审批 fail-closed，编码环境和验证环境的资源权限分别验证。
- 取消、重试和恢复先核对在途运行与外部副作用。旧 attempt 不能覆盖新结果，回信失败只重试投递。
- 无法确认微信发送结果时按真实渠道能力保留 uncertain 与对账记录。
- 自动交付 Draft PR，审批、合并与受保护变更按仓库规则执行。

验证与评审
- 对具体缺陷先复现，再做最小修复并执行行为回归。
- 优先复用 tests/support/rig.py、真实临时 SQLite、ASGITransport 和既有测试入口。
- StubAgent/FakeRuntime 的通过结果只说明模拟行为，真实内核、微信和 GitHub 验收分别记录。
- UI 修改保存同场景 Before/After，并实际操作浏览器验证。
- 评审覆盖授权、并发、事务、异常传播、资源清理、历史数据、迁移及发布恢复。

从仓库根目录执行下列命令并保留退出码。
python -m pytest tests/access tests/security -q -m "not integration and not resources"
python -m pytest tests/superagent tests/contracts -q
python -m pytest tests -q -m "not integration and not resources"
Push-Location agent_frontend
npm test
npm run type-check
npm run build
Pop-Location

每包交付差异、复现与修复证据、验证结果、评审发现、授权或设计依据、部署回滚与未验证项。所有论断附源码、命令、截图或标注推断。
最终汇总已完成、草稿待人工续作、环境阻塞和设计待决四类结果，给出相应续作条件。
```
