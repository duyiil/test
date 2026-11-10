from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urljoin

from app.core.clock import utcnow
from app.core.errors import AppError
from app.execution.variables import extract_values, substitute

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.execution.assertions import evaluate_assertions
from app.models.project import Project
from app.models.testing import RunResult, TestCaseVersion, TestRun
from app.modules.testing.service import _write_report, assert_base_url_allowed

Transport = Callable[[dict[str, Any]], tuple[int | None, str, str | None, str | None]]
READ_METHODS = {"GET", "HEAD"}


def execute_run(db: Session, run_id: uuid.UUID, transport: Transport | None = None) -> None:
    run = db.get(TestRun, run_id)
    if run is None or run.status not in {"running", "cancelling"}:
        return
    project = db.get(Project, run.project_id)
    if project is None:
        _finish(db, run, "failed", "项目不存在")
        return
    try:
        assert_base_url_allowed(project.base_url)
    except Exception as exc:
        _finish(db, run, "aborted", str(exc))
        return
    version_ids = [uuid.UUID(item) for item in run.snapshot.get("caseVersionIds", [])]
    versions = []
    for vid in version_ids:
        version = db.get(TestCaseVersion, vid)
        if version is not None:
            versions.append(version)
    sender = transport or _http_transport
    consecutive_connect_failures = 0
    aborted = False
    failed_cases: set[str] = set()
    variables: dict[str, Any] = {}
    for index, version in enumerate(versions, start=1):
        db.refresh(run)
        now = utcnow()
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=60)
        if run.cancel_requested or run.status == "cancelling":
            _skip_rest(db, run, versions[index - 1 :], index, "用户取消")
            _finish(db, run, "cancelled", "用户取消")
            return
        if aborted:
            _skip_rest(db, run, versions[index - 1 :], index, "环境异常")
            _finish(db, run, "aborted", "连续连接失败，已中止")
            return
        if any(str(dep) in failed_cases for dep in (version.dependencies or [])):
            _skip_one(db, run, version, index, "前置用例失败")
            failed_cases.add(str(version.case_id))
            db.commit()
            continue
        try:
            rendered = _render_version(version, variables)
        except AppError as exc:
            outcome = _error_outcome(
                {"method": version.method, "url": version.relative_path},
                "variable_missing",
                exc.message,
                1,
            )
            _save_result(db, run, version, index, outcome)
            failed_cases.add(str(version.case_id))
            db.commit()
            continue
        outcome = _execute_case(project.base_url, rendered, sender)
        if outcome["error_class"] in {"connect_error", "timeout"} and version.method in READ_METHODS and outcome["attempt_count"] == 1:
            outcome = _execute_case(project.base_url, version, sender)
            outcome["attempt_count"] = 2
        _save_result(db, run, version, index, outcome)
        if outcome["error_class"] in {"connect_error", "timeout"}:
            consecutive_connect_failures += 1
            if consecutive_connect_failures >= 5:
                aborted = True
        else:
            consecutive_connect_failures = 0
        if outcome["status"] == "passed":
            variables.update(extract_values(version.extract or [], outcome.get("response_body") or ""))
        else:
            failed_cases.add(str(version.case_id))
        db.commit()
    db.refresh(run)
    if aborted:
        _finish(db, run, "aborted", "连续连接失败，已中止")
        return
    if run.cancel_requested or run.status == "cancelling":
        _finish(db, run, "cancelled", "用户取消")
        return
    _finish(db, run, "succeeded", None)


def _render_version(version: TestCaseVersion, variables: dict[str, Any]) -> Any:
    return type(
        "RenderedCase",
        (),
        {
            "method": version.method,
            "relative_path": substitute(version.relative_path, variables),
            "headers": substitute(version.headers or {}, variables),
            "query": substitute(version.query or {}, variables),
            "path_params": substitute(version.path_params or {}, variables),
            "body": substitute(version.body, variables),
            "timeout_seconds": version.timeout_seconds,
            "assertions": version.assertions,
        },
    )()


def _skip_one(db: Session, run: TestRun, version: TestCaseVersion, ordinal: int, reason: str) -> None:
    db.add(
        RunResult(
            run_id=run.id,
            case_version_id=version.id,
            ordinal=ordinal,
            status="skipped",
            request={"method": version.method, "url": version.relative_path},
            response_status=None,
            response_body=None,
            error_class="skipped",
            error_message=reason,
            assertion_results=[],
            attempt_count=0,
            created_at=datetime.now(timezone.utc),
        )
    )
    run.skipped_count += 1


def _execute_case(base_url: str, version: TestCaseVersion, transport: Transport) -> dict[str, Any]:
    url = _build_url(base_url, version.relative_path, version.path_params or {})
    request = {
        "method": version.method,
        "url": url,
        "query": version.query or {},
        "headers": version.headers or {},
        "body": version.body,
        "timeout": version.timeout_seconds,
    }
    try:
        assert_base_url_allowed(url)
    except Exception as exc:
        return _error_outcome(request, "target_rejected", str(exc), 1)
    status, body, error_class, error_message = transport(request)
    if error_class:
        return _error_outcome(request, error_class, error_message or error_class, 1, status, body)
    assertions = evaluate_assertions(list(version.assertions or []), status_code=status, body_text=body)
    passed = all(item["passed"] for item in assertions) if assertions else False
    return {
        "status": "passed" if passed else "assertion_failed",
        "request": request,
        "response_status": status,
        "response_body": body[:20000],
        "error_class": None if passed else "assertion_failed",
        "error_message": None if passed else "存在未通过的断言",
        "assertion_results": assertions,
        "attempt_count": 1,
    }


def _error_outcome(
    request: dict[str, Any],
    error_class: str,
    message: str,
    attempts: int,
    status: int | None = None,
    body: str = "",
) -> dict[str, Any]:
    return {
        "status": "execution_error",
        "request": request,
        "response_status": status,
        "response_body": (body or "")[:20000],
        "error_class": error_class,
        "error_message": message,
        "assertion_results": [],
        "attempt_count": attempts,
    }


def _save_result(db: Session, run: TestRun, version: TestCaseVersion, ordinal: int, outcome: dict[str, Any]) -> None:
    db.add(
        RunResult(
            run_id=run.id,
            case_version_id=version.id,
            ordinal=ordinal,
            status=outcome["status"],
            request=outcome["request"],
            response_status=outcome["response_status"],
            response_body=outcome["response_body"],
            error_class=outcome["error_class"],
            error_message=outcome["error_message"],
            assertion_results=outcome["assertion_results"],
            attempt_count=outcome["attempt_count"],
            created_at=datetime.now(timezone.utc),
        )
    )
    run.executed_count += 1
    if outcome["status"] == "passed":
        run.passed_count += 1
    elif outcome["status"] == "assertion_failed":
        run.assertion_failed_count += 1
    else:
        run.execution_error_count += 1


def _skip_rest(db: Session, run: TestRun, versions: list[TestCaseVersion], start_ordinal: int, reason: str) -> None:
    for offset, version in enumerate(versions):
        db.add(
            RunResult(
                run_id=run.id,
                case_version_id=version.id,
                ordinal=start_ordinal + offset,
                status="skipped",
                request={"method": version.method, "url": version.relative_path},
                response_status=None,
                response_body=None,
                error_class="skipped",
                error_message=reason,
                assertion_results=[],
                attempt_count=0,
                created_at=datetime.now(timezone.utc),
            )
        )
        run.skipped_count += 1


def _finish(db: Session, run: TestRun, status: str, reason: str | None) -> None:
    run.status = status
    run.abort_reason = reason
    run.finished_at = datetime.now(timezone.utc)
    _write_report(db, run)
    db.commit()


def _build_url(base_url: str, path: str, path_params: dict[str, Any]) -> str:
    rendered = path
    for key, value in path_params.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return urljoin(base_url.rstrip("/") + "/", rendered.lstrip("/"))


def _http_transport(request: dict[str, Any]) -> tuple[int | None, str, str | None, str | None]:
    timeout = float(request.get("timeout") or 30)
    try:
        # trust_env=False：测试流量必须直连被测目标，不能走宿主机的系统代理
        # （Windows 上 httpx 会读取 IE/系统代理设置，会把回环地址转发给代理导致 502）。
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            response = client.request(
                request["method"],
                request["url"],
                params=request.get("query") or None,
                headers=request.get("headers") or None,
                json=request.get("body") if request.get("body") is not None else None,
            )
            if 300 <= response.status_code < 400:
                location = response.headers.get("location")
                if location:
                    target = urljoin(str(response.url), location)
                    try:
                        assert_base_url_allowed(target)
                    except AppError as exc:
                        return None, "", "ssrf_redirect", exc.message
                    response = client.request(request["method"], target)
    except httpx.TimeoutException:
        return None, "", "timeout", "请求超时"
    except httpx.TransportError as exc:
        return None, "", "connect_error", str(exc)
    return response.status_code, response.text, None, None


def counts_from_results(db: Session, run: TestRun) -> None:
    results = list(db.scalars(select(RunResult).where(RunResult.run_id == run.id)).all())
    run.executed_count = sum(1 for item in results if item.status != "skipped")
    run.passed_count = sum(1 for item in results if item.status == "passed")
    run.assertion_failed_count = sum(1 for item in results if item.status == "assertion_failed")
    run.execution_error_count = sum(1 for item in results if item.status == "execution_error")
    run.skipped_count = sum(1 for item in results if item.status == "skipped")
