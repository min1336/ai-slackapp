from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# PostgreSQL uses bigint + sequence; SQLite needs INTEGER for autoincrement
_BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (
        Index("ix_settlements_booking_key", "booking_key"),
        Index("idx_settlements_booking_key", "booking_key"),
        Index("idx_settlements_created_at", "created_at"),
        Index("idx_settlements_status", "status"),
        Index(
            "idx_settlements_sync_status",
            "sync_status",
            postgresql_where=text("sync_status = 'pending'"),
            sqlite_where=text("sync_status = 'pending'"),
        ),
        Index(
            "uq_settlements_booking_key_active",
            "booking_key",
            unique=True,
            postgresql_where=text("settlement_completed = false"),
            sqlite_where=text("settlement_completed = 0"),
        ),
    )

    id: Mapped[int] = mapped_column(_BigIntPK, primary_key=True)
    booking_key: Mapped[str] = mapped_column(String(100), nullable=False)
    settlement_day: Mapped[str] = mapped_column(String(20), nullable=False)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), default="", nullable=True)
    company_sub_name: Mapped[str] = mapped_column(
        String(200), default="", nullable=True
    )
    settlement_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    carmore_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_refund_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    issue_type: Mapped[str] = mapped_column(String(100), default="", nullable=True)
    sales_channel: Mapped[str] = mapped_column(String(100), default="", nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(100), nullable=False)
    thread_url: Mapped[str] = mapped_column(Text, default="", nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=True
    )

    # Sync metadata
    sheets_synced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    sheets_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sheets_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=True
    )

    reviewer_name: Mapped[str] = mapped_column(String(100), default="", nullable=True)
    rejection_reason: Mapped[str] = mapped_column(Text, default="", nullable=True)
    settlement_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=True
    )

    # Relationship
    issue_logs: Mapped[list[IssueLog]] = relationship(back_populates="settlement")


class IssueLog(Base):
    __tablename__ = "issue_logs"
    __table_args__ = (
        Index("idx_approval_logs_booking_key", "booking_key"),
        Index("idx_approval_logs_settlement_id", "settlement_id"),
        Index(
            "idx_approval_logs_sync_status",
            "sync_status",
            postgresql_where=text("sync_status = 'pending'"),
            sqlite_where=text("sync_status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(_BigIntPK, primary_key=True)
    settlement_id: Mapped[int | None] = mapped_column(
        ForeignKey("settlements.id"), nullable=True
    )
    booking_key: Mapped[str] = mapped_column(String(100), nullable=False)
    settlement_day: Mapped[str] = mapped_column(String(20), nullable=False)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), default="", nullable=True)
    company_sub_name: Mapped[str] = mapped_column(
        String(200), default="", nullable=True
    )
    settlement_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    carmore_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_refund_cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    issue_type: Mapped[str] = mapped_column(String(100), default="", nullable=True)
    sales_channel: Mapped[str] = mapped_column(String(100), default="", nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(100), nullable=False)
    thread_url: Mapped[str] = mapped_column(Text, default="", nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=True)
    reviewer_name: Mapped[str] = mapped_column(String(100), default="", nullable=True)
    rejection_reason: Mapped[str] = mapped_column(Text, default="", nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=True
    )

    # Sync metadata
    sheets_synced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    sheets_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sheets_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=True
    )

    # Relationship
    settlement: Mapped[Settlement | None] = relationship(back_populates="issue_logs")


class ThreadReference(Base):
    """예약번호 → 정산이슈 스레드 매핑.

    이관 예약 감지 시 기존 정산이슈 스레드를 빠르게 찾기 위한 캐시 테이블.
    root_booking_key로 A→B→C 이관 체인을 추적한다.
    """

    __tablename__ = "thread_references"
    __table_args__ = (
        Index(
            "idx_thread_refs_booking_key",
            "booking_key",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(_BigIntPK, primary_key=True)
    booking_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    thread_ts: Mapped[str] = mapped_column(String(50), nullable=False)
    root_booking_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=True
    )
