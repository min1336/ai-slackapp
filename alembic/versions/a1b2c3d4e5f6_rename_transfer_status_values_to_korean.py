"""rename transfer_status values to korean

Revision ID: a1b2c3d4e5f6
Revises: 3d3c9d6f1a2b
Create Date: 2026-02-23 18:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "3d3c9d6f1a2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 값 매핑: (old, new)
_VALUE_MAPPING = [
    ("none", ""),
    ("transferred", "재이관"),
    ("reverted", "재이관반려"),
]


def upgrade() -> None:
    """기존 영어 값을 한국어로 변환하고 server_default를 빈 문자열로 변경."""
    for old, new in _VALUE_MAPPING:
        op.execute(
            f"UPDATE settlements SET transfer_status = '{new}'"
            f" WHERE transfer_status = '{old}'"
        )
        op.execute(
            f"UPDATE issue_logs SET transfer_status = '{new}'"
            f" WHERE transfer_status = '{old}'"
        )

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.alter_column(
            "settlements",
            "transfer_status",
            server_default="",
        )
        op.alter_column(
            "issue_logs",
            "transfer_status",
            server_default="",
        )


def downgrade() -> None:
    """한국어 값을 영어로 되돌린다."""
    for old, new in _VALUE_MAPPING:
        op.execute(
            f"UPDATE settlements SET transfer_status = '{old}'"
            f" WHERE transfer_status = '{new}'"
        )
        op.execute(
            f"UPDATE issue_logs SET transfer_status = '{old}'"
            f" WHERE transfer_status = '{new}'"
        )

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.alter_column(
            "settlements",
            "transfer_status",
            server_default="none",
        )
        op.alter_column(
            "issue_logs",
            "transfer_status",
            server_default="none",
        )
