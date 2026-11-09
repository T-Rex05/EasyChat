"""access 模块公开契约与权限注册数据（权限整改 v2）。

权限整改（2026-11-09 方案）：
- PERMISSION_CATALOG：统一权限目录——每个权限归属功能模块、操作档位、
  依赖、风险与数据范围；9 个用户可理解的功能项由目录聚合生成；
- lifecycle：active / deprecated / retired。deprecated 键不再参与有效授权，
  角色表单不再展示（存量授权行保留作审计）；
- 模板版本（DEFAULT_TEMPLATE_VERSION）：全新库播种 v2；存量库由迁移 0023
  标记 legacy，升级必须经拥有者显式应用（apply_role_template）。

结构说明：
- chat.use 涵盖微信入站、收藏、基础偏好等已定义范围；
- file.* 是多模块依赖能力（账单导入/报告下载/媒体上传），归 internal，
  不进 9 功能项主界面，在高级设置中可见；
- evolution.view 并入技能模块高级区；evolution.manage 与 terminal.audit
  为 deprecated（无实际接线，见方案 §4），确认新治理实现后退役或重接。
"""
from __future__ import annotations

from dataclasses import dataclass

SUPER_ADMIN_ROLE = "super_admin"

# ---- 生命周期 ----------------------------------------------------------------

LIFECYCLE_ACTIVE = "active"
LIFECYCLE_DEPRECATED = "deprecated"
LIFECYCLE_RETIRED = "retired"

# deprecated/retired 键：不参与有效授权计算，角色 CRUD 拒绝新增，表单不展示。
# 存量授权行保留（审计），由 policy.effective_permissions 统一过滤。
DEPRECATED_PERMISSION_KEYS = frozenset({"terminal.audit", "evolution.manage"})

# 当前默认模板版本：全新部署与显式升级（apply_role_template）使用。
# 变更模板时递增版本号并更新 DEFAULT_ROLE_PERMISSIONS/DEFAULT_ROLE_TOOLSETS。
DEFAULT_TEMPLATE_VERSION = "v2"

# ---- 9 个功能模块（角色表单主界面；files 为 internal 依赖模块） -----------------

MODULE_KEYS = (
    "chat",        # 智能对话
    "memory",      # 记忆与情绪
    "skills",      # 个人技能
    "schedule",    # 提醒与简报
    "ledger",      # 账单
    "superagent",  # 编码代理
    "trace",       # 用量统计
    "identity",    # 用户与角色管理
    "config",      # 系统配置
)
INTERNAL_MODULE = "files"

MODULE_LABELS = {
    "chat": "智能对话",
    "memory": "记忆与情绪",
    "skills": "个人技能",
    "schedule": "提醒与简报",
    "ledger": "账单",
    "superagent": "编码代理",
    "trace": "用量统计",
    "identity": "用户与角色管理",
    "config": "系统配置",
    "files": "文件依赖（内部）",
}


def _perm(key: str, module: str, op: str, *, depends: tuple[str, ...] = (),
          risk: str = "low", scope: str = "self", internal: bool = False) -> dict:
    return {
        "key": key, "module": module, "op": op, "depends": depends,
        "risk": risk, "scope": scope, "internal": internal,
    }


# ---- 统一权限目录（唯一来源；新增权限必须登记，否则目录构建检查失败） ---------------

_PERMISSION_CATALOG: dict[str, dict] = {
    # 智能对话
    "chat.use": _perm("chat.use", "chat", "use"),
    # 记忆与情绪
    "memory.view": _perm("memory.view", "memory", "read"),
    "memory.edit": _perm("memory.edit", "memory", "use"),
    # 个人技能
    "skill.create": _perm("skill.create", "skills", "use"),
    "skill.manage": _perm("skill.manage", "skills", "manage", scope="global", risk="medium"),
    "evolution.view": _perm("evolution.view", "skills", "read"),
    # 提醒与简报
    "cron.create": _perm("cron.create", "schedule", "use"),
    # 账单
    "ledger.view": _perm("ledger.view", "ledger", "read"),
    "ledger.import": _perm("ledger.import", "ledger", "use", depends=("file.upload",)),
    "ledger.edit": _perm("ledger.edit", "ledger", "use"),
    "ledger.export": _perm("ledger.export", "ledger", "use", depends=("file.read",)),
    "ledger.manage": _perm("ledger.manage", "ledger", "manage", scope="self", risk="medium",
                           internal=True),  # 实际 owner 查询仍按本人；见方案 §4 修正说明
    # 编码代理
    "superagent.view": _perm("superagent.view", "superagent", "read"),
    "superagent.create": _perm("superagent.create", "superagent", "execute", risk="high"),
    "superagent.manage": _perm("superagent.manage", "superagent", "manage",
                               scope="global", risk="high"),
    # 用量统计
    "trace.view": _perm("trace.view", "trace", "read"),
    "trace.manage": _perm("trace.manage", "trace", "manage", scope="global", risk="medium"),
    # 用户与角色管理
    "system.manage": _perm("system.manage", "identity", "manage", scope="global", risk="high"),
    # 系统配置
    "system.config": _perm("system.config", "config", "manage", risk="high"),
    # 文件依赖（internal：多模块依赖能力，不进 9 功能项）
    "file.upload": _perm("file.upload", INTERNAL_MODULE, "use", internal=True),
    "file.read": _perm("file.read", INTERNAL_MODULE, "read", internal=True),
    "file.delete": _perm("file.delete", INTERNAL_MODULE, "manage",
                         risk="medium", internal=True),
}


def permission_catalog() -> dict[str, dict]:
    """统一权限目录（只读副本）。新增 active 权限必须登记，否则目录覆盖检查失败。"""
    return {k: dict(v) for k, v in _PERMISSION_CATALOG.items()}


# ---- 权限定义（key, label, description, group_name, group_label, sort_order, lifecycle） ----

PERMISSION_DEFS: tuple[dict, ...] = (
    {"key": "chat.use",        "label": "使用对话",   "group_name": "chat",    "group_label": "智能对话", "sort_order": 10, "lifecycle": LIFECYCLE_ACTIVE,  "description": "发起聊天、微信入站、收藏与基础偏好"},
    {"key": "skill.create",    "label": "使用个人技能", "group_name": "skill",  "group_label": "个人技能", "sort_order": 10, "lifecycle": LIFECYCLE_ACTIVE,  "description": "创建、修改与激活本人技能版本"},
    {"key": "skill.manage",    "label": "管理全部技能", "group_name": "skill",  "group_label": "个人技能", "sort_order": 20, "lifecycle": LIFECYCLE_ACTIVE,  "description": "跨用户管理技能资产"},
    {"key": "memory.view",     "label": "读取与召回记忆", "group_name": "memory", "group_label": "记忆与情绪", "sort_order": 10, "lifecycle": LIFECYCLE_ACTIVE,  "description": "查看本人记忆、召回与情绪读取"},
    {"key": "memory.edit",     "label": "写入记忆与情绪", "group_name": "memory", "group_label": "记忆与情绪", "sort_order": 20, "lifecycle": LIFECYCLE_ACTIVE,  "description": "记忆写入/修订/遗忘，情绪启用与记录"},
    {"key": "terminal.audit",  "label": "操作审计（待退役）", "group_name": "system", "group_label": "系统", "sort_order": 30, "lifecycle": LIFECYCLE_DEPRECATED, "description": "已退役占位：无实际校验入口；确认新审计产品后删除或重接"},
    {"key": "cron.create",     "label": "使用提醒与简报", "group_name": "schedule", "group_label": "提醒与简报", "sort_order": 10, "lifecycle": LIFECYCLE_ACTIVE,  "description": "建立与管理本人的提醒/定时任务"},
    {"key": "system.manage",   "label": "用户与角色管理", "group_name": "system",  "group_label": "系统",    "sort_order": 10, "lifecycle": LIFECYCLE_ACTIVE,  "description": "用户/角色/覆盖授权与多模块跨用户操作；不可管理拥有者身份"},
    {"key": "system.config",   "label": "系统配置",   "group_name": "system",  "group_label": "系统",    "sort_order": 20, "lifecycle": LIFECYCLE_ACTIVE,  "description": "模型、SMTP 等平台配置与凭证"},
    {"key": "trace.view",      "label": "查看用量",   "group_name": "trace",   "group_label": "用量统计", "sort_order": 10, "lifecycle": LIFECYCLE_ACTIVE,  "description": "查看本人用量与排行"},
    {"key": "trace.manage",    "label": "管理全局用量", "group_name": "trace",   "group_label": "用量统计", "sort_order": 20, "lifecycle": LIFECYCLE_ACTIVE,  "description": "跨用户查看明细与清理调用记录"},
    {"key": "evolution.view",  "label": "查看经验记录", "group_name": "evolution", "group_label": "经验（技能高级）", "sort_order": 10, "lifecycle": LIFECYCLE_ACTIVE,  "description": "查看本人学习任务与候选版本记录（技能模块高级区）"},
    {"key": "evolution.manage", "label": "进化管理（待退役）", "group_name": "evolution", "group_label": "经验（技能高级）", "sort_order": 20, "lifecycle": LIFECYCLE_DEPRECATED, "description": "已退役占位：进化治理未接线；统一治理策略后合并或重接"},
    {"key": "file.upload",     "label": "上传文件",   "group_name": "file",    "group_label": "文件依赖", "sort_order": 10, "lifecycle": LIFECYCLE_ACTIVE,  "description": "保存微信/Web 上传的原件（账单导入/对话上传依赖）"},
    {"key": "file.read",       "label": "读取文件",   "group_name": "file",    "group_label": "文件依赖", "sort_order": 20, "lifecycle": LIFECYCLE_ACTIVE,  "description": "查看/下载本人有权访问的文件（报告下载依赖）"},
    {"key": "file.delete",     "label": "删除文件",   "group_name": "file",    "group_label": "文件依赖", "sort_order": 30, "lifecycle": LIFECYCLE_ACTIVE,  "description": "按明确范围删除原件或引用"},
    {"key": "ledger.view",     "label": "查看账单",   "group_name": "ledger",  "group_label": "账单",    "sort_order": 10, "lifecycle": LIFECYCLE_ACTIVE,  "description": "查看本人账本、导入批次与候选"},
    {"key": "ledger.import",   "label": "导入账单",   "group_name": "ledger",  "group_label": "账单",    "sort_order": 20, "lifecycle": LIFECYCLE_ACTIVE,  "description": "建立候选并提交账本导入（依赖文件上传）"},
    {"key": "ledger.edit",     "label": "修正账目",   "group_name": "ledger",  "group_label": "账单",    "sort_order": 30, "lifecycle": LIFECYCLE_ACTIVE,  "description": "修正分类/备注等可编辑字段"},
    {"key": "ledger.export",   "label": "导出报告",   "group_name": "ledger",  "group_label": "账单",    "sort_order": 40, "lifecycle": LIFECYCLE_ACTIVE,  "description": "导出分析报告与明细（下载依赖文件读取）"},
    {"key": "ledger.manage",   "label": "账本高级操作", "group_name": "ledger",  "group_label": "账单",    "sort_order": 50, "lifecycle": LIFECYCLE_ACTIVE,  "description": "账本高级变更入口（当前 owner 查询仍严格按本人）"},
    {"key": "superagent.view", "label": "查看编码任务", "group_name": "superagent", "group_label": "编码代理", "sort_order": 10, "lifecycle": LIFECYCLE_ACTIVE,  "description": "查看自己的编码任务与执行轨迹"},
    {"key": "superagent.create", "label": "提交编码任务", "group_name": "superagent", "group_label": "编码代理", "sort_order": 20, "lifecycle": LIFECYCLE_ACTIVE,  "description": "提交编码任务：会消耗模型用量并产生远端代码产物（Draft PR）"},
    {"key": "superagent.manage", "label": "管理编码代理", "group_name": "superagent", "group_label": "编码代理", "sort_order": 30, "lifecycle": LIFECYCLE_ACTIVE,  "description": "配置仓库/凭证/策略与跨用户管理任务；高风险"},
)

ALL_PERMISSION_KEYS: frozenset[str] = frozenset(d["key"] for d in PERMISSION_DEFS)
ACTIVE_PERMISSION_KEYS: frozenset[str] = ALL_PERMISSION_KEYS - DEPRECATED_PERMISSION_KEYS

# 内置角色默认模板（v2）。变更模板必须递增 DEFAULT_TEMPLATE_VERSION。
# 存量库不会被自动补种（迁移 0023 已标记 legacy）；升级经拥有者显式应用。
DEFAULT_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "admin": (
        "chat.use", "skill.create", "skill.manage",
        "memory.view", "memory.edit", "cron.create",
        "system.manage", "system.config", "trace.view", "trace.manage",
        "evolution.view",
        "file.upload", "file.read", "file.delete",
        "ledger.view", "ledger.import", "ledger.edit", "ledger.export", "ledger.manage",
        "superagent.view", "superagent.create", "superagent.manage",
    ),
    "user": (
        "chat.use", "skill.create",
        "memory.view", "memory.edit",
        "cron.create", "trace.view",
        "file.upload", "file.read", "file.delete",
        "ledger.view", "ledger.import", "ledger.edit", "ledger.export",
        "superagent.view", "superagent.create",
    ),
}
# 上一版模板（仅用于升级差异展示；不再播种）
LEGACY_TEMPLATE_VERSION = "legacy"

# ---- 工具集定义（Hermes toolsets）----

TOOLSET_DEFS: tuple[dict, ...] = (
    {"key": "terminal",     "label": "终端执行", "description": "执行 Shell 命令", "risk": "high"},
    {"key": "file",         "label": "文件读写", "description": "读写文件", "risk": "high"},
    {"key": "web",          "label": "网络搜索", "description": "搜索网页和抓取 URL", "risk": "low"},
    {"key": "notification", "label": "通知推送", "description": "消息通知推送", "risk": "low"},
    {"key": "schedule",     "label": "定时任务", "description": "定时任务管理", "risk": "low"},
)

VALID_TOOLSETS: frozenset[str] = frozenset(t["key"] for t in TOOLSET_DEFS)

DEPRECATED_TOOLSETS: frozenset[str] = frozenset(
    {"vision", "session_search", "memory", "utility", "data", "email", "paper_repro"}
)

DEFAULT_ROLE_TOOLSETS: dict[str, tuple[str, ...]] = {
    "super_admin": tuple(t["key"] for t in TOOLSET_DEFS),
    # 纵深防御（审计 #2）：服务端 run 无人值守，默认不授予宿主执行工具集；
    # adapter 层的 fail-closed 审批回调是不变量，接受风险的运维可经
    # system.manage 按角色显式重新授予 terminal/file（升级预览会展示该差异）。
    "admin": ("web", "notification", "schedule"),
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
