from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, field_validator


@dataclass(frozen=True, slots=True)
class ThreadLocation:
    channel_id: str
    thread_ts: str


class SettlementStatus(StrEnum):
    REQUESTED = "요청"
    APPROVED = "승인"
    REJECTED = "반려"


class TransferStatus(StrEnum):
    NONE = ""
    TRANSFERRED = "재이관"
    REVERTED = "재이관반려"


class SettlementData(BaseModel):
    # ── 예약 정보 (필수) ──
    user_name: str
    booking_key: str
    company_name: str
    customer_name: str

    # ── 금액 정보 ──
    settlement_cost: int | None = None
    carmore_cost: int | None = None
    user_refund_cost: int | None = None

    # ── 이슈 정보 ──
    issue_type: str
    settlement_day: str
    company_sub_name: str | None = None
    seller_channel: str | None = None
    description: str | None = None
    note: str | None = None

    # ── 워크플로우 컨텍스트 ──
    requester_id: str
    original_channel_id: str | None = None
    original_thread_ts: str | None = None
    original_message_ts: str | None = None  # 대기중 메시지 ts (업데이트용)

    @field_validator(
        "settlement_cost", "carmore_cost", "user_refund_cost", mode="before"
    )
    @classmethod
    def parse_cost(cls, v: str | int | None) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, int):
            return v
        # "1,000,000원" → 1000000
        cleaned = re.sub(r"[^\d]", "", str(v))
        return int(cleaned) if cleaned else None


class ModalMetadata(BaseModel):
    channel_id: str = ""
    thread_ts: str = ""
    message_ts: str = ""
    user_name: str = ""
    booking_key: str = ""
    company_name: str = ""
    customer_name: str = ""


class RejectionMetadata(BaseModel):
    channel_id: str
    thread_ts: str
    message_ts: str
    requester_id: str
    button_data: str  # SettlementData JSON
    # 원본 스레드 정보 (승인 채널에서 반려 시 원본 스레드에 알림용)
    original_channel_id: str = ""
    original_thread_ts: str = ""
    original_message_ts: str = ""


def format_cost(value: int | None) -> str:
    if value is None:
        return ""
    return str(value)


@runtime_checkable
class RowConvertible(Protocol):
    settlement_day: str
    user_name: str
    customer_name: str
    booking_key: str
    company_name: str
    company_sub_name: str
    settlement_cost: int | None
    carmore_cost: int | None
    user_refund_cost: int | None
    issue_type: str
    sales_channel: str
    description: str
    status: str
    transfer_status: str
    approver_name: str
    thread_url: str
    reviewer_name: str
    rejection_reason: str
    created_at: datetime


@dataclass(slots=True)
class SettlementRow:
    settlement_day: str
    user_name: str
    customer_name: str
    booking_key: str
    company_name: str
    company_sub_name: str
    settlement_cost: str
    carmore_cost: str
    user_refund_cost: str
    description: str
    status: str
    approver_name: str
    transfer_status: str = TransferStatus.NONE.value
    issue_type: str = ""
    sales_channel: str = ""
    created_at: str = ""
    updated_at: str = ""
    thread_url: str = ""
    note: str = ""  # 비고 필드
    reviewer_name: str = ""
    rejection_reason: str = ""
    settlement_completed: str = "FALSE"  # 정산 시트 전용, to_dict()에 미포함

    @classmethod
    def from_settlement_data(
        cls,
        data: SettlementData,
        status: SettlementStatus,
        approver_name: str,
        thread_url: str = "",
        rejection_reason: str = "",
    ) -> SettlementRow:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return cls(
            settlement_day=data.settlement_day,
            user_name=data.user_name,
            customer_name=data.customer_name,
            booking_key=data.booking_key,
            company_name=data.company_name,
            company_sub_name=data.company_sub_name or "",
            settlement_cost=format_cost(data.settlement_cost),
            carmore_cost=format_cost(data.carmore_cost),
            user_refund_cost=format_cost(data.user_refund_cost),
            issue_type=data.issue_type,
            sales_channel=data.seller_channel or "",
            description=data.description or "",
            status=status.value,
            transfer_status=TransferStatus.NONE.value,
            approver_name=approver_name,
            thread_url=thread_url,
            note=data.note or "",
            reviewer_name=approver_name,
            rejection_reason=rejection_reason,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def from_entity(
        cls,
        entity: RowConvertible,
        *,
        include_updated_at: bool = True,
    ) -> SettlementRow:
        from app.constants import DateFormat

        updated_at = ""
        if include_updated_at and hasattr(entity, "updated_at"):
            updated_at = entity.updated_at.strftime(DateFormat.DATETIME)

        return cls(
            settlement_day=entity.settlement_day,
            user_name=entity.user_name,
            customer_name=entity.customer_name,
            booking_key=entity.booking_key,
            company_name=entity.company_name,
            company_sub_name=entity.company_sub_name,
            settlement_cost=format_cost(entity.settlement_cost),
            carmore_cost=format_cost(entity.carmore_cost),
            user_refund_cost=format_cost(entity.user_refund_cost),
            issue_type=entity.issue_type,
            sales_channel=entity.sales_channel,
            description=entity.description,
            status=entity.status,
            transfer_status=getattr(
                entity,
                "transfer_status",
                TransferStatus.NONE.value,
            ),
            approver_name=entity.approver_name,
            thread_url=entity.thread_url,
            created_at=entity.created_at.strftime(DateFormat.DATETIME),
            updated_at=updated_at,
            reviewer_name=entity.reviewer_name,
            rejection_reason=entity.rejection_reason,
            settlement_completed=(
                "TRUE" if getattr(entity, "settlement_completed", False) else "FALSE"
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name != "settlement_completed"
        }


SETTLEMENT_FIELDS: tuple[str, ...] = tuple(
    f.name for f in fields(SettlementRow) if f.name != "settlement_completed"
)
