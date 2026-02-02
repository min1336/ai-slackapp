from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    settlement_day: Mapped[str] = mapped_column(String(20), nullable=False)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), default="")
    company_sub_name: Mapped[str] = mapped_column(String(200), default="")
    settlement_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    carmore_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_refund_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    issue_type: Mapped[str] = mapped_column(String(100), default="")
    sales_channel: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(100), nullable=False)
    thread_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    # Sync metadata
    sheets_synced: Mapped[bool] = mapped_column(Boolean, default=False)
    sheets_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sheets_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="pending")

    # Relationship
    approval_logs: Mapped[list[ApprovalLog]] = relationship(back_populates="settlement")


class ApprovalLog(Base):
    __tablename__ = "approval_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int | None] = mapped_column(
        ForeignKey("settlements.id"), nullable=True
    )
    booking_key: Mapped[str] = mapped_column(String(100), nullable=False)
    settlement_day: Mapped[str] = mapped_column(String(20), nullable=False)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), default="")
    company_sub_name: Mapped[str] = mapped_column(String(200), default="")
    settlement_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    carmore_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_refund_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    issue_type: Mapped[str] = mapped_column(String(100), default="")
    sales_channel: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(100), nullable=False)
    thread_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Sync metadata
    sheets_synced: Mapped[bool] = mapped_column(Boolean, default=False)
    sheets_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sheets_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="pending")

    # Relationship
    settlement: Mapped[Settlement | None] = relationship(back_populates="approval_logs")
