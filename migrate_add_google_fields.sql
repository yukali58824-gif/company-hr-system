-- 遷移腳本：為 bookings 表添加 google_meet_link 和 google_event_id 字段
-- 執行方式：psql -U postgres -d hr_system -f migrate_add_google_fields.sql

ALTER TABLE bookings
ADD COLUMN IF NOT EXISTS google_meet_link VARCHAR(500),
ADD COLUMN IF NOT EXISTS google_event_id VARCHAR(255);

-- 創建索引以加快查詢
CREATE INDEX IF NOT EXISTS idx_bookings_event_id ON bookings (google_event_id) WHERE google_event_id IS NOT NULL;

-- 確認遷移成功
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'bookings' 
  AND column_name IN ('google_meet_link', 'google_event_id');
