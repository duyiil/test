"""projects.site_scan: 网站检测摘要,供执行报告展示

Revision ID: 0006_site_scan
Revises: 0005_management
Create Date: 2026-11-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_site_scan"
down_revision: Union[str, Sequence[str], None] = "0005_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("site_scan", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "site_scan")
