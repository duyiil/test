import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, get_db
from app.core.config import Settings, get_settings
from app.core.responses import success
from app.models.user import User
from app.modules.projects.service import create_project, get_owned_project, list_projects, project_payload, validate_base_url

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    base_url: str = Field(alias="baseUrl", min_length=1, max_length=500)
    env_label: str = Field(alias="envLabel", min_length=1, max_length=32)

    model_config = {"populate_by_name": True}

    @field_validator("name", "env_label")
    @classmethod
    def strip_required(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("不能为空")
        return text

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, value: str) -> str:
        return validate_base_url(value)


@router.post("", status_code=201)
def create(
    body: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    project = create_project(
        db,
        user,
        name=body.name,
        description=body.description,
        base_url=body.base_url,
        env_label=body.env_label,
        ip=client_ip(request, settings),
    )
    return success(project_payload(project), "创建成功")


@router.get("")
def list_my_projects(
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    rows, total = list_projects(db, user, q=q.strip() if q else None, page=page, page_size=page_size)
    return success(
        {
            "items": [project_payload(item) for item in rows],
            "page": page,
            "pageSize": page_size,
            "total": total,
        }
    )


@router.get("/{project_id}")
def detail(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    project = get_owned_project(db, user, project_id)
    return success(project_payload(project))
