from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.responses import success
from app.models.user import User
from app.modules.dashboard.service import dashboard_summary

router = APIRouter()


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    return success(dashboard_summary(db, user))
