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
