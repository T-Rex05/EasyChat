# Web登录误报、用量入口、技能与MCP、账单及角色复选框整改方案

日期为2026-11-14。依据用户五项反馈，核查当前源码及隔离行为后编写。当前产品工作区干净，本轮默认沿用此前的方案与执行模型交接方式。（范围选择与本轮Git核查）

## 1. 已确认结果

| 反馈 | 确认结果 | 尚待现场核实 |
|---|---|---|
| 问完问题报登录过期 | GET SSE以3秒内无消息且CLOSED推断登录过期；ticket请求503和网络异常也被折叠为登录提示 | 用户本次失败实际HTTP状态和运行结果 |
| 全局用量并入用量与排行 | 当前有两个页面和菜单，现有trace.manage可控制全局区域 | 合并后不同角色的浏览器交互 |
| 技能与MCP配置 | 已找到官方PDF、XLSX、skill-creator技能，当前MCP仅有底层适配与内核实现，未见配置API和生产装配 | 所选版本资源、实际依赖和真实MCP服务 |
| 账单上传422 | CSV上传登记实测200；入口允许图片却调用拒绝图片的登记接口；前端丢失业务message | 现场文件具体类型及原始422响应 |
| 角色恢复勾选 | 当前模块模式下拉和高级复选框并存，可改为按原子授权分组多选 | 历史部分权限、依赖提示与键盘操作 |

证据位置为 `agent_frontend/src/api/chat.ts:93`、`:160`、`src/views/LedgerView.vue:11`、`:313`、`src/api/request.ts`、`backend/modules/ledger/api.py:281`、`backend/integrations/mcp.py`，路由和权限据当前对应文件核查。（源码核查）

隔离实测包括真实sendMessageStream转译执行、ticket成功后立即CLOSED错误误报登录；真实ASGITransport/账单rig上传CSV返回200并登记200，图片登记422返回明确中文原因，空文件422，缺multipart boundary对照返回400。（本轮实测）

`python -m pytest tests/contracts/test_web_chat.py -q -k "busy_conflict_409 or stream_ticket_flow_single_use or stream_rejects_token_query_and_bad_ticket"` 结果为 `3 passed, 4 deselected in 2.32s`，证明有效身份可遇到409，ticket单次消费有现有契约覆盖。（本轮实测）

## 2. 接管与实施约定

- [ ] 读取AGENTS.md、CLAUDE.md，记录当前HEAD、工作区差异和运行版本，保留其他任务修改。（步骤）
- [ ] 已授权工作按范围推进，protected paths依仓库规则交付可评审草稿与续作简报，前端及可独立安全区工作继续完成。（仓库要求）
- [ ] 每项先保留具体失败行为，再最小修复和回归。敏感token及文件内容不进入截图、日志和报告。（步骤）
- [ ] UI保存同账号、同数据、同视口的Before/After，真实模型/外部MCP和上传测试使用已授权环境。（验收条件）

## 3. 登录过期误报与SSE恢复

**文件**　`E:\PythonCode\EasyChat\agent_frontend\src\api\chat.ts`、`auth.ts`、`request.ts`、`stores\auth.ts`、`composables\useChat.ts`，回归位于 `agent_frontend/tests/api-config.test.cjs` 和现有聊天契约测试。（拟定范围）

- [ ] 捕获脱敏的ticket/流请求状态和同一client_msg_id、run，不将服务端生成故障与认证失效混为一个提示。（诊断步骤）
- [ ] 移除3秒启发式，ticket请求区分明确401、403、409、429、5xx、网络错误和畸形响应，展示后端可读错误。（最小修复）
- [ ] EventSource错误事件本身无法提供HTTP状态，连接关闭先显示连接异常；需要认证判定时通过有明确HTTP状态的现有认证接口确认，保留有效token。（方案）
- [ ] 重连使用新ticket并保留原逻辑请求身份和已有事件游标，限制重试，验证服务端不会产生第二次模型执行。单次ticket的自动重放需显式处理。（方案）
- [ ] 完成、主动停止、首帧前断开、输出后断开、token过期及刷新失败分别验证，完成事件后的正常关闭保持完成状态。（具体回归）

**验收**　有效身份的网络/409/5xx故障显示准确；明确认证失效按既有登录流程处理；恢复不重复发送或计费。（要求）

## 4. 全局用量合并入口

**文件**　`agent_frontend/src/views/UsageView.vue`、`UserUsageView.vue`、`components/AppSidebar.vue`、`router/index.ts`。（拟定范围）

- [ ] `/trace` 下保留本人用量和排行，新增仅trace.manage或super_admin可见的全局明细区域，复用已有UserUsageView筛选与表格。（用户要求与方案）
- [ ] 侧栏保留一个入口，旧 `/trace/users` 定向至合并页相应区域。仅trace.manage角色在capabilities存在或缺失时均能按原权限访问。（具体行为）
- [ ] 本人ID就绪后再发本人调用请求，显式携带owner_id；全局区域单独管理查询和错误，避免管理员个人区误显示全量。（方案）
- [ ] 切换用户重置页码，快速切换防止旧响应覆盖新筛选。现有API没有精确调用总数时显示当前页和是否可继续翻页，后端增加count需有实际需求与回归。（方案）
- [ ] 普通用户页面不发送全局用户选项请求，手改owner_id仍由后端拒绝，撤权后正确清理全局显示状态。（具体回归）

**验收**　一个菜单入口，个人与全局范围清晰，多种权限组合及旧链接正常。（要求）

## 5. 技能目录与导入测试

本轮联网核查到Anthropic官方PDF、XLSX和skill-creator技能，作为可选样例来源，选定版本的正文、辅助资源和许可需一并固定。具体使用量排名本轮未测量。（来源与证据范围）[PDF](https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md)、[XLSX](https://github.com/anthropics/skills/blob/main/skills/xlsx/SKILL.md)、[skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)

**文件**　`agent_frontend/src/views/SkillsView.vue`、现有skills routes/api及已实现runtime快照接线，测试 `tests/skills/`。（拟定范围）

- [ ] 页面增加可选技能模板/导入入口，展示用途、来源、选定commit、许可、依赖和资源状态。首批为PDF、表格处理和技能编写，避免无选择地批量启用。（方案）
- [ ] 通过现有公开服务创建本人版本，内容冲突时明确新建版本或保留，激活后验证实际请求使用该快照。（步骤）
- [ ] 外部skill中引用的相对脚本、字体和运行环境需要完整适配。当前内容模型若只支持Markdown，先提供自包含适配版本并说明所支持操作，资源目录扩展单独设计。（方案）
- [ ] PDF生成中文测试文档并解析页数/标题，表格生成公式并独立校验结果，skill-creator生成可校验的技能草稿；记录工具与文件授权、版本切换和跨owner隔离。（具体验收）
- [ ] 技能指令和工具能力分别验证，依赖缺失返回可读原因，新增安装依赖按仓库规则评审。（步骤）

## 6. MCP配置前后端接入

当前 `backend/integrations/mcp.py` 有McpAdapter/McpServerConfig，Hermes有工具注册实现。前端配置接通需要持久配置、凭据管理、健康状态和每次运行的工具授权，以下为拟定增量设计。（源码核查与方案）

**建议文件**　新增 `backend/modules/mcp/{contracts,api,repository,routes}.py`，复用integrations适配并在app/bootstrap注册，存储迁移按实际下一编号追加；前端新增 `src/components/config/McpSettingsPanel.vue`、`src/api/mcp.ts` 并接入ConfigView。已有配置存储若可完整承载职责则复用并记录依据。（拟定结构）

- [ ] 首版沿用当前适配支持的远程StreamableHTTP，UI显示名称、URL、开关、凭据状态、连接/调用超时、允许工具、发现结果及错误。其他传输按实际需要另设工作包。（范围选择）
- [ ] 配置写操作复用system.config授权，能力默认关闭。服务端保存加密凭据，响应仅返回是否已设置；空输入保留既有凭据，清除通过显式操作。（方案）
- [ ] 拟定接口为 `/api/mcp/servers` 的列表/创建，以及按server_id更新/删除、测试连接和读取工具目录。请求/响应契约先评审后实现，测试连接与保存状态分别展示。（方案）
- [ ] URL、重定向、DNS解析、网络可达范围与敏感头按明确策略验证。本地或私网MCP如确有需求由受信任配置显式允许，模型不能自行修改目标。（方案）
- [ ] 测试连接有独立超时和工具目录数量上限，事务内无网络外呼，日志凭据脱敏。失败区分认证、连接、超时和空目录。（要求）
- [ ] 启用配置到runtime注册及工具schema逐项打通，选择的工具由服务端授权过滤，验证全局registry与Agent缓存不会使其他owner获得未授权工具。（验收要求）
- [ ] 保存、禁用、删除和修改后的生效时机明确，失败配置恢复到上次有效状态，旧连接资源可回收，核心聊天健康状态单独保留。（要求）
- [ ] 临时MCP服务分别模拟成功、401、超时、空目录、目录变更，完成配置→测试→启用→实际工具调用→禁用的闭环。（具体验收）

**验收**　前端配置对应真实持久数据和连接结果，凭据受保护、授权隔离有效、运行请求实际使用受控工具。（要求）

## 7. 账单422与错误展示

**文件**　`agent_frontend/src/views/LedgerView.vue`、`api/ledger.ts`、`api/request.ts`，复用 `backend/modules/files/routes.py`、`modules/ledger/api.py` 及现有上传测试。（拟定范围）

- [ ] 取得现场422的脱敏响应，区分图片、空文件和其他业务拒绝。现有file/request_id与file_id接口字段匹配，保持正常CSV上传契约。（实测依据与步骤）
- [ ] 账单文件入口只接受支持的CSV/XLSX，并在提交处校验；图片使用页面已有截图识别入口或明确分流，避免上传后直接调用账单文件登记。（最小修复）
- [ ] 普通请求统一提取业务message、字符串detail、对象detail与FastAPI detail数组，页面使用规范化后的可读错误。（最小修复）
- [ ] 回归CSV成功、XLSX成功、图片入口分流、空文件、业务422中文原因和字段校验数组，同时验证身份和文件归属。（验收）

## 8. 角色权限恢复分组复选框

**文件**　`agent_frontend/src/views/admin/RoleEditDialog.vue`、`utils/permissionGroups.ts` 和 `tests/role-modes.test.mjs`。（拟定范围）

- [ ] 以注册权限按模块分组，逐原子授权显示复选框，同组及跨组均可多选。原form.permissions继续作为保存真值，工具组继续独立多选。（用户要求与方案）
- [ ] 现有互斥模式预设转换为逐项行为，打开角色、只改名称、直接保存均保持历史权限集合。未知/退役权限按当前后端口径处理并显示保留或失效原因。（方案）
- [ ] 新勾账单导入只附加已定义file.upload依赖，新勾导出只附加file.read并提示。旧缺依赖配置打开时原样回显，取消动作保留其他模块共享文件授权。（具体回归）
- [ ] 仅trace.manage角色保持仅该键，不自动扩大为其他授权。拥有者角色依当前规则只读，权限/工具定义加载失败时保留原字段。（具体回归）
- [ ] 验证Tab、Space、Esc、取消不保存、窄屏滚动和多选payload，保存前后端有效权限一致。（验收）

## 9. 验证与交付

建议顺序为登录误报与账单错误→用量合并与复选框→技能模板与产物→MCP端到端接入。MCP涉及受保护接口和存储时按已有授权与AGENTS规则交付。（方案）

```powershell
Set-Location E:\PythonCode\EasyChat
python -m pytest tests/contracts/test_web_chat.py tests/contracts/test_file_upload.py tests/ledger tests/skills tests/contracts/test_mcp.py tests/usage -q
python -m pytest tests -q -m "not integration and not resources"
Push-Location agent_frontend
npm test
npm run type-check
npm run build
Pop-Location
```

新增回归纳入对应套件，每项交付源码差异、复现及通过证据、命令退出码、Before/After、授权与版本依据、回滚和具体未验证项。当前诊断的现场未知项保持显式标注。（验收要求）

## 10. 执行模型提示词

```text
接管 E:\PythonCode\EasyChat，修复本轮五项反馈并完成回归与代码评审。
先读取AGENTS.md、CLAUDE.md及
E:\PythonCode\EasyChat\docs\superpowers\plans\2026-11-14-web-auth-usage-skills-mcp-ledger-roles.md。
记录HEAD与已有修改，按当前代码复核证据，确认缺口后做最小实现。

1. 修复登录过期误报。GET SSE的3秒启发式不能判定JWT失效，ticket的401/409/429/5xx/网络错误需分别处理。恢复时用新ticket、原逻辑请求标识和既有游标，防止重复执行。真实401按现有登录机制处理。
2. 全局用量合并到用量与排行，单菜单入口，trace.manage控制全局区域，旧链接重定向。本人区明确owner，用户筛选重置页码和处理竞态，分页显示真实口径。
3. 技能页加入有来源和固定版本的PDF、XLSX和skill-creator模板/导入。处理资源与依赖，激活后验证实际使用及真实产物，保持owner和工具授权。
4. MCP加入系统配置前端，并接通真实配置API、加密凭据、持久化、连接测试、目录发现、工具选择与运行注册。先按计划评审接口及网络边界，能力默认关闭，测试覆盖认证、超时、空目录、禁用、缓存与跨用户隔离。
5. 账单上传支持的CSV/XLSX走登记，图片走已有截图识别入口。错误解析同时支持message和detail，显示真实中文原因。保持file/request_id和file_id正常契约。
6. 编辑角色恢复分组原子权限复选框，允许多选，保留历史自定义配置。依赖只在用户新勾对应动作时按后端已定义规则附加，取消不删共享权限，工具字段加载失败时保留。

先复现再修复，每包定向回归与评审。普通可逆工作按授权推进，protected paths遵循AGENTS.md和已有明确续作许可，其他可独立工作继续完成。
迁移只追加，事务内无外呼，WAL守卫有效，身份来自Principal/ToolContext，凭据不进入日志和浏览器持久存储。
执行计划中的后端与前端验证命令。UI修改实际操作浏览器并提供同场景Before/After。
最终交付修改、缺陷依据、测试与退出码、评审与复验、版本和回滚、真实外部测试及待验证项。
```
