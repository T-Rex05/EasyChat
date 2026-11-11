# WP4 记录（后端部分）:任务页逐项验收与返工闭环(2026-11-11)

## 设计依据（执行方案 §7 条件性新增的前置记录）

为什么不复用现有 reports：reports 为任务级文本摘要（kind/summary/head_sha/verification_ref），
**无检查项粒度状态（pass/fail/blocked/skipped）、无轮次不可改写语义、无逐项评审决定**；
验收要求"证据绑定 task/attempt/轮次/commit、打回进入原任务、历史轮次可追溯、
重复反馈幂等"都需要结构化可查询字段。故新增两张表（迁移 0025）。

模块形态决策：方案允许独立 acceptance 模块（条件性），**条件不成立**——无独立身份/权限面，
属任务账本生命周期，并入 `backend/modules/superagent/`（acceptance.py），路由挂
`/api/superagent/tasks/{id}/acceptance/*`，复用既有 `_task_for` 归属校验与装配点。

## 数据与语义（实测）

- `acceptance_rounds`：UNIQUE(task_id, round_no)，server 端 MAX+1 自增；requirement/verdict/
  summary/provenance(commit/tree/build/viewport/environment)。轮次**不可改写**——打回返工后
  提交新一轮，旧轮保留（历史可追溯测试断言 round [2,1] 并存）。
- `acceptance_checks`：UNIQUE(round_id, item_id)；status 闭集 {pass,fail,blocked,skipped}；
  decision ''|accepted|rejected + decided_by/at/note。
- **覆盖门**（Acceptance skill 同一契约，纯函数 `apply_coverage_gate`）：required_evidence
  声明的 medium 缺对应证据条目时 pass 强制降级 blocked——"缺规定证据标记待验证"。
- verdict 规则：有 fail→fail；全 pass→pass；否则 partial（blocked/skipped 混入）。
- **打回返工闭环**：首次 rejected → `append_input`（幂等键 `acceptance-reject:{check_id}`，
  重复打回不二次插入）+ succeeded/awaiting_review CAS 回队（与 P7 自动修复同白名单）+ 事件。
  改判 accepted→rejected 视为再次首次打回（可再返工一次入队，状态机自洽）。非终态任务打回：
  输入保留、requeued=False（在途运行不打断，符合"取消/重试先核对在途"约束）。

## 访问控制

- 读列表/提交轮次/决定：`_task_for`（owner 或 superagent.manage）+ 写操作再过
  `_require_cancel_like`（owner 需 create）→ 跨用户读/决定均 ForbiddenError（实测回归）。
- 证据文件：`GET .../evidence/{item_id}/{index}`——path 必须 `assets/` 相对前缀，
  根取自该轮 attempt 报告的 `verification_ref`（受控工件目录），resolve 后必须仍在根内
  （符号链接/相对逃逸拒绝）；列表端点剥离 evidence_json（防未授权内联）。
- HTML 报告隔离渲染：本轮 API 只供文件流（octet-stream），前端 WP4 前端部分若内嵌
  HTML 预览需 sandbox iframe——记录为前端实施约束。

## 交付与验证

- 文件：migrations/0025_superagent_acceptance.sql（追加式）、
  superagent/acceptance.py、api.py（4 方法+init）、routes.py（4 端点+3 body 模型）、
  shared/identifiers.py（arnd 前缀）、tests/storage/test_migration_0014.py（列表同步 0025）。
- 回归 tests/superagent/test_acceptance.py 3 项：覆盖门+verdict；打回→输入+回队+幂等+
  新一轮旧轮并存；跨用户拒绝+改判再返工+非法状态/空检查拒绝。**191 passed**
  （channels+wechat+delivery+**architecture**+superagent 合并定向）。
- 全量见本包末尾（含 architecture 首现失败修复记录，下节）。

## 过程中的架构教训（如实）

首轮全量 `tests/architecture::test_module_privacy_cross_imports` FAILED——根因是
**WP2 我在 delivery/wechat.py 私引了 channels.wechat.account**（跨模块私有引用），
而 WP2 定向命令（channels+wechat+delivery）不含 architecture 套件，未拦截。
修复：STALE_TOKEN_CODE 上移 `channels/contracts`（公开契约），暂停动作经
`ChannelService.report_stale_token` 公开方法；并新增 AST 约束回归
`test_delivery_uses_public_channels_surface_only`（教训固化进结构而非散文，
AGENTS.md encode-lessons-in-structure）。此后 WP 定向命令一律并入 architecture。

## 前端部分（未完成，本包剩余）

任务页验收区块（轮次选择、检查项列表+状态徽标+证据预览、接受/打回输入）、
Before/After 截图、契约测试扩展——按 P8 浏览器验收同标准另实施。
