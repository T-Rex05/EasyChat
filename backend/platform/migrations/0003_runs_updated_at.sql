-- 0003_runs_updated_at: runs 表补充 updated_at（状态机推进时间戳），并回填 created_at。
ALTER TABLE runs ADD COLUMN updated_at TEXT;
UPDATE runs SET updated_at = created_at WHERE updated_at IS NULL;
