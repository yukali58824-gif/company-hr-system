-- 測試數據庫連接和查詢
-- 執行方式：psql -U postgres -d hr_system -f test_query.sql

-- 檢查 bookings 表結構
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'bookings'
ORDER BY ordinal_position;

-- 檢查 interview_slots 表結構
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'interview_slots'
ORDER BY ordinal_position;

-- 測試查詢（如果表中有數據）
SELECT COUNT(*) as booking_count FROM bookings WHERE deleted_at IS NULL;
SELECT COUNT(*) as slot_count FROM interview_slots;
