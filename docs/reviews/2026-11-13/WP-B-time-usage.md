# WP-B 记录:时间显示与独立全局用量页(2026-11-13)

## 修改清单

**后端**（usage 域复用,无新模块）
- `backend/modules/usage/repository.py`：`user_options(limit, offset)` —— DISTINCT owner JOIN users，按最近调用排序分页，**仅返回 user_id/username/last_call**（最小授权字段面）。
- `backend/modules/usage/api.py`：`user_options(actor)` —— 仅 super_admin/trace.manage，否则 ForbiddenError。
- `backend/modules/usage/routes.py`：`GET /api/usage/users`。
- `tests/usage/test_calls.py`：`test_user_options_minimal_and_gated` 覆盖计划七场景之普通用户/trace.manage/super_admin/字段最小化（其余：无 token=路由 `_principal` 既有 401；仅 trace.view=同测试第一断言；撤销后=`_permissions` 实时有效权限+既有 `test_owner_permission_on_details`；手改 owner_id=既有越权 403 用例）。

**前端**
- 新增 `src/utils/dateTime.ts`：`formatDateTime(value, tz)` → `YYYY-MM-DD HH:mm`；时区显式（用户设置缺失回退 Asia/Shanghai 并在页头标注口径）；兼容 Z/`+00:00`/无后缀（按项目 UTC 存储约定解释）；空/无效返回 `—`，未知时区名回退不抛错。
- `UsageView.vue`：时间列格式化（Before 显示 `2026-11-13T09:03:00.039+00:00` raw UTC，截图 b-before）；**最近调用显式携带本人 owner_id**——修复 trace.manage 用户"个人页默认拉全量却呈现为我的调用"的语义失真。
- 新增 `UserUsageView.vue` + 路由 `/trace/users`（permission trace.manage / capLevel manage）+ 侧栏"全局用量"项（hasCap('trace','manage')）。
- `RoleEditDialog.vue`：trace 模块 desc 改"查看本人用量与排行；管理范围可查看全部用户调用明细"，模式扩为 off/read(查看本人)/manage(管理含全部用户明细)，governed 同步含 trace.manage（往返识别一致）。

## 验收实证

- 计划样例：`2026-11-13T07:19:35.942+00:00` 在 Asia/Shanghai 应显示 `2026-11-13 15:19`——实现口径实屏 `2026-11-13 17:03`（对应 09:03:00.039Z，同一规则）✓。
- 全局页：18 行含用户/来源列、筛选下拉（全部用户/指定）、分页器、时区口径标注；无加载错误。
- API 门禁实测：admin 200 含 2 用户；普通用户 403。
- Before/After 截图：`evidence/b-before-utc-raw.png`（raw UTC）、`b-after-formatted.png`、`b-after-global-page.png`。
  注：Before 截图仅回退了 UsageView（stash），侧栏"全局用量"项同属本包新增，Before 态应无该项——截图如实记录了这一取样限制，菜单差异以代码 diff 为准。
- 后端 usage 域 15 passed（含新用例）、security+superagent_api 39 passed 合计；npm test 27、type-check 0、build ✓。

## 统计时区口径（方案要求分别说明）

展示时区=用户时区（本版 Asia/Shanghai 回退）；**日汇总统计口径未变更**——`stat_date_for` 仍按 UTC 日界（历史数据兼容优先，调整日界另列数据兼容设计，本次不动）。

## 评审发现

- UserUsageView 的"总数"估算：后端 calls 接口未提供 count（保持窄接口不扩权），前端以"本页满页→可能还有下一页"近似并显示条数——**如实标注为估算**；若需要精确总数应在 usage 后端加 count 窄接口（登记为可选增强，不擅自扩面）。
- `users` 选项 limit 500 上限：超大规模用户需分页选择器——当前规模(2 用户)不适用，登记。

## 回滚

revert 后端提交+前端提交（或本包单提交）；无迁移、无数据变更。
