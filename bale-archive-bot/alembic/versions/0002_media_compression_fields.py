"""Add media size / compression accounting columns.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media_files", sa.Column("original_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("media_files", sa.Column("stored_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column(
        "media_files",
        sa.Column(
            "is_compressed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("media_files", "is_compressed")
    op.drop_column("media_files", "stored_size_bytes")
    op.drop_column("media_files", "original_size_bytes")
