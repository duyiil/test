"""Phase 2 主链路。Mock 生成不读取演示服务源码。"""

from __future__ import annotations

import sys
import threading
import time
import uuid
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from demo.sut.main import PRODUCTS, app as sut_app  # noqa: E402

from app.execution.runner import execute_run  # noqa: E402
from app.models import testing as testing_models  # noqa: E402
from app.modules.testing.service import process_generation_task  # noqa: E402
from tests.helpers import login  # noqa: E402


class FlakyProvider:
    name = "mock"

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def generate(self, *, project_name: str, contract: dict) -> list[dict]:
        path = contract["path"]
        self.calls[path] = self.calls.get(path, 0) + 1
        if path == "/api/products" and self.calls[path] == 1:
            raise RuntimeError("第一次调用失败")
        if path == "/api/products/{id}":
            raise RuntimeError("这个接口一直失败")
        return [
            {
                "name": "可用草稿",
                "description": project_name,
                "scenario": "正常功能",
                "basis": "契约声明了 201",
                "method": "POST",
                "relativePath": path,
                "headers": {},
                "query": {},
                "pathParams": {},
                "body": {"name": "示例商品", "price": 10.5},
                "timeout": 30,
                "assertions": [{"type": "statusCode", "expected": 201}],
                "origin": "mock",
            }
        ]


def _project(client: TestClient, name: str = "商品项目", base_url: str = "http://127.0.0.1:9000") -> str:
    login(client)
    response = client.post(
        "/api/v1/projects",
        json={"name": name, "description": "phase2", "baseUrl": base_url, "envLabel": "测试"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def _load_and_generate(client: TestClient, project_id: str, db_session: Session) -> None:
    loaded = client.post(f"/api/v1/projects/{project_id}/contract/demo")
    assert loaded.status_code == 200, loaded.text
    created = client.post(f"/api/v1/projects/{project_id}/generation-tasks")
    assert created.status_code == 202, created.text
    task_id = uuid.UUID(created.json()["data"]["id"])
    assert created.json()["data"]["status"] == "queued"
    process_generation_task(db_session, task_id)
    detail = client.get(f"/api/v1/generation-tasks/{task_id}")
    assert detail.json()["data"]["status"] == "succeeded"
    assert detail.json()["data"]["provider"] == "mock"


def test_generation_review_edit_and_reject(client: TestClient, db_session: Session) -> None:
    project_id = _project(client)
    _load_and_generate(client, project_id, db_session)
    cases = client.get(f"/api/v1/projects/{project_id}/cases", params={"reviewStatus": "draft"})
    items = cases.json()["data"]["items"]
    assert len(items) >= 3
    assert all(item["reviewStatus"] == "draft" for item in items)
    blocked = client.post("/api/v1/projects/" + project_id + "/runs", json={"confirmWrites": True})
    assert blocked.status_code == 422

    first = items[0]
    submitted = client.post(f"/api/v1/case-versions/{first['id']}/submit")
    assert submitted.status_code == 200
    empty_reason = client.post(f"/api/v1/case-versions/{first['id']}/reject", json={"reason": "   "})
    assert empty_reason.status_code == 422
    rejected = client.post(f"/api/v1/case-versions/{first['id']}/reject", json={"reason": "断言依据不足"})
    assert rejected.status_code == 200
    assert rejected.json()["data"]["reviewStatus"] == "rejected"
    assert rejected.json()["data"]["events"][-1]["reason"] == "断言依据不足"

    second = items[1]
    edited = client.post(f"/api/v1/case-versions/{second['id']}/edit", json={"name": "已修改的用例"})
    assert edited.status_code == 200
    assert edited.json()["data"]["versionNumber"] == 2
    assert edited.json()["data"]["reviewStatus"] == "draft"
    version_id = edited.json()["data"]["id"]
    client.post(f"/api/v1/case-versions/{version_id}/submit")
    approved = client.post(f"/api/v1/case-versions/{version_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["data"]["reviewStatus"] == "confirmed"
    revised = client.post(
        f"/api/v1/case-versions/{version_id}/edit",
        json={"assertions": [{"type": "statusCode", "expected": 200}]},
    )
    assert revised.status_code == 200
    assert revised.json()["data"]["reviewStatus"] == "pending_review"
    assert revised.json()["data"]["versionNumber"] == 3


def test_empty_assertions_cannot_be_approved(client: TestClient, db_session: Session) -> None:
    project_id = _project(client, "空断言")
    _load_and_generate(client, project_id, db_session)
    version = db_session.scalar(select(testing_models.TestCaseVersion).limit(1))
    assert version is not None
    version.assertions = []
    version.review_status = "pending_review"
    db_session.commit()
    response = client.post(f"/api/v1/case-versions/{version.id}/approve")
    assert response.status_code == 422
    assert "空断言" in response.text


def test_generation_keeps_other_targets_when_one_fails(client: TestClient, db_session: Session) -> None:
    project_id = _project(client, "部分失败")
    client.post(f"/api/v1/projects/{project_id}/contract/demo")
    created = client.post(f"/api/v1/projects/{project_id}/generation-tasks")
    task_id = uuid.UUID(created.json()["data"]["id"])
    process_generation_task(db_session, task_id, provider=FlakyProvider())
    detail = client.get(f"/api/v1/generation-tasks/{task_id}").json()["data"]
    by_status = {item["status"]: item for item in detail["targets"]}
    attempts = {item["endpointId"]: item["attempts"] for item in detail["targets"]}
    assert "failed" in by_status.values() or any(item["status"] == "failed" for item in detail["targets"])
    assert any(item["status"] == "succeeded" for item in detail["targets"])
    assert any(value == 2 for value in attempts.values())
    drafts = client.get(f"/api/v1/projects/{project_id}/cases").json()["data"]["items"]
    assert drafts


def test_write_confirmation_cancel_and_report(client: TestClient, db_session: Session) -> None:
    project_id = _project(client, "执行保护", "http://127.0.0.1:8765")
    _load_and_generate(client, project_id, db_session)
    cases = client.get(f"/api/v1/projects/{project_id}/cases").json()["data"]["items"]
    for item in cases:
        if item["method"] == "GET" and item["relativePath"] == "/api/products":
            client.post(f"/api/v1/case-versions/{item['id']}/submit")
            client.post(f"/api/v1/case-versions/{item['id']}/approve")
        if item["method"] == "POST":
            client.post(f"/api/v1/case-versions/{item['id']}/submit")
            approved = client.post(f"/api/v1/case-versions/{item['id']}/approve")
            assert approved.status_code == 200
    denied = client.post(f"/api/v1/projects/{project_id}/runs", json={"confirmWrites": False})
    assert denied.status_code == 409
    assert denied.json()["code"] == "WRITE_CONFIRMATION_REQUIRED"
    queued = client.post(f"/api/v1/projects/{project_id}/runs", json={"confirmWrites": True})
    assert queued.status_code == 202
    run_id = queued.json()["data"]["id"]
    cancelled = client.post(f"/api/v1/runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"
    report = client.get(f"/api/v1/runs/{run_id}/report")
    assert report.status_code == 200
    assert report.json()["data"]["aiStatus"] == "unavailable"
    again = client.post(f"/api/v1/runs/{run_id}/cancel")
    assert again.status_code == 409


def test_worker_executes_against_author_sut_and_keeps_report(client: TestClient, db_session: Session) -> None:
    PRODUCTS.clear()
    PRODUCTS["p-1"] = {"id": "p-1", "name": "演示水杯", "price": "12.5"}
    config = uvicorn.Config(sut_app, host="127.0.0.1", port=8765, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.05)
    try:
        project_id = _project(client, "联调", "http://127.0.0.1:8765")
        _load_and_generate(client, project_id, db_session)
        cases = client.get(f"/api/v1/projects/{project_id}/cases").json()["data"]["items"]
        for item in cases:
            client.post(f"/api/v1/case-versions/{item['id']}/submit")
            client.post(f"/api/v1/case-versions/{item['id']}/approve")
        created = client.post(f"/api/v1/projects/{project_id}/runs", json={"confirmWrites": True})
        assert created.status_code == 202, created.text
        run_id = uuid.UUID(created.json()["data"]["id"])
        run = db_session.get(testing_models.TestRun, run_id)
        assert run is not None
        run.status = "running"
        db_session.commit()
        execute_run(db_session, run_id)
        db_session.expire_all()
        finished = db_session.get(testing_models.TestRun, run_id)
        assert finished is not None
        assert finished.status == "succeeded"
        assert finished.assertion_failed_count > 0
        assert finished.passed_count > 0
        report = db_session.scalar(select(testing_models.DataReport).where(testing_models.DataReport.run_id == run_id))
        assert report is not None
        assert report.ai_status == "unavailable"
        body = client.get(f"/api/v1/runs/{run_id}/report")
        assert body.status_code == 200
        assert body.json()["data"]["data"]["passRate"] is not None
        remote = client.post(
            "/api/v1/projects",
            json={"name": "外网项目", "description": "", "baseUrl": "https://example.com", "envLabel": "测试"},
        )
        assert remote.status_code == 201
        client.post(f"/api/v1/projects/{remote.json()['data']['id']}/contract/demo")
        # 复用同一批已确认用例不在这个新项目里。只检查目标限制函数通过执行入口。
        from app.modules.testing.service import assert_base_url_allowed
        from app.core.errors import AppError

        with pytest.raises(AppError):
            assert_base_url_allowed("https://example.com")
    finally:
        server.should_exit = True
        thread.join(timeout=3)
