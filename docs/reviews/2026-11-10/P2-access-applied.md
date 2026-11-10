# P2 续作记录:access 四项修复已应用(2026-11-10)

许可依据：用户接管指令明确列出 "P2 权限草稿修复"，构成本会话对 `backend/modules/access/**` 受保护路径的续作许可（范围：应用已评审草稿补丁；委派上限与 memory 语义扩大不在授权内，保持设计待决）。

## 应用过程（顺序即证据链）

1. 隔离重放：`python docs/reviews/2026-11-10/replay_access_draft.py --apply-draft --existing-tests` → **62 passed**（指纹匹配，草稿对 HEAD d174afa 仍绿；实测）。
2. 应用补丁：`git apply docs/reviews/2026-11-10/access-fixes.draft.patch` 成功，改动 4 文件（api.py −24、repository.py +23、policy.py +3、test_policy.py 修正一处允许已移除键 kb.manage 的旧断言）。
3. 逐行评审结论：四项均为最小改动——①最后拥有者检查移入 repository 的 `db.transaction()`(BEGIN IMMEDIATE) 内，消除检查/更新间 TOCTOU，两条写入口（set_user_role/set_user_status）全覆盖；②改名同步 `users.role` 与 roles 更新同事务，冲突时靠事务回滚成员同步；③`effective_permissions` 默认注册集从空改为 `ALL_PERMISSION_KEYS` 并在撤销前先与注册表求交（撤销仍最后生效）；④capabilities 的 memory.read 改为按实际原子检查（仅 `memory.view`），不扩大授权。
4. 悬空引用检查：`grep _require_not_last_owner|_count_active_super_admins` 无残留调用方；`routes.py` 的 effective_permissions 走 service 委托，继承新默认值（实测 grep）。
5. 回归归位：草稿回归复制入 `tests/access/test_access_draft.py`（8 项），永久进入 CI。
6. 应用后验证（实测）：定向 `tests/access tests/security tests/contracts/test_tool_context.py` → **71 passed**；全量 `tests -m "not integration and not resources"` → **1140 passed, 2 skipped**（基线 1130+10 新增，无回归）。

## 回滚

`git revert` 本笔提交即回到草稿前状态（补丁不触碰迁移/契约签名；policy 默认参数变化仅影响未显式传注册集的调用方，行为=旧注册集语义收紧，配套回归覆盖）。

## 历史产物说明

`replay_access_draft.py` 与 docs/reviews/2026-11-10 草稿包保留为红绿证据；其基线指纹对应 d174afa，对应用后的 HEAD 重放会按设计指纹停止，属正常。

## P2 剩余工作包状态

- 全权限入口矩阵：进行中（本轮起算）。
- 前端模块模式/高级权限保存：RoleEditDialog 既有修复已入库（47952bd），`role-modes.test.mjs` 已入 npm test；行为符合计划 B2。
- 委派上限授权矩阵：**设计待决**（需产品确认，不实施）。
- 权限升级面板（admin/user 缺 superagent 键的差异呈现）：待 P2 矩阵产出后核查。
