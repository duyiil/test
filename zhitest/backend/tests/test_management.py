"""管理接口：环境、成员、归档删除、批量审核、通知、候选缺陷、计划。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.platform import DefectCandidate, Notification
from app.models.user import User
from app.modules.testing.service import process_generation_task
from tests.helpers import login


def _project(client: TestClient) -> str:
    login(client)
    response = client.post(
        "/api/v1/projects",
        json={"name": "管理项目", "description": "", "baseUrl": "http://127.0.0.1:9000", "envLabel": "测试"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def _user(db_session: Session, username: str) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        User(
            username=username,
            password_hash=hash_password("Member_Pass_123"),
            display_name=username,
            role="member",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def test_environments_archive_and_delete(client: TestClient) -> None:
    project_id = _project(client)
    created = client.post(
        f"/api/v1/projects/{project_id}/environments",
        json={"name": "预发", "baseUrl": "http://127.0.0.1:9001"},
    )
    assert created.status_code == 201, created.text
    env_id = created.json()["data"]["id"]
    listed = client.get(f"/api/v1/projects/{project_id}/environments")
    assert listed.json()["data"]["items"][0]["name"] == "预发"
    assert client.post(f"/api/v1/projects/{project_id}/environments/{env_id}/activate").status_code == 200
    active = client.get(f"/api/v1/projects/{project_id}/environments").json()["data"]["items"][0]
    assert active["isActive"] is True
    assert client.delete(f"/api/v1/projects/{project_id}/environments/{env_id}").status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}/environments").json()["data"]["items"] == []

    archived = client.post(f"/api/v1/projects/{project_id}/archive")
    assert archived.json()["data"]["status"] == "archived"
    assert client.get(f"/api/v1/projects/{project_id}").json()["data"]["status"] == "archived"
    restored = client.post(f"/api/v1/projects/{project_id}/restore")
    assert restored.json()["data"]["status"] == "active"

    refused = client.post(f"/api/v1/projects/{project_id}/delete", json={"confirm": False})
    assert refused.status_code == 422
    removed = client.post(f"/api/v1/projects/{project_id}/delete", json={"confirm": True})
    assert removed.status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404


def test_members_add_role_and_remove(client: TestClient, db_session: Session) -> None:
    project_id = _project(client)
    _user(db_session, "tester1")
    added = client.post(f"/api/v1/projects/{project_id}/members", json={"username": "tester1", "role": "tester"})
    assert added.status_code == 201, added.text
    member_id = added.json()["data"]["id"]
    listed = client.get(f"/api/v1/projects/{project_id}/members").json()["data"]
    assert listed["owner"]["role"] == "owner"
    assert listed["items"][0]["username"] == "tester1"
    changed = client.post(f"/api/v1/projects/{project_id}/members/{member_id}/role", json={"role": "readonly"})
    assert changed.json()["data"]["role"] == "readonly"
    assert client.delete(f"/api/v1/projects/{project_id}/members/{member_id}").status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}/members").json()["data"]["items"] == []
    missing = client.post(f"/api/v1/projects/{project_id}/members", json={"username": "nobody", "role": "tester"})
    assert missing.status_code == 404


def test_batch_review_approves_pending_cases(client: TestClient, db_session: Session) -> None:
    project_id = _project(client)
    assert client.post(f"/api/v1/projects/{project_id}/contract/demo").status_code == 200
    created = client.post(f"/api/v1/projects/{project_id}/generation-tasks")
    process_generation_task(db_session, uuid.UUID(created.json()["data"]["id"]))
    drafts = client.get(f"/api/v1/projects/{project_id}/cases", params={"reviewStatus": "draft"}).json()["data"]["items"]
    assert drafts
    for item in drafts:
        assert client.post(f"/api/v1/case-versions/{item['id']}/submit").status_code == 200
    pending = client.get(f"/api/v1/projects/{project_id}/cases", params={"reviewStatus": "pending_review"}).json()["data"]["items"]
    chosen = [item["id"] for item in pending[:2]]
    approved = client.post(
        f"/api/v1/projects/{project_id}/reviews/batch",
        json={"action": "approve", "versionIds": chosen},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["count"] == 2
    empty_reason = client.post(
        f"/api/v1/projects/{project_id}/reviews/batch",
        json={"action": "reject", "versionIds": [pending[2]["id"]], "reason": "  "},
    )
    assert empty_reason.status_code == 422


def test_notification_read_and_defect_status(client: TestClient, db_session: Session) -> None:
    project_id = _project(client)
    me = client.get("/api/v1/auth/me").json()["data"]
    db_session.add(
        Notification(
            user_id=uuid.UUID(me["id"]),
            title="执行完成",
            body="任务 succeeded",
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        DefectCandidate(
            project_id=uuid.UUID(project_id),
            title="断言失败候选",
            status="candidate",
            detail={"note": "这是失败候选，不是已确认漏洞。"},
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()
    notes = client.get("/api/v1/notifications")
    assert notes.json()["data"]["unreadCount"] == 1
    note_id = notes.json()["data"]["items"][0]["id"]
    read = client.post(f"/api/v1/notifications/{note_id}/read")
    assert read.json()["data"]["readAt"] is not None
    assert client.get("/api/v1/notifications").json()["data"]["unreadCount"] == 0

    defects = client.get(f"/api/v1/projects/{project_id}/defects").json()["data"]
    assert defects["label"].startswith("候选缺陷")
    defect_id = defects["items"][0]["id"]
    detail = client.get(f"/api/v1/defects/{defect_id}")
    assert "不是已确认" in detail.json()["data"]["label"]
    rejected = client.post(f"/api/v1/defects/{defect_id}/status", json={"status": "confirmed"})
    assert rejected.status_code == 422
    assert "不能标成已确认" in rejected.json()["message"]
    updated = client.post(f"/api/v1/defects/{defect_id}/status", json={"status": "dismissed"})
    assert updated.json()["data"]["status"] == "dismissed"


def test_schedule_edit_disable_and_history(client: TestClient) -> None:
    project_id = _project(client)
    assert client.post(f"/api/v1/projects/{project_id}/contract/demo").status_code == 200
    demo = client.post(f"/api/v1/projects/{project_id}/dependency-demo")
    assert demo.status_code == 201, demo.text
    suite_id = client.get(f"/api/v1/projects/{project_id}/suites").json()["data"]["items"][0]["id"]
    created = client.post(f"/api/v1/suites/{suite_id}/schedules", json={"cron": "0 2 * * *"})
    assert created.status_code == 201, created.text
    schedule_id = created.json()["data"]["id"]
    listed = client.get(f"/api/v1/projects/{project_id}/schedules")
    assert listed.json()["data"]["items"][0]["enabled"] is True
    assert "未验证" in listed.json()["data"]["note"]
    updated = client.post(f"/api/v1/schedules/{schedule_id}", json={"cron": "15 3 * * *", "enabled": False})
    assert updated.json()["data"]["cron"] == "15 3 * * *"
    assert updated.json()["data"]["enabled"] is False
    events = client.get(f"/api/v1/schedules/{schedule_id}/events").json()["data"]["items"]
    kinds = {item["kind"] for item in events}
    assert "created" in kinds
    assert "updated" in kinds
    assert "disabled" in kinds
