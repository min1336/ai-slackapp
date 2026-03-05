from __future__ import annotations

from app.models import SurveySubmission
from tests.fakes.fake_survey import FakeSurveySheet


class TestFakeSurveySheet:
    """FakeSurveySheet이 SurveySheetGateway 프로토콜을 올바르게 구현하는지 검증."""

    def test_빈_시트_빈_리스트_반환(self):
        sheet = FakeSurveySheet()
        assert sheet.get_all_submissions() == []

    def test_submissions_반환(self):
        submissions = [
            SurveySubmission(
                submission_id="1001",
                customer_name="홍길동",
                booking_key="R12345",
            ),
            SurveySubmission(
                submission_id="1002",
                customer_name="김철수",
                booking_key="R67890",
            ),
        ]
        sheet = FakeSurveySheet(submissions)
        result = sheet.get_all_submissions()

        assert len(result) == 2
        assert result[0].submission_id == "1001"
        assert result[1].booking_key == "R67890"

    def test_반환값은_원본의_복사본(self):
        submissions = [
            SurveySubmission(
                submission_id="1001",
                customer_name="홍길동",
                booking_key="R12345",
            ),
        ]
        sheet = FakeSurveySheet(submissions)
        result = sheet.get_all_submissions()
        result.clear()

        assert len(sheet.get_all_submissions()) == 1


class TestSurveySubmissionModel:
    def test_folder_name_프로퍼티(self):
        sub = SurveySubmission(
            submission_id="1",
            customer_name="홍길동",
            booking_key="R12345",
        )
        assert sub.folder_name == "홍길동_R12345"
