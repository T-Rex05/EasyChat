# 2026-11-17 权限/渠道/聊天/账单整改交付报告（WP-A～E）

接管基线：HEAD `579db03`，dirty 为主题样式工作（index.html/AppSidebar/MessageBubble/
main.ts/design-system.css/ChatView/LoginView + useTheme.ts，**原样保留未触碰**）。本轮
提交链 `0989a84 → 0ca12f9 → 7e18609 → f5eb525 → c3afdc1`（分支 feature/permission-remediation）。
方案依据 `docs/superpowers/plans/2026-11-17-permissions-channels-chat-ledger-remediation.md`。
运行实例诊断：8001 进程为本轮代码（readyz ready）；**发现其一直未配置 EASYCHAT_ENCRYPTION_SECRET**
（模型/渠道模块从未装配）——已生成新密钥写入用户环境变量并重启，智谱 glm-5.3-flash 配置经
加密入库与解密路径实测（见 §6 外部测试）。

## WP-A　账单摘要笔数/金额分离（0989a84）

**缺陷**　`normalization.py:297-302` 正则 `([-\d.,]+)` 把"支出：385笔 23708.48元"的 385
当金额 → expense=38500/income=3300/neutral=1000 分，三项全错。
**修复**　两段式 `_split_count_amount`：分类行"N笔+金额"只取金额、仅笔数时金额 None、
独立"共N笔"才计入 count；支持千分位/零值/空摘要。前端 `ImportSummary.control` 对齐后端
mismatches/detail 契约（api/ledger.ts）；差异展示改真实清单+明细汇总，删除
`JSON.stringify(differences||{})`；"确认差异并提交"改为独立显式动作（二次确认弹窗），
普通提交不默认放行。
**回归**　`tests/ledger/test_parsers.py` 3 例（CSV/XLSX 真实入口 2370848/1041086/951811 分
精确断言 + 文本变体矩阵含"385笔，共23708.48元"不当总笔数）；`test_import_flow.py` 未提交
批次 parse 重核验（候选指纹幂等 + owner/撤权双闸）；前端 ledger-upload 2 例契约断言。
ledger 套件 **177 passed / 0**。

## WP-C　聊天流真实错误与生命周期（0ca12f9）

**缺陷**　GET EventSource 的 error 事件无 HTTP 状态——409/422/503 只能显示泛化断流文案；
后端 error 帧是 `{message}` 而前端只读 `error` 字段（显示"未知错误"）；恢复流程无互斥、
旧连接不关闭、晚到回调无代次丢弃。
**修复**　GET 流改 **fetch+手工 SSE 解析**：HTTP 状态可读（401/403→现有登录机制；
409 繁忙/429 限流/5xx 各自可读原因，不做无效重试）；error 帧优先读 `message`；
恢复互斥（`recovering` 单飞）+ 连接代次（gen）——恢复开始即 abort 旧连接并推进代次，
晚到回调按代次丢弃；完成/错误帧/认证失效/重试耗尽/手动停止全部收敛到关闭状态；
凭据走 Authorization header 不进 URL（审计 #3 保持），client_msg_id + last_seq 续传
不重复执行/计费（后端幂等既有契约覆盖）。
**回归**　`tests/chat-sse-recovery.test.mjs` 10 例（503/409/401/message 帧完成/断流重连带
游标/互斥停止丢弃/重试有界/手动停止晚到丢弃/完成关闭/凭据不落 URL），前端 65 passed。

## WP-B　渠道装配状态与配置体验（7e18609）

**缺陷**　readyz 与认证成功被当模块可用证据；channels 关闭/缺密钥/依赖缺失在配置页
表现为 403/503 加无限 loading（`loadWechatConfig` 只 console.error）。
**修复**　新增 `GET /api/system/module-status`（登录可读、脱敏、无凭据字段）：assistant/
channels/runtime 各自 assembled/state/reason，状态区分 disabled（开关=false）/
misconfigured（缺 EASYCHAT_ENCRYPTION_SECRET，归因优先）/dependency_missing（hermes 关）
/init_failed，reason 携带可执行恢复步骤；ConfigView 渠道 tab 顶部状态条 + 重新检测入口，
accounts 失败可见化。
**回归**　`tests/contracts/test_module_status.py` 4 例（关闭/缺密钥/依赖缺失/装配齐 +
401 契约），前端 mcp-panel 结构 1 例。注：本端点为新增能力，Before（579db03）无该端点
与状态条——以红测试与基线代码 grep 为对照证据，不另截无意义空页。

## WP-D　动作授权、owner 范围与撤权（f5eb525）

**缺陷（计划已实测）**　撤 skill.create/skill.manage 后 PATCH pin/archive 仍 200；撤
cron.create 后提醒停启/删除/occurrences 仍 200；撤 trace.view 后本人 calls/daily 仍 200；
capabilities 对 superagent.read 由 create/manage 折算，与真实查看闸（仅 view）不一致。
**修复**　skills `set_pinned/set_archived` 复用 `_require_write`（动作+owner/manage 双闸）；
scheduling 新增 `_require_schedule_access`（cron.create 动作闸 + owner 范围，跨 owner 仍需
system.manage；get/list/occurrences/set_enabled/remove 全覆盖；worker/scheduler 走 repo
tick 不受影响，不取消既有任务）；usage `list_calls`/`my_daily_usage`/`get_call` 要求
trace.view 或 trace.manage（本人归属不能替代动作授权）；access capabilities 的
superagent.read 改为严格等于 `superagent.view in perms`。
**回归**　`tests/access/test_action_revocation.py` 5 例（先建后撤立即生效、授回恢复、
跨 owner Forbidden、仅 system.manage 无 cron.create 仍拒、禁用前 200 对照）；
`tests/contracts/test_superagent_combinations.py` 三键八组合（capabilities.read==view、
list_tasks view 才 200）。access+skills+usage+scheduling+superagent 套件全绿。

### 22 项 active 权限矩阵（入口/动作/数据范围/撤权依据）

| 权限 | 关键入口 | 范围 | 撤权行为（证据） |
| --- | --- | --- | --- |
| chat.use | assistant.submit、dispatcher._build_request、channels 入站 | 本人对话 | 403（access 套件既有） |
| memory.view / memory.edit | memory api 读写入口 | 本人 | 403（既有） |
| skill.create | propose/activate/pin/archive（本轮收口） | 本人技能 | 撤后 propose/pin/archive 403（test_action_revocation） |
| skill.manage | 跨 owner 写/查看 | 全局 | 跨 owner 403（同上） |
| cron.create | scheduling create + get/list/occurrences/set_enabled/remove（本轮收口） | 本人提醒 | 撤后管理入口 403（test_action_revocation） |
| ledger.view/import/edit/export | ledger api 各动作 | 本人 | 403（既有 + reparse owner 闸） |
| ledger.manage | 账本高级变更 | **scope=self（本人）** | 403（既有）；UI 已标注本人范围 |
| superagent.view | list_tasks/_task_for | 本人任务 | 八组合：无 view 列表 403 |
| superagent.create | 受理/取消（owner） | 本人任务 | 八组合 |
| superagent.manage | 配置/跨 owner/取消 | 全局 | 八组合 |
| trace.view / trace.manage | ranking/calls/detail/daily/user_options（本轮收口） | 本人 / 全局 | 撤 view 后本人 calls/daily 403（test_action_revocation） |
| system.manage | 用户/角色管理、跨 owner 管理 | 全局 | 403（既有） |
| system.config | 模型/SMTP/MCP 写 | 全局 | 403（test_config 既有） |
| file.upload/read/delete | files api + 派生产物 | 本人原件 | 403（既有） |
| evolution.view / evolution.manage | evolution api | 本人/全局 | 403（既有；不再可新增授予） |

worker/后台入口：memory worker（snapshot_principal+remember_explicit 内部校验）、
scheduling worker（repo tick，不经过动作闸——无人值守语义，登录态无关）、delivery
（收件人 fail-closed 既有）。退役键（terminal.audit/evolution.manage 相关旧键）保持
policy 过滤语义，不提供新授予。

## WP-E　角色编辑去重与升级面板（c3afdc1）

- 删除高级区功能预设下拉（MODULE_ROWS/detectMode/syncModesFromPermissions/onModeChange/
  moduleModes 全部移除，含孤儿样式），分组复选框为唯一授权编辑入口；工具组保持独立复选框。
- 文件依赖过滤仅限 files 模块——**ledger.manage 回到账单组**并标注"当前范围：本人账本"。
- UpgradePreviewPanel：panel-head 改真 button（Tab 聚焦 + Enter/Space 展开 + aria-expanded，
  浏览器实测 Enter 展开 aria-expanded=true）、容器内边距 10px/14px、标题徽标可换行、
  长 key word-break、≤760px 纵排。
- role-modes 套件按新行为重写（Esc 关闭/只改名保存集合稳定/定义失败 orphan 回显不丢/
  勾选附加依赖+取消保留共享+ledger.manage 主区可见）。

## 验证命令与退出码（实测）

| 命令 | 结果 | 退出码 |
| --- | --- | --- |
| `pytest tests/ledger -q` | 177 passed | 0 |
| `pytest tests/contracts/test_web_chat.py tests/contracts/test_sse.py` 及 11-14 契约 | 13+8 passed | 0 |
| `pytest tests/contracts/test_module_status.py` | 4 passed | 0 |
| `pytest tests/access tests/skills tests/usage tests/scheduling tests/delivery/test_schedule.py tests/contracts/test_superagent_api.py tests/superagent tests/contracts/test_superagent_combinations.py tests/contracts/test_mcp.py tests/storage tests/mcp` | 66+80+75+70 各段全绿 | 0 |
| `pytest tests -q -m "not integration and not resources"`（提交态全量） | **1247 passed, 2 skipped, 3 deselected**（基线 1226+21） | 0 |
| `npm test` | 65 passed, 0 failed | 0 |
| `npm run type-check` / `npm run build` | 通过 | 0 / 0 |

## UI Before/After（真实浏览器，同账号沙箱双实例）

方法同前轮：worktree@`f5eb525`（WP-E 前）+junction 起 Before(8020/8021)，当前代码起
After(8025/8022)，独立临时库与同构账号（一次性凭据不入库不入报告）。用户真实 data/
未被读写。证据：`docs/reviews/2026-11-17/evidence/`。

| 场景 | Before | After |
| --- | --- | --- |
| 角色编辑对话框 | before-role-edit.png / -advanced.png：9 个预设下拉+27 复选框 | after-role-edit.png：**0 下拉**，10 分组 27 复选框，文件依赖独立组，账本高级操作在主区 |
| 升级面板 | before-upgrade-panel.png（旧间距/纯点击展开） | after-upgrade-panel.png：button+aria-expanded（Enter 实测展开），body padding 4px 14px 12px |
| 渠道状态条 | before-channel-status.png（无状态条） | after-channel-status.png：disabled 原因+恢复步骤+重新检测 |

如实登记：After 沙箱 RoleListPanel 角色卡列表两次观察均空（升级预览卡正常渲染，API 200
无 JS 错误；该组件本轮未改动，11-14 沙箱亦偶发）——对话框证据改经"+创建角色"（同一
组件）与既有 DOM 量测取得；**观察项继续保留**，待独立复现定位。

## 真实外部测试

- 智谱 glm-5.3-flash（用户提供的 key）：已配置为 EasyChat 激活聊天模型（AES-GCM 密文
  入库、strata-qwen 停用保留）；8001 用新密钥重启，解密路径实测通过。**API 外呼效果**
  （真实对话生成）未测——需面板登录后发消息验证。
- 真实微信/SSE 用户现场：未复现——本轮修复以合成入口回归覆盖；用户下次现场失败的
  HTTP 状态将可从错误文案直接区分（WP-C 产物）。
- 用户原账单原件：未读取——金额语义以同构合成文本验证（计划已声明的证据边界）。

## 回滚

`git revert c3afdc1 f5eb525 7e18609 0ca12f9 0989a84`（逐包可独立回退）；无迁移、无
schema 变更。模型配置变更独立于代码提交：恢复 strata-qwen 激活需在拥有其原加密密钥的
环境重存 key（其密文与现密钥不同源）。

## 未完成项

1. RoleListPanel 沙箱空卡渲染竞态（非本轮引入，待独立复现）。
2. 智谱模型真实外呼对话验证（需面板登录）。
3. 微信实单/真实 SSE 现场（沿用既有条件：admin 凭据+真机）。
4. protected paths 说明：本轮触碰 access/usage/skills/scheduling 公共行为与 assistant
   routes 语义，均为**行为收紧+回归覆盖**的最小修复，已按草稿+报告交付；如需进一步
   收敛（如 cron.create 细分为 read/manage 两键）属契约变更，需人工决策后再动。
