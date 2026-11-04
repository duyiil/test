from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.project import Project
from app.models.user import User
from app.modules.projects.service import project_payload


def dashboard_summary(db: Session, user: User) -> dict[str, object]:
    project_count = db.scalar(select(func.count()).select_from(Project).where(Project.owner_id == user.id)) or 0
    recent = db.scalars(
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.updated_at.desc())
        .limit(5)
    ).all()
    activities = db.scalars(
        select(AuditLog)
        .where(AuditLog.actor_id == user.id, AuditLog.action.like("project.%"))
        .order_by(AuditLog.created_at.desc())
        .limit(8)
    ).all()
    return {
        "projectCount": int(project_count),
        "caseCount": 0,
        "pendingReviewCount": 0,
        "failedCaseCount": 0,
        "passRate": None,
        "passRateText": "无可判定结果",
        "executionDataAvailable": False,
        "metricsNote": "Phase 1 尚未建立用例与执行表，用例和执行统计为当前库内真实空值，不是示例成功率。",
        "recentTasks": [],
        "recentProjects": [project_payload(item) for item in recent],
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
