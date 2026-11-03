"""access 模块公开契约与权限注册数据。

权限种子口径（架构 §6、实施计划 Task 3）：
- 保留既有 16 键中不属于已删业务的 12 键；
- 移除 skill.pool.review / kb.manage / kb.eval / graph.manage / paper.use（R03/R14）；
- 新增 evolution.view / evolution.manage（R12：进化操作必须显式注册权限）；
- 默认授权仅在角色一条授权都没有时播种，不覆盖管理员自定义（旧 registry 规则）。
部门现状：旧库无 departments 表，仅历史权限键；本版不新增不删除。
"""
from __future__ import annotations

from dataclasses import dataclass

SUPER_ADMIN_ROLE = "super_admin"

# ---- 权限定义（key, label, group_name, group_label, sort_order, description） ----

PERMISSION_DEFS: tuple[dict, ...] = (
    {"key": "chat.use",        "label": "使用聊天",   "group_name": "chat",    "group_label": "对话",    "sort_order": 10, "description": "发起聊天与查看自己的会话"},
    {"key": "skill.create",    "label": "创建技能",   "group_name": "skill",   "group_label": "技能",    "sort_order": 10, "description": "创建与编辑个人技能"},
    {"key": "skill.manage",    "label": "管理全部技能", "group_name": "skill",  "group_label": "技能",    "sort_order": 20, "description": "跨用户管理技能资产"},
    {"key": "memory.view",     "label": "查看记忆监控", "group_name": "memory", "group_label": "记忆",    "sort_order": 10, "description": "查看记忆监控面板"},
    {"key": "memory.edit",     "label": "个人记忆管理", "group_name": "memory", "group_label": "记忆",    "sort_order": 20, "description": "管理个人事实/事件/经验记忆"},
    {"key": "terminal.audit",  "label": "操作审计",   "group_name": "system",  "group_label": "系统",    "sort_order": 30, "description": "查看执行治理与操作审计"},
    {"key": "cron.create",     "label": "创建定时任务", "group_name": "schedule", "group_label": "定时",  "sort_order": 10, "description": "建立与管理自己的提醒/定时任务"},
    {"key": "system.manage",   "label": "系统管理",   "group_name": "system",  "group_label": "系统",    "sort_order": 10, "description": "用户/角色/工具集等管理操作"},
    {"key": "system.config",   "label": "系统配置",   "group_name": "system",  "group_label": "系统",    "sort_order": 20, "description": "平台与模型等系统配置"},
    {"key": "trace.view",      "label": "查看链路",   "group_name": "trace",   "group_label": "可观测",  "sort_order": 10, "description": "查看用量/排行与最小Trace"},
    {"key": "trace.manage",    "label": "查看全部用户", "group_name": "trace",  "group_label": "可观测",  "sort_order": 20, "description": "跨用户查看Trace明细"},
    {"key": "evolution.view",  "label": "查看进化记录", "group_name": "evolution", "group_label": "进化", "sort_order": 10, "description": "查看学习任务与候选版本记录"},
    {"key": "evolution.manage", "label": "进化管理",  "group_name": "evolution", "group_label": "进化", "sort_order": 20, "description": "批准/回滚候选版本与调整预算"},
)

ALL_PERMISSION_KEYS: frozenset[str] = frozenset(d["key"] for d in PERMISSION_DEFS)

# 内置角色默认授权（仅当该角色零授权时播种；super_admin 运行时取全集）
DEFAULT_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "admin": (
        "chat.use", "skill.create", "skill.manage",
        "memory.view", "memory.edit", "terminal.audit", "cron.create",
        "system.manage", "system.config", "trace.view", "trace.manage",
        "evolution.view", "evolution.manage",
    ),
    "user": (
        "chat.use", "skill.create",
        "memory.view", "memory.edit",
        "cron.create", "trace.view",
    ),
}

# ---- 工具集定义（Hermes toolsets）----
# 移除 paper_repro（R14）；vision/session_search/memory/utility/data/email 为历史废弃键，
# 读取时永久过滤（沿用旧 checker 过滤清单并追加）。

TOOLSET_DEFS: tuple[dict, ...] = (
    {"key": "terminal",     "label": "终端执行", "description": "执行 Shell 命令"},
    {"key": "file",         "label": "文件读写", "description": "读写文件"},
    {"key": "web",          "label": "网络搜索", "description": "搜索网页和抓取 URL"},
    {"key": "notification", "label": "通知推送", "description": "消息通知推送"},
    {"key": "schedule",     "label": "定时任务", "description": "定时任务管理"},
)

VALID_TOOLSETS: frozenset[str] = frozenset(t["key"] for t in TOOLSET_DEFS)

DEPRECATED_TOOLSETS: frozenset[str] = frozenset(
    {"vision", "session_search", "memory", "utility", "data", "email", "paper_repro"}
)

DEFAULT_ROLE_TOOLSETS: dict[str, tuple[str, ...]] = {
    "super_admin": tuple(t["key"] for t in TOOLSET_DEFS),
    "admin": ("terminal", "file", "web", "notification", "schedule"),
    "user": ("web",),
}

BUILTIN_ROLES: tuple[dict, ...] = (
    {"name": "super_admin", "display_name": "超级管理员", "is_system": 1},
    {"name": "admin", "display_name": "管理员", "is_system": 1},
    {"name": "user", "display_name": "普通用户", "is_system": 1},
)


# ---- 值对象 ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UserSnapshot:
    """用户只读快照（不含密码哈希）。"""

    user_id: int
    username: str
    email: str
    role: str
    status: int  # 1=正常 0=禁用
    avatar: str
    created_at: str


@dataclass(frozen=True, slots=True)
class RoleInfo:
    role_id: int
    name: str
    display_name: str
    description: str
    is_system: bool
    permissions: tuple[str, ...]
    toolsets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PermissionOverride:
    permission: str
    granted: bool
