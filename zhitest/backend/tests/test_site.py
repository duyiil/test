"""网站检测：URL 校验、站点扫描、接口导入与报告携带扫描摘要。

网络访问全部用 httpx.MockTransport 或模块级 monkeypatch 模拟，
SSRF 用例使用字面 IP，不依赖真实 DNS。
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.platform import ProjectEnvironment
from app.models.project import Project
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

CANNED_DETECTION = {
    "url": "http://8.8.8.8/",
    "finalUrl": "http://8.8.8.8/",
    "status": 200,
    "title": "Demo",
    "redirects": [],
    "technologies": ["server: nginx"],
    "securityHeaders": [
        {"name": "Strict-Transport-Security", "present": False},
        {"name": "X-Frame-Options", "present": True},
    ],
    "probeResults": [{"path": "/robots.txt", "status": 404}],
    "specCandidates": [],
}


def _project(client: TestClient, name: str, base_url: str = "http://127.0.0.1:9000") -> str:
    login(client)
    response = client.post(
        "/api/v1/projects",
        json={"name": name, "description": "", "baseUrl": base_url, "envLabel": "测试"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def _handler(routes: dict[str, httpx.Response]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path in routes:
            return routes[request.url.path]
        return httpx.Response(404, text="not found")

    return httpx.MockTransport(handle)


PAGE_HTML = (
    "<html><head><title>Demo Site</title>"
    '<meta name="generator" content="Next.js"></head>'
    "<body><div id='__NEXT_DATA__'>x</div></body></html>"
)


# ---- parse_site_url ----

from app.modules.site import service as site_service  # noqa: E402


def test_parse_site_url_rejects_invalid() -> None:
    for value in ("", "   ", "ftp://example.com/", "http://user:pass@example.com/", "not a url"):
        with pytest.raises(AppError) as exc:
            site_service.parse_site_url(value)
        assert exc.value.status_code == 422


def test_parse_site_url_blocks_private_and_metadata() -> None:
    for value in ("http://10.0.0.8/", "http://192.168.1.10/", "http://169.254.169.254/"):
        with pytest.raises(AppError) as exc:
            site_service.parse_site_url(value)
        assert exc.value.status_code == 403
        assert exc.value.code == "SSRF_BLOCKED"


def test_parse_site_url_allows_public_literal_and_allowlisted() -> None:
    assert site_service.parse_site_url("http://8.8.8.8/") == "http://8.8.8.8/"
    assert site_service.parse_site_url("http://8.8.8.8:8080/x#frag") == "http://8.8.8.8:8080/"
    assert site_service.parse_site_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000/"


# ---- detect_site ----

def test_detect_site_captures_page_tech_and_security_headers() -> None:
    transport = _handler(
        {
            "/": httpx.Response(
                200,
                text=PAGE_HTML,
                headers={
                    "content-type": "text/html",
                    "server": "nginx",
                    "x-frame-options": "DENY",
                    "content-security-policy": "default-src 'self'",
                },
            )
        }
    )
    result = site_service.detect_site("http://127.0.0.1:8000/", transport=transport)
    assert result["status"] == 200
    assert result["title"] == "Demo Site"
    assert "server: nginx" in result["technologies"]
    assert "Next.js" in result["technologies"]
    present = {item["name"]: item["present"] for item in result["securityHeaders"]}
    assert present["X-Frame-Options"] is True
    assert present["Content-Security-Policy"] is True
    assert present["Strict-Transport-Security"] is False
    assert all(item["status"] == 404 for item in result["probeResults"])
    assert len(result["specCandidates"]) == len(site_service.SPEC_PATHS)
    assert all(not item["parseOk"] and item["error"] == "HTTP 404" for item in result["specCandidates"])


def test_detect_site_follows_redirects_and_records_chain() -> None:
    transport = _handler(
        {
            "/": httpx.Response(302, headers={"location": "/home"}),
            "/home": httpx.Response(200, text=PAGE_HTML),
        }
    )
    result = site_service.detect_site("http://127.0.0.1:8000/", transport=transport)
    assert result["finalUrl"].endswith("/home")
    assert result["status"] == 200
    assert len(result["redirects"]) == 1
    assert result["redirects"][0]["status"] == 302
    assert result["redirects"][0]["to"].endswith("/home")


def test_detect_site_blocks_redirect_to_private() -> None:
    transport = _handler(
        {"/": httpx.Response(302, headers={"location": "http://192.168.1.10/x"})}
    )
    with pytest.raises(AppError) as exc:
        site_service.detect_site("http://127.0.0.1:8000/", transport=transport)
    assert exc.value.status_code == 403
    assert "重定向" in exc.value.message


def test_detect_site_parses_openapi_candidate_and_captures_parse_error() -> None:
    transport = _handler(
        {
            "/": httpx.Response(200, text=PAGE_HTML),
            "/openapi.json": httpx.Response(200, text=OPENAPI, headers={"content-type": "application/json"}),
            "/swagger.json": httpx.Response(200, text="<html>spa</html>", headers={"content-type": "text/html"}),
        }
    )
    result = site_service.detect_site("http://127.0.0.1:8000/", transport=transport)
    by_path = {item["path"]: item for item in result["specCandidates"]}
    good = by_path["/openapi.json"]
    assert good["parseOk"] is True
    assert good["endpointCount"] == 1
    assert good["openapi"] == "3.0.3"
    bad = by_path["/swagger.json"]
    assert bad["parseOk"] is False
    assert "text/html" in bad["error"]


def test_detect_site_oversize_spec_rejected() -> None:
    transport = _handler(
        {
            "/": httpx.Response(200, text=PAGE_HTML),
            "/openapi.json": httpx.Response(
                200,
                text="{}",
                headers={"content-type": "application/json", "content-length": str(2 * 1024 * 1024 + 1)},
            ),
        }
    )
    result = site_service.detect_site("http://127.0.0.1:8000/", transport=transport)
    by_path = {item["path"]: item for item in result["specCandidates"]}
    assert by_path["/openapi.json"]["error"].find("2MB") >= 0


# ---- API / import / run report ----

@pytest.fixture
def canned(monkeypatch) -> None:
    monkeypatch.setattr(site_service, "detect_site", lambda url, transport=None: CANNED_DETECTION)
    monkeypatch.setattr(site_service, "_fetch_spec", lambda client, base_url, spec_path: OPENAPI)


def test_site_detect_endpoint(client: TestClient, canned) -> None:
    anonymous = client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000001/site/detect", json={"url": "http://8.8.8.8/"}
    )
    assert anonymous.status_code == 401
    project_id = _project(client, "site-detect")
    response = client.post(f"/api/v1/projects/{project_id}/site/detect", json={"url": "http://8.8.8.8/"})
    assert response.status_code == 200, response.text
    assert response.json()["code"] == "SUCCESS"


def test_site_import_persists_scan_and_updates_base_url(
    client: TestClient, db_session: Session, canned
) -> None:
    project_id = _project(client, "site-import")
    db_session.add(
        ProjectEnvironment(
            project_id=uuid.UUID(project_id),
            name="prod",
            base_url="http://127.0.0.1:9001",
            is_active=True,
        )
    )
    db_session.commit()
    response = client.post(
        f"/api/v1/projects/{project_id}/site/import",
        json={"url": "http://8.8.8.8/", "specPath": "/openapi.json", "updateBaseUrl": True},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["saved"] == 1
    assert data["baseUrlUpdated"] is True
    assert data["scan"]["title"] == "Demo"

    db_session.expire_all()
    project = db_session.get(Project, uuid.UUID(project_id))
    assert project is not None
    assert project.base_url == "http://8.8.8.8/"
    assert project.site_scan is not None
    assert project.site_scan["finalUrl"] == "http://8.8.8.8/"
    environment = db_session.query(ProjectEnvironment).filter_by(project_id=uuid.UUID(project_id)).one()
    assert environment.is_active is False

    endpoints = client.get(f"/api/v1/projects/{project_id}/endpoints").json()["data"]["items"]
    assert any(item.get("path") == "/api/items" for item in endpoints)


def test_site_import_auto_generate_and_run_report_carries_scan(
    client: TestClient, db_session: Session, canned
) -> None:
    from app.execution.runner import execute_run
    from app.modules.testing.service import process_generation_task

    project_id = _project(client, "site-report")
    response = client.post(
        f"/api/v1/projects/{project_id}/site/import",
        json={"url": "http://8.8.8.8/", "specPath": "/openapi.json", "autoGenerate": True, "updateBaseUrl": True},
    )
    assert response.status_code == 200, response.text
    task_id = uuid.UUID(response.json()["data"]["generationTaskId"])
    process_generation_task(db_session, task_id)
    db_session.commit()

    cases = client.get(f"/api/v1/projects/{project_id}/cases").json()["data"]["items"]
    target = next(item for item in cases if item["method"] == "GET" and item["relativePath"] == "/api/items")
    assert client.post(f"/api/v1/case-versions/{target['id']}/submit").status_code == 200
    assert client.post(f"/api/v1/case-versions/{target['id']}/approve").status_code == 200

    run = client.post(f"/api/v1/projects/{project_id}/runs", json={"confirmWrites": False})
    assert run.status_code == 202, run.text
    run_id = uuid.UUID(run.json()["data"]["id"])
    from app.models import testing as testing_models

    stored = db_session.get(testing_models.TestRun, run_id)
    assert stored is not None
    stored.status = "running"
    db_session.commit()
    execute_run(db_session, run_id, transport=lambda request: (200, "{}", None, None))
    db_session.commit()

    report = client.get(f"/api/v1/runs/{run_id}/report")
    assert report.status_code == 200, report.text
    snapshot = report.json()["data"]["data"]["snapshot"]
    assert snapshot["baseUrl"] == "http://8.8.8.8/"
    assert snapshot["siteScan"]["status"] == 200
    assert snapshot["siteScan"]["title"] == "Demo"
    assert snapshot["siteScan"]["securityHeaders"][0]["name"] == "Strict-Transport-Security"


def test_site_import_rejects_bad_spec(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(site_service, "detect_site", lambda url, transport=None: CANNED_DETECTION)
    monkeypatch.setattr(site_service, "_fetch_spec", lambda client, base_url, spec_path: "info:\n  title: x\npaths: {}\n")
    project_id = _project(client, "site-bad")
    response = client.post(
        f"/api/v1/projects/{project_id}/site/import",
        json={"url": "http://8.8.8.8/", "specPath": "/openapi.json"},
    )
    assert response.status_code == 422
    assert "只支持 OpenAPI 3.x 或 Swagger 2.0" in response.json()["message"]
