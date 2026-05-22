from datetime import datetime, timezone
from pathlib import Path
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"


def get_calendar_service(login_email: str = None):
    """取得 Google Calendar 授權服務"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=8080, login_hint=login_email)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    calendar = build("calendar", "v3", credentials=creds)
    return calendar


def delete_event(calendar, event_id: str, send_updates: str = "none") -> dict:
    """
    刪除日曆事件
    
    Args:
        calendar: Google Calendar 服務物件
        event_id: 要刪除的事件 ID
        send_updates: 更新方式，可選值：
            - "all": 寄送取消通知給所有與會者
            - "externalOnly": 僅寄送給外部與會者
            - "none": 不寄送任何通知（預設）
    
    Returns:
        刪除操作的結果
    """
    return calendar.events().delete(
        calendarId="primary",
        eventId=event_id,
        sendUpdates=send_updates,
    ).execute()


def delete_event_by_id(login_email: str, event_id: str, send_updates: str = "none") -> dict:
    """
    透過事件 ID 刪除日曆事件
    
    Args:
        login_email: Google 帳號 Email
        event_id: 要刪除的事件 ID
        send_updates: 更新方式（"all"、"externalOnly" 或 "none"）
    
    Returns:
        刪除操作的結果
    """
    calendar = get_calendar_service(login_email=login_email)
    print(f"正在刪除事件：{event_id}")
    result = delete_event(calendar, event_id, send_updates)
    print(f"事件 {event_id} 已成功刪除")
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="刪除 Google Calendar 事件")
    parser.add_argument("--login_email", default=os.environ.get("GOOGLE_MEET_SENDER_EMAIL", "yukali58822@gmail.com"))
    parser.add_argument("--event_id", required=True, help="要刪除的事件 ID")
    parser.add_argument("--send_updates", default="none", choices=["all", "externalOnly", "none"],
                        help="更新方式：all(寄送給所有人)、externalOnly(僅外部)、none(不寄送)")
    
    args = parser.parse_args()
    
    delete_event_by_id(args.login_email, args.event_id, args.send_updates)
