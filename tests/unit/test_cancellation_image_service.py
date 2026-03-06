from __future__ import annotations

import pymupdf

from app.models import DriveFile, SurveySubmission
from app.services.cancellation_image_service import CancellationImageService
from tests.fakes.fake_drive import FakeDriveClient
from tests.fakes.fake_slack import FakeSlackReader, FakeSlackWriter
from tests.fakes.fake_survey import FakeSurveySheet

TARGET_CH = "C-CANCEL"


def _make_service(
    *,
    survey: FakeSurveySheet | None = None,
    drive: FakeDriveClient | None = None,
    writer: FakeSlackWriter | None = None,
    reader: FakeSlackReader | None = None,
) -> CancellationImageService:
    return CancellationImageService(
        survey_sheet=survey or FakeSurveySheet(),
        drive=drive or FakeDriveClient(),
        writer=writer or FakeSlackWriter(),
        reader=reader or FakeSlackReader(),
        target_channel=TARGET_CH,
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


class TestPollAndUpload:
    def test_새_응답_이미지_업로드(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="img.jpg", mime_type="image/jpeg"),
        ]
        drive.file_contents["f1"] = b"\xff\xd8"

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 1
        uploaded = writer.uploaded_files[0]
        assert uploaded["channel"] == TARGET_CH
        assert uploaded["thread_ts"] == "1.0"
        assert uploaded["filename"] == "img.jpg"
        assert uploaded["content"] == b"\xff\xd8"

    def test_이미_처리된_응답은_건너뜀(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="img.jpg", mime_type="image/jpeg"),
        ]
        drive.file_contents["f1"] = b"\xff"

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)

        svc.poll_and_upload()
        svc.poll_and_upload()  # 두 번째 호출

        assert len(writer.uploaded_files) == 1

    def test_스레드_없으면_건너뜀(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])
        writer = FakeSlackWriter()

        svc = _make_service(survey=survey, writer=writer)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 0

    def test_폴더_없으면_건너뜀(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 0

    def test_이미지_없으면_업로드_안함(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        # folder-1에 이미지 없음

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 0

    def test_빈_설문_무동작(self):
        writer = FakeSlackWriter()
        svc = _make_service(writer=writer)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 0

    def test_여러_이미지_모두_업로드(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="a.jpg", mime_type="image/jpeg"),
            DriveFile(id="f2", name="b.png", mime_type="image/png"),
            DriveFile(id="f3", name="c.jpg", mime_type="image/jpeg"),
        ]
        drive.file_contents["f1"] = b"img1"
        drive.file_contents["f2"] = b"img2"
        drive.file_contents["f3"] = b"img3"

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 3

    def test_업로드_실패해도_나머지_계속_처리(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="a.jpg", mime_type="image/jpeg"),
            DriveFile(id="f2", name="b.jpg", mime_type="image/jpeg"),
        ]
        drive.file_contents["f1"] = b"img1"
        drive.file_contents["f2"] = b"img2"

        writer = FakeSlackWriter()
        call_count = 0
        original_upload = writer.upload_file

        def _failing_upload(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Slack API error")
            original_upload(**kwargs)

        writer.upload_file = _failing_upload  # type: ignore[assignment]

        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        # 첫 번째 실패, 두 번째 성공
        assert len(writer.uploaded_files) == 1


class TestSheetBasedTracking:
    """시트 기반 처리 상태 추적 테스트."""

    def test_성공_시_시트에_처리완료_기록(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="img.jpg", mime_type="image/jpeg"),
        ]
        drive.file_contents["f1"] = b"\xff"

        svc = _make_service(survey=survey, drive=drive, reader=reader)
        svc.poll_and_upload()

        assert "1001" in survey.processed_ids

    def test_실패_시_처리완료_기록_안함(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])
        # reader에 스레드 없음 → 실패

        svc = _make_service(survey=survey)
        svc.poll_and_upload()

        assert "1001" not in survey.processed_ids

    def test_시트_기반_중복_방지_재시작_후에도_유지(self):
        """FakeSurveySheet가 processed_ids로 필터링하므로
        서비스 인스턴스를 새로 만들어도 중복 처리 안 됨."""
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="img.jpg", mime_type="image/jpeg"),
        ]
        drive.file_contents["f1"] = b"\xff"

        writer = FakeSlackWriter()

        # 첫 번째 서비스 인스턴스
        svc1 = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc1.poll_and_upload()
        assert len(writer.uploaded_files) == 1

        # 두 번째 서비스 인스턴스 (재시작 시뮬레이션) — 같은 survey 객체 공유
        svc2 = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc2.poll_and_upload()
        assert len(writer.uploaded_files) == 1  # 중복 업로드 없음


class TestFormattedSheet:
    """운영현황 포맷 시트 작성 테스트."""

    def test_성공_시_포맷_시트에_행_추가(self):
        sub = _submission(
            submission_date="2026-03-05",
            company_name="고양이렌트카",
            phone="111-1111-1111",
        )
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="img.jpg", mime_type="image/jpeg"),
        ]
        drive.file_contents["f1"] = b"\xff"

        svc = _make_service(survey=survey, drive=drive, reader=reader)
        svc.poll_and_upload()

        assert len(survey.formatted_rows) == 1
        row = survey.formatted_rows[0]
        assert row.submission_date == "2026-03-05"
        assert row.customer_name == "홍길동"
        assert row.booking_key == "R12345"
        assert row.company_name == "고양이렌트카"
        assert row.phone == "111-1111-1111"

    def test_실패_시_포맷_시트에_기록_안함(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        svc = _make_service(survey=survey)
        svc.poll_and_upload()

        assert len(survey.formatted_rows) == 0


def _make_pdf_bytes(pages: int = 1) -> bytes:
    """테스트용 최소 PDF 바이너리 생성."""
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=100, height=100)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestPdfConversion:
    """PDF 파일을 이미지로 변환하여 업로드하는 테스트."""

    def test_pdf_파일_이미지로_변환_업로드(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="cert.pdf", mime_type="application/pdf"),
        ]
        drive.file_contents["f1"] = _make_pdf_bytes()

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 1
        uploaded = writer.uploaded_files[0]
        assert uploaded["filename"] == "cert.png"
        assert uploaded["content"][:4] == b"\x89PNG"  # PNG 시그니처

    def test_pdf와_이미지_혼합_폴더(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="photo.jpg", mime_type="image/jpeg"),
            DriveFile(id="f2", name="cert.pdf", mime_type="application/pdf"),
        ]
        drive.file_contents["f1"] = b"\xff\xd8"
        drive.file_contents["f2"] = _make_pdf_bytes()

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 2
        filenames = [f["filename"] for f in writer.uploaded_files]
        assert "photo.jpg" in filenames
        assert "cert.png" in filenames

    def test_다페이지_pdf_모든_페이지_업로드(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="multi.pdf", mime_type="application/pdf"),
        ]
        drive.file_contents["f1"] = _make_pdf_bytes(pages=3)

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 3
        filenames = [f["filename"] for f in writer.uploaded_files]
        assert filenames == ["multi_p1.png", "multi_p2.png", "multi_p3.png"]

    def test_pdf_업로드_시_리액션_추가(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="cert.pdf", mime_type="application/pdf"),
        ]
        drive.file_contents["f1"] = _make_pdf_bytes()

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.reactions) == 1
        reaction = writer.reactions[0]
        assert reaction["channel"] == TARGET_CH
        assert reaction["timestamp"] == "1.0"
        assert reaction["name"] == "pdf"

    def test_이미지만_있으면_pdf_리액션_없음(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="photo.jpg", mime_type="image/jpeg"),
        ]
        drive.file_contents["f1"] = b"\xff\xd8"

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.reactions) == 0

    def test_pdf_변환_실패_시_다음_파일_계속(self):
        sub = _submission()
        survey = FakeSurveySheet([sub])

        reader = FakeSlackReader()
        reader.messages_by_text[(TARGET_CH, "R12345")] = "1.0"

        drive = FakeDriveClient()
        drive.folders["홍길동_R12345"] = "folder-1"
        drive.files["folder-1"] = [
            DriveFile(id="f1", name="broken.pdf", mime_type="application/pdf"),
            DriveFile(id="f2", name="ok.jpg", mime_type="image/jpeg"),
        ]
        drive.file_contents["f1"] = b"not-a-real-pdf"
        drive.file_contents["f2"] = b"\xff\xd8"

        writer = FakeSlackWriter()
        svc = _make_service(survey=survey, drive=drive, writer=writer, reader=reader)
        svc.poll_and_upload()

        assert len(writer.uploaded_files) == 1
        assert writer.uploaded_files[0]["filename"] == "ok.jpg"
