"""결항확인서 검증 시스템 — 전체 흐름 모의 테스트.

각 Phase 수정사항이 실제 시나리오에서 올바르게 동작하는지 검증한다.
"""

from __future__ import annotations

from unittest.mock import Mock

from slack_sdk.errors import SlackApiError

from app.models import DriveFile, SurveySubmission
from app.services.cancellation_image_service import CancellationImageService
from app.services.drive_file_collector import DriveFileCollector
from app.services.image_analyzer import ImageAnalyzer
from app.services.pdf_converter import PdfConverter
from app.services.reservation_locator import ReservationLocator
from tests.fakes.fake_drive import FakeDrive
from tests.fakes.fake_gemini import FakeGeminiClient
from tests.fakes.fake_slack import FakeSlackReader, FakeSlackWriter
from tests.fakes.fake_survey import FakeSurveySheet

TARGET_CH = "C-CANCEL"
RESERVATION_CH = "C-RESERVE"

SAMPLE_RESERVATION_MSG = """\
[카모아 예약]
    예약번호 : R12345
    예약자명 : 홍길동
    예약자연락처 : 010-1234-5678
    예약기간 : 2026.3.1 (일) 오후 2시 00분 ~ 2026.3.5 (목) 오후 6시 00분 (4일 4시간)
    업체 : 패밀리렌트카 본사 [제주] - 입판가 정산
<결제정보>
    총 결제금액 : 185,704원"""

ANALYSIS_RESPONSE = {
    "extracted_fields": {
        "고객명": "홍길동",
        "예약번호": "R12345",
        "날짜": "2026-03-02",
        "항공편": "KE123",
        "결항사유": "기상악화",
        "발급기관": "대한항공",
    },
    "summary": "대한항공 KE123편이 2026-03-02 기상악화로 결항.",
    "rejection_reasons": [],
}

# ImageAnalyzer 4MB 필터를 통과할 크기의 JPEG 이미지
_JPEG_IMAGE = b"\xff\xd8\xff\xe0" + b"\x00" * 1000


def _sub(
    sid: str = "JF-999888",
    name: str = "홍길동",
    key: str = "R12345",
    date: str = "2026-03-20 09:55:05",
    phone: str = "010-1234-5678",
) -> SurveySubmission:
    return SurveySubmission(
        submission_id=sid,
        customer_name=name,
        booking_key=key,
        submission_date=date,
        phone=phone,
    )


def _setup_drive(drive: FakeDrive, sub: SurveySubmission) -> None:
    """Drive에 JPEG 이미지 1장 세팅."""
    drive.folders[sub.folder_name] = "folder-1"
    drive.files["folder-1"] = [
        DriveFile(id="f1", name="cancellation.jpg", mime_type="image/jpeg")
    ]
    drive.file_contents["f1"] = _JPEG_IMAGE


class TestPhase1_시트기록_booking_key:
    """Phase 1.1: write_analysis_result/write_verification_result가
    booking_key로 호출되는지 검증."""

    def test_분석결과_시트기록_booking_key_전달(self):
        """submission_id가 아닌 booking_key로 시트에 기록한다."""
        sub = _sub(sid="JF-999888", key="R12345")
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        drive = FakeDrive()
        _setup_drive(drive, sub)

        reader = FakeSlackReader()
        reader.messages_by_text = {(TARGET_CH, "R12345"): "thread-1"}

        gemini = FakeGeminiClient(result=ANALYSIS_RESPONSE)
        analyzer = ImageAnalyzer(gateway=gemini)

        svc = CancellationImageService(
            survey_sheet=survey,
            file_collector=DriveFileCollector(drive, PdfConverter()),
            writer=FakeSlackWriter(),
            reader=reader,
            target_channel=TARGET_CH,
            analyzer=analyzer,
        )
        svc.poll_and_upload()

        # 핵심 검증: booking_key("R12345")로 기록, submission_id("JF-999888") 아님
        assert len(survey.analysis_results) == 1
        recorded_key, _ = survey.analysis_results[0]
        assert recorded_key == "R12345"
        assert recorded_key != "JF-999888"

    def test_교차검증결과_시트기록_booking_key_전달(self):
        """교차검증 결과도 booking_key로 시트에 기록한다."""
        sub = _sub(sid="JF-999888", key="R12345")
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        drive = FakeDrive()
        _setup_drive(drive, sub)

        reader = FakeSlackReader()
        reader.messages_by_text = {(TARGET_CH, "R12345"): "thread-1"}
        reader.parent_messages = {
            (RESERVATION_CH, "res-thread-1"): SAMPLE_RESERVATION_MSG,
        }
        reader.thread_urls = {
            (RESERVATION_CH, "res-thread-1"): "https://slack.com/res",
            (TARGET_CH, "thread-1"): "https://slack.com/cancel",
        }
        reader.channel_messages = {
            RESERVATION_CH: [
                {"text": SAMPLE_RESERVATION_MSG, "ts": "res-thread-1"},
            ],
        }

        gemini = FakeGeminiClient(result=ANALYSIS_RESPONSE)
        analyzer = ImageAnalyzer(gateway=gemini)
        locator = ReservationLocator(reader, [RESERVATION_CH])

        svc = CancellationImageService(
            survey_sheet=survey,
            file_collector=DriveFileCollector(drive, PdfConverter()),
            writer=FakeSlackWriter(),
            reader=reader,
            target_channel=TARGET_CH,
            analyzer=analyzer,
            reservation_locator=locator,
        )
        svc.poll_and_upload()

        # 교차검증 결과도 booking_key로 기록
        assert len(survey.verification_results) == 1
        recorded_key, result = survey.verification_results[0]
        assert recorded_key == "R12345"
        assert result.verdict == "승인"


class TestPhase2_4_부적합사유_에러핸들링:
    """Phase 2.4: 부적합 사유 post_message 실패 시에도 처리 완료."""

    def test_부적합_사유_포스트_실패해도_처리_완료(self):
        sub = _sub()
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        drive = FakeDrive()
        _setup_drive(drive, sub)

        reader = FakeSlackReader()
        reader.messages_by_text = {(TARGET_CH, "R12345"): "thread-1"}

        writer = FakeSlackWriter()
        original_post = writer.post_message

        def _failing_post(**kwargs):
            if "부적합 사유" in kwargs.get("text", ""):
                raise SlackApiError("error", response=Mock())
            return original_post(**kwargs)

        writer.post_message = _failing_post

        invalid_response = {
            "extracted_fields": {},
            "summary": "이미지 흐림",
            "rejection_reasons": ["이미지가 흐려 판독 불가"],
        }
        gemini = FakeGeminiClient(result=invalid_response)
        analyzer = ImageAnalyzer(gateway=gemini)

        svc = CancellationImageService(
            survey_sheet=survey,
            file_collector=DriveFileCollector(drive, PdfConverter()),
            writer=writer,
            reader=reader,
            target_channel=TARGET_CH,
            analyzer=analyzer,
        )
        # 예외 없이 완료되어야 한다
        svc.poll_and_upload()
        assert survey.processed_ids == [sub.submission_id]


class TestPhase2_7_Fake중복체크_3필드:
    """Phase 2.7: FakeSurveySheet가 3필드 중복 체크를 수행하는지 검증."""

    def test_같은_예약번호_고객명_다른_날짜_별도행(self):
        """동일 booking_key+customer_name이지만 submission_date가 다르면 신규 행."""
        sheet = FakeSurveySheet()
        sub1 = _sub(date="2026-03-20 09:00:00")
        sub2 = _sub(date="2026-03-21 10:00:00")  # 같은 고객, 다른 날짜

        assert sheet.write_formatted_row(sub1) is True
        assert sheet.write_formatted_row(sub2) is True  # 별도 행으로 추가
        assert len(sheet.formatted_rows) == 2

    def test_완전히_동일한_3필드_중복(self):
        """3필드 모두 일치하면 중복 처리."""
        sheet = FakeSurveySheet()
        sub1 = _sub()
        sub2 = _sub()  # 동일한 데이터

        assert sheet.write_formatted_row(sub1) is True
        assert sheet.write_formatted_row(sub2) is False
        assert len(sheet.formatted_rows) == 1


class TestPhase2_3_RateLimitFalsePositive:
    """Phase 2.3: 'generate' 등 일반 에러가 rate limit으로 오인되지 않는지 검증."""

    def test_generate_content_에러는_rate_limit_아님(self):
        from app.infrastructure.fallback_gateway import is_rate_limit_error

        # "generate_content failed" — "rate"가 "generate"에 포함되지만 rate limit 아님
        assert is_rate_limit_error(Exception("generate_content failed")) is False

    def test_실제_rate_limit_에러_감지(self):
        from app.infrastructure.fallback_gateway import is_rate_limit_error

        assert is_rate_limit_error(Exception("429 Too Many Requests")) is True
        assert is_rate_limit_error(Exception("rate limit exceeded")) is True
        assert is_rate_limit_error(Exception("rate_limit_error")) is True
        assert is_rate_limit_error(Exception("quota exhausted")) is True


class TestPhase2_2_MimeDetection:
    """Phase 2.2: magic bytes 기반 MIME 타입 감지."""

    def test_jpeg_감지(self):
        from app.infrastructure.mime import detect_mime

        assert detect_mime(b"\xff\xd8\xff\xe0" + b"\x00" * 10) == "image/jpeg"

    def test_png_감지(self):
        from app.infrastructure.mime import detect_mime

        assert detect_mime(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10) == "image/png"

    def test_webp_감지(self):
        from app.infrastructure.mime import detect_mime

        assert detect_mime(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 10) == "image/webp"

    def test_unknown_기본값_png(self):
        from app.infrastructure.mime import detect_mime

        assert detect_mime(b"\x00\x00\x00\x00") == "image/png"


class TestPhase_전체흐름_시뮬레이션:
    """국내 건: 설문 → 이미지 업로드 → AI 분석 → 교차검증 승인 → 양방향 링크."""

    def test_국내_정상흐름_end_to_end(self):
        sub = _sub(sid="JF-999888", key="R12345", phone="010-1234-5678")
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        drive = FakeDrive()
        _setup_drive(drive, sub)

        reader = FakeSlackReader()
        reader.messages_by_text = {(TARGET_CH, "R12345"): "thread-1"}
        reader.parent_messages = {
            (RESERVATION_CH, "res-thread-1"): SAMPLE_RESERVATION_MSG,
        }
        reader.thread_urls = {
            (RESERVATION_CH, "res-thread-1"): "https://slack.com/res",
            (TARGET_CH, "thread-1"): "https://slack.com/cancel",
        }
        reader.channel_messages = {
            RESERVATION_CH: [
                {"text": SAMPLE_RESERVATION_MSG, "ts": "res-thread-1"},
            ],
        }

        writer = FakeSlackWriter()
        gemini = FakeGeminiClient(result=ANALYSIS_RESPONSE)
        analyzer = ImageAnalyzer(gateway=gemini)
        locator = ReservationLocator(reader, [RESERVATION_CH])

        svc = CancellationImageService(
            survey_sheet=survey,
            file_collector=DriveFileCollector(drive, PdfConverter()),
            writer=writer,
            reader=reader,
            target_channel=TARGET_CH,
            analyzer=analyzer,
            reservation_locator=locator,
        )
        svc.poll_and_upload()

        # 1. 처리 완료
        assert survey.processed_ids == ["JF-999888"]

        # 2. 운영현황 행 기록됨
        assert len(survey.formatted_rows) == 1

        # 3. 분석 결과가 booking_key로 기록됨
        assert len(survey.analysis_results) == 1
        key, analysis = survey.analysis_results[0]
        assert key == "R12345"

        # 4. 교차검증 결과가 booking_key로 기록됨
        assert len(survey.verification_results) == 1
        key, verification = survey.verification_results[0]
        assert key == "R12345"
        assert verification.verdict == "승인"

        # 5. Slack에 이미지 업로드 + 분석결과 포스트됨
        assert len(writer.uploaded_files) > 0
        assert len(writer.posted_messages) >= 2  # 분석결과 + permalink(s)

    def test_해외건_분석_스킵_멘션_리액션(self):
        """해외 건은 이미지 업로드 후 멘션+리액션만, AI 분석/교차검증 스킵."""
        sub = _sub(sid="2001", key="OT99999", name="田中太郎")
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        drive = FakeDrive()
        _setup_drive(drive, sub)

        reader = FakeSlackReader()
        reader.messages_by_text = {(TARGET_CH, "OT99999"): "thread-overseas"}

        writer = FakeSlackWriter()
        gemini = FakeGeminiClient(result=ANALYSIS_RESPONSE)
        analyzer = ImageAnalyzer(gateway=gemini)

        svc = CancellationImageService(
            survey_sheet=survey,
            file_collector=DriveFileCollector(drive, PdfConverter()),
            writer=writer,
            reader=reader,
            target_channel=TARGET_CH,
            analyzer=analyzer,
            overseas_prefixes=["OT", "HG", "KL", "IM"],
            overseas_mention="<!subteam^S03KUCG1H53>",
            overseas_reaction="flag-jp",
        )
        svc.poll_and_upload()

        # 분석/교차검증 없음
        assert len(survey.analysis_results) == 0
        assert len(survey.verification_results) == 0

        # 멘션 포스트 있음
        mention_msgs = [
            m for m in writer.posted_messages if "해외 결항 건" in m.get("text", "")
        ]
        assert len(mention_msgs) == 1

        # 리액션 있음
        jp_reactions = [r for r in writer.reactions if r.get("name") == "flag-jp"]
        assert len(jp_reactions) == 1

        # 처리 완료
        assert survey.processed_ids == ["2001"]
