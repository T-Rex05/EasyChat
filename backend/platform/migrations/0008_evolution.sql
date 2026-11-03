-- 0008_evolution: 学习任务、经验证据与每日/单次预算账本。
-- 后台学习唯一入口；按 source_event_id 去重；预算跨重启持久化。

CREATE TABLE IF NOT EXISTS evolution_tasks (
    id              TEXT PRIMARY KEY,
    owner_id        INTEGER NOT NULL,             -- SYSTEM_USER_ID=0 表示显式系统主体
    source_event_id TEXT NOT NULL,
    run_id          TEXT,
    source          TEXT NOT NULL DEFAULT 'chat', -- chat / schedule / memory / system
    status          TEXT NOT NULL DEFAULT 'pending', -- pending/running/done/rejected/paused
    evidence        TEXT NOT NULL DEFAULT '{}',
    budget_reserved INTEGER NOT NULL DEFAULT 0,
    budget_used     INTEGER NOT NULL DEFAULT 0,
    error           TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    finished_at     TEXT,
    UNIQUE(owner_id, source_event_id)
);
CREATE INDEX IF NOT EXISTS idx_evolution_tasks_status ON evolution_tasks(status, created_at);

CREATE TABLE IF NOT EXISTS evolution_experiences (
    id             TEXT PRIMARY KEY,
    task_id        TEXT NOT NULL REFERENCES evolution_tasks(id) ON DELETE CASCADE,
    owner_id       INTEGER NOT NULL,
    run_id         TEXT,
    content        TEXT NOT NULL,
    conditions     TEXT NOT NULL DEFAULT '',
    counterexample TEXT NOT NULL DEFAULT '',
    confidence     REAL NOT NULL DEFAULT 0.5,
    source_type    TEXT NOT NULL DEFAULT 'model_inferred',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experiences_owner ON evolution_experiences(owner_id, created_at DESC);

-- stat_date 按项目时区（Asia/Shanghai）；reserved 为未结算预留，used 为已核销。
CREATE TABLE IF NOT EXISTS evolution_budgets (
    stat_date TEXT    NOT NULL,
    user_id   INTEGER NOT NULL,
    reserved  INTEGER NOT NULL DEFAULT 0,
    used      INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT   NOT NULL,
    PRIMARY KEY(stat_date, user_id)
);
