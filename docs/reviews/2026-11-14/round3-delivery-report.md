# 2026-11-14 五项反馈整改交付报告（登录误报/用量合并/技能模板/MCP/账单/角色复选框）

接管基线：HEAD `55fcf68`、工作树干净（并发核对分支一致）。本轮提交链
`5c15b48 → 4b45be8 → 0ddf1a9 → d681a1a → ed0f82b → 1b8e944`（分支
feature/permission-remediation）。方案依据
`docs/superpowers/plans/2026-11-14-web-auth-usage-skills-mcp-ledger-roles.md`。

## 1. 修改清单与对应缺陷

| 包 | 缺陷证据（修复前） | 修改文件 |
| --- | --- | --- |
| P1 登录误报 | `chat.ts:160-174` 以"3 秒内无消息且 CLOSED"推断 JWT 失效；`chat.ts:94-107` ticket 401/409/429/5xx/网络全部折叠成"请先登录"且不清/走登录机制（红测试 7 例复现） | `agent_frontend/src/api/chat.ts`、`backend/modules/assistant/routes.py`（last_seq 游标回退）、`tests/contracts/test_web_chat.py` |
| P2 用量合并 | 双菜单双页面；旧筛选竞态（晚到响应覆盖）；伪总数"共 N 条"；本人区 myUid=0 时拉全量语义失真 | `UsageView.vue`、`UserUsageView.vue`、`router/index.ts`、`AppSidebar.vue`、新增 `utils/globalUsage.ts`、测试 `usage-merge.test.mjs` |
| P3 技能模板 | 技能页无来源固定的样例技能；pdf 大技能超预算被整体跳过（激活内容实际未进请求） | 新增 `backend/modules/skills/templates/{pdf-processing,xlsx-processing,skill-creator}.md`（anthropics/skills@**2c5958ecac7c**，Apache-2.0，EasyChat 适配改写）、`templates.py`、`api.py::import_template`、`routes.py`（/templates、/templates/{key}/import）、`dispatcher.py` 预算截断注入、`SkillsView.vue` 模板面板、`tests/skills/test_templates.py` |
| P4 MCP 配置 | integrations/mcp.py 仅底层适配，无配置 API/生产装配/前端入口 | 新增 `backend/modules/mcp/`（contracts/repository/api/routes）、迁移 **0026**、`integrations/mcp_probe.py`（StreamableHTTP 有界探针）、`bootstrap.py` 装配、`app.py` 路由、`dispatcher.mcp_grantor` 逐 run 注入、前端 `api/mcp.ts`+`McpSettingsPanel.vue`+ConfigView Tab、`tests/mcp/` 18 例、`mcp-panel.test.mjs` 5 例 |
| P5 账单 422 | 账单入口 accept 含 image/* 却送账单登记（后端明确拒绝图片）；`fail()` 只读 detail，AppError 顶层 message 丢失 → 界面显示 AxiosError/422 | 新增 `utils/errorMessage.ts`、`request.ts` 统一提取、`LedgerView.vue` 入口分流+识别函数抽取、`tests/ledger/test_import_flow.py` 2 例（真实 1x1 PNG）、`ledger-upload.test.mjs` 3 例 |
| P6 角色复选框 | 主区为 9 模式下拉，原子复选框被折叠在"高级"且标注"兼容"；依赖只在预设里隐式发生 | `RoleEditDialog.vue` 主区改分组原子复选框（后端 defs 驱动）、`permissionGroups.ts` 增 `permsAfterCheck/permsAfterUncheck/visiblePermissions/internalPermissionDefs/dependencyHint`、`role-checkgroups.test.mjs` 8 例、`role-modes.test.mjs` 迁移适配 |

## 2. 失败→通过证据（红先纪律）

- P1：9 例新测试对当前代码 **7 failed**（503/网络/401 误报、无重连、无游标、无界）→ 修复 9 pass；
  契约 `test_web_chat.py` 8 pass（last_seq 重连不二次执行，`execute_count==1` 断言）。
- P2：util 4 例先绿（新建纯函数）、结构 1 例红（旧接线）→ 全 5 pass。
- P3：模板 6+1 例先红（模块不存在/预算跳过）→ skills 全套 35 pass。
- P4：MCP 18 例（服务/探针/授权/HTTP）+前端结构 5 例，实现后全绿。
- P5：缺陷复现 1 例（旧 fail() 丢中文，绿=证明缺陷存在）+行为 2 例先红 → 全绿；后端
  真实 PNG 登记 422 message 断言 2 pass。
- P6：8 例先红（util 缺失+主区仍下拉）→ 全绿；既有 role-modes 6 例迁移后保持绿。

## 3. 验证命令与退出码（实测）

| 命令 | 结果 | 退出码 |
| --- | --- | --- |
| `pytest tests/contracts/test_web_chat.py tests/contracts/test_file_upload.py tests/ledger tests/skills tests/contracts/test_mcp.py tests/usage -q` | 见下合计* | 0 |
| `pytest tests/mcp -q` | 18 passed | 0 |
| `pytest tests -q -m "not integration and not resources"`（提交态） | **1226 passed, 2 skipped, 3 deselected**（基线 1198+28） | 0 |
| `npm test`（agent_frontend） | 61 passed, 0 failed（基线 27+34） | 0 |
| `npm run type-check` / `npm run build` | 通过 | 0 / 0 |

\* 计划组合命令在本轮中间态跑过 `tests/storage tests/mcp tests/contracts/test_mcp.py` 70 passed；
最终全量含全部套件。迁移列表硬编码断言随 0026 同步扩展（`test_migration_0014.py`，防意外迁移目的保持）。

## 4. 代码评审发现与处置

- **P1 探针语义**：/api/auth/me 401/403 归"认证失效"（403 在已登录查询不可能常态出现，保守按失效）；未知/网络归"连接异常"，不误清 token。
- **P1 重连幂等双保险**：submit 按 client_message_id 幂等（服务端既有语义）+ 游标 last_seq 续传；重连上限 2 次，防服务器故障风暴。
- **P3 预算截断**：超 16000 字符技能从"整体跳过注入"改为"截断注入并标注"，来源/许可头在文首得以保留——修复评审发现的"激活内容实际未进入请求"缺口；旧行为在 test_runtime_wiring 无大技能用例覆盖，故补 test_templates HTTP+真实请求断言。
- **P4 边界**：URL 仅 http(s)、拒内嵌凭据、探针 follow_redirects=False（防凭据随重定向外流）、目录 200 上限截断、凭据仅 register/probe 时内存解密、响应/日志零明文（测试断言）；启用 fail-closed（先测试后启用）；Hermes 无运行时注销 API，删除/停用对已建连接的回收依赖重启，已在面板文案与 api 注释如实声明。
- **P4 audience 授权**：config_admin（默认）仅 system.config 持有者获得 `mcp-<name>` 工具组；all 面向全体——由配置者显式选择；Agent 缓存键含 allowed_tools+permission_revision，跨 owner/跨授权不复用（test_runtime_grant 断言）。
- **P5 老页面兼容**：提取结果同时写回 `data.detail`（大量页面按 detail 读取）与 `error.message`；401 拦截逻辑顺序不变。
- **P6 历史保留**：定义加载失败不显示定义组但按现有键回显可编辑（orphan 组），保存不丢；取消动作仅删自身，共享 file.* 由用户显式取消；trace.manage 勾选无依赖附加。
- **测试基建**：jobs ORDER BY id 非确定性教训沿用——新测试均按 dedup/内容断言，不按随机主键定位。
- 硬约束复核：迁移只追加（0026）；事务体内无外呼（probe/register 全在事务外；mcp 表写为短事务）；身份仅 Principal；能力默认关闭（MCP enabled=0、模板导入不自动激活）；凭据未入日志/git。

## 5. 真实浏览器 Before/After（同账号、同视口、沙箱双实例）

方法：`git worktree`(55fcf68)+junction node_modules 起旧前端 8020→旧后端 8021；当前前端 8025→
新后端 8022；两侧独立临时数据目录与同构账号（reviewer=super_admin / teammate，一次性沙箱
凭据不入报告正文与 git）。用户真实 data/ 未被读写。证据：`docs/reviews/2026-11-14/evidence/`（14 张）：

| 场景 | Before | After |
| --- | --- | --- |
| 侧栏用量入口+页面 | before-usage-page（双入口，无全局区） | after-usage-page（单入口+页内全局调用明细） |
| 旧链接 /trace/users | before-trace-users-page（独立页） | after-trace-users-redirected（整页=合并页含全局区） |
| 技能页 | before-skills-page | after-skills-templates（模板三卡：来源/commit/许可/依赖） |
| 配置页 | before-config-page（无 MCP） | after-config-mcp-tab / after-config-mcp-form |
| 角色编辑 | before-role-edit-dialog（模式下拉） | after-role-edit-dialog（10 组 27 原子复选框，创建态同组件） |
| 账单页 | before-ledger-page（accept 含 image） | after-ledger-page（CSV/XLSX + 截图识别入口） |

沙箱观察项（如实）：After 角色列表卡片间歇性不渲染（无 JS 错误、API 200，RoleListPanel
为未改动组件，Before 同代码偶发同现象）——非本轮引入，登记为观察项待复现定位；
P1 修复的浏览器实时断线场景需真实代理中断配合，未做视觉截图（以 9+8 自动化回归代替）。

## 6. 真实外部测试

- 真实 MCP 服务：未执行——需外部可达的 StreamableHTTP MCP 端点；协议全链路以 httpx.MockTransport
  仿真（成功/401/超时/空目录/重定向/目录变更/截断）。续作：配置一个真实服务器 URL 后面板"测试连接"。
- 真实模型产物（PDF/XLSX/skill-creator 激活后执行）：当前环境 models 服务未配置（启动日志
  "记忆提取未配置 TextGenerator"），端到端产物需先配置模型；上一轮同款改写内容曾有真实产物证据
  （evidence/skill-imports/ artifact_one_page.pdf、artifact_expenses.xlsx、SSE 端到端）。
- 真实微信实单（记忆/提醒闭环）：沿用上轮登记条件（admin 凭据+手机配合）。

## 7. 回滚

`git revert 1b8e944 ed0f82b d681a1a 0ddf1a9 4b45be8 5c15b48`（按包单独可回退）。注意：
0026 迁移只追加，revert 代码后 mcp_servers 表保留但无引用（无数据损坏）；回滚后沙箱产物
templates 目录随代码消失。UI 回滚即恢复旧入口/旧角色编辑形态。

## 8. 待验证项汇总

1. 真实 MCP 服务端到端（配置→测试→启用→工具调用→停用）。
2. 真实模型下的模板激活产物（需模型配置）。
3. 真机微信记忆/提醒实单（上轮条件未变）。
4. P1 用户现场失败的真实 HTTP 状态取证（本轮已使错误文案精确，下次故障可直接区分认证/服务/网络）。
5. 角色列表卡片沙箱间歇空渲染（非本轮引入，待独立复现）。
