-- 角色归属、入队快照与微信来源历史。
CREATE TABLE persona_catalog (
    id          TEXT PRIMARY KEY,
    owner_id    INTEGER NOT NULL REFERENCES users(id),
    name        TEXT NOT NULL,
    name_key    TEXT NOT NULL,
    instruction TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    active      INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE(owner_id, name_key)
);

-- 旧会话及运行保留 NULL，继续使用默认角色。
ALTER TABLE sessions ADD COLUMN persona_id TEXT REFERENCES persona_catalog(id);
ALTER TABLE runs ADD COLUMN persona_id TEXT REFERENCES persona_catalog(id);
ALTER TABLE runs ADD COLUMN persona_version INTEGER;
ALTER TABLE runs ADD COLUMN persona_instruction TEXT NOT NULL DEFAULT '';

-- A role bound to a session belongs to the same owner and stays fixed for its history.
CREATE TRIGGER sessions_persona_owner_insert
BEFORE INSERT ON sessions
WHEN NEW.persona_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM persona_catalog WHERE id = NEW.persona_id AND owner_id = NEW.owner_id
)
BEGIN
    SELECT RAISE(ABORT, 'session persona owner mismatch');
END;

CREATE TRIGGER sessions_persona_immutable
BEFORE UPDATE OF persona_id, owner_id ON sessions
WHEN NEW.persona_id IS NOT OLD.persona_id OR
     (OLD.persona_id IS NOT NULL AND NEW.owner_id IS NOT OLD.owner_id)
BEGIN
    SELECT RAISE(ABORT, 'session persona is immutable');
END;

CREATE TRIGGER runs_persona_session_insert
BEFORE INSERT ON runs
WHEN NOT EXISTS (
    SELECT 1 FROM sessions
    WHERE id = NEW.session_id AND owner_id = NEW.owner_id AND persona_id IS NEW.persona_id
)
BEGIN
    SELECT RAISE(ABORT, 'run persona session mismatch');
END;

CREATE TABLE channel_session_history (
    session_id       TEXT PRIMARY KEY REFERENCES sessions(id),
    platform         TEXT NOT NULL,
    account_id       TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    external_chat_id TEXT NOT NULL,
    context_token    TEXT NOT NULL DEFAULT '',
    updated_at       TEXT NOT NULL
);
CREATE INDEX idx_channel_session_history_origin ON channel_session_history(
    platform, account_id, external_user_id, external_chat_id, updated_at DESC
);

-- 优先保留仍存在的活动游标。更早的路线只在找到已处理的原始 run 入站事件时恢复。
INSERT OR IGNORE INTO channel_session_history
    (session_id, platform, account_id, external_user_id, external_chat_id, context_token, updated_at)
SELECT c.session_id, c.platform, c.account_id, c.external_user_id, c.external_chat_id, c.context_token, c.updated_at
FROM channel_session_cursors c
JOIN sessions s ON s.id = c.session_id AND s.source = c.platform
JOIN channel_accounts a ON a.id = s.channel_account_id AND a.platform = c.platform AND a.account_id = c.account_id
ORDER BY c.updated_at DESC;

INSERT OR IGNORE INTO channel_session_history
    (session_id, platform, account_id, external_user_id, external_chat_id, context_token, updated_at)
SELECT s.id, e.platform, e.account_id,
       json_extract(e.envelope_json, '$.external_user_id'),
       json_extract(e.envelope_json, '$.external_chat_id'),
       COALESCE(json_extract(e.envelope_json, '$.context_token'), ''),
       COALESCE(e.processed_at, e.received_at)
FROM channel_events e
JOIN runs r ON r.id = e.run_id AND r.session_id = e.session_id AND r.source = e.platform
JOIN sessions s ON s.id = r.session_id AND s.owner_id = r.owner_id AND s.source = e.platform
JOIN channel_accounts a ON a.id = s.channel_account_id AND a.platform = e.platform AND a.account_id = e.account_id
WHERE e.state = 'processed' AND CASE WHEN json_valid(e.envelope_json) THEN
      json_extract(e.envelope_json, '$.account_pk') = a.id
      AND json_type(e.envelope_json, '$.external_user_id') = 'text'
      AND json_type(e.envelope_json, '$.external_chat_id') = 'text'
      ELSE 0 END
ORDER BY e.received_at DESC;

-- 重放继续使用首次解析的会话，保护角色和 owner 边界。
ALTER TABLE channel_events ADD COLUMN origin_session_id TEXT NOT NULL DEFAULT '';
ALTER TABLE channel_events ADD COLUMN origin_owner_id INTEGER REFERENCES users(id);
ALTER TABLE channel_events ADD COLUMN origin_cursor_version INTEGER;
ALTER TABLE channel_session_cursors ADD COLUMN cursor_version INTEGER NOT NULL DEFAULT 0;
