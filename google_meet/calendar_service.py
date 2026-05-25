from datetime import datetime, timezone


def create_meet_event(calendar, subject, start_dt, end_dt, description="", attendees=None):
    """建立含 Google Meet 連結的行事曆事件
    
    Args:
        calendar: Google Calendar 服務對象
        subject: 會議主題
        start_dt: 開始時間（含時區）
        end_dt: 結束時間（含時區）
        description: 會議說明
        attendees: 與會者列表，每個項目應包含 "email" 和 "name" 鍵
    
    Returns:
        建立的行事曆事件對象，包含 hangoutLink（Google Meet 連結）
    """
    event = {
        "summary": subject,
        "description": description,
    
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Taipei"}, #Google API 聽得懂的國際標準格式(ISO)
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": "Asia/Taipei"},
        "conferenceData": { #產生 Meet 連結
            "createRequest": { #請 Google 建立視訊會議
                "requestId": f"meet-{int(start_dt.timestamp())}",
                "conferenceSolution": {"type": "hangoutsMeet"},
            }
        },
        "reminders": { #通知設定
            "useDefault": False, #不要使用 Google 預設提醒
            "overrides": [
                {"method": "email",  "minutes": 60},# 60 分鐘前寄 Email
                {"method": "popup",  "minutes": 10},# 10 分鐘前跳通知
            ],
        },
    }
    # 若提供與會者，加入到事件中（Calendar 會統一發送邀請）
    if attendees:
        event["attendees"] = [
            {"email": a.get("email"), "displayName": a.get("name", a.get("email"))} 
            for a in attendees 
            if a.get("email")
        ]

    # 使用 sendUpdates='all' 讓 Google Calendar 自動發送邀請給所有參與者
    # 這樣可以確保：
    # 1. 所有參與者都收到 Google Calendar 邀請
    # 2. 他們可以直接在 Google Calendar 中接受/拒絕
    # 3. 但我們也會通過 Gmail API 發送 HTML + iCal 郵件以獲得更好的用戶體驗
    return calendar.events().insert(
        calendarId="primary",
        body=event,
        conferenceDataVersion=1,
        sendUpdates="all",  # 發送邀請給所有參與者
    ).execute()
