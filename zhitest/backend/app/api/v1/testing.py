import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, get_db
from app.core.config import Settings, get_settings
from app.core.responses import success
from app.models.user import User
from app.modules.testing.service import (
    approve_version,
    cancel_run,
    create_generation_task,
    create_run,
    edit_version,
    endpoint_payload,
    generation_payload,
    get_generation_task,
    get_run,
    get_version_for_user,
    list_cases,
    list_endpoints,
    list_reports,
    list_runs,
    load_demo_contract,
    reject_version,
    report_for_run,
    report_payload,
    run_payload,
    submit_review,
    version_payload,
)

router = APIRouter()


class RejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class EditBody(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    assertions: list[dict] | None = None


class RunBody(BaseModel):
    confirm_writes: bool = Field(default=False, alias="confirmWrites")

    model_config = {"populate_by_name": True}


@router.post("/projects/{project_id}/contract/demo")
def demo_contract(
    project_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    rows = load_demo_contract(db, user, project_id, client_ip(request, settings))
    return success({"items": [endpoint_payload(item) for item in rows]}, "已载入作者编写的演示契约")


@router.get("/projects/{project_id}/endpoints")
def endpoints(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    rows = list_endpoints(db, user, project_id)
    return success({"items": [endpoint_payload(item) for item in rows]})


@router.post("/projects/{project_id}/generation-tasks", status_code=202)
def generate(
    project_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    task = create_generation_task(db, user, project_id, client_ip(request, settings))
    return success(generation_payload(db, task), "生成任务已入队")


@router.get("/generation-tasks/{task_id}")
def generation_detail(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    task = get_generation_task(db, user, task_id)
    return success(generation_payload(db, task))


@router.get("/projects/{project_id}/cases")
def cases(
    project_id: uuid.UUID,
    review_status: str | None = Query(default=None, alias="reviewStatus"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    return success({"items": list_cases(db, user, project_id, review_status)})


@router.get("/case-versions/{version_id}")
def case_detail(
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    version = get_version_for_user(db, user, version_id)
    return success(version_payload(db, version))


@router.post("/case-versions/{version_id}/submit")
def submit(
    version_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    version = submit_review(db, user, version_id, client_ip(request, settings))
    return success(version_payload(db, version), "已提交审核")


@router.post("/case-versions/{version_id}/approve")
def approve(
    version_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    version = approve_version(db, user, version_id, client_ip(request, settings))
    return success(version_payload(db, version), "审核通过")


@router.post("/case-versions/{version_id}/reject")
def reject(
    version_id: uuid.UUID,
    body: RejectBody,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    version = reject_version(db, user, version_id, body.reason, client_ip(request, settings))
    return success(version_payload(db, version), "已驳回")


@router.post("/case-versions/{version_id}/edit")
def edit(
    version_id: uuid.UUID,
    body: EditBody,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    version = edit_version(
        db,
        user,
        version_id,
        name=body.name,
        description=body.description,
        assertions=body.assertions,
        ip=client_ip(request, settings),
    )
    return success(version_payload(db, version), "已保存为新版本")


@router.post("/projects/{project_id}/runs", status_code=202)
def start_run(
    project_id: uuid.UUID,
    body: RunBody,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    run = create_run(
        db,
        user,
        project_id,
        confirm_writes=body.confirm_writes,
        ip=client_ip(request, settings),
        idempotency_key=request.headers.get("idempotency-key"),
    )
    return success(run_payload(db, run), "执行任务已入队")


@router.get("/projects/{project_id}/runs")
def runs(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    from app.models.project import Project

    project = db.get(Project, project_id)
    name = project.name if project else None
    # 列表供轮询与表格使用，不返回结果响应体（明细页用 GET /runs/{run_id} 获取完整数据）。
    return success(
        {
            "items": [
                run_payload(db, item, project_name=name, with_response_body=False)
                for item in list_runs(db, user, project_id)
            ]
        }
    )


@router.get("/runs/{run_id}")
def run_detail(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    from app.models.project import Project

    run = get_run(db, user, run_id)
    project = db.get(Project, run.project_id)
    return success(run_payload(db, run, project_name=project.name if project else None))


@router.post("/runs/{run_id}/cancel")
def cancel(
    run_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    run = cancel_run(db, user, run_id, client_ip(request, settings))
    return success(run_payload(db, run), "已请求取消")


@router.get("/runs/{run_id}/report")
def report(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    return success(report_payload(report_for_run(db, user, run_id)))


@router.get("/projects/{project_id}/reports")
def reports(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    return success({"items": list_reports(db, user, project_id)})
