import os
import hashlib
import logging

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Cookie
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# JWT 設定
# ─────────────────────────────────────────────

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "dev-secret-key-change-in-production"
)

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        60 * 24 * 7  # 7天
    )
)

# ─────────────────────────────────────────────
# 密碼加密設定
# ─────────────────────────────────────────────

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# ─────────────────────────────────────────────
# 密碼預處理（解決 bcrypt 72 bytes 限制）
# ─────────────────────────────────────────────

def _normalize_password(password: str) -> str:

    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()

# ─────────────────────────────────────────────
# 驗證密碼
# ─────────────────────────────────────────────

def verify_password(
    plain: str,
    hashed: str
) -> bool:

    try:

        return pwd_context.verify(
            _normalize_password(plain),
            hashed
        )

    except Exception as e:

        logger.error(
            f"Password verify error: {str(e)}",
            exc_info=True
        )

        return False

# ─────────────────────────────────────────────
# 建立密碼
# ─────────────────────────────────────────────

def hash_password(plain: str) -> str:

    try:

        return pwd_context.hash(
            _normalize_password(plain)
        )

    except Exception as e:

        logger.error(
            f"Password hash error: {str(e)}",
            exc_info=True
        )

        raise

# ─────────────────────────────────────────────
# 建立 JWT
# ─────────────────────────────────────────────

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
):

    to_encode = data.copy()

    expire = datetime.utcnow() + (
        expires_delta or timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    to_encode.update({
        "exp": expire
    })

    encoded_jwt = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return encoded_jwt

# ─────────────────────────────────────────────
# 解碼 JWT
# ─────────────────────────────────────────────

def decode_token(token: str) -> dict:

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        return payload

    except JWTError:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登入已失效，請重新登入"
        )

# ─────────────────────────────────────────────
# 取得目前登入 HR
# ─────────────────────────────────────────────

async def get_current_hr(
    access_token: Optional[str] = Cookie(default=None)
):

    # 沒 Cookie
    if not access_token:

        raise HTTPException(
            status_code=401,
            detail="尚未登入"
        )

    # Decode JWT
    payload = decode_token(access_token)

    # JWT 內容驗證
    user_id = payload.get("sub")
    email = payload.get("email")
    role = payload.get("role")

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="登入資訊無效"
        )

    return {
        "id": user_id,
        "email": email,
        "role": role,
    }