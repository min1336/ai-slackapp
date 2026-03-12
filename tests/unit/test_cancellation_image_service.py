from __future__ import annotations

import pymupdf

from app.models import DriveFile, SurveySubmission
from app.services.cancellation_image_service import CancellationImageService
from app.services.image_analyzer import ImageAnalyzer
from tests.fakes.fake_gemini import FakeGeminiClient
from tests.fakes.fake_slack import FakeSlackReader, FakeSlackWriter
from tests.fakes.fake_survey import FakeSurveySheet

TARGET_CH = "C-CANCEL"


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
    analyzer: ImageAnalyzer | None = None,
) -> CancellationImageService:
    return CancellationImageService(
        survey_sheet=survey or FakeSurveySheet(),
        drive=drive or FakeDrive(),
        writer=writer or FakeSlackWriter(),
        reader=reader or FakeSlackReader(),
        target_channel=TARGET_CH,
        analyzer=analyzer,
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

    def test_valid_analysis_adds_checkmark(self):
        svc, writer, survey, gemini = self._setup()
        svc.poll_and_upload()

        assert any(r["name"] == "white_check_mark" for r in writer.reactions)
        assert len(writer.posted_messages) >= 1
        assert len(survey.analysis_results) == 1

    def test_invalid_analysis_adds_x(self):
        svc, writer, survey, _ = self._setup(
            gemini_result={
                "is_valid": False,
                "confidence": 0.8,
                "document_type": "결항확인서",
                "extracted_fields": {},
                "mismatches": ["예약번호 불일치"],
                "quality_issues": [],
                "reasoning": "불일치",
            }
        )
        svc.poll_and_upload()

        assert any(r["name"] == "x" for r in writer.reactions)

    def test_analysis_failure_adds_warning_but_upload_succeeds(self):
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
        assert any(r["name"] == "warning" for r in writer.reactions)
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
