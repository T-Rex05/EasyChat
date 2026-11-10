# P2 权限入口矩阵(2026-11-10,静态扫描实测)

扫描器：`perm_matrix.py`(同目录)。口径：统计各权限键字符串在 service(非 routes 的模块实现)/HTTP routes/channels/模型工具/前端/测试中的字面出现文件数；**盲区**：经角色默认授权生效而不点名键的调用不计(如 files 既有测试用默认 user 走通删除路径)，因此 tests 列是下限，拒绝用例以下文处置为准。

| 权限 | service | routes | channels | tools | 前端 | tests | 备注 |
|---|---|---|---|---|---|---|---|
| chat.use | 6 | 0 | 1 | 0 | 3 | 19 | |
| cron.create | 2 | 0 | 0 | 1 | 3 | 6 | tools 命中=工具组映射 |
| evolution.manage | 1 | 0 | 0 | 0 | 0 | 3 | DEPRECATED 集内(仅注册/过滤命中) |
| evolution.view | 2 | 0 | 0 | 0 | 1 | 3 | |
| file.delete | 2 | 0 | 0 | 0 | 1 | 0→3 | **已补**(见处置 1) |
| file.read | 2 | 0 | 0 | 0 | 1 | 1 | |
| file.upload | 2 | 0 | 0 | 0 | 1 | 1 | |
| ledger.edit | 2 | 0 | 0 | 0 | 1 | 1 | |
| ledger.export | 2 | 0 | 0 | 0 | 1 | 1 | |
| ledger.import | 2 | 0 | 0 | 0 | 1 | 3 | |
| ledger.manage | 2 | 0 | 0 | 0 | 1 | 0→3 | **已补**(create_account 入口) |
| ledger.view | 2 | 0 | 0 | 0 | 3 | 4 | |
| memory.edit | 3 | 0 | 0 | 0 | 3 | 4 | |
| memory.view | 4 | 0 | 0 | 0 | 3 | 4 | 与 capability 对齐(P2-4) |
| skill.create | 2 | 0 | 0 | 0 | 3 | 6 | backend-other=1(registry) |
| skill.manage | 2 | 0 | 0 | 0 | 2 | 3 | |
| superagent.create | 3 | 0 | 0 | 0 | 1 | 5 | worker 发布重检含 |
| superagent.manage | 2 | 0 | 0 | 0 | 1 | 1 | |
| superagent.view | 2 | 0 | 0 | 0 | 3 | 5 | |
| system.config | 3 | 0 | 0 | 0 | 4 | 0→3 | **已补**(ModelsService) |
| system.manage | 7 | 0 | 1 | 0 | 5 | 5 | |
| terminal.audit | 1 | 0 | 0 | 0 | 0 | 2 | DEPRECATED,无校验入口(注册注释自证) |
| trace.manage | 2 | 0 | 0 | 0 | 3 | 2 | |
| trace.view | 2 | 0 | 0 | 0 | 3 | 4 | |

## 结论与处置

1. **授权集中在 service 层**：24/24 键全部有 service 消费点；routes 列全 0 系架构使然(HTTP 路由委托 service,`backend/modules/*/routes.py` 不持权限键,实测)。符合权限整改方案 §7“所有入口经同一公开 service 授权”。
2. **三键无显式拒绝用例**(file.delete / ledger.manage / system.config)：已补 `tests/access/test_permission_entries.py`(3 functions passed;file.delete 走"默认允许 + 撤销拒绝"顺带验证撤销优先;另两键"默认拒绝 + grant 后允许")。实测 access+security 65 passed(原 52+新增)。
3. **两个待退役键现状一致**：terminal.audit、evolution.manage 在 `DEPRECATED_PERMISSION_KEYS` 且有效权限计算强制剔除(P2-3 修复的注册集过滤进一步保证历史残留惰性)；前端不再提供编辑入口。
4. **channels 面窄**：微信命令仅 chat.use/system.manage 直接消费,其余按 5.3 设计走业务工具→service 检查(`__always_available__` 注册,身份来自 ToolContext,模型无法传入 user_id——P0 已核 `backend/shared/tool_context.py`)。工具组与功能开关的"两个开关"观感问题属计划 §5.3 既有观察,前端已按 capability 统一渲染(1acd869),不再扩大本轮。
5. **升级差异可见性**：`permission_upgrade_preview`(service) + `/api/admin/permission-upgrade-preview`(route) + `UpgradePreviewPanel.vue`(前端)三层均存在(实测 grep),admin/user 缺 superagent 键的历史差异由该面板呈现,不自动补授——与整改方案 §2 结论一致。
6. **设计待决不变**：委派上限矩阵未实施(接管许可明确排除),保持设计待决。

## 每行"入口+拒绝"覆盖状态

24 键中 21 键此前已有拒绝类断言(tests 列>0 的文件含 ForbiddenError 类用例;个别为字符串盲区外沿),3 键本轮补齐。矩阵无"零 service 检查"的悬空键。
