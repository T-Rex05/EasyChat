# 聊天恢复、用量权限、技能、微信记忆与提醒整改方案

日期为 2026-11-13。本轮交付核查结果、执行方案及模型交接提示词，以下工作包由后续执行模型实施并验证。（交付范围）

## 1. 证据与判断

| 用户问题 | 本轮确认结果 | 仍需核实 |
|---|---|---|
| 回答中切页面再回来丢失回复 | 确认连接清理按动态当前会话执行、异步历史写入缺chatId、残缺缓存跳过对账，隔离实验复现A完成误关闭B连接 | 用户截图对应的真实跨路由事件顺序 |
| 时间与查看他人调用 | UsageView直接渲染UTC原文，后端trace.manage和按owner查询仍存在，前端缺少独立明细入口 | 当前各角色有效授权与全局明细实际展示范围 |
| 技能列表为空及示例测试 | 技能服务支持版本/激活，普通聊天RuntimeRequest固定skill_versions=()，上下文未见激活技能内容接线 | 所选技能的工具/依赖可用性、真实产物能力 |
| 微信里记住后无回复、无记录 | 复现生成器空文本导致零记忆却标job成功；失败/取消run没有完成回执接线 | 用户现场对应run、memory job和delivery状态 |
| 微信里创建提醒无回应 | reminder工具已有注册和schema暴露；模型失败、工具失败和投递失败需要分别定位 | 用户现场是否实际调用工具、权限/绑定/开关状态 |

前端证据在 `E:\PythonCode\EasyChat\agent_frontend\src\composables\useChat.ts:243`、`:405`、`:425`、`:439`、`:472` 及 `stores\chat.ts:98`、`:109`。隔离实验执行真实useChat和Pinia store，仅替换API。（源码核查与隔离实测）

用量证据在 `E:\PythonCode\EasyChat\agent_frontend\src\views\UsageView.vue`、`backend\modules\usage\api.py` 和 `backend\modules\access\contracts.py:133`，权限仍为trace.view与trace.manage。（源码核查）

技能证据在 `E:\PythonCode\EasyChat\backend\modules\assistant\dispatcher.py:311`、`runtime\hermes\adapter.py:133`、`runtime\hermes\skills_bridge.py`。技能文本可保存与运行请求实际采用技能需分别验收。（源码核查）

微信证据在 `backend\modules\memory\worker.py:64`、`:163`、`:189`、`backend\integrations\llm.py:42`、`backend\bootstrap.py:195`、`:533`、`:584` 和 `backend\modules\assistant\dispatcher.py:240`。（源码核查）

### 已执行验证

- `python -m pytest tests/usage tests/contracts/test_toolset_exposure.py tests/channels/test_development_commands.py tests/skills -q` → `56 passed in 25.84s`。（本轮实测）
- `python -m pytest tests/memory/test_explicit_capture.py tests/tools/test_reminder_tools.py -q` → `15 passed in 9.59s`。（本轮实测）
- 临时SQLite、真实MemoryWorker/JobQueue、人工输入“记住：我喜欢少糖咖啡”，空生成器得到memory_count=0且job=succeeded，generator=None时同输入生成1条记忆。（隔离实测）
- 真实useChat/store与替身API执行“A发流→B发流→A完成”，B连接被关闭、streaming和pending清除，B助手消息为空，返回时历史请求被缓存短路。（隔离实测）

上述结果用于确定缺口，真实微信链路与浏览器跨路由时序仍须执行模型验证。（验证范围）

## 2. 接管与实施约定

- [ ] 读取AGENTS.md、CLAUDE.md和本计划，记录HEAD、分支及工作区差异，保留架构文档、图片等已有修改。（步骤）
- [ ] 检查已有人工授权，在许可范围内完成工作。protected paths 依仓库规则交付草稿、行为回归与升级简报，前端等可独立工作继续推进。（仓库约束）
- [ ] 排障通过入站事件、owner、session、run、job和delivery关联，日志仅保留必要脱敏元数据，真实消息和凭据避免写入报告。（方案）
- [ ] 对具体缺陷先保留失败证据，再最小修复、定向验证及评审。已通过的旧测试不能替代本计划的新场景。（执行约定）

## 3. 工作包A 聊天连接与消息恢复

**修改位置**　`agent_frontend/src/composables/useChat.ts`、`stores/chat.ts`、`views/ChatView.vue`，必要时涉及 `api/chat.ts`。（拟定范围）

- [ ] 在测试后端或受控SSE中复现“流中离开chat→进入skills或trace→完成前/后返回”，记录连接数、chatId、运行标识和事件顺序。（复现步骤）
- [ ] 连接、pending和清理绑定发送所属的chatId及运行标识。旧运行完成或报错只清理自己登记的连接和状态，避免关闭后启动的其他运行。（最小修改）
- [ ] 历史请求显式写入请求对应chatId，并校验请求代次，晚到历史不能覆盖请求发出后产生的流式或完成消息。（最小修改）
- [ ] 跨页面维持稳定的连接所有权，返回页面复用有效流；失效连接依据pending与服务端运行状态重连。现有传输句柄可复用时保留其结构。（方案）
- [ ] 用户消息或空助手占位构成的残缺缓存需要对账，完整缓存与活跃流避免重复覆盖。最终事件按消息或运行身份upsert助手结果。（方案）
- [ ] 补充发送、停止、出错和组件卸载的资源释放检查，页面离开与用户取消保留各自语义。（步骤）

**回归矩阵**　完成前返回、完成后返回、A完成/B继续、A报错/B继续、A历史晚到/B当前、同会话旧完成晚到、新旧连接交叠、断流恢复、刷新、GET短消息与POST长消息/附件，两类传输均验证。（验收要求）

**通过标准**　回复自动出现，其他运行持续输出，无重复发送，历史归属正确，连接数量受控，并有同场景Before/After或录屏。（要求）

## 4. 工作包B 时间与独立全局用量页

**修改位置**　`agent_frontend/src/views/UsageView.vue`、`router/index.ts`、`components/AppSidebar.vue`、`views/admin/RoleEditDialog.vue`、权限模式映射；新增 `src/views/UserUsageView.vue` 和 `src/utils/dateTime.ts`，后端复用 `modules/usage/{api,repository,routes}.py`。（拟定范围）

- [ ] 将时间展示为 `YYYY-MM-DD HH:mm`。建议优先采用用户时区，缺失时采用Asia/Shanghai，并显示时区口径，存储保持UTC。（本版展示选择）
- [ ] 格式化处理空值、无效值、Z、带偏移及经项目确认的旧时间格式。用户示例 `2026-11-13T07:19:35.942+00:00` 在Asia/Shanghai显示 `2026-11-13 15:19`。（具体验收）
- [ ] 个人用量页显式请求本人owner，避免trace.manage用户默认拿全量却呈现为“我的调用”。全局范围采用独立页面，建议路径 `/trace/users`，受trace.manage保护。（拟定界面及路由）
- [ ] 全局页提供全部/指定用户、分页、模型/状态等已支持的筛选及调用详情。新增筛选参数先核查repository现有支持，必要时补窄接口。（方案）
- [ ] 用户选择仅返回该管理权限需要的ID与显示名称。若现有用户列表要求system.manage，应通过usage域提供最小用户选项接口，避免扩张授权。（方案）
- [ ] 角色编辑页显示“查看本人用量与排行”和“查看全部用户调用”等清晰文案，保持trace.view/trace.manage现有键及作用范围。模块简化模式与高级授权往返保存一致。（方案）
- [ ] 明细与用户选择API重新检查有效授权，覆盖无token、普通用户、trace.view、仅trace.manage、super_admin、撤销后访问和手改owner_id。（具体回归）
- [ ] 时间显示与日汇总的统计时区分别说明；此次先保持现有汇总定义，若调整统计日边界另列数据兼容设计。（范围选择）

**通过标准**　时间符合用户要求，个人和全局范围清楚，授权用户可进入独立页，未授权请求由后端拒绝。（要求）

## 5. 工作包C 示例技能与真实运行接线

### 来源与样例

已检索两个可参考来源，导入时固定commit、保留来源和许可信息。（本轮检索与方案）

| 样例 | 官方来源 | 测试任务 |
|---|---|---|
| PDF处理 | https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md | 生成一页中文PDF，再提取标题并核对页数 |
| 表格处理 | https://github.com/anthropics/skills/blob/main/skills/xlsx/SKILL.md | 生成含公式的支出表并校验结果 |
| 中文结构化摘要 | 本项目编写的最小测试技能 | 将人工文本输出为固定字段，用于验证注入和版本切换 |

本轮查看到pdf和xlsx各自LICENSE.txt为Apache-2.0，执行时重新固定所用版本的条款。样例正文、辅助脚本与资源需一起检查，外部skill中的安装环境假设按本项目实际能力改写并记录变更。（来源核查与方案）[PDF许可](https://github.com/anthropics/skills/blob/main/skills/pdf/LICENSE.txt)、[XLSX许可](https://github.com/anthropics/skills/blob/main/skills/xlsx/LICENSE.txt)

### 实施

**修改位置**　`backend/modules/assistant/dispatcher.py`、`backend/bootstrap.py`、`backend/modules/skills/api.py`、`runtime/hermes/{adapter,skills_bridge}.py`、`agent_frontend/src/views/SkillsView.vue`。（拟定范围）

- [ ] 先用最小中文摘要技能验证创建、版本、激活、运行请求快照和实际模型输入，复现当前空skill_versions接线缺口。（步骤）
- [ ] 在可信owner作用域查询已激活、未归档技能，固定本轮版本和内容，按当前RuntimeRequest/上下文接口最小接线。版本摘要与实际内容必须来自同一快照。（方案）
- [ ] 缓存键包含有效技能版本，激活/回滚仅影响下一轮。验证归档、空技能、跨用户访问、角色权限及失效缓存。（具体回归）
- [ ] 通过SkillService或现有HTTP入口为指定测试用户导入样例，重复执行遵循现有版本语义，既有同名技能需要比较内容并明确操作，记录创建的资源ID。（步骤）
- [ ] 先验证PDF/表格所需工具、依赖、字体、脚本和工件读取权限，使用隔离执行环境。缺失能力时准确记录结果并返回可读原因。（步骤）
- [ ] 真正生成PDF并打开/解析，表格检查公式和值，页面提供通过既有文件授权读取的产物。技能文本不扩大工具或文件授权。（验收要求）
- [ ] 使用两个用户验证技能与产物隔离，保留样例来源、版本、测试输入和结果。可选加载策略只在确有规模需求时设计，先完成现有快照接入。（方案）

**通过标准**　技能在页面可见，激活版本进入实际请求，修改/回滚后下一轮采用正确版本，产物能被独立工具验证。（要求）

## 6. 工作包D 微信记忆可靠写入与确认

**修改位置**　`backend/modules/memory/{capture,worker,api}.py`、`integrations/llm.py`、`bootstrap.py`、`modules/channels/{api,commands}.py`、`modules/assistant/dispatcher.py`、`modules/delivery/api.py`。（拟定范围）

- [ ] 使用临时rig覆盖当前空生成器实验，增加非法JSON、生成器异常及辅助模型未配置场景，分别断言记忆、job和回执状态。（失败回归）
- [ ] 明确“记住…”优先复用candidate_from_user_message进行确定性提取和授权写入，普通隐式信息继续走后台抽取。明确写入时机及与原后台capture的幂等关系，设计评审后实施。（本版建议行为）
- [ ] 写入在可信来源及memory.edit校验后发生，稳定source event/run作为来源和去重依据，保留可追溯SourceRef。微信绑定的owner与Web当前账号核对一致。（方案）
- [ ] 辅助抽取区分确实无候选、模型不可用、输出非法与持久化失败，按错误性质决定跳过或有界重试，状态可诊断。（方案）
- [ ] 业务确认在持久写入后产生，失败保留明确原因。明确记忆确认与普通聊天回复的协调规则，保证重复事件不重复记录或重复确认。（方案）
- [ ] run失败、取消和完成空回复均有终态处理，按有效目标与delivery策略产生可读反馈。取消反馈尊重用户意图及原会话归属，不能复活运行。（方案）
- [ ] 实单按event→run→capture/job→memory→delivery逐段定位，凭据、绑定和上下文失效单独呈现。（步骤）

**通过标准**　明确记忆在辅助模型不可用时仍按定义处理，用户收到真实写入结果，页面显示同一owner的记录，重复/重启/撤销授权均正确。（要求）

## 7. 工作包E 微信提醒闭环

**修改位置**　`backend/tools/business/reminder_tools.py`、`bootstrap_tools.py`、`modules/assistant/dispatcher.py`、`modules/scheduling/{api,scheduler}.py`、`modules/channels/api.py`、`modules/delivery/` 及提醒页。（拟定范围）

- [ ] 使用一次人工输入记录提醒工具schema、模型选择和tool_started/tool_finished，确认是否真正调用reminder_create，检查可读返回值及schedule表。（定位步骤）
- [ ] 明确解析未来时间、周期、用户时区、静默窗口和有效投递目标，时间信息不完整时追问。已存在工具经最小修复接入，不重复建立第二套调度。（方案）
- [ ] 权限不足、无绑定、开关关闭、模型失败、工具失败和发送失败分别返回明确状态，避免统一表现为空列表或无回复。（方案）
- [ ] 创建成功立即确认计划ID与触发时间，实际到期投递另有occurrence与delivery证据。成功文案以持久化结果为依据。（方案）
- [ ] 重复入站、模型重试或同一工具重复调用使用服务端稳定操作身份校验，确认当前create路径是否已有幂等保护，具体缺口复现后最小补齐。（步骤）
- [ ] 临时clock/rig验证创建、到期、暂停、删除、重启和重复触发，再用已授权账号做一次完整实单。（验收步骤）

**通过标准**　创建结果、页面记录、实际触发和回执各自可观察，失败可解释，用户仅获得本人任务操作权限。（要求）

## 8. 顺序、评审与验证

建议先处理A和B的前端确定性缺陷，同时定位D/E共享的runtime终态与delivery；随后完成D/E闭环和C技能接线与样例。受保护变更按已有授权和仓库规则交付。（建议顺序）

```powershell
Set-Location E:\PythonCode\EasyChat
python -m pytest tests/usage tests/skills tests/contracts/test_runtime.py tests/contracts/test_toolset_exposure.py -q
python -m pytest tests/memory tests/tools/test_reminder_tools.py tests/channels tests/delivery tests/scheduling -q
python -m pytest tests -q -m "not integration and not resources"
Push-Location agent_frontend
npm test
npm run type-check
npm run build
Pop-Location
```

新回归纳入实际套件。评审聚焦连接所有权、异步请求目标、幂等、owner边界、技能版本一致性、事务内外呼、终态回执、错误与重试分类。（交付要求）

每项交付修改文件、失败/通过证据、命令退出码、浏览器Before/After、测试资源ID、真实外发范围与待验证项。历史通过记录按历史证据引用。（要求）

## 9. 执行模型提示词

```text
接管 E:\PythonCode\EasyChat，处理用户报告的五项问题。
读取 AGENTS.md、CLAUDE.md，以及
E:\PythonCode\EasyChat\docs\superpowers\plans\2026-11-13-five-issues-remediation.md。

先记录代码基线与已有修改，按A至E工作包核查、复现、最小修复并验证。

A 聊天流恢复
真实跨路由复现回答中离开chat再返回。连接与清理按chatId和运行身份归属，异步历史写入指定会话并避免旧响应覆盖新结果，残缺缓存自动对账。覆盖A完成误关B、旧完成晚到、完成前后返回、GET/POST和附件路径。

B 时间与用量权限
时间显示YYYY-MM-DD HH:mm，采用明确用户时区，缺失时Asia/Shanghai，保持UTC存储。
复用trace.view与trace.manage，个人页明确本人范围，新增trace.manage控制的独立全局调用页，支持选用户、分页和详情。用户选择API按最小授权返回所需字段。后端检验owner范围与撤权，角色模式往返保存保持授权语义。

C 技能
先复现普通聊天skill_versions为空及技能内容未注入的问题，接通SkillService的owner作用域快照、实际内容和缓存版本。
从官方固定commit参考PDF与XLSX技能，保留许可和辅助资源，另用最小中文摘要技能验证版本切换。通过公开服务为测试用户导入并激活，生成真实文件且独立校验，授权和工具能力按当前配置检查。

D 微信记忆
复现已配置生成器返回空文本时零记忆却job成功。明确“记住”优先复用现有确定性提取，设计并实现可信来源写入及与后台capture的去重，写入后确认。辅助模型不可用、非法输出、实际无候选和持久化失败分别处理。
补齐runtime失败/取消/空回复的可读终态，按有效来源与delivery策略反馈，记忆和Web当前账号owner核对一致。

E 微信提醒
已有reminder工具与schema入口，先查是否调用、工具返回、实际schedule和delivery，再修具体断点。验证时间/时区、权限、绑定、开关、幂等、创建确认和到期投递。

约束
保留其他任务修改，复用现有模块。身份来自Principal/ToolContext和服务端来源。
按已有人工授权推进，protected paths遵循AGENTS.md的草稿、证据与续作规则，可独立安全区工作继续完成。
迁移只追加，WAL守卫有效，事务内无外呼，能力默认关闭，审批fail-closed。
真实模型、微信外发和测试用户写入使用已授权目标，记录测试资源和清理范围。

验证与交付
执行本方案测试命令，新增回归纳入对应套件。UI必须真实浏览器操作并保存同场景Before/After。
对全部改动评审，修复客观缺陷后复验。输出修改、复现与验证证据、退出码、评审结果、资源ID、回滚与具体未验证项。
```
