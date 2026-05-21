from datetime import datetime, timezone


def create_meet_event(calendar, subject, start_dt, end_dt, description="", attendees=None):
    """建立含 Google Meet 連結的行事曆事件"""
    event = {
        "summary": subject,
        "description": description,
    
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Taipei"}, #Google API 聽得懂的國際標準格式(ISO)
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": "Asia/Taipei"},
        "conferenceData": { #產生 Meet 連結
            "createRequest": { #請 Google 建立視訊會議
                "requestId": f"meet-{int(start_dt.timestamp())}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
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
            {"email": a.get("email"), "displayName": a.get("name")} for a in attendees if a.get("email")
        ]

    # 使用 sendUpdates='all' 讓 Calendar 自動發送邀請，避免另行寄送造成重複
    return calendar.events().insert(
        calendarId="primary",
        body=event,
        conferenceDataVersion=1,
        sendUpdates="none",
    ).execute()
