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
    company_name: str = ""  # 업체명 (요구사항상 기본은 비움)
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

    @field_validator("customer_name", mode="before")
    @classmethod
    def clean_customer_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            return v
        # 괄호 뒤 추가정보 제거 (예: "홍길동 (010-...)" -> "홍길동")
        return v.split("(")[0].strip()

    @field_validator("settlement_cost", "carmore_cost", mode="before")
    @classmethod
    def digits_only_money(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            return v
        return re.sub(r"[^0-9]", "", v)


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

    def _remove_bold(v: str) -> str:
        if not isinstance(v, str) or not v:
            return ""
        return re.sub(r"\*([^*]+)\*", r"\1", v).strip()

    def _clean_name(v: str) -> str:
        v = _remove_bold(v)
        return v.split("(")[0].strip()

    def _digits_only(v: str) -> str:
        v = _remove_bold(v)
        return re.sub(r"[^0-9]", "", v)

    lines = text.split("\n")
    i = 0
    n = len(lines)

    # 1) 인라인 "키 : 값" 패턴을 먼저 훑어서 채운다.
    #    (메시지 상단의 "이관 전 예약번호 : 1095976" 같은 형태 지원)
    inline_patterns: list[tuple[str, re.Pattern[str], str]] = [
        (
            "booking_key",
            re.compile(r"이관\s*전\s*예약번호\s*[:：]\s*([^\s]+)"),
            "booking_key",
        ),
        ("customer_name", re.compile(r"예약자명\s*[:：]\s*(.+)"), "customer_name"),
        ("company_sub_name", re.compile(r"업체\s*[:：]\s*(.+)"), "company_sub_name"),
        (
            "settlement_cost",
            re.compile(r"원금\s*[:：]\s*([0-9,]+)\s*원?"),
            "settlement_cost",
        ),
        (
            "carmore_cost",
            re.compile(r"카모아\s*부담(?:비용|금)\s*[:：]\s*([0-9,]+)\s*원?"),
            "carmore_cost",
        ),
    ]

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        for _, pattern, field_name in inline_patterns:
            match = pattern.search(line)
            if not match:
                continue
            current = getattr(result, field_name)
            if current:
                continue
            raw_value = match.group(1).strip()
            if field_name == "customer_name":
                setattr(result, field_name, _clean_name(raw_value))
            elif field_name in ("settlement_cost", "carmore_cost"):
                setattr(result, field_name, _digits_only(raw_value))
            else:
                setattr(result, field_name, _remove_bold(raw_value))

    while i < n:
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        def _next_value(start: int) -> str:
            j = start
            while j < n:
                v = lines[j].strip()
                if v:
                    return v
                j += 1
            return ""

        # "이관 전 예약번호" 다음 줄의 값 추출
        if line == "이관 전 예약번호":
            if not result.booking_key:
                result.booking_key = _remove_bold(_next_value(i + 1))
            i += 1
            continue

        # "예약자명" 다음 줄의 값 추출
        if line == "예약자명":
            if not result.customer_name:
                result.customer_name = _clean_name(_next_value(i + 1))
            i += 1
            continue

        # 요구사항: 업체명은 비우고, 업체/업체명/업체명2(대신배차)는 업체명2로 채운다.
        if line in ("업체", "업체명", "업체명2(대신배차)"):
            if not result.company_sub_name:
                result.company_sub_name = _remove_bold(_next_value(i + 1))
            i += 1
            continue

        # "원금 :" 패턴에서 금액 추출
        if "원금" in line and ":" in line:
            match = re.search(r"원금\s*[:：]\s*([0-9,]+)원", line)
            if match and not result.settlement_cost:
                result.settlement_cost = _digits_only(match.group(1))
            i += 1
            continue

        # "카모아 부담비용"/"카모아 부담금" 다음 줄의 값 추출
        if line in ("카모아 부담비용", "카모아 부담금"):
            if not result.carmore_cost:
                result.carmore_cost = _digits_only(_next_value(i + 1))
            i += 1
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
