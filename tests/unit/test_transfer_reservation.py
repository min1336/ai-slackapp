"""이관 예약 메시지 파싱 관련 테스트"""

from __future__ import annotations

from app.services.message_parser import (
    ParsedTransferReservation,
    is_transfer_reservation_message,
    parse_transfer_reservation_message,
)


class TestIsTransferReservationMessage:
    """is_transfer_reservation_message() 함수 테스트"""

    def test_이관_예약_메시지_패턴_감지(self):
        text = "이관 전 예약번호 : 1234567"
        assert is_transfer_reservation_message(text) is True

    def test_일반_메시지는_False_반환(self):
        text = "예약번호 : 1234567"
        assert is_transfer_reservation_message(text) is False

    def test_빈_문자열은_False_반환(self):
        assert is_transfer_reservation_message("") is False

    def test_부분_문자열_포함시_True(self):
        text = "안녕하세요, 이관 전 예약번호가 포함된 메시지입니다."
        assert is_transfer_reservation_message(text) is True

    def test_줄바꿈_포함된_메시지에서_감지(self):
        text = """첫번째 줄
이관 전 예약번호
1234567"""
        assert is_transfer_reservation_message(text) is True


class TestParsedTransferReservationValidators:
    """ParsedTransferReservation Pydantic 검증자 테스트"""

    def test_remove_markdown_bold_일반_볼드_제거(self):
        result = ParsedTransferReservation(booking_key="*ABC123*")
        assert result.booking_key == "ABC123"

    def test_remove_markdown_bold_볼드_없으면_그대로(self):
        result = ParsedTransferReservation(booking_key="ABC123")
        assert result.booking_key == "ABC123"

    def test_remove_markdown_bold_여러개_볼드_제거(self):
        result = ParsedTransferReservation(company_sub_name="*테스트* *업체*")
        assert result.company_sub_name == "테스트 업체"

    def test_remove_markdown_bold_공백_트림(self):
        result = ParsedTransferReservation(booking_key="  ABC123  ")
        assert result.booking_key == "ABC123"

    def test_clean_customer_name_괄호_앞_이름만_추출(self):
        result = ParsedTransferReservation(customer_name="홍길동 (010-1234-5678)")
        assert result.customer_name == "홍길동"

    def test_clean_customer_name_괄호_없으면_그대로(self):
        result = ParsedTransferReservation(customer_name="홍길동")
        assert result.customer_name == "홍길동"

    def test_clean_customer_name_빈값이면_빈값_유지(self):
        result = ParsedTransferReservation(customer_name="")
        assert result.customer_name == ""

    def test_clean_customer_name_볼드와_괄호_모두_처리(self):
        result = ParsedTransferReservation(customer_name="*홍길동* (010-1234)")
        assert result.customer_name == "홍길동"

    def test_digits_only_money_콤마_제거(self):
        result = ParsedTransferReservation(settlement_cost="332,500")
        assert result.settlement_cost == "332500"

    def test_digits_only_money_원_단위_제거(self):
        result = ParsedTransferReservation(settlement_cost="332,500원")
        assert result.settlement_cost == "332500"

    def test_digits_only_money_숫자만_있으면_그대로(self):
        result = ParsedTransferReservation(settlement_cost="332500")
        assert result.settlement_cost == "332500"

    def test_digits_only_money_빈값이면_빈값_유지(self):
        result = ParsedTransferReservation(settlement_cost="")
        assert result.settlement_cost == ""

    def test_digits_only_money_0원_처리(self):
        result = ParsedTransferReservation(carmore_cost="0원")
        assert result.carmore_cost == "0"

    def test_digits_only_money_공백_포함_처리(self):
        result = ParsedTransferReservation(settlement_cost=" 100,000 원 ")
        assert result.settlement_cost == "100000"


class TestParseTransferReservationMessageEdgeCases:
    """parse_transfer_reservation_message() 엣지케이스 테스트"""

    def test_인라인_패턴_기본_파싱(self):
        text = "이관 전 예약번호 : 1095976"
        result = parse_transfer_reservation_message(text)
        assert result.booking_key == "1095976"

    def test_인라인_패턴_fullwidth_콜론_지원(self):
        text = "이관 전 예약번호：1095976"
        result = parse_transfer_reservation_message(text)
        assert result.booking_key == "1095976"

    def test_멀티라인_패턴_파싱(self):
        text = """이관 전 예약번호
1095976"""
        result = parse_transfer_reservation_message(text)
        assert result.booking_key == "1095976"

    def test_예약자명_괄호_제거(self):
        text = "예약자명 : 홍길동 (010-1234-5678)"
        result = parse_transfer_reservation_message(text)
        assert result.customer_name == "홍길동"

    def test_업체명_추출(self):
        text = "업체 : 테스트렌터카"
        result = parse_transfer_reservation_message(text)
        assert result.company_sub_name == "테스트렌터카"

    def test_원금_콤마_제거하여_추출(self):
        text = "원금 : 332,500원"
        result = parse_transfer_reservation_message(text)
        assert result.settlement_cost == "332500"

    def test_카모아_부담비용_추출(self):
        text = "카모아 부담비용 : 50,000원"
        result = parse_transfer_reservation_message(text)
        assert result.carmore_cost == "50000"

    def test_카모아_부담금_추출(self):
        text = "카모아 부담금 : 30,000원"
        result = parse_transfer_reservation_message(text)
        assert result.carmore_cost == "30000"

    def test_볼드_마크업_포함_메시지_파싱(self):
        text = "*이관 전 예약번호* : *1095976*"
        result = parse_transfer_reservation_message(text)
        assert result.booking_key == "1095976"

    def test_빈_메시지는_빈_결과_반환(self):
        result = parse_transfer_reservation_message("")
        assert result.booking_key == ""
        assert result.customer_name == ""
        assert result.settlement_cost == ""

    def test_복합_메시지_전체_필드_파싱(self):
        text = """이관 전 예약번호 : 1095976
예약자명 : 홍길동 (010-1234-5678)
업체 : 테스트렌터카
원금 : 332,500원
카모아 부담비용 : 50,000원"""
        result = parse_transfer_reservation_message(text)

        assert result.booking_key == "1095976"
        assert result.customer_name == "홍길동"
        assert result.company_sub_name == "테스트렌터카"
        assert result.settlement_cost == "332500"
        assert result.carmore_cost == "50000"

    def test_인라인과_멀티라인_혼합시_인라인_우선(self):
        """인라인 패턴이 먼저 파싱되므로 멀티라인 값은 무시됨"""
        text = """이관 전 예약번호 : 1111111
이관 전 예약번호
2222222"""
        result = parse_transfer_reservation_message(text)
        assert result.booking_key == "1111111"

    def test_빈줄_포함된_멀티라인_메시지(self):
        text = """이관 전 예약번호

1095976"""
        result = parse_transfer_reservation_message(text)
        assert result.booking_key == "1095976"

    def test_업체명_변형_업체명2_대신배차(self):
        text = """업체명2(대신배차)
특수렌터카"""
        result = parse_transfer_reservation_message(text)
        assert result.company_sub_name == "특수렌터카"

    def test_company_name은_항상_빈값(self):
        """요구사항: company_name은 비워두고 company_sub_name만 채움"""
        text = "업체 : 테스트렌터카"
        result = parse_transfer_reservation_message(text)
        assert result.company_name == ""
        assert result.company_sub_name == "테스트렌터카"

    def test_이관후_예약번호_추출(self):
        """이관 전/후 예약번호가 모두 추출되는지 확인"""
        text = """이관 전 예약번호 : 1010
예약번호 : 2020
예약자명 : 홍길동"""
        result = parse_transfer_reservation_message(text)
        assert result.booking_key == "1010"
        assert result.new_booking_key == "2020"

    def test_이관후_예약번호_없으면_빈값(self):
        text = "이관 전 예약번호 : 1010"
        result = parse_transfer_reservation_message(text)
        assert result.booking_key == "1010"
        assert result.new_booking_key == ""

    def test_실제_이관_메시지_전체_파싱(self):
        """실제 이관 메시지 포맷에서 두 예약번호 모두 추출"""
        text = """[카모아 단기 업체이관]   전화예약 이에요!
                이관 전 예약번호 : 1010
                예약번호 : 2020
                예약자명 : 박종선 (01037187349)
                업체 : (주)특별한렌트카 김포지점
                원금 : 332,500원
                카모아 부담금 : 0원"""
        result = parse_transfer_reservation_message(text)
        assert result.booking_key == "1010"
        assert result.new_booking_key == "2020"
        assert result.customer_name == "박종선"
        assert result.settlement_cost == "332500"
        assert result.carmore_cost == "0"
