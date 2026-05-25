# Google Meet 自動化設定指南

## 問題症狀
- 應徵者完成預約後，郵件中沒有 Google Meet 會議連結
- 系統日誌中出現錯誤：`Google API 認證未完成`

## 原因
系統需要 Google API 認證以建立日曆事件和 Google Meet 會議。首次使用需要手動進行 OAuth2 認證，生成 `token.json` 文件。

## 解決步驟

### 1️⃣ 確認已有 credentials.json
檢查 `google_meet/credentials.json` 是否存在：
```bash
ls -la google_meet/credentials.json
```

**若不存在，需要從 Google Cloud Console 下載：**
- 訪問 [Google Cloud Console](https://console.cloud.google.com/)
- 創建或選擇項目
- 啟用 Calendar API 和 Gmail API
- 建立 OAuth2 認證（應用類型：桌面應用）
- 下載認證文件並重命名為 `credentials.json`
- 放置在 `google_meet/` 目錄下

### 2️⃣ 執行首次認證
在 `google_meet` 目錄中運行認證腳本：
```bash
cd google_meet
python authenticate.py
```

**預期輸出：**
```
============================================================
Google API 認證初始化
============================================================
🔗 正在啟動瀏覽器進行 Google 認證...
   如果沒有自動打開，請訪問本地 http://localhost:8080
   認證後會自動保存 token.json
```

### 3️⃣ 瀏覽器認證
1. 瀏覽器會自動打開 Google 登入頁面
2. 使用公司的 Google 帳號登入（例如：yukali58822@gmail.com）
3. 同意授予 Calendar 和 Gmail 權限
4. 看到「授權成功」頁面
5. 返回終端，會看到認證成功訊息

### 4️⃣ 驗證設定成功
檢查 `token.json` 是否已生成：
```bash
ls -la google_meet/token.json
```

若看到文件，表示認證成功！

### 5️⃣ 重啟應用
重啟 HR 系統應用，Google Meet 應該現在能正常運作：
```bash
python main.py
# 或使用 uvicorn
uvicorn main:app --reload
```

## 驗證成功
應徵者完成預約後，收到的郵件應包含：
- ✅ 面試時間
- ✅ 應徵職缺
- ✅ **「加入會議」按鈕（綠色）**
- ✅ 應徵者聯絡方式
- ✅ 取消預約按鈕

## 常見問題

### ❌ 錯誤：credentials.json 不存在
**解決：** 按照上方步驟 1️⃣ 下載並放置認證文件

### ❌ 錯誤：瀏覽器認證時出現重定向錯誤
**解決：** 
- 確保防火牆允許 localhost:8080
- 使用無痕瀏覽窗口
- 多試幾次

### ❌ token.json 已過期
**解決：** 重新運行：
```bash
python authenticate.py
```

### ❌ 郵件中顯示「Google Meet 連結將於面試前另行寄送」
**原因：** Google Meet 建立失敗（通常是認證問題）
**解決：**
1. 檢查 `token.json` 是否存在
2. 查看應用日誌中的錯誤訊息
3. 重新運行 `authenticate.py`

## 技術細節

- **Token 位置：** `google_meet/token.json`
- **認證作用域：**
  - `https://www.googleapis.com/auth/calendar` - 建立日曆事件
  - `https://www.googleapis.com/auth/gmail.send` - 寄送郵件
- **有效期：** Token 默認有效期很長，會自動刷新
- **安全性：** `token.json` 包含敏感信息，不應提交到版本控制系統

## 支援

若仍有問題，請檢查日誌：
```bash
# 查看最近的錯誤日誌
tail -f logs/app.log | grep -i "google_meet"
```

或聯繫技術支援。
