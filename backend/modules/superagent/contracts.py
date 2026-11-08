"""superagent 公开契约：状态机、phase、attempt、输入与报告（方案 §5）。

领域模型对齐 dsh-superagent-prototype：
Ticket（任务）由 Source（微信对话/Web 面板）产生，Executor（worker）在独立
会话与工作区以 attempt 为单位执行，产物是 Draft PR，回执走 delivery。

状态兼容：status 保留 queued/running/succeeded/failed/cancelled 供旧调用方；
新增 waiting_input/blocked/awaiting_review/interrupted/cancel_requested。
执行阶段 phase 单独保存（preparing/coding/verifying/publishing），
PR 状态单独保存（draft/open/merged/closed），不把「创建 PR」当作「已合并」。
"""
from __future__ import annotations

from dataclasses import dataclass

# ---- 任务状态 ----------------------------------------------------------------

TASK_QUEUED = "queued"                # 已受理，等待 worker 认领
TASK_RUNNING = "running"              # 有活跃 attempt 在执行
TASK_SUCCEEDED = "succeeded"          # 完成（PR 已创建或确认无代码交付）
TASK_FAILED = "failed"                # 失败（可 retry_task 重新入队）
TASK_CANCELLED = "cancelled"          # 已取消（终态）
TASK_WAITING_INPUT = "waiting_input"  # 代理追问，等待用户补充
TASK_BLOCKED = "blocked"              # 受阻（缺凭证/缺验证环境/预算耗尽），可重试
TASK_AWAITING_REVIEW = "awaiting_review"  # PR 就绪等待评审
TASK_INTERRUPTED = "interrupted"      # 服务重启/崩溃中断，重试前先对账
TASK_CANCEL_REQUESTED = "cancel_requested"  # 已请求取消，等待执行实际停止

# 可重试的失败类状态
RETRYABLE_TASK_STATUSES = frozenset(
    {TASK_FAILED, TASK_CANCELLED, TASK_BLOCKED, TASK_INTERRUPTED}
)
# 终态（不可再变更，除非 retry 显式开新 attempt）
TERMINAL_TASK_STATUSES = frozenset({TASK_SUCCEEDED, TASK_CANCELLED})
# 占用 worker 的活跃状态
ACTIVE_TASK_STATUSES = frozenset({TASK_RUNNING, TASK_CANCEL_REQUESTED})

# ---- 执行 phase ----------------------------------------------------------------

PHASE_PREPARING = "preparing"
PHASE_CODING = "coding"
PHASE_VERIFYING = "verifying"
PHASE_PUBLISHING = "publishing"

# ---- PR 状态 --------------------------------------------------------------------

PR_DRAFT = "draft"
PR_OPEN = "open"
PR_MERGED = "merged"
PR_CLOSED = "closed"
OUTCOME_CLOSED_UNMERGED = "closed_unmerged"

# ---- attempt ------------------------------------------------------------------

ATTEMPT_RUNNING = "running"
ATTEMPT_SUCCEEDED = "succeeded"
ATTEMPT_FAILED = "failed"
ATTEMPT_INTERRUPTED = "interrupted"

# 发布检查点（按推进顺序；attempt.checkpoint 保存已确认到达的最高检查点）
CK_PREPARED = "prepared"      # 工作区就绪、base_sha 已记录
CK_CODED = "coded"            # 代理完成（观察到 completed 事件）
CK_VERIFIED = "verified"      # 验证命令通过
CK_PUSH_INTENT = "push_intent"  # 已持久化发布意图（尚未 push）
CK_PUSHED = "pushed"          # 分支已推送远端
CK_PR_INTENT = "pr_intent"    # 已持久化建 PR 意图
CK_PR_CREATED = "pr_created"  # PR 已确认存在（新建或复用）
CK_NOTIFIED = "notified"      # 回执已入队

CHECKPOINT_ORDER = (
    CK_PREPARED, CK_CODED, CK_VERIFIED, CK_PUSH_INTENT,
    CK_PUSHED, CK_PR_INTENT, CK_PR_CREATED, CK_NOTIFIED,
)

# ---- 报告类型 --------------------------------------------------------------------

REPORT_PROGRESS = "progress"
REPORT_QUESTION = "question"
REPORT_BLOCKED = "blocked"
REPORT_READY = "ready"
REPORT_FAILED = "failed"
REPORT_NO_CHANGES = "no_changes"

# ---- 事件类型（面板时间线） --------------------------------------------------

EVENT_CREATED = "created"
EVENT_STARTED = "started"
EVENT_PROGRESS = "progress"
EVENT_QUESTION = "question"
EVENT_BLOCKED = "blocked"
EVENT_PR_CREATED = "pr_created"
EVENT_NO_CHANGES = "no_changes"
EVENT_FAILED = "failed"
EVENT_CANCEL_REQUESTED = "cancel_requested"
EVENT_CANCELLED = "cancelled"
EVENT_CANCELLED_AFTER_PUBLICATION = "cancelled_after_publication"
EVENT_NOTIFIED = "notified"
EVENT_INPUT = "input"
EVENT_RECONCILED = "reconciled"
EVENT_ATTEMPT_STARTED = "attempt_started"

# ---- 状态展示名（微信回执与前端共用） ---------------------------------------------

STATUS_LABELS = {
    TASK_QUEUED: "排队中",
    TASK_RUNNING: "执行中",
    TASK_SUCCEEDED: "已完成",
    TASK_FAILED: "失败",
    TASK_CANCELLED: "已取消",
    TASK_WAITING_INPUT: "等待补充",
    TASK_BLOCKED: "受阻",
    TASK_AWAITING_REVIEW: "待评审",
    TASK_INTERRUPTED: "已中断",
    TASK_CANCEL_REQUESTED: "取消中",
}

# ---- 来源 --------------------------------------------------------------------

SOURCE_WECHAT = "wechat"
SOURCE_WEB = "web"
SOURCE_TOOL = "tool"
SOURCE_INPUT_WECHAT = "wechat"
SOURCE_INPUT_WEB = "web"
SOURCE_INPUT_TOOL = "tool"
SOURCE_INPUT_CLARIFY = "clarify"

MAX_EVENTS_PER_TASK = 200
REQUIREMENT_MAX_CHARS = 8000
SUMMARY_MAX_CHARS = 2000

# 追问协议：代理最终回复以该前缀行结尾表示需要用户补充（worker 解析后进入 waiting_input）
QUESTION_PREFIX = "QUESTION:"


@dataclass(frozen=True, slots=True)
class SuperagentTask:
    """一次编码任务的只读视图。"""

    task_id: str
    owner_id: int
    title: str
    requirement: str
    context_extra: str
    source: str
    session_id: str
    status: str
    branch: str
    pr_url: str
    pr_number: int
    result_summary: str
    error: str
    run_id: str
    attempts: int
    created_at: str
    updated_at: str
    started_at: str
    finished_at: str
    # v2 字段（旧任务回填为空值）
    repo_url_snapshot: str = ""
    base_branch_snapshot: str = ""
    base_sha: str = ""
    settings_revision: str = ""
    policy_revision: int = 0
    source_event_id: str = ""
    source_channel_account_id: str = ""
    source_chat_id: str = ""
    source_ref: str = ""
    source_kind: str = ""
    executor_session_id: str = ""
    active_attempt_id: str = ""
    version: int = 1
    phase: str = ""
    cancel_requested_at: str = ""
    pr_state: str = ""
    outcome: str = ""

    @property
    def legacy_config_unknown(self) -> bool:
        """旧任务（0020 之前受理）没有仓库快照，重新执行前需确认目标配置。"""
        return self.repo_url_snapshot == "" and self.status in (
            TASK_QUEUED, TASK_FAILED, TASK_INTERRUPTED, TASK_BLOCKED,
        )


@dataclass(frozen=True, slots=True)
class TaskAttempt:
    """一次执行尝试；发布检查点与 PR 证据按 attempt 保存。"""

    attempt_id: str
    task_id: str
    attempt_no: int
    run_id: str
    session_id: str
    workspace_key: str
    state: str
    checkpoint: str
    head_sha: str
    remote_head_sha: str
    pr_number: int
    pr_url: str
    started_at: str
    heartbeat_at: str
    finished_at: str
    error_code: str
    error_summary: str


@dataclass(frozen=True, slots=True)
class TaskInput:
    """任务输入（原始需求或追问回答）；幂等键 = (source, external_event_id)。"""

    input_id: str
    task_id: str
    source: str
    external_event_id: str
    actor_id: int
    text: str
    attachment_refs: str
    created_at: str
    consumed_attempt_id: str


@dataclass(frozen=True, slots=True)
class TaskReport:
    """结构化执行报告；发布门禁与微信回执读取。"""

    report_id: str
    task_id: str
    attempt_id: str
    kind: str
    summary: str
    question: str
    head_sha: str
    verification_ref: str
    created_at: str


@dataclass(frozen=True, slots=True)
class SuperagentSettings:
    """部署级配置（单行）。github_token 只对外出掩码。"""

    enabled: bool
    repo_url: str
    base_branch: str
    github_token_mask: str
    has_github_token: bool
    pr_labels: str
    max_concurrent: int
    updated_at: str
    verify_profile: str = "[]"
    allow_unverified_draft: bool = True
