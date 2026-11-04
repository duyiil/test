"""schedule history events

Revision ID: 0005_management
Revises: 0004_generation_provider
Create Date: 2026-11-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_management"
down_revision: Union[str, Sequence[str], None] = "0004_generation_provider"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("schedule_id", sa.Uuid(), sa.ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("test_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_schedule_events_schedule_id", "schedule_events", ["schedule_id"])


def downgrade() -> None:
    op.drop_index("ix_schedule_events_schedule_id", table_name="schedule_events")
    op.drop_table("schedule_events")
