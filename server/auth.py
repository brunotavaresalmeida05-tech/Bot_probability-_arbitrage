from __future__ import annotations
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer()


def _secret() -> str:
    return os.getenv("JWT_SECRET", "changeme-please-set-JWT_SECRET-in-env")


def _expires_hours() -> int:
    return int(os.getenv("JWT_EXPIRES_HOURS", "24"))


def _dashboard_user() -> str:
    return os.getenv("DASHBOARD_USER", "admin")


def _dashboard_password() -> str:
    return os.getenv("DASHBOARD_PASSWORD", "changeme")


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=_expires_hours()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    try:
        payload = jwt.decode(credentials.credentials, _secret(), algorithms=["HS256"])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def check_credentials(username: str, password: str) -> bool:
    if not username or not password:
        return False
    user_ok = hmac.compare_digest(username.encode(), _dashboard_user().encode())
    pass_ok = hmac.compare_digest(password.encode(), _dashboard_password().encode())
    return user_ok and pass_ok
