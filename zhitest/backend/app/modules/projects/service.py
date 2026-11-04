from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.project import Project
from app.models.user import User
from app.modules.audit.service import write_audit


def validate_base_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("Base URL 必填")
    if len(raw) > 500 or any(ch in raw for ch in (" ", "\t", "\r", "\n")):
        raise ValueError("Base URL 格式非法")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("Base URL 格式非法")
    if parts.username or parts.password:
        raise ValueError("Base URL 不能包含用户名或密码")
    return raw


def project_payload(project: Project) -> dict[str, object]:
    return {
        "id": str(project.id),
        "ownerId": str(project.owner_id),
        "name": project.name,
        "description": project.description,
        "baseUrl": project.base_url,
        "envLabel": project.env_label,
        "endpointCount": 0,
        "caseCount": 0,
        "lastRun": None,
        "createdAt": project.created_at.isoformat(),
        "updatedAt": project.updated_at.isoformat(),
    }


def create_project(
    db: Session,
    user: User,
    *,
    name: str,
    description: str,
    base_url: str,
    env_label: str,
    ip: str | None,
) -> Project:
    now = datetime.now(timezone.utc)
    project = Project(
        owner_id=user.id,
        name=name,
        description=description,
        base_url=base_url,
        env_label=env_label,
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    try:
        db.flush()
    except IntegrityError as exc:
        raise AppError(409, "CONFLICT", "项目名称已存在") from exc
    write_audit(
        db,
        action="project.create",
        actor_id=user.id,
        resource_type="project",
        resource_id=str(project.id),
        detail={"name": project.name, "envLabel": project.env_label},
        ip=ip,
    )
    return project


def list_projects(
    db: Session,
    user: User,
    *,
    q: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Project], int]:
    filters = [Project.owner_id == user.id]
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(Project.name.ilike(f"%{escaped}%", escape="\\"))
    total = db.scalar(select(func.count()).select_from(Project).where(*filters)) or 0
    rows = db.scalars(
        select(Project)
        .where(*filters)
        .order_by(Project.updated_at.desc(), Project.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), int(total)


def get_owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise AppError(404, "NOT_FOUND", "资源不存在")
    return project
