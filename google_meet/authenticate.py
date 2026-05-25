#!/usr/bin/env python3
"""
Google API 認證初始化腳本

首次運行時需要執行此腳本以生成 token.json，完成 Google API 認證。
認證後會生成 token.json，之後應用就可以自動使用該 token。
"""

import os
import sys
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
]

def authenticate_google():
    """進行 Google OAuth2 認證並保存 token"""
    print("=" * 60)
    print("Google API 認證初始化")
    print("=" * 60)
    
    if not CREDENTIALS_FILE.exists():
        print(f"❌ 錯誤：找不到 {CREDENTIALS_FILE}")
        print("請先從 Google Cloud Console 下載 credentials.json")
        return False
    
    if TOKEN_FILE.exists():
        print(f"✓ Token 已存在：{TOKEN_FILE}")
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds.valid:
            print("✓ Token 有效，無需重新認證")
            return True
        elif creds.expired and creds.refresh_token:
            print("🔄 Token 已過期，嘗試自動刷新...")
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            print("✓ Token 已刷新")
            return True
    
    print("\n🔗 正在啟動瀏覽器進行 Google 認證...")
    print("   如果沒有自動打開，請訪問本地 http://localhost:8080")
    print("   認證後會自動保存 token.json\n")
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE, 
            SCOPES
        )
        creds = flow.run_local_server(port=8080)
        
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        
        print("\n✓ 認證成功！")
        print(f"✓ Token 已保存：{TOKEN_FILE}")
        return True
        
    except Exception as e:
        print(f"\n❌ 認證失敗：{e}")
        return False

if __name__ == "__main__":
    success = authenticate_google()
    sys.exit(0 if success else 1)
