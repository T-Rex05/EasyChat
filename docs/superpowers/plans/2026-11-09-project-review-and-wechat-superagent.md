# EasyChat 项目检查与微信 Superagent 实施方案

检查日期为 2026-11-09。交接对象为后续实现模型。

## 1. 检查范围、证据与默认决策

本次检查覆盖项目目录、当前启动入口、业务模块公开接口、前端路由及主要页面、微信接收和发送、后台执行、数据库迁移、Docker 与 CI。重点逐段检查 `backend/modules/superagent/`、微信 listener 与入站处理、Hermes 工作区绑定、SuperagentView 及现有测试。其余业务按模块接口和关键链路检查，内嵌 Hermes、历史论文复现和旧测试未逐文件逐行审计。

检查基于磁盘当前工作区，包含大量未提交功能。参考提交为 `3b3d6c5`，不能用该提交替代工作区作为执行基线。

当前维护区粗略规模为 modules 133 个 Python 文件、26,608 行，runtime 11 个文件、1,001 行，platform 25 个 Python/SQL 文件、1,966 行，前端 src 43 个 Vue/TS 文件、12,630 行。测试目录 188 个 Python 文件、33,928 行，包含停用的历史测试。

用户已确认，明确下达任务后自动创建 Draft PR。其余默认产品决策供用户复核

- 第一版面向一个已配置仓库、已绑定微信用户和明确的编码请求。
- 明确下达任务后自动编码、验证、创建 Draft PR。合并由仓库维护者决定。
- 模糊需求先追问。用户可选择特定仓库的自动执行规则，规则须持久化且可撤销。
- 先保持现有 SQLite 与单应用 worker 部署，编码执行逐步移到独立 runner。
- 群聊监听、@、引用消息和主动发送窗口依赖实际微信接入能力，先以 capability probe 的真实结果决定开放范围。

### 已执行验证

- 定向后端命令 `python -m pytest tests/superagent tests/contracts/test_superagent_api.py tests/contracts/test_wechat.py tests/architecture -q --tb=short`，55 passed。
- `npm run type-check`，退出码 0。
- `npm run build`，退出码 0。主 JS 约 1,020.59 kB，gzip 约 332.09 kB。主 CSS 约 371.64 kB，gzip 约 50.60 kB，出现大 chunk 提示。
- 临时本地 Git 仓库验证，任务分支已提交变更时 `git status --porcelain` 为空，`git diff baseline...HEAD` 仍有变更。证实当前收尾判据无法覆盖代理自行 commit 的输入。
- 维护测试全集命令 `python -m pytest tests -q -m "not integration and not resources" --tb=short`，1,036 passed、2 skipped、2 deselected，耗时 284.13 秒。根 conftest 排除了历史根目录测试，结果对应当前维护套件。

真实微信、真实 GitHub push/PR、Docker 构建和浏览器交互未联调。测试成功只覆盖实际执行的范围。

## 2. 当前架构与值得沿用的能力

真实启动路径为 `backend/server.py` → `backend/app.py` 工厂 → `backend/bootstrap.py` 生命周期。后端已经迁移到模块化 SQLite 架构，README 和 CLAUDE.md 中大量 MySQL、Redis、Neo4j、GraphRAG 描述属于旧架构。

当前主链路

```text
微信 iLink getupdates
  → parser 归一化
  → channels 身份绑定、去重、命令、媒体处理
  → assistant.submit → RunDispatcher → HermesRuntimeAdapter
  → superagent_submit_task 业务工具 → SuperagentService
  → superagent_tasks → SuperagentWorker → git / Hermes / GitHub REST
  → DeliveryService → 微信发送
```

可复用能力包括 access 的 Principal/RBAC、ToolContext 的可信身份、channels 的绑定与会话、files 的归一化存储、delivery 的账本与 uncertain 状态、jobs 的事务入队、usage 的模型用量、scheduling 的到期实例、memory 的来源与遗忘、inbox 的链接收藏、briefing 的聚合内容、ledger 的导入确认和去重。

这些基础能力已经足以支撑个人微信助手与编码代理。近期投入应优先落在跨模块事务、执行边界和任务连续性。

### 与上游的融合判断

本地实现采用 Python/Hermes 重建了 Source → Task → Executor → PR → Reply 主链路。上游是 DeepSeek Harness 的研究原型，具有 Trigger、Thread、Policy、Eval、Mandate、Assignment、Input、Report、Subscription 和持久化 Effects 等更多领域概念。本地当前属于其中一部分能力的适配实现。

优先吸收三个设计

1. 每个任务保留独立目录、会话、分支，以及后续输入和报告。
2. 来源事件去重，事件先落库，外部动作持久化后执行，重启后对账。
3. 将等待人回答、等待评审、阻塞和执行失败呈现在工作台中。

上游对执行目录和命令包装也明确说明了边界限制，本项目仍需建立自己的进程与凭证隔离。

参考来源

- [上游 README](https://github.com/deepseek-ai/dsh-superagent-prototype)
- [领域模型](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/001-domain.md)
- [执行与恢复](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/003-execution.md)
- [架构与持久化 Effects](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/007-architecture.md)

## 3. 按优先级排列的现有问题

以下“代码确认”表示可直接从当前实现推导，尚未真实外联复现的影响另作说明。

| 级别 | 问题及证据 | 影响与修复方向 |
|---|---|---|
| P0 | `superagent/worker.py:250` 用带 token URL clone，`github.py` 将 token 拼入 URL。Git clone 默认保存 origin URL | 与界面“凭证不会写入仓库配置”的说明冲突，token 还进入进程参数、Git 错误。改用无凭证 remote 和受控短生命周期认证助手，统一脱敏。对已有工作区清理 remote，暴露过的凭证由管理员轮换 |
| P0 | `runtime/hermes/adapter.py:105` 只注册 cwd，代码注释明确共享 default 容器 | terminal/file 的 cwd 无法限制绝对路径、进程或凭证访问。编码任务应使用独立 runner，限定文件挂载、网络、资源与进程生命周期 |
| P0 | `superagent/api.py:165` 直接调用异步 `runtime.cancel`，没有 await。worker 收尾只在开始检查一次 live | 运行中取消可能没有真正触发 interrupt，取消后仍可能 push、建 PR、覆盖终态。采用 cancel_requested、等待实际停止、run/attempt 条件更新，并覆盖每个外部动作边界 |
| P0 | `worker.py:245` 每次强制切回 base。`repository.py:207` 重试清空 PR 字段 | push 成功后建 PR 失败、PR 已创建但响应丢失时，重试可能丢本地提交、遇到非快进或重复创建。按 attempt 保存检查点并对账远端分支和已有 PR |
| P0 | `worker.py:265` 仅以 porcelain 判断改动。`_run_agent` 未要求观察到 completed。验证仅写在 prompt | 代理自行 commit 会被判无变更，流意外结束或测试失败也缺少确定性拒绝发布门禁。使用 base/head SHA、结构化执行报告和宿主控制的验证阶段 |
| P1 | `channels/api.py:468` 异常后删事件并返回 internal，listener 仍在批次末推进 cursor | 应用内部失败后上游未必重投，存在消息丢失路径。先事务持久化完整可重放 envelope，再推进 cursor，由本地 inbox 重试 |
| P1 | `worker.py:374` 工作区只由 owner/repo 得出，host/task 均未进入键。`tick` 批量置 running 后串行执行 | 当前 max_concurrent 实际是认领批量，多个任务共用目录。仓库设置切换和将来并行会放大问题。按 host/repo/task 隔离，先将真实并发固定为 1 |
| P1 | `RUN_TIMEOUT_SECONDS` 仅声明，Git communicate 与 agent 流没有对应时限 | 长任务可能无限占用 worker。分别增加 Git、验证、模型与总任务 deadline，停止后确认进程树退出 |
| P1 | 任务未保存 repo/base SHA/settings revision，执行读取当前 settings | 排队任务可能因管理员改配置而跑到另一个仓库。受理时固定仓库和策略快照，凭证引用允许受控轮换 |
| P1 | `api.py:133` 和 `_task_for` 未检查 `superagent.view`，cancel 依赖读取授权 | 后端行为与前端权限入口不一致。分别检查 view/create/cancel/manage，并与 owner 条件组合 |
| P1 | `worker.py:321` 使用 owner 第一个有效微信绑定回执，dedup key 固定为 task notify | 多账号时回错来源，失败通知后重试成功的回执可能被同一个 dedup key 抑制。持久化来源地址，按 task/attempt/report/target 唯一入队 |
| P1 | 终态更新和 `_notify` 分开事务，通知入队失败只写日志 | 崩溃或暂时存储故障可能造成完成结果无回执。结果、报告和 delivery 请求同事务提交，实际发送沿用 delivery worker |
| P1 | URL 校验用 substring 且允许 git@，真正 parser 只接受 HTTPS。pr_labels 保存后未应用 | 输入接受和执行能力不一致。第一版统一规范化 HTTPS GitHub，旧 Gitee/SSH 配置提供明确迁移提示与保留策略 |
| P1 | `SuperagentView.vue:174` 普通用户无论请求成功失败都设 gateReady=true。只在展开时拉 events | 页面错误表示可执行，运行轨迹不自动更新。新增 capabilities，任务和事件采用游标增量刷新 |
| P1 | `docker/Dockerfile` runtime 只显式安装 curl，worker 直接调用 git | 干净基础镜像缺少显式 git 依赖，目标项目验证环境也没有契约。给 runner 定义 git/runtime readiness 与镜像构建冒烟 |
| P2 | README/CLAUDE/requirements/pyproject 与新部署不一致，CI lint 带 `|| true` | 新模型容易恢复旧架构，检查不能形成发布门禁。以新架构文档为准，统一依赖入口，分阶段启用变更文件 lint |
| P2 | 前端路由和 auth store 多处读 localStorage，JSON.parse 无保护，userId 默认 '1' | 缓存损坏可能阻断导航，身份初始化有错误兜底。统一 auth.ready、校验存储、从 /me 初始化，未知身份保持待初始化 |
| P2 | 大页面和两套页面样式逐渐分化，主 JS 超 1 MB | 按业务区拆分 Config/Chat/MessageBubble，按构建分析处理 Element Plus 等实际依赖，再设置 gzip 首屏预算 |

另需补充，现有测试多用 FakeRuntime/FakeGit/FakePRClient，覆盖了业务主路径，对真实 Git、取消协程、发布阶段崩溃、页面竞态与执行隔离的覆盖较少。

## 4. 产品路线与方案选择

### 推荐路线

沿用现有 Python 模块与 Hermes，补齐任务输入、执行 attempt、发布检查点、来源地址和 runner 接缝。现有 access/delivery/files/jobs 保持为基础能力提供方。

另外两种可选路线

- 把上游 TypeScript 服务作为独立 sidecar，通过 API 桥接微信。能保留更多上游行为，但需要维护两套身份、状态和部署，在当前融合程度下成本较高。
- 把工作限定为显式命令触发、固定模板修改和串行 Draft PR。交付最快，适合第一阶段，后续逐步扩充自由编码与反馈处理。

推荐第一种的模块边界，先按第三种的产品范围上线。

### 微信交互

建议增加确定性命令，并保留自然语言入口，两者进入同一 service。

```text
/开发 修复导出 CSV 中中文乱码，增加回归测试
/任务 sag_xxx
/补充 sag_xxx 需要兼容 Windows Excel
/取消 sag_xxx
/重试 sag_xxx
/任务列表
```

简单且完整的明确请求可直接受理。模糊请求生成待澄清任务，追问一个影响实施的关键问题。追问回答写 task_inputs，继续使用原任务目录和分支。指代“刚才那个”时，仅有一个当前会话活跃任务才自动定位，否则返回可选任务短号。

聊天中粘贴的 issue 内容、网页、仓库文档和转发消息作为材料保留来源。任务发起权由绑定身份、仓库范围和已保存规则判断。授权规则的变更由 service 入口处理。

机器人即时回执给出任务号、仓库、当前阶段和查询方法。后续只在需要回答、受阻、验证失败、PR 就绪和合并/关闭时发送消息。普通步骤留在 Web 时间线。

“监听微信”在当前工程中具体指 iLink bot 账号的 getupdates 流。读取任意微信历史会话、联系人私聊或群聊的能力需要单独实测接入范围。

## 5. 数据模型与状态约束

第一版扩展现有 superagent 模块，新增迁移使用执行时的下一个空闲编号，当前最新为 0019。已发布迁移及 checksum 保持可校验，已有任务逐步回填。

### 表与字段

| 对象 | 建议字段与约束 |
|---|---|
| superagent_tasks 扩展 | repo_url_snapshot、base_branch_snapshot、base_sha、settings_revision、policy_revision、source_event_id、source_channel_account_id、source_chat_id、source_user_id、executor_session_id、active_attempt_id、version、phase、cancel_requested_at |
| superagent_attempts 新表 | id、task_id、attempt_no、run_id、session_id、workspace_key、state、checkpoint、head_sha、remote_head_sha、pr_number、pr_url、started_at、heartbeat_at、finished_at、error_code、error_summary，UNIQUE(task_id, attempt_no) |
| superagent_inputs 新表 | id、task_id、source、external_event_id、actor_id、text、attachment_refs、created_at、consumed_attempt_id，来源组合唯一，actor 与 owner 分开保存 |
| superagent_reports 新表 | id、task_id、attempt_id、kind、summary、question、head_sha、verification_ref、created_at，kind 为 progress/question/blocked/ready/failed/no_changes |
| channels 的持久 inbox | 原事件表补 envelope_version、受控 envelope 引用、processing_state、retry_at、attempts。唯一键沿用平台+账号+事件。持久保存重放所需文本、媒体引用和来源，敏感字段按现有密钥方案保护 |
| delivery 复用 | 结果与投递请求事务内写入，dedup_key 含 task/attempt/report/target。sending 的 uncertain 继续沿用已有人工对账语义 |

已有旧任务的仓库来源无法从历史记录恢复时，标记 legacy_config_unknown。已结束任务保留只读展示，排队/失败任务需在重新执行前确认目标配置并生成新 attempt。

### 状态

任务 status 保留 queued/running/succeeded/failed/cancelled 以兼容已有调用方。另加 waiting_input、blocked、awaiting_review、interrupted。执行 phase 单独表示 preparing/coding/verifying/publishing，PR 状态单独保存 draft/open/merged/closed，避免把创建 PR 当作已合并。

```text
queued → running
running → waiting_input → queued
running → blocked
running → awaiting_review → succeeded（合并）
running → succeeded（确认无代码交付）
running → failed / interrupted
queued → cancelled
running → cancel_requested → cancelled
```

`cancel_requested` 可作为新增兼容状态，旧调用方须先支持该值后开放写入。PR 关闭未合并时保留独立 outcome=closed_unmerged，UI 清楚显示结局。

所有写操作用 task_id + active_attempt_id + version + 允许的旧状态做条件更新。时间线事件写入同一事务。旧 worker 的迟到结果不得覆盖新 attempt。

取消和发布相遇时明确线性化边界。未发出 push/PR 请求时拒绝发布，已发出的动作以实际远端结果对账，记录 cancellation_after_publication 并回报。界面只有在执行停止后展示 cancelled。

## 6. 执行、Git 与验证方案

### 工作区和 runner

每个 task 独立 clone 或 worktree，路径包含规范化 host/repo 哈希及 task_id。目录名仅由服务生成，先解析绝对路径并验证仍在配置根目录。一个任务的多个 attempt 复用工作区，恢复前先读取 Git 与数据库检查点。

短期默认 concurrency=1，认领一个才置 running。实际并行开放前必须完成工作区隔离、共享 runtime 线程/环境检查和全局 runner 槽位控制。

定义窄接口 `CodingRunner.prepare / execute / verify / interrupt / inspect / cleanup`，请求含 task、attempt、仓库快照、workspace 引用、工具与资源策略，响应含 exit 状态、head SHA、报告、测试证据和工件引用。先利用已有 runtime 适配，随后提供独立进程/容器实现。

生产 runner 限定非 root 用户、任务目录读写、受控依赖缓存和网络出口、CPU/内存/PID/磁盘/时间配额。应用数据库、微信凭证、GitHub 发布 token 和宿主 Docker socket 由控制端持有。模型访问通过受控代理或任务级短期凭据。恶意依赖与仓库脚本同样处在执行边界内。

容器执行先用 Linux 验证，Windows 本地开发可经受控 runner endpoint 调用。若使用 worktree，明确处理 `.git` 文件并只暴露需要的 Git 元数据。

### Git 发布

1. 受理固定 repo、base_branch，prepare 记录 base_sha。remote URL 使用无凭证规范地址。
2. 执行后确认 runtime.completed 和结构化报告。阻塞、追问、失败分别进入相应状态。
3. 对合法工作树变更进行路径检查，拒绝新增敏感文件、越界链接和超出策略的文件修改，再 stage/commit。
4. 无论代理是否自行 commit，比较 `base_sha...HEAD`，并检查未跟踪文件、工作树、分支和 ancestry。无需交付时写明确 no_changes 报告。
5. 对最终 head_sha 运行确定性验证。验证完成后再次确认 HEAD 与工作树未变。
6. 发布前重新确认授权、attempt、取消状态和策略。保存 publish intent，使用控制端凭证 push。
7. 根据 repo/head/base 查询已有 PR，存在时复用。不存在时创建 Draft PR，body 带稳定 task 标记。保存 head/PR 检查点。
8. 结果报告、状态和回执账本同事务提交。网络超时后先查远端，不重新生成提交。

第一版优先 GitHub HTTPS，Gitee 和 SSH 如继续支持须分别实现相同 parser、认证、重试和契约测试。标签通过对应 issue labels 接口单独应用，标签失败记录为可重试次要动作。

认证采用专用 askpass/credential helper 或受控凭证代理。helper 只对目标 host/repo 响应，进程环境最小化、结束时回收，日志统一清洗 URL userinfo、token 和 HTTP authorization。GitHub App 可作为团队版后续凭证方案。

### 验证与预算

每个仓库保存可配置的验证命令、超时和必选检查，由管理员控制。执行端在隔离环境运行命令，记录命令、退出码、耗时、日志工件、head_sha 和环境镜像摘要。

当前 EasyChat 示例验证集为后端维护套件、前端 type-check/build。任务只改文档时可配置相应轻量 profile。缺验证环境时进入 blocked。可选“允许发布未验证 Draft PR”应为显式仓库策略，并在 PR 中记录缺失证据。

加入每 task 的最大耗时、模型调用次数、token、自动修复轮数和修改行数预算，usage 用 task_id/attempt_id/run_id 关联。预算耗尽保留代码和报告，进入 blocked。不要只依赖 prompt 提醒。

## 7. 前端修改方案

### 任务工作台

SuperagentView 拆出 TaskList、TaskDetail、TaskTimeline、TaskInputForm、RepositorySettings。列表支持当前用户、状态、来源、创建时间和游标分页，默认展示“需要我处理”。

任务详情显示需求与补充材料、仓库/base/head、当前阶段、执行耗时、最近心跳、预算、验证证据、变更文件摘要、PR/CI 状态、回执状态和失败后的明确操作。

建议新增接口

| 方法与路径 | 行为 |
|---|---|
| GET /api/superagent/capabilities | 返回当前用户 view/create/cancel/manage、enabled、configured、runner_ready、credentials_ready、可执行原因和限制，管理敏感值按权限过滤 |
| GET /api/superagent/tasks?status=&cursor=&limit= | 稳定分页，created_at/id 复合游标 |
| GET /api/superagent/tasks/{id}/events?after_id=&limit= | 增量事件与 next_cursor，按 task 授权 |
| POST /api/superagent/tasks | 接受 Idempotency-Key、需求和附件引用，来源身份由服务构造 |
| POST /api/superagent/tasks/{id}/inputs | 追加追问回答与补充需求，保证归属和请求幂等 |
| POST /api/superagent/tasks/{id}/cancel | 返回取消请求状态和实际执行状态 |
| POST /api/superagent/tasks/{id}/retry | 创建新 attempt，先远端对账 |
| GET /api/superagent/tasks/{id}/artifacts | 返回有权限的验证工件引用 |

先使用增量 polling，保留复用现有 SSE 基础设施的扩展点。页面可见且存在活跃任务时刷新详情，后台降频。没有活跃任务时仍低频更新列表，确保微信中新建任务能出现。限制同类请求只有一个在途，切换详情时取消旧请求或按 task_id 丢弃旧响应。

### 全局前端

- auth store 成为唯一身份入口，增加 ready 状态。读取缓存使用受保护 parser，初始化时从 /me 对齐，未知身份阻止依赖身份的请求。
- API 错误适配集中到 err.ts，fetch/SSE 和 axios 对 token 续期、401、403 和 capability_unavailable 使用一致用户反馈。
- 统一 CSS token、按钮、输入、空态、表格、状态徽标和响应式断点。微信偏好、账单与编码任务可沿用一个页面壳。
- 移动端优先保证二维码绑定、任务详情、补充回答和 PR 链接可用，验证 390px 和桌面布局。
- 首先分析构建依赖归属，再做 Element Plus 按需引入、实际重型编辑器延迟加载和 route chunk。初始目标为入口 JS gzip 低于 200 kB，若业务依赖导致无法达到，记录预算评审依据。
- ConfigView 1,716 行、ChatView 1,596 行、MessageBubble 1,040 行，按设置域和消息类型逐步拆分，每次保持外部 props/events 契约。

## 8. 其他微信功能建议

| 顺序 | 功能 | 当前基础与实施方式 |
|---|---|---|
| A | 截图/语音报 bug → 开发任务 | 复用 media/files/speech，将附件 ID、复现步骤和验收条件存入 inputs。语音先回显关键要求，含糊处追问 |
| A | 微信查询、取消、补充、重试编码任务 | 复用 commands、ToolContext 和 superagent service，所有命令有确定性解析和权限校验 |
| A | PR/CI/评审回流微信 | GitHub webhook 关联 repo/PR/head SHA，CI 失败摘要、待回答问题、待评审结果推微信，用户回复继续同一个任务 |
| B | 开发日报与待办汇总 | briefing/scheduling 聚合活跃任务、待评审 PR、失败投递和 inbox。只推用户订阅范围，遵守 quiet hours |
| B | 链接/文件收藏后检索 | 已有 inbox + files，增强标签、来源、稍后读摘要和引用到开发任务，优先改善现有功能体验 |
| B | 账单导入与确认 | 已有 ledger + 确认命令，增强微信侧待确认摘要、去重解释和月报，保留金额/退款的确定性计算 |
| B | 提醒、语音收件与记忆 | 已有 scheduling/memory/profiles，增加统一“我的待办”入口，展示可修改、删除和来源 |
| C | 指定群需求收集 | capability probe 成功后开放。绑定群、触发方式、发起人名单、目标仓库和通知目标，先形成需求候选 |
| C | 规则触发的定期修复/依赖维护 | 每条规则限定仓库、任务种类、频率、预算和允许路径，按规则生成 Draft PR，保留暂停开关 |

优先完成 A 类闭环。B 类多为既有能力的产品化，C 类需要额外来源能力与策略验证。

## 9. GitHub 回流设计

新增专用 webhook route。对原始请求体验证 HMAC-SHA256 签名，使用常量时间比较，事件先落库再快速应答，按 X-GitHub-Delivery 去重。来源仓库必须匹配配置 allowlist。具体协议依据 [GitHub webhook 验签文档](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)。

第一批接收 pull_request、pull_request_review、issue_comment 和 check_run。事件关联 task 的 repo/pr/head，迟到的旧 head CI 不覆盖当前结果。系统账号、自身评论和重复变更不触发递归工作。

人工评审建议作为 task input，CI 失败默认只摘要报告。管理员可给指定检查开启自动修复规则，最多两轮、指定路径和预算内执行，失败后转 blocked。合并或关闭形成最终报告。

外部创建 PR 使用 Draft 字段，恢复时通过 head/base 查找并复用 PR。API 能力依据 [GitHub Pull Requests API](https://docs.github.com/en/rest/pulls/pulls#create-a-pull-request)。

## 10. 可分批交付的实施任务

每项按“补失败用例 → 最小实现 → 定向验证 → 记录结果”推进。以下新文件是建议职责边界，已有等价模块时优先复用。

### T0 基线与文档对齐

- [ ] 保存 git status、当前 diff 摘要和测试基线，识别其他模型未提交工作。
- [ ] 将 README、CLAUDE.md、docs/architecture/operations.md 的入口和能力描述对齐新架构。
- [ ] 核对 requirements.txt、pyproject.toml、docker requirements 的安装范围与实际导入，给出一个开发入口和一个生产入口。
- [ ] CI 明确默认排除 integration/resources。收敛 lint `|| true`，先阻断新增修改文件的问题。

验收为干净环境可按文档启动、测试和构建，旧服务依赖不会被误认为必需。

### T1 状态、快照与权限

修改 superagent contracts/api/repository/routes、access/policy、frontend api。新增下一个增量 SQL 迁移。

- [ ] 增加 attempt、repo 快照、version、phase 与来源字段，以及兼容旧数据读取。
- [ ] 建立 CAS 状态迁移方法，任务状态和事件同事务。
- [ ] 明确 view/create/cancel/manage 权限，撤销权限后执行和发布阶段重新检查。
- [ ] 新增 capabilities，普通用户也能获得准确受理状态。

测试写入 `tests/superagent/test_task_lifecycle.py` 和 `tests/contracts/test_superagent_api.py`。覆盖旧库升级、权限撤回、跨用户访问、排队后换仓库、旧 attempt 迟到结果。

### T2 凭证与仓库解析

修改 github.py、api.py、worker.py，新增 `superagent/credentials.py`。

- [ ] 同一个 URL parser 完成保存、准备和发布校验，检查准确 host、path、userinfo、query 和 fragment，拒绝伪造域名、控制字符与选项式分支。
- [ ] 无凭证 clone/fetch remote，接入受控 credential helper，错误统一脱敏。
- [ ] 对现有工作区检测并清理 URL userinfo，输出凭证轮换清单的非敏感标识。
- [ ] 预检 GitHub token 和 repo/base 可达性，缺凭证的任务进入明确 blocked。

新增 `tests/superagent/test_credentials.py`。通过临时 Git 仓库及 fake helper 验证 argv、config、stdout、stderr、数据库错误字段都不包含合成 token。真实凭证联调单独标 integration。

### T3 工作区、取消、超时与 runner

修改 worker.py、runtime/contracts.py、runtime/hermes/adapter.py、bootstrap.py。新增 `superagent/workspaces.py` 和 `superagent/runner.py`，部署文件随 runner 实现补齐。

- [ ] 独立 task 目录与持久 executor session，真实并发先固定 1。
- [ ] cancel service 异步调用 await runtime.cancel，或由持久取消请求驱动 worker，所有调用点统一。
- [ ] 增加 git/agent/verify/总耗时限，超时确认子进程树回收。
- [ ] 隔离 runner credentials、挂载、出口和资源配额，增加 readiness。

新增 `tests/superagent/test_cancellation.py`、`test_workspaces.py`、`test_runner.py`。验证两个任务不同目录、排队任务取消后不启动、长命令取消、git hang 超时、应用退出后的清理和取消/发布竞态。

### T4 验证门禁、发布与恢复

修改 worker.py、github.py、repository.py、files/delivery 公开事务接口。新增 `superagent/verification.py`、`superagent/publishing.py`。

- [ ] 必须观察 completed，结构化报告区分 ready/blocked/question/failed。
- [ ] 使用 base/head 比较并覆盖代理自行 commit，验证最终提交的命令和工件由控制端保存。
- [ ] checkpoint 按 prepared/coded/verified/push_intent/pushed/pr_intent/pr_created/notified 推进。
- [ ] 发生未知外部结果时先 inspect 远端，复用已有分支与 PR。默认创建 Draft PR。
- [ ] 终态、报告、通知请求同事务，通知按 attempt/report/target 幂等。
- [ ] 启动后将活跃 attempt 标 interrupted 并先对账，保留工作区与历史。

新增 `tests/superagent/test_git_lifecycle.py`、`test_publish_recovery.py`、`test_verification.py`、`test_notifications.py`。模拟 push 成功后崩溃、PR 创建后响应丢失、失败后重试成功、通知入队失败、已提交无工作树差异、测试失败、有新旧 attempt 并存。

T0–T4 构成第一阶段，可交付可靠的单仓库显式微信编码与 Draft PR。

### T5 微信持久 inbox 与任务输入

修改 channels listener/api/repository/commands、shared/tool_context、superagent service/tools，新增 `superagent/intake.py`。

- [ ] 微信批次先保存可重放 inbox，事务成功后推进 cursor，逐事件重试，毒消息进入可见失败状态。
- [ ] task 创建唯一键连接可信事件和提交意图，HTTP 使用 Idempotency-Key，LLM 工具使用服务端操作键。
- [ ] ToolContext 传递 source 和 channel 引用，附加 server-side 来源查询，提交时固定回执目标。
- [ ] 实现 /开发、/任务、/补充、/取消、/重试、/任务列表，waiting_input 回答继续同一任务。
- [ ] 路由存在歧义时列出任务短号，保持所有权和仓库范围校验。

新增 `tests/channels/test_durable_intake.py`、`test_development_commands.py`、`tests/tools/test_superagent_tools.py`。覆盖重复消息、指纹窗口、媒体失败、内部异常后 cursor、一个会话多个任务、多绑定回执、转发材料伪造指令。

### T6 前端任务工作台

修改 SuperagentView、api/superagent，新增 components/superagent 与 useSuperagentTasks composable。

- [ ] 先落 capabilities、状态区分、分页和请求防竞态，再增加详情/输入/验证工件。
- [ ] 展示 queued、cancel_requested、blocked、waiting_input、awaiting_review、delivery uncertain。
- [ ] 增量刷新同时覆盖列表和展开详情，页面离开关闭请求与计时器。
- [ ] 补自动化用例，覆盖普通用户、无 create 权限、未配置 runner、切换任务响应乱序、微信新建任务出现、移动端长内容。

T5–T6 构成第二阶段，验收“微信创建 → 追问 → 补充 → 执行 → PR → 回信 → 查询”的完整体验。

### T7 GitHub CI 与评审回流

新增 `superagent/webhooks.py`、相应事件存储迁移，复用持久 jobs 执行短回调处理。

- [ ] 原始 body 验签、delivery 去重、仓库 allowlist、事件 schema/大小检查。
- [ ] 关联 repo/PR/head，处理乱序和旧 SHA，过滤机器人循环。
- [ ] 评审转 input，CI 转报告，按规则可有限自动修复。
- [ ] merged/closed 状态回流微信和工作台。

新增 `tests/superagent/test_webhooks.py`。覆盖验签失败、重放、未知仓库、旧 SHA、重复 CI、机器人自触发、关闭与续作竞态。

### T8 前端与运维优化

- [ ] auth 初始化收敛，移除未知用户默认 1，保护缓存解析。
- [ ] 对实际 bundle 归属分析后优化入口体积，记录前后 gzip 数据。
- [ ] 模块化大页面，统一响应式样式与错误组件。
- [ ] runner readiness、队列等待、执行时长、token、验证成功率、PR 失败和 delivery 状态进入运维面板。
- [ ] 备份范围加入 task inputs/reports/attempts 与需恢复的代码提交。区分可重建 cache、工作区、Git refs 和必须保留的产物。做一次隔离恢复演练。

T7–T8 构成第三阶段，随后按 A/B/C 功能表逐项立项。

## 11. 验收矩阵与回滚

必须通过的场景

1. 未绑定/禁用用户、缺权限用户、越权任务号不能创建、读取或控制任务。
2. 同一来源事件与同一提交幂等键重复到达，生成一个逻辑任务。
3. 需求不足后微信补充继续同一 task，session/workspace/branch 可追溯。
4. 两个任务互不污染目录，一个失败不破坏另一个任务的分支与文件。
5. 代理自行 commit 后仍能正确识别 diff，验证失败不会按默认策略发布。
6. 排队和运行中取消都按真实状态显示，已发布的取消竞态可解释。
7. push/PR/通知每个边界注入中断，恢复后对账并复用已知远端结果。
8. 失败通知后重试成功产生独立成功通知，同一报告重试发送遵守 delivery 账本。
9. 改仓库设置不会改变已受理任务，凭证轮换与授权撤回可生效。
10. token 在日志、错误、remote config、命令参数和执行沙箱中使用合成密钥检查。
11. Webhook 重复/乱序/旧 head 不触发重复任务或覆盖新结果。
12. 手机和桌面可完成绑定、提交、补充、取消、查看验证与打开 PR。

建议命令

```powershell
python -m pytest tests/superagent tests/contracts/test_superagent_api.py tests/contracts/test_wechat.py tests/architecture -q
python -m pytest tests -q -m "not integration and not resources"
cd agent_frontend
npm run type-check
npm run build
```

实现新增前端测试工具后，将对应命令加入 package.json 与 CI。真实微信/GitHub/runner 用测试账号和测试仓库单独执行 integration，并记录真实 PR URL、消息事件和工件。

迁移前做一致性备份。新增能力使用开关控制 intake、runner dispatch、webhook 自动修复。出现问题时关闭新受理与派发，保留 inbox、任务、代码和远端对账信息，先等待现有 runner 停止再切换版本。数据库恢复遵循现有 backup 模块的 verify 与保留旧数据流程，避免旧二进制误读新状态。

## 12. 交给实现模型的提示词

```text
你接手 E:\PythonCode\EasyChat。请读取并执行
docs/superpowers/plans/2026-11-09-project-review-and-wechat-superagent.md。

目标是将当前微信 → Hermes → 编码任务 → GitHub PR → 微信回执链路逐步做成可靠、可恢复、可追问的系统。先完成 T0–T4，再完成 T5–T6，随后 T7–T8。每阶段提供可运行结果、验收记录和剩余事项。

先检查 AGENTS.md/CLAUDE.md、当前 git status 和磁盘代码。当前工作区有大量未提交改动，以当前代码为准，识别已完成功能并复用。真实架构为 backend/server.py、backend/app.py、backend/bootstrap.py、backend/modules、SQLite 和 Vue，部分旧文档仍在描述 AgentForge 的历史架构。

优先修复凭证出现在 Git URL、cwd 隔离不足、异步取消未等待、取消/发布竞态、共享任务工作区、超时未生效、porcelain 漏掉已提交变更、缺验证门禁、重试前缺少远端对账、配置未快照、微信 internal 错误后推进 cursor、结果通知非事务和 dedup key 复用。现有定向测试通过不能替代这些回归场景。

用户已确认明确微信指令后自动编码并创建 Draft PR。模糊需求追问，合并交由维护者。群聊和 @ 能力先探测，按结果开放。复用 Principal/ToolContext、channels、files、delivery、jobs 和 usage，业务身份与来源由服务端推导。任务、attempt、input、report 和来源地址应持久化，数据库增量迁移保持旧 checksum 可校验，支持历史任务与状态兼容。

每个任务先增加能证明缺陷的测试，再做最小实现，运行相关测试并记录实际输出。发布和恢复使用持久 checkpoint、CAS、远端分支/PR 查询和同事务通知入队。已有能力满足时继续下一任务，有仓库策略或真实外部能力缺失时明确进入 blocked 并继续处理独立工作。

最终输出每项修改对应文件、测试/构建结果、迁移与回滚步骤、默认决策、真实联调证据及待验证项。先读本方案的验收矩阵，按条核对完成情况。
```

