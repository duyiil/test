"""GitHub 项目接入：从仓库网址检测项目并导入接口定义。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, get_db
from app.core.config import Settings, get_settings
from app.core.responses import success
from app.models.user import User
from app.modules.github import service as github_service
from app.modules.platform.service import get_owned_project
from app.modules.testing.service import create_generation_task

router = APIRouter()


class GithubUrlBody(BaseModel):
    url: str = Field(min_length=1, max_length=500)


class GithubImportBody(GithubUrlBody):
    specPath: str = Field(min_length=1, max_length=300)
    autoGenerate: bool = False


@router.post("/projects/{project_id}/github/detect")
def github_detect(
    project_id: uuid.UUID,
    body: GithubUrlBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    get_owned_project(db, user, project_id)
    return success(github_service.detect_project(body.url), "项目检测完成")


@router.post("/projects/{project_id}/github/import")
def github_import(
    project_id: uuid.UUID,
    body: GithubImportBody,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    get_owned_project(db, user, project_id)
    result = github_service.import_spec(db, user, project_id, body.url, body.specPath, client_ip(request, settings))
    payload: dict[str, object] = dict(result)
    if body.autoGenerate:
        task = create_generation_task(db, user, project_id, client_ip(request, settings))
        payload["generationTaskId"] = str(task.id)
        db.commit()
        return success(payload, "接口已导入，用例生成任务已入队")
    db.commit()
    return success(payload, "接口已导入")
