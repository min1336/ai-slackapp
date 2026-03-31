from __future__ import annotations

from app.infrastructure.survey_sheet import _normalize_booking_key
from app.models import SurveySubmission
from tests.fakes.fake_survey import FakeSurveySheet


class TestFakeSurveySheet:
    """FakeSurveySheet이 SurveySheetGateway 프로토콜을 올바르게 구현하는지 검증."""

    def test_초기_상태_빈_리스트(self):
        sheet = FakeSurveySheet()
        assert sheet.formatted_rows == []

    def test_write_formatted_row_기록(self):
        sheet = FakeSurveySheet()
        sub = SurveySubmission(
            submission_id="1001",
            customer_name="홍길동",
            booking_key="R12345",
        )
        sheet.write_formatted_row(sub)

        assert len(sheet.formatted_rows) == 1
        assert sheet.formatted_rows[0].submission_id == "1001"

    def test_여러_행_누적_기록(self):
        sheet = FakeSurveySheet()
        sub1 = SurveySubmission(
            submission_id="1001",
            customer_name="홍길동",
            booking_key="R12345",
        )
        sub2 = SurveySubmission(
            submission_id="1002",
            customer_name="김철수",
            booking_key="R67890",
        )
        sheet.write_formatted_row(sub1)
        sheet.write_formatted_row(sub2)

        assert len(sheet.formatted_rows) == 2
        assert sheet.formatted_rows[1].booking_key == "R67890"


class TestNormalizeBookingKey:
    """사용자 입력의 '예약번호:' 접두사 등을 제거한다."""

    def test_정상_예약번호_변경없음(self):
        assert _normalize_booking_key("HG106844") == "HG106844"

    def test_예약번호_콜론_공백(self):
        assert _normalize_booking_key("예약번호: HG106844") == "HG106844"

    def test_예약번호_콜론_공백없음(self):
        assert _normalize_booking_key("예약번호:HG106844") == "HG106844"

    def test_예약번호_공백_콜론없음(self):
        assert _normalize_booking_key("예약번호 HG106844") == "HG106844"

    def test_예약_번호_띄어쓰기(self):
        assert _normalize_booking_key("예약 번호: HG106844") == "HG106844"

    def test_빈문자열(self):
        assert _normalize_booking_key("") == ""

    def test_일반_예약번호_IN(self):
        assert _normalize_booking_key("IN2003129") == "IN2003129"

    def test_일반_예약번호_RB(self):
        assert _normalize_booking_key("RB2001216") == "RB2001216"

    def test_숫자만(self):
        assert _normalize_booking_key("1114373") == "1114373"

    def test_해시_접두사(self):
        assert _normalize_booking_key("#HG106844") == "HG106844"

    def test_공백_포함_예약번호(self):
        assert _normalize_booking_key("HG 106844") == "HG106844"

    def test_대시_포함(self):
        assert _normalize_booking_key("HG-106844") == "HG106844"

    def test_한글만_입력_폴백(self):
        assert _normalize_booking_key("홍길동") == "홍길동"
