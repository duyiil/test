from __future__ import annotations

import re
from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import hash_token
from app.db.session import SessionLocal
from app.models.session import UserSession
from app.models.user import User
from app.modules.auth.service import touch_session

_IP_RE = re.compile(r"[0-9A-Za-z:.]{1,64}")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def client_ip(request: Request, settings: Settings) -> str | None:
    if settings.trust_proxy:
        real = request.headers.get("x-real-ip", "")
        if _IP_RE.fullmatch(real):
            return real
    if request.client is None:
        return None
    return request.client.host


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        raise AppError(401, "UNAUTHORIZED", "未登录或登录已失效")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(raw)))
    now = datetime.now(timezone.utc)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise AppError(401, "UNAUTHORIZED", "未登录或登录已失效")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AppError(401, "UNAUTHORIZED", "未登录或登录已失效")
    touch_session(session, settings)
    request.state.refreshed_session_token = raw
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise AppError(403, "FORBIDDEN", "权限不足")
    return user
