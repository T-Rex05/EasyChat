# EasyChat 微信接入、任务协作与验收改造执行方案

> 执行模型逐项读取、核查并勾选本计划。有 `executing-plans` 技能时按其任务验收方式执行，受保护区域遵循仓库 `AGENTS.md` 与会话中已有明确授权。（交接约定）

**目标**　在现有 Hermes 与微信编码链路上修正协议兼容性和错误分类，接入逐项验收证据，完善任务协作与受控执行，使后续升级和引擎替换有可验证依据。（方案）

**架构**　EasyChat 管理身份、权限、任务、验证、发布和回执，Hermes 经现有 ExecutionRuntime/CodingRunner 执行。借鉴 LobeHub 的任务与事件设计，先试验独立 Acceptance，再按实际需求扩展任务拆解、并发与远程执行。（建议路线）

**技术栈**　Python、SQLite、Hermes、Vue/Vite，沿用当前 pytest 和前端脚本，验收工具及执行器的新增依赖逐项记录版本与引入理由。（源码依据与方案，`CLAUDE.md`、`agent_frontend/package.json`）

## 1. 当前基线与方案关系

- 上一版总计划为 `E:\PythonCode\EasyChat\docs\superpowers\plans\2026-11-10-superagent-production-execution.md`，P0–P8 已有实施记录。本版从当前代码重新核查，已满足的能力保留证据后进入下一项。（磁盘核查与执行约定）
- `docs/reviews/2026-11-10/P2-access-applied.md`、`P3-hermes-governance.md`、`P4-isolation-record.md`、`P5-publish-recovery-record.md`、`P6-wechat-intake-record.md`、`P7-feedback-autofix-record.md`、`P8-browser-acceptance.md` 是接管输入，逐项核对记录中的提交、测试和待验证条件。（磁盘核查）
- 当前 `account.py` 的 `X-WECHAT-UIN` 为时间戳字符串，`CHANNEL_VERSION` 为 `2.2.0`。listener 将 `errcode=-14` 描述为风控/频率限制。（2026-11-11 源码核查，`backend/modules/channels/wechat/account.py`、`listener.py`）
- 官方当前协议参考描述随机 uint32 十进制字符串的 Base64 编码，版本规则涉及插件协议代际。官方代码将 `-14` 定义为 bot token 失效/过期，并对账号入站与出站做暂停处理。（上游核查）[协议参考](https://github.com/Tencent/openclaw-weixin/blob/main/docs/protocol.md)、[凭据状态处理](https://github.com/Tencent/openclaw-weixin/blob/main/src/api/session-guard.ts)
- 本会话上一轮局部基线为 `python -m pytest tests/contracts/test_runtime.py tests/channels/test_development_commands.py tests/superagent -q`，结果 `87 passed in 58.11s`。执行模型重新运行相关检查，以当前输出作为实施基线。（2026-11-11 既有实测）

## 2. 微信使用范围与证据口径

1. 产品行为采用用户明确下达开发任务后自动编码、验证、创建 Draft PR，再回到原会话，人工评审与合并。（已接受需求）
2. 对封号的判断绑定官方规则、账号实际状态及服务端证据。当前已确认的协议差异按兼容性问题处理，`-14` 按凭据状态处理。（证据口径）
3. 使用官方产品扫码授权流程与公开参考能力，具体账号的绑定范围和通道能力记录实际验证结果。接入方案中的授权未决事项明确列出依据与影响，不推导任意账号、任意群和任意主动消息均可使用。（方案）
4. 规则依据包括未经授权接入、规避安全措施、骚扰和垃圾信息等条款，具体处罚由平台根据行为和情节判断。（官方协议核查）[微信协议](https://oper.my-qcloud.com/cgi-bin/readtemplate?lang=zh_CN&s=default&t=weixin_agreement)
5. 频率上限、消息窗口与重试次数只采用可核对的服务端要求或明确的产品预算。自行设置的保守限额注明产品默认值与调整入口。（方案）

## 3. 目标执行链

```text
微信 / Web / 已授权 GitHub 事件
    → 来源归一化、身份、去重与受理策略
    → 原有任务 / 必要时生成的子任务
    → 控制端调度与状态持久化
    → CodingRunner → Hermes / 经试验的其他执行器
    → 隔离工作区与测试环境
    → 代码验证 + 可观察验收项 + 截图/录屏/日志
    → 控制端验证最终 SHA、发布 Draft PR
    → 任务页显示证据与评审反馈
    → delivery 汇总通知原微信会话
```

任务记录是事实来源，主管根据可见任务生成摘要，子代理的授权范围受原任务约束。编码执行、验证和发布分别记录执行身份与凭据范围。（拟定设计）

## 4. 工作包一 接管与既有结果复核

**文件范围**　`E:\PythonCode\EasyChat\AGENTS.md`、`CLAUDE.md`、`EASYCHAT_HANDOFF.md`、上一版计划与本计划、`docs\reviews\2026-11-10\`。（输入）

- [ ] 记录分支、HEAD、工作区差异、部署版本和活跃任务，保留现有实验及其他任务修改。（步骤）
- [ ] 对照 P0–P8 记录当前实现，核验权限草稿是否已应用、自动修复是否已实现、前端问题是否已修复，输出剩余缺口。（步骤）
- [ ] 核对已有人工授权，许可覆盖范围内继续完成，protected paths 依 `AGENTS.md` 交付草稿与升级简报。安全区任务在依赖满足后继续推进。（步骤）
- [ ] 复用现有备份和恢复流程，核对应用库、Hermes 会话库、工件、Git refs 和加密密钥引用的恢复范围。（步骤）

```powershell
Set-Location E:\PythonCode\EasyChat
git status --short
git rev-parse HEAD
python -m pytest tests/contracts/test_runtime.py tests/channels/test_development_commands.py tests/superagent -q
```

**验收**　每项历史工作有“当前通过、当前缺口、设计待决或外部阻塞”的证据，继续执行的修改范围明确。（要求）

## 5. 工作包二 微信协议与凭据生命周期

**核查与修改文件**　`E:\PythonCode\EasyChat\backend\modules\channels\wechat\account.py`、`listener.py`、`urlpolicy.py`、`backend\modules\delivery\wechat.py`，契约变化涉及 `backend\modules\channels\contracts.py`，UI 涉及 `agent_frontend\src\views\WeChatSettingsView.vue`。（拟定范围）

**测试文件**　复用 `E:\PythonCode\EasyChat\tests\contracts\test_wechat.py`、`tests\channels\test_qr.py`、`tests\delivery\test_wechat_error_classification.py`，请求头专项回归可新增 `tests\channels\test_ilink_protocol.py`。（拟定测试位置）

- [ ] 固定腾讯参考代码的 commit，列出协议代际、请求头、扫码方法与参数、重定向、PIN/实名绑定条件、消息结构、返回码和媒体要求。逐项与当前实现比较。（步骤）
- [ ] 先用当前纯函数增加以下请求头行为回归，确认具体失败后修正编码。读取请求头时保持凭据脱敏。（步骤）

```python
import base64

from backend.modules.channels.wechat.account import ilink_headers


def test_wechat_uin_encodes_decimal_uint32():
    value = ilink_headers()["X-WECHAT-UIN"]
    decoded = base64.b64decode(value, validate=True).decode("ascii")
    assert decoded.isdecimal()
    assert 0 <= int(decoded) <= 0xFFFFFFFF
```

- [ ] 实现随机 uint32 的规范编码，并按端点核对应携带的头与认证。版本值以选定兼容代际和实际实现为依据，变更版本元数据时一并完成该代际必需行为回归。（拟定修改）
- [ ] 用 FakeTransport 分别返回 `ret=-14`、`errcode=-14` 及两字段组合，验证账号进入凭据失效/暂停状态、轮询停止或有界退避、面板提示正确、其他账号继续运行。（具体回归）
- [ ] 当前入站处理检查 `errcode`，同时核查官方参考对 `ret` 的处理。出站需共享账号凭据状态，等待期与恢复条件参照选定版本行为，持久化需求沿用当前账号生命周期设计。（拟定修改）
- [ ] 真实限流、认证拒绝、消息上下文失效、网络超时和未知投递结果分别分类。明确拒绝与暂停期间的消息保留，发送恢复前重新检查来源绑定与有效上下文。（步骤）
- [ ] 账号和会话级发送预算、消息分段、退避与通知合并复用现有 delivery 机制，重复事件和 Worker 进度经统一出口发送。（方案）
- [ ] 用已授权测试账号验证扫码、接收、短回复、长任务结果和解绑。群聊及主动发送分别核实实际能力，记录不具备的测试条件。（步骤）

```powershell
python -m pytest tests/channels tests/contracts/test_wechat.py tests/delivery -q
```

**验收**　协议差异均有处理依据，凭据失效提示正确且账号间隔离，重试有界，真实测试结果与模拟回归分开记录。（要求）

## 6. 工作包三 Acceptance 本地试验

**复用文件**　`E:\PythonCode\EasyChat\backend\modules\superagent\verification.py`、`worker.py`、`contracts.py`，`agent_frontend\src\views\SuperagentView.vue`，既有 P8 浏览器证据。（拟定集成位置）

- [ ] 在隔离验证环境固定 Acceptance skill/CLI 的版本或 commit，验证该组合的本地生成与反馈能力，记录所有依赖。先采用本地报告模式。（方案）
- [ ] 试验覆盖三个已有场景，聊天左右栏拖动与刷新恢复、超级代理表单间距、角色卡与编辑弹窗。复用有效 P8 证据，缺少证据的行为重新操作。（步骤）
- [ ] 每项记录需求、操作步骤、实际结果、截图或录屏、控制台日志、commit/tree、前端构建、视口、主题及执行时间。（证据要求）
- [ ] 拖动用录屏或连续截图呈现，角色弹窗验证点击、Tab/Esc 和窄屏滚动，表单在 1440、950、679 CSS 像素宽下检查布局。（具体试验）
- [ ] 缺少要求的证据时标记待验证，自动测试退出码与产品验收结果分别保留。（规则）
- [ ] 报告共享采用用户指定的访问范围。在线发布涉及上传的报告、截图和日志，应使用已授权目标，先核查敏感内容与访问控制。（执行条件）

**验收**　本地报告能展示并读取逐项反馈，一项打回后可以建立下一轮并复验，安装及运行问题有复现记录。（要求）

官方说明支持本地报告及独立使用，具体版本的行为以试验为准。（上游核查与验证要求）[Acceptance](https://github.com/lobehub/acceptance)

## 7. 工作包四 任务页集成验收与返工

**已有文件**　`E:\PythonCode\EasyChat\backend\modules\superagent\api.py`、`repository.py`、`routes.py`、`verification.py`、`agent_frontend\src\views\SuperagentView.vue`、`agent_frontend\src\api\superagent.ts`。（复用范围）

**按试验确认后新增**　如需独立验收业务模块，使用 `E:\PythonCode\EasyChat\backend\modules\acceptance\contracts.py`、`api.py`、`repository.py`、`routes.py`，在既有装配点注册。迁移编号按磁盘下一可用编号追加。实现前先记录为何现有报告结构无法充分承载该行为。（条件性设计）

- [ ] 确认最小数据关系为 task、attempt、验收项、轮次、证据及评审决定，已有报告和附件字段可复用时优先复用。（设计步骤）
- [ ] 检查项状态区分通过、失败、待验证、跳过，评审决定区分接受和打回；检查结果、PR 状态、人工审批分别展示。（拟定语义）
- [ ] 证据绑定代码版本、构建和环境，按文件或共享依赖变化使受影响证据失效。无法可靠判断影响范围时重新验证对应验收组，保留此前轮次。（拟定规则）
- [ ] 证据引用经现有文件授权路径读取，HTTP 接口检查 task owner、当前权限和附件归属，返回受控引用。HTML 报告采用隔离展示或静态渲染，检查脚本、外链及敏感日志。（拟定实现约束）
- [ ] 人工打回使用幂等操作键，在原任务追加输入并按现有生命周期创建必要 attempt。验证旧轮次反馈、重复点击、并发接受与打回的处理。（具体回归）
- [ ] 页面提供验收列表、轮次、证据预览和反馈入口，微信只汇总阻塞或完成信息，并给出受权限保护的任务页地址。（方案）

**验收**　一项打回能关联返工与新证据，历史记录可追溯，跨用户访问被拒绝，最终发布 SHA 与验收覆盖一致，前端有 Before/After。（要求）

## 8. 工作包五 主管汇总与复杂任务拆解

**文件范围**　`E:\PythonCode\EasyChat\backend\modules\superagent\api.py`、`repository.py`、`contracts.py`、`worker.py`、`runner.py`、`intake.py` 及对应前端任务页。（拟定范围）

- [ ] 先实现对已有任务的授权查询与摘要，主管依据任务、输入、报告和证据回答状态、卡点与下一步。摘要附依据，完整日志留在任务内。（最小交付）
- [ ] 对复杂需求增加父子任务、执行者、负责人及依赖关系，明确简单任务的直接执行路径。模型提出拆解，服务端校验身份、预算、依赖环和授权范围。（拟定设计）
- [ ] 父任务传递相关需求、约束和工件引用，子任务保存独立上下文和 attempt，汇总读取当前有效结果。检验跨 owner 引用与越权继承。（具体回归）
- [ ] 同一仓库并发先定义工作区、分支和集成顺序。父任务预算约束所有子任务的总执行量，依赖成功或失败决定后续任务的可运行条件。（拟定规则）
- [ ] 验证简单任务、两项独立子任务、串行依赖、子任务失败、父任务取消、主管重启和人工接管，已有 Draft PR 对账继续有效。（具体验收）

**验收**　主管能依据持久化事实回答进展，任务依赖合法，失败和取消传播明确，队列重投和晚到结果不重复推进任务。（要求）

## 9. 工作包六 事件策略与远程执行

### 事件策略

**复用位置**　`E:\PythonCode\EasyChat\backend\modules\channels\commands.py`、`api.py`、`backend\modules\superagent\intake.py`、`webhooks.py`、`backend\tools\business\superagent_tools.py`。（拟定范围）

- [ ] 规则处理来源、绑定、重复事件、机器人回声及确定性命令，必要的语义判断接收有限上下文，并返回受理、关联、追问或忽略。（拟定流程）
- [ ] 明确开发指令按已有授权执行，普通讨论及引用内容按具体语境判断。语义判断超时、格式错误或预算不足时保留事件状态和可解释结果。（拟定行为）
- [ ] 复用已实现的 webhook 自动修复和预算，核查 P7 记录后补缺口。人工暂停解除来源按仓库规则判定。（步骤）

### 远程执行

**接入位置**　现有 `E:\PythonCode\EasyChat\backend\modules\superagent\runner.py` 的 CodingRunner 接口。（源码依据）

- [ ] 对照 P4 隔离记录，用当前任务验证独立执行环境能否满足要求，再决定是否新增远程 Runner。（决策步骤）
- [ ] 远程执行设计写明设备身份、任务凭据范围、租约、心跳、输入幂等、取消确认、工件上传与晚到结果拒绝。数据库、渠道密钥和发布凭据由控制端管理。（拟定设计）
- [ ] 分别验证浏览器关闭、执行设备休眠、网络断开、控制端重启及工具进程残留，按真实存活状态展示运行、失联、等待恢复或已停止。（具体验收）
- [ ] 增加其他执行器时固定其版本，复用同一 CodingRunner 行为测试和实际任务比较。Hermes、Harness 或其他 CLI 的切换依据试验结果。（方案）

**验收**　事件处理可追溯且有界，执行设备失联可观察，取消可确认，结果归属与重启恢复一致。（要求）

## 10. 升级、回滚与最终验证

- [ ] 引擎、微信协议参考、Acceptance 工具、依赖和前端构建分别记录版本与组合。参考上游升级前生成差异，隔离验证后发布整套产物。（升级要求）
- [ ] 复用 P3 来源和补丁治理，保护必要自定义行为，追加迁移，并用旧数据库副本验证升级。（步骤）
- [ ] 以固定 baseline 评审授权、并发、事务、错误传播、资源回收、证据有效期和外部副作用，缺陷修复后重跑对应回归。（评审要求）
- [ ] 回滚先停止新任务派发，处理在途运行，核对分支、PR、投递和消费游标，再恢复匹配的代码与一致性数据快照。已发生外部副作用保留对账记录。（回滚要求）
- [ ] 使用已授权测试目标演练微信指令、追问补充、编码验证、Draft PR、原会话回执和单项打回，确认同一逻辑任务的关联完整。（实单验收）

```powershell
Set-Location E:\PythonCode\EasyChat
python -m pytest tests/channels tests/contracts/test_wechat.py tests/delivery -q
python -m pytest tests/superagent tests/contracts -q
python -m pytest tests -q -m "not integration and not resources"
Push-Location agent_frontend
npm test
npm run type-check
npm run build
Pop-Location
```

新增工作包的回归同步加入对应套件，纯静态检查、模拟运行、浏览器验收与真实渠道验收分别记录覆盖范围与退出码。（交付要求）

## 11. 依赖、范围与交付

推进顺序为接管复核 → 微信兼容性 → Acceptance 试验 → 任务页验收与返工 → 主管与任务依赖 → 事件与远程执行，每包以自己的验收结果交付。（建议顺序）

当前推荐近期沿用 Hermes、自托管本地验收报告和统一微信通知出口。是否使用独立 acceptance 模块、任务并发上限、远程执行协议及引擎切换由对应设计和试验结果确定。（本版设计选择）

复用上游代码时分别记录对应文件的版本、许可和保留声明。Acceptance 项目采用 Apache-2.0，LobeHub 主仓库采用 Community License，其商业衍生作品条款需要结合实际分发方式核查。（上游许可核查与执行要求）[Acceptance 许可](https://github.com/lobehub/acceptance/blob/main/LICENSE)、[LobeHub 许可](https://github.com/lobehub/lobehub/blob/canary/LICENSE)

任务拆解、远程设备和替换执行器按需求增量引入，既有确定性缺陷优先修复。缺少必要外部条件时完成可运行部分并记录具体剩余项。（执行约定）

每包输出基线、变更文件、依据、失败与通过证据、评审结果、Before/After、版本、回滚和待验证项，结论同句附证据或标注推断。（仓库要求）

## 12. 交给其他执行模型的提示词

```text
接管 E:\PythonCode\EasyChat，执行增量改造并完成验证与代码评审。

先读取 AGENTS.md、CLAUDE.md、EASYCHAT_HANDOFF.md，以及
E:\PythonCode\EasyChat\docs\superpowers\plans\2026-11-11-wechat-task-acceptance-evolution.md。
同时读取上一版总计划和 docs/reviews/2026-11-10/P0 至 P8 的实施记录。

用户目标是通过微信明确下达开发任务后，自动编码、验证和创建 Draft PR，回复原会话，人工评审与合并。近期沿用 Hermes，增加可观察验收、任务协作和可验证升级能力，其他引擎根据试验复评。

先记录 HEAD、分支、工作区差异、部署和活跃任务，保留已有修改。复核历史记录对应当前代码，已有且通过的能力只记录证据，确认缺口后实施最小修改。

按新计划工作包依次推进。
1. 接管与既有结果复核。
2. 微信协议核查、请求头与版本兼容、扫码绑定、凭据生命周期和错误分类。
3. Acceptance 固定版本的本地试验，覆盖聊天拖动、超级代理间距、角色卡与权限弹窗。
4. 任务页接入逐项验收、证据、轮次、接受与打回，以及原任务返工。
5. 主管依据持久化任务汇总，复杂需求再增加父子任务、依赖、负责人和预算。
6. 规则与语义结合的事件策略，按需要接入远程 Runner 和其他执行器。
7. 升级治理、全部差异评审、真实闭环和回滚演练。

微信重点
对照腾讯官方固定 commit 的协议参考与实现。
https://github.com/Tencent/openclaw-weixin/blob/main/docs/protocol.md
https://github.com/Tencent/openclaw-weixin/blob/main/src/api/session-guard.ts
当前 X-WECHAT-UIN 使用时间戳字符串，需验证随机 uint32 十进制字符串的 Base64 编码要求。
当前 -14 文案为风控/频率限制，应核查为 bot token 失效/过期，覆盖 ret 和 errcode，并统一入站/出站的账号暂停与恢复语义。
版本变更绑定实际支持的协议代际，请求头、扫码流程和服务端返回码一起验证。
凭据失效、真实限流、发送上下文失效、网络超时和投递 uncertain 分别分类。
封号判断引用官方规则和实际证据，协议兼容性问题按其真实含义说明。

验收重点
Acceptance 先验证本地报告，固定依赖版本，实际操作产品并生成截图、录屏与日志。
参考 https://github.com/lobehub/acceptance。
证据绑定 task、attempt、验收项、轮次、commit/tree、构建、环境和时间。
缺少规定证据标记待验证。代码或环境变化后核查原证据的有效范围。
人工打回进入原任务，重复反馈幂等，跨用户证据访问拒绝。
线上发布报告使用已授权目标与范围，核对敏感信息和访问控制。

架构与执行约束
复用 ExecutionRuntime、CodingRunner、SuperagentWorker、任务账本、文件授权和 delivery。
身份来自 Principal/ToolContext 和服务端来源，服务端验证任务与附件归属。
每包先复现具体缺口，再最小修复、回归和评审。普通可逆选择按现有授权推进。
核对已有人工授权，已覆盖范围继续完成。protected paths 按 AGENTS.md 交付草稿与升级简报，继续可独立完成的安全区工作。
SQLite WAL 守卫有效，迁移只追加，事务内无外呼，能力默认关闭，审批 fail-closed。
取消、重试和恢复先对账在途运行与外部副作用，旧 attempt 结果不能覆盖新任务状态。
主管统一汇总通知，子任务继承受限授权与总预算，人工暂停解除遵循仓库规则。
保留当前产品功能与历史数据，所需新模块、依赖和接口先说明具体必要性。

验证
python -m pytest tests/channels tests/contracts/test_wechat.py tests/delivery -q
python -m pytest tests/superagent tests/contracts -q
python -m pytest tests -q -m "not integration and not resources"
前端执行 npm test、npm run type-check、npm run build。
新增具体回归纳入所属套件。UI 修改提供同场景 Before/After 和真实浏览器操作证据。

最终给出修改文件、问题依据、验证命令与退出码、评审发现与修复、版本和回滚、实际外部验收结果、剩余项和续作条件。结论附证据或标注推断。
```
