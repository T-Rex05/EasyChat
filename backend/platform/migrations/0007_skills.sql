-- 0007_skills: 个人技能资产、不可变版本与激活指针。
-- 内容文件不可变（版本路径由版本ID决定，与用户可控name无关）；
-- 元数据先写文件后入库，孤立文件延迟清理；active指针是DB权威。

CREATE TABLE IF NOT EXISTS skills (
    id                TEXT PRIMARY KEY,
    owner_id          INTEGER NOT NULL REFERENCES users(id),
    name              TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    origin            TEXT NOT NULL DEFAULT 'user', -- user / web / background / evolution
    pinned            INTEGER NOT NULL DEFAULT 0,
    archived          INTEGER NOT NULL DEFAULT 0,
    active_version_id TEXT,                         -- 指向 skill_versions.id；由条件更新维护
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE(owner_id, name)
);
CREATE INDEX IF NOT EXISTS idx_skills_owner_archived
    ON skills(owner_id, archived, updated_at DESC);

CREATE TABLE IF NOT EXISTS skill_versions (
    id                TEXT PRIMARY KEY,
    skill_id          TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    version_seq       INTEGER NOT NULL,
    content_path      TEXT NOT NULL,   -- 相对技能内容根目录；不接受用户控制
    content_hash      TEXT NOT NULL,   -- sha256(内容字节)
    parent_version_id TEXT,
    source            TEXT NOT NULL,   -- user / web / background / evolution
    status            TEXT NOT NULL DEFAULT 'draft', -- draft/validated/rejected/active/superseded
    created_at        TEXT NOT NULL,
    UNIQUE(skill_id, version_seq)
);
CREATE INDEX IF NOT EXISTS idx_skill_versions_skill
    ON skill_versions(skill_id, version_seq DESC);
