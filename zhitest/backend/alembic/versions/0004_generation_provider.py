"""generation task provider and model

Revision ID: 0004_generation_provider
Revises: 0003_platform
Create Date: 2026-11-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_generation_provider"
down_revision: Union[str, Sequence[str], None] = "0003_platform"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generation_tasks",
        sa.Column("provider", sa.String(32), nullable=False, server_default="mock"),
    )
    op.add_column("generation_tasks", sa.Column("model_name", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("generation_tasks", "model_name")
    op.drop_column("generation_tasks", "provider")
