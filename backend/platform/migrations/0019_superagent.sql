-- 0019_superagent: 超级代理（微信收需求 → 后台编码 → 自动提 PR）。
--
-- 设计对齐 deepseek-ai/dsh-superagent-prototype 的领域模型：
--   Source(微信/Web) → Ticket(superagent_tasks) → Executor(独立会话+工作区)
--   → PR(GitHub) → Reply(delivery 回微信)。
-- 约定：
--   * 任务表自身就是队列（queued → running → 终态），不走共享 jobs 表：
--     编码任务单次执行可达数十分钟，超过 JobQueue lease 语义；
--   * settings 是单行部署级配置（id=1），token 只存 AES-GCM 密文；
--   * events 是面向面板的任务时间线，按任务追加，有界（写入方截断）。

CREATE TABLE IF NOT EXISTS superagent_settings (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    enabled          INTEGER NOT NULL DEFAULT 0,
    repo_url         TEXT    NOT NULL DEFAULT '',
    base_branch      TEXT    NOT NULL DEFAULT 'main',
    github_token_enc TEXT    NOT NULL DEFAULT '',
    pr_labels        TEXT    NOT NULL DEFAULT '',
    max_concurrent   INTEGER NOT NULL DEFAULT 1,
    updated_at       TEXT    NOT NULL DEFAULT ''
);

INSERT INTO superagent_settings (id, enabled, updated_at)
SELECT 1, 0, ''
WHERE NOT EXISTS (SELECT 1 FROM superagent_settings WHERE id = 1);

CREATE TABLE IF NOT EXISTS superagent_tasks (
    id             TEXT    PRIMARY KEY,
    owner_id       INTEGER NOT NULL REFERENCES users(id),
    title          TEXT    NOT NULL DEFAULT '',
    requirement    TEXT    NOT NULL DEFAULT '',
    context_extra  TEXT    NOT NULL DEFAULT '',
    source         TEXT    NOT NULL DEFAULT 'wechat',
    session_id     TEXT    NOT NULL DEFAULT '',
    status         TEXT    NOT NULL DEFAULT 'queued',
    branch         TEXT    NOT NULL DEFAULT '',
    pr_url         TEXT    NOT NULL DEFAULT '',
    pr_number      INTEGER,
    result_summary TEXT    NOT NULL DEFAULT '',
    error          TEXT    NOT NULL DEFAULT '',
    run_id         TEXT    NOT NULL DEFAULT '',
    attempts       INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL,
    started_at     TEXT,
    finished_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_superagent_tasks_owner
    ON superagent_tasks(owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_superagent_tasks_status
    ON superagent_tasks(status, created_at);

CREATE TABLE IF NOT EXISTS superagent_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    TEXT    NOT NULL REFERENCES superagent_tasks(id) ON DELETE CASCADE,
    kind       TEXT    NOT NULL,
    detail     TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_superagent_events_task
    ON superagent_events(task_id, id);
