# Access 修复草稿升级简报

## 状态与停因

状态为 blocked，停在可评审草稿。仓库 AGENTS.md 将 `backend/modules/access/**` 列为受保护路径，要求自主会话停在草稿及升级简报，由人工答复后续作。本轮只在临时隔离副本中实施、验证补丁，当前工作区的 access 源码无差异，证据为 `git diff -- backend/modules/access` 空输出。

本轮产物为 `access-fixes.draft.patch`、独立回归文件、隔离重放脚本、基线指纹及红绿验证输出。没有提交、推送或部署动作，操作记录对应本目录产物。

## 已确认问题与草稿修复

1. 最后拥有者保护存在并发窗口。当前 `api.py` 在写事务外查询活动拥有者数量，然后调用 repository 更新。回归通过在真实写事务入口同步两个调用，复现两次降权或禁用全部成功。草稿把检查放入 repository 的现有 `BEGIN IMMEDIATE` 写事务，第二次操作明确拒绝，验收结果保留一个活动拥有者。测试为 `test_concurrent_owner_losses_leave_one_active_owner`。
2. 自定义角色改名没有同步成员引用。当前 `repository.py` 更新 `roles.name`，用户仍使用旧的 `users.role`，有效权限与工具组随之丢失。草稿在同一事务同步成员角色名，权限行、角色 ID 和工具配置保持既有含义。回归同时验证名称冲突时事务回滚。测试为 `test_role_rename_preserves_members_permissions_and_toolsets` 和 `test_renaming_to_existing_role_rolls_back_members_and_grants`。
3. 未注册历史键仍可参与有效权限。当前 `policy.py` 只减去固定废弃集合。草稿在角色与用户授予合并后，与调用者提供的注册集合求交，默认使用源码注册集合，随后执行撤销优先。历史授权记录继续保留供审计。测试为 `test_unknown_keys_are_inert_from_role_and_user_override` 和 `test_explicit_empty_registry_grants_nothing`。
4. 记忆 capability 把写权限推导为读取权限。仅有 `memory.edit` 时当前返回 `read=True`，而记忆列表仍检查 `memory.view`。草稿只使记忆 `read` 标志对应实际原子读取检查，不补授 `memory.view`。测试为 `test_memory_capabilities_match_actual_atomic_checks`，涵盖仅写、仅读、读写与空授权。

补丁涉及 `backend/modules/access/api.py`、`repository.py`、`policy.py` 及一项既有 policy 回归断言。该断言原先明确允许已经移除的 `kb.manage` 生效，与本次注册集合过滤要求冲突，因此在隔离补丁中同步修正。补丁内容见 `access-fixes.draft.patch`。

## 验证证据

下列命令从仓库根目录执行，脚本使用临时目录中的源码副本和临时 SQLite，未读取真实业务数据库或运行环境凭据。

```powershell
python docs/reviews/2026-11-10/replay_access_draft.py
python docs/reviews/2026-11-10/replay_access_draft.py --apply-draft --existing-tests
git apply --check docs/reviews/2026-11-10/access-fixes.draft.patch
git diff -- backend/modules/access
```

基线回归为 6 failed、4 passed，非零退出是预期红灯，详见 `baseline-red.txt`。隔离应用草稿后，新增回归与既有 access/security 套件为 62 passed，详见 `draft-green.txt`。补丁可应用检查通过，当前 access 源码差异为空，均为本轮实测。

重放脚本先校验 `baseline-sha256.json`，基线变动时会停止，避免对已变化源码静默套用。它只复制 Git 跟踪的 Python、SQL 和 pytest 配置，应用补丁及运行测试均发生在临时目录，行为见 `replay_access_draft.py`。

验证覆盖本次四项缺陷及既有 access/security 行为，全量维护套件、真实多进程部署和上线验收尚未执行，因此本产物仍为草稿。

## 人工待决与续作

- 委派上限尚需产品决策。只持有 `system.manage` 的管理者当前可以给自己授予 `system.config`，离线公开 service 调用已复现。方案要求明确委派边界，但没有足以确定具体上限的已接受规则。本草稿没有调整委派能力。
- 记忆 capability 草稿保留已有部分授权范围。如果产品希望写权限隐含读权限，需要另行确认并调整 service 授权语义，本草稿没有扩大授权。
- 并发保护覆盖当前角色、状态两条 repository 写入口，使用现有短写事务。共享多进程权限缓存失效策略未纳入本次四项修复，补丁没有修改缓存架构。
- 人工评审补丁与回归证据后，续作应在获准的隔离分支应用补丁，执行仓库 AGENTS.md 的完整验证命令，再按既有评审和部署流程处理。当前会话停在本草稿状态。
