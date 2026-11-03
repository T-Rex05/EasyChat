-- 0009_evolution_validation: 候选验证报告与采用/回滚记录。
-- 验证与采用分离：报告可重放；采用只切 skills.active_version 指针。

CREATE TABLE IF NOT EXISTS evolution_validations (
    id                    TEXT PRIMARY KEY,
    task_id               TEXT,
    owner_id              INTEGER NOT NULL,
    skill_id              TEXT NOT NULL,
    baseline_version_id   TEXT NOT NULL DEFAULT '',
    candidate_version_id  TEXT NOT NULL,
    report                TEXT NOT NULL DEFAULT '{}',
    passed                INTEGER NOT NULL DEFAULT 0,
    reason                TEXT NOT NULL DEFAULT '',
    created_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_validations_skill ON evolution_validations(skill_id, created_at DESC);

CREATE TABLE IF NOT EXISTS evolution_adoptions (
    id            TEXT PRIMARY KEY,
    validation_id TEXT NOT NULL REFERENCES evolution_validations(id) ON DELETE CASCADE,
    owner_id      INTEGER NOT NULL,
    skill_id      TEXT NOT NULL,
    version_id    TEXT NOT NULL,
    action        TEXT NOT NULL,  -- adopt / rollback / keep
    reason        TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_adoptions_skill ON evolution_adoptions(skill_id, created_at DESC);
