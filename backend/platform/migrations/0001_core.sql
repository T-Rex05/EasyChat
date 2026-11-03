-- 0001_core: 首批业务表（access/models/assistant/channels/usage + jobs + app_settings）
-- 约束依据架构 §5.2；时间统一 UTC ISO-8601 文本；jobs 调度字段用 REAL epoch 秒。
-- 业务种子仅限无业务归属的系统默认值，全部幂等（ON CONFLICT DO NOTHING）。

-- ════════ access ════════

CREATE TABLE IF NOT EXISTS roles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    display_name TEXT    NOT NULL DEFAULT '',
    description  TEXT    NOT NULL DEFAULT '',
    is_system    INTEGER NOT NULL DEFAULT 0,
    hermes_tools TEXT    NOT NULL DEFAULT '[]',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password      TEXT    NOT NULL,
    email         TEXT    NOT NULL DEFAULT '',
    role          TEXT    NOT NULL DEFAULT 'user',
    role_id       INTEGER REFERENCES roles(id),
    avatar        TEXT    NOT NULL DEFAULT '',
    status        INTEGER NOT NULL DEFAULT 1,
    last_login_at TEXT,
    last_login_ip TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id);

CREATE TABLE IF NOT EXISTS role_permissions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id    INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    UNIQUE(role_id, permission)
);

CREATE TABLE IF NOT EXISTS user_permissions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission TEXT    NOT NULL,
    granted    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT    NOT NULL,
    UNIQUE(user_id, permission)
);

CREATE TABLE IF NOT EXISTS permission_defs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT    NOT NULL UNIQUE,
    label       TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    group_name  TEXT    NOT NULL,
    group_label TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL
);

-- ════════ channels ════════

CREATE TABLE IF NOT EXISTS channel_accounts (
    id             TEXT PRIMARY KEY,
    platform       TEXT    NOT NULL,
    account_id     TEXT    NOT NULL,
    display_name   TEXT    NOT NULL DEFAULT '',
    status         TEXT    NOT NULL DEFAULT 'active',
    credentials_ref TEXT   NOT NULL DEFAULT '',
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL,
    UNIQUE(platform, account_id)
);

CREATE TABLE IF NOT EXISTS channel_bindings (
    id               TEXT PRIMARY KEY,
    platform         TEXT    NOT NULL,
    account_id       TEXT    NOT NULL,
    external_user_id TEXT    NOT NULL,
    user_id          INTEGER NOT NULL REFERENCES users(id),
    status           TEXT    NOT NULL DEFAULT 'active',
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    UNIQUE(platform, account_id, external_user_id)
);
CREATE INDEX IF NOT EXISTS idx_bindings_user ON channel_bindings(user_id);

CREATE TABLE IF NOT EXISTS channel_events (
    id                TEXT PRIMARY KEY,
    platform          TEXT NOT NULL,
    account_id        TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    event_kind        TEXT NOT NULL DEFAULT '',
    payload           TEXT NOT NULL DEFAULT '{}',
    fingerprint       TEXT NOT NULL DEFAULT '',
    received_at       TEXT NOT NULL,
    processed_at      TEXT,
    UNIQUE(platform, account_id, external_event_id)
);

-- ════════ assistant ════════

-- channel_account_id 使用非空规范值：Web/无渠道账号用 ''（架构 §5.2）
CREATE TABLE IF NOT EXISTS sessions (
    id                TEXT PRIMARY KEY,
    owner_id          INTEGER NOT NULL REFERENCES users(id),
    title             TEXT    NOT NULL DEFAULT '',
    source            TEXT    NOT NULL DEFAULT 'web',
    channel_account_id TEXT   NOT NULL DEFAULT '',
    external_chat_id  TEXT    NOT NULL DEFAULT '',
    hermes_session_id TEXT    NOT NULL DEFAULT '',
    active            INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_owner ON sessions(owner_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS runs (
    id                   TEXT PRIMARY KEY,
    owner_id             INTEGER NOT NULL REFERENCES users(id),
    session_id           TEXT    NOT NULL REFERENCES sessions(id),
    source               TEXT    NOT NULL,
    channel_account_scope TEXT   NOT NULL DEFAULT '',
    client_message_id    TEXT    NOT NULL,
    status               TEXT    NOT NULL DEFAULT 'queued',
    input_summary        TEXT    NOT NULL DEFAULT '',
    attachment_ids       TEXT    NOT NULL DEFAULT '[]',
    artifact_refs        TEXT    NOT NULL DEFAULT '[]',
    error                TEXT,
    runtime_checkpoint   TEXT,
    created_at           TEXT    NOT NULL,
    started_at           TEXT,
    finished_at          TEXT,
    UNIQUE(owner_id, session_id, source, channel_account_scope, client_message_id)
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

CREATE TABLE IF NOT EXISTS conversations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT    NOT NULL,
    owner_id      INTEGER NOT NULL,
    run_id        TEXT,
    role          TEXT    NOT NULL,
    content       TEXT    NOT NULL,
    status        INTEGER NOT NULL DEFAULT 1,
    chat_mode     TEXT    NOT NULL DEFAULT 'normal',
    session_title TEXT,
    source        TEXT    NOT NULL DEFAULT 'web',
    metadata      TEXT    NOT NULL DEFAULT '{}',
    seq           INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_owner_status ON conversations(owner_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id, created_at);

CREATE TABLE IF NOT EXISTS attachments (
    id         TEXT PRIMARY KEY,
    owner_id   INTEGER NOT NULL REFERENCES users(id),
    session_id TEXT    NOT NULL DEFAULT '',
    run_id     TEXT,
    file_name  TEXT    NOT NULL DEFAULT '',
    file_path  TEXT    NOT NULL,
    file_size  INTEGER NOT NULL DEFAULT 0,
    mime       TEXT    NOT NULL DEFAULT '',
    file_type  INTEGER NOT NULL DEFAULT 0,
    sha256     TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attachments_session ON attachments(session_id);

-- ════════ usage ════════

CREATE TABLE IF NOT EXISTS llm_calls (
    call_id           TEXT PRIMARY KEY,
    owner_id          INTEGER NOT NULL,
    source            TEXT    NOT NULL,
    run_id            TEXT,
    session_id        TEXT,
    provider          TEXT    NOT NULL DEFAULT '',
    model             TEXT    NOT NULL DEFAULT '',
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    reasoning_tokens  INTEGER,
    cached_tokens     INTEGER,
    usage_complete    INTEGER NOT NULL DEFAULT 0,
    estimated         INTEGER NOT NULL DEFAULT 0,
    raw_usage         TEXT    NOT NULL DEFAULT '{}',
    status            TEXT    NOT NULL DEFAULT 'ok',
    error             TEXT,
    created_at        TEXT    NOT NULL,
    completed_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_calls_owner_time ON llm_calls(owner_id, created_at);
CREATE INDEX IF NOT EXISTS idx_calls_run ON llm_calls(run_id);

CREATE TABLE IF NOT EXISTS daily_user_stats (
    stat_date         TEXT    NOT NULL,
    user_id           INTEGER NOT NULL,
    source            TEXT    NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    call_count        INTEGER NOT NULL DEFAULT 0,
    UNIQUE(stat_date, user_id, source)
);

-- ════════ models ════════

CREATE TABLE IF NOT EXISTS model_configs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL,
    provider         TEXT    NOT NULL,
    model            TEXT    NOT NULL,
    api_key_ref      TEXT    NOT NULL DEFAULT '',
    base_url         TEXT    NOT NULL DEFAULT '',
    is_active        INTEGER NOT NULL DEFAULT 0,
    is_multimodal    INTEGER NOT NULL DEFAULT 0,
    reasoning_effort TEXT    NOT NULL DEFAULT '',
    config_version   INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);

-- ════════ 平台 ════════

CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    kind            TEXT    NOT NULL,
    dedup_key       TEXT    NOT NULL UNIQUE,
    owner_id        INTEGER,
    payload_version INTEGER NOT NULL DEFAULT 1,
    payload         TEXT    NOT NULL DEFAULT '{}',
    state           TEXT    NOT NULL DEFAULT 'pending',
    available_at    REAL    NOT NULL,
    lease_until     REAL,
    lease_owner     TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 5,
    last_error      TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs(state, available_at);

-- ════════ 系统种子（幂等） ════════

INSERT INTO app_settings(key, value, updated_at)
VALUES ('timezone', '"Asia/Shanghai"', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
ON CONFLICT(key) DO NOTHING;
