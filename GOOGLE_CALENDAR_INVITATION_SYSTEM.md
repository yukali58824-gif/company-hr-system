# Google Meet 邀請系統 - 完整實裝指南

## 系統概述

本系統確保應徵者完成預約後，所有參與者（應徵者、面試官、發起者）都能收到完整的 Google Calendar 邀請，並支持：
- ✅ 加入 Google 日曆
- ✅ 接受/拒絕邀請  
- ✅ 查看 Google Meet 連結
- ✅ 查看完整的會議詳情

## 架構改進

### 1. 數據庫改進
新增三個相關表格：

#### `interviewers` 表
存儲面試官信息，不再依賴硬編碼。

```sql
CREATE TABLE interviewers (
    id UUID PRIMARY KEY,
    hr_user_id UUID NOT NULL REFERENCES hr_users(id),
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    role VARCHAR(50) DEFAULT '面試官',
    is_active BOOLEAN DEFAULT TRUE
);
```

#### `position_interviewers` 表
建立職位與面試官的多對多關係。

```sql
CREATE TABLE position_interviewers (
    id UUID PRIMARY KEY,
    position_id UUID NOT NULL REFERENCES job_positions(id),
    interviewer_id UUID NOT NULL REFERENCES interviewers(id),
    UNIQUE(position_id, interviewer_id)
);
```

#### `email_logs` 表擴展
新增欄位以追蹤所有參與者的邀請：
- `attendee_emails`: 所有參與者的 email 列表
- `attendee_names`: 所有參與者的名字列表

### 2. 代碼改進

#### Google Calendar API 配置
改變 `sendUpdates` 設置以自動發送邀請：

```python
# 之前：sendUpdates='none'（不發送邀請）
# 現在：sendUpdates='all'（自動發送邀請）

calendar.events().insert(
    calendarId="primary",
    body=event,
    conferenceDataVersion=1,
    sendUpdates="all"  # 確保所有參與者都收到邀請
).execute()
```

#### 面試官管理系統
新增函數以從數據庫動態讀取面試官：

```python
async def get_interviewers_for_position(pool, position_id: str) -> list[dict]:
    """從數據庫取得該職位的面試官列表"""
    # 查詢 position_interviewers 表
    # 返回該職位的所有活躍面試官
```

#### 郵件通知改進
- 應徵者收到：確認信 + Google Calendar 邀請 + 取消按鈕
- 面試官收到：Google Calendar 邀請 + HTML 郵件說明
- 發起者（HR）收到：Google Calendar 邀請

### 3. API 端點新增

新增面試官管理 API：

#### 獲取所有面試官
```
GET /api/interviewers
```

#### 獲取職位的面試官
```
GET /api/positions/{position_id}/interviewers
```

#### 新增面試官到職位
```
POST /api/positions/{position_id}/interviewers/{interviewer_id}
```

#### 從職位移除面試官
```
DELETE /api/positions/{position_id}/interviewers/{interviewer_id}
```

## 部署步驟

### 步驟 1: 執行數據庫遷移

```bash
psql -U postgres -d hr_system -f migrate_add_interviewers_table.sql
```

檢查遷移是否成功：
```bash
psql -U postgres -d hr_system -c "SELECT * FROM interviewers;"
psql -U postgres -d hr_system -c "SELECT * FROM position_interviewers;"
```

### 步驟 2: 更新應用代碼

確保以下文件已更新：
- ✅ [main.py](main.py) - 添加了面試官管理 API 和改進的 Google Meet 排程
- ✅ [google_meet/main.py](google_meet/main.py) - 支持通過命令行參數傳遞面試官列表
- ✅ [google_meet/calendar_service.py](google_meet/calendar_service.py) - 改進的 Google Calendar 邀請配置

### 步驟 3: 設置面試官

在 Web 管理界面中：
1. 進入「職缺管理」
2. 選擇要配置的職缺
3. 點擊「面試官」按鈕
4. 新增該職缺對應的面試官

或使用 API：
```bash
# 新增面試官
curl -X POST http://localhost:8000/api/positions/{position_id}/interviewers/{interviewer_id} \
  -H "Cookie: access_token={your_token}"

# 移除面試官
curl -X DELETE http://localhost:8000/api/positions/{position_id}/interviewers/{interviewer_id} \
  -H "Cookie: access_token={your_token}"
```

### 步驟 4: 驗證設置

測試預約流程：

1. 應徵者通過前台預約
2. 檢查應徵者信箱：
   - 收到確認信（HTML 格式）
   - 收到 Google Calendar 邀請（.ics 格式）
3. 檢查面試官信箱：
   - 收到 Google Calendar 邀請
   - 可以接受/拒絕邀請
4. 查看 Google Calendar：
   - 所有參與者都應該能看到會議
   - 會議應該包含 Google Meet 連結

## 郵件流程圖

```
應徵者預約
    ↓
系統獲取職位的面試官列表
    ↓
調用 Google Meet 腳本
    ├─ 創建 Google Calendar 事件
    │  └─ Google Calendar API 自動發送邀請給所有參與者
    ├─ 發送郵件給應徵者（確認信 + iCal）
    └─ 發送郵件給面試官（iCal）
    ↓
記錄郵件日誌
    ├─ 應徵者確認信
    ├─ 面試官邀請
    └─ Google Calendar 事件 ID 和 Meet 連結
```

## 故障排除

### 面試官無法收到邀請

1. 檢查 `position_interviewers` 表中是否有該職位的面試官配置
   ```sql
   SELECT * FROM position_interviewers WHERE position_id = '{your_position_id}';
   ```

2. 檢查面試官是否標記為活躍
   ```sql
   SELECT * FROM interviewers WHERE email = 'interviewer@example.com';
   ```

3. 查看應用日誌，搜索 "schedule_google_meet.interviewers_fetched"

### Google Calendar 邀請未顯示 Google Meet 連結

1. 確保 `GOOGLE_MEET_SENDER_EMAIL` 環境變數已設置
2. 確認 Google API credentials 權限包括 Calendar API
3. 檢查 `create_meet_event` 函數的 `conferenceData` 配置

### 郵件中看不到日期/時間

1. 確認系統時區設置為 `Asia/Taipei`
2. 檢查 `build_confirmation_email` 和 `build_email_html` 函數中的日期格式

## 後續改進建議

1. **前端 UI 改進**
   - 在「職缺管理」頁面添加「面試官」選項卡
   - 顯示該職缺已配置的面試官列表
   - 支持拖放以管理面試官

2. **通知系統改進**
   - 在預約確認後實時通知 HR/面試官
   - 支持 Slack/Teams 整合通知

3. **面試官排程系統**
   - 支持為不同時段設置不同的面試官
   - 支持面試官的忙碌時段標記

4. **分析和報告**
   - 統計每位面試官的邀請接受率
   - 生成月度面試報告

## 相關文件

- [系統架構文檔](README.md)
- [Google Meet 設置指南](GOOGLE_MEET_SETUP.md)
- [數據庫遷移腳本](migrate_add_interviewers_table.sql)
- [主應用代碼](main.py)
- [Google Meet 集成代碼](google_meet/)
