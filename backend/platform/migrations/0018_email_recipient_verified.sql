-- 0018_email_recipient_verified：收件人所有权验证（审计 #4）。
-- 注册不再等于可信：新登记/重登记的地址 verified=0，确认后方可投递；
-- 存量行保持 verified=0（fail-closed），需重新完成确认。
-- confirm_token 用于一次性确认链接，24 小时过期。

ALTER TABLE email_recipients ADD COLUMN verified INTEGER NOT NULL DEFAULT 0;
ALTER TABLE email_recipients ADD COLUMN confirm_token TEXT NOT NULL DEFAULT '';
ALTER TABLE email_recipients ADD COLUMN token_expires_at TEXT NOT NULL DEFAULT '';
