from __future__ import annotations

import uuid
from typing import Any

import logging

from sqlalchemy.orm import Session

from app.core.request_context import get_request_id
from app.models.audit import AuditLog

logger = logging.getLogger("zhitest.audit")


def write_audit(
    db: Session,
    *,
    action: str,
    actor_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            ip=ip,
            request_id=get_request_id(),
        )
    )


def commit_audit(
    *,
    action: str,
    actor_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """独立提交审计。登录失败会回滚请求事务，失败记录不能跟着被丢掉。"""

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        write_audit(
            db,
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            ip=ip,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("failed to persist audit action=%s", action)
    finally:
        db.close()
