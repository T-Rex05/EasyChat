-- 0011_files: 统一文件权威（stored_files / upload_receipts / file_references / file_extractions）
--
-- 设计依据 docs/superpowers/specs/2026-11-04-files-ledger-design.md §4–§5。
-- 约定：
--   * 数据库只存相对 storage_key，原文件名只是展示元数据，不参与路径定位；
--   * 完整性状态（status）与分析状态（file_extractions.state）分开；
--   * 同 owner 相同 sha256 复用一条 stored_file，跨 owner 不做去重；
--   * 旧 attachments/artifacts 追加 stored_file_id，保持旧 ID 可用（不是第二套权威）。

CREATE TABLE IF NOT EXISTS stored_files (
    id               TEXT    PRIMARY KEY,
    owner_id         INTEGER NOT NULL REFERENCES users(id),
    storage_key      TEXT    NOT NULL UNIQUE,
    original_name    TEXT    NOT NULL DEFAULT '',
    declared_mime    TEXT    NOT NULL DEFAULT '',
    verified_mime    TEXT    NOT NULL DEFAULT '',
    size_bytes       INTEGER NOT NULL DEFAULT 0,
    sha256           TEXT    NOT NULL DEFAULT '',
    kind             TEXT    NOT NULL DEFAULT 'other',
    status           TEXT    NOT NULL DEFAULT 'receiving',
    source           TEXT    NOT NULL DEFAULT '',
    retention_policy TEXT    NOT NULL DEFAULT 'permanent',
    error            TEXT,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    deleted_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_stored_files_owner ON stored_files(owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stored_files_owner_hash ON stored_files(owner_id, sha256);
CREATE INDEX IF NOT EXISTS idx_stored_files_status ON stored_files(status, updated_at);
-- 同 owner 同内容复用；deleted 记录不占位，重新上传可建新行
CREATE UNIQUE INDEX IF NOT EXISTS uq_stored_files_owner_hash
    ON stored_files(owner_id, sha256) WHERE sha256 <> '' AND status <> 'deleted';

CREATE TABLE IF NOT EXISTS upload_receipts (
    id                TEXT    PRIMARY KEY,
    owner_id          INTEGER NOT NULL REFERENCES users(id),
    request_id        TEXT    NOT NULL DEFAULT '',
    channel           TEXT    NOT NULL DEFAULT '',
    account_id        TEXT    NOT NULL DEFAULT '',
    external_event_id TEXT    NOT NULL DEFAULT '',
    media_index       INTEGER NOT NULL DEFAULT -1,
    file_id           TEXT    REFERENCES stored_files(id),
    state             TEXT    NOT NULL DEFAULT 'receiving',
    expected_key      TEXT    NOT NULL DEFAULT '',
    expected_sha256   TEXT    NOT NULL DEFAULT '',
    expected_size     INTEGER NOT NULL DEFAULT 0,
    original_name     TEXT    NOT NULL DEFAULT '',
    error             TEXT,
    received_at       TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);
-- Web 幂等键：owner + 调用方 request_id（空串不参与，避免所有 Web 上传互相冲突）
CREATE UNIQUE INDEX IF NOT EXISTS uq_upload_receipt_request
    ON upload_receipts(owner_id, request_id) WHERE request_id <> '';
-- 微信媒体幂等键：账号 + 事件 + 附件序号（与 channel_events 同粒度）
CREATE UNIQUE INDEX IF NOT EXISTS uq_upload_receipt_media
    ON upload_receipts(channel, account_id, external_event_id, media_index)
    WHERE external_event_id <> '' AND media_index >= 0;
CREATE INDEX IF NOT EXISTS idx_upload_receipts_state ON upload_receipts(state, updated_at);

CREATE TABLE IF NOT EXISTS file_references (
    id         TEXT PRIMARY KEY,
    file_id    TEXT NOT NULL REFERENCES stored_files(id),
    owner_id   INTEGER NOT NULL REFERENCES users(id),
    ref_kind   TEXT NOT NULL,
    ref_id     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(file_id, ref_kind, ref_id)
);
CREATE INDEX IF NOT EXISTS idx_file_refs_target ON file_references(ref_kind, ref_id);
CREATE INDEX IF NOT EXISTS idx_file_refs_file ON file_references(file_id);

CREATE TABLE IF NOT EXISTS file_extractions (
    id                TEXT    PRIMARY KEY,
    file_id           TEXT    NOT NULL REFERENCES stored_files(id),
    owner_id          INTEGER NOT NULL REFERENCES users(id),
    extractor         TEXT    NOT NULL,
    extractor_version TEXT    NOT NULL,
    input_hash        TEXT    NOT NULL DEFAULT '',
    state             TEXT    NOT NULL DEFAULT 'pending',
    derived_file_id   TEXT    REFERENCES stored_files(id),
    quality_summary   TEXT    NOT NULL DEFAULT '{}',
    error             TEXT,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    UNIQUE(file_id, extractor, extractor_version, input_hash)
);
CREATE INDEX IF NOT EXISTS idx_file_extractions_file ON file_extractions(file_id, created_at);
CREATE INDEX IF NOT EXISTS idx_file_extractions_state ON file_extractions(state, updated_at);

-- 旧附件/产物表：追加统一文件引用（旧 path 读取保留到迁移核验完成）
ALTER TABLE attachments ADD COLUMN stored_file_id TEXT;
ALTER TABLE artifacts ADD COLUMN stored_file_id TEXT;
