-- 0026: MCP 服务器配置表（P4）。凭据列只存 enc:v1: 密文；能力默认关闭（enabled=0）。
CREATE TABLE IF NOT EXISTS mcp_servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    credential_enc TEXT NOT NULL DEFAULT '',
    allowed_tools TEXT NOT NULL DEFAULT '[]',
    excluded_tools TEXT NOT NULL DEFAULT '[]',
    connect_timeout_s INTEGER NOT NULL DEFAULT 60,
    call_timeout_s INTEGER NOT NULL DEFAULT 300,
    audience TEXT NOT NULL DEFAULT 'config_admin',
    enabled INTEGER NOT NULL DEFAULT 0,
    last_check_state TEXT NOT NULL DEFAULT '',
    last_check_error TEXT NOT NULL DEFAULT '',
    last_check_tools TEXT NOT NULL DEFAULT '[]',
    last_checked_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
