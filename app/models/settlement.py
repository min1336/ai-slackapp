from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, field_validator


class SettlementStatus(str, Enum):
    REQUESTED = "요청"
    APPROVED = "승인"
    REJECTED = "반려"


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
    """반려 모달용 메타데이터"""

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
    """int 금액을 시트 저장용 str로 변환."""
    if value is None:
        return ""
    return str(value)


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
    issue_type: str = ""
    sales_channel: str = ""
    created_at: str = ""
    updated_at: str = ""
    thread_url: str = ""
    note: str = ""  # 비고 필드
    reviewer_name: str = ""
    rejection_reason: str = ""
    settlement_completed: str = "FALSE"  # 정산 시트 전용, to_dict()에 미포함

    def __post_init__(self) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    @classmethod
    def from_settlement_data(
        cls,
        data: SettlementData,
        status: SettlementStatus,
        approver_name: str,
        thread_url: str = "",
        rejection_reason: str = "",
    ) -> SettlementRow:
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
            approver_name=approver_name,
            thread_url=thread_url,
            note=data.note or "",
            reviewer_name=approver_name,
            rejection_reason=rejection_reason,
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
