"""工作台只返回当前用户的真实计数，没有执行数据时通过率为空。"""

import pytest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from tests.helpers import login


def test_dashboard_empty_state(client: TestClient) -> None:
    login(client)
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["projectCount"] == 0
    assert data["caseCount"] == 0
    assert data["pendingReviewCount"] == 0
    assert data["failedCaseCount"] == 0
    assert data["passRate"] is None
    assert data["passRateText"] == "无可判定结果"
    assert data["executionDataAvailable"] is False
    assert data["recentTasks"] == []
    assert data["recentProjects"] == []
    assert "%" not in data["passRateText"]


def test_dashboard_counts_only_owned_projects(client: TestClient, db_session: Session) -> None:
    login(client)
    created = client.post(
        "/api/v1/projects",
        json={"name": "我的项目", "description": "说明", "baseUrl": "https://example.com", "envLabel": "预发"},
    )
    assert created.status_code == 201
    summary = client.get("/api/v1/dashboard/summary").json()["data"]
    assert summary["projectCount"] == 1
    assert summary["recentProjects"][0]["name"] == "我的项目"
    assert summary["passRate"] is None
    assert summary["recentTasks"] == []
    assert summary["recentActivities"][0]["action"] == "project.create"
    assert summary["recentActivities"][0]["detail"]["name"] == "我的项目"

    now = datetime.now(timezone.utc)
    db_session.add(
        User(
            username="alice",
            password_hash=hash_password("Alice_Pass_123"),
            display_name="Alice",
            role="member",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    client.cookies.clear()
    login(client, "alice", "Alice_Pass_123")
    isolated = client.get("/api/v1/dashboard/summary").json()["data"]
    assert isolated["projectCount"] == 0
    assert isolated["recentProjects"] == []
    assert isolated["recentActivities"] == []


def test_internal_error_does_not_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("token=sekret")

    monkeypatch.setattr("app.api.v1.dashboard.dashboard_summary", boom)
    with TestClient(app, raise_server_exceptions=False) as raw_client:
        login(raw_client)
        response = raw_client.get("/api/v1/dashboard/summary", headers={"X-Request-Id": "err-case-1"})
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.json()["message"] == "服务器内部错误"
    assert response.json()["requestId"] == "err-case-1"
    assert "sekret" not in response.text
