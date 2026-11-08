-- 0022_superagent_webhooks: GitHub 回流事件存储（T7，方案 §9）。
--
-- 事件先落库再快速应答；按 X-GitHub-Delivery 去重；处理经持久 jobs
-- （kind=superagent.webhook.process）异步执行，重复投递不触发重复工作。

CREATE TABLE IF NOT EXISTS superagent_webhook_events (
    id              TEXT    PRIMARY KEY,
    delivery_id     TEXT    NOT NULL,
    event_type      TEXT    NOT NULL DEFAULT '',
    action          TEXT    NOT NULL DEFAULT '',
    repo_full_name  TEXT    NOT NULL DEFAULT '',
    pr_number       INTEGER,
    head_sha        TEXT    NOT NULL DEFAULT '',
    sender_login    TEXT    NOT NULL DEFAULT '',
    sender_is_bot   INTEGER NOT NULL DEFAULT 0,
    payload         TEXT    NOT NULL DEFAULT '{}',
    processed_at    TEXT,
    process_error   TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_superagent_webhook_delivery
    ON superagent_webhook_events(delivery_id);
CREATE INDEX IF NOT EXISTS idx_superagent_webhook_repo_pr
    ON superagent_webhook_events(repo_full_name, pr_number, created_at DESC);
