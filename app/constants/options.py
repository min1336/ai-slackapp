from __future__ import annotations

from enum import Enum


class IssueType(str, Enum):
    IGNORE_SETTLEMENT = "정산제외"
    CANCEL_CHARGE_FEE = "취소수수료"
    COST_CHANGED = "금액변경"
    INSTEAD_DISPATCH = "대신배차"
    ADD_SETTLEMENT = "정산추가"
    EARLY_RETURN_BEFORE = "조기반납(전)"
    EARLY_RETURN_AFTER = "조기반납(후)"
    ETC = "기타"

    def to_slack_option(self) -> dict:
        return {
            "text": {"type": "plain_text", "text": self.value},
            "value": self.name.lower(),
        }


class SellerChannel(str, Enum):
    CARMORE = "카모아"
    TMAP = "티맵"
    KLOOK = "클룩"
    WEB_TOUR = "웹투어"
    YANOLJA = "야놀자"
    INBOUND = "인바운드"
    TRAVEL_BUCKET = "트레블버킷"
    LUA = "루아"
    BIZ_PLAY = "비즈플레이"
    TRIP_DOT_COM = "트립닷컴"

    def to_slack_option(self) -> dict:
        return {
            "text": {"type": "plain_text", "text": self.value},
            "value": self.name.lower(),
        }


class Description(str, Enum):
    EXCLUDE_UNABLE_DISPATCH = "배차불가로 인한 정산제외 (정산 100% 제외)"
    EXCLUDE_FLIGHT_CANCEL = "결항으로 인한 정산제외 (정산 100% 제외)"
    EXCLUDE_PARTNER = "파트너사 협의 후 정산제외 (정산 100% 제외)"
    CHANGE_USAGE_PERIOD = "실 사용기간 변경으로 정산기준일 변동"
    TRANSFER_UNABLE_DISPATCH = "배차불가로 인한 이관"
    TRANSFER_RESERVATION = "예약변경으로 인한 이관"
    PARTIAL_FLIGHT_CANCEL = "결항으로 인한 부분환불"
    PARTIAL_PARTNER = "파트너사 협의 후 부분환불"
    REFUND_PARTNER_5 = "파트너사 협의 후 5% 공제 후 환불"
    REFUND_PARTNER_10 = "파트너사 협의 후 10% 공제 후 환불"
    REFUND_PARTNER_10_2 = "파트너사 협의 후 10% 공제 후 환불"
    REFUND_PARTNER_20 = "파트너사 협의 후 20% 공제 후 환불"
    REFUND_PARTNER_30 = "파트너사 협의 후 30% 공제 후 환불"
    REFUND_CONDITION_50 = "대여조건 미달로 50% 공제 후 환불"
    REFUND_CONDITION_30 = "대여조건 미달로 30% 공제 후 환불"
    CHANGE_USAGE_PERIOD_2 = "실 사용기간 변경으로 정산기준일 변동"
    MONTHLY_EXTEND = "월렌트 반납일 이후 연장(정산일 변동)"
    EARLY_RETURN = "조기반납으로 인한 정산기준금 변동"
    ADD_MISMATCH = "오매칭으로 인한 정산추가"
    ADD_MISSING = "정산누락으로 추가필요"
    DEDUCT_DUPLICATE = "중복 정산되어 다음정산에서 차감필요"
    REFUND_AFTER_SETTLEMENT = "정산 후 환불 (파트너사 협의 후 다음 정산에서 차감)"
    EXCLUDE_CARD_ERROR = "카드결제전 오류로 확인됐지만 취소로 인한 정산제외"
    NORMAL_NEED_SETTLEMENT = "정상예약건 / 카드결제전에서 확인 가능 (정산필요건)"
    INBOUND_AS_IS = "인바운드 (정산기준금액 그대로 정산 필요)"
    API_ERROR_CANCEL = "api 통신오류 건 수기 취소 (전액환불 구간)"
    MONTHLY_SUB_MANUAL = "월구독 수기결제 진행 된 건 정산 누락 방지 차 기재"

    def to_slack_option(self) -> dict:
        return {
            "text": {"type": "plain_text", "text": self.value},
            "value": self.name.lower(),
        }


ISSUE_TYPE_OPTIONS: list[dict] = [x.to_slack_option() for x in IssueType]
SELLER_CHANNEL_OPTIONS: list[dict] = [x.to_slack_option() for x in SellerChannel]
DESCRIPTION_OPTIONS: list[dict] = [x.to_slack_option() for x in Description]


def find_option_by_text(options: list[dict], text: str) -> dict | None:
    for option in options:
        if option["text"]["text"] == text:
            return option
    return None
