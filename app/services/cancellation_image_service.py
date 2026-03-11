from __future__ import annotations

from contextlib import suppress
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import pymupdf
from slack_sdk.errors import SlackApiError

from app.core import get_logger

if TYPE_CHECKING:
    from app.infrastructure.protocols import (
        DriveImageGateway,
        SlackMessageReader,
        SlackMessageWriter,
        SurveySheetGateway,
    )
    from app.models import SurveySubmission

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
    ) -> None:
        self._survey_sheet = survey_sheet
        self._drive = drive
        self._writer = writer
        self._reader = reader
        self._target_channel = target_channel

    def poll_and_upload(self) -> None:
        """새 설문 응답을 폴링하고 이미지를 업로드한다."""
        logger.info("cancellation_poll_started")
        submissions = self._survey_sheet.get_all_submissions()
        if not submissions:
            logger.info("cancellation_poll_no_submissions")
            return

        processed = 0
        for sub in submissions:
            if self._process_submission(sub):
                self._survey_sheet.mark_processed(sub.submission_id)
                self._survey_sheet.write_formatted_row(sub)
                processed += 1

        logger.info(
            "cancellation_poll_completed",
            total=len(submissions),
            processed=processed,
            skipped=len(submissions) - processed,
        )

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

        uploaded = 0
        has_pdf = False
        for file in files:
            try:
                content = self._drive.download_file(file.id)
                if file.mime_type == "application/pdf":
                    images = self._convert_pdf_to_images(content, file.name)
                    logger.info(
                        "cancellation_pdf_converted",
                        file_name=file.name,
                        pages=len(images),
                        booking_key=sub.booking_key,
                    )
                    for img_name, img_bytes in images:
                        self._writer.upload_file(
                            channel=self._target_channel,
                            thread_ts=thread_ts,
                            content=img_bytes,
                            filename=img_name,
                        )
                        uploaded += 1
                    has_pdf = True
                else:
                    self._writer.upload_file(
                        channel=self._target_channel,
                        thread_ts=thread_ts,
                        content=content,
                        filename=file.name,
                    )
                    uploaded += 1
            except Exception:
                logger.exception(
                    "cancellation_upload_failed",
                    file_name=file.name,
                    booking_key=sub.booking_key,
                )

        if uploaded == 0:
            return False

        if has_pdf:
            with suppress(SlackApiError):
                self._writer.add_reaction(
                    channel=self._target_channel,
                    timestamp=thread_ts,
                    name=_PDF_EMOJI,
                )

        logger.info(
            "cancellation_uploaded",
            booking_key=sub.booking_key,
            count=uploaded,
            has_pdf=has_pdf,
        )
        return True

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
