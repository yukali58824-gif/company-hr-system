import sys
import os

with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(len(lines)):
    if 'await _send(to=payload.email, subject=subject, html=html)' in lines[i] and i + 1 < len(lines) and 'await conn.execute(' in lines[i+1]:
        # Adjusted indentation to 28 spaces (match await _send)
        lines[i+1] = '                            await conn.execute(\n'
        lines[i+2] = '                                """\n'
        lines[i+3] = '                                UPDATE email_logs\n'
        lines[i+4] = "                                SET status='sent',\n"
        lines[i+5] = '                                        sent_at=NOW()\n'
        lines[i+6] = "                                WHERE booking_id=$1 AND email_type='booking_confirm'\n"
        lines[i+7] = '                                    AND cancel_token=$2\n'
        lines[i+8] = '                                """\n'
        lines[i+9] = '                                , booking_uuid\n'
        lines[i+10] = '                                , cancel_token\n'
        lines[i+11] = '                            )\n'
        break

with open('main.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
