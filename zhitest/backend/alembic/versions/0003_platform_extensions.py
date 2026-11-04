"""openapi, suites, ssrf support columns, idempotency, notifications

Revision ID: 0003_platform
Revises: 0002_phase2
Create Date: 2026-11-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_platform"
down_revision: Union[str, Sequence[str], None] = "0002_phase2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("status", sa.String(32), nullable=False, server_default="active"))
    op.add_column("api_endpoints", sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("test_case_versions", sa.Column("extract", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column(
        "test_case_versions",
        sa.Column("dependencies", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("test_runs", sa.Column("suite_id", sa.Uuid(), nullable=True))
    op.add_column("test_runs", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.add_column("test_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("test_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("test_runs", sa.Column("fencing_token", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "project_environments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "name", name="uq_project_environments_name"),
    )
    op.create_table(
        "project_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members"),
    )
    op.create_table(
        "suites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_regression", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "name", name="uq_suites_project_name"),
    )
    op.create_table(
        "suite_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("suite_id", sa.Uuid(), sa.ForeignKey("suites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("suite_id", "position", name="uq_suite_items_position"),
    )
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idem_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "idem_key", name="uq_idempotency_user_key"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_table(
        "defect_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("test_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "schedules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("suite_id", sa.Uuid(), sa.ForeignKey("suites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cron", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("schedules")
    op.drop_table("defect_candidates")
    op.drop_table("notifications")
    op.drop_table("idempotency_records")
    op.drop_table("suite_items")
    op.drop_table("suites")
    op.drop_table("project_members")
    op.drop_table("project_environments")
    op.drop_column("test_runs", "fencing_token")
    op.drop_column("test_runs", "lease_expires_at")
    op.drop_column("test_runs", "heartbeat_at")
    op.drop_column("test_runs", "idempotency_key")
    op.drop_column("test_runs", "suite_id")
    op.drop_column("test_case_versions", "dependencies")
    op.drop_column("test_case_versions", "extract")
    op.drop_column("api_endpoints", "disabled")
    op.drop_column("projects", "status")
