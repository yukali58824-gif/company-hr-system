# 面試系統更新說明

## 功能更新

### 1. 自動填入應徵者的面試連結
所有預約紀錄現在會自動填入應徵者的 Google Meet 面試連結。系統會在建立預約時自動記錄 `google_meet_link` 和 `google_event_id`。

### 2. 自動取消日曆行程
當應徵者的預約狀態改為 **cancelled** 或 **no_show** 時，系統會自動取消對應的 Google Calendar 事件和 Google Meet 會議。

## 實施步驟

### 第一步：執行數據庫遷移

```bash
psql -U postgres -d hr_system -f migrate_add_google_fields.sql
```

此命令將在 `bookings` 表中添加以下欄位：
- `google_meet_link`: 存儲 Google Meet 會議連結
- `google_event_id`: 存儲 Google Calendar 事件 ID

### 第二步：重新啟動應用程式

```bash
python.exe -m uvicorn main:app --port 8006
```

## 工作流程

### 建立預約
1. 應徵者預約面試時段
2. 系統在背景執行 `google_meet/main.py` 建立 Google Meet 會議
3. 會議 ID 和連結會自動保存到 `bookings` 表
4. 應徵者會收到包含 Google Meet 連結的確認郵件

### 取消預約
1. HR 人員或應徵者取消預約
2. 預約狀態改為 `cancelled` 或 `no_show`
3. 系統自動調用 `google_meet/delete_event.py` 刪除 Google Calendar 事件
4. Google Meet 會議連結失效

## API 變更

### GET /api/bookings
現在返回的預約記錄包含以下新字段：
```json
{
  "id": "...",
  "applicant_name": "...",
  "applicant_email": "...",
  "google_meet_link": "https://meet.google.com/...",
  "status": "confirmed",
  ...
}
```

### PATCH /api/bookings/{booking_id}
當狀態改為 `cancelled` 或 `no_show` 時，會自動觸發日曆事件刪除

### DELETE /api/bookings/{booking_id}
刪除預約時，會自動觸發日曆事件刪除

## 文件清單

新增文件：
- `migrate_add_google_fields.sql` - 數據庫遷移腳本
- `google_meet/delete_event.py` - Google Calendar 事件刪除腳本

修改文件：
- `init_db.sql` - 更新 bookings 表結構
- `main.py` - 添加預約取消、日曆事件刪除等邏輯
- `google_meet/calendar_service.py` - 添加 `delete_meet_event()` 函數
- `google_meet/main.py` - 輸出 event ID

## 環境要求

- Python 3.12+
- PostgreSQL
- Google Calendar API 認證 (credentials.json)

## 故障排除

### Google Calendar 事件無法刪除
檢查 `google_meet/token.json` 是否有效，可能需要重新授權

### 預約未保存 google_meet_link
查看 uvicorn 日誌中的錯誤信息：
```
logger.error(f"Failed to update booking with meet link: {str(e)}")
```

### 遷移腳本失敗
確保：
1. 已連接到正確的數據庫
2. 擁有執行 ALTER TABLE 的權限
3. PostgreSQL 版本 >= 10.0
