"""
权限注册中心 — 管理 permission_defs 表的权限定义。
支持模块启动时注册权限，启动后播种到数据库。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from backend.db.schema import get_conn
from backend.utils.log_utils import log

logger = log


@dataclass
class PermissionDef:
    key: str
    label: str
    description: str = ""
    group_name: str = ""
    group_label: str = ""
    sort_order: int = 0


# 内存中的权限注册表（启动时各模块注册，启动后播种到 DB）
_registry: Dict[str, PermissionDef] = {}


def register_perm(
    key: str,
    label: str,
    description: str = "",
    group_name: str = "",
    group_label: str = "",
    sort_order: int = 0,
) -> None:
    """注册一个权限定义。幂等——重复注册自动覆盖。"""
    _registry[key] = PermissionDef(
        key=key,
        label=label,
        description=description,
        group_name=group_name,
        group_label=group_label,
        sort_order=sort_order,
    )


def seed_to_db() -> None:
    """将内存注册表中的权限同步到 permission_defs 表。新增 + 更新标签。

    同时：
    - 清理已废弃的权限（kb.create, kb.admin 及已合并的 graph 细粒度权限，见 obsolete_keys）
    - 自动给 super_admin 角色分配所有权限
    """
    if not _registry:
        logger.warning("权限注册表为空，跳过播种")
        return

    conn = get_conn()
    try:
        # 同步权限定义到 permission_defs 表
        for perm in _registry.values():
            conn.execute(
                """INSERT INTO permission_defs (`key`, label, description, group_name, group_label, sort_order)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                     label=VALUES(label),
                     description=VALUES(description),
                     group_name=VALUES(group_name),
                     group_label=VALUES(group_label),
                     sort_order=VALUES(sort_order)""",
                (perm.key, perm.label, perm.description, perm.group_name, perm.group_label, perm.sort_order),
            )

        # 清理已废弃的权限（新增废弃权限时在此追加）
        # 注：graph 的细粒度权限已合并进 graph.manage，此处登记后启动时自动从
        #     role_permissions / user_permissions / permission_defs 三张表清除
        # 注：system.manage（5 合 1）与 system.config（2 合 1）同理 —— 原 7 个 key 登记在此清理
        obsolete_keys = [
            "kb.create", "kb.admin", "graph.view", "graph.review", "graph.community",
            # → system.manage（系统管理）
            "terminal.whitelist", "terminal.blacklist",
            "admin.users", "admin.roles", "admin.departments",
            # → system.config（系统配置）
            "config.model", "config.email",
            # → trace.view（查看排行榜合并进查看链路）
            "trace.ranking",
        ]

        # 合并后的"授予映射"：旧 key 的持有者自动获得新 key。
        # ⛔ 顺序至关重要：**必须先授后删**。只删不授会让持有旧 key 的角色凭空掉权限
        #    （上一轮 graph/system 合并就是这么做的，见 obsolete_keys 里的其它条目）。
        merged_grants = {
            "trace.ranking": "trace.view",
        }
        for old_key, new_key in merged_grants.items():
            try:
                holders = conn.execute(
                    "SELECT DISTINCT role_id FROM role_permissions WHERE permission = %s",
                    (old_key,),
                ).fetchall()
                for h in holders:
                    conn.execute(
                        "INSERT IGNORE INTO role_permissions (role_id, permission) VALUES (%s, %s)",
                        (h["role_id"], new_key),
                    )
                uholders = conn.execute(
                    "SELECT DISTINCT user_id FROM user_permissions "
                    "WHERE permission = %s AND granted = 1",
                    (old_key,),
                ).fetchall()
                for h in uholders:
                    conn.execute(
                        "INSERT IGNORE INTO user_permissions (user_id, permission, granted) "
                        "VALUES (%s, %s, 1)",
                        (h["user_id"], new_key),
                    )
                if holders or uholders:
                    logger.info(
                        f"权限合并（先授后删）：{old_key} → {new_key}，"
                        f"角色 {len(holders)} 个 / 用户 {len(uholders)} 个"
                    )
            except Exception as e:
                logger.warning(f"权限合并授予失败（{old_key} → {new_key}）: {e}")
        if obsolete_keys:
            placeholders = ", ".join(["%s"] * len(obsolete_keys))
            params = tuple(obsolete_keys)
            # 从 role_permissions 表删除旧权限关联
            conn.execute(
                f"DELETE FROM role_permissions WHERE permission IN ({placeholders})",
                params,
            )
            # 从 user_permissions 表删除旧权限覆盖（防止孤儿数据）
            conn.execute(
                f"DELETE FROM user_permissions WHERE permission IN ({placeholders})",
                params,
            )
            # 从 permission_defs 表删除旧权限定义
            conn.execute(
                f"DELETE FROM permission_defs WHERE `key` IN ({placeholders})",
                params,
            )
            logger.info(f"已清理废弃权限: {obsolete_keys}")

        # 自动给 super_admin 角色分配所有权限
        all_perm_keys = list(_registry.keys())
        if all_perm_keys:
            # 先获取 super_admin 的 role_id
            row = conn.execute("SELECT id FROM roles WHERE name = 'super_admin'").fetchone()
            if row:
                super_admin_id = row["id"]
                # 删除 super_admin 的旧权限
                conn.execute("DELETE FROM role_permissions WHERE role_id = %s", (super_admin_id,))
                # 插入所有权限
                for perm_key in all_perm_keys:
                    conn.execute(
                        "INSERT INTO role_permissions (role_id, permission) VALUES (%s, %s)",
                        (super_admin_id, perm_key),
                    )
                logger.info(f"已为 super_admin 分配 {len(all_perm_keys)} 个权限")

        # 为**其它内置角色**播种默认权限。
        # 硬约束：仅当该角色【一条授权行都没有】时才播种 —— 权限现在由前端
        # 角色编辑唯一决定，重启绝不能回滚管理员的勾选/取消。
        try:
            from backend.permission.builtin import DEFAULT_ROLE_PERMISSIONS
        except Exception:  # 防御：builtin 导入失败不应让启动挂掉
            DEFAULT_ROLE_PERMISSIONS = {}
        for role_name, keys in (DEFAULT_ROLE_PERMISSIONS or {}).items():
            if role_name == "super_admin":
                continue  # 上面已按注册表全量重置
            row = conn.execute("SELECT id FROM roles WHERE name = %s", (role_name,)).fetchone()
            if not row:
                continue  # 该角色不存在（例如被删过）→ 跳过
            rid = row["id"]
            cnt_row = conn.execute(
                "SELECT COUNT(*) AS n FROM role_permissions WHERE role_id = %s", (rid,)
            ).fetchone()
            if cnt_row and cnt_row["n"]:
                continue  # 已有授权（可能被用户改过）→ 一律不覆盖
            seeded = 0
            for k in keys:
                if k in _registry:  # 只播种注册表里真实存在的 key
                    conn.execute(
                        "INSERT IGNORE INTO role_permissions (role_id, permission) VALUES (%s, %s)",
                        (rid, k),
                    )
                    seeded += 1
            logger.info(f"已为角色 {role_name} 播种默认权限 {seeded} 个")

        # 清理"幻影授权"：permission 不在 permission_defs 里的行。
        # 历史种子里的 skill.view / agent.* / review.* / config.view 等 key 既不在
        # 定义表中、也不被 obsolete_keys 覆盖，会一直留在授权表里造成口径分裂
        # （_get_role_permissions 读得到、前端看不到也改不掉）。
        # 注：子查询来自 permission_defs（与被删表不同），MySQL 允许。
        try:
            phantom = conn.execute(
                "DELETE FROM role_permissions WHERE permission NOT IN "
                "(SELECT `key` FROM permission_defs)"
            )
            phantom_u = conn.execute(
                "DELETE FROM user_permissions WHERE permission NOT IN "
                "(SELECT `key` FROM permission_defs)"
            )
            n1 = getattr(phantom, "rowcount", 0) or 0
            n2 = getattr(phantom_u, "rowcount", 0) or 0
            if n1 or n2:
                logger.info(f"已清理幻影授权: role_permissions={n1}, user_permissions={n2}")
        except Exception as e:
            logger.warning(f"清理幻影授权失败（不影响启动）: {e}")

        # 收敛 roles.hermes_tools：全新库这三行是 NULL，会让
        # `checker.get_user_hermes_tools()` 返回 [] → Hermes 的 enabled_toolsets
        # 里没有 web/file/terminal → **Agent 一个工具都没有**。
        # 硬约束：仅当值为 NULL/空时才写入，**绝不覆盖管理员手改过的值**。
        try:
            from backend.permission.builtin import DEFAULT_ROLE_TOOLSETS
        except Exception:
            DEFAULT_ROLE_TOOLSETS = {}
        import json as _json
        for role_name, tools in (DEFAULT_ROLE_TOOLSETS or {}).items():
            row = conn.execute(
                "SELECT id, hermes_tools FROM roles WHERE name = %s", (role_name,)
            ).fetchone()
            if not row:
                continue
            cur_val = row.get("hermes_tools")
            if cur_val:  # 已有值（含管理员手改）→ 不动
                continue
            conn.execute(
                "UPDATE roles SET hermes_tools = %s WHERE id = %s",
                (_json.dumps(list(tools), ensure_ascii=False), row["id"]),
            )
            logger.info(f"已为角色 {role_name} 播种默认 toolset {len(tools)} 个")

        conn.commit()

        # ⚠️ 迁移/播种后必须让 Redis 权限缓存失效。
        # 否则 obsolete_keys 删除、merge-grant 授予、默认权限播种的结果最长
        # 30 分钟（role 命名空间 TTL 1800s）不生效 —— 而且**重启后端也不会清**
        # （Redis 是外部进程，缓存比进程活得久）。
        # 延迟到函数内导入，避免 registry ↔ checker 的模块级循环导入。
        try:
            from backend.permission.checker import _invalidate_permission_cache
            _invalidate_permission_cache()
            logger.info("权限缓存已失效（迁移/播种后）")
        except Exception as e:
            logger.warning(f"权限缓存失效失败（请手动清 agentforge:permission:*）: {e}")
    finally:
        conn.close()


def get_all_permissions() -> List[dict]:
    """从数据库读取全部权限定义（扁平列表）。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT `key`, label, description, group_name, group_label, sort_order FROM permission_defs ORDER BY sort_order, id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_permission_tree() -> List[dict]:
    """返回分组树结构，供前端渲染权限勾选面板。

    返回格式:
    [
      {
        "group_name": "skill",
        "group_label": "技能管理",
        "permissions": [
          {"key": "skill.create", "label": "创建技能", "description": "..."},
          ...
        ]
      },
      ...
    ]
    """
    all_perms = get_all_permissions()
    groups: Dict[str, dict] = {}
    for p in all_perms:
        gn = p["group_name"]
        if gn not in groups:
            groups[gn] = {
                "group_name": gn,
                "group_label": p.get("group_label", gn),
                "permissions": [],
            }
        groups[gn]["permissions"].append({
            "key": p["key"],
            "label": p["label"],
            "description": p.get("description", ""),
        })
    return list(groups.values())
