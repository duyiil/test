import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_health_is_public_and_uses_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-Id": "req-health-1"})
    body = response.json()
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-health-1"
    assert body["code"] == "SUCCESS"
    assert body["message"] == "操作成功"
    assert body["details"] is None
    assert body["requestId"] == "req-health-1"
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] == "ok"
    assert body["data"]["phase"] == "phase1"


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-Id": "bad id\r\nX-Injected"})
    request_id = response.headers["x-request-id"]
    assert "\n" not in request_id
    assert " " not in request_id
    assert response.json()["requestId"] == request_id


def test_health_database_failure_hides_internals(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(self: Session, *args: object, **kwargs: object) -> None:
        raise RuntimeError("postgres password=supersecret")

    monkeypatch.setattr(Session, "execute", explode)
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert "supersecret" not in response.text
