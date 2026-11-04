"""导入模型，保证元数据注册完整。"""

from app.models.audit import AuditLog
from app.models.platform import (
    DefectCandidate,
    IdempotencyRecord,
    Notification,
    ProjectEnvironment,
    ProjectMember,
    Schedule,
    ScheduleEvent,
    Suite,
    SuiteItem,
)
from app.models.project import Project
from app.models.session import UserSession
from app.models.testing import (
    ApiEndpoint,
    DataReport,
    GenerationTarget,
    GenerationTask,
    ReviewEvent,
    RunResult,
    TestCase,
    TestCaseVersion,
    TestRun,
)
from app.models.user import User

__all__ = [
    "ApiEndpoint",
    "DefectCandidate",
    "IdempotencyRecord",
    "Notification",
    "ProjectEnvironment",
    "ProjectMember",
    "Schedule",
    "ScheduleEvent",
    "Suite",
    "SuiteItem",
    "AuditLog",
    "DataReport",
    "GenerationTarget",
    "GenerationTask",
    "Project",
    "ReviewEvent",
    "RunResult",
    "TestCase",
    "TestCaseVersion",
    "TestRun",
    "User",
    "UserSession",
]
