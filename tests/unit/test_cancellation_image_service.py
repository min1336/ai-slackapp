from __future__ import annotations

import types

import pymupdf

from app.models import DriveFile, SurveySubmission
from app.services.cancellation_image_service import CancellationImageService
from app.services.cross_verifier import CrossVerifier
from app.services.drive_file_collector import DriveFileCollector
from app.services.image_analyzer import ImageAnalyzer
from app.services.pdf_converter import PdfConverter
from app.services.reservation_locator import ReservationLocator
from app.services.thread_reference_store import ThreadReferenceStore
from tests.fakes.fake_database import FakeDatabase
from tests.fakes.fake_gemini import FakeGeminiClient
from tests.fakes.fake_slack import FakeSlackReader, FakeSlackWriter
from tests.fakes.fake_survey import FakeSurveySheet

TARGET_CH = "C-CANCEL"
RESERVATION_CH = "C-RESERVE"

# 교차검증 "승인" 유도 — 날짜가 렌트기간 내, 모든 필드 일치
_APPROVE_RESPONSE = {
    "document_type": "항공사 운항정보확인서",
    "extracted_fields": {
        "고객명": "홍길동",
        "예약번호": "R12345",
        "날짜": "2026-02-28",
        "항공편": "KE123",
        "결항사유": "기상악화",
        "발급기관": "대한항공",
    },
    "summary": "대한항공 KE123편이 2026-02-28 기상악화로 결항.",
    "rejection_reasons": [],
}

# 교차검증 "반려" 유도 — 날짜가 렌트기간 밖
_REJECT_RESPONSE = {
    "document_type": "항공사 운항정보확인서",
    "extracted_fields": {
        "고객명": "홍길동",
        "예약번호": "R12345",
        "날짜": "2025-12-13",
        "항공편": "KE123",
        "결항사유": "기상악화",
        "발급기관": "대한항공",
    },
    "summary": "대한항공 KE123편이 2025-12-13 기상악화로 결항.",
    "rejection_reasons": [],
}

# 이미지 부적합 — rejection_reasons 포함
_INVALID_IMAGE_RESPONSE = {
    "document_type": "기타",
    "extracted_fields": {},
    "summary": "이미지가 흐려 내용 확인 불가",
    "rejection_reasons": ["이미지가 흐리거나 텍스트를 읽을 수 없음"],
}

SAMPLE_RESERVATION_MSG = """\
[카모아 예약]
    예약번호 : R12345
    예약자명 : 홍길동
    예약자연락처 : 010-1234-5678
    예약기간 : 2026.2.27 (금) 오후 9시 00분 ~ 2026.3.2 (월) 오후 7시 30분 (2일 22시간 30분)
    업체 : 패밀리렌트카 본사 [제주] - 입판가 정산
<결제정보>
    총 결제금액 : 185,704원"""


class FakeDrive:
    """DriveImageGateway Protocol 호환 Fake."""

    def __init__(self):
        self.folders: dict[str, str] = {}  # folder_name → folder_id
        self.files: dict[str, list[DriveFile]] = {}  # folder_id → files
        self.file_contents: dict[str, bytes] = {}  # file_id → bytes

    def find_folder(self, folder_name: str) -> str | None:
        return self.folders.get(folder_name)

    def list_image_files(self, folder_id: str) -> list[DriveFile]:
        return self.files.get(folder_id, [])

    def download_file(self, file_id: str) -> bytes:
        return self.file_contents[file_id]


def _submission(
    sid: str = "1001",
    name: str = "홍길동",
    key: str = "R12345",
    **kwargs,
) -> SurveySubmission:
    return SurveySubmission(
        submission_id=sid,
        customer_name=name,
        booking_key=key,
        **kwargs,
    )


def _make_service(
    *,
    survey: FakeSurveySheet | None = None,
    drive: FakeDrive | None = None,
    writer: FakeSlackWriter | None = None,
    reader: FakeSlackReader | None = None,
    file_collector: DriveFileCollector | None = None,
    analyzer: ImageAnalyzer | None = None,
    cross_verifier: CrossVerifier | None = None,
    reservation_locator: ReservationLocator | None = None,
    reservation_channels: list[str] | None = None,
    thread_ref_store: ThreadReferenceStore | None = None,
) -> CancellationImageService:
    _reader = reader or FakeSlackReader()
    _drive = drive or FakeDrive()
    _locator = reservation_locator
    if _locator is None and reservation_channels is not None:
        _locator = ReservationLocator(_reader, reservation_channels, thread_ref_store)
    return CancellationImageService(
        survey_sheet=survey or FakeSurveySheet(),
        file_collector=file_collector or DriveFileCollector(_drive, PdfConverter()),
        writer=writer or FakeSlackWriter(),
        reader=_reader,
        target_channel=TARGET_CH,
        analyzer=analyzer,
        cross_verifier=cross_verifier,
        reservation_locator=_locator,
    )


class TestPollAndUpload:
    def test_미처리_건_처리_후_마킹(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        drive = FakeDrive()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="img.jpg", mime_type="image/jpeg")
        ]
        drive.file_contents["f1"] = b"\xff\xd8"

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 1
        assert survey.processed_ids == ["1001"]
        assert len(survey.formatted_rows) == 1

    def test_빈_submissions이면_아무것도_안함(self):
        survey = FakeSurveySheet()
        writer = FakeSlackWriter()

        svc = _make_service(survey=survey, writer=writer)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 0
        assert len(survey.processed_ids) == 0

    def test_스레드_없으면_마킹_안함(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]
        # reader에 스레드 없음

        svc = _make_service(survey=survey)
        svc.poll_and_upload()

        assert len(survey.processed_ids) == 0
        assert len(survey.formatted_rows) == 0

    def test_Drive_폴더_없으면_마킹_안함(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        drive = FakeDrive()  # 폴더 없음

        svc = _make_service(survey=survey, drive=drive, reader=reader)
        svc.poll_and_upload()

        assert len(survey.processed_ids) == 0

    def test_Drive_파일_없으면_마킹_안함(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        drive = FakeDrive()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = []  # 파일 없음

        svc = _make_service(survey=survey, drive=drive, reader=reader)
        svc.poll_and_upload()

        assert len(survey.processed_ids) == 0


class TestProcessSubmission:
    def test_모든_다운로드_실패_시_마킹_안함(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDrive()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="bad.jpg", mime_type="image/jpeg"),
        ]
        # f1 content 없음 → KeyError on download

        svc = _make_service(survey=survey, drive=drive, reader=reader)
        svc.poll_and_upload()

        assert len(survey.processed_ids) == 0

    def test_여러_파일_모두_업로드(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        drive = FakeDrive()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="a.jpg", mime_type="image/jpeg"),
            DriveFile(id="f2", name="b.png", mime_type="image/png"),
        ]
        drive.file_contents["f1"] = b"\xff\xd8"
        drive.file_contents["f2"] = b"\x89PNG"

        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 2

    def test_다운로드_실패해도_나머지_계속(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        drive = FakeDrive()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="bad.jpg", mime_type="image/jpeg"),
            DriveFile(id="f2", name="ok.jpg", mime_type="image/jpeg"),
        ]
        # f1은 contents 없음 → KeyError
        drive.file_contents["f2"] = b"\xff\xd8"

        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 1
        assert writer.uploaded_files[0]["filename"] == "ok.jpg"


class TestPdfConversion:
    def _make_pdf_bytes(self, pages: int = 1) -> bytes:
        doc = pymupdf.open()
        for _ in range(pages):
            doc.new_page(width=100, height=100)
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    def test_pdf_파일_이미지로_변환_업로드(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]
        pdf_bytes = self._make_pdf_bytes()

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        drive = FakeDrive()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="cert.pdf", mime_type="application/pdf")
        ]
        drive.file_contents["f1"] = pdf_bytes

        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 1
        assert writer.uploaded_files[0]["filename"] == "cert.png"
        assert writer.uploaded_files[0]["content"][:4] == b"\x89PNG"

    def test_다페이지_pdf_모든_페이지_업로드(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]
        pdf_bytes = self._make_pdf_bytes(pages=3)

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        drive = FakeDrive()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="multi.pdf", mime_type="application/pdf")
        ]
        drive.file_contents["f1"] = pdf_bytes

        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 3
        filenames = [f["filename"] for f in writer.uploaded_files]
        assert filenames == ["multi_p1.png", "multi_p2.png", "multi_p3.png"]

    def test_pdf_업로드_시_리액션_추가(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]
        pdf_bytes = self._make_pdf_bytes()

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        drive = FakeDrive()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="cert.pdf", mime_type="application/pdf")
        ]
        drive.file_contents["f1"] = pdf_bytes

        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.reactions) == 1
        assert writer.reactions[0]["name"] == "pdf"

    def test_이미지만_있으면_pdf_리액션_없음(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        drive = FakeDrive()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="photo.jpg", mime_type="image/jpeg")
        ]
        drive.file_contents["f1"] = b"\xff\xd8"

        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.reactions) == 0

    def test_pdf_변환_실패_시_다음_파일_계속(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        drive = FakeDrive()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="broken.pdf", mime_type="application/pdf"),
            DriveFile(id="f2", name="ok.jpg", mime_type="image/jpeg"),
        ]
        drive.file_contents["f1"] = b"not-a-real-pdf"
        drive.file_contents["f2"] = b"\xff\xd8"

        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 1
        assert writer.uploaded_files[0]["filename"] == "ok.jpg"


class TestFormattedSheet:
    def test_성공_시_포맷_시트에_행_추가(self):
        sub = _submission(
            submission_date="2026-03-05",
            company_name="고양이렌트카",
            phone="111-1111-1111",
        )
        survey = FakeSurveySheet()
        survey.submissions = [sub]

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDrive()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="img.jpg", mime_type="image/jpeg")
        ]
        drive.file_contents["f1"] = b"\xff\xd8"

        svc = _make_service(survey=survey, drive=drive, reader=reader)
        svc.poll_and_upload()

        assert len(survey.formatted_rows) == 1
        row = survey.formatted_rows[0]
        assert row.submission_date == "2026-03-05"
        assert row.customer_name == "홍길동"
        assert row.booking_key == "R12345"
        assert row.company_name == "고양이렌트카"

    def test_실패_시_포맷_시트에_기록_안함(self):
        sub = _submission()
        survey = FakeSurveySheet()
        survey.submissions = [sub]
        # reader에 스레드 없음 → 실패

        svc = _make_service(survey=survey)
        svc.poll_and_upload()

        assert len(survey.formatted_rows) == 0


class TestAnalysisIntegration:
    def _setup(self, gemini_result=None):
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient(result=gemini_result)
        analyzer = ImageAnalyzer(gemini)

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        svc = _make_service(
            survey=survey, drive=drive, writer=writer, reader=reader, analyzer=analyzer
        )
        return svc, writer, survey, gemini

    def test_analysis_posts_summary(self):
        svc, writer, survey, gemini = self._setup()
        svc.poll_and_upload()

        assert len(writer.posted_messages) >= 1
        assert len(survey.analysis_results) == 1

    def test_analysis_failure_still_uploads(self):
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient(result=RuntimeError("API down"))
        analyzer = ImageAnalyzer(gemini)

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        svc = _make_service(
            survey=survey, drive=drive, writer=writer, reader=reader, analyzer=analyzer
        )
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 1
        assert sub.submission_id in survey.processed_ids

    def test_no_analyzer_skips_analysis(self):
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 1
        analysis_emojis = [
            r
            for r in writer.reactions
            if r["name"] in ("white_check_mark", "x", "warning")
        ]
        assert len(analysis_emojis) == 0


class TestCrossVerification:
    """교차검증 통합 테스트: 분석 → 예약검색 → 교차비교 → 댓글 전체 체인."""

    def _setup_full_chain(
        self, *, gemini_result=None, reservation_msg=SAMPLE_RESERVATION_MSG
    ):
        """분석 + 교차검증 전체 체인 세팅 헬퍼."""
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient(result=gemini_result)
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini)

        sub = _submission()
        survey.submissions = [sub]

        # 결항 채널 스레드 세팅
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        # 예약 채널 세팅
        reader.messages_by_text[(RESERVATION_CH, sub.booking_key)] = "reserve-thread-1"
        reader.parent_messages[(RESERVATION_CH, "reserve-thread-1")] = reservation_msg

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH],
        )
        return svc, writer, survey, gemini

    def test_분석후_교차검증_실행(self):
        """분석 완료 후 예약 메시지를 찾아 교차검증하고, 검증 결과를 스레드에 포스트한다."""
        svc, writer, survey, _ = self._setup_full_chain()
        svc.poll_and_upload()

        # 분석 결과 댓글 (기존) + 교차검증 결과 댓글 = 최소 2개
        assert len(writer.posted_messages) >= 2
        # 교차검증 결과가 시트에 기록됨
        assert len(survey.verification_results) == 1

    def test_교차검증_verdict_포함_댓글(self):
        """교차검증 결과 댓글에 verdict 관련 텍스트가 포함된다."""
        svc, writer, survey, _ = self._setup_full_chain()
        svc.poll_and_upload()

        # 마지막 posted_message가 교차검증 결과
        verification_msg = writer.posted_messages[-1]
        assert verification_msg["thread_ts"] == "cancel-thread-1"
        assert verification_msg["blocks"] is not None

    def test_예약_스레드_없으면_보류_포스트(self):
        """예약 채널에서 스레드를 못 찾으면 verdict='보류'로 포스트한다."""
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient()
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini)

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"
        # 예약 채널에는 아무것도 세팅하지 않음 → 검색 실패

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH],
        )
        svc.poll_and_upload()

        # 보류 결과가 기록됨
        assert len(survey.verification_results) == 1
        assert survey.verification_results[0][1].verdict == "보류"

    def test_교차검증_실패해도_분석결과_유지(self):
        """교차검증 중 예외가 발생해도 이미지 업로드 + 분석 결과는 유지된다."""
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient()
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini)

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH],
        )

        # _cross_verify_and_report가 예외를 던지도록 조작
        def _boom(self_inner, *a, **kw):
            raise RuntimeError("cross verify exploded")

        svc._cross_verify_and_report = types.MethodType(_boom, svc)

        svc.poll_and_upload()

        # 이미지 업로드는 성공
        assert len(writer.uploaded_files) == 1
        # 분석 결과도 기록됨
        assert len(survey.analysis_results) == 1
        # submission은 처리 완료 마킹됨
        assert sub.submission_id in survey.processed_ids

    def test_cross_verifier_없으면_교차검증_스킵(self):
        """cross_verifier=None이면 분석만 하고 교차검증은 실행하지 않는다."""
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient()
        analyzer = ImageAnalyzer(gemini)

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        # cross_verifier=None → 교차검증 스킵
        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=None,
        )
        svc.poll_and_upload()

        # 분석 결과만 포스트 (교차검증 댓글 없음)
        assert len(writer.posted_messages) == 1
        assert len(survey.verification_results) == 0

    def test_여러_예약채널_순회_첫번째_발견시_사용(self):
        """reservation_channels를 순회하다 첫 번째 매칭 채널에서 예약 데이터를 가져온다."""
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient()
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini)

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        # 첫 번째 채널에는 없고, 두 번째 채널에 있음
        second_ch = "C-RESERVE-2"
        reader.messages_by_text[(second_ch, sub.booking_key)] = "reserve-thread-2"
        reader.parent_messages[(second_ch, "reserve-thread-2")] = SAMPLE_RESERVATION_MSG

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH, second_ch],
        )
        svc.poll_and_upload()

        # 두 번째 채널에서 찾았으므로 교차검증 결과 존재
        assert len(survey.verification_results) == 1


class TestImageValidation:
    """이미지 유효성 검증 및 X 리액션 테스트."""

    def _setup_with_response(self, gemini_response, *, with_cross_verifier=False):
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient(result=gemini_response)
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini) if with_cross_verifier else None

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        if with_cross_verifier:
            reader.messages_by_text[(RESERVATION_CH, sub.booking_key)] = (
                "reserve-thread-1"
            )
            reader.parent_messages[(RESERVATION_CH, "reserve-thread-1")] = (
                SAMPLE_RESERVATION_MSG
            )

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH] if with_cross_verifier else None,
        )
        return svc, writer, survey

    def test_이미지_부적합_사유댓글(self):
        svc, writer, _ = self._setup_with_response(_INVALID_IMAGE_RESPONSE)
        svc.poll_and_upload()

        rejection_msgs = [
            m for m in writer.posted_messages if "부적합 사유" in m["text"]
        ]
        assert len(rejection_msgs) == 1
        assert "텍스트를 읽을 수 없음" in rejection_msgs[0]["text"]

    def test_이미지_부적합_교차검증_스킵(self):
        svc, writer, survey = self._setup_with_response(
            _INVALID_IMAGE_RESPONSE, with_cross_verifier=True
        )
        svc.poll_and_upload()

        assert len(survey.verification_results) == 0
        assert len(survey.analysis_results) == 0


class TestCrossVerificationReactions:
    """교차검증 verdict별 후속 처리(X 리액션, 양방향 링크) 테스트."""

    def _setup_with_verdict(self, gemini_response, *, with_links=False):
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient(result=gemini_response)
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini)

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        reader.channel_messages[RESERVATION_CH] = [
            {"text": SAMPLE_RESERVATION_MSG, "ts": "reserve-thread-1"},
        ]
        reader.parent_messages[(RESERVATION_CH, "reserve-thread-1")] = (
            SAMPLE_RESERVATION_MSG
        )

        if with_links:
            reader.thread_urls[(RESERVATION_CH, "reserve-thread-1")] = (
                "https://slack.com/reserve-link"
            )
            reader.thread_urls[(TARGET_CH, "cancel-thread-1")] = (
                "https://slack.com/cancel-link"
            )

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH],
        )
        return svc, writer, survey

    def test_교차검증_반려_링크없음(self):
        svc, writer, _ = self._setup_with_verdict(_REJECT_RESPONSE, with_links=True)
        svc.poll_and_upload()

        link_msgs = [m for m in writer.posted_messages if "slack.com" in m["text"]]
        assert len(link_msgs) == 0

    def test_교차검증_승인_양방향링크(self):
        svc, writer, _ = self._setup_with_verdict(_APPROVE_RESPONSE, with_links=True)
        svc.poll_and_upload()

        x_reactions = [r for r in writer.reactions if r["name"] == "x"]
        assert len(x_reactions) == 0
        link_msgs = [m for m in writer.posted_messages if "slack.com" in m["text"]]
        assert len(link_msgs) == 2
        # 취소 스레드에 예약 링크
        cancel_thread_links = [m for m in link_msgs if m["channel"] == TARGET_CH]
        assert len(cancel_thread_links) == 1
        assert "reserve-link" in cancel_thread_links[0]["text"]
        # 예약 스레드에 취소 링크
        reserve_thread_links = [m for m in link_msgs if m["channel"] == RESERVATION_CH]
        assert len(reserve_thread_links) == 1
        assert "cancel-link" in reserve_thread_links[0]["text"]

    def test_교차검증_보류_X없음_링크없음(self):
        """예약 스레드를 못 찾으면 보류 — X 리액션 없고 링크도 없다."""
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient(result=_APPROVE_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini)

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"
        # 예약 채널에 아무것도 없음

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH],
        )
        svc.poll_and_upload()

        x_reactions = [r for r in writer.reactions if r["name"] == "x"]
        assert len(x_reactions) == 0
        link_msgs = [m for m in writer.posted_messages if "slack.com" in m["text"]]
        assert len(link_msgs) == 0


# 문서 간 날짜 불일치 — rejection_reasons 포함
_DATE_INCONSISTENCY_RESPONSE = {
    "document_type": "항공사 운항정보확인서",
    "extracted_fields": {
        "고객명": "홍길동",
        "항공편": "OZ8197",
        "날짜": "2018-03-26",
        "결항사유": "기상악화",
        "발급기관": "아시아나항공",
    },
    "summary": "아시아나 OZ8197편 결항 확인서",
    "rejection_reasons": [
        "제출된 두 문서(공식 확인서 및 카카오톡 알림톡)에서 동일 항공편(OZ8197)의 "
        "결항 날짜가 각각 2018년 3월 26일과 2018년 3월 18일로 상이하여 "
        "핵심 정보인 날짜의 일관성이 부족합니다."
    ],
}

# 문서 간 편명 불일치 — rejection_reasons 포함
_FLIGHT_INCONSISTENCY_RESPONSE = {
    "document_type": "항공사 운항정보확인서",
    "extracted_fields": {
        "고객명": "홍길동",
        "항공편": "KE123",
        "날짜": "2026-02-28",
        "결항사유": "기상악화",
        "발급기관": "대한항공",
    },
    "summary": "대한항공 결항 확인서",
    "rejection_reasons": [
        "문서 1의 항공편(KE123)과 문서 2의 항공편(OZ456)이 상이합니다."
    ],
}


class TestDocumentConsistencyIntegration:
    """여러 문서 간 정보 불일치 시 전체 흐름 테스트."""

    def _setup_with_response(self, gemini_response, *, with_cross_verifier=False):
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient(result=gemini_response)
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini) if with_cross_verifier else None

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="confirm.png", mime_type="image/png"),
            DriveFile(id="f2", name="kakao.png", mime_type="image/png"),
        ]
        drive.file_contents["f1"] = b"fake-confirm-img"
        drive.file_contents["f2"] = b"fake-kakao-img"

        if with_cross_verifier:
            reader.messages_by_text[(RESERVATION_CH, sub.booking_key)] = (
                "reserve-thread-1"
            )
            reader.parent_messages[(RESERVATION_CH, "reserve-thread-1")] = (
                SAMPLE_RESERVATION_MSG
            )

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH] if with_cross_verifier else None,
        )
        return svc, writer, survey

    def test_날짜_불일치_사유댓글(self):
        """문서 간 날짜 불일치 시 부적합 사유 댓글."""
        svc, writer, _ = self._setup_with_response(_DATE_INCONSISTENCY_RESPONSE)
        svc.poll_and_upload()

        rejection_msgs = [
            m for m in writer.posted_messages if "부적합 사유" in m["text"]
        ]
        assert len(rejection_msgs) == 1
        assert "날짜" in rejection_msgs[0]["text"]
        assert "상이" in rejection_msgs[0]["text"]

    def test_날짜_불일치_교차검증_스킵(self):
        """문서 간 날짜 불일치 시 교차검증이 실행되지 않아야 한다."""
        svc, writer, survey = self._setup_with_response(
            _DATE_INCONSISTENCY_RESPONSE, with_cross_verifier=True
        )
        svc.poll_and_upload()

        assert len(survey.verification_results) == 0
        assert len(survey.analysis_results) == 0

    def test_편명_불일치_교차검증_스킵(self):
        """문서 간 편명 불일치 시 교차검증 스킵."""
        svc, writer, survey = self._setup_with_response(
            _FLIGHT_INCONSISTENCY_RESPONSE, with_cross_verifier=True
        )
        svc.poll_and_upload()

        assert len(survey.verification_results) == 0

    def test_날짜_불일치에도_이미지_업로드_유지(self):
        """문서 부적합이어도 이미지 업로드 자체는 완료되어야 한다."""
        svc, writer, survey = self._setup_with_response(_DATE_INCONSISTENCY_RESPONSE)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 2
        assert survey.processed_ids == ["1001"]


class TestPhoneFallback:
    """전화번호 fallback 검색 테스트."""

    def test_예약번호실패_전화번호로_검색_성공(self):
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient(result=_APPROVE_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini)

        sub = _submission(phone="010-1234-5678")
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        # 예약번호로는 못 찾고, 전화번호로 찾음
        reader.channel_messages[RESERVATION_CH] = [
            {"text": SAMPLE_RESERVATION_MSG, "ts": "reserve-thread-1"},
        ]
        reader.parent_messages[(RESERVATION_CH, "reserve-thread-1")] = (
            SAMPLE_RESERVATION_MSG
        )

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH],
        )
        svc.poll_and_upload()

        assert len(survey.verification_results) == 1
        assert survey.verification_results[0][1].verdict == "승인"


class TestReservationThreadDBLookup:
    """DB 캐시 → Slack API 폴백 예약 스레드 검색 테스트."""

    def test_DB캐시_예약스레드_사용(self):
        """DB에 저장된 위치 → Slack API 채널 순회 없이 ReservationLocation 반환."""
        fake_db = FakeDatabase()
        store = ThreadReferenceStore(fake_db.get_session)
        store.save("R12345", RESERVATION_CH, "reserve-thread-1")

        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient(result=_APPROVE_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini)

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        # DB에 캐시된 위치의 parent message만 세팅 (채널 검색용 세팅 없음)
        reader.parent_messages[(RESERVATION_CH, "reserve-thread-1")] = (
            SAMPLE_RESERVATION_MSG
        )

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH],
            thread_ref_store=store,
        )
        svc.poll_and_upload()

        assert len(survey.verification_results) == 1

    def test_Slack_API_폴백_후_DB_캐시(self):
        """DB miss → Slack API 발견 → DB에 캐시 저장 확인."""
        fake_db = FakeDatabase()
        store = ThreadReferenceStore(fake_db.get_session)

        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient(result=_APPROVE_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini)

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        # Slack API로 찾을 수 있게 세팅
        reader.channel_messages[RESERVATION_CH] = [
            {"text": SAMPLE_RESERVATION_MSG, "ts": "reserve-thread-1"},
        ]
        reader.parent_messages[(RESERVATION_CH, "reserve-thread-1")] = (
            SAMPLE_RESERVATION_MSG
        )

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH],
            thread_ref_store=store,
        )
        svc.poll_and_upload()

        # Slack API 검색 성공 후 DB에 캐시됨
        cached = store.get_by_booking_key("R12345")
        assert cached is not None
        assert cached.channel_id == RESERVATION_CH
        assert cached.thread_ts == "reserve-thread-1"

    def test_store_미설정시_기존동작(self):
        """cancel_thread_store=None → 기존 Slack API 검색만 사용."""
        survey = FakeSurveySheet()
        drive = FakeDrive()
        writer = FakeSlackWriter()
        reader = FakeSlackReader()
        gemini = FakeGeminiClient(result=_APPROVE_RESPONSE)
        analyzer = ImageAnalyzer(gemini)
        cross_verifier = CrossVerifier(gateway=gemini)

        sub = _submission()
        survey.submissions = [sub]
        reader.messages_by_text[(TARGET_CH, sub.booking_key)] = "cancel-thread-1"
        drive.folders[sub.folder_name] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="doc.png", mime_type="image/png")
        ]
        drive.file_contents["f1"] = b"fake-png-bytes"

        reader.channel_messages[RESERVATION_CH] = [
            {"text": SAMPLE_RESERVATION_MSG, "ts": "reserve-thread-1"},
        ]
        reader.parent_messages[(RESERVATION_CH, "reserve-thread-1")] = (
            SAMPLE_RESERVATION_MSG
        )

        svc = _make_service(
            survey=survey,
            drive=drive,
            writer=writer,
            reader=reader,
            analyzer=analyzer,
            cross_verifier=cross_verifier,
            reservation_channels=[RESERVATION_CH],
            thread_ref_store=None,
        )
        svc.poll_and_upload()

        assert len(survey.verification_results) == 1
