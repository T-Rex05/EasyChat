-- 0020_superagent_v2: 任务快照、执行 attempt、输入与报告（方案 §5）。
--
-- 目标（T1）：
--   * 受理时快照 repo/base/策略，执行读取快照而非当前配置（排队后换仓库不影响已受理任务）；
--   * attempts 把一次执行变成可恢复单元：checkpoint、head/remote SHA、PR 字段按 attempt 保存，
--     重试 = 新 attempt + 远端对账，迟到结果不得覆盖新 attempt（active_attempt_id + version CAS）；
--   * inputs 记录微信/HTTP 来源的原始输入（幂等键唯一），waiting_input 的追问回答续接同一任务；
--   * reports 结构化执行报告（progress/question/blocked/ready/failed/no_changes），发布门禁读取。
-- 兼容：全部 ALTER 追加可空/带默认列，旧行读取时 repo_url_snapshot='' 视为 legacy_config_unknown；
-- 已发布迁移 checksum 不变；新表 IF NOT EXISTS，回滚 = 不再使用新列/新表（旧代码忽略未知列会失败，
-- 回滚需恢复到 0019 代码版本并从备份还原，见方案 §11）。

ALTER TABLE superagent_tasks ADD COLUMN repo_url_snapshot TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN base_branch_snapshot TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN base_sha TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN settings_revision TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN policy_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE superagent_tasks ADD COLUMN source_event_id TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN source_channel_account_id TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN source_chat_id TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN source_ref TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN source_kind TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN executor_session_id TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN active_attempt_id TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE superagent_tasks ADD COLUMN phase TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN cancel_requested_at TEXT;
ALTER TABLE superagent_tasks ADD COLUMN pr_state TEXT NOT NULL DEFAULT '';
ALTER TABLE superagent_tasks ADD COLUMN outcome TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS superagent_attempts (
    id              TEXT    PRIMARY KEY,
    task_id         TEXT    NOT NULL REFERENCES superagent_tasks(id),
    attempt_no      INTEGER NOT NULL,
    run_id          TEXT    NOT NULL DEFAULT '',
    session_id      TEXT    NOT NULL DEFAULT '',
    workspace_key   TEXT    NOT NULL DEFAULT '',
    state           TEXT    NOT NULL DEFAULT 'running',
    checkpoint      TEXT    NOT NULL DEFAULT '',
    head_sha        TEXT    NOT NULL DEFAULT '',
    remote_head_sha TEXT    NOT NULL DEFAULT '',
    pr_number       INTEGER,
    pr_url          TEXT    NOT NULL DEFAULT '',
    started_at      TEXT    NOT NULL,
    heartbeat_at    TEXT    NOT NULL DEFAULT '',
    finished_at     TEXT,
    error_code      TEXT    NOT NULL DEFAULT '',
    error_summary   TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    UNIQUE(task_id, attempt_no)
);
CREATE INDEX IF NOT EXISTS idx_superagent_attempts_task
    ON superagent_attempts(task_id, attempt_no DESC);

CREATE TABLE IF NOT EXISTS superagent_inputs (
    id                  TEXT    PRIMARY KEY,
    task_id             TEXT    NOT NULL REFERENCES superagent_tasks(id),
    source              TEXT    NOT NULL,
    external_event_id   TEXT    NOT NULL DEFAULT '',
    actor_id            INTEGER NOT NULL DEFAULT 0,
    text                TEXT    NOT NULL DEFAULT '',
    attachment_refs     TEXT    NOT NULL DEFAULT '[]',
    created_at          TEXT    NOT NULL,
    consumed_attempt_id TEXT    NOT NULL DEFAULT ''
);
-- 幂等：同一来源的同一外部事件/Idempotency-Key 只产生一条输入。
CREATE UNIQUE INDEX IF NOT EXISTS uq_superagent_inputs_event
    ON superagent_inputs(source, external_event_id)
    WHERE external_event_id <> '';
CREATE INDEX IF NOT EXISTS idx_superagent_inputs_task
    ON superagent_inputs(task_id, created_at);

CREATE TABLE IF NOT EXISTS superagent_reports (
    id               TEXT    PRIMARY KEY,
    task_id          TEXT    NOT NULL REFERENCES superagent_tasks(id),
    attempt_id       TEXT    NOT NULL DEFAULT '',
    kind             TEXT    NOT NULL,
    summary          TEXT    NOT NULL DEFAULT '',
    question         TEXT    NOT NULL DEFAULT '',
    head_sha         TEXT    NOT NULL DEFAULT '',
    verification_ref TEXT    NOT NULL DEFAULT '',
    created_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_superagent_reports_task
    ON superagent_reports(task_id, created_at);

-- 仓库验证策略（管理员配置；JSON 数组 [{name, command, timeout_seconds}]）与
-- 未验证发布策略（默认允许 Draft PR 但在报告中记录缺失证据；置 0 后缺验证 → blocked）。
ALTER TABLE superagent_settings ADD COLUMN verify_profile TEXT NOT NULL DEFAULT '[]';
ALTER TABLE superagent_settings ADD COLUMN allow_unverified_draft INTEGER NOT NULL DEFAULT 1;
