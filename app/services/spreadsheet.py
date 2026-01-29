from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import gspread
from google.oauth2.service_account import Credentials

from app.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


class SettlementStatus(str, Enum):
    APPROVED = "승인"
    REJECTED = "반려"


@dataclass
class SettlementRow:
    """스프레드시트에 저장할 정산 데이터"""

    settlement_day: str  # 정산기준일
    user_name: str  # 작성자
    customer_name: str  # 고객명
    booking_key: str  # 예약번호
    company_name: str  # 업체명1
    company_sub_name: str  # 업체명2(대신배차)
    settlement_cost: str  # 정산기준금액
    carmore_cost: str  # 카모아 부담비용
    user_refund_cost: str  # 고객환불금액
    description: str  # 내용
    status: str  # 처리 (승인/반려)
    approver_name: str  # 승인자
    issue_type: str = ""  # 이슈사항 (null)
    sales_channel: str = ""  # 판매채널 (null)
    created_at: str = ""  # 등록시간
    updated_at: str = ""  # 수정시간
    thread_url: str = ""  # 스레드 링크

    def __post_init__(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    @classmethod
    def from_button_data(
        cls,
        data: dict,
        status: SettlementStatus,
        approver_name: str,
        thread_url: str = "",
    ) -> SettlementRow:
        return cls(
            settlement_day=data.get("settlement_day", ""),
            user_name=data.get("user_name", ""),
            customer_name=data.get("customer_name", ""),
            booking_key=data.get("booking_key", ""),
            company_name=data.get("company_name", ""),
            company_sub_name=data.get("company_sub_name", ""),
            settlement_cost=data.get("settlement_cost", ""),
            carmore_cost=data.get("carmore_cost", ""),
            user_refund_cost=data.get("user_refund_cost", ""),
            issue_type=data.get("issue_type", ""),
            sales_channel=data.get("seller_channel", ""),
            description=data.get("description", ""),
            status=status.value,
            approver_name=approver_name,
            thread_url=thread_url,
        )

    def to_row(self) -> list[str]:
        """스프레드시트 행 데이터로 변환 (컬럼 순서에 맞게)"""
        return [
            self.settlement_day,  # 정산기준일
            self.user_name,  # 작성자
            self.issue_type,  # 이슈사항 (null)
            self.customer_name,  # 고객명
            self.booking_key,  # 예약번호
            self.company_name,  # 업체명1
            self.company_sub_name,  # 업체명2(대신배차)
            self.settlement_cost,  # 정산기준금액
            self.carmore_cost,  # 카모아 부담비용
            self.user_refund_cost,  # 고객환불금액
            self.sales_channel,  # 판매채널 (null)
            self.description,  # 내용
            self.status,  # 처리
            self.approver_name,  # 승인자
            self.created_at,  # 등록시간
            self.updated_at,  # 수정시간
            self.thread_url,  # 스레드 링크
        ]


def get_spreadsheet_client() -> gspread.Spreadsheet:
    """Google Sheets 클라이언트를 반환합니다."""
    credentials = Credentials.from_service_account_file(
        settings.GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES,
    )
    gc = gspread.authorize(credentials)
    return gc.open_by_key(settings.SPREADSHEET_ID)


def append_settlement_row(row: SettlementRow, sheet_name: str | None = None) -> bool:
    """
    정산 데이터를 스프레드시트에 추가합니다.

    Args:
        row: 정산 데이터
        sheet_name: 시트 이름 (기본값: settings.SHEET_NAME)

    Returns:
        성공 여부
    """
    if sheet_name is None:
        sheet_name = settings.SHEET_NAME

    try:
        spreadsheet = get_spreadsheet_client()
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.append_row(row.to_row())
        return True
    except Exception:
        return False
