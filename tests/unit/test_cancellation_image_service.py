from __future__ import annotations

import types

import pymupdf

from app.models import DriveFile, SurveySubmission
from app.services.cancellation_image_service import CancellationImageService
from app.services.cross_verifier import CrossVerifier
from app.services.image_analyzer import ImageAnalyzer
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
    analyzer: ImageAnalyzer | None = None,
    cross_verifier: CrossVerifier | None = None,
    reservation_channels: list[str] | None = None,
) -> CancellationImageService:
    return CancellationImageService(
        survey_sheet=survey or FakeSurveySheet(),
        drive=drive or FakeDrive(),
        writer=writer or FakeSlackWriter(),
        reader=reader or FakeSlackReader(),
        target_channel=TARGET_CH,
        analyzer=analyzer,
        cross_verifier=cross_verifier,
        reservation_channels=reservation_channels,
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
