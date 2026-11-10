"""数据访问层与默认项目种子数据。

柴诗雨任务：bootstrap 阶段为管理员准备一个开箱可用的默认项目——
Base URL 指向 8001 端口的 demo/sut，并载入演示契约，
让「生成 → 审核 → 执行 → 报告」在空库上无需手工建项目即可演示。

幂等：仅当管理员名下没有任何项目时才创建，重复启动不会产生重复数据。
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models.project import Project
from app.models.user import User

logger = logging.getLogger("zhitest.seed")

DEFAULT_PROJECT_NAME = "演示项目（SUT 8001）"
DEFAULT_PROJECT_DESCRIPTION = "bootstrap 种子项目：被测服务为 8001 端口的 demo/sut，已载入演示契约。"
DEFAULT_SUT_BASE_URL = "http://127.0.0.1:8001"
SEED_IP = "127.0.0.1"


def seed_default_project(settings: Settings | None = None) -> Project | None:
    """为管理员创建默认演示项目（幂等）。

    返回新创建的项目；已有项目时返回 None。
    """

    settings = settings or get_settings()
    if not settings.seed_demo:
        logger.info("seed demo disabled by ZHITEST_SEED_DEMO, skipped")
        return None

    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.username == settings.admin_username))
        if admin is None:
            logger.warning("seed skipped: admin user not found")
            return None
        owned = db.scalar(select(Project.id).where(Project.owner_id == admin.id).limit(1))
        if owned is not None:
            logger.info("seed skipped: admin already owns projects")
            return None

        from app.modules.projects.service import create_project
        from app.modules.testing.service import load_demo_contract

        project = create_project(
            db,
            admin,
            name=DEFAULT_PROJECT_NAME,
            description=DEFAULT_PROJECT_DESCRIPTION,
            base_url=DEFAULT_SUT_BASE_URL,
            env_label="default",
            ip=SEED_IP,
        )
        load_demo_contract(db, admin, project.id, ip=SEED_IP)
        db.commit()
        logger.info("seed default project created: %s -> %s", project.id, DEFAULT_SUT_BASE_URL)
        return project
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
