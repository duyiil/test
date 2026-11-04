from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import dummy_verify, hash_token, new_session_token, verify_password
from app.models.session import UserSession
from app.models.user import User
from app.modules.audit.service import commit_audit, write_audit


def user_payload(user: User) -> dict[str, str]:
    return {
        "id": str(user.id),
        "username": user.username,
        "displayName": user.display_name,
        "role": user.role,
    }


def login(db: Session, settings: Settings, username: str, password: str, ip: str | None) -> tuple[User, str]:
    attempted = username.strip()[:64]
    user = db.scalar(select(User).where(User.username == username.strip()))
    if user is None:
        dummy_verify(password)
        password_ok = False
    else:
        password_ok = verify_password(password, user.password_hash)
    if user is None or not password_ok:
        commit_audit(
            action="auth.login_failed",
            actor_id=user.id if user is not None else None,
            resource_type="user",
            resource_id=str(user.id) if user is not None else None,
            detail={"username": attempted},
            ip=ip,
        )
        raise AppError(401, "UNAUTHORIZED", "用户名或密码错误")
    if not user.is_active:
        commit_audit(
            action="auth.login_denied",
            actor_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            detail={"username": user.username, "reason": "inactive"},
            ip=ip,
        )
        raise AppError(401, "UNAUTHORIZED", "账号已停用，请联系管理员")

    raw = new_session_token()
    now = datetime.now(timezone.utc)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
            ip=ip,
            created_at=now,
        )
    )
    write_audit(
        db,
        action="auth.login",
        actor_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        detail={"username": user.username},
        ip=ip,
    )
    return user, raw


def logout(db: Session, raw_token: str, user: User, ip: str | None) -> None:
    token_hash = hash_token(raw_token) if raw_token else ""
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
    write_audit(
        db,
        action="auth.logout",
        actor_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        detail={"username": user.username},
        ip=ip,
    )


def touch_session(session: UserSession, settings: Settings) -> None:
    session.expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.session_ttl_seconds)
