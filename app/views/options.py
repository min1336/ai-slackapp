from __future__ import annotations

# 이슈사항 옵션
ISSUE_TYPE_OPTIONS = [
    {"text": {"type": "plain_text", "text": "정산제외"}, "value": "ignore_settlement"},
    {"text": {"type": "plain_text", "text": "취소수수료"}, "value": "cancel_charge_fee"},
    {"text": {"type": "plain_text", "text": "금액변경"}, "value": "cost_changed"},
    {"text": {"type": "plain_text", "text": "대신배차"}, "value": "instead_dispatch"},
    {"text": {"type": "plain_text", "text": "정산추가"}, "value": "add_settlement"},
    {"text": {"type": "plain_text", "text": "조기반납(전)"}, "value": "early_return_before"},
    {"text": {"type": "plain_text", "text": "조기반납(후)"}, "value": "early_return_after"},
    {"text": {"type": "plain_text", "text": "기타"}, "value": "etc"},
]

# 판매채널 옵션
SELLER_CHANNEL_OPTIONS = [
    {"text": {"type": "plain_text", "text": "카모아"}, "value": "carmore"},
    {"text": {"type": "plain_text", "text": "티맵"}, "value": "tmap"},
    {"text": {"type": "plain_text", "text": "클룩"}, "value": "klook"},
    {"text": {"type": "plain_text", "text": "웹투어"}, "value": "web_tour"},
    {"text": {"type": "plain_text", "text": "야놀자"}, "value": "yanolja"},
    {"text": {"type": "plain_text", "text": "인바운드"}, "value": "inbound"},
    {"text": {"type": "plain_text", "text": "트레블버킷"}, "value": "travel_bucket"},
    {"text": {"type": "plain_text", "text": "루아"}, "value": "lua"},
    {"text": {"type": "plain_text", "text": "비즈플레이"}, "value": "biz_play"},
    {"text": {"type": "plain_text", "text": "트립닷컴"}, "value": "trip_dot_com"},
]

# 내용 옵션
DESCRIPTION_OPTIONS = [
    {"text": {"type": "plain_text", "text": "배차불가로 인한 정산제외 (정산 100% 제외)"}, "value": "exclude_unable_dispatch"},
    {"text": {"type": "plain_text", "text": "결항으로 인한 정산제외 (정산 100% 제외)"}, "value": "exclude_flight_cancel"},
    {"text": {"type": "plain_text", "text": "파트너사 협의 후 정산제외 (정산 100% 제외)"}, "value": "exclude_partner"},
    {"text": {"type": "plain_text", "text": "실 사용기간 변경으로 정산기준일 변동"}, "value": "change_usage_period"},
    {"text": {"type": "plain_text", "text": "배차불가로 인한 이관"}, "value": "transfer_unable_dispatch"},
    {"text": {"type": "plain_text", "text": "예약변경으로 인한 이관"}, "value": "transfer_reservation"},
    {"text": {"type": "plain_text", "text": "결항으로 인한 부분환불"}, "value": "partial_flight_cancel"},
    {"text": {"type": "plain_text", "text": "파트너사 협의 후 부분환불"}, "value": "partial_partner"},
    {"text": {"type": "plain_text", "text": "파트너사 협의 후 5% 공제 후 환불"}, "value": "refund_partner_5"},
    {"text": {"type": "plain_text", "text": "파트너사 협의 후 10% 공제 후 환불"}, "value": "refund_partner_10"},
    {"text": {"type": "plain_text", "text": "파트너사 협의 후 10% 공제 후 환불"}, "value": "refund_partner_10_2"},
    {"text": {"type": "plain_text", "text": "파트너사 협의 후 20% 공제 후 환불"}, "value": "refund_partner_20"},
    {"text": {"type": "plain_text", "text": "파트너사 협의 후 30% 공제 후 환불"}, "value": "refund_partner_30"},
    {"text": {"type": "plain_text", "text": "대여조건 미달로 50% 공제 후 환불"}, "value": "refund_condition_50"},
    {"text": {"type": "plain_text", "text": "대여조건 미달로 30% 공제 후 환불"}, "value": "refund_condition_30"},
    {"text": {"type": "plain_text", "text": "실 사용기간 변경으로 정산기준일 변동"}, "value": "change_usage_period_2"},
    {"text": {"type": "plain_text", "text": "월렌트 반납일 이후 연장(정산일 변동)"}, "value": "monthly_extend"},
    {"text": {"type": "plain_text", "text": "조기반납으로 인한 정산기준금 변동"}, "value": "early_return"},
    {"text": {"type": "plain_text", "text": "오매칭으로 인한 정산추가"}, "value": "add_mismatch"},
    {"text": {"type": "plain_text", "text": "정산누락으로 추가필요"}, "value": "add_missing"},
    {"text": {"type": "plain_text", "text": "중복 정산되어 다음정산에서 차감필요"}, "value": "deduct_duplicate"},
    {"text": {"type": "plain_text", "text": "정산 후 환불 (파트너사 협의 후 다음 정산에서 차감)"}, "value": "refund_after_settlement"},
    {"text": {"type": "plain_text", "text": "카드결제전 오류로 확인됐지만 취소로 인한 정산제외"}, "value": "exclude_card_error"},
    {"text": {"type": "plain_text", "text": "정상예약건 / 카드결제전에서 확인 가능 (정산필요건)"}, "value": "normal_need_settlement"},
    {"text": {"type": "plain_text", "text": "인바운드 (정산기준금액 그대로 정산 필요)"}, "value": "inbound_as_is"},
    {"text": {"type": "plain_text", "text": "api 통신오류 건 수기 취소 (전액환불 구간)"}, "value": "api_error_cancel"},
    {"text": {"type": "plain_text", "text": "월구독 수기결제 진행 된 건 정산 누락 방지 차 기재"}, "value": "monthly_sub_manual"},
]


def find_option_by_text(options: list[dict], text: str) -> dict | None:
    """text로 옵션을 찾아 반환"""
    for option in options:
        if option["text"]["text"] == text:
            return option
    return None
