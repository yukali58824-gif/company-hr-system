# HR 系統 Google Meet 整合 - 部署清單

## 📋 部署前準備

- [ ] 備份現有數據庫
- [ ] 確保 `google_meet/credentials.json` 和 `google_meet/token.json` 存在且有效
- [ ] 確保 Google Calendar API 已啟用

## 🔧 部署步驟

### 步驟 1：執行數據庫遷移
```bash
cd c:\Users\PC02\Downloads\hr_system
psql -U postgres -d hr_system -f migrate_add_google_fields.sql
```

**預期輸出：**
```
ALTER TABLE
CREATE INDEX
 column_name      | data_type
------------------+-----------
 google_meet_link | character varying
 google_event_id  | character varying
```

### 步驟 2：驗證遷移成功
```bash
psql -U postgres -d hr_system -c "
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'bookings' 
ORDER BY ordinal_position;
"
```

確保 `google_meet_link` 和 `google_event_id` 列已存在。

### 步驟 3：停止現有應用程式
```
Ctrl+C (在 uvicorn 終端)
```

### 步驟 4：重新啟動應用程式
```bash
python.exe -m uvicorn main:app --port 8006
```

### 步驟 5：驗證功能

#### 5a. 測試建立預約
1. 訪問 http://127.0.0.1:8006
2. 選擇職位和時段建立預約
3. 檢查 uvicorn 日誌確認 Google Meet 創建成功
4. 查看預約郵件，確認包含 Google Meet 連結

#### 5b. 測試取消預約
1. 訪問 http://127.0.0.1:8006/hr/bookings
2. 選擇一個預約並刪除
3. 檢查 uvicorn 日誌確認日曆事件刪除
4. 驗證 Google Calendar 中的事件已被移除

## 📊 驗證新功能

### 檢查 bookings 表中的新欄位
```bash
psql -U postgres -d hr_system -c "
SELECT id, applicant_id, status, google_meet_link, google_event_id 
FROM bookings 
LIMIT 5;
"
```

應該看到 `google_meet_link` 和 `google_event_id` 欄位已填充。

### 檢查 API 響應
```bash
curl -X GET http://127.0.0.1:8006/api/bookings \
  -H "Cookie: token=<your_token>"
```

應該看到返回的 JSON 包含 `google_meet_link` 字段。

## 🐛 常見問題排查

### Q: Google Meet 連結沒有被填入
**A:** 檢查 uvicorn 日誌中是否有錯誤：
```
ERROR: Failed to update booking with meet link
```

可能的原因：
- Google Calendar API 認證失敗
- 網絡連接問題
- 數據庫遷移未完成

### Q: 刪除預約時日曆事件未被刪除
**A:** 確認：
1. `google_event_id` 已正確保存 - 查看日誌輸出
2. `google_meet/token.json` 仍然有效
3. 預約狀態確實改為 `cancelled` 或 `no_show`

### Q: 運行遷移時出現權限錯誤
**A:** 使用 PostgreSQL 超級用戶執行：
```bash
psql -U postgres -d hr_system -f migrate_add_google_fields.sql
```

## 📝 文件變更總結

### 新增
- `migrate_add_google_fields.sql` - 數據庫遷移
- `google_meet/delete_event.py` - 刪除事件腳本
- `MIGRATION_UPDATE.md` - 功能說明
- `DEPLOYMENT_CHECKLIST.md` - 本清單

### 修改
- `init_db.sql` - bookings 表添加新欄位
- `main.py` - 大量 API 更新
- `google_meet/calendar_service.py` - 添加 delete_meet_event()
- `google_meet/main.py` - 輸出 event ID

## 🔍 監控建議

### 在 Production 環境中監控

添加以下日誌監控：
```
# 監控 Google Meet 創建
"Google Meet scheduler stdout:"

# 監控 Google Meet 刪除
"Google Meet event delete"

# 監控失敗
"Failed to update booking with meet link"
"Failed to delete event"
```

## ✅ 部署完成檢查

- [ ] 數據庫遷移成功
- [ ] 應用程式重新啟動無誤
- [ ] 新預約自動填入 google_meet_link
- [ ] 取消預約自動刪除日曆事件
- [ ] 郵件通知正常工作
- [ ] 無在日誌中的關鍵錯誤

---

**預期效果：**
✨ 所有預約會自動關聯 Google Meet 連結
✨ 取消或標記為 no_show 的預約會自動刪除日曆事件
✨ HR 人員無需手動管理 Google Calendar
