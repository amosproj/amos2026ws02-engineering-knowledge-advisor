"""Enable pg_trgm extension for full-text search.

Adds the pg_trgm extension required by the /records/query endpoint
for trigram-based similarity search.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16 23:17:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
