"""test_match 公共夹具：指向后端代码与测试库。

与 zhitest/backend/tests/conftest.py 保持同样的环境约定：
测试库 zhitest_test、auto_bootstrap 关闭、LLM 密钥留空（Mock 研判）。
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "zhitest" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://zhitest:zhitest@127.0.0.1:5432/zhitest_test")
os.environ.setdefault("ZHITEST_ENV", "test")
os.environ["ZHITEST_AUTO_BOOTSTRAP"] = "false"
os.environ["ZHITEST_ADMIN_USERNAME"] = "admin"
os.environ["ZHITEST_ADMIN_PASSWORD"] = "Admin_Pass_123"
os.environ["ZHITEST_ADMIN_DISPLAY_NAME"] = "系统管理员"
os.environ["ZHITEST_COOKIE_SECURE"] = "false"
os.environ["ZHITEST_TRUST_PROXY"] = "false"
os.environ["ZHITEST_SESSION_TTL_SECONDS"] = "7200"
os.environ["ZHITEST_LOG_LEVEL"] = "WARNING"
os.environ["ZHITEST_LLM_API_KEY"] = ""
os.environ["ZHITEST_TARGET_ALLOWLIST"] = "127.0.0.1,localhost,::1"

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.main import app
from app.modules.bootstrap import bootstrap_admin


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    # 从 test/test_match 运行时，ini 里的相对路径不再指向后端目录，改为显式绝对路径
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(BACKEND_ROOT))
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
        conn.execute(
            text(
                "TRUNCATE TABLE schedule_events, schedules, defect_candidates, notifications, idempotency_records, "
                "suite_items, suites, project_members, project_environments, data_reports, run_results, "
                "test_runs, review_events, test_case_versions, generation_targets, test_cases, "
                "generation_tasks, api_endpoints, audit_logs, projects, user_sessions, users "
                "RESTART IDENTITY CASCADE"
            )
        )
