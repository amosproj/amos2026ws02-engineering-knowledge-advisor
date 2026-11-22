"""Adds the up axis of each CAD file to the uploads table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-22 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "uploads",
        sa.Column("up_axis", sa.String(), server_default="Z", nullable=False),
    )
    op.create_check_constraint(
        "ck_uploads_up_axis",
        "uploads",
        "up_axis IN ('X', 'Y', 'Z', '-X', '-Y', '-Z')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_uploads_up_axis", "uploads", type_="check")
    op.drop_column("uploads", "up_axis")
