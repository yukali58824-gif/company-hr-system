import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from calendar_service import create_meet_event
from gmail_service import send_to_applicant, send_to_attendees

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
]
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"
GOOGLE_CANCEL_FORM_URL = os.environ.get("GOOGLE_CANCEL_FORM_URL", "")


def get_services(login_email: str = None):
    """取得 Google Calendar 與 Gmail 授權服務"""
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
    gmail    = build("gmail",    "v1", credentials=creds)
    return calendar, gmail


def schedule_meeting(
    login_email: str,
    subject: str,
    start_dt: datetime,
    end_dt: datetime,
    description: str = "",
    applicant: dict = None,
    attendees: list[dict] = None,
):
 
    calendar, gmail = get_services(login_email=login_email)


    print("建立 Google Meet 會議中...")
    invitees = []
    if applicant:
        invitees.append(applicant)
    if attendees:
        invitees.extend(attendees)

    event = create_meet_event(calendar, subject, start_dt, end_dt, description, invitees)
    meet_link = event.get("hangoutLink", "")
    print(f"會議建立成功：{meet_link}")
    print(f"行事曆網址：{event['htmlLink']}")

    if attendees:
        send_to_attendees(
            gmail=gmail,
            sender=login_email,
            subject=subject,
            start_dt=start_dt,
            end_dt=end_dt,
            meet_link=meet_link,
            description=description,
            attendees=attendees,
            job_title=applicant.get("job_title", "") if applicant else "",
            applicant_email=applicant.get("email", "") if applicant else "",
            applicant_phone=applicant.get("phone", "") if applicant else "",
        )

    if applicant:
        google_form_url = GOOGLE_CANCEL_FORM_URL or "https://docs.google.com/forms/d/e/1FAIpQLSdPVYIMyx_IgSl3jfFqHZ9hOahASTEHpg8LbEP8_LFdqviN_A/viewform?edit2=2_ABaOnucGnsoPAbh2wmDy5el3KiDVKxDf8fzJGH3Rz9GKi4qx9BQDgRKN8VIa_dWRcQ"
        send_to_applicant(
            gmail=gmail,
            sender=login_email,
            subject=subject,
            start_dt=start_dt,
            end_dt=end_dt,
            meet_link=meet_link,
            description=description,
            applicant=applicant,
            all_attendees=attendees or [],
            google_form_url=google_form_url,
            job_title=applicant.get("job_title", ""),
            applicant_phone=applicant.get("phone", ""),
        )

    return event


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="建立 Google Meet 會議並寄送通知給應徵者與內部人員")
    parser.add_argument("--login_email", default=os.environ.get("GOOGLE_MEET_SENDER_EMAIL", "yukali58822@gmail.com"))
    parser.add_argument("--applicant_name", required=True)
    parser.add_argument("--applicant_email", required=True)
    parser.add_argument("--applicant_phone", default="")
    parser.add_argument("--job_title", required=True)
    parser.add_argument("--start_dt", required=True)
    parser.add_argument("--end_dt", required=True)
    parser.add_argument("--description", default="若有任何問題歡迎<br><b>在104留下訊息</b>，<br>或直接來電 <b>0906-205-353</b>，<br>我們會儘速與您聯繫。")
    args = parser.parse_args()

    tz = timezone(timedelta(hours=8))
    start_dt = datetime.fromisoformat(args.start_dt)
    end_dt = datetime.fromisoformat(args.end_dt)

    applicant = {
        "name": args.applicant_name,
        "email": args.applicant_email,
        "phone": args.applicant_phone,
        "job_title": args.job_title,
    }

    attendees = [{"name": "Alice 陳", "email": "yukali58820@gmail.com"}]

    if "業務" in args.job_title:
        rules = {
            ("高雄屏東區",  "市場開發組"): [
                {"name": "小佩", "email": "yukali58821@gmaol.com"}
            ],
            ("台南區",  "市場開發組"): [],
        }

        for keywords, members in rules.items():
            if all(word in args.job_title for word in keywords):
                attendees.extend(members)

    event = schedule_meeting(
        login_email=args.login_email,
        subject=f"鼎霖視訊面試- {args.applicant_name}_{args.job_title}",
        start_dt=start_dt,
        end_dt=end_dt,
        description=args.description,
        applicant=applicant,
        attendees=attendees,
    )

    print(f"EVENT_ID:{event.get('id','')}")
    print(f"MEET_LINK:{event.get('hangoutLink','')}")



#應徵者資訊
'''
job_title
applicant_name
applicant_email
start_dt
end_dt
'''