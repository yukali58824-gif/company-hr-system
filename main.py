import os
import sys
import json
import uuid
import logging
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime, time, date, timedelta
import asyncio
from datetime import timezone

from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, Cookie, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from jose import jwt, JWTError
from asyncpg.exceptions import UniqueViolationError
from openpyxl import Workbook
from io import BytesIO

from backend.auth import get_current_hr, verify_password, create_access_token, decode_token, SECRET_KEY
from backend.database import get_pool
from backend.email_utils import generate_cancel_token, _send, BASE_URL
from google_meet.calendar_delete import get_calendar_service, delete_event

logger = logging.getLogger(__name__)


def log_json(level: int, event: str, **fields):
    payload = {"event": event, **fields}
    logger.log(level, json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":")))

# ─────────────────────────────────────────────
# Initialize FastAPI
# ─────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
app = FastAPI()

# Setup static files
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "frontend" / "static")),
    name="static"
)

# Setup templates
templates = Jinja2Templates(directory=str(BASE_DIR / "frontend"))

# 取消預約外部表單連結，可用於將取消按鈕直接導向 Google 表單
CANCEL_FORM_URL = os.getenv("GOOGLE_CANCEL_FORM_URL", "")

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class SlotCreate(BaseModel):
    slot_date: str
    start_time: str
    end_time: str
    max_capacity: int
    google_meet_link: Optional[str] = ""
    notes: Optional[str] = ""

class SlotEdit(BaseModel):
    slot_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    max_capacity: Optional[int] = None
    status: Optional[str] = None
    google_meet_link: Optional[str] = None
    notes: Optional[str] = None

class PositionCreate(BaseModel):
    title: str

class BookingCreate(BaseModel):
    slot_id: str
    position_id: str
    name: str
    email: str
    phone: str

class BookingModify(BaseModel):
    booking_id: str
    slot_id: str
    position_id: str
    name: str
    email: str
    phone: str

class CancelBookingRequest(BaseModel):
    email: str
    position_id: Optional[str] = None

class CancelTokenRequest(BaseModel):
    token: str

class BookingUpdate(BaseModel):
    applicant_name: Optional[str] = None
    applicant_email: Optional[str] = None
    phone: Optional[str] = None
    position_id: Optional[str] = None
    status: Optional[str] = None
    slot_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    google_meet_link: Optional[str] = None

KEYWORD_RESTRICTED_POSITIONS = ["產品", "研發"]  #限定一個時段只有一個名額

def is_keyword_restricted_position(title: str) -> bool:
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in KEYWORD_RESTRICTED_POSITIONS)

def render_html_template(template: str, variables: dict) -> str:
    for key, value in variables.items():
        template = template.replace(f"{{{{{key}}}}}", str(value))
    return template


def build_confirmation_email(
        applicant_name: str,
        position_title: str,
        slot_date,
        start_time,
        end_time,
        cancel_token: str,
        subject_prefix: str = "面試預約確認",
        meet_link: str = "",
        applicant_email: str = "",
        applicant_phone: str = "",
) -> tuple[str, str]:
        """組裝確認信 subject 與 HTML body，回傳 (subject, html)。"""
        cancel_url = CANCEL_FORM_URL or "https://forms.gle/iuzrhmWH7XrzZSbX6"
        date_str = slot_date.strftime("%Y-%m-%d") if slot_date else ""
        start_str = start_time.strftime("%H:%M") if start_time else ""
        end_str = end_time.strftime("%H:%M") if end_time else ""

        if subject_prefix == "面試預約確認":
            subject = f"鼎霖視訊面試- {applicant_name}_{position_title}"
        else:
            subject = f"【{subject_prefix}】{applicant_name} — {date_str} {start_str}"

        try:
            template_path = BASE_DIR / "google_meet" / "templates" / "invite_email.html"
            template = template_path.read_text(encoding="utf-8")

            tz_offset = timezone(timedelta(hours=8))
            if slot_date and start_time:
                start_dt = datetime.combine(slot_date, start_time).replace(tzinfo=tz_offset)
            else:
                start_dt = datetime.now(tz_offset)
            if slot_date and end_time:
                end_dt = datetime.combine(slot_date, end_time).replace(tzinfo=tz_offset)
            else:
                end_dt = start_dt + timedelta(minutes=30)

            description_text = "若您有任何問題，歡迎在 104 留下訊息，或來電 0906-205-353。"
            cancel_button_html = f'<a href="{cancel_url}" class="cancel-btn">取消預約</a>'
            job_title_block = f"""
        <div class=\"info-row\">\n          <div class=\"label\">應徵職缺</div>\n          <div class=\"content-text\">{position_title}</div>\n        </div>""" if position_title else ""
            description_block = f"""
        <div class=\"info-row\">\n          <div class=\"label\">說明</div>\n          <div class=\"content-text\">{description_text}</div>\n        </div>"""

            # 應徵者聯絡資訊區塊
            applicant_info_block = ""
            if applicant_email or applicant_phone:
                info_items = []
                if applicant_email:
                    info_items.append(applicant_email)
                if applicant_phone:
                    info_items.append(applicant_phone)
                applicant_info_block = f"""
        <div class=\"info-row\">\n          <div class=\"label\">應徵者</div>\n          <div class=\"content-text\">{" · ".join(info_items)}</div>\n        </div>"""

            # 有 meet_link 才顯示加入會議按鈕；否則顯示提示文字
            if meet_link:
                meet_button_html = f'<a href="{meet_link}" class="btn">加入會議</a>'
            else:
                meet_button_html = '<p style="color:#64748b;font-size:13px;margin-top:8px;">Google Meet 會議連結將於面試前另行寄送，請留意信箱。</p>'

            variables = {
                "recipient_name": applicant_name,
                "recipient_role": "應聘者",
                "subject": subject,
                "start_str": start_dt.strftime("%Y年%m月%d日 %H:%M"),
                "end_str": end_dt.strftime("%H:%M"),
                "duration": int((end_dt - start_dt).seconds / 60),
                "meet_link": meet_link or "",
                "meet_button": meet_button_html,
                "description_block": description_block,
                "organizer_email": os.environ.get("GOOGLE_MEET_SENDER_EMAIL", "yukali58822@gmail.com"),
                "attendee_rows": "",
                "attendee_section": "",
                "job_title_block": job_title_block,
                "applicant_info_block": applicant_info_block,
                "cancel_section": cancel_button_html,
            }
            html = render_html_template(template, variables)
        except Exception:
            logger.exception("build_confirmation_email failed, falling back to plain HTML", exc_info=True)
            meeting_action = ""
            if meet_link:
                meeting_action = f"""
                <p>
                    <a href=\"{meet_link}\"
                         style=\"display:inline-block;padding:10px 24px;background:#2563eb;color:#fff;border-radius:6px;text-decoration:none;font-weight:bold;\">
                        加入會議
                    </a>
                </p>
                """
            html = f"""
            <div style=\"font-family:sans-serif;max-width:560px;margin:auto;color:#333;\">
                <h2 style=\"color:#2563eb;\">{subject_prefix}</h2>
                <p><b>{applicant_name}</b>，</p>
                <p>您的面試預約已成功確認，詳細資訊如下：</p>
                <table style=\"border-collapse:collapse;width:100%;margin:16px 0;\">
                    <tr><td style=\"padding:8px;border:1px solid #e5e7eb;background:#f9fafb;width:30%;\">應徵職缺</td>
                            <td style=\"padding:8px;border:1px solid #e5e7eb;\">{position_title}</td></tr>
                    <tr><td style=\"padding:8px;border:1px solid #e5e7eb;background:#f9fafb;\">面試日期</td>
                            <td style=\"padding:8px;border:1px solid #e5e7eb;\">{date_str}</td></tr>
                    <tr><td style=\"padding:8px;border:1px solid #e5e7eb;background:#f9fafb;\">面試時間</td>
                            <td style=\"padding:8px;border:1px solid #e5e7eb;\">{start_str} – {end_str}</td></tr>
                </table>
                {meeting_action}
                <p style=\"margin-top:24px;\">如需取消預約，請點擊下方按鈕：</p>
                <p>
                    <a href=\"{cancel_url}\"
                         style=\"display:inline-block;padding:10px 24px;background:#ef4444;\n                                        color:#fff;border-radius:6px;text-decoration:none;font-weight:bold;\">
                        取消預約
                    </a>
                </p>
                <p style=\"color:#6b7280;font-size:13px;margin-top:32px;\">
                    若您有任何問題，歡迎在 104 留下訊息，或來電 0906-205-353。
                </p>
            </div>
            """

        return subject, html

async def delete_old_google_event(event_id: str, sender_email: str = None):
    """
    刪除舊的 Google Calendar 事件（不通知參與者）
    
    Args:
        event_id: 要刪除的事件 ID
        sender_email: Google 帳號 Email（預設從環境變數取得）
    """
    if not event_id:
        return
    
    try:
        sender_email = sender_email or os.environ.get("GOOGLE_MEET_SENDER_EMAIL", "yukali58822@gmail.com")
        calendar = get_calendar_service(login_email=sender_email)
        delete_event(calendar, event_id, send_updates="none")  # 不通知參與者
        log_json(
            logging.INFO,
            "old_event.deleted",
            event_id=event_id,
            sender_email=sender_email,
        )
    except Exception as e:
        log_json(
            logging.WARNING,
            "old_event.delete_failed",
            event_id=event_id,
            error=str(e),
        )

async def send_event_cancellation_notification(
    applicant_name: str,
    applicant_email: str,
    position_title: str,
    slot_date,
    start_time,
    end_time,
    sender_email: str = None
):
    """
    寄送行程刪除通知給應徵者
    
    Args:
        applicant_name: 應徵者名字
        applicant_email: 應徵者 Email
        position_title: 職位名稱
        slot_date: 面試日期
        start_time: 開始時間
        end_time: 結束時間
        sender_email: 發起者 Email（發件人）
    """
    try:
        sender_email = sender_email or os.environ.get("GOOGLE_MEET_SENDER_EMAIL", "yukali58822@gmail.com")
        
        date_str = slot_date.strftime("%Y-%m-%d") if slot_date else ""
        start_str = start_time.strftime("%H:%M") if start_time else ""
        end_str = end_time.strftime("%H:%M") if end_time else ""
        
        subject = f"【面試行程取消】{applicant_name} — {date_str} {start_str}"
        html = f"""
        <div style="font-family:sans-serif;max-width:560px;margin:auto;color:#333;">
            <h2 style="color:#ef4444;">面試行程已取消</h2>
            <p>親愛的 <b>{applicant_name}</b>，</p>
            <p>很抱歉通知您，您的面試行程已被取消。詳細資訊如下：</p>
            <table style="border-collapse:collapse;width:100%;margin:16px 0;">
                <tr><td style="padding:8px;border:1px solid #e5e7eb;background:#f9fafb;width:30%;">應徵職缺</td>
                        <td style="padding:8px;border:1px solid #e5e7eb;">{position_title}</td></tr>
                <tr><td style="padding:8px;border:1px solid #e5e7eb;background:#f9fafb;">原定日期</td>
                        <td style="padding:8px;border:1px solid #e5e7eb;">{date_str}</td></tr>
                <tr><td style="padding:8px;border:1px solid #e5e7eb;background:#f9fafb;">原定時間</td>
                        <td style="padding:8px;border:1px solid #e5e7eb;">{start_str} – {end_str}</td></tr>
            </table>
            <p style="margin-top:24px;">若您有任何問題，歡迎在 104 留下訊息，或直接來電 0906-205-353。</p>
            <p style="color:#6b7280;font-size:13px;margin-top:32px;">
                感謝您的理解！
            </p>
        </div>
        """
        
        await _send(to=applicant_email, subject=subject, html=html)
        log_json(
            logging.INFO,
            "event_cancellation.email_sent",
            applicant_email=applicant_email,
            applicant_name=applicant_name,
        )
    except Exception as e:
        log_json(
            logging.WARNING,
            "event_cancellation.email_failed",
            applicant_email=applicant_email,
            applicant_name=applicant_name,
            error=str(e),
        )

async def complete_expired_confirmed_bookings(conn):
        # 先獲取所有即將過期的 confirmed 預約及其 google_event_id
        expired_bookings = await conn.fetch(
                """
                SELECT b.id, b.google_event_id
                FROM bookings b
                JOIN interview_slots s ON b.slot_id = s.id
                WHERE b.status = 'confirmed'
                    AND b.deleted_at IS NULL
                    AND (
                                s.slot_date + INTERVAL '1 day' < NOW()::date
                                OR (s.slot_date + INTERVAL '1 day' = NOW()::date AND s.end_time <= NOW()::time)
                            )
                """
        )
        
        # 刪除過期預約的 Google Calendar 事件
        for booking in expired_bookings:
            if booking.get("google_event_id"):
                try:
                    await delete_old_google_event(booking["google_event_id"])
                except Exception as e:
                    logger.exception(f"Failed to delete expired booking event {booking['id']}: {e}")
        
        # 更新狀態為 auto_completed
        await conn.execute(
                """
                UPDATE bookings b
                SET status='auto_completed', google_event_id=NULL
                FROM interview_slots s
                WHERE b.slot_id = s.id
                    AND b.status = 'confirmed'
                    AND b.deleted_at IS NULL
                    AND (
                                s.slot_date + INTERVAL '1 day' < NOW()::date
                                OR (s.slot_date + INTERVAL '1 day' = NOW()::date AND s.end_time <= NOW()::time)
                            )
                """
        )

async def log_slot_count_change(conn, slot_id, old_count, new_count, reason):
        if old_count == new_count:
                return
        note = f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] booked_count {old_count} -> {new_count} ({reason})"
        await conn.execute(
                """
                UPDATE interview_slots
                SET log_notes = CASE
                        WHEN log_notes IS NULL OR log_notes = '' THEN $1
                        ELSE log_notes || E'\n' || $1
                    END,
                    updated_at = NOW()
                WHERE id=$2
                """,
                note,
                slot_id
        )


async def get_interviewers_for_position(pool, position_id: str) -> list[dict]:
    """
    從數據庫取得該職位的面試官列表
    
    Returns:
        List of dicts with keys: name, email, role
    """
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT i.name, i.email, i.role
                FROM interviewers i
                JOIN position_interviewers pi ON pi.interviewer_id = i.id
                WHERE pi.position_id=$1 AND i.is_active=TRUE
                ORDER BY i.name
                """,
                uuid.UUID(position_id)
            )
            return [dict(r) for r in rows]
    except Exception as e:
        log_json(
            logging.WARNING,
            "get_interviewers_failed",
            position_id=position_id,
            error=str(e),
        )
        # 若無法從數據庫取得，返回預設的面試官
        return [{"name": "Alice 陳", "email": "yukali58820@gmail.com", "role": "面試官"}]


async def schedule_google_meet_for_booking(booking_id: str, delay_seconds: int =0):
    try:
        await asyncio.sleep(delay_seconds)
        pool = await get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT b.id, b.slot_id, b.position_id, a.id AS applicant_id, a.name AS applicant_name, a.email AS applicant_email,
                       a.phone AS applicant_phone,
                       p.title AS job_title, s.slot_date, s.start_time, s.end_time
                FROM bookings b
                JOIN applicants a ON a.id = b.applicant_id
                JOIN job_positions p ON p.id = b.position_id
                JOIN interview_slots s ON s.id = b.slot_id
                WHERE b.id=$1
                """,
                uuid.UUID(booking_id)
            )

        if not row:
            logger.warning(f"schedule_google_meet_for_booking: booking not found {booking_id}")
            return

        tz = timezone(timedelta(hours=8))
        start_dt = datetime.combine(row["slot_date"], row["start_time"]).replace(tzinfo=tz)
        end_dt = datetime.combine(row["slot_date"], row["end_time"]).replace(tzinfo=tz)

        # 獲取該職位的面試官列表
        interviewers = await get_interviewers_for_position(pool, str(row["position_id"]))
        
        log_json(
            logging.INFO,
            "schedule_google_meet.interviewers_fetched",
            booking_id=booking_id,
            position_id=str(row["position_id"]),
            interviewer_count=len(interviewers),
            interviewers=[{"name": i.get("name"), "email": i.get("email")} for i in interviewers],
        )

        script_path = str(BASE_DIR / "google_meet" / "main.py")
        sender_email = os.environ.get("GOOGLE_MEET_SENDER_EMAIL", "yukali58822@gmail.com")
        proc_args = [
            sys.executable,
            script_path,
            "--login_email",
            sender_email,
            "--applicant_name",
            str(row["applicant_name"]),
            "--applicant_email",
            str(row["applicant_email"]),
            "--applicant_phone",
            str(row["applicant_phone"] or ""),
            "--job_title",
            str(row["job_title"]),
            "--start_dt",
            start_dt.isoformat(),
            "--end_dt",
            end_dt.isoformat(),
            "--interviewers",
            json.dumps([{"name": i.get("name"), "email": i.get("email"), "role": i.get("role")} for i in interviewers]),
        ]

        result = await asyncio.to_thread(
            subprocess.run,
            proc_args,
            capture_output=True,
            text=True,
            check=False,
        )

        out = result.stdout or ""
        err = result.stderr or ""

        log_json(
            logging.INFO,
            "google_meet.subprocess_finished",
            booking_id=booking_id,
            returncode=result.returncode,
            stdout_preview=out[:2000],
            stderr_preview=err[:2000],
            command=proc_args,
        )

        event_id = None
        meet_link = None
        for line in out.splitlines():
            if line.startswith("EVENT_ID:"):
                event_id = line.split("EVENT_ID:", 1)[1].strip()
            if line.startswith("MEET_LINK:"):
                meet_link = line.split("MEET_LINK:", 1)[1].strip()

        log_json(
            logging.INFO,
            "google_meet.subprocess_parsed",
            booking_id=booking_id,
            event_id=event_id,
            meet_link=meet_link,
        )

        if event_id or meet_link:
            async with pool.acquire() as conn:
                booking_update_result = await conn.execute(
                    "UPDATE bookings SET google_event_id=$2, google_meet_link=$3 WHERE id=$1",
                    uuid.UUID(booking_id),
                    event_id,
                    meet_link,
                )
                slot_update_result = await conn.execute(
                    "UPDATE interview_slots SET google_event_id=$2, google_meet_link=$3, updated_at=NOW() WHERE id=$1",
                    row["slot_id"],
                    event_id,
                    meet_link,
                )
                applicant_update_result = await conn.execute(
                    "UPDATE applicants SET google_meet_link=$2, updated_at=NOW() WHERE id=$1",
                    row["applicant_id"],
                    meet_link,
                )

            log_json(
                logging.INFO,
                "google_meet.writeback_completed",
                booking_id=booking_id,
                booking_update_result=booking_update_result,
                slot_update_result=slot_update_result,
                applicant_update_result=applicant_update_result,
                event_id=event_id,
                meet_link=meet_link,
            )
        else:
            log_json(
                logging.ERROR,
                "google_meet.writeback_skipped",
                booking_id=booking_id,
                returncode=result.returncode,
                stdout_preview=out[:2000],
                stderr_preview=err[:2000],
            )

        # 無論 Google Meet 是否成功建立，都寄出確認信
        # 有 meet_link：顯示加入會議按鈕；無 meet_link：顯示「連結將另行寄送」提示
        if not meet_link:
            log_json(
                logging.ERROR,
                "google_meet.no_meet_link_send_fallback_email",
                booking_id=booking_id,
            )
        try:
            cancel_token, cancel_expires = generate_cancel_token()
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO email_logs (booking_id, recipient_email, email_type, status, cancel_token, cancel_token_expires_at) VALUES ($1, $2, $3, $4, $5, $6)",
                    uuid.UUID(booking_id),
                    row["applicant_email"],
                    'booking_confirm',
                    'pending',
                    cancel_token,
                    cancel_expires,
                )

            subject, html = build_confirmation_email(
                applicant_name=row["applicant_name"],
                position_title=row["job_title"],
                slot_date=row["slot_date"],
                start_time=row["start_time"],
                end_time=row["end_time"],
                cancel_token=cancel_token,
                meet_link=meet_link or "",
                applicant_email=row["applicant_email"],
                applicant_phone=row.get("applicant_phone") or "",
            )
            await _send(to=row["applicant_email"], subject=subject, html=html)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE email_logs SET status='sent', sent_at=NOW(), updated_at=NOW() WHERE booking_id=$1 AND email_type='booking_confirm' AND cancel_token=$2",
                    uuid.UUID(booking_id),
                    cancel_token,
                )
            
            # 記錄向面試官發送的 Google Calendar 邀請
            if interviewers:
                async with pool.acquire() as conn:
                    for interviewer in interviewers:
                        try:
                            await conn.execute(
                                "INSERT INTO email_logs (booking_id, recipient_email, email_type, status) VALUES ($1, $2, $3, $4)",
                                uuid.UUID(booking_id),
                                interviewer["email"],
                                'hr_notify',
                                'sent',  # Google Calendar API 已自動發送
                            )
                        except Exception as e:
                            logger.warning(f"Failed to log email for interviewer {interviewer['email']}: {e}")
        except Exception:
            logger.exception(f"Failed to send booking confirmation email for booking {booking_id}")


        if err:
            log_json(
                logging.ERROR,
                "google_meet.subprocess_stderr",
                booking_id=booking_id,
                stderr=err,
            )

        if not meet_link:
            log_json(
                logging.ERROR,
                "google_meet.no_meet_link",
                booking_id=booking_id,
                returncode=result.returncode,
                stdout=out,
                stderr=err,
                event_id=event_id,
                slot_id=str(row["slot_id"]),
            )

        async with pool.acquire() as conn:
            verify_row = await conn.fetchrow(
                """
                SELECT b.google_meet_link AS booking_meet_link,
                       b.google_event_id AS booking_event_id,
                       s.google_meet_link AS slot_meet_link,
                       s.google_event_id AS slot_event_id
                FROM bookings b
                JOIN interview_slots s ON s.id = b.slot_id
                WHERE b.id=$1
                """,
                uuid.UUID(booking_id),
            )

        if verify_row:
            log_json(
                logging.INFO,
                "meet_link.writeback_check",
                booking_id=booking_id,
                booking_meet_link=verify_row["booking_meet_link"],
                slot_meet_link=verify_row["slot_meet_link"],
                booking_event_id=verify_row["booking_event_id"],
                slot_event_id=verify_row["slot_event_id"],
                parsed_meet_link=meet_link,
                parsed_event_id=event_id,
                returncode=result.returncode,
            )

    except asyncio.CancelledError:
        logger.info(f"schedule_google_meet_for_booking cancelled for booking {booking_id}")
        return

    except Exception as e:
        logger.error(f"schedule_google_meet_for_booking error: {str(e)}", exc_info=True)


async def inspect_google_meet_link_state(booking_id: str, label: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT b.google_meet_link AS booking_meet_link,
                       b.google_event_id AS booking_event_id,
                       s.google_meet_link AS slot_meet_link,
                       s.google_event_id AS slot_event_id
                FROM bookings b
                JOIN interview_slots s ON s.id = b.slot_id
                WHERE b.id=$1
                """,
                uuid.UUID(booking_id),
            )

        if not row:
            logger.warning(f"{label}: booking not found {booking_id}")
            return

        log_json(
            logging.INFO,
            "meet_link.state",
            label=label,
            booking_id=booking_id,
            booking_meet_link=row["booking_meet_link"],
            slot_meet_link=row["slot_meet_link"],
            booking_event_id=row["booking_event_id"],
            slot_event_id=row["slot_event_id"],
        )
    except Exception:
        log_json(
            logging.ERROR,
            "meet_link.inspect_failed",
            label=label,
            booking_id=booking_id,
        )


async def delayed_inspect_google_meet_link_state(booking_id: str, delay_seconds: int, label: str):
    try:
        await asyncio.sleep(delay_seconds)
        await inspect_google_meet_link_state(booking_id, label)
    except asyncio.CancelledError:
        log_json(
            logging.INFO,
            "meet_link.delayed_inspection_cancelled",
            label=label,
            booking_id=booking_id,
            delay_seconds=delay_seconds,
        )
    except Exception:
        log_json(
            logging.ERROR,
            "meet_link.delayed_inspection_failed",
            label=label,
            booking_id=booking_id,
            delay_seconds=delay_seconds,
        )

# ─────────────────────────────────────────────
# PAGES
# ─────────────────────────────────────────────

async def get_current_hr_optional(
    access_token: Optional[str] = Cookie(default=None)
):
    if not access_token:
        return None

    try:
        payload = decode_token(access_token)
        return {
            "id": payload.get("sub"),
            "email": payload.get("email"),
            "role": payload.get("role"),
        }
    except HTTPException:
        return None

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


# 管理 API：由外部 cron/system 排程呼叫此 endpoint 來執行過期預約狀態更新
@app.post("/api/admin/complete-expired")
async def admin_complete_expired(request: Request):
    """
    受保護的管理端點。外部排程應在 HTTP 標頭 `X-ADMIN-TOKEN` 中帶入
    與環境變數 `ADMIN_CRON_TOKEN` 相同的值以驗證呼叫者。
    """
    token = os.environ.get("ADMIN_CRON_TOKEN")
    header = request.headers.get("X-ADMIN-TOKEN")
    if not token or header != token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await complete_expired_confirmed_bookings(conn)
        except Exception as e:
            logger.error(f"Admin complete-expired error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="執行過期預約更新失敗")

    return {"ok": True}

# 已登入則直接進後台
@app.get("/hr/login", response_class=HTMLResponse)
async def hr_login_page(
    request: Request,
    access_token: str = Cookie(None)
):

    if access_token:
        try:
            jwt.decode(
                access_token,
                SECRET_KEY,
                algorithms=["HS256"]
            )

            return RedirectResponse(
                url="/hr",
                status_code=302
            )

        except JWTError:
            pass

    return templates.TemplateResponse(
        "hr_login.html",
        {"request": request}
    )

# 必須登入才能進
@app.get("/hr", response_class=HTMLResponse)
async def hr_dashboard(
    request: Request,
    current=Depends(get_current_hr)
):
    return templates.TemplateResponse(
        "hr_dashboard.html",
        {
            "request": request,
            "current_user": current
        }
    )

# 必須登入才能進
@app.get("/hr/bookings", response_class=HTMLResponse)
async def hr_bookings_page(
    request: Request,
    current=Depends(get_current_hr)
):
    return templates.TemplateResponse(
        "hr_bookings.html",
        {
            "request": request,
            "current_user": current
        }
    )

@app.get("/cancel", response_class=HTMLResponse)
async def cancel_page(request: Request, t: str = ""):
    if t and CANCEL_FORM_URL:
        return RedirectResponse(CANCEL_FORM_URL)

    return templates.TemplateResponse(
        "cancel.html",
        {
            "request": request,
            "token": t,
            "cancel_form_url": CANCEL_FORM_URL,
        }
    )

# ─────────────────────────────────────────────
# AUTH API
# ─────────────────────────────────────────────

@app.post("/api/hr/login")
async def hr_login(
    email: str = Form(...),
    password: str = Form(...)
):
    try:

        pool = await get_pool()

        if pool is None:
            raise HTTPException(
                status_code=500,
                detail="資料庫連接失敗"
            )

        row = await pool.fetchrow(
            """
            SELECT *
            FROM hr_users
            WHERE email=$1
            AND is_active=TRUE
            """,
            email
        )

        if not row:
            raise HTTPException(
                status_code=401,
                detail="帳號或密碼錯誤"
            )

        if not verify_password(
            password,
            row["password_hash"]
        ):
            raise HTTPException(
                status_code=401,
                detail="帳號或密碼錯誤"
            )

        # 更新登入時間
        await pool.execute(
            """
            UPDATE hr_users
            SET last_login_at=NOW()
            WHERE id=$1
            """,
            row["id"]
        )

        # JWT
        token = create_access_token({
            "sub": str(row["id"]),
            "email": row["email"],
            "role": row["role"]
        })

        # Response
        resp = JSONResponse({
            "ok": True,
            "name": row["name"],
            "role": row["role"]
        })

        # Cookie
        resp.set_cookie(
            key="access_token",
            value=token,

            httponly=True,

            # localhost 開發先 False
            secure=False,

            samesite="lax",

            # 7天
            max_age=60 * 60 * 24 * 7
        )

        return resp

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            f"Login error: {str(e)}",
            exc_info=True
        )

        raise HTTPException(
            status_code=500,
            detail="登入失敗，請稍後重試"
        )

# 登出
@app.post("/api/hr/logout")
async def hr_logout():

    resp = JSONResponse({
        "ok": True
    })

    resp.delete_cookie("access_token")

    return resp

# 取得目前登入者
@app.get("/api/hr/me")
async def hr_me(
    current=Depends(get_current_hr)
):

    try:

        pool = await get_pool()

        row = await pool.fetchrow(
            """
            SELECT
                id,
                name,
                email,
                role
            FROM hr_users
            WHERE id=$1
            """,
            uuid.UUID(current["id"])
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail="使用者不存在"
            )

        return dict(row)

    except HTTPException:
        raise

    except Exception as e:

        logger.error(
            f"Get current user error: {str(e)}",
            exc_info=True
        )

        raise HTTPException(
            status_code=500,
            detail="取得使用者資訊失敗"
        )

# ─────────────────────────────────────────────
# SLOTS API
# ─────────────────────────────────────────────

@app.get("/api/slots")
async def get_slots(
    open_only: bool = False,
    current=Depends(get_current_hr_optional)
):
    try:
        pool = await get_pool()

        if open_only:
            rows = await pool.fetch(
                """
                SELECT
                    id,
                    slot_date,
                    start_time,
                    end_time,
                    max_capacity,
                    booked_count,
                    status,
                    google_meet_link,
                    notes
                FROM interview_slots
                WHERE status='open'
                ORDER BY slot_date ASC, start_time ASC
                """
            )
        else:
            if not current:
                raise HTTPException(status_code=401, detail="尚未登入")

            rows = await pool.fetch(
                """
                SELECT
                    id,
                    slot_date,
                    start_time,
                    end_time,
                    max_capacity,
                    booked_count,
                    status,
                    google_meet_link,
                    notes
                FROM interview_slots
                WHERE created_by=$1
                  AND status <> 'cancelled'
                ORDER BY slot_date DESC, start_time DESC
                """,
                uuid.UUID(current["id"])
            )
        
        return [dict(row) for row in rows]
    
    except Exception as e:
        logger.error(f"Get slots error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="取得時段失敗")

@app.post("/api/slots")
async def create_slot(
    payload: SlotCreate,
    current=Depends(get_current_hr)
):
    try:
        pool = await get_pool()
        
        # Convert string to date and time objects
        slot_date = datetime.strptime(payload.slot_date, "%Y-%m-%d").date()
        start_time = datetime.strptime(payload.start_time, "%H:%M").time()
        end_time = datetime.strptime(payload.end_time, "%H:%M").time()
        
        slot_id = await pool.fetchval(
            """
            INSERT INTO interview_slots
            (created_by, slot_date, start_time, end_time, max_capacity, status, google_meet_link, notes)
            VALUES ($1, $2, $3, $4, $5, 'open', $6, $7)
            RETURNING id
            """,
            uuid.UUID(current["id"]),
            slot_date,
            start_time,
            end_time,
            payload.max_capacity,
            payload.google_meet_link or None,
            payload.notes or None
        )
        
        return {
            "ok": True,
            "id": str(slot_id)
        }
    
    except Exception as e:
        logger.error(f"Create slot error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="新增時段失敗")

@app.patch("/api/slots/{slot_id}")
async def update_slot(
    slot_id: str,
    payload: SlotEdit,
    current=Depends(get_current_hr)
):
    try:
        pool = await get_pool()
        slot_uuid = uuid.UUID(slot_id)
        current_uuid = uuid.UUID(current["id"])

        existing = await pool.fetchrow(
            """
            SELECT booked_count, max_capacity, status
            FROM interview_slots
            WHERE id=$1 AND created_by=$2
            """,
            slot_uuid,
            current_uuid
        )

        if not existing:
            raise HTTPException(status_code=404, detail="時段不存在")

        updates = []
        values = []
        index = 1

        if payload.slot_date is not None:
            updates.append(f"slot_date=${index}")
            values.append(datetime.strptime(payload.slot_date, "%Y-%m-%d").date())
            index += 1

        if payload.start_time is not None:
            updates.append(f"start_time=${index}")
            try:
                values.append(time.fromisoformat(payload.start_time))
            except ValueError:
                values.append(datetime.strptime(payload.start_time, "%H:%M").time())
            index += 1

        if payload.end_time is not None:
            updates.append(f"end_time=${index}")
            try:
                values.append(time.fromisoformat(payload.end_time))
            except ValueError:
                values.append(datetime.strptime(payload.end_time, "%H:%M").time())
            index += 1

        if payload.max_capacity is not None:
            if payload.max_capacity < existing["booked_count"]:
                raise HTTPException(status_code=400, detail="名額上限不能小於已預約人數")
            updates.append(f"max_capacity=${index}")
            values.append(payload.max_capacity)
            index += 1

        if payload.status is not None:
            updates.append(f"status=${index}")
            values.append(payload.status)
            index += 1

        if payload.google_meet_link is not None:
            updates.append(f"google_meet_link=${index}")
            values.append(payload.google_meet_link or None)
            index += 1

        if payload.notes is not None:
            updates.append(f"notes=${index}")
            values.append(payload.notes or None)
            index += 1

        if not updates:
            return {"ok": True}

        if payload.status is None:
            final_capacity = payload.max_capacity if payload.max_capacity is not None else existing["max_capacity"]
            final_status = existing["status"]
            if final_status not in ("cancelled", "closed"):
                final_status = "full" if final_capacity <= existing["booked_count"] else "open"
            updates.append(f"status=${index}")
            values.append(final_status)
            index += 1

        values.extend([slot_uuid, current_uuid])

        await pool.execute(
            f"""
            UPDATE interview_slots
            SET {', '.join(updates)},
                updated_at = NOW()
            WHERE id=${index} AND created_by=${index + 1}
            """,
            *values
        )

        time_fields_changed = (
            payload.slot_date is not None or
            payload.start_time is not None or
            payload.end_time is not None
        )

        if time_fields_changed:
            async with pool.acquire() as conn:
                affected_bookings = await conn.fetch(
                    """
                    SELECT b.id AS booking_id,
                           b.google_event_id,
                           b.google_meet_link,
                           a.email AS applicant_email,
                           a.phone AS applicant_phone,
                           a.name AS applicant_name,
                           p.title AS position_title,
                           s.slot_date, s.start_time, s.end_time
                    FROM bookings b
                    JOIN applicants a ON a.id = b.applicant_id
                    JOIN job_positions p ON p.id = b.position_id
                    JOIN interview_slots s ON s.id = b.slot_id
                    WHERE b.slot_id = $1
                      AND b.status = 'confirmed'
                      AND b.deleted_at IS NULL
                    """,
                    slot_uuid
                )

                for bk in affected_bookings:
                    booking_id = bk["booking_id"]
                    recipient_email = bk["applicant_email"]

                    # 刪除舊的 Google Meet 事件
                    if bk.get("google_event_id"):
                        await delete_old_google_event(bk["google_event_id"])

                    cancel_token, cancel_expires = generate_cancel_token()

                    await conn.execute(
                        """
                        UPDATE email_logs
                        SET cancel_token = NULL,
                            cancel_token_expires_at = NULL,
                            updated_at = NOW()
                        WHERE booking_id = $1
                          AND email_type = 'booking_confirm'
                        """,
                        booking_id,
                    )

                    await conn.execute(
                        """
                        INSERT INTO email_logs
                        (booking_id, recipient_email, email_type, status,
                         cancel_token, cancel_token_expires_at)
                        VALUES ($1, $2, 'booking_confirm', 'pending', $3, $4)
                        """,
                        booking_id,
                        recipient_email,
                        cancel_token,
                        cancel_expires,
                    )

                    # 清除舊的 Google Meet 相關欄位
                    await conn.execute(
                        "UPDATE bookings SET google_event_id=NULL WHERE id=$1",
                        booking_id,
                    )

                    try:
                        subject, html = build_confirmation_email(
                            applicant_name=bk["applicant_name"],
                            position_title=bk["position_title"],
                            slot_date=bk["slot_date"],
                            start_time=bk["start_time"],
                            end_time=bk["end_time"],
                            cancel_token=cancel_token,
                            subject_prefix="面試時間異動確認",
                            meet_link=bk.get("google_meet_link") or "",
                            applicant_email=bk.get("applicant_email") or "",
                            applicant_phone=bk.get("applicant_phone") or "",
                        )
                        await _send(to=recipient_email, subject=subject, html=html)
                        await conn.execute(
                            """
                            UPDATE email_logs
                            SET status='sent',
                                sent_at=NOW(),
                                updated_at=NOW()
                            WHERE booking_id=$1 AND email_type='booking_confirm'
                              AND cancel_token=$2
                            """,
                            booking_id,
                            cancel_token,
                        )
                    except Exception:
                        logger.exception(
                            f"Failed to send reschedule email for booking {booking_id}"
                        )

        return {"ok": True}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Update slot error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="編輯時段失敗")

@app.get("/api/slots/{slot_id}/bookings")
async def get_slot_bookings(
    slot_id: str,
    current=Depends(get_current_hr)
):
    """取得特定面試時段的所有預約（包括應徵者名字和職務）"""
    try:
        pool = await get_pool()
        
        bookings = await pool.fetch(
            """
            SELECT
                b.id,
                a.name AS applicant_name,
                p.title AS position_title,
                b.status,
                b.booked_at
            FROM bookings b
            JOIN applicants a ON a.id = b.applicant_id
            JOIN job_positions p ON p.id = b.position_id
            WHERE b.slot_id = $1
              AND b.deleted_at IS NULL
            ORDER BY b.booked_at ASC
            """,
            uuid.UUID(slot_id)
        )
        
        return [dict(row) for row in bookings]
    
    except Exception as e:
        logger.error(f"Get slot bookings error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="取得預約失敗")

@app.delete("/api/slots/{slot_id}")
async def delete_slot(
    slot_id: str,
    current=Depends(get_current_hr)
):
    try:
        pool = await get_pool()

        result = await pool.execute(
            """
            UPDATE interview_slots
            SET status='cancelled',
                updated_at=NOW()
            WHERE id=$1 AND created_by=$2
            """,
            uuid.UUID(slot_id),
            uuid.UUID(current["id"])
        )

        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="時段不存在")

        return {"ok": True}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Delete slot error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="刪除時段失敗")

@app.patch("/api/slots/{slot_id}/close")
async def close_slot(
    slot_id: str,
    current=Depends(get_current_hr)
):
    try:
        pool = await get_pool()
        
        await pool.execute(
            """
            UPDATE interview_slots
            SET status='closed'
            WHERE id=$1 AND created_by=$2
            """,
            uuid.UUID(slot_id),
            uuid.UUID(current["id"])
        )
         
        return {"ok": True}
    
    except Exception as e:
        logger.error(f"Close slot error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="關閉時段失敗")

# ─────────────────────────────────────────────
# POSITIONS API
# ─────────────────────────────────────────────

@app.get("/api/positions")
async def get_positions(
    active_only: bool = True,
    current=Depends(get_current_hr_optional)
):
    try:
        pool = await get_pool()
        
        if active_only:
            rows = await pool.fetch(
                """
                SELECT id, title, is_active
                FROM job_positions
                WHERE is_active=TRUE
                ORDER BY created_at DESC
                """
            )
        else:
            if not current:
                raise HTTPException(status_code=401, detail="尚未登入")

            rows = await pool.fetch(
                """
                SELECT id, title, is_active
                FROM job_positions
                ORDER BY created_at DESC
                """
            )
        
        return [dict(row) for row in rows]
    
    except Exception as e:
        logger.error(f"Get positions error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="取得職缺失敗")

@app.post("/api/positions")
async def create_position(
    payload: PositionCreate,
    current=Depends(get_current_hr)
):
    try:
        pool = await get_pool()
        
        position_id = await pool.fetchval(
            """
            INSERT INTO job_positions (title, created_by)
            VALUES ($1, $2)
            RETURNING id
            """,
            payload.title,
            uuid.UUID(current["id"])
        )
        
        return {
            "ok": True,
            "id": str(position_id),
            "title": payload.title
        }
    
    except Exception as e:
        logger.error(f"Create position error: {str(e)}", exc_info=True)
        if "duplicate key" in str(e):
            raise HTTPException(status_code=400, detail="職缺已存在")
        raise HTTPException(status_code=500, detail="新增職缺失敗")

@app.delete("/api/positions/{position_id}")
async def delete_position(
    position_id: str,
    current=Depends(get_current_hr)
):
    try:
        pool = await get_pool()
        pos_uuid = uuid.UUID(position_id)
        
        # 檢查是否有未確認的預約（即將進行面試的預約）
        active_booking_count = await pool.fetchval(
            """
            SELECT COUNT(*)
            FROM bookings
            WHERE position_id=$1 AND status IN ('confirmed') AND deleted_at IS NULL
            """,
            pos_uuid
        )
        
        if active_booking_count and active_booking_count > 0:
            # 有待進行的預約，提示用戶先取消
            raise HTTPException(
                status_code=400, 
                detail=f"此職缺有 {active_booking_count} 個待進行的預約，無法直接刪除。請先取消相關預約，再進行刪除操作。"
            )
        
        # 刪除相關的預約記錄（軟刪除）
        # 刪除相關的預約記錄（改為硬刪除以避免外鍵限制阻止職缺刪除）
        await pool.execute(
            """
            DELETE FROM bookings
            WHERE position_id=$1
            """,
            pos_uuid
        )
        
        # 刪除職缺
        result = await pool.execute(
            """
            DELETE FROM job_positions
            WHERE id=$1
            """,
            pos_uuid
        )
        
        if "0" in str(result):
            raise HTTPException(status_code=404, detail="職缺不存在")
        
        return {"ok": True, "message": "職缺及相關預約已成功刪除"}
    
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Delete position error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="刪除職缺失敗")

@app.patch("/api/positions/{position_id}")
async def update_position(
    position_id: str,
    payload: PositionCreate,
    current=Depends(get_current_hr)
):
    try:
        pool = await get_pool()
        
        await pool.execute(
            """
            UPDATE job_positions
            SET title=$1,
                updated_at=NOW()
            WHERE id=$2
            """,
            payload.title,
            uuid.UUID(position_id)
        )

        return {"ok": True}

    except Exception as e:
        logger.error(f"Update position error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="編輯職缺失敗")

@app.patch("/api/positions/{position_id}/visibility")
async def toggle_position_visibility(
    position_id: str,
    current=Depends(get_current_hr)
):
    try:
        pool = await get_pool()
        
        await pool.execute(
            """
            UPDATE job_positions
            SET is_active = NOT is_active,
                updated_at = NOW()
            WHERE id=$1
            """,
            uuid.UUID(position_id)
        )

        return {"ok": True}

    except Exception as e:
        logger.error(f"Toggle position visibility error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新職缺顯示狀態失敗")

# ─────────────────────────────────────────────
# INTERVIEWERS API - 面試官管理
# ─────────────────────────────────────────────

@app.get("/api/interviewers")
async def get_interviewers(current=Depends(get_current_hr)):
    """取得所有面試官列表"""
    try:
        pool = await get_pool()
        
        rows = await pool.fetch(
            """
            SELECT i.id, i.name, i.email, i.role, i.is_active, 
                   COUNT(pi.id) as position_count
            FROM interviewers i
            LEFT JOIN position_interviewers pi ON pi.interviewer_id = i.id
            GROUP BY i.id
            ORDER BY i.name
            """
        )
        
        return [dict(r) for r in rows]
    
    except Exception as e:
        logger.error(f"Get interviewers error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="取得面試官列表失敗")


@app.get("/api/positions/{position_id}/interviewers")
async def get_position_interviewers(
    position_id: str,
    current=Depends(get_current_hr)
):
    """取得職位的面試官列表"""
    try:
        pool = await get_pool()
        
        rows = await pool.fetch(
            """
            SELECT i.id, i.name, i.email, i.role
            FROM interviewers i
            JOIN position_interviewers pi ON pi.interviewer_id = i.id
            WHERE pi.position_id=$1 AND i.is_active=TRUE
            ORDER BY i.name
            """,
            uuid.UUID(position_id)
        )
        
        return [dict(r) for r in rows]
    
    except Exception as e:
        logger.error(f"Get position interviewers error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="取得職位面試官列表失敗")


@app.post("/api/positions/{position_id}/interviewers/{interviewer_id}")
async def add_interviewer_to_position(
    position_id: str,
    interviewer_id: str,
    current=Depends(get_current_hr)
):
    """將面試官新增到職位"""
    try:
        pool = await get_pool()
        
        # 確保職位存在
        position_exists = await pool.fetchval(
            "SELECT id FROM job_positions WHERE id=$1",
            uuid.UUID(position_id)
        )
        if not position_exists:
            raise HTTPException(status_code=404, detail="職位不存在")
        
        # 確保面試官存在
        interviewer_exists = await pool.fetchval(
            "SELECT id FROM interviewers WHERE id=$1",
            uuid.UUID(interviewer_id)
        )
        if not interviewer_exists:
            raise HTTPException(status_code=404, detail="面試官不存在")
        
        # 新增關聯
        await pool.execute(
            """
            INSERT INTO position_interviewers (position_id, interviewer_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            uuid.UUID(position_id),
            uuid.UUID(interviewer_id)
        )
        
        return {"ok": True, "message": "面試官已新增到職位"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add interviewer error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="新增面試官失敗")


@app.delete("/api/positions/{position_id}/interviewers/{interviewer_id}")
async def remove_interviewer_from_position(
    position_id: str,
    interviewer_id: str,
    current=Depends(get_current_hr)
):
    """將面試官從職位移除"""
    try:
        pool = await get_pool()
        
        result = await pool.execute(
            """
            DELETE FROM position_interviewers
            WHERE position_id=$1 AND interviewer_id=$2
            """,
            uuid.UUID(position_id),
            uuid.UUID(interviewer_id)
        )
        
        return {"ok": True, "message": "面試官已從職位移除"}
    
    except Exception as e:
        logger.error(f"Remove interviewer error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="移除面試官失敗")


@app.post("/api/book")
async def create_booking(payload: BookingCreate):
    try:
        pool = await get_pool()

        slot_uuid = uuid.UUID(payload.slot_id)
        position_uuid = uuid.UUID(payload.position_id)

        async with pool.acquire() as conn:
            async with conn.transaction():
                await complete_expired_confirmed_bookings(conn)
                slot = await conn.fetchrow(
                    """
                    SELECT id, slot_date, start_time, end_time, max_capacity, booked_count, status
                    FROM interview_slots
                    WHERE id=$1
                    """,
                    slot_uuid
                )

                if not slot or slot["status"] != "open":
                    raise HTTPException(status_code=400, detail="所選時段不可預約")

                position = await conn.fetchrow(
                    """
                    SELECT id, title
                    FROM job_positions
                    WHERE id=$1 AND is_active=TRUE
                    """,
                    position_uuid
                )

                if not position:
                    raise HTTPException(status_code=400, detail="所選職缺不可用")

                keyword_restricted = is_keyword_restricted_position(position["title"])

                existing_booking = await conn.fetchrow(
                    """
                    SELECT b.id,
                           b.booked_at,
                           p.title AS position_title,
                           s.slot_date,
                           s.start_time,
                           s.end_time,
                           a.email
                    FROM bookings b
                    JOIN applicants a ON a.id = b.applicant_id
                    JOIN job_positions p ON p.id = b.position_id
                    JOIN interview_slots s ON s.id = b.slot_id
                    WHERE LOWER(a.email)=LOWER($1)
                      AND b.status='confirmed'
                      AND b.deleted_at IS NULL
                    ORDER BY b.booked_at DESC
                    LIMIT 1
                    """,
                    payload.email
                )

                if existing_booking:
                    last_booked = existing_booking["booked_at"]
                    if last_booked is not None:
                        next_allowed = last_booked.date() + timedelta(days=30)
                        if date.today() < next_allowed:
                            raise HTTPException(
                                status_code=400,
                                detail={
                                    "message": f"你已於{last_booked.date()}預約過，請於{next_allowed}再次預約，或按「確認修改原預約」修改現有預約。",
                                    "code": "duplicate_confirmed_booking",
                                    "booking_id": str(existing_booking["id"]),
                                    "position_title": existing_booking["position_title"],
                                    "slot_date": str(existing_booking["slot_date"]),
                                    "start_time": str(existing_booking["start_time"]),
                                    "end_time": str(existing_booking["end_time"]),
                                    "email": existing_booking["email"]
                                }
                            )

                completed_booking = await conn.fetchrow(
                    """
                    SELECT b.id,
                           p.title AS position_title,
                           s.slot_date,
                           s.start_time,
                           s.end_time,
                           a.email
                    FROM bookings b
                    JOIN applicants a ON a.id = b.applicant_id
                    JOIN job_positions p ON p.id = b.position_id
                    JOIN interview_slots s ON s.id = b.slot_id
                    WHERE LOWER(a.email)=LOWER($1)
                      AND b.status='auto_completed'
                      AND b.deleted_at IS NULL
                      AND s.slot_date >= NOW()::date - INTERVAL '30 days'
                    ORDER BY s.slot_date DESC
                    LIMIT 1
                    """,
                    payload.email
                )

                if completed_booking:
                    last_completed = completed_booking["slot_date"]
                    next_allowed = last_completed + timedelta(days=30)
                    if date.today() < next_allowed:
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "message": f"您於{last_completed}完成的預約須在{next_allowed}之後才能再次預約。",
                                "code": "recent_auto_completed_booking",
                                "booking_id": str(completed_booking["id"]),
                                "position_title": completed_booking["position_title"],
                                "slot_date": str(completed_booking["slot_date"]),
                                "start_time": str(completed_booking["start_time"]),
                                "end_time": str(completed_booking["end_time"]),
                                "email": completed_booking["email"]
                            }
                        )

                if keyword_restricted:
                    existing_booking_count = await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM bookings
                        WHERE slot_id=$1
                          AND status='confirmed'
                          AND deleted_at IS NULL
                        """,
                        slot_uuid
                    )
                    if existing_booking_count and existing_booking_count > 0:
                        raise HTTPException(
                            status_code=400,
                            detail="此時段已被特殊職務預約，該時段僅保留一個名額"
                        )

                else:
                    restricted_slot_count = await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM bookings b
                        JOIN job_positions p ON p.id = b.position_id
                        WHERE b.slot_id=$1
                          AND b.status='confirmed'
                          AND b.deleted_at IS NULL
                          AND (
                                LOWER(p.title) LIKE '%產品%'
                             OR LOWER(p.title) LIKE '%研發%'
                          )
                        """,
                        slot_uuid
                    )
                    if restricted_slot_count and restricted_slot_count > 0:
                        raise HTTPException(
                            status_code=400,
                            detail="此時段已由產品/研發職務預約，無法再加入其他人"
                        )

                applicant_id = await conn.fetchval(
                    """
                    INSERT INTO applicants (name, email, phone)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (email) DO UPDATE
                    SET name=EXCLUDED.name,
                        phone=EXCLUDED.phone
                    RETURNING id
                    """,
                    payload.name,
                    payload.email,
                    payload.phone
                )

                booking_id = await conn.fetchval(
                    """
                    INSERT INTO bookings (slot_id, applicant_id, position_id, status)
                    VALUES ($1, $2, $3, 'confirmed')
                    RETURNING id
                    """,
                    slot_uuid,
                    applicant_id,
                    position_uuid
                )

                new_booked_count = slot["booked_count"] + 1
                if keyword_restricted:
                    new_status = "full"
                else:
                    new_status = "full" if new_booked_count >= slot["max_capacity"] else "open"

                await conn.execute(
                    """
                    UPDATE interview_slots
                    SET booked_count=$2,
                        status=$3,
                        updated_at=NOW()
                    WHERE id=$1
                    """,
                    slot_uuid,
                    new_booked_count,
                    new_status
                )

                await log_slot_count_change(conn, slot_uuid, slot["booked_count"], new_booked_count, "new confirmed booking")

        # 先建立 Google Meet 會議並寫回 DB，確認信會在建立成功後由 schedule_google_meet_for_booking 發出。
        try:
            await schedule_google_meet_for_booking(str(booking_id), delay_seconds=0)
        except Exception:
            logger.exception(f"Failed to create google meet for booking {booking_id}")

        return {"ok": True, "booking_id": str(booking_id), "message": "預約成功，稍後將收到包含會議連結的信件。"}

    except HTTPException:
        raise

    except UniqueViolationError as e:
        logger.error(f"Create booking unique violation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="您已預約過，若要修改預約時間，請先取消預約"
        )

    except Exception as e:
        logger.error(f"Create booking error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="預約失敗")

@app.post("/api/bookings/modify")
async def modify_booking(payload: BookingModify, background_tasks: BackgroundTasks):
    try:
        pool = await get_pool()

        booking_uuid = uuid.UUID(payload.booking_id)
        slot_uuid = uuid.UUID(payload.slot_id)
        position_uuid = uuid.UUID(payload.position_id)

        async with pool.acquire() as conn:
            async with conn.transaction():
                await complete_expired_confirmed_bookings(conn)
                booking = await conn.fetchrow(
                    """
                    SELECT b.id, b.slot_id, b.position_id, b.status, b.deleted_at, b.google_event_id, a.id AS applicant_id
                    FROM bookings b
                    JOIN applicants a ON a.id = b.applicant_id
                    WHERE b.id=$1
                      AND b.status='confirmed'
                      AND b.deleted_at IS NULL
                    """,
                    booking_uuid
                )

                if not booking:
                    raise HTTPException(status_code=404, detail="找不到可修改的預約")

                slot = await conn.fetchrow(
                    """
                    SELECT id, slot_date, start_time, end_time, max_capacity, booked_count, status
                    FROM interview_slots
                    WHERE id=$1
                    """,
                    slot_uuid
                )

                if not slot or slot["status"] != "open":
                    raise HTTPException(status_code=400, detail="所選時段不可預約")

                position = await conn.fetchrow(
                    """
                    SELECT id, title
                    FROM job_positions
                    WHERE id=$1 AND is_active=TRUE
                    """,
                    position_uuid
                )

                if not position:
                    raise HTTPException(status_code=400, detail="所選職缺不可用")

                keyword_restricted = is_keyword_restricted_position(position["title"])

                if keyword_restricted:
                    existing_booking_count = await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM bookings
                        WHERE slot_id=$1
                          AND status='confirmed'
                          AND deleted_at IS NULL
                          AND id <> $2
                        """,
                        slot_uuid,
                        booking_uuid
                    )
                    if existing_booking_count and existing_booking_count > 0:
                        raise HTTPException(
                            status_code=400,
                            detail="此時段已被特殊職務預約，該時段僅保留一個名額"
                        )
                else:
                    restricted_slot_count = await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM bookings b
                        JOIN job_positions p ON p.id = b.position_id
                        WHERE b.slot_id=$1
                          AND b.status='confirmed'
                          AND b.deleted_at IS NULL
                          AND b.id <> $2
                          AND (
                                LOWER(p.title) LIKE '%產品%'
                             OR LOWER(p.title) LIKE '%研發%'
                          )
                        """,
                        slot_uuid,
                        booking_uuid
                    )
                    if restricted_slot_count and restricted_slot_count > 0:
                        raise HTTPException(
                            status_code=400,
                            detail="此時段已由產品/研發職務預約，無法再加入其他人"
                        )

                if booking["slot_id"] != slot_uuid:
                    # 刪除舊的 Google Calendar 事件
                    if booking.get("google_event_id"):
                        await delete_old_google_event(booking["google_event_id"])
                    
                    old_slot = await conn.fetchrow(
                        """
                        SELECT id, booked_count, max_capacity, status
                        FROM interview_slots
                        WHERE id=$1
                        """,
                        booking["slot_id"]
                    )

                    old_booked_count = max((old_slot["booked_count"] or 0) - 1, 0)
                    old_status = old_slot["status"]
                    if old_status not in ("cancelled", "closed"):
                        old_status = "open" if old_booked_count < old_slot["max_capacity"] else "full"

                    await conn.execute(
                        """
                        UPDATE interview_slots
                        SET booked_count=$2,
                            status=$3,
                            updated_at=NOW()
                        WHERE id=$1
                        """,
                        booking["slot_id"],
                        old_booked_count,
                        old_status
                    )

                    await log_slot_count_change(conn, booking["slot_id"], old_slot["booked_count"], old_booked_count, "booking moved away")

                    new_booked_count = slot["booked_count"] + 1
                    if keyword_restricted:
                        new_status = "full"
                    else:
                        new_status = "full" if new_booked_count >= slot["max_capacity"] else "open"

                    await conn.execute(
                        """
                        UPDATE interview_slots
                        SET booked_count=$2,
                            status=$3,
                            updated_at=NOW()
                        WHERE id=$1
                        """,
                        slot_uuid,
                        new_booked_count,
                        new_status
                    )

                    await log_slot_count_change(conn, slot_uuid, slot["booked_count"], new_booked_count, "booking moved in")
                else:
                    new_booked_count = slot["booked_count"]
                    if keyword_restricted:
                        new_status = "full"
                    else:
                        new_status = "full" if new_booked_count >= slot["max_capacity"] else "open"

                    await conn.execute(
                        """
                        UPDATE interview_slots
                        SET status=$2,
                            updated_at=NOW()
                        WHERE id=$1
                        """,
                        slot_uuid,
                        new_status
                    )

                await conn.execute(
                    """
                    UPDATE applicants
                    SET name=$1,
                        email=$2,
                        phone=$3
                    WHERE id=$4
                    """,
                    payload.name,
                    payload.email,
                    payload.phone,
                    booking["applicant_id"]
                )

                await conn.execute(
                    """
                    UPDATE bookings
                    SET slot_id=$1,
                        position_id=$2
                    WHERE id=$3
                    """,
                    slot_uuid,
                    position_uuid,
                    booking_uuid
                )

                # 不論是否變更時段，都重新產生取消 token 並寄送更新確認信；
                # 若時段變動則額外排程 Google Meet 重建
                try:
                    cancel_token, cancel_expires = generate_cancel_token()

                    await conn.execute(
                        """
                        UPDATE email_logs
                        SET cancel_token = NULL,
                            cancel_token_expires_at = NULL
                        WHERE booking_id = $1
                          AND email_type = 'booking_confirm'
                        """,
                        booking_uuid,
                    )

                    await conn.execute(
                        """
                        INSERT INTO email_logs
                        (booking_id, recipient_email, email_type, status,
                         cancel_token, cancel_token_expires_at)
                        VALUES ($1, $2, 'booking_confirm', 'pending', $3, $4)
                        """,
                        booking_uuid,
                        payload.email,
                        cancel_token,
                        cancel_expires,
                    )

                    try:
                        subject_prefix = "面試時間異動確認" if booking["slot_id"] != slot_uuid else "預約資料更新確認"
                        subject, html = build_confirmation_email(
                            applicant_name=payload.name,
                            position_title=position["title"],
                            slot_date=slot["slot_date"],
                            start_time=slot["start_time"],
                            end_time=slot["end_time"],
                            cancel_token=cancel_token,
                            subject_prefix=subject_prefix,
                            applicant_email=payload.email,
                            applicant_phone=payload.phone or "",
                        )
                        await _send(to=payload.email, subject=subject, html=html)
                        await conn.execute(
                            """
                            UPDATE email_logs
                            SET status='sent',
                                sent_at=NOW()
                            WHERE booking_id=$1 AND email_type='booking_confirm'
                              AND cancel_token=$2
                            """,
                            booking_uuid,
                            cancel_token,
                        )
                    except Exception:
                        logger.exception(f"Failed to send update email for booking {booking_uuid}")

                    # 若時段變動，排程 Google Meet
                    if booking["slot_id"] != slot_uuid:
                        try:
                            background_tasks.add_task(
                                schedule_google_meet_for_booking,
                                str(booking_uuid),
                                10,
                            )
                        except Exception:
                            logger.exception(f"Failed to reschedule google meet for booking {booking_uuid}")

                except Exception:
                    logger.exception(f"Failed to create email log for modified booking {booking_uuid}")

        return {"ok": True}

    except HTTPException:
        raise

    except UniqueViolationError as e:
        logger.error(f"Modify booking unique violation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail="該 Email 已被其他使用者使用，請改用不同 Email。")

    except Exception as e:
        logger.error(f"Modify booking error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="修改預約失敗")

@app.get("/api/bookings/by-email")
async def get_booking_by_email(email: str):
    try:
        pool = await get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT b.id AS booking_id
                FROM bookings b
                JOIN applicants a ON a.id = b.applicant_id
                WHERE LOWER(a.email)=LOWER($1)
                  AND b.status='confirmed'
                  AND b.deleted_at IS NULL
                ORDER BY b.booked_at DESC
                LIMIT 1
                """,
                email,
            )

        if not row:
            raise HTTPException(status_code=404, detail="找不到預約紀錄")

        return {"booking_id": str(row["booking_id"])}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Get booking by email error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="查詢預約紀錄失敗")

@app.post("/api/bookings/cancel-existing")
async def cancel_existing_booking(payload: CancelBookingRequest):
    try:
        pool = await get_pool()

        async with pool.acquire() as conn:
            async with conn.transaction():
                await complete_expired_confirmed_bookings(conn)
                bookings = await conn.fetch(
                    """
                    SELECT
                        b.id,
                        b.slot_id,
                        b.google_event_id,
                        a.name AS applicant_name,
                        a.email AS applicant_email,
                        p.title AS position_title,
                        s.slot_date, s.start_time, s.end_time,
                        s.booked_count,
                        s.max_capacity,
                        s.status
                    FROM bookings b
                    JOIN applicants a ON a.id = b.applicant_id
                    JOIN job_positions p ON p.id = b.position_id
                    JOIN interview_slots s ON s.id = b.slot_id
                    WHERE LOWER(a.email)=LOWER($1)
                      AND b.status='confirmed'
                      AND b.deleted_at IS NULL
                    ORDER BY b.booked_at DESC
                    """,
                    payload.email
                )

                if not bookings:
                    raise HTTPException(status_code=404, detail="找不到可取消的預約")

                for booking in bookings:
                    # 刪除 Google Calendar 事件
                    if booking.get("google_event_id"):
                        await delete_old_google_event(booking["google_event_id"])

                    await conn.execute(
                        """
                        UPDATE bookings
                        SET status='cancelled',
                            cancelled_by='applicant',
                            cancelled_at=NOW(),
                            google_event_id=NULL
                        WHERE id=$1
                        """,
                        booking["id"]
                    )

                    new_booked_count = max((booking["booked_count"] or 0) - 1, 0)
                    new_status = booking["status"]
                    if new_status not in ("cancelled", "closed"):
                        new_status = "open" if new_booked_count < booking["max_capacity"] else "full"

                    await conn.execute(
                        """
                        UPDATE interview_slots
                        SET booked_count=$2,
                            status=$3,
                            updated_at=NOW()
                        WHERE id=$1
                        """,
                        booking["slot_id"],
                        new_booked_count,
                        new_status
                    )

                    await log_slot_count_change(conn, booking["slot_id"], booking["booked_count"], new_booked_count, "booking cancelled")
                
                # 交易外發送取消通知（避免超時）
                for booking in bookings:
                    try:
                        await send_event_cancellation_notification(
                            applicant_name=booking["applicant_name"],
                            applicant_email=booking["applicant_email"],
                            position_title=booking["position_title"],
                            slot_date=booking["slot_date"],
                            start_time=booking["start_time"],
                            end_time=booking["end_time"],
                        )
                    except Exception:
                        logger.exception(f"Failed to send cancellation notification for {booking['applicant_email']}")

        return {"ok": True}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Cancel existing booking error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="取消預約失敗")

@app.post("/api/cancel")
async def cancel_booking(payload: CancelTokenRequest):
    """
    應徵者通過郵件中的 cancel_token 取消預約
    """
    try:
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                await complete_expired_confirmed_bookings(conn)
                # 驗證 cancel_token 是否有效
                email_log = await conn.fetchrow(
                    """
                    SELECT 
                        el.booking_id,
                        el.recipient_email,
                        el.cancel_token_expires_at,
                        el.cancel_token_used_at,
                        b.id AS booking_id_check,
                        b.status AS booking_status,
                        b.google_event_id,
                        a.name AS applicant_name,
                        p.title AS position_title,
                        s.slot_date, s.start_time, s.end_time
                    FROM email_logs el
                    JOIN bookings b ON b.id = el.booking_id
                    JOIN applicants a ON a.id = b.applicant_id
                    JOIN job_positions p ON p.id = b.position_id
                    JOIN interview_slots s ON s.id = b.slot_id
                    WHERE el.cancel_token=$1 
                      AND el.cancel_token IS NOT NULL
                    """,
                    payload.token
                )

                if not email_log:
                    raise HTTPException(status_code=404, detail="無效的取消連結")

                # 檢查 token 是否已過期
                if email_log["cancel_token_expires_at"] < datetime.utcnow():
                    raise HTTPException(status_code=410, detail="取消連結已過期（7天內有效）")

                # 檢查 token 是否已使用
                if email_log["cancel_token_used_at"] is not None:
                    raise HTTPException(status_code=400, detail="此預約已取消")

                # 檢查預約狀態
                if email_log["booking_status"] != "confirmed":
                    raise HTTPException(status_code=400, detail="只能取消確認中的預約")

                booking_id = email_log["booking_id"]

                # 獲取預約的 slot_id 以更新 booked_count
                booking = await conn.fetchrow(
                    """
                    SELECT slot_id, applicant_id
                    FROM bookings
                    WHERE id=$1
                    """,
                    booking_id
                )

                # 刪除 Google Calendar 事件
                if email_log.get("google_event_id"):
                    await delete_old_google_event(email_log["google_event_id"])

                # 更新預約狀態為 cancelled（不soft delete，保留在列表中）
                await conn.execute(
                    """
                    UPDATE bookings
                    SET status='cancelled',
                        cancelled_by='applicant',
                        cancelled_at=NOW(),
                        google_event_id=NULL
                    WHERE id=$1
                    """,
                    booking_id
                )
                
                # 更新 email_logs 標記 token 已使用
                await conn.execute(
                    """
                    UPDATE email_logs
                    SET cancel_token_used_at=NOW(),
                        status='sent'
                    WHERE booking_id=$1 AND email_type='booking_confirm'
                    """,
                    booking_id
                )
                
                # 更新 interview_slots 的 booked_count
                slot = await conn.fetchrow(
                    """
                    SELECT max_capacity, booked_count, status
                    FROM interview_slots
                    WHERE id=$1
                    """,
                    booking["slot_id"]
                )
                
                if slot:
                    new_booked_count = max((slot["booked_count"] or 0) - 1, 0)
                    new_status = slot["status"]
                    if new_status not in ("cancelled", "closed"):
                        new_status = "open" if new_booked_count < slot["max_capacity"] else "full"
                    
                    await conn.execute(
                        """
                        UPDATE interview_slots
                        SET booked_count=$2,
                            status=$3,
                            updated_at=NOW()
                        WHERE id=$1
                        """,
                        booking["slot_id"],
                        new_booked_count,
                        new_status
                    )

                    await log_slot_count_change(conn, booking["slot_id"], slot["booked_count"], new_booked_count, "booking cancelled")
        
        # 發送取消確認郵件給應徵者（交易外執行以避免超時）
        try:
            await send_event_cancellation_notification(
                applicant_name=email_log["applicant_name"],
                applicant_email=email_log["recipient_email"],
                position_title=email_log["position_title"],
                slot_date=email_log["slot_date"],
                start_time=email_log["start_time"],
                end_time=email_log["end_time"],
            )
        except Exception:
            logger.exception(f"Failed to send cancellation notification")
        
        return {"ok": True, "status": "cancelled"}

    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Cancel booking error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="取消預約失敗")

# ─────────────────────────────────────────────
# BOOKINGS API
# ─────────────────────────────────────────────

@app.get("/api/booking-edit-options")
async def get_booking_edit_options(current=Depends(get_current_hr)):
    try:
        pool = await get_pool()
        
        # 獲取所有活躍職缺
        positions = await pool.fetch(
            "SELECT id, title FROM job_positions WHERE is_active=TRUE ORDER BY title"
        )
        
        # 獲取所有可用的面試時段
        slots = await pool.fetch(
            """
            SELECT id, slot_date, start_time, end_time, google_meet_link 
            FROM interview_slots 
            ORDER BY slot_date DESC, start_time
            """
        )
        
        return {
            "positions": [dict(p) for p in positions],
            "slots": [dict(s) for s in slots]
        }
    
    except Exception as e:
        logger.error(f"Get booking edit options error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取編輯選項失敗")

@app.get("/api/bookings")
async def get_bookings(current=Depends(get_current_hr)):
    try:
        pool = await get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    b.id,
                    b.applicant_id,
                    b.position_id,
                    b.slot_id,
                    b.status,
                    b.booked_at,
                    a.name AS applicant_name,
                    a.email AS applicant_email,
                    a.phone AS applicant_phone,
                    p.title AS position_title,
                    s.slot_date,
                    s.start_time,
                    s.end_time,
                    COALESCE(NULLIF(b.google_meet_link, ''), NULLIF(a.google_meet_link, ''), s.google_meet_link) AS google_meet_link
                FROM bookings b
                JOIN applicants a ON a.id = b.applicant_id
                JOIN job_positions p ON p.id = b.position_id
                JOIN interview_slots s ON s.id = b.slot_id
                WHERE b.deleted_at IS NULL
                ORDER BY b.booked_at DESC
                """
            )

        return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Get bookings error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="取得預約失敗")

@app.get("/api/bookings/export-file")
async def export_bookings(
    status: Optional[str] = Query(None),
    position: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    current=Depends(get_current_hr)
):
    try:
        pool = await get_pool()
        where_clauses = ["b.deleted_at IS NULL"]
        values = []

        if status:
            values.append(status)
            where_clauses.append(f"b.status=$%d" % len(values))
        if position:
            values.append(position)
            where_clauses.append(f"p.title=$%d" % len(values))
        if name:
            values.append(name)
            where_clauses.append(f"a.name=$%d" % len(values))
        if email:
            values.append(email)
            where_clauses.append(f"a.email=$%d" % len(values))
        if keyword:
            values.append(f"%{keyword.lower()}%")
            values.append(f"%{keyword.lower()}%")
            where_clauses.append(
                f"(LOWER(a.name) LIKE $%d OR LOWER(a.email) LIKE $%d)" % (len(values) - 1, len(values))
            )

        query = f"""
            SELECT
                b.id,
                b.status,
                b.booked_at,
                a.name AS applicant_name,
                a.email AS applicant_email,
                a.phone AS applicant_phone,
                p.title AS position_title,
                s.slot_date,
                s.start_time,
                s.end_time
            FROM bookings b
            JOIN applicants a ON a.id = b.applicant_id
            JOIN job_positions p ON p.id = b.position_id
            JOIN interview_slots s ON s.id = b.slot_id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY b.booked_at DESC
        """

        async with pool.acquire() as conn:
            await complete_expired_confirmed_bookings(conn)
            rows = await conn.fetch(query, *values)

        wb = Workbook()
        ws = wb.active
        ws.title = "預約紀錄"

        headers = [
            "應徵者",
            "Email",
            "電話",
            "應徵職缺",
            "面試日期",
            "開始時間",
            "結束時間",
            "狀態",
            "預約時間"
        ]
        ws.append(headers)

        for row in rows:
            ws.append([
                row["applicant_name"],
                row["applicant_email"],
                row["applicant_phone"],
                row["position_title"],
                row["slot_date"].strftime("%Y-%m-%d") if row["slot_date"] else "",
                row["start_time"].strftime("%H:%M") if row["start_time"] else "",
                row["end_time"].strftime("%H:%M") if row["end_time"] else "",
                row["status"],
                row["booked_at"].strftime("%Y-%m-%d %H:%M:%S") if row["booked_at"] else ""
            ])

        for column_cells in ws.columns:
            length = max(len(str(cell.value)) for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = min(max(length + 2, 10), 40)

        stream = BytesIO()
        wb.save(stream)
        stream.seek(0)

        filename = f"bookings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        logger.error(f"Export bookings error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="匯出 Excel 失敗")

@app.patch("/api/bookings/{booking_id}")
async def update_booking(
    booking_id: str,
    payload: BookingUpdate,
    background_tasks: BackgroundTasks,
    current=Depends(get_current_hr)
):
    try:
        pool = await get_pool()
        
        # 驗證 booking_id 格式
        try:
            booking_uuid = uuid.UUID(booking_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="預約 ID 格式無效")

        async with pool.acquire() as conn:
            async with conn.transaction():
                time_updated = False  # 追踪時間是否被更新
                
                # 獲取 booking 的 applicant_id、slot_id、status、google_event_id
                booking = await conn.fetchrow(
                    "SELECT applicant_id, slot_id, status, google_event_id FROM bookings WHERE id=$1 AND deleted_at IS NULL",
                    booking_uuid
                )
                if not booking:
                    raise HTTPException(status_code=404, detail="預約不存在")

                applicant_id = booking['applicant_id']
                slot_id = booking['slot_id']
                current_status = booking['status']

                # 更新 applicants 表
                if payload.applicant_name or payload.applicant_email or payload.phone is not None:
                    updates = []
                    params = []
                    if payload.applicant_name:
                        updates.append(f"name=${len(params)+1}")
                        params.append(payload.applicant_name)
                    if payload.applicant_email:
                        updates.append(f"email=${len(params)+1}")
                        params.append(payload.applicant_email)
                    if payload.phone is not None:
                        updates.append(f"phone=${len(params)+1}")
                        params.append(payload.phone)

                    if updates:
                        params.append(applicant_id)
                        await conn.execute(
                            f"UPDATE applicants SET {','.join(updates)} WHERE id=${len(params)}",
                            *params
                        )

                # 更新 interview_slots 表（如果提供了時間）
                if payload.slot_date or payload.start_time or payload.end_time:
                    time_updated = True  # 標記時間已被更新
                    
                    # 時間被更改，刪除舊的 Google Calendar 事件
                    if booking.get("google_event_id"):
                        await delete_old_google_event(booking["google_event_id"])
                    
                    updates = []
                    params = []

                    try:
                        if payload.slot_date:
                            updates.append(f"slot_date=${len(params)+1}")
                            params.append(datetime.strptime(payload.slot_date, "%Y-%m-%d").date())

                        if payload.start_time:
                            time_str = payload.start_time
                            if len(time_str) == 5:
                                time_str = f"{time_str}:00"
                            updates.append(f"start_time=${len(params)+1}")
                            params.append(datetime.strptime(time_str, "%H:%M:%S").time())

                        if payload.end_time:
                            time_str = payload.end_time
                            if len(time_str) == 5:
                                time_str = f"{time_str}:00"
                            updates.append(f"end_time=${len(params)+1}")
                            params.append(datetime.strptime(time_str, "%H:%M:%S").time())

                        if updates:
                            params.append(slot_id)
                            query = f"UPDATE interview_slots SET {','.join(updates)}, updated_at=NOW() WHERE id=${len(params)}"
                            await conn.execute(query, *params)

                    except ValueError as e:
                        raise HTTPException(status_code=400, detail=f"日期或時間格式無效: {str(e)}")

                # 更新 bookings 表
                bookings_needs_update = (
                    payload.position_id or 
                    payload.status or 
                    payload.google_meet_link is not None or 
                    time_updated
                )
                
                if bookings_needs_update:
                    updates = []
                    params = []
                    new_status = None
                    has_google_meet_link_update = False
                    
                    if payload.position_id:
                        try:
                            pos_uuid = uuid.UUID(payload.position_id)
                            updates.append(f"position_id=${len(params)+1}")
                            params.append(pos_uuid)
                        except ValueError:
                            raise HTTPException(status_code=400, detail="職缺 ID 格式無效")
                    
                    if payload.status:
                        normalized_status = payload.status.strip().lower()
                        if not normalized_status:
                            normalized_status = None
                        if normalized_status and normalized_status not in ('confirmed', 'cancelled', 'no_show', 'auto_completed'):
                            raise HTTPException(status_code=400, detail="無效的狀態值")
                        if normalized_status:
                            new_status = normalized_status
                            updates.append(f"status=${len(params)+1}")
                            params.append(normalized_status)

                    if payload.google_meet_link is not None:
                        normalized_meet_link = payload.google_meet_link.strip() or None
                        updates.append(f"google_meet_link=${len(params)+1}")
                        params.append(normalized_meet_link)
                        has_google_meet_link_update = True

                    # 如果時間被更新，清除舊的 Google Meet 相關欄位（如果還沒有更新過）
                    if time_updated:
                        updates.append("google_event_id=NULL")
                        if not has_google_meet_link_update:
                            updates.append("google_meet_link=NULL")

                    if new_status and new_status != current_status:
                        slot = await conn.fetchrow(
                            "SELECT booked_count, max_capacity, status FROM interview_slots WHERE id=$1",
                            slot_id
                        )
                        if not slot:
                            raise HTTPException(status_code=400, detail="指定預約時段不存在")

                        if current_status == 'confirmed' and new_status != 'confirmed':
                            # 如果狀態變為 no_show 或 cancelled，刪除 Google Calendar 事件
                            if new_status in ('no_show', 'cancelled'):
                                if booking.get("google_event_id"):
                                    await delete_old_google_event(booking["google_event_id"])
                                updates.append("google_event_id=NULL")
                            
                            new_booked_count = max((slot['booked_count'] or 0) - 1, 0)
                            new_slot_status = slot['status']
                            if new_slot_status not in ('cancelled', 'closed'):
                                new_slot_status = 'open' if new_booked_count < slot['max_capacity'] else 'full'
                            await conn.execute(
                                """
                                UPDATE interview_slots
                                SET booked_count=$2,
                                    status=$3,
                                    updated_at=NOW()
                                WHERE id=$1
                                """,
                                slot_id,
                                new_booked_count,
                                new_slot_status
                            )
                            await log_slot_count_change(conn, slot_id, slot['booked_count'], new_booked_count,
                                                        f"booking status changed {current_status} -> {new_status}")

                        elif current_status != 'confirmed' and new_status == 'confirmed':
                            if slot['booked_count'] >= slot['max_capacity']:
                                raise HTTPException(status_code=400, detail="所選時段已滿，無法設為 confirmed")
                            new_booked_count = slot['booked_count'] + 1
                            new_slot_status = 'full' if new_booked_count >= slot['max_capacity'] else 'open'
                            await conn.execute(
                                """
                                UPDATE interview_slots
                                SET booked_count=$2,
                                    status=$3,
                                    updated_at=NOW()
                                WHERE id=$1
                                """,
                                slot_id,
                                new_booked_count,
                                new_slot_status
                            )
                            await log_slot_count_change(conn, slot_id, slot['booked_count'], new_booked_count,
                                                        f"booking status changed {current_status} -> {new_status}")

                    if updates:
                        params.append(booking_uuid)
                        await conn.execute(
                            f"UPDATE bookings SET {','.join(updates)} WHERE id=${len(params)}",
                            *params
                        )
            
            # 如果時間被更新且預約是 confirmed 狀態，重新排程新的 Google Meet
            if time_updated and current_status == 'confirmed':
                try:
                    log_json(
                        logging.INFO,
                        "schedule_google_meet.triggered",
                        booking_id=str(booking_uuid),
                        reason="time_updated",
                    )
                    background_tasks.add_task(
                        schedule_google_meet_for_booking,
                        str(booking_uuid),
                        5,
                    )
                except Exception as e:
                    logger.exception(f"Failed to reschedule google meet for booking {booking_uuid}")
                    log_json(
                        logging.ERROR,
                        "schedule_google_meet.failed",
                        booking_id=str(booking_uuid),
                        error=str(e),
                    )

        return {"ok": True}
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Update booking error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新預約失敗")

@app.delete("/api/bookings/{booking_id}")
async def delete_booking(
    booking_id: str,
    current=Depends(get_current_hr)
):
    try:
        pool = await get_pool()

        async with pool.acquire() as conn:
            async with conn.transaction():
                booking = await conn.fetchrow(
                    """
                    SELECT b.slot_id, 
                           b.google_event_id, 
                           b.position_id,
                           a.name AS applicant_name,
                           a.email AS applicant_email,
                           p.title AS position_title,
                           s.slot_date, s.start_time, s.end_time
                    FROM bookings b
                    JOIN applicants a ON a.id = b.applicant_id
                    JOIN job_positions p ON p.id = b.position_id
                    JOIN interview_slots s ON s.id = b.slot_id
                    WHERE b.id=$1 AND b.deleted_at IS NULL
                    """,
                    uuid.UUID(booking_id)
                )

                if not booking:
                    raise HTTPException(status_code=404, detail="預約不存在")

                slot = await conn.fetchrow(
                    """
                    SELECT booked_count, max_capacity, status
                    FROM interview_slots
                    WHERE id=$1
                    """,
                    booking["slot_id"]
                )

                # 刪除 Google Calendar 事件
                if booking.get("google_event_id"):
                    await delete_old_google_event(booking["google_event_id"])

                await conn.execute(
                    """
                    UPDATE bookings
                    SET status='cancelled',
                        cancelled_by='hr',
                        cancelled_at=NOW(),
                        deleted_at=NOW(),
                        deleted_by=$2,
                        google_event_id=NULL
                    WHERE id=$1
                    """,
                    uuid.UUID(booking_id),
                    uuid.UUID(current["id"])
                )

                if slot:
                    new_booked_count = max((slot["booked_count"] or 0) - 1, 0)
                    new_status = slot["status"]
                    if new_status not in ("cancelled", "closed"):
                        new_status = "open" if new_booked_count < slot["max_capacity"] else "full"

                    await conn.execute(
                        """
                        UPDATE interview_slots
                        SET booked_count = $2,
                            status = $3,
                            updated_at = NOW()
                        WHERE id=$1
                        """,
                        booking["slot_id"],
                        new_booked_count,
                        new_status
                    )

                    await log_slot_count_change(conn, booking["slot_id"], slot["booked_count"], new_booked_count, "booking deleted by hr")
        
        # 發送取消通知給應徵者（交易外執行以避免超時）
        try:
            await send_event_cancellation_notification(
                applicant_name=booking["applicant_name"],
                applicant_email=booking["applicant_email"],
                position_title=booking["position_title"],
                slot_date=booking["slot_date"],
                start_time=booking["start_time"],
                end_time=booking["end_time"],
            )
        except Exception:
            logger.exception(f"Failed to send cancellation email for booking {booking_id}")

        return {"ok": True}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Delete booking error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="刪除預約失敗")