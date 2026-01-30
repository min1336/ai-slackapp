from __future__ import annotations

from app.services.message_parser import (
    ParsedSettlement,
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

    def test_카모아_부담비용_라벨도_파싱한다(self):
        text = """이관 전 예약번호
1095976
예약자명
박종선
업체명
(주)특별한렌트카 김포지점
카모아 부담비용
0원
"""

        result = parse_transfer_reservation_message(text)

        assert result.booking_key == "1095976"
        assert result.carmore_cost == "0"
