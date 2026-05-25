# HR Interview Platform

人資招募面試預約平台，使用 **FastAPI + PostgreSQL** 建構，純 HTML/CSS/JS 前端（無框架依賴）。

---

## 功能清單

### 應徵者端（公開）
- 下拉選擇應徵職缺
- 查看目前有名額的面試時段
- 填寫姓名 / Email / 電話完成預約
- 預約成功後自動寄送確認信，信中含「取消預約」按鈕
- 點擊 Email 連結即可取消，無需帳號

### HR 後台
- 多帳號登入（JWT Cookie 驗證）
- 新增 / 刪除應徵職缺（下拉清單）
- 新增面試時段（日期、開始/結束時間、名額、Meet 連結）
- 前端即時驗證結束時間不得早於開始時間
- 關閉 / 停用時段
- 查看所有預約紀錄，支援狀態篩選 + 關鍵字搜尋
- 刪除任意預約紀錄（軟刪除）

---

## 快速啟動

### 1. 建立 PostgreSQL 資料庫

```bash
$env:PGPASSWORD="LiMin20260505"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d hr_system -f init_db.sql
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env，填入你的 DB 連線字串與 Email 設定
```

### 3. 安裝套件並啟動

```bash
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

瀏覽器打開 http://localhost:8000

---

## 預設帳號

| Email | 密碼 | 角色 |
|-------|------|------|
| admin@example.com | Admin1234 | admin |

---

## 頁面對應

| URL | 說明 |
|-----|------|
| `/` | 應徵者預約頁面 |
| `/hr/login` | HR 登入 |
| `/hr` | HR 後台（時段管理 + 職缺管理）|
| `/hr/bookings` | 所有預約紀錄 |
| `/cancel?t=<token>` | 應徵者取消預約 |

---

## Email 設定（Gmail）

1. 開啟 Gmail 兩步驟驗證
2. 至 [應用程式密碼](https://myaccount.google.com/apppasswords) 產生密碼
3. 填入 `.env`：
   ```
   SMTP_USER=your@gmail.com
   SMTP_PASSWORD=your-16-char-app-password
   ```

> 若未設定 Email，系統仍可正常運作，僅在終端機印出 `[MAIL SKIP]` 訊息。

---

## 專案結構

```
hr_system/
├── main.py                  # FastAPI 主程式，所有 API 路由
├── init_db.sql              # PostgreSQL 建表 + seed 資料
├── requirements.txt
├── .env.example
├── backend/
│   ├── database.py          # asyncpg 連線池
│   ├── auth.py              # JWT / bcrypt
│   └── email_utils.py       # aiosmtplib 寄信
└── frontend/
    ├── index.html           # 應徵者預約
    ├── hr_login.html        # HR 登入
    ├── hr_dashboard.html    # HR 後台
    ├── hr_bookings.html     # 預約紀錄
    ├── cancel.html          # 取消預約
    └── static/css/
        └── style.css
```

📌 Google 認證步驟
# 進入 google_meet 目錄
cd c:\Users\PC02\Downloads\hr_system\google_meet

# 執行認證腳本
python authenticate.py
這將打開瀏覽器進行 Google OAuth2 認證，完成後會生成 token.json 文件。