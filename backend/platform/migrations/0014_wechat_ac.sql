-- 0014_wechat_ac：微信 A+C（人格/收件箱/情绪）与 weekly/briefing 调度扩展。
-- 只追加；不改 0001–0013。时间文本统一 UTC ISO-8601，日期/星期按用户时区解释。

CREATE TABLE IF NOT EXISTS assistant_profiles (
    owner_id            INTEGER PRIMARY KEY REFERENCES users(id),
    persona_preset      TEXT NOT NULL DEFAULT 'warm',
    address_form        TEXT NOT NULL DEFAULT '你',
    max_chars           INTEGER NOT NULL DEFAULT 120,
    emoji_level         TEXT NOT NULL DEFAULT 'sparse',   -- none/sparse/rich
    proactivity         TEXT NOT NULL DEFAULT 'normal',   -- low/normal/high
    quiet_start         TEXT NOT NULL DEFAULT '23:00',
    quiet_end           TEXT NOT NULL DEFAULT '07:30',
    timezone            TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    custom_instruction  TEXT NOT NULL DEFAULT '',
    mood_opt_in         INTEGER NOT NULL DEFAULT 0,
    mood_retention_days INTEGER NOT NULL DEFAULT 90,
    last_care_at        TEXT,
    persona_revision    INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inbox_items (
    id            TEXT PRIMARY KEY,
    owner_id      INTEGER NOT NULL REFERENCES users(id),
    kind          TEXT NOT NULL,                 -- link/note/file/image
    title         TEXT NOT NULL DEFAULT '',
    url           TEXT NOT NULL DEFAULT '',
    file_id       TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT '',
    summary       TEXT NOT NULL DEFAULT '',
    tags_json     TEXT NOT NULL DEFAULT '[]',
    status        TEXT NOT NULL DEFAULT 'unread',-- unread/read/archived
    enrich_state  TEXT NOT NULL DEFAULT 'pending',-- pending/ready/failed/skipped
    source_run_id TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inbox_owner_status ON inbox_items(owner_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_inbox_owner_url ON inbox_items(owner_id, url) WHERE url <> '';

CREATE TABLE IF NOT EXISTS mood_entries (
    id            TEXT PRIMARY KEY,
    owner_id      INTEGER NOT NULL REFERENCES users(id),
    entry_date    TEXT NOT NULL,                 -- 用户时区 YYYY-MM-DD
    score         INTEGER NOT NULL,              -- -2..2，当日样本算术平均（四舍五入）
    score_total   INTEGER NOT NULL DEFAULT 0,    -- 当日全部样本分数之和（原始值）
    sample_count  INTEGER NOT NULL DEFAULT 1,    -- 当日有效样本数（上限 10）
    labels_json   TEXT NOT NULL DEFAULT '[]',
    summary       TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',    -- 最多 3 条短引文
    source_run_id TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(owner_id, entry_date)
);
CREATE INDEX IF NOT EXISTS idx_mood_owner_date ON mood_entries(owner_id, entry_date DESC);

ALTER TABLE scheduled_jobs ADD COLUMN weekday INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scheduled_jobs ADD COLUMN content_kind TEXT NOT NULL DEFAULT 'text';
ALTER TABLE scheduled_jobs ADD COLUMN briefing_kind TEXT NOT NULL DEFAULT '';
ALTER TABLE scheduled_occurrences ADD COLUMN job_id TEXT NOT NULL DEFAULT '';
