from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.project import Project
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
from app.modules.ai.demo_contract import DEMO_CONTRACT
from app.modules.ai.mock_provider import MockGenerationProvider
from app.modules.audit.service import write_audit
from app.modules.projects.service import get_owned_project

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ACTIVE_RUN = {"queued", "running", "cancelling"}
AI_MESSAGE = "未配置真实研判模型。这里只展示数据报告，不把 Mock 生成说成模型分析。"


def pass_rate(passed: int, assertion_failed: int) -> tuple[float | None, str]:
    denominator = passed + assertion_failed
    if denominator == 0:
        return None, "无可判定结果"
    rate = passed / denominator
    return rate, f"{round(rate * 100)}%"


def load_demo_contract(db: Session, user: User, project_id: uuid.UUID, ip: str | None) -> list[ApiEndpoint]:
    project = get_owned_project(db, user, project_id)
    created: list[ApiEndpoint] = []
    for item in DEMO_CONTRACT:
        method = str(item["method"])
        path = str(item["path"])
        existing = db.scalar(
            select(ApiEndpoint).where(
                ApiEndpoint.project_id == project.id,
                ApiEndpoint.method == method,
                ApiEndpoint.path == path,
            )
        )
        if existing is not None:
            created.append(existing)
            continue
        endpoint = ApiEndpoint(
            project_id=project.id,
            spec_version=1,
            method=method,
            path=path,
            summary=str(item.get("summary") or ""),
            contract=item,
            created_at=datetime.now(timezone.utc),
        )
        db.add(endpoint)
        db.flush()
        created.append(endpoint)
    write_audit(
        db,
        action="contract.demo_load",
        actor_id=user.id,
        resource_type="project",
        resource_id=str(project.id),
        detail={"count": len(created), "source": "author-demo-contract"},
        ip=ip,
    )
    return created


def endpoint_payload(endpoint: ApiEndpoint) -> dict[str, object]:
    return {
        "id": str(endpoint.id),
        "projectId": str(endpoint.project_id),
        "specVersion": endpoint.spec_version,
        "method": endpoint.method,
        "path": endpoint.path,
        "summary": endpoint.summary,
        "createdAt": endpoint.created_at.isoformat(),
    }


def list_endpoints(db: Session, user: User, project_id: uuid.UUID) -> list[ApiEndpoint]:
    get_owned_project(db, user, project_id)
    return list(
        db.scalars(
            select(ApiEndpoint).where(ApiEndpoint.project_id == project_id).order_by(ApiEndpoint.created_at)
        ).all()
    )


def create_generation_task(db: Session, user: User, project_id: uuid.UUID, ip: str | None) -> GenerationTask:
    project = get_owned_project(db, user, project_id)
    endpoints = list(db.scalars(select(ApiEndpoint).where(ApiEndpoint.project_id == project.id)).all())
    if not endpoints:
        raise AppError(422, "VALIDATION_ERROR", "项目还没有接口契约，无法生成用例")
    task = GenerationTask(
        project_id=project.id,
        status="queued",
        created_by=user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.flush()
    for endpoint in endpoints:
        db.add(GenerationTarget(task_id=task.id, endpoint_id=endpoint.id, status="queued", attempts=0))
    write_audit(
        db,
        action="generation.create",
        actor_id=user.id,
        resource_type="generation_task",
        resource_id=str(task.id),
        detail={"endpointCount": len(endpoints), "provider": "mock"},
        ip=ip,
    )
    return task


def generation_payload(db: Session, task: GenerationTask) -> dict[str, object]:
    targets = list(db.scalars(select(GenerationTarget).where(GenerationTarget.task_id == task.id)).all())
    return {
        "id": str(task.id),
        "projectId": str(task.project_id),
        "status": task.status,
        "provider": "mock",
        "targetCount": len(targets),
        "succeededCount": sum(1 for item in targets if item.status == "succeeded"),
        "failedCount": sum(1 for item in targets if item.status == "failed"),
        "error": task.error,
        "createdAt": task.created_at.isoformat(),
        "startedAt": task.started_at.isoformat() if task.started_at else None,
        "finishedAt": task.finished_at.isoformat() if task.finished_at else None,
        "targets": [
            {
                "id": str(item.id),
                "endpointId": str(item.endpoint_id),
                "status": item.status,
                "attempts": item.attempts,
                "error": item.error,
            }
            for item in targets
        ],
    }


def get_generation_task(db: Session, user: User, task_id: uuid.UUID) -> GenerationTask:
    task = db.get(GenerationTask, task_id)
    if task is None:
        raise AppError(404, "NOT_FOUND", "资源不存在")
    get_owned_project(db, user, task.project_id)
    return task


def latest_versions(db: Session, project_id: uuid.UUID) -> list[TestCaseVersion]:
    cases = list(db.scalars(select(TestCase).where(TestCase.project_id == project_id)).all())
    versions: list[TestCaseVersion] = []
    for case in cases:
        version = db.scalar(
            select(TestCaseVersion)
            .where(TestCaseVersion.case_id == case.id)
            .order_by(TestCaseVersion.version_number.desc())
            .limit(1)
        )
        if version is not None:
            versions.append(version)
    return versions


def version_payload(db: Session, version: TestCaseVersion) -> dict[str, object]:
    db.flush()
    case = db.get(TestCase, version.case_id)
    events = list(
        db.scalars(
            select(ReviewEvent).where(ReviewEvent.version_id == version.id).order_by(ReviewEvent.created_at)
        ).all()
    )
    history = list(
        db.scalars(
            select(TestCaseVersion)
            .where(TestCaseVersion.case_id == version.case_id)
            .order_by(TestCaseVersion.version_number)
        ).all()
    )
    return {
        "id": str(version.id),
        "caseId": str(version.case_id),
        "projectId": str(case.project_id) if case else None,
        "endpointId": str(case.endpoint_id) if case else None,
        "versionNumber": version.version_number,
        "specVersion": version.spec_version,
        "name": version.name,
        "description": version.description,
        "scenario": version.scenario,
        "basis": version.basis,
        "method": version.method,
        "relativePath": version.relative_path,
        "headers": version.headers,
        "query": version.query,
        "pathParams": version.path_params,
        "body": version.body,
        "timeout": version.timeout_seconds,
        "assertions": version.assertions,
        "reviewStatus": version.review_status,
        "enabled": version.enabled,
        "origin": version.origin,
        "createdAt": version.created_at.isoformat(),
        "events": [
            {
                "id": str(event.id),
                "action": event.action,
                "reason": event.reason,
                "actorId": str(event.actor_id) if event.actor_id else None,
                "createdAt": event.created_at.isoformat(),
            }
            for event in events
        ],
        "history": [
            {
                "id": str(item.id),
                "versionNumber": item.version_number,
                "reviewStatus": item.review_status,
                "name": item.name,
                "createdAt": item.created_at.isoformat(),
            }
            for item in history
        ],
    }


def list_cases(db: Session, user: User, project_id: uuid.UUID, review_status: str | None) -> list[dict[str, object]]:
    get_owned_project(db, user, project_id)
    rows = []
    for version in latest_versions(db, project_id):
        if review_status and version.review_status != review_status:
            continue
        rows.append(version_payload(db, version))
    return rows


def get_version_for_user(db: Session, user: User, version_id: uuid.UUID) -> TestCaseVersion:
    version = db.get(TestCaseVersion, version_id)
    if version is None:
        raise AppError(404, "NOT_FOUND", "资源不存在")
    case = db.get(TestCase, version.case_id)
    if case is None:
        raise AppError(404, "NOT_FOUND", "资源不存在")
    get_owned_project(db, user, case.project_id)
    return version


def _require_latest(db: Session, version: TestCaseVersion) -> None:
    latest = db.scalar(
        select(func.max(TestCaseVersion.version_number)).where(TestCaseVersion.case_id == version.case_id)
    )
    if latest != version.version_number:
        raise AppError(409, "CONFLICT", "只能操作该用例的最新版本")


def submit_review(db: Session, user: User, version_id: uuid.UUID, ip: str | None) -> TestCaseVersion:
    version = get_version_for_user(db, user, version_id)
    _require_latest(db, version)
    if version.review_status not in {"draft", "rejected"}:
        raise AppError(409, "CONFLICT", "当前状态不能提交审核")
    if not version.assertions:
        raise AppError(422, "VALIDATION_ERROR", "空断言用例不能提交审核")
    version.review_status = "pending_review"
    db.add(ReviewEvent(version_id=version.id, action="submit", actor_id=user.id, created_at=datetime.now(timezone.utc)))
    write_audit(db, action="case.submit", actor_id=user.id, resource_type="case_version", resource_id=str(version.id), ip=ip)
    return version


def approve_version(db: Session, user: User, version_id: uuid.UUID, ip: str | None) -> TestCaseVersion:
    version = get_version_for_user(db, user, version_id)
    _require_latest(db, version)
    if version.review_status != "pending_review":
        raise AppError(409, "CONFLICT", "只有待审核用例可以通过")
    if not version.assertions:
        raise AppError(422, "VALIDATION_ERROR", "空断言用例不能通过审核")
    version.review_status = "confirmed"
    now = datetime.now(timezone.utc)
    db.add(ReviewEvent(version_id=version.id, action="approve", actor_id=user.id, created_at=now))
    write_audit(
        db,
        action="case.approve",
        actor_id=user.id,
        resource_type="case_version",
        resource_id=str(version.id),
        detail={"version": version.version_number, "reviewerId": str(user.id)},
        ip=ip,
    )
    return version


def reject_version(db: Session, user: User, version_id: uuid.UUID, reason: str, ip: str | None) -> TestCaseVersion:
    text = reason.strip()
    if not text:
        raise AppError(422, "VALIDATION_ERROR", "驳回必须填写原因")
    version = get_version_for_user(db, user, version_id)
    _require_latest(db, version)
    if version.review_status != "pending_review":
        raise AppError(409, "CONFLICT", "只有待审核用例可以驳回")
    version.review_status = "rejected"
    db.add(
        ReviewEvent(
            version_id=version.id,
            action="reject",
            reason=text,
            actor_id=user.id,
            created_at=datetime.now(timezone.utc),
        )
    )
    write_audit(
        db,
        action="case.reject",
        actor_id=user.id,
        resource_type="case_version",
        resource_id=str(version.id),
        detail={"reason": text},
        ip=ip,
    )
    return version


def edit_version(
    db: Session,
    user: User,
    version_id: uuid.UUID,
    *,
    name: str | None,
    description: str | None,
    assertions: list[dict[str, Any]] | None,
    ip: str | None,
) -> TestCaseVersion:
    current = get_version_for_user(db, user, version_id)
    _require_latest(db, current)
    next_status = "pending_review" if current.review_status == "confirmed" else "draft"
    latest_number = db.scalar(
        select(func.max(TestCaseVersion.version_number)).where(TestCaseVersion.case_id == current.case_id)
    )
    created = TestCaseVersion(
        case_id=current.case_id,
        version_number=int(latest_number or 1) + 1,
        spec_version=current.spec_version,
        name=(name or current.name).strip(),
        description=current.description if description is None else description.strip(),
        scenario=current.scenario,
        basis=current.basis,
        method=current.method,
        relative_path=current.relative_path,
        headers=current.headers,
        query=current.query,
        path_params=current.path_params,
        body=current.body,
        timeout_seconds=current.timeout_seconds,
        assertions=current.assertions if assertions is None else assertions,
        review_status=next_status,
        enabled=True,
        origin=current.origin,
        created_by=user.id,
        created_at=datetime.now(timezone.utc),
    )
    if not created.name:
        raise AppError(422, "VALIDATION_ERROR", "用例名称不能为空")
    db.add(created)
    db.flush()
    db.add(
        ReviewEvent(
            version_id=created.id,
            action="edit",
            actor_id=user.id,
            reason="可执行内容变更产生新版本",
            created_at=datetime.now(timezone.utc),
        )
    )
    write_audit(
        db,
        action="case.edit",
        actor_id=user.id,
        resource_type="case_version",
        resource_id=str(created.id),
        detail={"fromVersion": current.version_number, "reviewStatus": next_status},
        ip=ip,
    )
    return created


def executable_versions(db: Session, project_id: uuid.UUID) -> list[TestCaseVersion]:
    chosen: list[TestCaseVersion] = []
    for version in latest_versions(db, project_id):
        if version.review_status == "confirmed" and version.enabled and version.assertions:
            chosen.append(version)
    return chosen


def create_run(db: Session, user: User, project_id: uuid.UUID, *, confirm_writes: bool, ip: str | None) -> TestRun:
    project = get_owned_project(db, user, project_id)
    assert_base_url_allowed(project.base_url)
    active = db.scalar(
        select(TestRun).where(TestRun.project_id == project.id, TestRun.status.in_(ACTIVE_RUN)).limit(1)
    )
    if active is not None:
        raise AppError(409, "RUN_IN_PROGRESS", "该项目已有未结束的执行任务")
    versions = executable_versions(db, project.id)
    if not versions:
        raise AppError(422, "VALIDATION_ERROR", "没有已确认且带断言的用例可执行")
    writes = [item for item in versions if item.method in WRITE_METHODS]
    if writes and not confirm_writes:
        raise AppError(
            409,
            "WRITE_CONFIRMATION_REQUIRED",
            f"该执行包含 {len(writes)} 条写操作用例，确认后才会入队",
            details={
                "operations": [
                    {"name": item.name, "method": item.method, "path": item.relative_path} for item in writes
                ]
            },
        )
    snapshot = {
        "baseUrl": project.base_url,
        "envLabel": project.env_label,
        "caseVersionIds": [str(item.id) for item in versions],
        "specVersions": sorted({item.spec_version for item in versions}),
        "provider": "mock",
    }
    run = TestRun(
        project_id=project.id,
        status="queued",
        snapshot=snapshot,
        total_count=len(versions),
        confirm_writes=confirm_writes,
        created_by=user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    write_audit(
        db,
        action="run.create",
        actor_id=user.id,
        resource_type="test_run",
        resource_id=str(run.id),
        detail={"total": len(versions), "writes": len(writes)},
        ip=ip,
    )
    return run


def assert_base_url_allowed(base_url: str) -> None:
    host = (urlsplit(base_url).hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise AppError(403, "FORBIDDEN", "Phase 2 只允许把测试发到本机演示地址")


def list_runs(db: Session, user: User, project_id: uuid.UUID) -> list[TestRun]:
    get_owned_project(db, user, project_id)
    return list(
        db.scalars(select(TestRun).where(TestRun.project_id == project_id).order_by(TestRun.created_at.desc())).all()
    )


def get_run(db: Session, user: User, run_id: uuid.UUID) -> TestRun:
    run = db.get(TestRun, run_id)
    if run is None:
        raise AppError(404, "NOT_FOUND", "资源不存在")
    get_owned_project(db, user, run.project_id)
    return run


def run_payload(db: Session, run: TestRun, *, project_name: str | None = None) -> dict[str, object]:
    rate, text = pass_rate(run.passed_count, run.assertion_failed_count)
    results = list(db.scalars(select(RunResult).where(RunResult.run_id == run.id).order_by(RunResult.ordinal)).all())
    return {
        "id": str(run.id),
        "projectId": str(run.project_id),
        "projectName": project_name,
        "status": run.status,
        "totalCount": run.total_count,
        "executedCount": run.executed_count,
        "passedCount": run.passed_count,
        "assertionFailedCount": run.assertion_failed_count,
        "executionErrorCount": run.execution_error_count,
        "skippedCount": run.skipped_count,
        "passRate": rate,
        "passRateText": text,
        "confirmWrites": run.confirm_writes,
        "abortReason": run.abort_reason,
        "snapshot": run.snapshot,
        "createdAt": run.created_at.isoformat(),
        "startedAt": run.started_at.isoformat() if run.started_at else None,
        "finishedAt": run.finished_at.isoformat() if run.finished_at else None,
        "results": [
            {
                "id": str(item.id),
                "caseVersionId": str(item.case_version_id),
                "ordinal": item.ordinal,
                "status": item.status,
                "request": item.request,
                "responseStatus": item.response_status,
                "responseBody": item.response_body,
                "errorClass": item.error_class,
                "errorMessage": item.error_message,
                "assertionResults": item.assertion_results,
                "attemptCount": item.attempt_count,
            }
            for item in results
        ],
    }


def cancel_run(db: Session, user: User, run_id: uuid.UUID, ip: str | None) -> TestRun:
    run = get_run(db, user, run_id)
    if run.status in {"succeeded", "failed", "aborted", "cancelled"}:
        raise AppError(409, "CONFLICT", "任务已结束，不能取消")
    if run.status == "queued":
        run.status = "cancelled"
        run.finished_at = datetime.now(timezone.utc)
        run.abort_reason = "用户取消"
        _write_report(db, run)
    else:
        run.status = "cancelling"
        run.cancel_requested = True
    write_audit(db, action="run.cancel", actor_id=user.id, resource_type="test_run", resource_id=str(run.id), ip=ip)
    return run


def report_for_run(db: Session, user: User, run_id: uuid.UUID) -> DataReport:
    run = get_run(db, user, run_id)
    report = db.scalar(select(DataReport).where(DataReport.run_id == run.id))
    if report is None:
        raise AppError(404, "NOT_FOUND", "报告尚未生成")
    return report


def report_payload(report: DataReport) -> dict[str, object]:
    return {
        "id": str(report.id),
        "runId": str(report.run_id),
        "aiStatus": report.ai_status,
        "aiMessage": report.ai_message,
        "createdAt": report.created_at.isoformat(),
        "data": report.payload,
    }


def list_reports(db: Session, user: User, project_id: uuid.UUID) -> list[dict[str, object]]:
    get_owned_project(db, user, project_id)
    runs = list(db.scalars(select(TestRun.id).where(TestRun.project_id == project_id)).all())
    if not runs:
        return []
    reports = list(
        db.scalars(select(DataReport).where(DataReport.run_id.in_(runs)).order_by(DataReport.created_at.desc())).all()
    )
    return [report_payload(item) for item in reports]


def _write_report(db: Session, run: TestRun) -> DataReport:
    existing = db.scalar(select(DataReport).where(DataReport.run_id == run.id))
    if existing is not None:
        return existing
    rate, text = pass_rate(run.passed_count, run.assertion_failed_count)
    results = list(db.scalars(select(RunResult).where(RunResult.run_id == run.id).order_by(RunResult.ordinal)).all())
    payload = {
        "runId": str(run.id),
        "projectId": str(run.project_id),
        "status": run.status,
        "snapshot": run.snapshot,
        "totalCount": run.total_count,
        "executedCount": run.executed_count,
        "passedCount": run.passed_count,
        "assertionFailedCount": run.assertion_failed_count,
        "executionErrorCount": run.execution_error_count,
        "skippedCount": run.skipped_count,
        "passRate": rate,
        "passRateText": text,
        "abortReason": run.abort_reason,
        "finishedAt": run.finished_at.isoformat() if run.finished_at else None,
        "results": [
            {
                "caseVersionId": str(item.case_version_id),
                "status": item.status,
                "responseStatus": item.response_status,
                "errorClass": item.error_class,
                "errorMessage": item.error_message,
                "assertionResults": item.assertion_results,
                "request": item.request,
                "responseBody": item.response_body,
            }
            for item in results
        ],
    }
    report = DataReport(
        run_id=run.id,
        payload=payload,
        ai_status="unavailable",
        ai_message=AI_MESSAGE,
        created_at=datetime.now(timezone.utc),
    )
    db.add(report)
    db.flush()
    return report


def validate_generated_case(case: dict[str, Any], contract: dict[str, Any]) -> None:
    method = str(case.get("method") or "")
    if method not in METHODS:
        raise ValueError("无效请求方法")
    if not case.get("assertions"):
        raise ValueError("无断言用例")
    if case.get("relativePath") != contract.get("path"):
        raise ValueError("用例引用了不存在的接口路径")
    blob = str(case)
    if "{{" in blob:
        raise ValueError("存在未声明变量")


def process_generation_task(db: Session, task_id: uuid.UUID, provider: MockGenerationProvider | None = None) -> None:
    provider = provider or MockGenerationProvider()
    task = db.get(GenerationTask, task_id)
    if task is None:
        return
    if task.status == "queued":
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        db.commit()
    elif task.status != "running":
        return
    project = db.get(Project, task.project_id)
    target_ids = list(
        db.scalars(select(GenerationTarget.id).where(GenerationTarget.task_id == task.id, GenerationTarget.status == "queued")).all()
    )
    for target_id in target_ids:
        last_error = ""
        saved = False
        for _attempt in (1, 2):
            target = db.get(GenerationTarget, target_id)
            endpoint = db.get(ApiEndpoint, target.endpoint_id) if target else None
            if target is None or endpoint is None or project is None:
                last_error = "接口不存在"
                break
            target.attempts += 1
            db.commit()
            try:
                drafted = provider.generate(project_name=project.name, contract=endpoint.contract)
                if not drafted:
                    raise ValueError("生成结果为空")
                for item in drafted:
                    validate_generated_case(item, endpoint.contract)
                    _store_draft(db, project, endpoint, item, task.created_by)
                current = db.get(GenerationTarget, target_id)
                if current is None:
                    raise ValueError("生成目标丢失")
                current.status = "succeeded"
                current.error = None
                db.commit()
                saved = True
                break
            except Exception as exc:
                db.rollback()
                last_error = str(exc)
        if not saved:
            current = db.get(GenerationTarget, target_id)
            if current is not None and current.status != "succeeded":
                current.status = "failed"
                current.error = last_error[:500]
                db.commit()
    task = db.get(GenerationTask, task_id)
    if task is None:
        return
    failed = db.scalar(
        select(func.count()).select_from(GenerationTarget).where(
            GenerationTarget.task_id == task.id, GenerationTarget.status == "failed"
        )
    )
    succeeded = db.scalar(
        select(func.count()).select_from(GenerationTarget).where(
            GenerationTarget.task_id == task.id, GenerationTarget.status == "succeeded"
        )
    )
    task.status = "failed" if succeeded == 0 and failed else "succeeded"
    task.error = "部分接口生成失败" if failed and succeeded else None
    task.finished_at = datetime.now(timezone.utc)
    db.commit()


def _store_draft(db: Session, project: Project, endpoint: ApiEndpoint, item: dict[str, Any], user_id: uuid.UUID) -> None:
    case = TestCase(project_id=project.id, endpoint_id=endpoint.id, created_at=datetime.now(timezone.utc))
    db.add(case)
    db.flush()
    db.add(
        TestCaseVersion(
            case_id=case.id,
            version_number=1,
            spec_version=endpoint.spec_version,
            name=str(item["name"])[:200],
            description=str(item.get("description") or ""),
            scenario=str(item.get("scenario") or ""),
            basis=str(item.get("basis") or ""),
            method=str(item["method"]),
            relative_path=str(item["relativePath"]),
            headers=item.get("headers") or {},
            query=item.get("query") or {},
            path_params=item.get("pathParams") or {},
            body=item.get("body"),
            timeout_seconds=int(item.get("timeout") or 30),
            assertions=list(item.get("assertions") or []),
            review_status="draft",
            enabled=True,
            origin=str(item.get("origin") or "mock"),
            created_by=user_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.flush()


def claim_generation_task(db: Session) -> uuid.UUID | None:
    task = db.scalar(
        select(GenerationTask)
        .where(GenerationTask.status == "queued")
        .order_by(GenerationTask.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if task is None:
        return None
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    task_id = task.id
    db.commit()
    return task_id


def claim_run(db: Session, worker_id: str) -> uuid.UUID | None:
    run = db.scalar(
        select(TestRun)
        .where(TestRun.status == "queued")
        .order_by(TestRun.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if run is None:
        return None
    run.status = "running"
    run.worker_id = worker_id
    run.started_at = datetime.now(timezone.utc)
    db.commit()
    return run.id
