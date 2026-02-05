from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum

from pydantic import BaseModel


class SettlementColumnIndex(IntEnum):
    """SettlementRow.to_row()의 컬럼 인덱스 (0-based)."""

    SETTLEMENT_DAY = 0
    USER_NAME = 1
    ISSUE_TYPE = 2
    CUSTOMER_NAME = 3
    BOOKING_KEY = 4
    COMPANY_NAME = 5
    COMPANY_SUB_NAME = 6
    SETTLEMENT_COST = 7
    CARMORE_COST = 8
    USER_REFUND_COST = 9
    SALES_CHANNEL = 10
    DESCRIPTION = 11
    STATUS = 12
    APPROVER_NAME = 13
    CREATED_AT = 14
    UPDATED_AT = 15
    THREAD_URL = 16
    NOTE = 17  # 비고 필드 인덱스
    # 승인로그 시트 전용 (to_row() + sync_key)
    SYNC_KEY = 18


class SettlementStatus(str, Enum):
    APPROVED = "승인"
    REJECTED = "반려"


class SettlementData(BaseModel):
    user_name: str = ""
    booking_key: str = ""
    company_name: str = ""
    customer_name: str = ""
    settlement_day: str = ""
    issue_type: str = ""
    settlement_cost: str = ""
    company_sub_name: str = ""
    carmore_cost: str = ""
    user_refund_cost: str = ""
    seller_channel: str = ""
    description: str = ""
    note: str = ""  # 비고 필드


class ModalMetadata(BaseModel):
    channel_id: str = ""
    thread_ts: str = ""
    message_ts: str = ""
    user_name: str = ""
    booking_key: str = ""
    company_name: str = ""
    customer_name: str = ""


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
    ) -> SettlementRow:
        return cls(
            settlement_day=data.settlement_day,
            user_name=data.user_name,
            customer_name=data.customer_name,
            booking_key=data.booking_key,
            company_name=data.company_name,
            company_sub_name=data.company_sub_name,
            settlement_cost=data.settlement_cost,
            carmore_cost=data.carmore_cost,
            user_refund_cost=data.user_refund_cost,
            issue_type=data.issue_type,
            sales_channel=data.seller_channel,
            description=data.description,
            status=status.value,
            approver_name=approver_name,
            thread_url=thread_url,
            note=data.note,
        )

    def to_row(self) -> list[str]:
        return [
            self.settlement_day,
            self.user_name,
            self.issue_type,
            self.customer_name,
            self.booking_key,
            self.company_name,
            self.company_sub_name,
            self.settlement_cost,
            self.carmore_cost,
            self.user_refund_cost,
            self.sales_channel,
            self.description,
            self.status,
            self.approver_name,
            self.created_at,
            self.updated_at,
            self.thread_url,
            self.note,  # 맨 마지막에 추가하여 기존 시트와 호환성 유지
        ]
