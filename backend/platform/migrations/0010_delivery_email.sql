-- 0010_delivery_email: SMTP 配置、收件人与按需报告能力。
-- 密码只存 AES-GCM 密文；配置响应只出掩码。未启用 SMTP/PDF 时不建立连接。

CREATE TABLE IF NOT EXISTS email_configs (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    host            TEXT    NOT NULL DEFAULT '',
    port            INTEGER NOT NULL DEFAULT 587,
    username        TEXT    NOT NULL DEFAULT '',
    password_cipher TEXT    NOT NULL DEFAULT '',
    sender_email    TEXT    NOT NULL DEFAULT '',
    sender_name     TEXT    NOT NULL DEFAULT 'EasyChat',
    use_tls         INTEGER NOT NULL DEFAULT 1,
    enabled         INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS email_recipients (
    id         TEXT PRIMARY KEY,
    owner_id   INTEGER NOT NULL REFERENCES users(id),
    name       TEXT NOT NULL DEFAULT '',
    address    TEXT NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(owner_id, address)
);
CREATE INDEX IF NOT EXISTS idx_email_recipients_owner ON email_recipients(owner_id, active);

-- 邮件主题（文本提醒为空；报告投递保存标题）
ALTER TABLE deliveries ADD COLUMN subject TEXT NOT NULL DEFAULT '';
