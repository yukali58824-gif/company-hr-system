import os
import secrets
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", 587))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
MAIL_FROM     = os.getenv("MAIL_FROM", "noreply@example.com")
MAIL_FROM_NAME= os.getenv("MAIL_FROM_NAME", "Interview Platform")
BASE_URL      = os.getenv("BASE_URL", "http://localhost:8000")
GOOGLE_CANCEL_FORM_URL = os.getenv("GOOGLE_CANCEL_FORM_URL", "")

def generate_cancel_token() -> tuple[str, datetime]:
    token = secrets.token_urlsafe(64)
    expires = datetime.utcnow() + timedelta(days=7)
    return token, expires

async def send_booking_confirm_email(
    to_email: str,
    applicant_name: str,
    position_title: str,
    slot_date: str,
    start_time: str,
    end_time: str,
    cancel_token: str,
):
    cancel_url = GOOGLE_CANCEL_FORM_URL or f"{BASE_URL}/cancel?t={cancel_token}"
    subject = f"【面試預約確認】{position_title} — {slot_date}"
    body = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; color: #333; margin: 0; padding: 0; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 20px auto; background-color: #fff; border-radius: 4px; overflow: hidden;">
        <!-- Header -->
        <div style="background-color: #1a1a1a; color: #fff; padding: 16px 24px; border-bottom: 4px solid #f39c12;">
            <h1 style="margin: 0; font-size: 18px; font-weight: 600;">HR Interview Platform</h1>
        </div>
        
        <!-- Content -->
        <div style="padding: 24px;">
            <p style="margin: 0 0 16px 0; font-size: 14px;">您好，<strong>{applicant_name}</strong>：</p>
            
            <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6;">
                恭喜您進入面試階段！感謝您提交申請，以下是您的面試預約詳情：
            </p>
            
            <!-- Interview Details -->
            <div style="border-left: 4px solid #f39c12; padding-left: 16px; margin: 24px 0; background-color: #fafafa; padding: 16px; padding-left: 16px;">
                <h3 style="margin: 0 0 12px 0; color: #1a1a1a; font-size: 14px; font-weight: 600;">面試時間</h3>
                <p style="margin: 0 0 12px 0; font-size: 14px;"><strong>{slot_date} {start_time} – {end_time}</strong></p>
                
                <h3 style="margin: 12px 0; color: #1a1a1a; font-size: 14px; font-weight: 600;">應徵職位</h3>
                <p style="margin: 0; font-size: 14px;"><strong>{position_title}</strong></p>
                
                <h3 style="margin: 12px 0; color: #1a1a1a; font-size: 14px; font-weight: 600;">說明</h3>
                <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.6;">
                    若有任何問題，請在面試前留言或致電聯繫。<br>
                    我們期待與您進行對話。
                </p>
            </div>
            
            <p style="margin: 24px 0 16px 0; font-size: 14px; font-weight: 600;">Google Meet 會議室連結：</p>
            <p style="margin: 0 0 24px 0; font-size: 13px; color: #666;">會議連結將在面試前發送</p>
            
            <!-- Action Buttons -->
            <div style="display: flex; gap: 12px; margin: 24px 0;">
                <a href="{BASE_URL}" style="flex: 1; padding: 12px; text-align: center; background-color: #f39c12; color: #fff; text-decoration: none; border-radius: 4px; font-weight: 600; font-size: 14px; display: inline-block;">查看預約詳情</a>
                <a href="{cancel_url}" style="flex: 1; padding: 12px; text-align: center; background-color: #1a1a1a; color: #fff; text-decoration: none; border-radius: 4px; font-weight: 600; font-size: 14px; display: inline-block;">取消預約</a>
            </div>
            
            <p style="margin: 24px 0 0 0; font-size: 12px; color: #888; border-top: 1px solid #e0e0e0; padding-top: 16px;">
                若非您本人操作，請忽略此信。此連結 7 天內有效。
            </p>
        </div>
        
        <!-- Footer -->
        <div style="background-color: #f9f9f9; padding: 12px 24px; text-align: center; font-size: 12px; color: #888; border-top: 1px solid #e0e0e0;">
            <p style="margin: 0;">© 2024 HR Interview Platform. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""
    await _send(to_email, subject, body)

async def send_cancel_notify_email(
    to_email: str,
    applicant_name: str,
    position_title: str,
    slot_date: str,
):
    subject = f"【面試取消通知】{position_title}"
    body = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; color: #333; margin: 0; padding: 0; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 20px auto; background-color: #fff; border-radius: 4px; overflow: hidden;">
        <!-- Header -->
        <div style="background-color: #1a1a1a; color: #fff; padding: 16px 24px; border-bottom: 4px solid #f39c12;">
            <h1 style="margin: 0; font-size: 18px; font-weight: 600;">HR Interview Platform</h1>
        </div>
        
        <!-- Content -->
        <div style="padding: 24px;">
            <p style="margin: 0 0 16px 0; font-size: 14px;">您好，<strong>{applicant_name}</strong>：</p>
            
            <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6;">
                您的面試預約已成功取消。
            </p>
            
            <!-- Cancellation Details -->
            <div style="border-left: 4px solid #f39c12; padding-left: 16px; margin: 24px 0; background-color: #fafafa; padding: 16px; padding-left: 16px;">
                <h3 style="margin: 0 0 12px 0; color: #1a1a1a; font-size: 14px; font-weight: 600;">取消詳情</h3>
                <p style="margin: 0 0 8px 0; font-size: 14px;"><strong>職位：</strong>{position_title}</p>
                <p style="margin: 0; font-size: 14px;"><strong>預約日期：</strong>{slot_date}</p>
            </div>
            
            <p style="margin: 24px 0; font-size: 14px; line-height: 1.6;">
                若需要重新預約或有任何疑問，歡迎隨時聯繫我們。
            </p>
            
            <!-- Action Button -->
            <div style="text-align: center; margin: 24px 0;">
                <a href="{BASE_URL}" style="padding: 12px 28px; background-color: #f39c12; color: #fff; text-decoration: none; border-radius: 4px; font-weight: 600; font-size: 14px; display: inline-block;">返回預約頁面</a>
            </div>
            
            <p style="margin: 24px 0 0 0; font-size: 12px; color: #888; border-top: 1px solid #e0e0e0; padding-top: 16px;">
                若非您本人操作，請忽略此信。
            </p>
        </div>
        
        <!-- Footer -->
        <div style="background-color: #f9f9f9; padding: 12px 24px; text-align: center; font-size: 12px; color: #888; border-top: 1px solid #e0e0e0;">
            <p style="margin: 0;">© 2024 HR Interview Platform. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""
    await _send(to_email, subject, body)

async def _send(to: str, subject: str, html: str):
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[MAIL SKIP] To: {to} | Subject: {subject}")
        return
    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{MAIL_FROM_NAME} <{MAIL_FROM}>"
        msg["To"]      = to
        msg.attach(MIMEText(html, "html", "utf-8"))
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            start_tls=True,
        )
        print(f"[MAIL SENT] To: {to}")
    except Exception as e:
        print(f"[MAIL ERROR] {e}")
        import logging
        logging.getLogger(__name__).error(f"Failed to send email: {e}", exc_info=True)
