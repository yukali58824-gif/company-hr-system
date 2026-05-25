# 快速開始指南 - Google Meet 邀請系統

## 🎯 系統功能概述

完成本次實裝後，系統將自動：

1. **應徵者預約時**
   - ✅ 自動產生 Google Meet 連結
   - ✅ 寄送 Google Calendar 邀請給應徵者
   - ✅ 寄送 Google Calendar 邀請給面試官
   - ✅ 建立 Google Calendar 行程

2. **所有參與者都能收到**
   - ✅ 加入 Google 日曆的選項
   - ✅ 接受/拒絕邀請的功能
   - ✅ 查看 Google Meet 連結

## 📌 快速部署（5 分鐘）

### 1. 執行數據庫遷移
```bash
cd c:\Users\PC02\Downloads\hr_system
psql -U postgres -d hr_system -f migrate_add_interviewers_table.sql
```

### 2. 重啟應用
```bash
# 按 Ctrl+C 停止當前的應用程序
# 然後重新啟動
python -m uvicorn main:app --reload --port 8000
```

### 3. 配置面試官（任選一種方式）

#### 方式 A：Web 界面（推薦用於小規模配置）
1. 登入 HR 系統
2. 進入職缺管理
3. 選擇職缺並點擊「面試官」
4. 新增相應的面試官

#### 方式 B：API（推薦用於批量配置）
```bash
# 新增 Alice 到「軟體工程師」職位
curl -X POST \
  "http://localhost:8000/api/positions/{position_id}/interviewers/{interviewer_id}" \
  -H "Cookie: access_token={your_token}"
```

#### 方式 C：SQL（DBA 使用）
```sql
-- 查詢職位 ID
SELECT id, title FROM job_positions WHERE title = '軟體工程師';

-- 查詢面試官 ID
SELECT id, name, email FROM interviewers WHERE is_active = TRUE;

-- 建立關聯
INSERT INTO position_interviewers (position_id, interviewer_id) 
VALUES ('{position_id}', '{interviewer_id}');
```

## 📨 郵件流程

### 應徵者收到的郵件

#### 1. 確認郵件（HTML 格式）
內容包括：
- 面試時間和職位
- Google Meet 連結
- 取消預約按鈕
- 企業聯絡方式

#### 2. Google Calendar 邀請
格式：
- .ics 附件
- 可直接加入 Google Calendar
- 支持接受/拒絕

### 面試官收到的郵件

#### 1. Google Calendar 邀請
內容包括：
- 會議時間
- Google Meet 連結
- 應徵者信息
- 所有參與者列表

#### 2. 功能
- 可在 Google Calendar 中查看
- 可接受/拒絕邀請
- 直接點擊進入 Google Meet

## 🔍 驗證系統

### 測試應徵者預約流程

1. **前台預約**
   - 訪問 http://localhost:8000
   - 選擇職缺、時段
   - 填寫個人信息並預約

2. **檢查應徵者郵件**
   - 應檢查郵箱（收件夾和垃圾郵件）
   - 應收到兩封郵件：確認信 + iCal 邀請

3. **檢查面試官郵件**
   - 登入面試官郵箱
   - 應收到 Google Calendar 邀請

4. **驗證 Google Calendar**
   - 應徵者 Google Calendar：應能看到「鼎霖視訊面試」事件
   - 面試官 Google Calendar：應能看到相同的事件
   - 事件詳情應包含 Google Meet 連結

### 檢查系統日誌

```bash
# 查看郵件發送日誌
psql -U postgres -d hr_system -c "
  SELECT recipient_email, email_type, status 
  FROM email_logs 
  WHERE booking_id = '{booking_id}' 
  ORDER BY created_at DESC;"

# 查看 Google Calendar 事件
psql -U postgres -d hr_system -c "
  SELECT google_event_id, google_meet_link 
  FROM bookings 
  WHERE id = '{booking_id}';"
```

## ⚙️ 常見操作

### 添加新的面試官

```bash
# 1. 先確認面試官是否已在系統中
psql -U postgres -d hr_system -c "
  SELECT id, name, email FROM interviewers 
  WHERE email = 'new_interviewer@example.com';"

# 2. 如果不存在，先添加面試官
psql -U postgres -d hr_system -c "
  INSERT INTO interviewers (hr_user_id, name, email, role, is_active) 
  VALUES ('{hr_user_id}', 'New Name', 'new_interviewer@example.com', '面試官', TRUE);"

# 3. 將面試官添加到職位
curl -X POST \
  "http://localhost:8000/api/positions/{position_id}/interviewers/{interviewer_id}" \
  -H "Cookie: access_token={your_token}"
```

### 移除職位的面試官

```bash
curl -X DELETE \
  "http://localhost:8000/api/positions/{position_id}/interviewers/{interviewer_id}" \
  -H "Cookie: access_token={your_token}"
```

### 查看職位的所有面試官

```bash
curl -X GET \
  "http://localhost:8000/api/positions/{position_id}/interviewers" \
  -H "Cookie: access_token={your_token}" \
  -H "Accept: application/json"
```

## 🐛 常見問題排查

### Q: 為什麼面試官收不到邀請？

**A:** 檢查以下幾項：

1. 確認面試官已被分配到職位
   ```bash
   psql -U postgres -d hr_system -c "
     SELECT COUNT(*) FROM position_interviewers 
     WHERE position_id = '{position_id}';"
   ```

2. 確認面試官的 is_active 為 TRUE
   ```bash
   psql -U postgres -d hr_system -c "
     SELECT is_active FROM interviewers 
     WHERE email = 'interviewer@example.com';"
   ```

3. 查看應用日誌中的錯誤信息
   ```bash
   tail -f {application_log} | grep -i "interviewer\|google_meet"
   ```

### Q: Google Meet 連結為什麼沒有出現在郵件中？

**A:** 可能的原因：

1. Google API 認證失敗
   - 確認 `token.json` 存在
   - 重新執行 `python google_meet/authenticate.py`

2. 面試官郵箱配置錯誤
   - 確認 `GOOGLE_MEET_SENDER_EMAIL` 環境變數正確

3. Google Calendar API 權限不足
   - 檢查 Google Cloud 控制台的權限設置

### Q: 應徵者收到的郵件時間不正確？

**A:** 檢查系統時區設置：

```python
# 確認 main.py 中的時區設置
tz = timezone(timedelta(hours=8))  # Asia/Taipei

# 或檢查 google_meet/main.py
tz = timezone(timedelta(hours=8))
```

## 📊 監控系統健康

定期檢查以下指標：

```bash
# 1. 未發送的郵件數量（應該為 0）
psql -U postgres -d hr_system -c "
  SELECT COUNT(*) as pending_emails 
  FROM email_logs WHERE status = 'pending';"

# 2. 今天的郵件成功率
psql -U postgres -d hr_system -c "
  SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) as sent,
    ROUND(100.0 * SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
  FROM email_logs 
  WHERE DATE(created_at) = CURRENT_DATE;"

# 3. 未配置面試官的職位（應該都已配置）
psql -U postgres -d hr_system -c "
  SELECT p.title 
  FROM job_positions p 
  WHERE p.is_active = TRUE 
  AND NOT EXISTS (
    SELECT 1 FROM position_interviewers 
    WHERE position_id = p.id
  );"
```

## 📚 參考文件

| 文件名 | 用途 |
|------|------|
| [GOOGLE_CALENDAR_INVITATION_SYSTEM.md](GOOGLE_CALENDAR_INVITATION_SYSTEM.md) | 完整系統文檔 |
| [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) | 部署清單和驗證步驟 |
| [GOOGLE_MEET_SETUP.md](GOOGLE_MEET_SETUP.md) | Google Meet 初始設置 |
| [migrate_add_interviewers_table.sql](migrate_add_interviewers_table.sql) | 數據庫遷移腳本 |

## 💡 最佳實踐

1. **定期維護數據**
   - 定期檢查未配置面試官的職位
   - 刪除已離職員工的面試官記錄

2. **郵件監控**
   - 定期檢查郵件發送率
   - 設置告警當失敗率超過 5%

3. **測試新職位**
   - 配置面試官後進行一次完整的預約流程測試
   - 確認所有參與者都收到郵件

4. **備份**
   - 定期備份數據庫
   - 記錄 Google API 的重要設置

## 🎓 進階功能

完成基本配置後，可考慮以下增強功能：

- [ ] 不同時段的不同面試官
- [ ] 面試官忙碌時段標記
- [ ] 自動提醒（面試前 24 小時）
- [ ] 面試結果錄入系統
- [ ] Slack/Teams 集成

---

**需要幫助？** 查看 [故障排除指南](IMPLEMENTATION_CHECKLIST.md#-故障排除) 或聯繫技術支持。
