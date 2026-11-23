"""登录、会话与权限。

追踪（只覆盖接口行为，不代表整条手工用例已通过）：
- TC-CONFIG-008 的过期判断逻辑，未做两小时墙钟等待
- TC-CONFIG-009 未登录 401、非管理员 403
- TC-CONFIG-010 登录成功与失败会写审计，不含模型配置等尚未实现的操作
"""

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.session import UserSession
from app.models.user import User
from app.modules.bootstrap import bootstrap_admin
from app.core.config import get_settings
from tests.helpers import ADMIN_PASSWORD, login


def test_login_success_and_me(client: TestClient, db_session: Session) -> None:
    response = login(client)
    body = response.json()
    assert response.status_code == 200
    assert body["code"] == "SUCCESS"
    assert body["message"] == "登录成功"
    assert body["data"]["username"] == "admin"
    assert body["data"]["role"] == "admin"
    assert "password" not in body["data"]
    cookie = response.headers.get("set-cookie", "")
    assert "zhitest_session=" in cookie
    assert "httponly" in cookie.lower()
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["displayName"] == "系统管理员"
    user = db_session.scalar(select(User).where(User.username == "admin"))
    assert user is not None
    assert user.password_hash != ADMIN_PASSWORD
    assert ADMIN_PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$2")


def test_login_failure_messages_do_not_distinguish_user(client: TestClient, db_session: Session) -> None:
    unknown = login(client, "nobody", "Wrong_Pass_123")
    db_session.add(
        User(
            username="alice",
            password_hash=hash_password("Alice_Pass_123"),
            display_name="Alice",
            role="member",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()
    wrong = login(client, "alice", "Wrong_Pass_123")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["message"] == wrong.json()["message"] == "用户名或密码错误"
    assert unknown.json()["code"] == "UNAUTHORIZED"
    failed = db_session.scalars(select(AuditLog).where(AuditLog.action == "auth.login_failed")).all()
    assert len(failed) >= 1
    assert all(item.detail and "password" not in item.detail for item in failed)


def test_login_validation_does_not_echo_password(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": 123456789})
    assert response.status_code == 422
    assert "123456789" not in response.text
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "data" not in response.json()


def test_inactive_user_and_wrong_password(client: TestClient, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        User(
            username="bob",
            password_hash=hash_password("Bob_Pass_123"),
            display_name="Bob",
            role="member",
            is_active=False,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    wrong = login(client, "bob", "not-the-password")
    assert wrong.status_code == 401
    assert wrong.json()["message"] == "用户名或密码错误"
    disabled = login(client, "bob", "Bob_Pass_123")
    assert disabled.status_code == 401
    assert disabled.json()["message"] == "账号已停用，请联系管理员"


def test_logout_revokes_session(client: TestClient) -> None:
    login(client)
    token = client.cookies.get("zhitest_session")
    assert token
    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["data"]["loggedOut"] is True
    client.cookies.clear()
    client.cookies.set("zhitest_session", token)
    again = client.get("/api/v1/auth/me")
    assert again.status_code == 401
    assert again.json()["message"] == "未登录或登录已失效"


def test_expired_session_is_rejected(client: TestClient, db_session: Session) -> None:
    login(client)
    row = db_session.scalar(select(UserSession))
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    db_session.commit()
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_anonymous_cannot_read_protected_resources(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/projects").status_code == 401
    assert client.get("/api/v1/dashboard/summary").status_code == 401
    assert client.get("/api/v1/admin/status").status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 401


def test_member_admin_status_is_forbidden(client: TestClient, db_session: Session) -> None:
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
    login(client, "alice", "Alice_Pass_123")
    response = client.get("/api/v1/admin/status")
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    assert response.json()["message"] == "权限不足"


def test_admin_status_counts_real_users(client: TestClient, db_session: Session) -> None:
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
    login(client)
    response = client.get("/api/v1/admin/status")
    assert response.status_code == 200
    assert response.json()["data"]["userCount"] == 2
    assert response.json()["data"]["projectCount"] == 0
    assert response.json()["data"]["role"] == "admin"


def test_bootstrap_does_not_reset_existing_password(db_session: Session) -> None:
    user = db_session.scalar(select(User).where(User.username == "admin"))
    assert user is not None
    user.password_hash = hash_password("Another_Pass_123")
    db_session.commit()
    changed = user.password_hash
    bootstrap_admin(get_settings())
    db_session.expire_all()
    refreshed = db_session.scalar(select(User).where(User.username == "admin"))
    assert refreshed is not None
    assert refreshed.password_hash == changed
    assert not refreshed.password_hash.startswith(ADMIN_PASSWORD)


def test_secret_key_changes_session_token_hash(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.core.security import hash_token

    plain = hashlib.sha256(b"session-token").hexdigest()
    get_settings.cache_clear()
    monkeypatch.setenv("ZHITEST_SECRET_KEY", "unit-test-secret")
    try:
        assert hash_token("session-token") != plain
    finally:
        get_settings.cache_clear()


def test_session_ttl_setting_matches_team_case() -> None:
    assert get_settings().session_ttl_seconds == 7200


def test_proxy_header_is_ignored_unless_enabled(client: TestClient, db_session: Session) -> None:
    response = login(client)
    assert response.status_code == 200
    db_session.expire_all()
    row = db_session.scalar(select(AuditLog).where(AuditLog.action == "auth.login"))
    assert row is not None
    assert row.ip == "testclient"
    client.cookies.clear()
    spoofed = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
        headers={"X-Real-IP": "10.1.2.3"},
    )
    assert spoofed.status_code == 200
    db_session.expire_all()
    rows = db_session.scalars(select(AuditLog).where(AuditLog.action == "auth.login")).all()
    assert all(item.ip != "10.1.2.3" for item in rows)
