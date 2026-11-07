"""superagent 公开契约：状态、任务视图与部署级配置。

领域模型对齐 dsh-superagent-prototype：
Ticket（本模块的任务）由 Source（微信对话/Web 面板）产生，
Executor（worker）在独立会话与工作区执行，产物是 PR，回执走 delivery。
"""
from __future__ import annotations

from dataclasses import dataclass

# ---- 任务状态机（任务表自身就是队列，不走共享 jobs 表） ----------------------

TASK_QUEUED = "queued"        # 已受理，等待 worker 认领
TASK_RUNNING = "running"      # worker 执行中（独立会话+工作区）
TASK_SUCCEEDED = "succeeded"  # 完成（可能带 PR，也可能无代码变更）
TASK_FAILED = "failed"        # 失败（可 retry_task 重新入队）
TASK_CANCELLED = "cancelled"  # 用户取消

TERMINAL_TASK_STATUSES = frozenset({TASK_SUCCEEDED, TASK_FAILED, TASK_CANCELLED})

# ---- 事件类型（面板时间线） --------------------------------------------------

EVENT_CREATED = "created"
EVENT_STARTED = "started"
EVENT_PROGRESS = "progress"
EVENT_PR_CREATED = "pr_created"
EVENT_NO_CHANGES = "no_changes"
EVENT_FAILED = "failed"
EVENT_CANCELLED = "cancelled"
EVENT_NOTIFIED = "notified"

# ---- 来源 --------------------------------------------------------------------

SOURCE_WECHAT = "wechat"
SOURCE_WEB = "web"
SOURCE_TOOL = "tool"

MAX_EVENTS_PER_TASK = 200
REQUIREMENT_MAX_CHARS = 8000
SUMMARY_MAX_CHARS = 2000


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


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """任务时间线上的一个条目。"""

    event_id: int
    task_id: str
    kind: str
    detail: str
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
