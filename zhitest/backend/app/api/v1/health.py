import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.responses import UTF8JSONResponse, error_body, success

logger = logging.getLogger("zhitest.health")
router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)) -> object:
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("database health check failed")
        try:
            db.rollback()
        except Exception:
            logger.exception("health check rollback failed")
        return UTF8JSONResponse(
            status_code=503,
            content=error_body("DATABASE_UNAVAILABLE", "数据库不可用"),
        )
    return success(
        {
            "status": "ok",
            "database": "ok",
            "service": "zhitest-api",
            "phase": "phase2",
        }
    )
