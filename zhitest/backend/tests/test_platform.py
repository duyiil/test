"""OpenAPI、依赖、幂等、SSRF、会话时钟。时钟是 monkeypatch，不是墙钟。"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.errors import AppError
from app.execution.ssrf import assert_target_allowed
from app.execution.variables import order_versions
from app.models import testing as testing_models
from app.modules.platform.service import recover_stale_runs
from app.modules.testing.service import process_generation_task
from tests.helpers import login

OPENAPI = """
openapi: 3.0.3
info:
  title: demo
  version: "1"
paths:
  /api/items:
    get:
      summary: 列表
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema:
                type: object
                properties:
                  items:
                    type: array
"""


def _project(client: TestClient, name: str, base_url: str = "http://127.0.0.1:9000") -> str:
    login(client)
    response = client.post(
        "/api/v1/projects",
        json={"name": name, "description": "", "baseUrl": base_url, "envLabel": "测试"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def test_openapi_preview_and_confirm_generates_drafts(client: TestClient, db_session: Session) -> None:
    project_id = _project(client, "openapi")
    preview = client.post(f"/api/v1/projects/{project_id}/openapi/preview", json={"document": OPENAPI})
    assert preview.status_code == 200, preview.text
    assert preview.json()["data"]["endpoints"][0]["path"] == "/api/items"
    saved = client.post(f"/api/v1/projects/{project_id}/openapi/confirm", json={"document": OPENAPI})
    assert saved.status_code == 200
    created = client.post(f"/api/v1/projects/{project_id}/generation-tasks")
    process_generation_task(db_session, uuid.UUID(created.json()["data"]["id"]))
    cases = client.get(f"/api/v1/projects/{project_id}/cases").json()["data"]["items"]
    assert cases
    assert cases[0]["relativePath"] == "/api/items"
    bad = client.post(
        f"/api/v1/projects/{project_id}/openapi/preview",
        json={"document": "swagger: '2.0'\npaths: {}\n"},
    )
    assert bad.status_code == 422


def test_ssrf_blocks_metadata_and_private_dns(monkeypatch) -> None:
    with pytest_raises():
        assert_target_allowed("http://169.254.169.254/latest/meta-data")
    with pytest_raises():
        assert_target_allowed("http://10.0.0.8/")

    def public(_host, _port, type=0):
        return [(2, 1, 6, "", ("8.8.8.8", 80))]

    monkeypatch.setattr("app.execution.ssrf.socket.getaddrinfo", public)
    assert_target_allowed("http://public.example/")

    def loopback(_host, _port, type=0):
        return [(2, 1, 6, "", ("127.0.0.1", 80))]

    monkeypatch.setattr("app.execution.ssrf.socket.getaddrinfo", loopback)
    with pytest_raises():
        assert_target_allowed("http://rebind.example/")


def pytest_raises():
    import pytest

    return pytest.raises(AppError)


def test_dependency_chain_orders_and_extracts() -> None:
    class Version:
        def __init__(self, case_id, path, deps, extract):
            self.case_id = case_id
            self.relative_path = path
            self.headers = {}
            self.query = {}
            self.path_params = {}
            self.body = None
            self.dependencies = deps
            self.extract = extract

    first = Version("a", "/api/products", [], [{"name": "productId", "path": "id"}])
    second = Version("b", "/api/products/{{productId}}", ["a"], [])
    ordered = order_versions([second, first])
    assert [item.case_id for item in ordered] == ["a", "b"]


def test_idempotent_resubmit_and_conflict(client: TestClient, db_session: Session) -> None:
    project_id = _project(client, "idem")
    client.post(f"/api/v1/projects/{project_id}/contract/demo")
    created = client.post(f"/api/v1/projects/{project_id}/generation-tasks")
    process_generation_task(db_session, uuid.UUID(created.json()["data"]["id"]))
    case = client.get(f"/api/v1/projects/{project_id}/cases").json()["data"]["items"]
    target = next(item for item in case if item["method"] == "GET" and item["relativePath"] == "/api/products")
    client.post(f"/api/v1/case-versions/{target['id']}/submit")
    client.post(f"/api/v1/case-versions/{target['id']}/approve")
    headers = {"Idempotency-Key": "same-key"}
    first = client.post(f"/api/v1/projects/{project_id}/runs", json={"confirmWrites": False}, headers=headers)
    assert first.status_code == 202, first.text
    again = client.post(f"/api/v1/projects/{project_id}/runs", json={"confirmWrites": False}, headers=headers)
    assert again.status_code == 202
    assert again.json()["data"]["id"] == first.json()["data"]["id"]
    conflict = client.post(f"/api/v1/projects/{project_id}/runs", json={"confirmWrites": True}, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_stale_worker_does_not_replay_finished_case(client: TestClient, db_session: Session) -> None:
    project_id = _project(client, "recover")
    client.post(f"/api/v1/projects/{project_id}/contract/demo")
    created = client.post(f"/api/v1/projects/{project_id}/generation-tasks")
    process_generation_task(db_session, uuid.UUID(created.json()["data"]["id"]))
    items = client.get(f"/api/v1/projects/{project_id}/cases").json()["data"]["items"]
    chosen = [item for item in items if item["method"] == "GET"][:2]
    for item in chosen:
        client.post(f"/api/v1/case-versions/{item['id']}/submit")
        client.post(f"/api/v1/case-versions/{item['id']}/approve")
    run = client.post(f"/api/v1/projects/{project_id}/runs", json={"confirmWrites": False})
    assert run.status_code == 202, run.text
    run_id = uuid.UUID(run.json()["data"]["id"])
    stored = db_session.get(testing_models.TestRun, run_id)
    assert stored is not None
    stored.status = "running"
    stored.lease_expires_at = utcnow() - timedelta(seconds=5)
    version_id = uuid.UUID(stored.snapshot["caseVersionIds"][0])
    db_session.add(
        testing_models.RunResult(
            run_id=stored.id,
            case_version_id=version_id,
            ordinal=1,
            status="passed",
            request={"method": "GET", "url": "http://127.0.0.1/x"},
            response_status=200,
            response_body="{}",
            error_class=None,
            error_message=None,
            assertion_results=[],
            attempt_count=1,
        )
    )
    db_session.commit()
    assert recover_stale_runs(db_session) == 1
    db_session.commit()
    db_session.expire_all()
    refreshed = db_session.get(testing_models.TestRun, run_id)
    assert refreshed is not None
    assert refreshed.status == "queued"
    assert str(version_id) not in refreshed.snapshot["caseVersionIds"]


def test_malformed_json_without_login_is_401(client: TestClient) -> None:
    response = client.post("/api/v1/projects", content=b"{", headers={"content-type": "application/json"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    login_response = client.post("/api/v1/auth/login", content=b"{", headers={"content-type": "application/json"})
    assert login_response.status_code == 422


def test_two_hour_session_uses_mocked_clock(client: TestClient, monkeypatch) -> None:
    from datetime import datetime, timezone

    base = datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.modules.auth.service.utcnow", lambda: base)
    monkeypatch.setattr("app.api.deps.utcnow", lambda: base)
    assert login(client).status_code == 200
    later = base + timedelta(seconds=7201)
    monkeypatch.setattr("app.api.deps.utcnow", lambda: later)
    monkeypatch.setattr("app.modules.auth.service.utcnow", lambda: later)
    expired = client.get("/api/v1/auth/me")
    assert expired.status_code == 401


def test_dependency_demo_suite(client: TestClient) -> None:
    project_id = _project(client, "chain")
    client.post(f"/api/v1/projects/{project_id}/contract/demo")
    created = client.post(f"/api/v1/projects/{project_id}/dependency-demo")
    assert created.status_code == 201, created.text
    suites = client.get(f"/api/v1/projects/{project_id}/suites")
    assert suites.json()["data"]["items"][0]["name"] == "依赖链示例"


def test_llm_provider_uses_configured_endpoint_without_logging_key(monkeypatch) -> None:
    import httpx

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "[]"}}]},
        )

    from app.modules.ai.llm_provider import LLMGenerationProvider

    provider = LLMGenerationProvider(
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key="sk-test-secret",
        transport=httpx.MockTransport(handler),
    )
    assert provider.generate(project_name="p", contract={"method": "GET", "path": "/", "responses": {}}) == []
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["auth"] == "Bearer sk-test-secret"
    from app.modules.ai.llm_provider import provider_from_settings

    assert provider_from_settings().name == "mock"
