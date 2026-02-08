"""baseline: existing schema

Revision ID: 83c070e537ee
Revises:
Create Date: 2026-02-06 16:56:17.309310

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "83c070e537ee"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create settlements and issue_logs tables."""
    _pk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

    op.create_table(
        "settlements",
        sa.Column("id", _pk, primary_key=True),
        sa.Column("booking_key", sa.String(100), nullable=False),
        sa.Column("settlement_day", sa.String(20), nullable=False),
        sa.Column("user_name", sa.String(100), nullable=False),
        sa.Column("customer_name", sa.String(100), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=True, server_default=""),
        sa.Column("company_sub_name", sa.String(200), nullable=True, server_default=""),
        sa.Column("settlement_cost", sa.BigInteger(), nullable=True),
        sa.Column("carmore_cost", sa.BigInteger(), nullable=True),
        sa.Column("user_refund_cost", sa.BigInteger(), nullable=True),
        sa.Column("issue_type", sa.String(100), nullable=True, server_default=""),
        sa.Column("sales_channel", sa.String(100), nullable=True, server_default=""),
        sa.Column("description", sa.Text(), nullable=True, server_default=""),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("approver_name", sa.String(100), nullable=False),
        sa.Column("thread_url", sa.Text(), nullable=True, server_default=""),
        sa.Column("note", sa.Text(), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "sheets_synced",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("false"),
        ),
        sa.Column("sheets_synced_at", sa.DateTime(), nullable=True),
        sa.Column("sheets_sync_error", sa.Text(), nullable=True),
        sa.Column(
            "sync_status",
            sa.String(20),
            nullable=True,
            server_default="pending",
        ),
        sa.Column(
            "reviewer_name",
            sa.String(100),
            nullable=True,
            server_default="",
        ),
        sa.Column(
            "rejection_reason",
            sa.Text(),
            nullable=True,
            server_default="",
        ),
        sa.Column(
            "settlement_completed",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_settlements_booking_key", "settlements", ["booking_key"])
    op.create_index("idx_settlements_booking_key", "settlements", ["booking_key"])
    op.create_index("idx_settlements_created_at", "settlements", ["created_at"])
    op.create_index("idx_settlements_status", "settlements", ["status"])
    op.create_index(
        "idx_settlements_sync_status",
        "settlements",
        ["sync_status"],
        postgresql_where=sa.text("sync_status = 'pending'"),
        sqlite_where=sa.text("sync_status = 'pending'"),
    )
    op.create_index(
        "uq_settlements_booking_key_active",
        "settlements",
        ["booking_key"],
        unique=True,
        postgresql_where=sa.text("settlement_completed = false"),
        sqlite_where=sa.text("settlement_completed = 0"),
    )

    op.create_table(
        "issue_logs",
        sa.Column("id", _pk, primary_key=True),
        sa.Column(
            "settlement_id",
            sa.BigInteger(),
            sa.ForeignKey("settlements.id"),
            nullable=True,
        ),
        sa.Column("booking_key", sa.String(100), nullable=False),
        sa.Column("settlement_day", sa.String(20), nullable=False),
        sa.Column("user_name", sa.String(100), nullable=False),
        sa.Column("customer_name", sa.String(100), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=True, server_default=""),
        sa.Column("company_sub_name", sa.String(200), nullable=True, server_default=""),
        sa.Column("settlement_cost", sa.BigInteger(), nullable=True),
        sa.Column("carmore_cost", sa.BigInteger(), nullable=True),
        sa.Column("user_refund_cost", sa.BigInteger(), nullable=True),
        sa.Column("issue_type", sa.String(100), nullable=True, server_default=""),
        sa.Column("sales_channel", sa.String(100), nullable=True, server_default=""),
        sa.Column("description", sa.Text(), nullable=True, server_default=""),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("approver_name", sa.String(100), nullable=False),
        sa.Column("thread_url", sa.Text(), nullable=True, server_default=""),
        sa.Column("note", sa.Text(), nullable=True, server_default=""),
        sa.Column("reviewer_name", sa.String(100), nullable=True, server_default=""),
        sa.Column("rejection_reason", sa.Text(), nullable=True, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column(
            "sheets_synced",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("false"),
        ),
        sa.Column("sheets_synced_at", sa.DateTime(), nullable=True),
        sa.Column("sheets_sync_error", sa.Text(), nullable=True),
        sa.Column(
            "sync_status",
            sa.String(20),
            nullable=True,
            server_default="pending",
        ),
    )
    op.create_index("idx_approval_logs_booking_key", "issue_logs", ["booking_key"])
    op.create_index("idx_approval_logs_settlement_id", "issue_logs", ["settlement_id"])
    op.create_index(
        "idx_approval_logs_sync_status",
        "issue_logs",
        ["sync_status"],
        postgresql_where=sa.text("sync_status = 'pending'"),
        sqlite_where=sa.text("sync_status = 'pending'"),
    )


def downgrade() -> None:
    """Drop issue_logs and settlements tables."""
    op.drop_table("issue_logs")
    op.drop_table("settlements")
