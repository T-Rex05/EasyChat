-- 0006_memory: 事实/偏好、事件、经验统一模型 + 版本/反馈/遗忘规则/幂等信号。
-- 来源缺失不得补造；遗忘墓碑只保留哈希，不保留被删除原文。

CREATE TABLE IF NOT EXISTS memories (
    id            TEXT PRIMARY KEY,
    owner_id      INTEGER NOT NULL REFERENCES users(id),
    kind          TEXT NOT NULL,              -- fact / preference / event / experience
    content       TEXT NOT NULL,
    source_refs   TEXT NOT NULL DEFAULT '[]', -- JSON: [{"kind":"message","ref":"..."}]
    scope         TEXT NOT NULL DEFAULT 'user',
    event_at      TEXT,
    recorded_at   TEXT NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'active', -- active / archived / deleted
    pinned        INTEGER NOT NULL DEFAULT 0,
    confidence    REAL NOT NULL DEFAULT 0.5,
    source_type   TEXT NOT NULL DEFAULT 'model_inferred', -- user_confirmed / model_inferred
    supersedes    TEXT,
    last_decay_at TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_owner_status ON memories(owner_id, status, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_owner_kind ON memories(owner_id, kind, status);
CREATE INDEX IF NOT EXISTS idx_memories_event_at ON memories(owner_id, event_at);

CREATE TABLE IF NOT EXISTS memory_revisions (
    id          TEXT PRIMARY KEY,
    memory_id   TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    version     INTEGER NOT NULL,
    content     TEXT NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    source_refs TEXT NOT NULL DEFAULT '[]',
    actor       TEXT NOT NULL DEFAULT 'user',
    created_at  TEXT NOT NULL,
    UNIQUE(memory_id, version)
);

CREATE TABLE IF NOT EXISTS memory_tags (
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    tag       TEXT NOT NULL,
    UNIQUE(memory_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_memory_tags_tag ON memory_tags(tag);

CREATE TABLE IF NOT EXISTS memory_feedback (
    id              TEXT PRIMARY KEY,
    owner_id        INTEGER NOT NULL,
    memory_id       TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    source_event_id TEXT NOT NULL,
    signal          TEXT NOT NULL,  -- used / confirmed / rejected / corrected
    note            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    UNIQUE(memory_id, source_event_id)
);

-- 墓碑：只存目标哈希/类型，不存被删除的原文或可还原片段。
CREATE TABLE IF NOT EXISTS forget_rules (
    id           TEXT PRIMARY KEY,
    owner_id     INTEGER NOT NULL REFERENCES users(id),
    target_kind  TEXT NOT NULL,   -- memory / source_ref / content
    target_hash  TEXT NOT NULL,
    reason       TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    UNIQUE(owner_id, target_kind, target_hash)
);

-- 幂等信号：同一 source_event_id 只处理一次；job 消费此表。
CREATE TABLE IF NOT EXISTS memory_signals (
    id              TEXT PRIMARY KEY,
    owner_id        INTEGER NOT NULL REFERENCES users(id),
    source_event_id TEXT NOT NULL,
    signal          TEXT NOT NULL,  -- remember / forget / correct / stage_complete / feedback
    payload         TEXT NOT NULL DEFAULT '{}',
    state           TEXT NOT NULL DEFAULT 'pending', -- pending / processed / rejected / failed
    error           TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    processed_at    TEXT,
    UNIQUE(owner_id, source_event_id)
);
CREATE INDEX IF NOT EXISTS idx_memory_signals_state ON memory_signals(state, created_at);
