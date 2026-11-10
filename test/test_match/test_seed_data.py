"""柴诗雨功能：数据访问层与默认项目种子数据。

对应测试用例 TCM-SEED-001 ~ 004，见本目录 README。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.project import Project
from app.models.testing import ApiEndpoint
from app.modules.seed import DEFAULT_PROJECT_NAME, DEFAULT_SUT_BASE_URL, seed_default_project


def _login(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin_Pass_123"})
    assert response.status_code == 200, response.text


def test_seed_creates_default_project_with_demo_contract() -> None:
    """TCM-SEED-001：空库上执行种子后，管理员名下出现默认项目且载入演示契约。"""

    project = seed_default_project(get_settings())
    assert project is not None
    assert project.name == DEFAULT_PROJECT_NAME
    assert project.base_url == DEFAULT_SUT_BASE_URL
    assert project.env_label == "default"
    assert project.status == "active"

    db = SessionLocal()
    try:
        endpoint_count = len(
            list(db.scalars(select(ApiEndpoint).where(ApiEndpoint.project_id == project.id)).all())
        )
    finally:
        db.close()
    # 演示契约共 3 个接口：GET 列表、GET 详情、POST 创建
    assert endpoint_count == 3


def test_seed_is_idempotent() -> None:
    """TCM-SEED-002：重复执行种子不会创建第二个项目。"""

    first = seed_default_project(get_settings())
    second = seed_default_project(get_settings())
    assert first is not None
    assert second is None

    db = SessionLocal()
    try:
        projects = list(db.scalars(select(Project)).all())
    finally:
        db.close()
    assert len(projects) == 1


def test_seed_visible_via_api_after_login(client: TestClient) -> None:
    """TCM-SEED-003：种子项目通过项目列表接口可见，Base URL 指向 8001。"""

    seed_default_project(get_settings())
    _login(client)
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["name"] == DEFAULT_PROJECT_NAME
    assert items[0]["baseUrl"] == DEFAULT_SUT_BASE_URL
    assert items[0]["endpointCount"] == 3


def test_seed_skips_when_seed_demo_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """TCM-SEED-004：ZHITEST_SEED_DEMO=false 时不创建种子项目。"""

    from app.core.config import get_settings as raw_get_settings

    monkeypatch.setenv("ZHITEST_SEED_DEMO", "false")
    raw_get_settings.cache_clear()
    try:
        assert seed_default_project(get_settings()) is None
    finally:
        monkeypatch.delenv("ZHITEST_SEED_DEMO", raising=False)
        raw_get_settings.cache_clear()
