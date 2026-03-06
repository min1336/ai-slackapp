from __future__ import annotations

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


class TestSurveySubmissionModel:
    def test_folder_name_프로퍼티(self):
        sub = SurveySubmission(
            submission_id="1",
            customer_name="홍길동",
            booking_key="R12345",
        )
        assert sub.folder_name == "홍길동_R12345"
