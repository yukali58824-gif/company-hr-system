# Meeting Scheduler

自動建立 Google Meet 會議並批次寄送個人化邀請信。

## 專案結構

```
meeting_scheduler/
├── main.py                  # 主程式（從這裡執行）
├── calendar_service.py      # 建立 Google Meet 會議
├── gmail_service.py         # 批次寄信邏輯
├── role_config.py           # 職稱與準備事項對照表
├── requirements.txt         # 套件清單
├── credentials.json         # ← （從 Google Cloud 下載）
└── templates/
    └── invite_email.html    # 信件 HTML 模板
```

## 安裝步驟

### 1. 安裝套件
pip install -r requirements.txt


### 2. 設定 Google Cloud
1. 前往 https://console.cloud.google.com
2. 建立新專案，啟用 **Google Calendar API** 與 **Gmail API**
3. 建立憑證 → OAuth 2.0 用戶端 ID → 選「桌面應用程式」
4. 下載憑證並命名為 `credentials.json` 放入本目錄

### 3. 修改 main.py
編輯 `main.py` 底部的執行範例，填入你的資訊：
```python
schedule_meeting(
    login_email="your@gmail.com",   # 你的 Gmail
    subject="會議主題",
    start_dt=datetime(2026, 5, 21, 14, 0, tzinfo=tz),
    end_dt=datetime(2026, 5, 21, 15, 0, tzinfo=tz),
    description="會議說明（選填）",
    attendees=[
        {"name": "姓名", "email": "email@gmail.com", "role": "職稱"},
    ],
)
```

### 4. 執行
python main.py

首次執行會開啟瀏覽器要求 Google 授權，授權後自動儲存 `token.json`。

## 支援職稱

| 職稱關鍵字 | 準備事項類型 |
|---|---|
| PM / Project Manager | 專案進度、Blocker、里程碑 |
| 工程師 / Engineer | 開發進度、Bug、技術難題 |
| 設計師 / Designer | 設計稿、產出、設計決策 |
| QA / 測試 | 測試報告、Bug 清單 |
| 行銷 / Marketing | 成效數據、廣告報告 |
| 主管 / Manager | OKR、跨部門協調 |
| 其他 | 預設通用準備事項 |

## 注意事項
- `credentials.json` 與 `token.json` 請勿上傳至 Git
- 修改信件樣式只需編輯 `templates/invite_email.html`
- 新增職稱只需在 `role_config.py` 的 `ROLE_PREPARATION` 加入新條目
