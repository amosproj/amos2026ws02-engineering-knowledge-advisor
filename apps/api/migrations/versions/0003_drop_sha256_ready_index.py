"""Drops the unique index on the content hash of ready CAD files: machines may share a CAD file.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08 12:00:00.000000

Downgrade fails if several ready files share a hash.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "uq_cad_uploads_sha256_ready",
        table_name="cad_uploads",
        postgresql_where=sa.text("status = 'ready'"),
    )


def downgrade() -> None:
    op.create_index(
        "uq_cad_uploads_sha256_ready",
        "cad_uploads",
        ["sha256"],
        unique=True,
        postgresql_where=sa.text("status = 'ready'"),
    )
