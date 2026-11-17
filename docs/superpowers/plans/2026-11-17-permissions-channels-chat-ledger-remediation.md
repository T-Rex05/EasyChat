# 权限、渠道、聊天与账单整改实施方案

日期为2026-11-17。审查基线为HEAD `579db03` 加当前工作区。本文交付代码审查、修改方案和执行提示词，实施尚待执行。（范围与Git实测）

执行模型可使用 executing-plans 按下列工作包推进，每包先复现、再最小修改、回归、评审。技术栈沿用现有Vue/TypeScript、FastAPI、SQLite和Hermes运行时Seam。（实施方案）

## 1. 审查结论与证据边界

| 优先级 | 已确认问题 | 依据 |
|---|---|---|
| P1 | 账单把分类笔数当金额，精准产生385、33、10三项错误总额 | CSV/XLSX合成428行入口实测，normalization.py:298–325 |
| P1 | 撤销权限后，本人技能固定/归档、提醒停启、本人用量接口仍可调用 | 临时SQLite和真实HTTP路由实测 |
| P1 | GET聊天流隐藏HTTP失败原因，重连终态未关闭连接，error字段失配 | 前端内存harness实测、chat.ts:210–247及493 |
| P1 | 模块未装配时，认证和ticket成功仍可同时遇到channels503与assistant503 | 临时rig+真实应用HTTP实测 |
| P2 | 权限复选框与高级预设下拉重复，预设关闭可能留下管理授权 | RoleEditDialog.vue:30–115、233–239 |
| P2 | 编码代理capabilities推导read与真实查看权限不一致 | create单独授权的服务实测，access/api.py:413及superagent/api.py:275 |
| P2 | 升级条目缺少内边距和窄容器换行，内部权限分组错位 | 用户截图、UpgradePreviewPanel.vue样式、permissionGroups.ts:53 |

已实测出模块未装配导致两项症状的组合，但未取得用户当前失败流的真实HTTP响应，也未核对当前进程加载的全部开关。用户真实账单原件未经读取，精准复现使用合成数据。当前浏览器布局依据用户截图和源码，实施时仍需同场景Before/After。（证据边界）

本轮审查发现的权限问题是动作授权与撤权一致性缺口。已检查核心模块另有owner边界，尚未证明所有入口和全部组合均完成越权隔离验收。（实测与覆盖限制）

## 2. 接管与约束

- [ ] 读取AGENTS.md、CLAUDE.md，记录HEAD、diff、运行版本及启动命令。当前已存在index.html、AppSidebar、MessageBubble、main.ts、design-system.css、ChatView、LoginView修改，以及新增useTheme.ts，保留这些工作。（Git实测、步骤）
- [ ] 认证/权限、调度、运行时、外发、存储迁移、公共contracts等protected paths按仓库要求交付可评审草稿及升级简报，写清停因、证据、剩余和续作。可独立完成的前端、文档及测试继续推进。（AGENTS要求）
- [ ] 能力默认关闭、AES-GCM凭据、ToolContext身份、事务内无外呼、追加迁移、WAL守卫继续作为验收条件。诊断只记录开关布尔值与secret是否存在，避免输出凭据值。（仓库要求与诊断方案）
- [ ] 不从历史根目录测试显式选入已被conftest默认排除的旧架构套件。本轮初次误选旧测试遇collection/fixture错误后已停止，以下通过数来自维护中目录。（本轮验证记录）

## 3. WP-A　修复账单控制总额源头

**修改范围**　`backend/modules/ledger/normalization.py`、`parsers/wechat_csv.py`与`wechat_xlsx.py`调用点按需核查，`agent_frontend/src/api/ledger.ts`、`views/LedgerView.vue`。测试扩展`tests/ledger/test_parsers.py`、`test_import_flow.py`及前端账单行为测试。（方案）

### 已复现输入

```text
共428笔记录
收入：33笔 10410.86元
支出：385笔 23708.48元
中性交易：10笔 9518.11元
```

共享正则抓标签后第一个数字，再交parse_money，结果expense_minor=38500、income_minor=3300、neutral_minor=1000。正确金额应为2370848、1041086、951811分。完整CSV/XLSX均428行、零坏行，并生成用户同款三条不一致提示。（实测，normalization.py:299–325、api.py:1373–1383）

- [ ] 增加失败回归，调用真实CSV/XLSX入口，断言三类金额及总笔数。另测`支出：385笔，共23708.48元`不会产生总笔数23708。（实测缺陷对应测试）
- [ ] 在共享函数区分笔数字段与金额字段，支持分类后可选笔数再跟金额、既有直接金额格式、千分位、零值及空摘要。只有笔数时金额保持None，不能让错误首值抢占后续正确摘要。（最小修复方案）
- [ ] 明确摘要区域和金额语义，避免把日期、统计周期或交易明细首个数字当总额。对歧义输入返回可说明的缺失/警告状态，真实金额差异继续阻止普通提交。（回归要求）
- [ ] 对齐UI与后端字段。LedgerView.vue:57读取differences，实际api.py:387提供mismatches/detail，api/ledger.ts:46的声明也需同步，展示实际差异。（源码证据与步骤）
- [ ] 修正“再次提交并允许差异”的不可达交互。当前LedgerView.vue:357没有传confirmMismatch，api/ledger.ts:121默认false。正常摘要错误先修解析并重核验；若保留显式差异确认，必须有独立确认动作、实际差异清单和明确payload，禁止自动或默认confirm_mismatch=true。（源码证据与方案）
- [ ] 修复后对未提交批次使用已有`POST /api/ledger/imports/{import_id}/parse`刷新解析与核验，验证候选重建、幂等和owner边界。已提交批次保留现有状态机限制，单独评估受影响范围。（routes.py:201–208、api.py:373–401与方案）

**通过条件**　合成样例金额精确到分，CSV/XLSX均可正常核验；真实差异仍阻止普通提交；现有未提交批次可重解析修复，无重复入账。（验收要求）

## 4. WP-B　渠道装配状态与配置体验

**修改范围**　`backend/bootstrap.py`、`backend/app.py`和现有配置/能力API按实际职责选取，`agent_frontend/src/api/platform.ts`、`views/ConfigView.vue`，增加启动组合与配置页测试。（方案）

runtime在hermes_enabled时构造，assistant要求runtime+access，channels还要求wechat_enabled、assistant、access及加密secret。默认开关为false；app.py:64将None模块转为503。ConfigView.vue:790直接加载accounts，:798只console.error，readyz仅标记启动已完成。（bootstrap.py:171、220、343–375，platform/settings.py:25、45，源码核查）

- [ ] 先核对当前运行实例加载版本、配置来源、hermes_enabled/wechat_enabled、secret是否存在及启动错误摘要。区分功能关闭、依赖缺失、初始化失败和监听运行状态，不从readyz推断全部模块可用。（诊断步骤）
- [ ] 复用现有能力/配置状态机制提供脱敏的模块状态和原因。授权能力与运行可用状态分别呈现，后台仍执行权限校验。当前缺少字段时再提出最小公开契约草稿。（方案）
- [ ] 配置页在渠道关闭时展示原因、必要配置项与重新检测入口；accounts请求失败有可见错误，避免残留旧状态或无限loading。（前端方案）
- [ ] 明确首次启用方式与是否需重启，遵守现有部署设置加载机制。经授权的启用后再验登录/绑定/监听，保留默认关闭和缺密钥拒绝行为。（实施与验收要求）
- [ ] 覆盖开关关闭、secret缺失、runtime关闭、正常装配、初始化异常。若当前架构必须依赖Hermes，界面明确显示此依赖；渠道管理与监听解耦只在确有需求时另行设计。（范围控制）

**通过条件**　用户能从配置页知道当前阻塞原因，修复对应条件后真实模块就绪。配置展示不泄露凭据，失败请求保持明确HTTP状态。（验收要求）

## 5. WP-C　聊天真实错误与SSE生命周期

**修改范围**　`agent_frontend/src/api/chat.ts`、`composables/useChat.ts`及实际调用者，按需核查`backend/modules/assistant/routes.py`。测试`tests/chat-sse-recovery.test.mjs`、后端`tests/contracts/test_web_chat.py`和`test_sse.py`。（方案）

认证和ticket仅证明access可用。GET stream可能返回409/422/503/500，EventSource error没有HTTP状态，当前恢复只探测auth并最终显示泛化文案。后端发`{type:error,message}`，前端chat.ts:493只读error，已实测显示“未知错误”。重试额度耗尽时连接仍可处于CONNECTING。（源码与harness实测）

- [ ] 保留脱敏的失败HTTP状态、run_id、client_msg_id及服务端错误，不记录ticket/token。先关联当前现场失败与模块状态，确定是请求前失败还是运行中断流。（诊断步骤）
- [ ] 让真实HTTP响应可见。优先评估复用现有POST fetch流并统一文本/附件调用，确保其事件解析与恢复行为完整；如保留GET，提供能保真传播失败状态的有限请求流程。单独预检不能替代对实际流请求失败的处理。（方案选择）
- [ ] error事件读取message，并在确有旧调用时兼容error。终态失败显示真实错误，结束当前连接和状态，避免随后被通用断流提示覆盖。（最小修复方案）
- [ ] 恢复开始立即关闭旧EventSource，增加单一恢复中的互斥和连接代次标识，丢弃晚到回调。认证失败、额度耗尽、用户停止、完成和错误均收敛到关闭状态。（方案）
- [ ] 保持同一client_msg_id与last_seq续传，新ticket一次性使用；退避有界。测试断开后没有第二次模型运行或重复计费。对429/认证/不可用配置按具体状态决定恢复，避免无效重试。（验收要求）
- [ ] 补测HTTP 409/422/503、后端error.message、首次无token事件失败、输出后断开、连续error并发、终态CONNECTING关闭、完成后正常关闭、切页返回和手动停止。（回归要求）

**通过条件**　实际原因可见，所有终态连接关闭，正常完成与切页恢复不报假错误，同一任务不会重复执行。（验收要求）

## 6. WP-D　权限动作、数据范围与撤权

### 已审查目录与缺口

当前目录22项active与2项deprecated，见`backend/modules/access/contracts.py:35、78–117`。下面为入口核查概览，完整HTTP/工具/后台任务组合仍需矩阵验收。（源码与覆盖限制）

| 权限组 | 已找到的服务端约束 | 本轮发现或剩余验证 |
|---|---|---|
| chat.use | assistant/api.py:176、dispatcher.py:297，channels/api.py:617 | 补撤权后入站及运行中行为 |
| memory.view/edit | memory/api.py:69及读写入口、profiles/api.py:175/198，owner查询 | 套件通过，补通道一致性 |
| skill.create/manage、evolution.view | skills/api.py:96–106、evolution/api.py:130 | pin/archive漏动作检查 |
| cron.create | scheduling/api.py:81创建检查 | 已有提醒停启等入口漏动作检查 |
| ledger.view/import/edit/export/manage | ledger/api.py:253/279/695/722/1070，owner查询233/236 | ledger.manage当前范围仍为本人 |
| superagent.view/create/manage | superagent/api.py:130/188/275/451–466 | 能力聚合与原子组合不一致 |
| trace.view/manage | usage/api.py:154–169、跨用户需manage | 本人calls/detail/daily漏view检查 |
| system.manage | access/api.py:434起、owner保护377 | 补跨模块和缓存失效矩阵 |
| system.config | models/api.py:123–125、SMTP相关入口 | 配置套件通过，补各入口一致性 |
| file.upload/read/delete | files/api.py:212/366/444及owner103 | 核查跨用户授权与派生产物 |
| terminal.audit、evolution.manage | policy.py过滤退役键 | 不再作为可新增授权项 |

普通账号撤销skill.create/skill.manage/cron.create/trace.view/trace.manage后，有效集合与五键交集为空，但技能PATCH、提醒PATCH、用量calls/detail/daily返回200，对照ranking及技能新版本返回403。（临时SQLite+ASGITransport实测）

**修改范围**　`modules/skills/api.py`、`modules/scheduling/api.py`、`modules/usage/api.py`，`modules/access/api.py`能力聚合，实际tools/worker和路由入口逐项核查；公共契约修改先形成草稿。（方案）

- [ ] 在现有维护中测试补三类撤权回归。技能固定/归档复用现有write检查；提醒管理匹配“建立与管理本人提醒”的已定义权限；本人用量读取要求trace.view或trace.manage。（建议的明确行为）
- [ ] 每个操作同时满足动作权限与资源范围，复用现有Access检查和owner过滤。本人资源归属本身不能代替动作授权，manage也仅在该域已定义范围内生效。（目标语义）
- [ ] 对提醒的读取、删除、occurrences逐项写明所需权限。检查worker取任务与外发前的当前身份/权限行为，复用现有无人值守守卫，避免把Web修复扩成隐式取消全部既有任务。（方案与范围）
- [ ] 增加普通角色A/B及管理角色测试，覆盖无权限、本人、他人、管理、显式revoke、撤权立即生效、禁用账号、过期凭据、直调API。HTTP、微信命令、工具与worker入口分别列证据，全部active键须有对应行。（矩阵验收）
- [ ] 退役键保持审计与过滤语义，旧角色与用户覆盖不自动授予新增权限。检查role更新及用户override后的缓存失效；super_admin全集是现有特殊策略，负向验收使用普通角色。（policy.py:30及方案）

### 编码任务查看与权限组合

“查看编码任务”位于左侧“超级代理”即`/superagent`。页面显示列表，展开任务查看事件和验收。普通view用户仅查本人；view+manage可查全局；创建需要create，仓库/凭据配置需要manage，后端任务详情共用_task_for检查。（AppSidebar.vue:158、router/index.ts:45、SuperagentView.vue:9/104/126/158、superagent/api.py:269/451）

- [ ] 明确view/create/manage三项独立语义。建议capabilities对superagent.read以真实view计算，创建和配置按钮依据对应动作，导航与实际API保持一致，不自动向历史角色补view。（方案选择）
- [ ] 测试三键的8种组合，包含只create与只manage。角色编辑展示相关操作与页面查看前提，不能用自动扩大授权掩盖组合缺口；配置子页按真实管理动作权限访问。（验收要求）
- [ ] 任务列表、详情、事件、报告下载、attempt、取消、重试、输入和验收决策均覆盖owner与动作检查。失败请求无任务、文件和远端PR副作用。（验收要求）

## 7. WP-E　角色编辑去重与布局

**修改范围**　`views/admin/RoleEditDialog.vue`、`UpgradePreviewPanel.vue`、`utils/permissionGroups.ts`、相关前端测试。已有共享设计系统修改在本轮基线中，定位具体选择器后做局部改动。（方案）

- [ ] 删除高级区功能预设下拉及该组件专用模式同步状态/处理函数，保留分组复选框为授权编辑入口。工具能力保留独立分组复选框。共享工具函数若仍有其他调用者则保留。（用户要求与最小改动）
- [ ] 权限分组依据module/group_name，文件依赖组仅收文件项。ledger.manage虽internal也回到账单组，标注当前本人范围。各项展示中文名称、本人/全局范围和必要风险提示，长说明自然换行。（源码缺陷与方案）
- [ ] 保留form.permissions和原工具集合，开窗、只改名称、取消、直接保存均验证集合稳定；定义加载失败时避免清空字段。历史键按后端允许策略可见，退役键不提供新授予。（回归要求）
- [ ] UpgradePreviewPanel增加容器内边距。标题、待升级数量、展开按钮使用可换行布局，窄容器改纵向排列，按钮有可访问名称和展开状态，摘要可键盘触发。（用户截图与方案）
- [ ] 升级详情按角色分组，先显示差异数量与高风险数量，展开后显示中文名和key；长key换行，操作独立一行。普通管理者可查看说明，owner确认升级的现有边界保持有效。（方案）
- [ ] 复选框不收缩，说明占据可换行列，label有足够点击区域，保留Tab/Space焦点与禁用状态。弹窗正文滚动时头尾操作保持可达。（布局验收）
- [ ] 在727×685、用户截图对应宽度及桌面宽屏验证，另补320 CSS px或200%缩放。提交同账号、同数据、同主题、同滚动位置Before/After，检查长说明、风险徽标和历史权限。（UI验收要求）

## 8. 测试现状与执行顺序

本轮实际完成下列验证，现有测试未捕获上述新增复现行为，执行者必须补行为用例。（实测）

| 命令范围 | 结果 |
|---|---|
| tests/ledger/test_parsers.py + test_import_flow.py | 43 passed |
| tests/contracts/test_web_chat.py + test_sse.py | 13 passed |
| tests/access、superagent HTTP/service/acceptance、files、memory、skills、profiles、ledger identity/API | 310 passed |
| tests/usage、delivery/test_schedule.py、auth契约、channels开发命令、superagent/ledger工具 | 62 passed |
| agent_frontend npm test | 61 passed |
| agent_frontend npm run type-check | 退出码0 |

不同命令中存在路径重叠，表内按各次结果报告，不累计为去重总数。另有前端SSE定向9项及后端精简42项重叠验证，不另计。（统计口径）

建议先完成WP-A和WP-C的失败回归，再推进WP-B真实装配状态和WP-D授权矩阵，最后统一WP-E界面与全流程验收。各包可独立评审；受保护实现按AGENTS升级，其他可独立交付部分继续完成。（实施顺序）

```powershell
Set-Location E:\PythonCode\EasyChat
python -m pytest tests/ledger/test_parsers.py tests/ledger/test_import_flow.py tests/contracts/test_ledger_api.py -q
python -m pytest tests/contracts/test_web_chat.py tests/contracts/test_sse.py -q
python -m pytest tests/access tests/skills tests/usage tests/delivery/test_schedule.py tests/contracts/test_superagent_api.py tests/superagent/test_superagent_service.py -q -m "not integration and not resources"
python -m pytest tests -q -m "not integration and not resources"
python -m pytest tests/superagent tests/contracts -q
Push-Location agent_frontend
npm test
npm run type-check
npm run build
Pop-Location
```

新测试纳入现有套件。最终报告逐包列变更、失败复现、通过命令和退出码、UI对照、真实外部测试与待验证项。真实微信、模型和远端PR运行仅在已有授权环境执行，隔离测试明确标注。（交付要求）

## 9. Modern Web Guidance

本轮检索并阅读checkbox与form-factor-adaptation指南，布局方案采用关联label、可点击区域、容器内换行和文本自适应；尚未修改或验证界面实现。（使用范围）

## 10. 对接执行模型的提示词

```text
接管 E:\PythonCode\EasyChat，按以下计划修复并验收本轮反馈。
先读取 AGENTS.md、CLAUDE.md 和
E:\PythonCode\EasyChat\docs\superpowers\plans\2026-11-17-permissions-channels-chat-ledger-remediation.md。
记录实际HEAD、已有dirty改动和进程版本，保留其他工作。本轮审查基线579db03，使用当前代码复核。

工作包A　修复共享账单摘要解析，把“385笔 23708.48元”等笔数与金额分开；CSV/XLSX真实入口补失败回归。修正前端mismatches/detail契约与差异确认交互。未提交旧批次通过已有parse接口重核验，保持真实金额差异守卫和幂等。
工作包B　核对运行实例hermes/wechat开关、加密secret是否存在和装配条件。配置页显示渠道关闭/依赖缺失/初始化失败的真实原因及恢复步骤，保留默认关闭。readyz和认证成功不能当模块可用证据。
工作包C　让实际聊天流HTTP失败与error.message可见。修复恢复流程互斥、旧连接关闭、晚到回调和所有终态关闭。保持原client_msg_id、续传游标和一次性ticket，不重复模型执行或计费。保留HTTP409/422/503等原因。
工作包D　补撤权后技能pin/archive、提醒停启等管理、本人用量calls/detail/daily的HTTP回归，按动作权限+owner统一现有服务检查。建立22项active权限的入口/动作/数据范围/撤权矩阵，覆盖HTTP、微信、工具与后台入口。编码代理view/create/manage八种组合与capabilities、菜单、任务列表一致，保留原子授权和历史角色，不自动扩大授权。
工作包E　角色编辑只保留分组权限复选框及独立工具复选框，删除重复预设下拉和专用同步逻辑。ledger.manage回到账单组。修复权限模板升级面板内边距、换行、键盘展开与窄屏布局。提供同场景Before/After。

先复现并保存失败证据，再做最小实现，每包定向回归与代码评审。运行计划的后端测试、前端test/type-check/build，完成浏览器真实交互。
protected paths按AGENTS交付草稿与升级简报并等待人工续作授权，可独立安全工作继续完成。保持WAL守卫、追加迁移、事务内无外呼、ToolContext可信身份和加密凭据。
不要把合成复现当成用户现场已验证；当前真实SSE状态、渠道进程开关、真实原账单仍需各自确认。现有通过测试没有覆盖本轮缺陷，必须补行为回归。
最后交付逐包修改与依据、命令退出码、权限矩阵、UI对照、评审与复验、真实外部测试和未完成项。受保护草稿列明具体文件、停因、证据及续作步骤。
```
