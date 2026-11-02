"""create machines

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "machines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_machines"),
        sa.UniqueConstraint("object_key", name="uq_machines_object_key"),
        sa.CheckConstraint(
            "status IN ('uploading', 'processing', 'ready', 'failed')",
            name=op.f("ck_machines_status"),
        ),
    )
    op.create_index(
        "uq_machines_sha256_ready",
        "machines",
        ["sha256"],
        unique=True,
        postgresql_where=sa.text("status = 'ready'"),
    )


def downgrade() -> None:
    op.drop_index("uq_machines_sha256_ready", table_name="machines")
    op.drop_table("machines")
