#!/usr/bin/env python3
"""Test email sending functionality"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import after dotenv
from backend.email_utils import _send

async def test_send_email():
    """Test sending a simple email"""
    recipient = os.getenv("SMTP_USER", "")
    
    if not recipient:
        print("ERROR: SMTP_USER not configured in .env")
        return False
    
    test_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial, sans-serif; background: #f5f5f5; }
            .card { max-width: 600px; margin: auto; background: #fff; padding: 20px; border-radius: 8px; }
            .header { background: #222222; color: white; padding: 20px; border-bottom: 3px solid #e8961a; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <h2>郵件測試</h2>
            </div>
            <div style="padding: 20px;">
                <p>這是一封測試郵件，確認您的 SMTP 配置是否正常工作。</p>
                <p>如果您收到此郵件，表示郵件服務配置成功！</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    print(f"Sending test email to: {recipient}")
    print(f"SMTP_HOST: {os.getenv('SMTP_HOST')}")
    print(f"SMTP_PORT: {os.getenv('SMTP_PORT')}")
    print(f"MAIL_FROM: {os.getenv('MAIL_FROM')}")
    
    try:
        await _send(
            to=recipient,
            subject="HR 系統郵件服務測試",
            html=test_html
        )
        print("✓ 郵件已發送！")
        return True
    except Exception as e:
        print(f"✗ 郵件發送失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_send_email())
    exit(0 if result else 1)
