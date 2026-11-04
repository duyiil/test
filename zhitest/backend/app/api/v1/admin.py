from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.responses import success
from app.models.project import Project
from app.models.user import User

router = APIRouter()


@router.get("/status")
def status(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict[str, object]:
    user_count = db.scalar(select(func.count()).select_from(User)) or 0
    project_count = db.scalar(select(func.count()).select_from(Project)) or 0
    return success(
        {
            "role": admin.role,
            "userCount": int(user_count),
            "projectCount": int(project_count),
        }
    )
