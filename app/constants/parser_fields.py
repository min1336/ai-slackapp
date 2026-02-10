from __future__ import annotations

from enum import StrEnum


class TransferMessageField(StrEnum):
    BOOKING_KEY = "이관 전 예약번호"
    CUSTOMER_NAME = "예약자명"
    COMPANY = "업체"
    COMPANY_NAME = "업체명"
    COMPANY_SUB_NAME = "업체명2(대신배차)"
    PRINCIPAL = "원금"
    CARMORE_COST = "카모아 부담금"
    CARMORE_BURDEN = "카모아 부담비용"


class DateFormat(StrEnum):
    DATETIME = "%Y-%m-%d %H:%M:%S"
    DATE_ONLY = "%Y-%m-%d"
