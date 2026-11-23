from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, get_db
from app.core.config import Settings, get_settings
from app.core.responses import success
from app.models.audit import AuditLog
from app.models.user import User
from app.modules.auth.service import login as login_user
from app.modules.auth.service import logout as logout_user
from app.modules.auth.service import user_payload

router = APIRouter()


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=72)


@router.post("/login")
def login(
    body: LoginBody,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    user, token = login_user(db, settings, body.username, body.password, client_ip(request, settings))
    request.state.refreshed_session_token = token
    return success(user_payload(user), "登录成功")


@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    raw = request.cookies.get(settings.session_cookie_name, "")
    logout_user(db, raw, user, client_ip(request, settings))
    request.state.clear_session_cookie = True
    return success({"loggedOut": True}, "已退出登录")


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict[str, object]:
    return success(user_payload(user))


@router.get("/audit")
def my_audit(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    rows = db.scalars(
        select(AuditLog).where(AuditLog.actor_id == user.id).order_by(AuditLog.created_at.desc()).limit(20)
    ).all()
    return success(
        {
            "items": [
                {
                    "id": str(item.id),
                    "action": item.action,
                    "resourceType": item.resource_type,
                    "resourceId": item.resource_id,
                    "detail": item.detail or {},
                    "requestId": item.request_id,
                    "createdAt": item.created_at.isoformat(),
                }
                for item in rows
            ]
        }
    )
