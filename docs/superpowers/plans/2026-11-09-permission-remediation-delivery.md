# 权限整改交付记录（P0–P3）

日期：2026-11-09。分支 `feature/permission-remediation`。方案：`docs/superpowers/plans/2026-11-09-permission-remediation.md`。

## 提交链

| 提交 | 内容 |
|---|---|
| `0d80b15` | P1 后端：0023 迁移（lifecycle + role_seed_state）、模板版本播种、目录、capabilities、委派边界、统一校验、升级预览/应用、usage 排行口径 |
| `3f56dec` | P1 lint 修复 |
| `1acd869` | P2 前端：RoleEditDialog 9 功能项重写、Sidebar/router capabilities、有效权限预览、UpgradePreviewPanel |
| （本次） | P3：迁移兼容/回滚回归 + 迁移测试列表 + 本文档 |

## 一、权限映射（24 键 → 9 功能模块）

| 功能项 | 模式（角色表单档位） | 底层原子键 |
|---|---|---|
| 智能对话 | 关闭 / 使用 | chat.use |
| 记忆与情绪 | 关闭 / 只读 / 使用 | memory.view；memory.edit |
| 个人技能 | 关闭 / 使用 | skill.create；高级：skill.manage（全局）、evolution.view |
| 提醒与简报 | 关闭 / 使用 | cron.create |
| 账单 | 关闭 / 只读 / 使用 | ledger.view；使用 = +import/edit/export 并自动包含 file.upload/file.read；高级：ledger.manage |
| 编码代理 | 关闭 / 只读 / 执行 | superagent.view；执行 = +create；高级：superagent.manage（全局，高风险） |
| 用量统计 | 关闭 / 查看 | trace.view；高级：trace.manage（全局） |
| 用户与角色管理 | 关闭 / 管理 | system.manage（高风险；不可管理拥有者身份） |
| 系统配置 | 关闭 / 配置 | system.config（高风险） |
| （内部）文件依赖 | 高级区原子控制 | file.upload / file.read / file.delete——账单/对话上传/报告下载的依赖能力 |

已退役（deprecated，不参与有效授权、角色 CRUD 拒绝、表单隐藏；存量授权行保留审计）：
- `terminal.audit`：无实际校验入口（方案 §4 确认），待新审计产品确定后删除或重接。
- `evolution.manage`：进化治理未按此键接线（实际用 system.manage/技能权限），统一治理后合并或重接。

## 二、操作矩阵（后端校验点摘要）

- capabilities：`access.capabilities(principal)` 为唯一聚合出口；`/api/auth/me` 与 `/api/auth/capabilities` 输出；前端菜单/路由消费。
- 委派边界：super_admin 目标/分配仅 super_admin 可操作；最后一个活跃拥有者不可降级/禁用（`_require_owner_management` / `_require_not_last_owner`）。
- 角色 CRUD：创建与更新共用 `_validate_role_payload`（未注册键、deprecated 键、未注册工具组）；super_admin 模板角色配置只读。
- 升级受控：`GET /api/admin/permission-upgrade-preview`（差异 + 高风险标注）；`POST /api/admin/roles/{name}/apply-template`（仅 super_admin，先留快照）。
- 用户明细：`GET /api/admin/users/{id}/effective-perms`（角色/单独授予/撤销来源 + 不生效标注）。
- usage 排行：trace.view 或 trace.manage（入口与菜单一致）。
- 微信命令 / 模型工具 / 后台 worker：经各自 service 最终都走 `access.require_permission` / `validate_principal`；superagent worker 在执行与发布前重检 `superagent.create`（已在前一轮交付，本轮未改动）。

## 三、迁移与回滚

- 0023 迁移：`permission_defs.lifecycle` 列 + `role_seed_state` 表；存量库回填 `template_version='legacy'`（已存在的内置角色视为已初始化，不再被播种）；全新库首启由 seed 写入 `v2`。
- 升级路径：管理员在「系统管理 → 角色管理 → 权限模板升级」查看差异（高风险标注）→ super_admin 点应用（先快照到 `role_seed_state.snapshot_json`）。
- 回滚步骤：
  1. 代码回退到本分支前（`5e7e373` 或容器 easychat:v2 原镜像）；
  2. 如需恢复某角色升级前授权：用 `apply-role-template` 响应中的 `previous_permissions`（或 `role_seed_state.snapshot_json`）经角色编辑保存回去；
  3. 0023 为追加列/表，旧代码忽略未知列即可运行，无需数据回滚。

## 四、默认决策（复核点）

- 「个人技能只读」无单独原子键，第一版技能行只提供 关闭/使用 两档（方案 §6 已预留说明），后续需要时新增 `skill.view` 类键再补档位。
- 账单「使用」自动包含 file.upload/file.read（依赖不可拆分提示在表单中）；关闭账单不会自动回收文件键（保守，避免误伤其他依赖方）。
- evolution.view 并入技能高级区展示；微信偏好页多口径混合暂按 chat.use 入场保持（页面内部能力展示待 P2 二期）。
- 旧自定义角色进入编辑即展开高级区并显示「自定义（高级）」模式，不会被自动扩成完整功能授权。

## 五、尚未验证的外部路径

- 真实容器（easychat:v2）尚未重建为新代码——当前容器仍是 superagent-reliability 版本；下次重建时迁移 0023 会自动应用，admin/user 角色在卷中已按旧逻辑初始化，会回填 legacy（不自动获得编码代理授权，需拥有者在面板显式升级——这是本方案的预期行为）。
- 浏览器端到端（角色表单交互、升级面板点击流）未实测。
- 微信命令与模型工具的真实授权路径未在本轮回归外重跑（依赖既有模块测试覆盖）。
