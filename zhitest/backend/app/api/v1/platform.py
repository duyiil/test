import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, get_db
from app.core.config import Settings, get_settings
from app.core.responses import success
from app.models.user import User
from app.modules.platform.service import (
    activate_environment,
    add_environment,
    add_member,
    archive_project,
    batch_review,
    confirm_openapi,
    create_suite,
    defect_payload,
    delete_environment,
    delete_project,
    dependency_demo,
    environment_payload,
    get_defect,
    list_defects,
    list_environments,
    list_members,
    list_notifications,
    list_schedule_events,
    list_schedules,
    list_suites,
    mark_all_notifications_read,
    mark_notification_read,
    notification_payload,
    preview_openapi,
    remove_member,
    report_html,
    restore_project,
    save_schedule,
    suite_versions,
    update_defect_status,
    update_member_role,
    update_schedule,
)
from app.modules.projects.service import get_owned_project
from app.modules.testing.service import create_run, report_for_run, report_payload

router = APIRouter()


class SuiteBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    case_ids: list[uuid.UUID] = Field(alias="caseIds")
    is_regression: bool = Field(default=False, alias="isRegression")

    model_config = {"populate_by_name": True}


class RunSuiteBody(BaseModel):
    confirm_writes: bool = Field(default=False, alias="confirmWrites")

    model_config = {"populate_by_name": True}


class OpenApiBody(BaseModel):
    document: str = Field(min_length=1)


class EnvBody(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    base_url: str = Field(alias="baseUrl")

    model_config = {"populate_by_name": True}


class MemberBody(BaseModel):
    username: str
    role: str = "tester"


class BatchBody(BaseModel):
    action: str
    version_ids: list[uuid.UUID] = Field(alias="versionIds")
    reason: str | None = None

    model_config = {"populate_by_name": True}


class DeleteBody(BaseModel):
    confirm: bool = False


class ScheduleBody(BaseModel):
    cron: str


class SchedulePatch(BaseModel):
    cron: str | None = None
    enabled: bool | None = None


class RoleBody(BaseModel):
    role: str


class DefectStatusBody(BaseModel):
    status: str


@router.post("/projects/{project_id}/openapi/preview")
def openapi_preview(
    project_id: uuid.UUID,
    body: OpenApiBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    get_owned_project(db, user, project_id)
    return success(preview_openapi(body.document))


@router.post("/projects/{project_id}/openapi/confirm")
async def openapi_confirm(
    project_id: uuid.UUID,
    body: OpenApiBody,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    return success(
        confirm_openapi(db, user, project_id, body.document, client_ip(request, settings)),
        "已保存接口版本",
    )


@router.get("/projects/{project_id}/suites")
def suites(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    return success({"items": list_suites(db, user, project_id)})


@router.post("/projects/{project_id}/suites", status_code=201)
def new_suite(
    project_id: uuid.UUID,
    body: SuiteBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    suite = create_suite(
        db,
        user,
        project_id,
        name=body.name,
        case_ids=body.case_ids,
        is_regression=body.is_regression,
    )
    return success({"id": str(suite.id), "name": suite.name, "isRegression": suite.is_regression}, "用例集已创建")


@router.post("/projects/{project_id}/dependency-demo", status_code=201)
def demo_dependency(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    return success(dependency_demo(db, user, project_id), "已创建依赖链示例")


@router.post("/suites/{suite_id}/runs", status_code=202)
def run_suite(
    suite_id: uuid.UUID,
    body: RunSuiteBody,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    from app.models.platform import Suite

    suite = db.get(Suite, suite_id)
    if suite is None:
        from app.core.errors import AppError

        raise AppError(404, "NOT_FOUND", "用例集不存在")
    versions = suite_versions(db, suite)
    run = create_run(
        db,
        user,
        suite.project_id,
        confirm_writes=body.confirm_writes,
        ip=client_ip(request, settings),
        versions=versions,
        suite_id=suite.id,
        idempotency_key=request.headers.get("idempotency-key"),
    )
    from app.modules.testing.service import run_payload

    return success(run_payload(db, run), "用例集已入队")


@router.post("/projects/{project_id}/environments", status_code=201)
def create_environment(
    project_id: uuid.UUID,
    body: EnvBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    env = add_environment(db, user, project_id, body.name, body.base_url)
    return success(environment_payload(env))


@router.get("/projects/{project_id}/environments")
def environments(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    return success({"items": list_environments(db, user, project_id)})


@router.delete("/projects/{project_id}/environments/{environment_id}")
def remove_environment(
    project_id: uuid.UUID,
    environment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    delete_environment(db, user, project_id, environment_id)
    return success({"deleted": True}, "环境已删除")


@router.post("/projects/{project_id}/environments/{environment_id}/activate")
def activate(
    project_id: uuid.UUID,
    environment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    activate_environment(db, user, project_id, environment_id)
    return success({"active": str(environment_id)}, "已切换环境")


@router.post("/projects/{project_id}/archive")
def archive(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    project = archive_project(db, user, project_id)
    return success({"id": str(project.id), "status": project.status}, "项目已归档")


@router.post("/projects/{project_id}/restore")
def restore(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    project = restore_project(db, user, project_id)
    return success({"id": str(project.id), "status": project.status}, "项目已恢复")


@router.post("/projects/{project_id}/delete")
def remove(
    project_id: uuid.UUID,
    body: DeleteBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    delete_project(db, user, project_id, confirm=body.confirm)
    return success({"deleted": True}, "项目已删除")


@router.get("/projects/{project_id}/members")
def members(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    return success(list_members(db, user, project_id))


@router.post("/projects/{project_id}/members", status_code=201)
def member(
    project_id: uuid.UUID,
    body: MemberBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    row = add_member(db, user, project_id, body.username, body.role)
    return success({"id": str(row.id), "role": row.role})


@router.post("/projects/{project_id}/members/{member_id}/role")
def member_role(
    project_id: uuid.UUID,
    member_id: uuid.UUID,
    body: RoleBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    row = update_member_role(db, user, project_id, member_id, body.role)
    return success({"id": str(row.id), "role": row.role}, "角色已更新")


@router.delete("/projects/{project_id}/members/{member_id}")
def member_remove(
    project_id: uuid.UUID,
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    remove_member(db, user, project_id, member_id)
    return success({"deleted": True}, "成员已移除")


@router.post("/projects/{project_id}/reviews/batch")
def batch(
    project_id: uuid.UUID,
    body: BatchBody,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    count = batch_review(
        db,
        user,
        project_id,
        action=body.action,
        version_ids=body.version_ids,
        reason=body.reason,
        ip=client_ip(request, settings),
    )
    return success({"count": count}, "批量审核已处理")


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    rows = list_notifications(db, user)
    items = [notification_payload(item) for item in rows]
    return success({"items": items, "unreadCount": sum(1 for item in items if item["readAt"] is None)})


@router.post("/notifications/{notification_id}/read")
def notification_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    item = mark_notification_read(db, user, notification_id)
    return success(notification_payload(item), "已标为已读")


@router.post("/notifications/read-all")
def notifications_read_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    count = mark_all_notifications_read(db, user)
    return success({"count": count}, "已全部标为已读")


@router.get("/projects/{project_id}/defects")
def defects(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    rows = list_defects(db, user, project_id)
    return success({"items": [defect_payload(item) for item in rows], "label": "候选缺陷，不是已确认缺陷或漏洞"})


@router.get("/defects/{defect_id}")
def defect_detail(defect_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    return success(defect_payload(get_defect(db, user, defect_id)))


@router.post("/defects/{defect_id}/status")
def defect_status(
    defect_id: uuid.UUID,
    body: DefectStatusBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    item = update_defect_status(db, user, defect_id, body.status)
    return success(defect_payload(item), "候选状态已更新")


@router.post("/suites/{suite_id}/schedules", status_code=201)
def schedule(
    suite_id: uuid.UUID,
    body: ScheduleBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    row = save_schedule(db, user, suite_id, body.cron)
    return success({"id": str(row.id), "cron": row.cron, "enabled": row.enabled, "note": "只保存计划。未验证系统级 cron 守护进程。"})


@router.get("/projects/{project_id}/schedules")
def schedules(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    return success({"items": list_schedules(db, user, project_id), "note": "只保存计划。未验证系统级 cron 守护进程。"})


@router.post("/schedules/{schedule_id}")
def schedule_update(
    schedule_id: uuid.UUID,
    body: SchedulePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    row = update_schedule(db, user, schedule_id, cron=body.cron, enabled=body.enabled)
    return success({"id": str(row.id), "cron": row.cron, "enabled": row.enabled}, "计划已更新")


@router.get("/schedules/{schedule_id}/events")
def schedule_events(schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, object]:
    return success({"items": list_schedule_events(db, user, schedule_id)})


@router.get("/runs/{run_id}/report/export")
def export_report(
    run_id: uuid.UUID,
    format: str = "json",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    report = report_for_run(db, user, run_id)
    if format == "html":
        return HTMLResponse(report_html(report.payload))
    return success(report_payload(report))


@router.post("/projects/{project_id}/target-check")
def target_check(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    from app.modules.platform.service import active_base_url
    from app.modules.testing.service import assert_base_url_allowed

    project = get_owned_project(db, user, project_id)
    url = active_base_url(db, project)
    assert_base_url_allowed(url)
    return success({"baseUrl": url, "allowed": True}, "目标通过 SSRF 检查")
