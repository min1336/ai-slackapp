from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, field_validator


class BookingMessageField(str, Enum):
    """메시지 필드 (영문 필드명 = 한글 레이블)"""
    booking_key = "예약번호"
    company_name = "업체"
    customer_name = "예약자명"


class ParsedSettlement(BaseModel):
    booking_key: str = ""   # 예약번호
    company_name: str = ""  # 업체명
    customer_name: str = "" # 예약자명

    @field_validator("customer_name", mode="before")
    @classmethod
    def clean_customer_name(cls, v: str) -> str:
        if not v:
            return v
        return v.split("(")[0].strip()


def parse_settlement_message(text: str) -> ParsedSettlement:
    data: dict[str, str] = {}

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        match = re.match(r"^([가-힣]+)\s*[:：]\s*(.+)$", line)
        if match:
            korean_key = match.group(1).strip()
            value = match.group(2).strip()

            for field in BookingMessageField:
                if field.value == korean_key:
                    data[field.name] = value
                    break

    return ParsedSettlement(**data)
