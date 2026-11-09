-- 0023_permission_lifecycle: 权限生命周期 + 角色模板版本记录（权限整改 P1）。
--
-- 问题（方案 §5.2）：
--   1. seed_builtin_roles 以「角色授权数为零」判断是否播种——管理员显式清空
--      内置角色授权后，重启会被重新补入默认权限；
--   2. 已有授权角色不会获得新模板权限（如 superagent.*）——该行为本身正确
--      （新增授权必须显式确认），但需要模板版本记录来表达
--      「尚未初始化 / 已初始化（含明确空授权）」两种状态。
-- 修复：
--   * role_seed_state 记录每个内置角色的模板版本；播种只发生在「无记录」时；
--   * 存量库回填 template_version='legacy'：标记已按旧逻辑初始化，永不再补种，
--     升级由拥有者经 upgrade-preview/apply-template 显式完成；
--   * permission_defs 增加 lifecycle（active/deprecated/retired），
--     deprecated/retired 键不参与有效授权，也不在角色表单出现。

ALTER TABLE permission_defs ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'active';

CREATE TABLE IF NOT EXISTS role_seed_state (
    role_name        TEXT PRIMARY KEY,
    template_version TEXT NOT NULL,
    seeded_at        TEXT NOT NULL,
    snapshot_json    TEXT NOT NULL DEFAULT '[]'
);

-- 存量库回填：迁移执行时已存在的内置角色视为「已按旧逻辑初始化」。
-- 空库（全新部署）roles 表为空，不回填——首次启动由播种逻辑写入 v2 模板。
INSERT INTO role_seed_state(role_name, template_version, seeded_at, snapshot_json)
SELECT r.name, 'legacy', strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'), '[]'
FROM roles r
WHERE r.name IN ('admin', 'user', 'super_admin')
  AND NOT EXISTS (SELECT 1 FROM role_seed_state s WHERE s.role_name = r.name);
