-- 0005_delivery: 不可变产物、投递账本、分块尝试与提醒计划/实例。
-- 投递与生成分离：run 终态/报告产物先落库，发送失败只重试同一结果。
-- 时间：投递重试/计划下次执行用 REAL epoch 秒；业务时间戳用 UTC ISO 文本。

CREATE TABLE IF NOT EXISTS artifacts (
    id         TEXT PRIMARY KEY,
    owner_id   INTEGER NOT NULL REFERENCES users(id),
    run_id     TEXT,
    kind       TEXT NOT NULL DEFAULT 'report',
    file_path  TEXT NOT NULL DEFAULT '',
    sha256     TEXT NOT NULL DEFAULT '',
    file_size  INTEGER NOT NULL DEFAULT 0,
    mime       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_artifacts_owner ON artifacts(owner_id, created_at DESC);

-- 一个 run/提醒对应一条投递；dedup_key 保证同一业务结果只建一次。
CREATE TABLE IF NOT EXISTS deliveries (
    id                 TEXT PRIMARY KEY,
    owner_id           INTEGER NOT NULL REFERENCES users(id),
    run_id             TEXT,
    source             TEXT NOT NULL DEFAULT 'wechat',
    target_kind        TEXT NOT NULL,
    target_ref         TEXT NOT NULL,
    channel_account_id TEXT NOT NULL DEFAULT '',
    context_token      TEXT NOT NULL DEFAULT '',
    content_text       TEXT NOT NULL DEFAULT '',
    artifact_id        TEXT,
    dedup_key          TEXT NOT NULL UNIQUE,
    status             TEXT NOT NULL DEFAULT 'pending',
    attempts           INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    REAL NOT NULL DEFAULT 0,
    error              TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    sent_at            TEXT
);
CREATE INDEX IF NOT EXISTS idx_deliveries_due ON deliveries(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_deliveries_owner ON deliveries(owner_id, created_at DESC);

-- 分块：同一 delivery 的 seq 唯一；已发送块在重试时跳过。
CREATE TABLE IF NOT EXISTS delivery_parts (
    id          TEXT PRIMARY KEY,
    delivery_id TEXT NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    content     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    external_id TEXT NOT NULL DEFAULT '',
    error       TEXT NOT NULL DEFAULT '',
    sent_at     TEXT,
    UNIQUE(delivery_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_parts_delivery ON delivery_parts(delivery_id, seq);

-- 提醒计划：once/interval/daily；next_run_at 为 UTC epoch，重启后继续。
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id                 TEXT PRIMARY KEY,
    owner_id           INTEGER NOT NULL REFERENCES users(id),
    title              TEXT NOT NULL DEFAULT '',
    text               TEXT NOT NULL,
    target_kind        TEXT NOT NULL DEFAULT 'wechat',
    target_ref         TEXT NOT NULL,
    channel_account_id TEXT NOT NULL DEFAULT '',
    schedule_kind      TEXT NOT NULL,
    interval_seconds   INTEGER NOT NULL DEFAULT 0,
    at_time            TEXT NOT NULL DEFAULT '',
    timezone           TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    next_run_at        REAL NOT NULL,
    enabled            INTEGER NOT NULL DEFAULT 1,
    last_run_at        TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedules_due ON scheduled_jobs(enabled, next_run_at);

-- 每计划 scheduled_at 唯一：重启/重复 tick 不重复生成实例。
CREATE TABLE IF NOT EXISTS scheduled_occurrences (
    id           TEXT PRIMARY KEY,
    schedule_id  TEXT NOT NULL REFERENCES scheduled_jobs(id) ON DELETE CASCADE,
    scheduled_at TEXT NOT NULL,
    state        TEXT NOT NULL DEFAULT 'pending',
    delivery_id  TEXT NOT NULL DEFAULT '',
    missed       INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    processed_at TEXT,
    UNIQUE(schedule_id, scheduled_at)
);
CREATE INDEX IF NOT EXISTS idx_occurrences_schedule ON scheduled_occurrences(schedule_id, scheduled_at);

-- 渠道会话游标补 context_token：微信主动回复在 24h 窗口内需要它。
ALTER TABLE channel_session_cursors ADD COLUMN context_token TEXT NOT NULL DEFAULT '';
