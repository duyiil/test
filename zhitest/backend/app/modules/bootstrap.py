from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.security import hash_password, validate_username
from app.db.session import SessionLocal
from app.models.user import User

logger = logging.getLogger("zhitest.bootstrap")
_USERNAME_RE = re.compile(r"[A-Za-z0-9._-]{3,64}")


def bootstrap_admin(settings: Settings | None = None) -> None:
    """创建初始管理员。已存在时不重置口令。"""

    settings = settings or get_settings()
    if not _USERNAME_RE.fullmatch(settings.admin_username):
        raise RuntimeError("ZHITEST_ADMIN_USERNAME 非法，启动已中止")
    try:
        username = validate_username(settings.admin_username)
        password_hash = hash_password(settings.admin_password)
    except ValueError as exc:
        raise RuntimeError(f"管理员初始化失败：{exc}") from exc

    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.username == username))
        if existing is not None:
            logger.info("admin user %s already exists, password not reset", username)
            return
        now = datetime.now(timezone.utc)
        db.add(
            User(
                username=username,
                password_hash=password_hash,
                display_name=settings.admin_display_name.strip() or username,
                role="admin",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        logger.info("admin user %s created", username)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
