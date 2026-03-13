from __future__ import annotations

from contextlib import suppress
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import pymupdf
from slack_sdk.errors import SlackApiError

from app.core import get_logger
from app.models.analysis import CrossVerificationResult
from app.services.message_parser import parse_reservation_message
from app.views.analysis import (
    build_analysis_result_blocks,
    build_cross_verification_blocks,
)

if TYPE_CHECKING:
    from app.infrastructure.protocols import (
        DriveImageGateway,
        SlackMessageReader,
        SlackMessageWriter,
        SurveySheetGateway,
    )
    from app.models import SurveySubmission
    from app.models.analysis import AnalysisResult
    from app.models.cancellation import ReservationData
    from app.services.cross_verifier import CrossVerifier
    from app.services.image_analyzer import ImageAnalyzer

logger = get_logger(__name__)

_PDF_EMOJI = "pdf"


class CancellationImageService:
    """설문 응답 폴링 → Drive 이미지 검색 → Slack 스레드 업로드."""

    def __init__(
        self,
        survey_sheet: SurveySheetGateway,
        drive: DriveImageGateway,
        writer: SlackMessageWriter,
        reader: SlackMessageReader,
        target_channel: str,
        analyzer: ImageAnalyzer | None = None,
        cross_verifier: CrossVerifier | None = None,
        reservation_channels: list[str] | None = None,
    ) -> None:
        self._survey_sheet = survey_sheet
        self._drive = drive
        self._writer = writer
        self._reader = reader
        self._target_channel = target_channel
        self._analyzer = analyzer
        self._cross_verifier = cross_verifier
        self._reservation_channels = reservation_channels or []

    def poll_and_upload(self) -> int:
        """새 설문 응답을 폴링하고 이미지를 업로드한다. 미처리 건수를 반환."""
        logger.info("cancellation_poll_started")
        submissions = self._survey_sheet.get_all_submissions()
        if not submissions:
            logger.info("cancellation_poll_no_submissions")
            return 0

        processed = 0
        for sub in submissions:
            if self._process_submission(sub):
                self._survey_sheet.mark_processed(sub.submission_id)
                processed += 1

        skipped = len(submissions) - processed
        logger.info(
            "cancellation_poll_completed",
            total=len(submissions),
            processed=processed,
            skipped=skipped,
        )
        return skipped

    def _process_submission(self, sub: SurveySubmission) -> bool:
        logger.info(
            "cancellation_processing",
            submission_id=sub.submission_id,
            booking_key=sub.booking_key,
            customer_name=sub.customer_name,
            folder_name=sub.folder_name,
        )
        thread_ts = self._reader.find_message_by_text(
            self._target_channel, sub.booking_key
        )
        if not thread_ts:
            logger.info(
                "cancellation_no_thread",
                booking_key=sub.booking_key,
                submission_id=sub.submission_id,
            )
            return False
        logger.debug(
            "cancellation_thread_found",
            booking_key=sub.booking_key,
            thread_ts=thread_ts,
        )

        folder_id = self._drive.find_folder(sub.folder_name)
        if not folder_id:
            logger.info(
                "cancellation_no_folder",
                folder_name=sub.folder_name,
                submission_id=sub.submission_id,
            )
            return False

        files = self._drive.list_image_files(folder_id)
        if not files:
            logger.info(
                "cancellation_no_images",
                folder_name=sub.folder_name,
            )
            return False
        logger.debug(
            "cancellation_files_found",
            booking_key=sub.booking_key,
            file_count=len(files),
            file_names=[f.name for f in files],
            mime_types=[f.mime_type for f in files],
        )

        # 운영현황 행 선점: 이미 존재하면 중복 처리 방지 (Slack 업로드/댓글 스킵)
        if not self._survey_sheet.write_formatted_row(sub):
            logger.info(
                "cancellation_already_processed",
                booking_key=sub.booking_key,
            )
            return True
        logger.debug(
            "cancellation_formatted_row_created",
            booking_key=sub.booking_key,
        )

        downloads: list[tuple[str, bytes]] = []
        has_pdf = False
        for file in files:
            try:
                content = self._drive.download_file(file.id)
                logger.debug(
                    "cancellation_file_downloaded",
                    file_name=file.name,
                    size=len(content),
                    mime_type=file.mime_type,
                )
                if file.mime_type == "application/pdf":
                    images = self._convert_pdf_to_images(content, file.name)
                    logger.info(
                        "cancellation_pdf_converted",
                        file_name=file.name,
                        pages=len(images),
                        booking_key=sub.booking_key,
                    )
                    downloads.extend(images)
                    has_pdf = True
                else:
                    downloads.append((file.name, content))
            except Exception:
                logger.exception(
                    "cancellation_download_failed",
                    file_name=file.name,
                    booking_key=sub.booking_key,
                )

        if not downloads:
            return False

        self._writer.upload_files(
            channel=self._target_channel,
            thread_ts=thread_ts,
            file_uploads=[
                {"content": data, "filename": name, "title": name}
                for name, data in downloads
            ],
        )
        uploaded = len(downloads)
        collected_images = [data for _, data in downloads]

        if has_pdf:
            with suppress(SlackApiError):
                self._writer.add_reaction(
                    channel=self._target_channel,
                    timestamp=thread_ts,
                    name=_PDF_EMOJI,
                )

        if self._analyzer and collected_images:
            self._analyze_and_report(collected_images, sub, thread_ts)

        logger.info(
            "cancellation_uploaded",
            booking_key=sub.booking_key,
            count=uploaded,
            has_pdf=has_pdf,
        )
        return True

    def _analyze_and_report(
        self,
        image_data: list[bytes],
        submission: SurveySubmission,
        thread_ts: str,
    ) -> None:
        try:
            logger.info(
                "analysis_started",
                booking_key=submission.booking_key,
                image_count=len(image_data),
                image_sizes=[len(img) for img in image_data],
            )
            result = self._analyzer.analyze(image_data, submission)  # type: ignore[union-attr]
            logger.info(
                "analysis_completed",
                booking_key=submission.booking_key,
                document_type=result.document_type,
                summary=result.summary[:200] if result.summary else "",
                extracted_fields=result.extracted_fields,
            )
            blocks = build_analysis_result_blocks(result)
            self._writer.post_message(
                channel=self._target_channel,
                text="검증 결과",
                thread_ts=thread_ts,
                blocks=blocks,
            )
            self._survey_sheet.write_analysis_result(submission.submission_id, result)
            logger.info(
                "analysis_report_posted",
                booking_key=submission.booking_key,
            )
            if self._cross_verifier:
                try:
                    self._cross_verify_and_report(result, submission, thread_ts)
                except Exception:
                    logger.exception(
                        "cross_verification_failed",
                        booking_key=submission.booking_key,
                    )
        except Exception:
            logger.exception(
                "image_analysis_failed", booking_key=submission.booking_key
            )

    def _cross_verify_and_report(
        self,
        analysis_result: AnalysisResult,
        submission: SurveySubmission,
        thread_ts: str,
    ) -> None:
        """예약 데이터를 찾아 교차검증하고 결과를 스레드에 포스트한다."""
        reservation_data = self._find_reservation_data(submission.booking_key)

        if reservation_data is None:
            result = CrossVerificationResult(
                verdict="보류",
                reason="예약 스레드를 찾지 못했습니다.",
            )
        else:
            result = self._cross_verifier.verify(  # type: ignore[union-attr]
                analysis_result, reservation_data, submission
            )

        blocks = build_cross_verification_blocks(result)
        self._writer.post_message(
            channel=self._target_channel,
            text=f"교차검증: {result.verdict}",
            thread_ts=thread_ts,
            blocks=blocks,
        )
        self._survey_sheet.write_verification_result(submission.submission_id, result)
        logger.info(
            "cross_verification_posted",
            booking_key=submission.booking_key,
            verdict=result.verdict,
        )

    def _find_reservation_data(self, booking_key: str) -> ReservationData | None:
        """예약 채널을 순회하며 예약 메시지를 찾아 파싱한다."""
        for channel in self._reservation_channels:
            found_ts = self._reader.find_message_by_text(channel, booking_key)
            if not found_ts:
                continue
            parent_text = self._reader.get_parent_message(channel, found_ts)
            if not parent_text:
                continue
            return parse_reservation_message(parent_text)
        return None

    @staticmethod
    def _convert_pdf_to_images(
        pdf_bytes: bytes, original_name: str
    ) -> list[tuple[str, bytes]]:
        """PDF를 페이지별 PNG 이미지로 변환한다."""
        stem = PurePosixPath(original_name).stem
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        try:
            pages = len(doc)
            result = []
            for i, page in enumerate(doc, 1):
                pix = page.get_pixmap(dpi=150)
                img_name = f"{stem}_p{i}.png" if pages > 1 else f"{stem}.png"
                result.append((img_name, pix.tobytes("png")))
            return result
        finally:
            doc.close()
