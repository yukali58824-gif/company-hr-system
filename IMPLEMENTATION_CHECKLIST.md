# 實裝清單 - Google Meet 邀請系統

## 📋 預備條件檢查

- [ ] Python 3.8+ 已安裝
- [ ] PostgreSQL 12+ 已安裝且運行中
- [ ] Google Cloud 項目已建立
- [ ] Google Calendar API 已啟用
- [ ] Google Meet 認證文件 (`credentials.json`) 已下載
- [ ] `token.json` 已生成（已執行 `authenticate.py`）

## 🔧 實裝步驟

### 1️⃣ 數據庫遷移（必須執行）

```bash
# 進入項目根目錄
cd c:\Users\PC02\Downloads\hr_system

# 執行遷移腳本
psql -U postgres -d hr_system -f migrate_add_interviewers_table.sql
```

驗證遷移結果：
```bash
# 檢查新表是否已創建
psql -U postgres -d hr_system -c "\dt interviewers position_interviewers"

# 檢查初始化數據
psql -U postgres -d hr_system -c "SELECT * FROM interviewers;"
```

### 2️⃣ 代碼更新確認

確保以下文件已更新（自動執行）：

#### main.py
- [x] 添加了 `get_interviewers_for_position()` 函數
- [x] 改進了 `schedule_google_meet_for_booking()` 函數
- [x] 添加了面試官管理 API 端點
- [x] 改進了郵件日誌記錄

驗證方法：
```bash
# 搜索新添加的函數
grep -n "get_interviewers_for_position" c:\Users\PC02\Downloads\hr_system\main.py

# 搜索新添加的 API 路由
grep -n "INTERVIEWERS API" c:\Users\PC02\Downloads\hr_system\main.py
```

#### google_meet/main.py
- [x] 添加了 `--interviewers` 命令行參數
- [x] 改進了參數解析邏輯
- [x] 支持 JSON 格式的面試官列表

驗證方法：
```bash
# 檢查是否正確導入 json 模塊
grep -n "import json" c:\Users\PC02\Downloads\hr_system\google_meet\main.py

# 檢查參數解析
grep -n "args.interviewers" c:\Users\PC02\Downloads\hr_system\google_meet\main.py
```

#### google_meet/calendar_service.py
- [x] 改進了 `create_meet_event()` 函數
- [x] 改變 `sendUpdates` 設置為 `'all'`
- [x] 改進了與會者配置

驗證方法：
```bash
# 檢查 sendUpdates 設置
grep -n "sendUpdates" c:\Users\PC02\Downloads\hr_system\google_meet\calendar_service.py
```

### 3️⃣ 應用程序重啟

```bash
# 停止現有的應用程序
# Ctrl+C 在終端中停止 uvicorn

# 重新啟動應用程序
python -m uvicorn main:app --reload --port 8000
```

### 4️⃣ 配置面試官（Web 管理界面）

1. 使用 HR 帳號登入系統
2. 進入「職缺管理」
3. 選擇要配置的職缺
4. 點擊新的「面試官」選項卡
5. 新增對應的面試官

**或使用 API 配置：**

```bash
# 獲取所有面試官
curl -X GET http://localhost:8000/api/interviewers \
  -H "Cookie: access_token={your_token}" \
  -H "Accept: application/json"

# 獲取職位的面試官
curl -X GET http://localhost:8000/api/positions/{position_id}/interviewers \
  -H "Cookie: access_token={your_token}" \
  -H "Accept: application/json"

# 新增面試官到職位
curl -X POST http://localhost:8000/api/positions/{position_id}/interviewers/{interviewer_id} \
  -H "Cookie: access_token={your_token}" \
  -H "Content-Type: application/json"
```

## ✅ 驗證清單

### 預約流程測試

- [ ] 應徵者通過前台成功預約
- [ ] 應徵者收到確認郵件（HTML 格式）
- [ ] 應徵者收到 Google Calendar 邀請（.ics 附件）
- [ ] 應徵者可以在 Google Calendar 中看到會議
- [ ] 應徵者可以接受/拒絕邀請

### 面試官通知驗證

- [ ] 面試官收到 Google Calendar 邀請
- [ ] 面試官在 Google Calendar 中看到會議
- [ ] 面試官可以接受/拒絕邀請
- [ ] 面試官可以查看 Google Meet 連結

### 郵件內容驗證

所有郵件應包含：
- [ ] 面試時間（正確的時區）
- [ ] 職位名稱
- [ ] Google Meet 連結（可點擊）
- [ ] 所有參與者列表
- [ ] 應徵者聯絡方式
- [ ] 企業聯絡方式

### Google Calendar 事件驗證

- [ ] 事件標題正確（「鼎霖視訊面試 - {名字}_{職位}」）
- [ ] 事件時間正確（亞洲/台北時區）
- [ ] Google Meet 連結包含在事件中
- [ ] 所有參與者都列在與會者中
- [ ] 事件說明包含職位、應徵者信息

### 數據庫驗證

```bash
# 檢查郵件日誌
psql -U postgres -d hr_system -c "
  SELECT booking_id, recipient_email, email_type, status, sent_at 
  FROM email_logs 
  WHERE booking_id = '{your_booking_id}' 
  ORDER BY sent_at DESC;"

# 檢查面試官配置
psql -U postgres -d hr_system -c "
  SELECT p.title, i.name, i.email 
  FROM position_interviewers pi 
  JOIN job_positions p ON p.id = pi.position_id 
  JOIN interviewers i ON i.id = pi.interviewer_id;"

# 檢查 Google Calendar 事件
psql -U postgres -d hr_system -c "
  SELECT b.id, b.google_event_id, b.google_meet_link 
  FROM bookings b 
  WHERE b.id = '{your_booking_id}';"
```

## 🐛 故障排除

### 問題：面試官未收到邀請

**檢查清單：**
1. 驗證面試官在 `interviewers` 表中存在
2. 驗證職位-面試官關聯在 `position_interviewers` 表中存在
3. 檢查面試官的 `is_active` 標記為 TRUE
4. 查看應用日誌中的 "schedule_google_meet.interviewers_fetched"

**解決步驟：**
```bash
# 檢查面試官是否已正確配置
psql -U postgres -d hr_system -c "
  SELECT COUNT(*) FROM position_interviewers 
  WHERE position_id = '{your_position_id}';"

# 如果計數為 0，則需要添加面試官
# 使用 API 或 SQL 添加：
psql -U postgres -d hr_system -c "
  INSERT INTO position_interviewers (position_id, interviewer_id) 
  VALUES ('{position_id}', '{interviewer_id}');"
```

### 問題：Google Calendar 邀請中沒有 Google Meet 連結

**檢查清單：**
1. 確認 `GOOGLE_MEET_SENDER_EMAIL` 環境變數已設置
2. 驗證 Google API credentials 擁有 Calendar API 權限
3. 檢查 `create_meet_event()` 函數的 `conferenceData` 配置

**查看日誌：**
```bash
# 搜索 Google Meet 相關的日誌
tail -f {application_log} | grep -i "google_meet"
```

### 問題：郵件格式不正確

**檢查清單：**
1. 驗證系統時區設置為 "Asia/Taipei"
2. 檢查 `build_email_html()` 函數中的變量替換
3. 確認 HTML 模板文件存在且格式正確

### 問題：應用程序啟動失敗

**常見原因：**
- 數據庫連接失敗：檢查 DATABASE_URL
- Python 依賴缺失：執行 `pip install -r requirements.txt`
- 端口被占用：更改 `--port` 參數

**調試步驟：**
```bash
# 查看詳細錯誤信息
python main.py --debug

# 檢查數據庫連接
psql -U postgres -d hr_system -c "SELECT 1;"
```

## 📊 系統健康檢查

定期執行以下命令以確保系統健康運行：

```bash
# 檢查未發送的郵件
psql -U postgres -d hr_system -c "
  SELECT COUNT(*) FROM email_logs 
  WHERE status = 'pending';"

# 檢查過去 7 天的郵件發送率
psql -U postgres -d hr_system -c "
  SELECT email_type, COUNT(*), 
    ROUND(100.0 * SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
  FROM email_logs 
  WHERE sent_at >= NOW() - INTERVAL '7 days'
  GROUP BY email_type;"

# 檢查未配置面試官的職位
psql -U postgres -d hr_system -c "
  SELECT p.id, p.title FROM job_positions p 
  WHERE p.is_active = TRUE 
  AND p.id NOT IN (SELECT DISTINCT position_id FROM position_interviewers);"
```

## 📝 相關文檔

- [Google Meet 邀請系統完整指南](GOOGLE_CALENDAR_INVITATION_SYSTEM.md)
- [原始 Google Meet 設置指南](GOOGLE_MEET_SETUP.md)
- [數據庫遷移腳本](migrate_add_interviewers_table.sql)
- [系統 README](README.md)

## 🎯 下一步

完成上述所有步驟後，系統應該能夠：

1. ✅ 應徵者預約時自動產生 Google Meet 連結
2. ✅ 寄送 Google Calendar 邀請給所有參與者
3. ✅ 建立 Google Calendar 行程
4. ✅ 所有參與者都能：
   - 加入 Google 日曆
   - 接受/拒絕邀請
   - 查看 Google Meet 連結

如有問題，請參考「故障排除」部分或查看應用日誌。
