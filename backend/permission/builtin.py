"""
内置权限定义 — AgentForge 脚手架预置权限。

"""
from backend.permission.registry import register_perm


def register_all_builtin_permissions() -> None:
    """注册所有内置权限定义。幂等，可在每次启动时调用。"""

    # 模块: chat
    register_perm(
        key="chat.use", label="使用聊天",
        description="允许使用智能对话功能（Web + 微信）",
        group_name="chat", group_label="聊天", sort_order=10,
    )

    # 模块: skill
    register_perm(
        key="skill.create", label="创建技能",
        description="创建个人技能（含查看/编辑/删除自己的、发布到技能池）",
        group_name="skill", group_label="技能管理", sort_order=20,
    )
    register_perm(
        key="skill.pool.review", label="技能池审核",
        description="审核用户提交到技能池的技能申请（通过/拒绝）",
        group_name="skill", group_label="技能管理", sort_order=21,
    )
    register_perm(
        key="skill.manage", label="管理全部技能",
        description="查看/编辑/删除任意技能",
        group_name="skill", group_label="技能管理", sort_order=22,
    )
    register_perm(
        key="memory.view", label="查看记忆监控",
        description="查看记忆系统监控看板（含各层记忆统计、向量化/图覆盖率、KGStore 知识图谱指标等）",
        group_name="skill", group_label="记忆管理", sort_order=23,
    )
    register_perm(
        key="memory.edit", label="个人记忆管理",
        description="查看/编辑自己的跨会话记忆（MySQL + 向量库），提交经验到分享池",
        group_name="skill", group_label="记忆管理", sort_order=24,
    )

    # 模块: terminal（终端安全）
    # 注：原终端安全组的白名单/黑名单两个细粒度权限已合并进 system.manage（见下方"系统管理"）
    #     操作审计（terminal.audit）保持独立，不在合并范围内
    register_perm(
        key="terminal.audit", label="操作审计",
        description="查看 AI 对话中的服务器命令执行记录、审批记录（含审核人）",
        group_name="terminal", group_label="终端安全", sort_order=41,
    )

    # 模块: cron
    register_perm(
        key="cron.create", label="创建定时任务",
        description="创建个人定时任务（含查看/编辑/删除自己的）",
        group_name="cron", group_label="定时任务", sort_order=50,
    )

    # 模块: admin（系统管理）
    # 注：原"主机白名单 / 命令黑名单管理 / 管理用户 / 管理角色 / 部门管理"5 个细粒度权限
    #     已合并为唯一的 system.manage（统一入口，避免嵌套 fallback 链口径不一致；
    #     具体废弃 key 清单见 registry.py 的 obsolete_keys，启动时自动清理三张表）
    register_perm(
        key="system.manage", label="系统管理",
        description=(
            "系统管理统一权限：主机白名单（含白名单主机免密登录，每条命令仍需人工审批）、"
            "命令黑名单规则管理、用户管理（列表/角色/状态）、角色管理（增删改查）、"
            "部门管理（创建/编辑/删除部门，为用户和知识库分配部门）"
        ),
        group_name="admin", group_label="系统管理", sort_order=60,
    )

    # 模块: config（系统配置）
    # 注：原"管理模型配置"与"管理邮箱配置"2 个细粒度权限已合并为唯一的 system.config
    #     （具体废弃 key 清单见 registry.py 的 obsolete_keys）
    register_perm(
        key="system.config", label="系统配置",
        description="系统配置统一权限：模型配置（查看/新增/编辑/切换 LLM 模型配置）与邮箱配置（查看/新增/编辑/切换邮箱配置）",
        group_name="config", group_label="系统配置", sort_order=70,
    )

    # 模块: trace（可观测性）
    # 注：`trace.ranking`（查看排行榜）已**合并进 `trace.view`** —— 二者语义重叠，
    #     且原先排行榜还要单独勾选，实际使用中只会造成"勾了链路却看不到排行"的困惑。
    #     合并采用 grant-then-delete（见 registry.seed_to_db），持有旧 key 的角色
    #     会自动获得 `trace.view`，不会掉权限。
    #     ⚠️ 副作用：此后凡有「查看链路」的角色都能看到**所有用户**的 Token 消耗排名。
    register_perm(
        key="trace.view", label="查看链路",
        description="查看 LLM 调用链路与统计，含所有用户的 Token 消耗排行榜",
        group_name="trace", group_label="可观测性", sort_order=80,
    )
    register_perm(
        key="trace.manage", label="查看全部用户",
        description="查看所有用户的链路数据 + 配置采集策略",
        group_name="trace", group_label="可观测性", sort_order=82,
    )

    # 模块: paper（论文复现）
    register_perm(
        key="paper.use", label="使用论文复现",
        description="使用论文复现系统（解析论文、提取主张、代码复现、证据验证）",
        group_name="paper", group_label="论文复现", sort_order=90,
    )

    # 模块: kb（知识库）— 单一权限
    register_perm(
        key="kb.manage", label="管理知识库",
        description="查看/创建/编辑/删除知识库和文档（全部操作）",
        group_name="kb", group_label="知识库", sort_order=90,
    )
    register_perm(
        key="kb.eval", label="RAG 测评",
        description="创建/运行知识库测评集，查看评测结果",
        group_name="kb", group_label="知识库", sort_order=91,
    )

    # 模块: graph（知识图谱 - 属于知识库权限组）
    # 注：原 graph 细粒度权限（查看/审核/社区检测）已废弃并合并进 graph.manage
    #（统一入口，避免三层 fallback 链口径不一致；废弃 key 由 registry.py 的 obsolete_keys 清理）
    register_perm(
        key="graph.manage", label="管理知识图谱",
        description=(
            "知识图谱统一权限：查看图谱（节点/关系/子图/路径）、实体与关系的新增/编辑/删除、"
            "实体审核（可疑实体与关系）、社区检测（Louvain）与社区报告、GraphRAG 智能检索"
        ),
        group_name="kb", group_label="知识库", sort_order=92,
    )


# ── 工具集（toolset）定义 ──

TOOLSET_DEFINITIONS = [
    {"key": "terminal",       "label": "终端执行",   "desc": "执行 Shell 命令",          "group": "hermes"},
    {"key": "file",           "label": "文件读写",   "desc": "读写文件",               "group": "hermes"},
    {"key": "web",            "label": "网络搜索",   "desc": "搜索网页和抓取 URL",        "group": "hermes"},
    {"key": "notification",   "label": "通知推送",   "desc": "消息通知推送",           "group": "project"},
    {"key": "schedule",       "label": "定时任务",   "desc": "定时任务管理",           "group": "project"},
    {"key": "paper_repro",    "label": "论文复现",   "desc": "学术论文代码复现系统",     "group": "project"},
]

# 各角色的默认 toolset 分配
# 注：data toolset 已移除，knowledge_search 所有用户默认可用，无需权限分配
# 注：memory / session_search 已移除，AgentForge 记忆架构原生支持跨会话，无需 Hermes 原生工具
# 注：utility（时间/TODO 等基础工具）已改为 __always_available__，所有用户自动可用，无需权限分配
DEFAULT_ROLE_TOOLSETS = {
    "super_admin": [t["key"] for t in TOOLSET_DEFINITIONS],
    "admin":       ["terminal", "file", "web", "notification", "schedule", "paper_repro"],
    "user":        ["web", "paper_repro"],
}

# ── 内置角色的默认权限 ──
#
# 为什么需要它：此前内置角色的默认权限**只**由 `sql/agentforge_schema.sql` 播种，
# 而那份种子里的 key 早已过期（含 skill.view / agent.* / review.* / config.view /
# admin.departments 等**已不存在**的 key）。它们既不在 permission_defs 里、也不被
# obsolete_keys 清理，于是成为"幻影授权"：`_get_role_permissions()` 读得到、
# 前端看不到也改不掉。结果是**全新部署**的 admin 只剩 3 个有效权限
# （chat.use / skill.create / kb.manage），系统管理、可观测性、定时任务全部 403。
#
# 用法：`registry.seed_to_db()` 会**仅当某角色一条授权都没有时**才按此播种，
# 因此它不会覆盖管理员在前端角色编辑里做过的任何勾选/取消。
#
# 注意：当前注册的权限共 16 个，super_admin/admin 持有全部 16 个。
DEFAULT_ROLE_PERMISSIONS: dict = {
    # super_admin 由 seed_to_db() 按注册表全量重置，此处列出仅为完整性
    "super_admin": [
        "chat.use", "skill.create", "skill.pool.review", "skill.manage",
        "memory.view", "memory.edit", "terminal.audit", "cron.create",
        "system.manage", "system.config",
        "trace.view", "trace.manage",
        "kb.manage", "kb.eval", "graph.manage",
        "paper.use",
    ],
    # admin 持有全部 16 个权限
    "admin": [
        "chat.use", "skill.create", "skill.pool.review", "skill.manage",
        "memory.view", "memory.edit", "terminal.audit", "cron.create",
        "system.manage", "system.config",
        "trace.view", "trace.manage",
        "kb.manage", "kb.eval", "graph.manage",
        "paper.use",
    ],
    # 普通用户：基础可用集合。
    # 注：`trace.ranking` 已合并进 `trace.view`，故此处 `trace.view` 同时意味着
    #     可以看到所有用户的 Token 消耗排行榜（与活库现状一致 —— 活库的 user
    #     角色本来就持有 trace.ranking）。若不希望普通用户看到全站排行，
    #     请在角色编辑里取消 user 的「查看链路」，或改为不勾选该权限。
    "user": [
        "chat.use", "skill.create",
        "memory.view", "memory.edit",
        "cron.create", "trace.view",
        "paper.use",
    ],
}
