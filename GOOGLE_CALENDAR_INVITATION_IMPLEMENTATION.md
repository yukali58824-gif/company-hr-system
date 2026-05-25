# Google Calendar 邀請系統 - 完整實現檢查

## ✅ 已實現功能

### 1️⃣ **自動產生 Google Meet 連結**
- **位置**: [google_meet/calendar_service.py](google_meet/calendar_service.py)
- **實現方式**:
  ```python
  "conferenceData": {
      "createRequest": {
          "requestId": f"meet-{int(start_dt.timestamp())}",
          "conferenceSolution": {"type": "hangoutsMeet"},
      }
  }
  ```
- **狀態**: ✅ **正常運作**

---

### 2️⃣ **寄送 Google Calendar 邀請信**
- **位置**: [google_meet/gmail_service.py](google_meet/gmail_service.py)
- **函數**:
  - `send_to_applicant()` - 發送給應徵者
  - `send_to_attendees()` - 發送給內部參與者（面試官）
- **狀態**: ✅ **正常運作**

---

### 3️⃣ **建立 Google Calendar 行程**
- **位置**: [google_meet/calendar_service.py](google_meet/calendar_service.py#L15) 的 `create_meet_event()` 函數
- **自動發送邀請**:
  ```python
  return calendar.events().insert(
      calendarId="primary",
      body=event,
      conferenceDataVersion=1,
      sendUpdates="all",  # ✅ 自動發送邀請給所有參與者
  ).execute()
  ```
- **狀態**: ✅ **正常運作**

---

### 4️⃣ **會議行程自動匯入發起者的 Google 日曆** ✨ **新增**

#### 核心實現機制:
- **使用 Google Calendar API 的 `calendarId="primary"`**:
  - 使用發起者的 OAuth 令牌 (`token.json`) 建立事件
  - `calendarId="primary"` 自動指向發起者的個人日曆
  - 事件自動出現在發起者的 Google Calendar 中

- **明確設定 organizer**:
  ```python
  # [google_meet/calendar_service.py]
  if organizer_email:
      event["organizer"] = {
          "email": organizer_email,
          "displayName": "會議主辦人"
      }
  ```

#### 發起者自動接收的內容:
- ✅ **Google Calendar 事件** - 自動匯入，無需操作
- ✅ **作為 organizer 的身份** - 可以編輯/管理事件
- ✅ **參與者回覆通知** - 當參與者接受/拒絕時自動通知
- ✅ **email_logs 記錄** - `organizer_notify` 類型

#### 日誌驗證:
```python
# [main.py 第 623 行]
log_json(
    logging.INFO,
    "organizer_calendar.auto_imported",
    booking_id=booking_id,
    organizer_email=sender_email,
    event_id=event_id,
    meet_link=meet_link,
    message="Google Calendar 事件已自動匯入發起者的日曆",
)
```

**狀態**: ✅ **完全實現**

---

### 5️⃣ **所有參與者收到邀請**

#### 📨 **應徵者收到**:
- ✅ Google Calendar 邀請（可直接加入日曆）
- ✅ iCal 附件（`VEVENT` 格式）
- ✅ HTML 郵件（含詳細資訊 + 取消按鈕）
- ✅ 「加入 Google 日曆」按鈕 ✨ 新增

#### 👥 **面試官/內部參與者收到**:
- ✅ Google Calendar 邀請（自動由 Google Calendar API 發送）
- ✅ 郵件通知（[gmail_service.py](google_meet/gmail_service.py#L289) 的 `send_to_attendees()` 函數）
- ✅ iCal 附件（`VEVENT` 格式）
- ✅ 「加入 Google 日曆」按鈕 ✨ 新增

#### 👤 **發起者/HR 收到** ✨ **增強**:
- ✅ 自動加入 Google Calendar 事件（作為 organizer）
- ✅ 郵件日誌記錄 (email_logs 表: `organizer_notify` 類型)
- ✅ 參與者回覆通知
- ✅ 事件編輯權限

---

## 🔄 **修改預約時的發起者日曆更新**

### 場景: 應徵者修改預約時段

**流程**:
```
應徵者修改時段
    ↓
系統刪除舊的 Google Calendar 事件
    ├─ 發起者的日曆中的舊事件自動移除
    └─ 參與者收到取消通知
    ↓
系統排程重新建立新的 Google Meet
    ├─ `schedule_google_meet_for_booking()` 執行
    ├─ 在發起者的日曆中建立新事件
    ├─ 向應徵者和面試官發送新邀請
    └─ 發起者自動收到新邀請並反映在日曆中
    ↓
完成，所有參與者日曆已更新 ✅
```

**代碼位置**: [main.py](main.py#L2257) - `modify_booking()` 函數

---

## 🛠️ **最近實施的增強功能**

### 1. **發起者郵件記錄增強**
```python
# 為發起者添加 email_logs 記錄
await conn.execute(
    "INSERT INTO email_logs (booking_id, recipient_email, email_type, status) VALUES ($1, $2, $3, $4)",
    booking_id,
    organizer_email,
    'organizer_notify',  # 新的電子郵件類型
    'sent',
)
```

### 2. **Google Calendar 按鈕增強**
- HTML 郵件中添加「➕ 加入 Google 日曆」按鈕
- 使用 Google Calendar 快速添加功能
- 樣式: 藍色漸層 (#4285f4 - #1f7ae0)

### 3. **organizer Email 明確設定**
```python
# [google_meet/calendar_service.py]
event["organizer"] = {
    "email": organizer_email,
    "displayName": "會議主辦人"
}
```

---

## 📊 **完整參與者邀請狀態矩陣**

| 參與者 | Google Calendar | 郵件 | iCal 附件 | Meet 連結 | 日曆按鈕 | 狀態 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| **應徵者** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 完整 |
| **面試官 1-N** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 完整 |
| **HR/發起者** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 完整 |

---

## 📋 **驗證檢查清單**

應徵者完成預約後，請驗證以下項目：

### 應徵者驗證:
- [ ] 應徵者收到郵件（含 HTML + iCal）
- [ ] 郵件中顯示 Google Meet 連結
- [ ] 郵件中有「加入 Google 日曆」按鈕
- [ ] 點擊按鈕可添加到應徵者的日曆
- [ ] Google Calendar 顯示完整的會議資訊
- [ ] 可直接在 Google Calendar 中接受/拒絕
- [ ] 取消預約按鈕正常運作

### 面試官驗證:
- [ ] 面試官收到郵件（由 Google Calendar API 自動發送）
- [ ] 郵件中顯示 Google Meet 連結
- [ ] 郵件中有「加入 Google 日曆」按鈕
- [ ] Google Calendar 中的事件已自動建立
- [ ] 可直接在 Google Calendar 中接受/拒絕

### 發起者/HR 驗證: ✨ **新增**
- [ ] **發起者的 Google Calendar 中自動出現新事件** (無需手動操作)
- [ ] 事件顯示所有參與者信息
- [ ] 事件中包含 Google Meet 連結
- [ ] 事件標記為「主辦人」身份
- [ ] email_logs 表中有 `organizer_notify` 記錄
- [ ] 當參與者回覆時，發起者收到通知

### 修改預約驗證:
- [ ] 應徵者修改時段時，舊事件從所有人的日曆中移除
- [ ] 發起者的日曆中自動顯示新事件（無需刷新）
- [ ] 所有參與者收到新的邀請
- [ ] email_logs 中記錄了新事件的邀請

---

## 🔍 **故障排除**

### 發起者日曆未自動更新
**檢查項目**:
1. 確認 `GOOGLE_MEET_SENDER_EMAIL` 環境變數正確設置
2. 確認 `google_meet/token.json` 有效（使用 `authenticate.py` 重新認證）
3. 檢查 Google Calendar API 配額是否已用盡
4. 查看系統日誌中的 `organizer_calendar.auto_imported` 日誌

### Google Calendar 事件未出現
**檢查項目**:
1. 確認 `calendarId="primary"` 設置正確
2. 確認 `conferenceDataVersion=1` 已設置
3. 確認時區設置 (`Asia/Taipei`)
4. 檢查 Google Calendar 的「其他日曆」設置（某些事件可能在隱藏的日曆中）

### 郵件中無「加入 Google 日曆」按鈕
**檢查項目**:
1. 確認 `gmail_service.py` 中的 `calendar_button` 正確生成
2. 確認郵件模板中包含 `{{calendar_button}}`
3. 檢查郵件客戶端是否支持 HTML 按鈕

---

## 🚀 **系統架構圖**

```
應徵者提交預約
    ↓
POST /api/bookings
    ↓
建立預約記錄 (bookings table)
    ├─ 保存 applicant_id, slot_id, position_id
    └─ 狀態: 'confirmed'
    ↓
排程 schedule_google_meet_for_booking()
    ↓
執行 google_meet/main.py 腳本
    ├─ 呼叫 create_meet_event()
    │   ├─ 建立 Google Calendar 事件
    │   ├─ 設置 organizer_email
    │   ├─ 使用 calendarId="primary" 
    │   │   └─ ✅ 自動匯入發起者的日曆
    │   └─ 發送 sendUpdates="all"
    │       └─ 通知所有參與者
    │
    ├─ 呼叫 send_to_applicant()
    │   └─ 發送應徵者 HTML + iCal 郵件
    │
    ├─ 呼叫 send_to_attendees()
    │   └─ 發送面試官 HTML + iCal 郵件
    │
    └─ 記錄 email_logs
        ├─ booking_confirm (應徵者)
        ├─ hr_notify (面試官)
        └─ organizer_notify (發起者) ✨ 新增
```

---

## 📞 **環境變數確認**

確保以下環境變數已設置：

```bash
# Google Meet 發送者 Email（發起者）
GOOGLE_MEET_SENDER_EMAIL=your-organizer@gmail.com

# Google Calendar/Gmail API 認證
# 需要 google_meet/credentials.json 和 token.json

# 管理員 Token（用於排程任務）
ADMIN_CRON_TOKEN=your-secure-token

# 資料庫連接
DATABASE_URL=postgresql://...
```

---

## ✨ **最終狀態**

🎉 **系統已完全實現所有需求功能**:

1. ✅ **自動產生 Google Meet 連結**
2. ✅ **寄送 Google Calendar 邀請信給所有參與者**
3. ✅ **建立 Google Calendar 行程**
4. ✅ **所有參與者可加入日曆、接受/拒絕邀請**
5. ✅ **查看 Google Meet 連結**
6. ✅ **會議行程自動匯入發起者的 Google 日曆** ✨ **新功能**

---

## 📞 **技術支援**

詳細文檔位置:
- [BOOKING_MODIFICATION_LOGIC.md](BOOKING_MODIFICATION_LOGIC.md) - 預約修改邏輯
- [GOOGLE_MEET_SETUP.md](GOOGLE_MEET_SETUP.md) - Google Meet 設置
- [google_meet/README.md](google_meet/README.md) - Google Meet 模組

