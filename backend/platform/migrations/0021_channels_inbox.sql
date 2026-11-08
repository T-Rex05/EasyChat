-- 0021_channels_inbox: 微信入站事件的持久可重放 envelope（T5，方案 §5）。
--
-- 目标：消灭“内部失败 → delete_event → listener 批末推进游标 → 消息丢失”路径。
-- 事件受理时同事务保存完整 envelope（全文、媒体引用、来源标识），处理失败改为
-- 标记 processing_state=failed + retry_at 退避，由本地 replay 重试；毒消息在
-- attempts 耗尽后进入 dead（可见失败状态），不再依赖上游重投。
-- 兼容：全部为追加列；历史行 processing_state='' 视为已终结，不参与 replay。

ALTER TABLE channel_events ADD COLUMN envelope_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE channel_events ADD COLUMN envelope_json TEXT NOT NULL DEFAULT '';
ALTER TABLE channel_events ADD COLUMN processing_state TEXT NOT NULL DEFAULT '';
ALTER TABLE channel_events ADD COLUMN retry_at REAL;
ALTER TABLE channel_events ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE channel_events ADD COLUMN last_error TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_channel_events_replay
    ON channel_events(processing_state, retry_at);
