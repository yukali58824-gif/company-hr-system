#!/usr/bin/env python3
"""驗證預約更新的兩個 Google Meet 分支。

測試內容：
1. 只改姓名 / Email / 電話 / 職稱，面試時段不變時，Google Event ID 應保持不變。
2. 只改面試日期 / 開始時間 / 結束時間時，舊事件應被刪除並重建，Google Event ID 應改變。

需求：
- 先在瀏覽器登入 HR 後台，取得 access_token cookie。
- 將該 cookie 值放到環境變數 HR_ACCESS_TOKEN 或 ACCESS_TOKEN。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta

import asyncpg
import requests


DEFAULT_API_BASE = os.getenv("API_BASE", "http://localhost:8013")
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "LiMin20260505"),
    "database": os.getenv("DB_NAME", "hr_system"),
}


def make_session(api_base: str) -> requests.Session:
    token = os.getenv("HR_ACCESS_TOKEN") or os.getenv("ACCESS_TOKEN")
    if not token:
        raise SystemExit(
            "請先把 HR access_token 放到環境變數 HR_ACCESS_TOKEN 或 ACCESS_TOKEN"
        )

    session = requests.Session()
    session.cookies.set("access_token", token)

    me = session.get(f"{api_base}/api/hr/me", timeout=20)
    if not me.ok:
        raise SystemExit(
            f"登入驗證失敗：/api/hr/me 回傳 {me.status_code}，請確認 access_token 是否有效"
        )

    return session


async def fetch_reference_booking(conn: asyncpg.Connection):
    row = await conn.fetchrow(
        """
        SELECT b.id,
               b.slot_id,
               b.position_id,
               b.status,
               b.google_event_id,
               b.google_meet_link,
               a.id AS applicant_id,
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
        WHERE b.status = 'confirmed'
          AND b.deleted_at IS NULL
          AND b.google_event_id IS NOT NULL
        ORDER BY b.booked_at DESC
        LIMIT 1
        """
    )

    return dict(row) if row else None


async def fetch_booking_state(conn: asyncpg.Connection, booking_id: str):
    row = await conn.fetchrow(
        """
        SELECT b.id,
               b.slot_id,
               b.position_id,
               b.status,
               b.google_event_id,
               b.google_meet_link,
               a.id AS applicant_id,
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
        WHERE b.id = $1
        """,
        uuid.UUID(booking_id),
    )

    return dict(row) if row else None


async def fetch_alternative_position(conn: asyncpg.Connection, current_position_id: str):
    row = await conn.fetchrow(
        """
        SELECT id, title
        FROM job_positions
        WHERE is_active = TRUE
          AND id <> $1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        uuid.UUID(current_position_id),
    )
    return dict(row) if row else None


def patch_booking(api_base: str, session: requests.Session, booking_id: str, payload: dict):
    response = session.patch(
        f"{api_base}/api/bookings/{booking_id}",
        json=payload,
        timeout=30,
    )
    return response


async def wait_for_condition(conn: asyncpg.Connection, booking_id: str, predicate, timeout_seconds: int = 40):
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    latest = None

    while asyncio.get_event_loop().time() < deadline:
        latest = await fetch_booking_state(conn, booking_id)
        if latest and predicate(latest):
            return latest
        await asyncio.sleep(2)

    return latest


async def main() -> int:
    parser = argparse.ArgumentParser(description="驗證預約更新的 Google Meet 兩個分支")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--timeout-seconds", type=int, default=40)
    args = parser.parse_args()

    session = make_session(args.api_base)
    conn = await asyncpg.connect(**DB_CONFIG)

    try:
        initial = await fetch_reference_booking(conn)
        if not initial:
            print("找不到可測試的 confirmed booking（需要 google_event_id 且未刪除）")
            return 1

        alternative_position = await fetch_alternative_position(conn, initial["position_id"])

        print("=" * 80)
        print("初始資料")
        print(f"Booking ID: {initial['id']}")
        print(f"Event ID: {initial['google_event_id']}")
        print(f"應徵者: {initial['applicant_name']} / {initial['applicant_email']}")
        print(f"職稱: {initial['position_title']}")
        print(f"時段: {initial['slot_date']} {initial['start_time']} - {initial['end_time']}")
        print("=" * 80)

        if alternative_position:
            new_position_id = alternative_position["id"]
            new_position_title = alternative_position["title"]
        else:
            new_position_id = initial["position_id"]
            new_position_title = initial["position_title"]

        info_payload = {
            "applicant_name": f"測試姓名_{datetime.now().strftime('%H%M%S')}",
            "applicant_email": f"test_{datetime.now().strftime('%H%M%S')}@example.com",
            "phone": "0912-000-123",
            "position_id": str(new_position_id),
        }

        print("\n[1/2] 測試只改資料、不改時段")
        print(f"新的姓名: {info_payload['applicant_name']}")
        print(f"新的 Email: {info_payload['applicant_email']}")
        print(f"新的 職稱: {new_position_title}")

        response = patch_booking(args.api_base, session, initial["id"], info_payload)
        print(f"PATCH 狀態: {response.status_code}")
        if not response.ok:
            print(response.text)
            return 1

        info_result = await wait_for_condition(
            conn,
            initial["id"],
            lambda row: (
                row["google_event_id"] == initial["google_event_id"]
                and row["applicant_name"] == info_payload["applicant_name"]
                and row["applicant_email"] == info_payload["applicant_email"]
                and row["applicant_phone"] == info_payload["phone"]
                and row["position_id"] == uuid.UUID(str(new_position_id))
            ),
            timeout_seconds=args.timeout_seconds,
        )

        if not info_result:
            print("❌ 等不到資訊更新完成")
            return 1

        if info_result["google_event_id"] == initial["google_event_id"]:
            print("✅ 資料更新分支：Google Event ID 保持不變")
        else:
            print("❌ 資料更新分支：Google Event ID 已變更，這不符合預期")
            print(f"   before: {initial['google_event_id']}")
            print(f"   after : {info_result['google_event_id']}")
            return 1

        updated_event_id = info_result["google_event_id"]

        current_start = initial["start_time"]
        current_end = initial["end_time"]
        current_date = initial["slot_date"]

        if hasattr(current_date, "toordinal"):
            new_date = current_date + timedelta(days=7)
        else:
            new_date = datetime.strptime(str(current_date), "%Y-%m-%d").date() + timedelta(days=7)

        time_payload = {
            "slot_date": new_date.strftime("%Y-%m-%d"),
            "start_time": current_start.strftime("%H:%M") if hasattr(current_start, "strftime") else str(current_start)[:5],
            "end_time": current_end.strftime("%H:%M") if hasattr(current_end, "strftime") else str(current_end)[:5],
        }

        print("\n[2/2] 測試只改時段")
        print(f"新的日期: {time_payload['slot_date']}")
        print(f"新的開始: {time_payload['start_time']}")
        print(f"新的結束: {time_payload['end_time']}")

        response = patch_booking(args.api_base, session, initial["id"], time_payload)
        print(f"PATCH 狀態: {response.status_code}")
        if not response.ok:
            print(response.text)
            return 1

        time_result = await wait_for_condition(
            conn,
            initial["id"],
            lambda row: row["google_event_id"] not in (None, updated_event_id),
            timeout_seconds=args.timeout_seconds,
        )

        if not time_result:
            print("❌ 等不到時段重建完成")
            return 1

        if time_result["google_event_id"] != updated_event_id:
            print("✅ 時段變更分支：Google Event ID 已重建")
            print(f"   before: {updated_event_id}")
            print(f"   after : {time_result['google_event_id']}")
        else:
            print("❌ 時段變更分支：Google Event ID 沒有變更")
            return 1

        print("\n" + "=" * 80)
        print("✅ 兩個分支都通過")
        print("=" * 80)
        return 0

    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))