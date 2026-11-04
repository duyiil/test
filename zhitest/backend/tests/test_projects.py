"""项目创建、查询与归属隔离。

追踪（接口部分，不是完整手工用例通过）：
- TC-PROJECT-001 创建成功
- TC-PROJECT-002 同一账号下重名拒绝
- TC-PROJECT-003 Base URL 必填与格式
- TC-PROJECT-008 无项目时列表为空
跨项目访问按 Phase 1 约定返回 404。
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.project import Project
from app.models.user import User
from tests.helpers import login


def _create(client: TestClient, name: str = "订单服务", base_url: str = "http://127.0.0.1:9000") -> dict:
    response = client.post(
        "/api/v1/projects",
        json={
            "name": name,
            "description": "演示项目",
            "baseUrl": base_url,
            "envLabel": "测试",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_create_list_and_detail(client: TestClient, db_session: Session) -> None:
    login(client)
    created = _create(client)
    assert created["name"] == "订单服务"
    assert created["baseUrl"] == "http://127.0.0.1:9000"
    assert created["envLabel"] == "测试"
    assert created["endpointCount"] == 0
    assert created["caseCount"] == 0
    assert created["lastRun"] is None
    listed = client.get("/api/v1/projects")
    assert listed.status_code == 200
    body = listed.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]
    detail = client.get(f"/api/v1/projects/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["description"] == "演示项目"
    audit = db_session.scalar(select(AuditLog).where(AuditLog.action == "project.create"))
    assert audit is not None
    assert audit.ip == "testclient"
    assert audit.resource_id == created["id"]
    assert audit.detail == {"name": "订单服务", "envLabel": "测试"}
    stored = db_session.scalar(select(Project))
    assert stored is not None
    assert stored.base_url == "http://127.0.0.1:9000"


def test_duplicate_name_same_owner_conflict_and_other_owner_allowed(client: TestClient, db_session: Session) -> None:
    login(client)
    _create(client, "订单服务")
    duplicated = client.post(
        "/api/v1/projects",
        json={"name": "订单服务", "description": "", "baseUrl": "http://example.com", "envLabel": "开发"},
    )
    assert duplicated.status_code == 409
    assert duplicated.json()["code"] == "CONFLICT"
    assert duplicated.json()["message"] == "项目名称已存在"
    assert db_session.scalar(select(func.count()).select_from(Project)) == 1

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
    assert login(client, "alice", "Alice_Pass_123").status_code == 200
    created = _create(client, "订单服务", "http://alice.example")
    assert created["name"] == "订单服务"
    assert db_session.scalar(select(func.count()).select_from(Project)) == 2


def test_base_url_validation(client: TestClient) -> None:
    login(client)
    empty = client.post(
        "/api/v1/projects",
        json={"name": "无地址", "description": "", "baseUrl": "   ", "envLabel": "测试"},
    )
    assert empty.status_code == 422
    assert "Base URL 必填" in empty.text
    invalid = client.post(
        "/api/v1/projects",
        json={"name": "坏地址", "description": "", "baseUrl": "notaurl", "envLabel": "测试"},
    )
    assert invalid.status_code == 422
    assert "Base URL 格式非法" in invalid.text
    secret = client.post(
        "/api/v1/projects",
        json={"name": "带口令", "description": "", "baseUrl": "http://user:secret@example.com", "envLabel": "测试"},
    )
    assert secret.status_code == 422
    assert "不能包含用户名或密码" in secret.text
    assert "secret" not in secret.text
    allowed = _create(client, "本地服务", "http://127.0.0.1:8001/api")
    assert allowed["baseUrl"] == "http://127.0.0.1:8001/api"


def test_cross_project_access_is_not_found(client: TestClient, db_session: Session) -> None:
    login(client)
    created = _create(client, "管理员项目")
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
    hidden = client.get(f"/api/v1/projects/{created['id']}")
    assert hidden.status_code == 404
    assert hidden.json()["message"] == "资源不存在"
    listing = client.get("/api/v1/projects")
    assert listing.json()["data"]["total"] == 0
    missing = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
    assert missing.json()["message"] == hidden.json()["message"]


def test_search_and_pagination(client: TestClient) -> None:
    login(client)
    for index in range(3):
        _create(client, f"项目{index}", f"http://svc-{index}.example")
    page = client.get("/api/v1/projects", params={"page": 1, "pageSize": 2})
    body = page.json()["data"]
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["pageSize"] == 2
    found = client.get("/api/v1/projects", params={"q": "项目1"})
    assert found.json()["data"]["total"] == 1
    assert found.json()["data"]["items"][0]["name"] == "项目1"
    none = client.get("/api/v1/projects", params={"q": "不存在"})
    assert none.json()["data"]["total"] == 0
    assert none.json()["data"]["items"] == []


def test_empty_project_list(client: TestClient) -> None:
    login(client)
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 0
    assert response.json()["data"]["items"] == []
