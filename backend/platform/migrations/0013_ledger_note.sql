-- 0013：交易备注（纠正/对账说明）；迁移只追加，不改已发布的 0012。
ALTER TABLE ledger_transactions ADD COLUMN note TEXT NOT NULL DEFAULT '';
