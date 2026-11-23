from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.project import Project
from app.models.testing import TestCase, TestRun
from app.models.user import User
from app.modules.projects.service import project_payload
from app.modules.testing.service import latest_versions, pass_rate


def dashboard_summary(db: Session, user: User) -> dict[str, object]:
    project_count = db.scalar(select(func.count()).select_from(Project).where(Project.owner_id == user.id)) or 0
    recent = db.scalars(
        select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc()).limit(5)
    ).all()
    project_ids = [item.id for item in db.scalars(select(Project).where(Project.owner_id == user.id)).all()]
    case_count = 0
    pending = 0
    if project_ids:
        case_count = (
            db.scalar(select(func.count()).select_from(TestCase).where(TestCase.project_id.in_(project_ids))) or 0
        )
        for project_id in project_ids:
            for version in latest_versions(db, project_id):
                if version.review_status == "pending_review":
                    pending += 1
    runs = []
    if project_ids:
        runs = list(
            db.scalars(
                select(TestRun).where(TestRun.project_id.in_(project_ids)).order_by(TestRun.created_at.desc()).limit(5)
            ).all()
        )
    latest_terminal = next((item for item in runs if item.status in {"succeeded", "failed", "aborted", "cancelled"}), None)
    if latest_terminal is None:
        rate, text = None, "无可判定结果"
        failed_cases = 0
        execution_available = False
    else:
        rate, text = pass_rate(latest_terminal.passed_count, latest_terminal.assertion_failed_count)
        failed_cases = latest_terminal.assertion_failed_count
        execution_available = latest_terminal.passed_count + latest_terminal.assertion_failed_count > 0
    names = {item.id: item.name for item in recent}
    if runs:
        extra = db.scalars(select(Project).where(Project.id.in_([item.project_id for item in runs]))).all()
        names.update({item.id: item.name for item in extra})
    activities = db.scalars(
        select(AuditLog)
        .where(AuditLog.actor_id == user.id, AuditLog.action.like("project.%"))
        .order_by(AuditLog.created_at.desc())
        .limit(8)
    ).all()
    return {
        "projectCount": int(project_count),
        "caseCount": int(case_count),
        "pendingReviewCount": pending,
        "failedCaseCount": failed_cases,
        "passRate": rate,
        "passRateText": text,
        "executionDataAvailable": execution_available,
        "metricsNote": "统计来自当前账号的项目、用例和执行记录。没有可判定结果时不显示成功率。",
        "recentTasks": [
            {
                "id": str(item.id),
                "projectId": str(item.project_id),
                "projectName": names.get(item.project_id, ""),
                "status": item.status,
                "createdAt": item.created_at.isoformat(),
                "passRate": pass_rate(item.passed_count, item.assertion_failed_count)[0],
                "passRateText": pass_rate(item.passed_count, item.assertion_failed_count)[1],
            }
            for item in runs
        ],
        "recentProjects": [project_payload(item, db) for item in recent],
        "recentActivities": [
            {
                "id": str(item.id),
                "action": item.action,
                "resourceType": item.resource_type,
                "resourceId": item.resource_id,
                "detail": item.detail or {},
                "createdAt": item.created_at.isoformat(),
            }
            for item in activities
        ],
    }
