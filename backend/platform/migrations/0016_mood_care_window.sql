-- 0016_mood_care_window：high 主动关心的滚动 7 天计数（§14.4）。
-- 只追加；last_care_at 继续表示最后成功发送时间，日志用于精确窗口计数。

CREATE TABLE IF NOT EXISTS mood_care_log (
    id         TEXT PRIMARY KEY,
    owner_id   INTEGER NOT NULL REFERENCES users(id),
    cared_at   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mood_care_owner_time
    ON mood_care_log(owner_id, cared_at DESC);
