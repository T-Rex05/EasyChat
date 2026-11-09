-- 0015_mood_samples: 情绪采样幂等账本（只记 run/日期，不存原文）。
-- 目的：同一 run 重放不重复计入当天平均；并发采样在 BEGIN IMMEDIATE 下按日限额。

CREATE TABLE IF NOT EXISTS mood_samples (
    id         TEXT PRIMARY KEY,
    owner_id   INTEGER NOT NULL REFERENCES users(id),
    run_id     TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(owner_id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_mood_samples_owner_date
    ON mood_samples(owner_id, entry_date);
