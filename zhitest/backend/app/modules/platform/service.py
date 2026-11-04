from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.errors import AppError
from app.models.platform import (
    DefectCandidate,
    IdempotencyRecord,
    Notification,
    ProjectEnvironment,
    ProjectMember,
    Schedule,
    Suite,
    SuiteItem,
)
from app.models.project import Project
from app.models.testing import ApiEndpoint, RunResult, TestCase, TestCaseVersion, TestRun
from app.models.user import User
from app.modules.audit.service import write_audit
from app.modules.projects.service import get_owned_project, validate_base_url
from app.modules.testing.service import (
    ACTIVE_RUN,
    WRITE_METHODS,
    _create_run_body,
    executable_versions,
    latest_versions,
)

_IDEMPOTENCY_HOURS = 24


def prepare_run(
    db: Session,
    user: User,
    project_id: uuid.UUID,
    *,
    confirm_writes: bool,
    ip: str | None,
    versions: list[TestCaseVersion] | None,
    suite_id: uuid.UUID | None,
    idempotency_key: str | None,
) -> TestRun:
    project = get_owned_project(db, user, project_id)
    _reject_archived(project)
    _reject_readonly(db, user, project)
    chosen = versions if versions is not None else executable_versions(db, project.id)
    base_url = active_base_url(db, project)
    digest = _request_hash(project.id, suite_id, confirm_writes, [str(item.id) for item in chosen])
    if idempotency_key:
        existing = _idempotent_run(db, user, idempotency_key, digest)
        if existing is not None:
            return existing
    run = _create_run_body(
        db,
        user,
        project,
        chosen,
        confirm_writes=confirm_writes,
        ip=ip,
        suite_id=suite_id,
        base_url=base_url,
    )
    if idempotency_key:
        run.idempotency_key = idempotency_key[:128]
        db.add(
            IdempotencyRecord(
                user_id=user.id,
                idem_key=idempotency_key[:200],
                request_hash=digest,
                run_id=run.id,
                expires_at=utcnow() + timedelta(hours=_IDEMPOTENCY_HOURS),
            )
        )
        db.flush()
    return run


def active_base_url(db: Session, project: Project) -> str:
    env = db.scalar(
        select(ProjectEnvironment).where(
            ProjectEnvironment.project_id == project.id,
            ProjectEnvironment.is_active.is_(True),
        )
    )
    return env.base_url if env is not None else project.base_url


def preview_openapi(raw: str) -> dict[str, Any]:
    from app.modules.ai.openapi_parser import parse_openapi_document

    try:
        return parse_openapi_document(raw)
    except ValueError as exc:
        raise AppError(422, "VALIDATION_ERROR", str(exc)) from exc


def confirm_openapi(db: Session, user: User, project_id: uuid.UUID, raw: str, ip: str | None) -> dict[str, Any]:
    project = get_owned_project(db, user, project_id)
    parsed = preview_openapi(raw)
    incoming = parsed["endpoints"]
    seen: set[tuple[str, str]] = set()
    saved = 0
    for item in incoming:
        key = (str(item["method"]), str(item["path"]))
        seen.add(key)
        endpoint = db.scalar(
            select(ApiEndpoint).where(
                ApiEndpoint.project_id == project.id,
                ApiEndpoint.method == key[0],
                ApiEndpoint.path == key[1],
            )
        )
        if endpoint is None:
            endpoint = ApiEndpoint(
                project_id=project.id,
                spec_version=1,
                method=key[0],
                path=key[1],
                summary=str(item.get("summary") or "")[:200],
                contract=item,
                disabled=False,
                created_at=utcnow(),
            )
            db.add(endpoint)
        else:
            endpoint.spec_version += 1
            endpoint.contract = item
            endpoint.summary = str(item.get("summary") or "")[:200]
            endpoint.disabled = False
            _mark_cases_for_review(db, endpoint)
        saved += 1
    db.flush()
    existing = list(db.scalars(select(ApiEndpoint).where(ApiEndpoint.project_id == project.id)).all())
    disabled = 0
    for endpoint in existing:
        if (endpoint.method, endpoint.path) not in seen and not endpoint.disabled:
            endpoint.disabled = True
            disabled += 1
    write_audit(
        db,
        action="openapi.confirm",
        actor_id=user.id,
        resource_type="project",
        resource_id=str(project.id),
        detail={"saved": saved, "disabled": disabled, "errors": len(parsed["errors"])},
        ip=ip,
    )
    return {"saved": saved, "disabled": disabled, "errors": parsed["errors"]}


def _mark_cases_for_review(db: Session, endpoint: ApiEndpoint) -> None:
    cases = list(db.scalars(select(TestCase).where(TestCase.endpoint_id == endpoint.id)).all())
    for case in cases:
        latest = db.scalar(
            select(TestCaseVersion)
            .where(TestCaseVersion.case_id == case.id)
            .order_by(TestCaseVersion.version_number.desc())
            .limit(1)
        )
        if latest is None or latest.review_status != "confirmed":
            continue
        db.add(
            TestCaseVersion(
                case_id=case.id,
                version_number=latest.version_number + 1,
                spec_version=endpoint.spec_version,
                name=latest.name,
                description=latest.description,
                scenario=latest.scenario,
                basis="接口契约已更新，需要重新审核。历史执行仍指向旧版本。",
                method=latest.method,
                relative_path=latest.relative_path,
                headers=latest.headers,
                query=latest.query,
                path_params=latest.path_params,
                body=latest.body,
                timeout_seconds=latest.timeout_seconds,
                assertions=latest.assertions,
                extract=list(latest.extract or []),
                dependencies=list(latest.dependencies or []),
                review_status="pending_review",
                enabled=True,
                origin=latest.origin,
                created_by=latest.created_by,
                created_at=utcnow(),
            )
        )


def create_suite(
    db: Session,
    user: User,
    project_id: uuid.UUID,
    *,
    name: str,
    case_ids: list[uuid.UUID],
    is_regression: bool,
) -> Suite:
    project = get_owned_project(db, user, project_id)
    if not name.strip():
        raise AppError(422, "VALIDATION_ERROR", "用例集名称不能为空")
    suite = Suite(project_id=project.id, name=name.strip(), is_regression=is_regression, created_at=utcnow())
    db.add(suite)
    db.flush()
    for index, case_id in enumerate(case_ids):
        case = db.get(TestCase, case_id)
        if case is None or case.project_id != project.id:
            raise AppError(404, "NOT_FOUND", "用例不存在")
        db.add(SuiteItem(suite_id=suite.id, case_id=case.id, position=index))
    db.flush()
    return suite


def suite_versions(db: Session, suite: Suite) -> list[TestCaseVersion]:
    items = list(
        db.scalars(select(SuiteItem).where(SuiteItem.suite_id == suite.id).order_by(SuiteItem.position)).all()
    )
    versions: list[TestCaseVersion] = []
    for item in items:
        version = db.scalar(
            select(TestCaseVersion)
            .where(TestCaseVersion.case_id == item.case_id)
            .order_by(TestCaseVersion.version_number.desc())
            .limit(1)
        )
        if version is None or version.review_status != "confirmed" or not version.assertions:
            raise AppError(422, "VALIDATION_ERROR", "用例集包含未确认或空断言用例")
        versions.append(version)
    return versions


def list_suites(db: Session, user: User, project_id: uuid.UUID) -> list[dict[str, Any]]:
    get_owned_project(db, user, project_id)
    suites = list(db.scalars(select(Suite).where(Suite.project_id == project_id).order_by(Suite.created_at)).all())
    payload = []
    for suite in suites:
        items = list(
            db.scalars(select(SuiteItem).where(SuiteItem.suite_id == suite.id).order_by(SuiteItem.position)).all()
        )
        payload.append(
            {
                "id": str(suite.id),
                "name": suite.name,
                "isRegression": suite.is_regression,
                "caseIds": [str(item.case_id) for item in items],
            }
        )
    return payload


def add_environment(db: Session, user: User, project_id: uuid.UUID, name: str, base_url: str) -> ProjectEnvironment:
    project = get_owned_project(db, user, project_id)
    env = ProjectEnvironment(
        project_id=project.id,
        name=name.strip(),
        base_url=validate_base_url(base_url),
        is_active=False,
        created_at=utcnow(),
    )
    db.add(env)
    db.flush()
    return env


def activate_environment(db: Session, user: User, project_id: uuid.UUID, environment_id: uuid.UUID) -> None:
    get_owned_project(db, user, project_id)
    rows = list(db.scalars(select(ProjectEnvironment).where(ProjectEnvironment.project_id == project_id)).all())
    found = False
    for row in rows:
        row.is_active = row.id == environment_id
        found = found or row.is_active
    if not found:
        raise AppError(404, "NOT_FOUND", "环境不存在")


def archive_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = get_owned_project(db, user, project_id)
    project.status = "archived"
    return project


def delete_project(db: Session, user: User, project_id: uuid.UUID, *, confirm: bool) -> None:
    project = get_owned_project(db, user, project_id)
    if not confirm:
        raise AppError(422, "VALIDATION_ERROR", "删除项目需要确认")
    active = db.scalar(select(TestRun).where(TestRun.project_id == project.id, TestRun.status.in_(ACTIVE_RUN)))
    if active is not None:
        raise AppError(409, "RUN_IN_PROGRESS", "存在活动任务，不能删除项目")
    db.delete(project)


def add_member(db: Session, user: User, project_id: uuid.UUID, username: str, role: str) -> ProjectMember:
    project = get_owned_project(db, user, project_id)
    if role not in {"tester", "readonly"}:
        raise AppError(422, "VALIDATION_ERROR", "角色只能是 tester 或 readonly")
    member_user = db.scalar(select(User).where(User.username == username.strip()))
    if member_user is None:
        raise AppError(404, "NOT_FOUND", "用户不存在")
    row = ProjectMember(project_id=project.id, user_id=member_user.id, role=role, created_at=utcnow())
    db.add(row)
    db.flush()
    return row


def batch_review(
    db: Session,
    user: User,
    project_id: uuid.UUID,
    *,
    action: str,
    version_ids: list[uuid.UUID],
    reason: str | None,
    ip: str | None,
) -> int:
    from app.modules.testing.service import approve_version, reject_version

    get_owned_project(db, user, project_id)
    count = 0
    for version_id in version_ids:
        if action == "approve":
            approve_version(db, user, version_id, ip)
        elif action == "reject":
            reject_version(db, user, version_id, reason or "", ip)
        else:
            raise AppError(422, "VALIDATION_ERROR", "批量操作只支持通过或驳回")
        count += 1
    return count


def list_notifications(db: Session, user: User) -> list[Notification]:
    return list(
        db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(30)).all()
    )


def notify(db: Session, user_id: uuid.UUID | None, title: str, body: str) -> None:
    if user_id is None:
        return
    db.add(Notification(user_id=user_id, title=title, body=body, created_at=utcnow()))


def record_defect_candidates(db: Session, run: TestRun) -> int:
    results = list(db.scalars(select(RunResult).where(RunResult.run_id == run.id, RunResult.status == "assertion_failed")).all())
    created = 0
    for result in results:
        db.add(
            DefectCandidate(
                project_id=run.project_id,
                run_id=run.id,
                title="断言失败候选",
                status="candidate",
                detail={
                    "note": "这是失败候选，不是已确认漏洞。",
                    "responseStatus": result.response_status,
                    "errorClass": result.error_class,
                    "errorMessage": result.error_message,
                },
                created_at=utcnow(),
            )
        )
        created += 1
    return created


def list_defects(db: Session, user: User, project_id: uuid.UUID) -> list[DefectCandidate]:
    get_owned_project(db, user, project_id)
    return list(
        db.scalars(select(DefectCandidate).where(DefectCandidate.project_id == project_id).order_by(DefectCandidate.created_at.desc())).all()
    )


def save_schedule(db: Session, user: User, suite_id: uuid.UUID, cron: str) -> Schedule:
    suite = db.get(Suite, suite_id)
    if suite is None:
        raise AppError(404, "NOT_FOUND", "用例集不存在")
    get_owned_project(db, user, suite.project_id)
    parts = cron.split()
    if len(parts) != 5:
        raise AppError(422, "VALIDATION_ERROR", "cron 需要 5 段")
    row = Schedule(suite_id=suite.id, cron=cron, enabled=True, next_run_at=utcnow(), created_at=utcnow())
    db.add(row)
    db.flush()
    return row


def dispatch_due_schedules(db: Session, user: User) -> int:
    """只处理已经到期的记录。这里不声称系统 cron 已在后台持续运行。"""

    due = list(
        db.scalars(select(Schedule).where(Schedule.enabled.is_(True), Schedule.next_run_at.is_not(None), Schedule.next_run_at <= utcnow())).all()
    )
    count = 0
    for item in due:
        suite = db.get(Suite, item.suite_id)
        if suite is None:
            continue
        try:
            versions = suite_versions(db, suite)
            prepare_run(
                db,
                user,
                suite.project_id,
                confirm_writes=False,
                ip=None,
                versions=versions,
                suite_id=suite.id,
                idempotency_key=None,
            )
            count += 1
        except AppError:
            pass
        item.next_run_at = None
    return count


def dependency_demo(db: Session, user: User, project_id: uuid.UUID) -> dict[str, str]:
    project = get_owned_project(db, user, project_id)
    endpoint = db.scalar(select(ApiEndpoint).where(ApiEndpoint.project_id == project.id, ApiEndpoint.method == "POST"))
    detail = db.scalar(
        select(ApiEndpoint).where(ApiEndpoint.project_id == project.id, ApiEndpoint.path == "/api/products/{id}")
    )
    if endpoint is None or detail is None:
        raise AppError(422, "VALIDATION_ERROR", "请先载入包含创建和详情接口的契约")
    first_case = TestCase(project_id=project.id, endpoint_id=endpoint.id, created_at=utcnow())
    second_case = TestCase(project_id=project.id, endpoint_id=detail.id, created_at=utcnow())
    db.add(first_case)
    db.add(second_case)
    db.flush()
    first = TestCaseVersion(
        case_id=first_case.id,
        version_number=1,
        spec_version=endpoint.spec_version,
        name="创建商品并提取编号",
        description="从响应提取 productId，供后续用例使用。",
        scenario="依赖链",
        basis="契约声明创建成功返回 201，响应含 id。",
        method="POST",
        relative_path="/api/products",
        headers={},
        query={},
        path_params={},
        body={"name": "依赖商品", "price": 10.5},
        timeout_seconds=30,
        assertions=[{"type": "statusCode", "expected": 201}],
        extract=[{"name": "productId", "path": "id"}],
        dependencies=[],
        review_status="confirmed",
        enabled=True,
        origin="manual",
        created_by=user.id,
        created_at=utcnow(),
    )
    second = TestCaseVersion(
        case_id=second_case.id,
        version_number=1,
        spec_version=detail.spec_version,
        name="用提取的编号查询商品",
        description="路径使用 {{productId}}。",
        scenario="依赖链",
        basis="前置步骤提取 productId。本用例不写死演示服务里的缺陷。",
        method="GET",
        relative_path="/api/products/{{productId}}",
        headers={},
        query={},
        path_params={},
        body=None,
        timeout_seconds=30,
        assertions=[{"type": "statusCode", "expected": 200}],
        extract=[],
        dependencies=[str(first_case.id)],
        review_status="confirmed",
        enabled=True,
        origin="manual",
        created_by=user.id,
        created_at=utcnow(),
    )
    db.add(first)
    db.add(second)
    db.flush()
    suite = create_suite(
        db,
        user,
        project.id,
        name="依赖链示例",
        case_ids=[first_case.id, second_case.id],
        is_regression=False,
    )
    return {"suiteId": str(suite.id), "firstCaseId": str(first_case.id), "secondCaseId": str(second_case.id)}


def recover_stale_runs(db: Session) -> int:
    from app.modules.testing.service import _write_report

    now = utcnow()
    stale = list(
        db.scalars(select(TestRun).where(TestRun.status == "running", TestRun.lease_expires_at.is_not(None), TestRun.lease_expires_at < now)).all()
    )
    recovered = 0
    for run in stale:
        saved = {
            str(item.case_version_id)
            for item in db.scalars(select(RunResult).where(RunResult.run_id == run.id)).all()
        }
        remaining = [item for item in run.snapshot.get("caseVersionIds", []) if item not in saved]
        unknown = False
        if remaining:
            version = db.get(TestCaseVersion, uuid.UUID(str(remaining[0])))
            if version is not None and version.method in WRITE_METHODS:
                db.add(
                    RunResult(
                        run_id=run.id,
                        case_version_id=version.id,
                        ordinal=len(saved) + 1,
                        status="execution_error",
                        request={"method": version.method, "url": version.relative_path},
                        response_status=None,
                        response_body=None,
                        error_class="unknown",
                        error_message="写请求结果未知，禁止自动重放",
                        assertion_results=[],
                        attempt_count=1,
                        created_at=now,
                    )
                )
                run.execution_error_count += 1
                remaining = remaining[1:]
                unknown = True
        snapshot = dict(run.snapshot)
        snapshot["caseVersionIds"] = remaining
        run.snapshot = snapshot
        run.worker_id = None
        run.lease_expires_at = None
        if remaining:
            run.status = "queued"
        else:
            run.status = "failed" if unknown else "succeeded"
            run.abort_reason = "Worker 失联后已恢复。未知结果的写请求没有重放。" if unknown else None
            run.finished_at = now
            _write_report(db, run)
        recovered += 1
    return recovered


def report_html(payload: dict[str, Any]) -> str:
    rows = []
    for item in payload.get("results") or []:
        request = item.get("request") or {}
        rows.append(
            f"<li>{request.get('method', '')} {request.get('url', '')} {item.get('status')} {item.get('errorMessage') or ''}</li>"
        )
    return (
        "<html><body><h1>数据报告</h1>"
        f"<p>通过率 {payload.get('passRateText')}</p><ul>{''.join(rows)}</ul></body></html>"
    )


def _reject_archived(project: Project) -> None:
    if project.status == "archived":
        raise AppError(409, "ARCHIVED", "归档项目不能执行")


def _reject_readonly(db: Session, user: User, project: Project) -> None:
    if project.owner_id == user.id:
        return
    member = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
    )
    if member is not None and member.role == "readonly":
        raise AppError(403, "FORBIDDEN", "只读成员不能执行")


def _request_hash(project_id: uuid.UUID, suite_id: uuid.UUID | None, confirm_writes: bool, version_ids: list[str]) -> str:
    raw = "|".join(
        [
            str(project_id),
            str(suite_id or ""),
            "1" if confirm_writes else "0",
            ",".join(sorted(version_ids)),
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _idempotent_run(db: Session, user: User, key: str, digest: str) -> TestRun | None:
    record = db.scalar(
        select(IdempotencyRecord).where(IdempotencyRecord.user_id == user.id, IdempotencyRecord.idem_key == key[:200])
    )
    if record is None or record.expires_at <= utcnow():
        return None
    if record.request_hash != digest:
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "同一个 Idempotency-Key 对应了不同参数")
    run = db.get(TestRun, record.run_id)
    if run is None:
        return None
    return run
