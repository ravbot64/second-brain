from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib
import hmac
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from .config import settings
from .database import SessionLocal
from .models_db import DBUser

security = HTTPBearer(auto_error=False)


PBKDF2_ALGO = "sha256"
PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGO,
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_{PBKDF2_ALGO}${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iter_str, salt, expected = password_hash.split("$", 3)
        if scheme != f"pbkdf2_{PBKDF2_ALGO}":
            return False
        iterations = int(iter_str)
        digest = hashlib.pbkdf2_hmac(
            PBKDF2_ALGO,
            password.encode("utf-8"),
            bytes.fromhex(salt),
            iterations,
        ).hex()
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def create_access_token(user_id: str, expires_minutes: Optional[int] = None) -> str:
    minutes = expires_minutes or settings.JWT_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> DBUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    db = SessionLocal()
    try:
        user = db.query(DBUser).filter(DBUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
    finally:
        db.close()
