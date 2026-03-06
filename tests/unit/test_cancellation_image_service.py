from __future__ import annotations

import pymupdf

from app.models import SurveySubmission
from app.services.cancellation_image_service import CancellationImageService
from tests.fakes.fake_slack import FakeSlackReader, FakeSlackWriter
from tests.fakes.fake_survey import FakeSurveySheet

TARGET_CH = "C-CANCEL"


def _make_service(
    *,
    survey: FakeSurveySheet | None = None,
    writer: FakeSlackWriter | None = None,
    reader: FakeSlackReader | None = None,
    downloader=None,
) -> CancellationImageService:
    return CancellationImageService(
        survey_sheet=survey or FakeSurveySheet(),
        writer=writer or FakeSlackWriter(),
        reader=reader or FakeSlackReader(),
        target_channel=TARGET_CH,
        file_downloader=downloader or (lambda url: b"\xff\xd8"),
    )


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


class TestHandleWebhook:
    def test_파일_URL에서_다운로드_후_업로드(self):
        sub = _submission()
        survey = FakeSurveySheet()
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, writer=writer, reader=reader)
        result = svc.handle_webhook(sub, file_urls=["https://example.com/img.jpg"])

        assert result is True
        assert len(writer.uploaded_files) == 1
        assert writer.uploaded_files[0]["filename"] == "img.jpg"
        assert writer.uploaded_files[0]["thread_ts"] == "1.0"

    def test_스레드_없으면_업로드_안함(self):
        sub = _submission()
        survey = FakeSurveySheet()
        writer = FakeSlackWriter()

        svc = _make_service(survey=survey, writer=writer)
        result = svc.handle_webhook(sub, file_urls=["https://example.com/img.jpg"])

        assert result is False
        assert len(writer.uploaded_files) == 0
        assert len(survey.formatted_rows) == 0

    def test_빈_파일_URL이면_업로드_안함(self):
        sub = _submission()
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()
        survey = FakeSurveySheet()

        svc = _make_service(survey=survey, writer=writer, reader=reader)
        result = svc.handle_webhook(sub, file_urls=[])

        assert result is False
        assert len(writer.uploaded_files) == 0

    def test_성공_시_운영현황_시트_작성(self):
        sub = _submission()
        survey = FakeSurveySheet()
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        svc = _make_service(survey=survey, reader=reader)
        svc.handle_webhook(sub, file_urls=["https://example.com/a.jpg"])

        assert len(survey.formatted_rows) == 1
        assert survey.formatted_rows[0].booking_key == "R12345"

    def test_여러_파일_모두_업로드(self):
        sub = _submission()
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        svc = _make_service(writer=writer, reader=reader)
        svc.handle_webhook(
            sub,
            file_urls=[
                "https://example.com/a.jpg",
                "https://example.com/b.png",
                "https://example.com/c.jpg",
            ],
        )

        assert len(writer.uploaded_files) == 3

    def test_다운로드_실패해도_나머지_계속(self):
        sub = _submission()
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        call_count = 0

        def _failing_downloader(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("download failed")
            return b"\xff\xd8"

        svc = _make_service(
            writer=writer, reader=reader, downloader=_failing_downloader
        )
        svc.handle_webhook(
            sub,
            file_urls=[
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
            ],
        )

        assert len(writer.uploaded_files) == 1

    def test_URL에서_파일명_추출(self):
        sub = _submission()
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        svc = _make_service(writer=writer, reader=reader)
        svc.handle_webhook(
            sub,
            file_urls=["https://jotform.com/uploads/Carmore/12345/image%20(1).png"],
        )

        assert writer.uploaded_files[0]["filename"] == "image (1).png"


class TestPdfConversion:
    """PDF 파일을 이미지로 변환하여 업로드하는 테스트."""

    def _make_pdf_bytes(self, pages: int = 1) -> bytes:
        doc = pymupdf.open()
        for _ in range(pages):
            doc.new_page(width=100, height=100)
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    def test_pdf_파일_이미지로_변환_업로드(self):
        sub = _submission()
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()
        pdf_bytes = self._make_pdf_bytes()

        svc = _make_service(
            writer=writer, reader=reader, downloader=lambda url: pdf_bytes
        )
        svc.handle_webhook(sub, file_urls=["https://example.com/cert.pdf"])

        assert len(writer.uploaded_files) == 1
        assert writer.uploaded_files[0]["filename"] == "cert.png"
        assert writer.uploaded_files[0]["content"][:4] == b"\x89PNG"

    def test_다페이지_pdf_모든_페이지_업로드(self):
        sub = _submission()
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()
        pdf_bytes = self._make_pdf_bytes(pages=3)

        svc = _make_service(
            writer=writer, reader=reader, downloader=lambda url: pdf_bytes
        )
        svc.handle_webhook(sub, file_urls=["https://example.com/multi.pdf"])

        assert len(writer.uploaded_files) == 3
        filenames = [f["filename"] for f in writer.uploaded_files]
        assert filenames == ["multi_p1.png", "multi_p2.png", "multi_p3.png"]

    def test_pdf_업로드_시_리액션_추가(self):
        sub = _submission()
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()
        pdf_bytes = self._make_pdf_bytes()

        svc = _make_service(
            writer=writer, reader=reader, downloader=lambda url: pdf_bytes
        )
        svc.handle_webhook(sub, file_urls=["https://example.com/cert.pdf"])

        assert len(writer.reactions) == 1
        assert writer.reactions[0]["name"] == "pdf"

    def test_이미지만_있으면_pdf_리액션_없음(self):
        sub = _submission()
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        svc = _make_service(writer=writer, reader=reader)
        svc.handle_webhook(sub, file_urls=["https://example.com/photo.jpg"])

        assert len(writer.reactions) == 0

    def test_pdf_변환_실패_시_다음_파일_계속(self):
        sub = _submission()
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"
        writer = FakeSlackWriter()

        call_count = 0

        def _downloader(url):
            nonlocal call_count
            call_count += 1
            if "broken" in url:
                return b"not-a-real-pdf"
            return b"\xff\xd8"

        svc = _make_service(writer=writer, reader=reader, downloader=_downloader)
        svc.handle_webhook(
            sub,
            file_urls=[
                "https://example.com/broken.pdf",
                "https://example.com/ok.jpg",
            ],
        )

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
        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        svc = _make_service(survey=survey, reader=reader)
        svc.handle_webhook(sub, file_urls=["https://example.com/img.jpg"])

        assert len(survey.formatted_rows) == 1
        row = survey.formatted_rows[0]
        assert row.submission_date == "2026-03-05"
        assert row.customer_name == "홍길동"
        assert row.booking_key == "R12345"
        assert row.company_name == "고양이렌트카"

    def test_실패_시_포맷_시트에_기록_안함(self):
        sub = _submission()
        survey = FakeSurveySheet()
        # reader에 스레드 없음 → 실패

        svc = _make_service(survey=survey)
        svc.handle_webhook(sub, file_urls=["https://example.com/img.jpg"])

        assert len(survey.formatted_rows) == 0
