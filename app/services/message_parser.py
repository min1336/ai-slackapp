from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, field_validator


class BookingMessageField(str, Enum):
    booking_key = "예약번호"
    company_name = "업체"
    customer_name = "예약자명"


class ParsedSettlement(BaseModel):
    booking_key: str = ""  # 예약번호
    company_name: str = ""  # 업체명
    customer_name: str = ""  # 예약자명

    @field_validator("customer_name", mode="before")
    @classmethod
    def clean_customer_name(cls, v: str) -> str:
        if not v:
            return v
        # 먼저 bold 마크업 제거
        v = re.sub(r"\*([^*]+)\*", r"\1", v).strip()
        return v.split("(")[0].strip()

    @field_validator("booking_key", "company_name", mode="before")
    @classmethod
    def remove_markdown_bold(cls, v: str) -> str:
        """Slack bold 마크업(*) 제거"""
        if not isinstance(v, str):
            return v
        return re.sub(r"\*([^*]+)\*", r"\1", v).strip()


class ParsedTransferReservation(BaseModel):
    booking_key: str = ""  # 이관 전 예약번호
    customer_name: str = ""  # 예약자명
    company_sub_name: str = ""  # 업체명 (company_name은 비워둠)
    settlement_cost: str = ""  # 원금
    carmore_cost: str = ""  # 카모아 부담비용

    @field_validator("*", mode="before")
    @classmethod
    def remove_markdown_bold(cls, v: str) -> str:
        """Slack bold 마크업(*) 제거"""
        if not isinstance(v, str):
            return v
        # *text* → text
        return re.sub(r"\*([^*]+)\*", r"\1", v).strip()


def is_transfer_reservation_message(text: str) -> bool:
    """이관 예약 메시지 패턴 확인"""
    return "이관 전 예약번호" in text


def parse_transfer_reservation_message(text: str) -> ParsedTransferReservation:
    """이관 예약 메시지 파싱

    Example format:
        이관 전 예약번호
        1095976
        예약자명
        박종선
        업체명
        (주)특별한렌트카[카모아 예약]
        ...
        원금 : 111,111원 (대여 : 79,500원, 자차 : 30,000원, 배달 : 20,000원)
        ...
        카모아 부담비용
        0
    """
    result = ParsedTransferReservation()

    lines = text.split("\n")
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()

        # "이관 전 예약번호" 다음 줄의 값 추출
        if line == "이관 전 예약번호":
            if i + 1 < n:
                result.booking_key = lines[i + 1].strip()
            i += 2
            continue

        # "예약자명" 다음 줄의 값 추출
        if line == "예약자명":
            if i + 1 < n:
                result.customer_name = lines[i + 1].strip()
            i += 2
            continue

        # "업체명" 다음 줄의 값 추출
        if line == "업체명":
            if i + 1 < n:
                result.company_sub_name = lines[i + 1].strip()
            i += 2
            continue

        # "원금 :" 패턴에서 금액 추출
        if "원금" in line and ":" in line:
            match = re.search(r"원금\s*[:：]\s*([0-9,]+)원", line)
            if match:
                result.settlement_cost = match.group(1)
            i += 1
            continue

        # "카모아 부담비용" 다음 줄의 값 추출
        if line == "카모아 부담비용":
            if i + 1 < n:
                result.carmore_cost = lines[i + 1].strip()
            i += 2
            continue

        i += 1

    return result


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
