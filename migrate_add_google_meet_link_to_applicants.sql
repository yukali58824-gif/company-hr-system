-- 遷移腳本：為 applicants 表添加 google_meet_link 和 updated_at 字段
-- 執行方式：psql -U postgres -d hr_system -f migrate_add_google_meet_link_to_applicants.sql

ALTER TABLE applicants
ADD COLUMN IF NOT EXISTS google_meet_link VARCHAR(500),
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- 創建索引以加快查詢
CREATE INDEX IF NOT EXISTS idx_applicants_meet_link ON applicants (google_meet_link) WHERE google_meet_link IS NOT NULL;

-- 確認遷移成功
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'applicants' 
  AND column_name IN ('google_meet_link', 'updated_at');
