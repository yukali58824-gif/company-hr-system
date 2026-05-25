import base64
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent / "templates" / "invite_email.html"
# https://chatgpt.com/share/6a0c26db-a2c8-8320-9cde-9765a2768d43
# 1. 產生 HTML 郵件
# 2. 產生 Calendar(.ics)
# 3. 組合 Gmail 郵件格式
# 4. 用 Gmail API 寄出

def load_template() -> str:
    """載入 HTML 模板"""
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def render_template(template: str, variables: dict) -> str:
    """將 {{變數名}} 替換為實際內容"""
    for key, value in variables.items():
        template = template.replace(f"{{{{{key}}}}}", str(value))
    return template


def build_email_html(
    recipient_name: str,
    recipient_role: str,
    subject: str,
    start_dt: datetime,
    end_dt: datetime,
    meet_link: str,
    description: str,
    organizer_email: str, #主辦人 Email
    all_attendees: list[dict],
    job_title: str = "",
    applicant_email: str = "",
    applicant_phone: str = "",
    cancel_section: str = "", #不是每封信都需要，因此預設空字串
) -> str: #HTML內容
    """載入模板並填入變數"""

    # 與會者清單
    attendee_rows = "".join([
        f'<li>👤 {a.get("name") or a["email"]}'
        f'  <span style="color:#aaa;">({a["email"]})</span>'
        f'  <span class="badge">{a.get("role","")}</span></li>'
        for a in all_attendees
    ])

    # 職缺資訊區塊
    job_title_block = ""
    if job_title:
        job_title_block = f'<div class="info-row"><div class="label">應徵職缺</div><div class="content-text">{job_title}</div></div>'

    # 應徵者聯絡資訊區塊
    applicant_info_block = ""
    if applicant_email or applicant_phone:
        info_items = []
        if applicant_email:
            info_items.append(applicant_email)
        if applicant_phone:
            info_items.append(applicant_phone)
        applicant_info_block = f'<div class="info-row"><div class="label">應徵者</div><div class="content-text">{" · ".join(info_items)}</div></div>'

    attendee_section = ""
    if attendee_rows:
        attendee_section = f'<div class="info-row"><div class="label">參與人員</div><div class="content-text"><ul>{attendee_rows}</ul></div></div>'

    # 說明區塊（選填）
    description_block = ""
    if description:
        description_block = f'<div class="info-row"><div class="label">說明</div><div class="content-text">{description}</div></div>'

    # Google Meet 按鈕
    meet_button = ""
    if meet_link:
        meet_button = f'<a href="{meet_link}" class="btn" target="_blank">加入 Google Meet 會議</a>'

    cancel_section = cancel_section or ""
    variables = {
        "recipient_name":    recipient_name,
        "recipient_role":    recipient_role,
        "subject":           subject,
        "start_str":         start_dt.strftime("%Y年%m月%d日 %H:%M"),
        "end_str":           end_dt.strftime("%H:%M"),
        "duration":          int((end_dt - start_dt).seconds / 60),
        "meet_link":         meet_link,
        "meet_button":       meet_button,
        "description_block": description_block,
        "organizer_email":   organizer_email,
        "attendee_rows":     attendee_rows,
        "attendee_section":  attendee_section,
        "job_title_block":   job_title_block,
        "applicant_info_block": applicant_info_block,
        "attendee_count":    len(all_attendees),
        "cancel_section":    cancel_section,
        }

    return render_template(load_template(), variables)


def build_ical_event(
    organizer_email: str,
    subject: str,
    start_dt: datetime,
    end_dt: datetime,
    description: str,
    meet_link: str,
    attendees: list[dict],
) -> str:
    """產生 iCal 會議邀請內容"""
    start_utc = start_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end_utc = end_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    attendees_lines = []
    for attendee in attendees:
        name = attendee.get("name") or attendee["email"].split("@")[0]
        attendees_lines.append(
            "ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED;RSVP=TRUE;CN={name}:mailto:{email}".format(
                name=name,
                email=attendee["email"],
            )
        )

    ical = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//DingLin//Google Meet Invitation//ZH
METHOD:REQUEST
BEGIN:VEVENT
UID:{int(time.time())}@dinglin.local
DTSTAMP:{dtstamp}
DTSTART:{start_utc}
DTEND:{end_utc}
SUMMARY:{subject}
DESCRIPTION:{description}\\n\\n📹 Google Meet 連結\\n{meet_link}
LOCATION:Google Meet ({meet_link})
URL:{meet_link}
ORGANIZER;CN=Organizer:mailto:{organizer_email}
{chr(10).join(attendees_lines)}
SEQUENCE:0
STATUS:CONFIRMED
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""
    return ical


def send_simple_email(
    gmail,
    sender: str,
    recipient_email: str,
    subject: str,
    html_body: str,
):
    """寄送純 HTML 郵件（無日歷邀請）"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"面試邀請：{subject}"
    msg["From"] = f"Interview Platform <{sender}>"
    msg["To"] = recipient_email

    part1 = MIMEText("您有一封新的面試邀請。", "plain", "utf-8")
    part1.replace_header("Content-Transfer-Encoding", "8bit")
    msg.attach(part1)
    
    part2 = MIMEText(html_body, "html", "utf-8")
    part2.replace_header("Content-Transfer-Encoding", "8bit")
    msg.attach(part2)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail.users().messages().send(userId="me", body={"raw": raw}).execute()


def send_calendar_invite(
    gmail,
    sender: str,
    recipient_email: str,
    subject: str,
    html_body: str,
    ical_body: str,
):
    """寄送合併 HTML 與 iCal 的會議邀請"""
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"會議邀請：{subject}"
    msg["From"] = f"Interview Platform <{sender}>"
    msg["To"] = recipient_email
    msg["Content-class"] = "urn:content-classes:calendarmessage"

    alternative = MIMEMultipart("alternative")
    part1 = MIMEText("您有一封新的會議邀請。", "plain", "utf-8")
    part1.replace_header("Content-Transfer-Encoding", "8bit")
    alternative.attach(part1)
    
    part2 = MIMEText(html_body, "html", "utf-8")
    part2.replace_header("Content-Transfer-Encoding", "8bit")
    alternative.attach(part2)
    msg.attach(alternative)

    ics_part = MIMEText(ical_body, "calendar", "utf-8")
    ics_part.add_header("Content-Disposition","inline")
    ics_part.replace_header(
        "Content-Type",
        'text/calendar;method=REQUEST;charset="UTF-8"'
    )
    msg.attach(ics_part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail.users().messages().send(userId="me", body={"raw": raw}).execute()


def send_to_applicant(
    gmail,
    sender: str,
    subject: str,
    start_dt: datetime,
    end_dt: datetime,
    meet_link: str,
    description: str,
    applicant: dict,
    all_attendees: list[dict],
    google_form_url: str,
    job_title: str = "",
    applicant_phone: str = "",
) -> dict:
    """寄送 Google Calendar 邀請給應聘者（含完整郵件說明與取消按鈕）"""
    email = applicant["email"]
    name = applicant.get("name") or email.split("@")[0]
    role = applicant.get("role", "應聘者")

    cancel_button_html = ""
    if google_form_url:
        cancel_button_html = f'<a href="{google_form_url}" class="cancel-btn">取消預約</a>'

    try:
        # 產生富文本郵件內容（包含所有信息）
        html = build_email_html(
            recipient_name=name,
            recipient_role=role,
            subject=subject,
            start_dt=start_dt,
            end_dt=end_dt,
            meet_link=meet_link,
            description=description,
            organizer_email=sender,
            all_attendees=all_attendees,
            job_title=job_title,
            applicant_email=applicant["email"],
            applicant_phone=applicant_phone,
            cancel_section=cancel_button_html,
        )
        
        # 產生 iCal 邀請（包含所有與會者）
        ical = build_ical_event(
            organizer_email=sender,
            subject=subject,
            start_dt=start_dt,
            end_dt=end_dt,
            description=description,
            meet_link=meet_link,
            attendees=all_attendees,
        )
        
        # 發送 Calendar 邀請，讓應聘者可以加入日曆、接受/拒絕
        send_calendar_invite(gmail, sender, email, subject, html, ical)
        print(f"  ✅ 應聘者 {name}（{role}）→ {email} [含 Calendar 邀請、取消按鈕]")
        return {"success": [email], "failed": []}
    except Exception as e:
        print(f"  ❌ 應聘者 {name}（{role}）→ 失敗：{e}")
        import traceback
        traceback.print_exc()
        return {"success": [], "failed": [{"email": email, "error": str(e)}]}


def send_to_attendees(
    gmail,
    sender: str,
    subject: str,
    start_dt: datetime,
    end_dt: datetime,
    meet_link: str,
    description: str,
    attendees: list[dict],
    job_title: str = "",
    applicant_email: str = "",
    applicant_phone: str = "",
    delay_seconds: float = 1.0,
) -> dict:
    """寄送 Google Calendar 邀請給內部參與者（含優化的 HTML 郵件說明）"""
    total = len(attendees)
    success = []
    failed = []

    print(f"\n寄送 Google Calendar 邀請給 {total} 位內部參與者")
    print("─" * 50)

    for i, person in enumerate(attendees, start=1):
        email = person["email"]
        name = person.get("name") or email.split("@")[0]
        role = person.get("role", "與會者")

        try:
            # 為內部參與者產生優化的 HTML 郵件內容（不含應聘者取消按鈕）
            html = build_email_html(
                recipient_name=name,
                recipient_role=role,
                subject=subject,
                start_dt=start_dt,
                end_dt=end_dt,
                meet_link=meet_link,
                description=description,
                organizer_email=sender,
                all_attendees=attendees,
                job_title=job_title,
                applicant_email=applicant_email,
                applicant_phone=applicant_phone,
                cancel_section="",  # 內部參與者不需要取消按鈕
            )
            
            # 產生 iCal 邀請（包含所有與會者）
            ical = build_ical_event(
                organizer_email=sender,
                subject=subject,
                start_dt=start_dt,
                end_dt=end_dt,
                description=description,
                meet_link=meet_link,
                attendees=attendees,
            )
            
            # 發送 Calendar 邀請，讓內部人員可以加入日曆、接受/拒絕
            send_calendar_invite(gmail, sender, email, subject, html, ical)
            success.append(email)
            print(f"  [{i:02d}/{total}] ✅ {name}（{role}）→ {email} [Calendar 邀請]")

        except Exception as e:
            failed.append({"email": email, "error": str(e)})
            print(f"  [{i:02d}/{total}] ❌ {name}（{role}）→ 失敗：{e}")
            import traceback
            traceback.print_exc()

        if i < total:
            time.sleep(delay_seconds)

    print("─" * 50)
    print(f"成功 {len(success)} 封　失敗 {len(failed)} 封")
    if failed:
        print("\n失敗清單：")
        for f in failed:
            print(f"     • {f['email']}：{f['error']}")

    return {"success": success, "failed": failed}
