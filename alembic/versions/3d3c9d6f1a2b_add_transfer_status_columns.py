"""add transfer_status columns

Revision ID: 3d3c9d6f1a2b
Revises: f7a08a3118ab
Create Date: 2026-02-23 13:45:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3d3c9d6f1a2b"
down_revision: str | Sequence[str] | None = "f7a08a3118ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "settlements",
        sa.Column(
            "transfer_status",
            sa.String(length=20),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "issue_logs",
        sa.Column(
            "transfer_status",
            sa.String(length=20),
            nullable=False,
            server_default="none",
        ),
    )
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.alter_column("settlements", "transfer_status", server_default=None)
        op.alter_column("issue_logs", "transfer_status", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("issue_logs", "transfer_status")
    op.drop_column("settlements", "transfer_status")
