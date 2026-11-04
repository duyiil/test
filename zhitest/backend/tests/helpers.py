from __future__ import annotations

from fastapi.testclient import TestClient


ADMIN_PASSWORD = "Admin_Pass_123"


def login(client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def auth_headers_from_login(client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD) -> None:
    response = login(client, username, password)
    assert response.status_code == 200, response.text
