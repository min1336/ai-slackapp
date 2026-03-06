from __future__ import annotations

import urllib.request
from collections.abc import Callable
from contextlib import suppress
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

import pymupdf
from slack_sdk.errors import SlackApiError

from app.core import get_logger

if TYPE_CHECKING:
    from app.infrastructure.protocols import (
        SlackMessageReader,
        SlackMessageWriter,
        SurveySheetGateway,
    )
    from app.models import SurveySubmission

logger = get_logger(__name__)

_PDF_EMOJI = "pdf"


def _default_download(url: str) -> bytes:
    """URL에서 파일을 다운로드한다."""
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        return resp.read()


def _filename_from_url(url: str) -> str:
    """URL에서 파일명을 추출한다."""
    path = urlparse(url).path
    return unquote(PurePosixPath(path).name) or "file"


def _mime_from_filename(filename: str) -> str:
    """파일명에서 MIME 타입을 추론한다."""
    ext = PurePosixPath(filename).suffix.lower()
    if ext == ".pdf":
        return "application/pdf"
    return f"image/{ext.lstrip('.')}" if ext else "application/octet-stream"


class CancellationImageService:
    """Jotform webhook 수신 → 파일 다운로드 → Slack 스레드 업로드."""

    def __init__(
        self,
        survey_sheet: SurveySheetGateway,
        writer: SlackMessageWriter,
        reader: SlackMessageReader,
        target_channel: str,
        file_downloader: Callable[[str], bytes] = _default_download,
    ) -> None:
        self._survey_sheet = survey_sheet
        self._writer = writer
        self._reader = reader
        self._target_channel = target_channel
        self._download = file_downloader

    def handle_webhook(self, sub: SurveySubmission, file_urls: list[str]) -> bool:
        """Jotform webhook에서 받은 파일 URL을 Slack 스레드에 업로드한다."""
        logger.info(
            "cancellation_webhook_received",
            submission_id=sub.submission_id,
            booking_key=sub.booking_key,
            customer_name=sub.customer_name,
            file_count=len(file_urls),
        )

        thread_ts = self._reader.find_message_by_text(
            self._target_channel, sub.booking_key
        )
        if not thread_ts:
            logger.info("cancellation_no_thread", booking_key=sub.booking_key)
            return False

        if not file_urls:
            logger.info("cancellation_no_files", booking_key=sub.booking_key)
            return False

        uploaded = 0
        has_pdf = False

        for url in file_urls:
            try:
                content = self._download(url)
                filename = _filename_from_url(url)
                mime_type = _mime_from_filename(filename)

                if mime_type == "application/pdf":
                    images = self._convert_pdf_to_images(content, filename)
                    logger.info(
                        "cancellation_pdf_converted",
                        file_name=filename,
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
                        filename=filename,
                    )
                    uploaded += 1
            except Exception:
                logger.exception(
                    "cancellation_upload_failed",
                    url=url,
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

        self._survey_sheet.write_formatted_row(sub)
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
