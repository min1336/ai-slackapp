from __future__ import annotations

import re
from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, field_validator

from app.constants import TransferMessageField


class BookingMessageField(StrEnum):
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
        if not isinstance(v, str):
            return v
        return re.sub(r"\*([^*]+)\*", r"\1", v).strip()


class ParsedTransferReservation(BaseModel):
    booking_key: str = ""  # 이관 전 예약번호
    new_booking_key: str = ""  # 이관 후 예약번호
    customer_name: str = ""  # 예약자명
    company_name: str = ""  # 업체명 (요구사항상 기본은 비움)
    company_sub_name: str = ""  # 업체명 (company_name은 비워둠)
    settlement_cost: str = ""  # 원금
    carmore_cost: str = ""  # 카모아 부담비용

    @field_validator("*", mode="before")
    @classmethod
    def remove_markdown_bold(cls, v: str) -> str:
        if not isinstance(v, str):
            return v
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
        negative = v.strip().startswith("-")
        cleaned = re.sub(r"[^0-9]", "", v)
        if not cleaned:
            return v
        return f"-{cleaned}" if negative else cleaned


def is_transfer_reservation_message(text: str) -> bool:
    return TransferMessageField.BOOKING_KEY in text


# --- 파서 헬퍼 함수 (모듈 레벨) ---


def _strip_value(v: str) -> str:
    if not isinstance(v, str) or not v:
        return ""
    return v.strip()


def _clean_name(v: str) -> str:
    v = _strip_value(v)
    # 괄호 뒤 추가정보 제거: "홍길동 (010-...)" -> "홍길동"
    return v.split("(")[0].strip()


def _digits_only(v: str) -> str:
    v = _strip_value(v)
    negative = v.startswith("-")
    cleaned = re.sub(r"[^0-9]", "", v)
    if not cleaned:
        return v
    return f"-{cleaned}" if negative else cleaned


def _get_next_nonempty_line(lines: list[str], start: int) -> str:
    for line in lines[start:]:
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


# 인라인 패턴 정의 (컴파일은 한 번만)
_INLINE_PATTERNS: list[tuple[re.Pattern[str], str, Callable[[str], str]]] = [
    (
        re.compile(r"이관\s*전\s*예약번호\s*[:：]\s*([^\s]+)"),
        "booking_key",
        _strip_value,
    ),
    (
        re.compile(r"(?<!전\s)예약번호\s*[:：]\s*([^\s]+)"),
        "new_booking_key",
        _strip_value,
    ),
    (re.compile(r"예약자명\s*[:：]\s*(.+)"), "customer_name", _clean_name),
    (re.compile(r"업체\s*[:：]\s*(.+)"), "company_sub_name", _strip_value),
    (re.compile(r"원금\s*[:：]\s*(-?[0-9,]+)\s*원?"), "settlement_cost", _digits_only),
    (
        re.compile(r"카모아\s*부담(?:비용|금)\s*[:：]\s*(-?[0-9,]+)\s*원?"),
        "carmore_cost",
        _digits_only,
    ),
]

# 멀티라인 필드 매핑 (키 라인 → (필드명, 변환 함수))
_MULTILINE_FIELD_MAP: dict[str, tuple[str, Callable[[str], str]]] = {
    TransferMessageField.BOOKING_KEY: ("booking_key", _strip_value),
    TransferMessageField.CUSTOMER_NAME: ("customer_name", _clean_name),
    TransferMessageField.COMPANY: ("company_sub_name", _strip_value),
    TransferMessageField.COMPANY_NAME: ("company_sub_name", _strip_value),
    TransferMessageField.COMPANY_SUB_NAME: ("company_sub_name", _strip_value),
}


def parse_transfer_reservation_message(text: str) -> ParsedTransferReservation:
    result = ParsedTransferReservation()

    # 전체 텍스트에서 볼드 마크업 제거 (슬랙 포맷팅 정규화)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    lines = text.split("\n")

    # 1) 인라인 "키 : 값" 패턴 추출
    _extract_inline_patterns(result, lines)

    # 2) 멀티라인 패턴 추출 (키가 한 줄, 값이 다음 줄)
    _extract_multiline_patterns(result, lines)

    return result


def _extract_inline_patterns(
    result: ParsedTransferReservation, lines: list[str]
) -> None:
    for line in lines:
        line = line.strip()
        if not line:
            continue

        for pattern, field_name, transform in _INLINE_PATTERNS:
            # 이미 값이 있으면 스킵
            if getattr(result, field_name):
                continue

            match = pattern.search(line)
            if match:
                setattr(result, field_name, transform(match.group(1).strip()))


def _extract_multiline_patterns(
    result: ParsedTransferReservation, lines: list[str]
) -> None:
    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        # 매핑된 키인지 확인
        if line not in _MULTILINE_FIELD_MAP:
            continue

        field_name, transform = _MULTILINE_FIELD_MAP[line]

        # 이미 값이 있으면 스킵
        if getattr(result, field_name):
            continue

        # 다음 비어있지 않은 줄에서 값 추출
        value = _get_next_nonempty_line(lines, i + 1)
        if value:
            setattr(result, field_name, transform(value))


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
