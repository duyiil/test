from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
os.environ["DATABASE_URL"] = "postgresql+psycopg://zhitest:zhitest@127.0.0.1:5432/zhitest_test"
os.environ["ZHITEST_ENV"] = "test"
os.environ["ZHITEST_AUTO_BOOTSTRAP"] = "false"
os.environ["ZHITEST_ADMIN_USERNAME"] = "admin"
os.environ["ZHITEST_ADMIN_PASSWORD"] = "Admin_Pass_123"
os.environ["ZHITEST_ADMIN_DISPLAY_NAME"] = "系统管理员"
os.environ["ZHITEST_COOKIE_SECURE"] = "false"
os.environ["ZHITEST_TRUST_PROXY"] = "false"
os.environ["ZHITEST_SESSION_TTL_SECONDS"] = "7200"
os.environ["ZHITEST_LOG_LEVEL"] = "WARNING"

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.main import app
from app.modules.bootstrap import bootstrap_admin


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    _truncate()
    bootstrap_admin(get_settings())
    yield
    _truncate()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def _truncate() -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE audit_logs, projects, user_sessions, users RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_session() -> Generator[object, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
