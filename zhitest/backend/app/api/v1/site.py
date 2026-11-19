"""网站检测：从真实网页地址扫描站点并导入接口定义。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, get_db
from app.core.config import Settings, get_settings
from app.core.responses import success
from app.models.user import User
from app.modules.platform.service import get_owned_project
from app.modules.site import service as site_service
from app.modules.testing.service import create_generation_task

router = APIRouter()


class SiteUrlBody(BaseModel):
    url: str = Field(min_length=1, max_length=500)


class SiteImportBody(SiteUrlBody):
    specPath: str = Field(min_length=1, max_length=300)
    autoGenerate: bool = False
    updateBaseUrl: bool = False


@router.post("/projects/{project_id}/site/detect")
def site_detect(
    project_id: uuid.UUID,
    body: SiteUrlBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    get_owned_project(db, user, project_id)
    return success(site_service.detect_site(body.url), "网站检测完成")


@router.post("/projects/{project_id}/site/import")
def site_import(
    project_id: uuid.UUID,
    body: SiteImportBody,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    get_owned_project(db, user, project_id)
    result = site_service.import_site_spec(
        db,
        user,
        project_id,
        body.url,
        body.specPath,
        ip=client_ip(request, settings),
        update_base_url=body.updateBaseUrl,
    )
    payload: dict[str, object] = dict(result)
    if body.autoGenerate:
        task = create_generation_task(db, user, project_id, client_ip(request, settings))
        payload["generationTaskId"] = str(task.id)
        db.commit()
        return success(payload, "接口已导入，用例生成任务已入队")
    db.commit()
    return success(payload, "接口已导入")
