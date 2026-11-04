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


def project_payload(project: Project, db: Session | None = None) -> dict[str, object]:
    endpoint_count = 0
    case_count = 0
    last_run: dict[str, object] | None = None
    if db is not None:
        from app.models.testing import ApiEndpoint, TestCase, TestRun
        from app.modules.testing.service import pass_rate

        endpoint_count = (
            db.scalar(select(func.count()).select_from(ApiEndpoint).where(ApiEndpoint.project_id == project.id)) or 0
        )
        case_count = db.scalar(select(func.count()).select_from(TestCase).where(TestCase.project_id == project.id)) or 0
        last = db.scalar(
            select(TestRun).where(TestRun.project_id == project.id).order_by(TestRun.created_at.desc()).limit(1)
        )
        if last is not None:
            rate, text = pass_rate(last.passed_count, last.assertion_failed_count)
            last_run = {
                "id": str(last.id),
                "status": last.status,
                "finishedAt": last.finished_at.isoformat() if last.finished_at else None,
                "passRate": rate,
                "passRateText": text,
            }
    return {
        "id": str(project.id),
        "ownerId": str(project.owner_id),
        "name": project.name,
        "description": project.description,
        "baseUrl": project.base_url,
        "envLabel": project.env_label,
        "endpointCount": int(endpoint_count),
        "caseCount": int(case_count),
        "lastRun": last_run,
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
