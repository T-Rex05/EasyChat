-- 0024_superagent_auto_fix: 有限自动修复（执行指令 P7，方案 §5 D3）。
--
-- 开关默认关闭（能力开关默认关闭）；轮数预算按任务记录，
-- 预算耗尽或人工暂停时不再自动入队（CAS 状态前置保证）。
-- 时间文本统一 UTC ISO-8601（继承既有约束，本迁移不含时间列语义变化）。
ALTER TABLE superagent_settings ADD COLUMN auto_fix_enabled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE superagent_settings ADD COLUMN auto_fix_max_rounds INTEGER NOT NULL DEFAULT 1;
ALTER TABLE superagent_tasks ADD COLUMN auto_fix_rounds INTEGER NOT NULL DEFAULT 0;
