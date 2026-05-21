-- 遷移腳本：為 email_logs 表添加 updated_at 欄位
-- 執行方式：psql -U postgres -d hr_system -f migrate_add_email_logs_updated_at.sql

ALTER TABLE email_logs
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

-- 確認遷移成功
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'email_logs'
  AND column_name IN ('updated_at');
