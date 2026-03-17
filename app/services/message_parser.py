from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, field_validator

from app.constants import TransferMessageField
from app.models.cancellation import ReservationData


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


# 예약 메시지 필드 매핑: 한글 키 → (ReservationData 필드명, 변환 함수 or None)
_RESERVATION_FIELD_MAP: dict[str, str] = {
    "예약번호": "booking_key",
    "예약자명": "customer_name",
    "예약자연락처": "phone",
    "업체": "company_name",
    "총 결제금액": "payment_amount",
    "예약기간": "rental_period",
}

_DATE_PATTERN = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})")
_TIME_PATTERN = re.compile(r"(오전|오후)\s*(\d{1,2})시\s*(\d{1,2})분")


def _parse_rental_period(raw: str) -> tuple[datetime | None, datetime | None]:
    """예약기간 문자열에서 시작/종료 datetime을 추출한다."""
    if not raw or "~" not in raw:
        return None, None

    tilde_idx = raw.index("~")
    left = raw[:tilde_idx]
    right = raw[tilde_idx + 1 :]

    # 괄호 안 trailing info (e.g. "(2일 22시간 30분)") 제거: 날짜+시간 파트만 사용
    # 오른쪽 파트에서 두 번째 괄호 이후 제거 (첫 번째는 요일)
    right = re.sub(r"\(\d+일.*?\)", "", right)

    def _parse_part(part: str) -> datetime | None:
        date_m = _DATE_PATTERN.search(part)
        if not date_m:
            return None
        year = int(date_m.group(1))
        month = int(date_m.group(2))
        day = int(date_m.group(3))
        time_m = _TIME_PATTERN.search(part)
        if not time_m:
            return datetime(year, month, day, 0, 0)
        ampm, hour, minute = time_m.group(1), int(time_m.group(2)), int(time_m.group(3))
        if ampm == "오전":
            hour = 0 if hour == 12 else hour
        else:  # 오후
            hour = hour if hour == 12 else hour + 12
        return datetime(year, month, day, hour, minute)

    return _parse_part(left), _parse_part(right)


def parse_reservation_message(text: str) -> ReservationData:
    """예약 채널 메시지에서 예약 정보를 추출한다."""
    result = ReservationData()

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        match = re.match(r"^([가-힣\s]+?)\s*[:：]\s*(.+)$", line)
        if not match:
            continue

        korean_key = match.group(1).strip()
        value = match.group(2).strip()

        field = _RESERVATION_FIELD_MAP.get(korean_key)
        if not field:
            continue

        if field == "booking_key":
            result.booking_key = _strip_value(value)
        elif field == "customer_name":
            result.customer_name = _clean_name(value)
        elif field == "phone":
            result.phone = _strip_value(value)
        elif field == "company_name":
            result.company_name = _strip_value(value)
        elif field == "payment_amount":
            digits = _digits_only(value)
            is_numeric = digits.lstrip("-").isdigit()
            result.payment_amount = int(digits) if is_numeric else None
        elif field == "rental_period":
            start, end = _parse_rental_period(value)
            result.rental_period_start, result.rental_period_end = start, end

    return result


def extract_thread_references(
    messages: Iterable[dict],
) -> tuple[list[tuple[str, str]], int]:
    """메시지에서 (booking_key, thread_ts) 쌍을 추출한다.

    Returns:
        (references, scanned): 추출된 참조 리스트와 스캔한 총 메시지 수.
    """
    refs: list[tuple[str, str]] = []
    scanned = 0
    try:
        for msg in messages:
            scanned += 1
            try:
                text = msg.get("text", "")
                parsed = parse_settlement_message(text)
                booking_key = parsed.booking_key.strip()
                if not booking_key:
                    continue
                message_ts = msg.get("ts", "")
                if not message_ts:
                    continue
                refs.append((booking_key, message_ts))
            except Exception:
                continue
    except Exception:
        pass  # iterator 에러 시 수집된 부분 결과 반환
    return refs, scanned
