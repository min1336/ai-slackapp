from __future__ import annotations

from app.services.message_parser import (
    ParsedSettlement,
    _digits_only,
    parse_settlement_message,
    parse_transfer_reservation_message,
)


class TestParseSettlementMessage:
    def test_모든_필드가_있는_메시지를_파싱한다(self):
        text = """
                    예약번호: ABC123
                    업체: 민혁렌트카
                    예약자명: 나민혁
                """

        result = parse_settlement_message(text)

        assert result.booking_key == "ABC123"
        assert result.company_name == "민혁렌트카"
        assert result.customer_name == "나민혁"

    def test_일부_필드만_있는_메시지를_파싱한다(self):
        text = """
                    예약번호: AWS123
                    예약자명: 나민혁
                """

        result = parse_settlement_message(text)

        assert result.booking_key == "AWS123"
        assert result.company_name == ""
        assert result.customer_name == "나민혁"

    def test_빈_텍스트를_파싱하면_빈_객체를_반환한다(self):
        result = parse_settlement_message("")

        assert result.booking_key == ""
        assert result.company_name == ""
        assert result.customer_name == ""

    def test_공백이_포함된_메시지를_파싱한다(self):
        text = """  예약번호:   ABC123
                        업체 :테스트업체
                """

        result = parse_settlement_message(text)

        assert result.booking_key == "ABC123"
        assert result.company_name == "테스트업체"

    def test_알수없는_필드는_무시한다(self):
        text = """
            예약번호: ABC123
            알수없는필드: 무시됨
            예약자명: 나민혁
        """

        result = parse_settlement_message(text)

        assert result.booking_key == "ABC123"
        assert result.customer_name == "나민혁"

    def test_형식에_맞지않는_줄은_무시한다(self):
        text = """
            예약번호: ABC123
            이건 그냥 텍스트
            예약자명: 나민혁
            123: 숫자키
        """

        result = parse_settlement_message(text)

        assert result.booking_key == "ABC123"
        assert result.customer_name == "나민혁"

    def test_예약자명_뒤에_추가정보가_있으면_이름만_추출한다(self):
        text = """
            예약번호: ABC123
            예약자명: 나민혁 (아이폰, 가입일: 2026.1.1(화) 오후 2시 30분)
        """

        result = parse_settlement_message(text)

        assert result.booking_key == "ABC123"
        assert result.customer_name == "나민혁"


class TestParsedSettlementValidator:
    def test_customer_name_괄호_앞_이름만_추출한다(self):
        settlement = ParsedSettlement(customer_name="나민혁 (아이폰)")

        assert settlement.customer_name == "나민혁"

    def test_customer_name_괄호_없으면_그대로_유지한다(self):
        settlement = ParsedSettlement(customer_name="나민혁")

        assert settlement.customer_name == "나민혁"

    def test_customer_name_빈값이면_빈값_유지한다(self):
        settlement = ParsedSettlement(customer_name="")

        assert settlement.customer_name == ""

    def test_customer_name_복잡한_괄호도_처리한다(self):
        settlement = ParsedSettlement(
            customer_name="홍길동 (안드로이드, 가입일: 2025.12.25(목) 오전 10시)"
        )

        assert settlement.customer_name == "홍길동"


class TestParseTransferReservationMessage:
    def test_이관_예약_메시지에서_원하는_필드들을_추출한다(self):
        text = """[카모아 단기 업체이관]  :morecar_callme: 전화예약 이에요!
이관 전 예약번호 : 1095976
예약번호 : 1095983
예약자명 : 박종선 (01037187349)
업체 : (주)특별한렌트카 김포지점

<결제 정보>
원금 : 332,500원
카모아 부담금 : 0원

예약번호
1095976
업체명
*(주)특별한렌트카 김포지점*
예약자명
*박종선*
"""

        result = parse_transfer_reservation_message(text)

        assert result.booking_key == "1095976"
        assert result.customer_name == "박종선"
        assert result.company_name == ""
        assert result.company_sub_name == "(주)특별한렌트카 김포지점"
        assert result.settlement_cost == "332500"
        assert result.carmore_cost == "0"

    def test_음수_금액이_포함된_이관_메시지를_파싱한다(self):
        text = """[카모아 단기 업체이관]
이관 전 예약번호 : 1095976
예약번호 : 1095983
예약자명 : 박종선
업체 : 테스트렌트카

<결제 정보>
원금 : -332,500원
카모아 부담금 : -10,000원
"""

        result = parse_transfer_reservation_message(text)

        assert result.settlement_cost == "-332500"
        assert result.carmore_cost == "-10000"


class TestDigitsOnly:
    def test_음수_금액_문자열에서_부호를_보존한다(self):
        assert _digits_only("-332,500원") == "-332500"

    def test_양수_금액_문자열은_기존처럼_동작한다(self):
        assert _digits_only("332,500원") == "332500"

    def test_빈_문자열은_빈_문자열을_반환한다(self):
        assert _digits_only("") == ""

    def test_숫자만_있으면_그대로_반환한다(self):
        assert _digits_only("50000") == "50000"


# --- 예약 메시지 파서 테스트 ---

from datetime import datetime  # noqa: E402

from app.models.cancellation import ReservationData  # noqa: E402
from app.services.message_parser import (  # noqa: E402
    _parse_rental_period,
    parse_reservation_message,
)

SAMPLE_RESERVATION_MESSAGE = """\
[카모아 예약]
    예약번호 : OR2017576
    예약자명 : 박성구 (안드로이드, 가입일 : 2026.2.4 (수) 오후 3시 47분)
    예약자연락처 : 010-6680-0292
    예약자생년월일 : 만 52세 (730318)
    예약누적횟수 : 1회
    예약기간 : 2026.2.27 (금) 오후 9시 00분 ~ 2026.3.2 (월) 오후 7시 30분 (2일 22시간 30분)
    업체 : 패밀리렌트카 본사 [제주] - 입판가 정산
    차종 : 아반떼 CN7, 연식(2020 ~ 2021), 휘발유
    보험 : 일반자차 26세 이상
<결제정보>
    결제수단 : 네이버페이
    원금 : 190,704원 (대여(자차 포함) : 176,904원, 배달 : 0원)
    할인요금 : 5,000원
    추가자차상품비용: 9,900원 (상품명: TPA 보험)
    총 결제금액 : 185,704원"""


class TestParseReservationMessage:
    def test_전체_필드_파싱(self):
        result = parse_reservation_message(SAMPLE_RESERVATION_MESSAGE)

        assert isinstance(result, ReservationData)
        assert result.booking_key == "OR2017576"
        assert result.customer_name == "박성구"
        assert result.phone == "010-6680-0292"
        assert result.rental_period_start == datetime(2026, 2, 27, 21, 0)
        assert result.rental_period_end == datetime(2026, 3, 2, 19, 30)
        assert result.company_name == "패밀리렌트카 본사 [제주] - 입판가 정산"
        assert result.payment_amount == 185704

    def test_예약자명_괄호_뒤_정보_제거(self):
        text = "예약자명 : 홍길동 (안드로이드, 가입일 : 2026.1.1 (수) 오전 10시)"
        result = parse_reservation_message(text)

        assert result.customer_name == "홍길동"

    def test_결제금액_쉼표_원_제거(self):
        text = "총 결제금액 : 185,704원"
        result = parse_reservation_message(text)

        assert result.payment_amount == 185704

    def test_빈_메시지_기본값_반환(self):
        result = parse_reservation_message("")

        assert result.booking_key == ""
        assert result.customer_name == ""
        assert result.phone == ""
        assert result.rental_period_start is None
        assert result.rental_period_end is None
        assert result.company_name == ""
        assert result.payment_amount is None

    def test_일부_필드만_있는_메시지(self):
        text = "예약번호 : ABC123\n예약자명 : 김철수"
        result = parse_reservation_message(text)

        assert result.booking_key == "ABC123"
        assert result.customer_name == "김철수"
        assert result.phone == ""
        assert result.payment_amount is None

    def test_알수없는_필드는_무시한다(self):
        text = "예약번호 : ABC123\n알수없는필드 : 무시됨\n예약자명 : 김철수"
        result = parse_reservation_message(text)

        assert result.booking_key == "ABC123"
        assert result.customer_name == "김철수"

    def test_fullwidth_콜론도_파싱(self):
        text = "예약번호：OR9999999\n예약자명：이순신"
        result = parse_reservation_message(text)

        assert result.booking_key == "OR9999999"
        assert result.customer_name == "이순신"


class TestParseRentalPeriod:
    def test_표준_형식_파싱(self):
        raw = "2026.2.27 (금) 오후 9시 00분 ~ 2026.3.2 (월) 오후 7시 30분 (2일 22시간 30분)"
        start, end = _parse_rental_period(raw)

        assert start == datetime(2026, 2, 27, 21, 0)
        assert end == datetime(2026, 3, 2, 19, 30)

    def test_오전_시간_파싱(self):
        raw = "2026.2.27 (금) 오전 10시 00분 ~ 2026.3.2 (월) 오전 8시 30분"
        start, end = _parse_rental_period(raw)

        assert start == datetime(2026, 2, 27, 10, 0)
        assert end == datetime(2026, 3, 2, 8, 30)

    def test_오후12시_정오_처리(self):
        raw = "2026.2.27 (금) 오후 12시 00분 ~ 2026.3.2 (월) 오후 1시 00분"
        start, end = _parse_rental_period(raw)

        assert start == datetime(2026, 2, 27, 12, 0)
        assert end == datetime(2026, 3, 2, 13, 0)

    def test_오전12시_자정_처리(self):
        raw = "2026.2.27 (금) 오전 12시 00분 ~ 2026.3.2 (월) 오전 12시 00분"
        start, end = _parse_rental_period(raw)

        assert start == datetime(2026, 2, 27, 0, 0)
        assert end == datetime(2026, 3, 2, 0, 0)

    def test_틸드_없으면_None_반환(self):
        raw = "2026.2.27 (금) 오후 9시 00분"
        start, end = _parse_rental_period(raw)

        assert start is None
        assert end is None

    def test_날짜만_있고_시간_없으면_자정(self):
        raw = "2026.2.27 ~ 2026.3.2"
        start, end = _parse_rental_period(raw)

        assert start == datetime(2026, 2, 27, 0, 0)
        assert end == datetime(2026, 3, 2, 0, 0)

    def test_빈_문자열은_None_반환(self):
        start, end = _parse_rental_period("")

        assert start is None
        assert end is None
