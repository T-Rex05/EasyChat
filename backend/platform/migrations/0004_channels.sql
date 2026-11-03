-- 0004_channels: 渠道账号生命周期、长轮询游标与事件处理结果。
-- 0001 已建 channel_accounts/channel_bindings/channel_events；
-- 本迁移只追加列，已提交的 0001-0003 不可修改（checksum 固定）。

-- 账号：真实可观测的监听状态（last_poll_at/last_error 由 listener 写入，
-- 不是内存里的假 running 标志）、机器人自身标识与 getupdates 游标。
ALTER TABLE channel_accounts ADD COLUMN bot_user_id TEXT NOT NULL DEFAULT '';
ALTER TABLE channel_accounts ADD COLUMN sync_cursor TEXT NOT NULL DEFAULT '';
ALTER TABLE channel_accounts ADD COLUMN last_poll_at TEXT;
ALTER TABLE channel_accounts ADD COLUMN last_error TEXT NOT NULL DEFAULT '';

-- 事件：记录该条入站消息被拒绝/已提交到哪个 run，重启后仍可对账。
-- 稳定 message_id 用 msg:<id>；无稳定 ID 时用 fp:<fingerprint>:<窗口桶>，
-- 窗口桶保证相同文本只在一个短窗口内去重，不会被永久吞掉。
ALTER TABLE channel_events ADD COLUMN session_id TEXT NOT NULL DEFAULT '';
ALTER TABLE channel_events ADD COLUMN run_id TEXT NOT NULL DEFAULT '';
ALTER TABLE channel_events ADD COLUMN state TEXT NOT NULL DEFAULT 'received';
ALTER TABLE channel_events ADD COLUMN error TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_channel_events_account_time
    ON channel_events(platform, account_id, received_at DESC);

-- 每个微信聊天当前指向的 Assistant 会话（/new、/N 切换后持久化）。
-- 只保存会话引用；会话本身仍归 assistant 模块所有。
CREATE TABLE IF NOT EXISTS channel_session_cursors (
    platform          TEXT NOT NULL,
    account_id        TEXT NOT NULL,
    external_user_id  TEXT NOT NULL,
    external_chat_id  TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    PRIMARY KEY(platform, account_id, external_user_id, external_chat_id)
);
