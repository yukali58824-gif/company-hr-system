# 預約修改邏輯 - 完整說明

## 📋 概述

系統根據修改預約時變動的內容類型，自動判斷是否需要重建 Google Meet 連結和通知其他參與者。

## 🎯 兩種修改場景

### 場景 1：修改面試時間（時段變動）

**觸發條件：**
- 修改 `slot_id`（選擇不同的面試時段）

**自動處理流程：**

```
應徵者提交修改時段
    ↓
系統驗證新時段是否存在
    ↓
刪除舊的 Google Calendar 事件
    ↓
發送「面試時間異動確認」信給應徵者
    ├─ 郵件主旨：「面試時間異動確認」
    ├─ 包含新的面試時間
    └─ 包含取消連結
    ↓
後台排程建立新的 Google Meet
    ├─ 獲取該職位的面試官列表
    ├─ 建立 Google Calendar 事件
    ├─ 添加應徵者、面試官、發起者為與會者
    └─ Google Calendar API 自動發送邀請給所有參與者 ✅
    ↓
完成，所有參與者收到新邀請
```

**通知對象：**
- ✅ 應徵者：確認信 + 新的 Google Calendar 邀請
- ✅ 面試官：新的 Google Calendar 邀請
- ✅ 發起者（HR）：自動加入新的 Google Calendar 事件

### 場景 2：修改其他資訊（時段不變）

**觸發條件：**
- 修改應徵者名字、電話、郵箱
- 修改職位（position_id）
- 修改預約狀態
- 但**不修改** `slot_id`

**自動處理流程：**

```
應徵者提交修改資訊
    ↓
系統更新資訊
    ├─ applicants 表：名字、電話、郵箱
    └─ bookings 表：職位、狀態等
    ↓
發送「預約資料更新確認」信給應徵者（只有應徵者）
    ├─ 郵件主旨：「預約資料更新確認」
    ├─ 包含更新後的應徵者資訊
    └─ 時間不變
    ↓
完成，不通知其他參與者 ✅
```

**通知對象：**
- ✅ 應徵者：確認信
- ❌ 面試官：不通知
- ❌ 發起者（HR）：不通知
- ✅ Google Meet 連結：保持不變（無需重建）

## 🔧 實現細節

### 時段驗證邏輯

```python
# 檢查時段是否變動
slot_changed = booking["slot_id"] != slot_uuid

# 如果時段沒有變動，時段可以是任何狀態；
# 如果時段變動，則新時段必須是 'open' 狀態
if slot_changed and slot["status"] != "open":
    raise HTTPException(status_code=400, detail="所選時段不可預約")
```

### 郵件發送邏輯

```python
if slot_changed:
    # 時段變動：發送「面試時間異動確認」
    subject_prefix = "面試時間異動確認"
    # 排程重建 Google Meet（會通知所有參與者）
    background_tasks.add_task(schedule_google_meet_for_booking, ...)
else:
    # 時段未變動：發送「預約資料更新確認」
    subject_prefix = "預約資料更新確認"
    # 不排程 Google Meet（無需通知其他參與者）
```

## 📊 修改流程對比

| 修改項目 | 面試時間 | 名字/電話/郵箱 | 職位 |
|---------|--------|--------------|------|
| 驗證新時段 | ✓ | - | - |
| 刪除舊 Google Meet | ✓ | - | - |
| 發送給應徵者 | ✓ | ✓ | ✓ |
| 發送給面試官 | ✓ | ✗ | ✗ |
| 發送給發起者 | ✓ | ✗ | ✗ |
| 重建 Google Meet | ✓ | ✗ | ✗ |
| 郵件主旨 | 面試時間異動確認 | 預約資料更新確認 | 預約資料更新確認 |

## 📝 API 端點

### 修改預約（應徵者前台）

```
POST /api/bookings/modify
Content-Type: application/json

{
  "booking_id": "uuid",
  "slot_id": "新的時段ID（可選，若提供則視為時段變動）",
  "position_id": "職位ID",
  "name": "新名字",
  "email": "新郵箱",
  "phone": "新電話"
}
```

**回應：**
```json
{
  "ok": true
}
```

### 編輯預約（HR 後台）

```
PATCH /api/bookings/{booking_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "applicant_name": "新名字（可選）",
  "applicant_email": "新郵箱（可選）",
  "phone": "新電話（可選）",
  "slot_date": "新日期（可選，格式：YYYY-MM-DD）",
  "start_time": "新開始時間（可選，格式：HH:MM）",
  "end_time": "新結束時間（可選，格式：HH:MM）",
  "position_id": "新職位ID（可選）",
  "status": "新狀態（可選：confirmed, cancelled, no_show, auto_completed）",
  "google_meet_link": "手動設定 Google Meet 連結（可選）"
}
```

**邏輯：**
- 若 `slot_date` 或 `start_time` 或 `end_time` 被提供，視為時段變動 → 重建 Google Meet
- 否則視為其他資訊變動 → 只發給應徵者

## 🔍 日誌追蹤

系統會記錄修改的類型，便於故障排除：

```
booking.time_modified          - 時段變動，將重新建立 Google Meet
booking.info_modified          - 應徵者資訊變動，無需通知其他參與者
booking.modified_no_google_meet_needed - 無需重新建立 Google Meet
schedule_google_meet.triggered_on_modify - 面試時間異動，重新建立 Google Meet
```

## 💡 使用場景

### 場景 1：應徵者延期面試

應徵者因故無法參加原定時間的面試，申請改期到下週。

系統自動：
1. ✅ 刪除舊的 Google Meet 連結
2. ✅ 發送「面試時間異動確認」給應徵者
3. ✅ 通知所有參與者新的面試時間和 Google Meet 連結

### 場景 2：應徵者更正聯絡方式

應徵者預約後發現留下的電話號碼有誤，申請修正。

系統自動：
1. ✅ 更新應徵者的電話號碼
2. ✅ 發送「預約資料更新確認」給應徵者
3. ✓ 保持現有的 Google Meet 連結不變
4. ✗ 不通知面試官和發起者（因為面試時間未變）

### 場景 3：HR 調整職位

HR 在後台編輯預約，發現應徵者應聘的職位錯誤，進行修正。

系統自動：
1. ✅ 更新預約的職位
2. ✅ 發送「預約資料更新確認」給應徵者
3. ✓ 保持現有的 Google Meet 連結不變
4. ✗ 不通知面試官和發起者

### 場景 4：HR 改期面試

HR 在後台編輯預約，將面試時間從下午改到上午。

系統自動：
1. ✅ 刪除舊的 Google Meet 連結
2. ✅ 發送「面試時間異動確認」給應徵者
3. ✅ 通知面試官新的面試時間
4. ✅ Google Calendar 自動更新發起者的日曆

## ⚙️ 配置參數

```python
# main.py 中的相關配置
schedule_google_meet_for_booking(booking_id, delay_seconds=10)
```

- `delay_seconds=10`：延遲 10 秒後才開始建立 Google Meet，避免與郵件發送產生競爭

## 🚀 後續改進建議

1. **實時通知**
   - 使用 WebSocket 向應徵者實時通知修改結果
   - 面試官可即時看到時間變動

2. **修改歷史**
   - 記錄每次修改的內容和時間
   - 應徵者可查看完整的修改歷史

3. **智能通知**
   - 根據修改內容的重要性自動調整通知策略
   - 例如：時間提前 2 小時以上才發 SMS 通知

4. **修改限制**
   - 限制應徵者在距面試時間 24 小時內的修改次數
   - 防止頻繁修改影響準備

## 📖 相關文檔

- [Google Meet 邀請系統完整指南](GOOGLE_CALENDAR_INVITATION_SYSTEM.md)
- [快速開始指南](QUICK_START_GUIDE.md)
- [系統實裝清單](IMPLEMENTATION_CHECKLIST.md)
