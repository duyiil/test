"""phase 2 cases, runs, and reports

Revision ID: 0002_phase2
Revises: 0001_phase1
Create Date: 2026-11-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase2"
down_revision: Union[str, Sequence[str], None] = "0001_phase1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_endpoints",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("spec_version", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("summary", sa.String(200), nullable=False, server_default=""),
        sa.Column("contract", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "method", "path", name="uq_api_endpoints_project_method_path"),
    )
    op.create_index("ix_api_endpoints_project_id", "api_endpoints", ["project_id"])

    op.create_table(
        "generation_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_generation_tasks_project_id", "generation_tasks", ["project_id"])

    op.create_table(
        "test_cases",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), sa.ForeignKey("api_endpoints.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_test_cases_project_id", "test_cases", ["project_id"])

    op.create_table(
        "generation_targets",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("generation_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), sa.ForeignKey("api_endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_generation_targets_task_id", "generation_targets", ["task_id"])

    op.create_table(
        "test_case_versions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("spec_version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("scenario", sa.String(64), nullable=False, server_default=""),
        sa.Column("basis", sa.Text(), nullable=False, server_default=""),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("relative_path", sa.String(300), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("query", sa.JSON(), nullable=False),
        sa.Column("path_params", sa.JSON(), nullable=False),
        sa.Column("body", sa.JSON(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("assertions", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("origin", sa.String(32), nullable=False, server_default="mock"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("case_id", "version_number", name="uq_case_versions_number"),
    )
    op.create_index("ix_test_case_versions_case_id", "test_case_versions", ["case_id"])
    op.create_index("ix_test_case_versions_review_status", "test_case_versions", ["review_status"])

    op.create_table(
        "review_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("test_case_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_review_events_version_id", "review_events", ["version_id"])

    op.create_table(
        "test_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("executed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assertion_failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirm_writes", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("abort_reason", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_test_runs_project_id", "test_runs", ["project_id"])
    op.create_index("ix_test_runs_status", "test_runs", ["status"])

    op.create_table(
        "run_results",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_version_id", sa.Uuid(), sa.ForeignKey("test_case_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("error_class", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("assertion_results", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_run_results_run_id", "run_results", ["run_id"])

    op.create_table(
        "data_reports",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("ai_status", sa.String(32), nullable=False),
        sa.Column("ai_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("run_id", name="uq_data_reports_run_id"),
    )


def downgrade() -> None:
    op.drop_table("data_reports")
    op.drop_table("run_results")
    op.drop_table("test_runs")
    op.drop_table("review_events")
    op.drop_table("test_case_versions")
    op.drop_table("generation_targets")
    op.drop_table("test_cases")
    op.drop_table("generation_tasks")
    op.drop_table("api_endpoints")
