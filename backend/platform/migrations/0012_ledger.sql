-- 0012_ledger: 账本/导入批次/原始行/标准交易/来源/退款关联/分类/规则/变更/分析
--
-- 设计依据 docs/superpowers/specs/2026-11-04-files-ledger-design.md §7–§8。
-- 约定：
--   * 金额一律整数最小货币单位（分），币种单独存（默认 CNY），不做浮点求和；
--   * 交易身份 identity_key 唯一（同一 owner 下），带 event_role 区分原支付/退款；
--   * 来源行 locator 稳定幂等（sheet+row 或 CSV 行号）；
--   * 导入批次最终文档不可原地改写：修正表现为 revision 递增 + ledger_changes；
--   * refund 关联允许多笔退款对应一笔原支付，累计不得超过原支付金额。

CREATE TABLE IF NOT EXISTS ledger_accounts (
    id            TEXT    PRIMARY KEY,
    owner_id      INTEGER NOT NULL REFERENCES users(id),
    provider      TEXT    NOT NULL,
    account_alias TEXT    NOT NULL DEFAULT '',
    currency      TEXT    NOT NULL DEFAULT 'CNY',
    timezone      TEXT    NOT NULL DEFAULT 'Asia/Shanghai',
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    UNIQUE(owner_id, provider, account_alias)
);

CREATE TABLE IF NOT EXISTS ledger_imports (
    id               TEXT    PRIMARY KEY,
    owner_id         INTEGER NOT NULL REFERENCES users(id),
    account_id       TEXT    NOT NULL REFERENCES ledger_accounts(id),
    file_id          TEXT    NOT NULL REFERENCES stored_files(id),
    parser           TEXT    NOT NULL,
    parser_version   TEXT    NOT NULL,
    state            TEXT    NOT NULL DEFAULT 'saved',
    declared_from    TEXT,
    declared_to      TEXT,
    coverage_kind    TEXT    NOT NULL DEFAULT 'unknown',
    currency         TEXT    NOT NULL DEFAULT 'CNY',
    control_totals   TEXT    NOT NULL DEFAULT '{}',
    row_counts       TEXT    NOT NULL DEFAULT '{}',
    quality          TEXT    NOT NULL DEFAULT '{}',
    error            TEXT,
    commit_request_id TEXT,
    revision         INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    UNIQUE(owner_id, file_id, parser, parser_version)
);
CREATE INDEX IF NOT EXISTS idx_ledger_imports_owner ON ledger_imports(owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ledger_imports_state ON ledger_imports(state, updated_at);
CREATE INDEX IF NOT EXISTS idx_ledger_imports_account ON ledger_imports(account_id, created_at);

CREATE TABLE IF NOT EXISTS ledger_source_rows (
    id         TEXT    PRIMARY KEY,
    import_id  TEXT    NOT NULL REFERENCES ledger_imports(id) ON DELETE CASCADE,
    owner_id   INTEGER NOT NULL REFERENCES users(id),
    sheet      TEXT    NOT NULL DEFAULT '',
    row_number INTEGER NOT NULL DEFAULT 0,
    locator    TEXT    NOT NULL,
    raw_fields TEXT    NOT NULL DEFAULT '{}',
    raw_hash   TEXT    NOT NULL DEFAULT '',
    parse_state TEXT   NOT NULL DEFAULT 'ok',
    errors     TEXT    NOT NULL DEFAULT '[]',
    -- 标准化投影（提交时不再重新解析；raw_fields 仍是原始权威）
    occurred_at TEXT,
    amount_minor INTEGER,
    currency   TEXT    NOT NULL DEFAULT 'CNY',
    direction  TEXT    NOT NULL DEFAULT 'unknown',
    event_role TEXT    NOT NULL DEFAULT 'payment',
    tx_type    TEXT    NOT NULL DEFAULT '',
    merchant   TEXT    NOT NULL DEFAULT '',
    product    TEXT    NOT NULL DEFAULT '',
    status     TEXT    NOT NULL DEFAULT '',
    external_id TEXT   NOT NULL DEFAULT '',
    merchant_id TEXT   NOT NULL DEFAULT '',
    note       TEXT    NOT NULL DEFAULT '',
    pay_method TEXT    NOT NULL DEFAULT '',
    id_reliable INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL,
    UNIQUE(import_id, locator)
);
CREATE INDEX IF NOT EXISTS idx_source_rows_import ON ledger_source_rows(import_id, row_number);

CREATE TABLE IF NOT EXISTS ledger_categories (
    id         TEXT    PRIMARY KEY,
    owner_id   INTEGER NOT NULL REFERENCES users(id),
    name       TEXT    NOT NULL,
    kind       TEXT    NOT NULL DEFAULT 'expense',
    parent_id  TEXT    REFERENCES ledger_categories(id),
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    UNIQUE(owner_id, name)
);

CREATE TABLE IF NOT EXISTS ledger_transactions (
    id            TEXT    PRIMARY KEY,
    owner_id      INTEGER NOT NULL REFERENCES users(id),
    account_id    TEXT    NOT NULL REFERENCES ledger_accounts(id),
    provider      TEXT    NOT NULL DEFAULT 'wechat',
    external_id   TEXT    NOT NULL DEFAULT '',
    event_role    TEXT    NOT NULL DEFAULT 'payment',
    identity_key  TEXT    NOT NULL,
    amount_minor  INTEGER NOT NULL,
    currency      TEXT    NOT NULL DEFAULT 'CNY',
    direction     TEXT    NOT NULL,
    tx_type       TEXT    NOT NULL DEFAULT '',
    merchant      TEXT    NOT NULL DEFAULT '',
    product       TEXT    NOT NULL DEFAULT '',
    occurred_at   TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT '',
    status_key    TEXT    NOT NULL DEFAULT 'unknown',
    category_id   TEXT    REFERENCES ledger_categories(id),
    verification  TEXT    NOT NULL DEFAULT 'parsed',
    revision      INTEGER NOT NULL DEFAULT 1,
    deleted_at    TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    UNIQUE(owner_id, identity_key)
);
CREATE INDEX IF NOT EXISTS idx_tx_owner_time ON ledger_transactions(owner_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_tx_account_time ON ledger_transactions(account_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_tx_external ON ledger_transactions(owner_id, external_id);
CREATE INDEX IF NOT EXISTS idx_tx_category ON ledger_transactions(owner_id, category_id);

CREATE TABLE IF NOT EXISTS ledger_transaction_sources (
    id            TEXT    PRIMARY KEY,
    owner_id      INTEGER NOT NULL REFERENCES users(id),
    transaction_id TEXT   NOT NULL REFERENCES ledger_transactions(id) ON DELETE CASCADE,
    source_row_id TEXT    NOT NULL REFERENCES ledger_source_rows(id) ON DELETE CASCADE,
    import_id     TEXT    NOT NULL REFERENCES ledger_imports(id) ON DELETE CASCADE,
    observed_at   TEXT    NOT NULL,
    status_observed TEXT  NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL,
    UNIQUE(transaction_id, source_row_id)
);
CREATE INDEX IF NOT EXISTS idx_tx_sources_tx ON ledger_transaction_sources(transaction_id);
CREATE INDEX IF NOT EXISTS idx_tx_sources_import ON ledger_transaction_sources(import_id);

CREATE TABLE IF NOT EXISTS ledger_refund_links (
    id                      TEXT    PRIMARY KEY,
    owner_id                INTEGER NOT NULL REFERENCES users(id),
    refund_transaction_id   TEXT    NOT NULL REFERENCES ledger_transactions(id) ON DELETE CASCADE,
    original_transaction_id TEXT    NOT NULL REFERENCES ledger_transactions(id) ON DELETE CASCADE,
    amount_minor            INTEGER NOT NULL,
    match_method            TEXT    NOT NULL DEFAULT 'manual',
    confirmation            TEXT    NOT NULL DEFAULT 'suggested',
    revision                INTEGER NOT NULL DEFAULT 1,
    created_at              TEXT    NOT NULL,
    updated_at              TEXT    NOT NULL,
    UNIQUE(refund_transaction_id, original_transaction_id)
);
CREATE INDEX IF NOT EXISTS idx_refund_original ON ledger_refund_links(original_transaction_id);
CREATE INDEX IF NOT EXISTS idx_refund_owner ON ledger_refund_links(owner_id, confirmation);

CREATE TABLE IF NOT EXISTS ledger_category_rules (
    id          TEXT    PRIMARY KEY,
    owner_id    INTEGER NOT NULL REFERENCES users(id),
    category_id TEXT    NOT NULL REFERENCES ledger_categories(id) ON DELETE CASCADE,
    match_field TEXT    NOT NULL DEFAULT 'merchant',
    match_op    TEXT    NOT NULL DEFAULT 'contains',
    match_value TEXT    NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 100,
    origin      TEXT    NOT NULL DEFAULT 'user',
    enabled     INTEGER NOT NULL DEFAULT 1,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rules_owner ON ledger_category_rules(owner_id, enabled, priority);

CREATE TABLE IF NOT EXISTS ledger_changes (
    id         TEXT    PRIMARY KEY,
    owner_id   INTEGER NOT NULL REFERENCES users(id),
    actor_id   INTEGER NOT NULL,
    run_id     TEXT    NOT NULL DEFAULT '',
    request_id TEXT    NOT NULL DEFAULT '',
    entity     TEXT    NOT NULL,
    entity_id  TEXT    NOT NULL,
    revision   INTEGER NOT NULL DEFAULT 1,
    change     TEXT    NOT NULL DEFAULT '{}',
    reason     TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_changes_entity ON ledger_changes(entity, entity_id, created_at);

CREATE TABLE IF NOT EXISTS ledger_analyses (
    id                 TEXT    PRIMARY KEY,
    owner_id           INTEGER NOT NULL REFERENCES users(id),
    import_ids         TEXT    NOT NULL DEFAULT '[]',
    query_plan         TEXT    NOT NULL,
    plan_version       INTEGER NOT NULL DEFAULT 1,
    snapshot_revision  INTEGER NOT NULL DEFAULT 0,
    data_cutoff        TEXT    NOT NULL,
    coverage           TEXT    NOT NULL DEFAULT '{}',
    result             TEXT    NOT NULL DEFAULT '{}',
    state              TEXT    NOT NULL DEFAULT 'succeeded',
    report_file_id     TEXT    REFERENCES stored_files(id),
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_owner ON ledger_analyses(owner_id, created_at DESC);
