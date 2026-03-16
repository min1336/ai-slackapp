from __future__ import annotations

from contextlib import suppress
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, NamedTuple

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
    from app.services.thread_reference_store import ThreadReferenceStore

logger = get_logger(__name__)

_PDF_EMOJI = "pdf"
_INVALID_EMOJI = "x"


class ReservationLocation(NamedTuple):
    """예약 데이터 + 해당 스레드 위치."""

    data: ReservationData
    channel: str
    thread_ts: str


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
        thread_ref_store: ThreadReferenceStore | None = None,
    ) -> None:
        self._survey_sheet = survey_sheet
        self._drive = drive
        self._writer = writer
        self._reader = reader
        self._target_channel = target_channel
        self._analyzer = analyzer
        self._cross_verifier = cross_verifier
        self._reservation_channels = reservation_channels or []
        self._thread_ref_store = thread_ref_store

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
        else:
            logger.warning(
                "analysis_skipped",
                booking_key=sub.booking_key,
                reason="no_analyzer" if not self._analyzer else "no_images",
                has_analyzer=self._analyzer is not None,
                image_count=len(collected_images),
            )

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

            # 이미지 품질 부적합 → X + 사유, 즉시 종료
            if not result.is_valid:
                logger.info(
                    "analysis_invalid_image",
                    booking_key=submission.booking_key,
                    rejection_reasons=result.rejection_reasons,
                )
                reason_text = "부적합 사유:\n" + "\n".join(
                    f"- {r}" for r in result.rejection_reasons
                )
                self._writer.post_message(
                    channel=self._target_channel,
                    text=reason_text,
                    thread_ts=thread_ts,
                )
                with suppress(SlackApiError):
                    self._writer.add_reaction(
                        channel=self._target_channel,
                        timestamp=thread_ts,
                        name=_INVALID_EMOJI,
                    )
                return

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
        location = self._find_reservation_data(submission.booking_key, submission.phone)

        if location is None:
            result = CrossVerificationResult(
                verdict="보류",
                reason="예약 스레드를 찾지 못했습니다.",
            )
        else:
            result = self._cross_verifier.verify(  # type: ignore[union-attr]
                analysis_result, location.data, submission
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

        if result.verdict == "반려":
            with suppress(SlackApiError):
                self._writer.add_reaction(
                    channel=self._target_channel,
                    timestamp=thread_ts,
                    name=_INVALID_EMOJI,
                )
        elif result.verdict == "승인" and location is not None:
            self._post_bidirectional_links(thread_ts, location, submission)

    def _post_bidirectional_links(
        self,
        thread_ts: str,
        location: ReservationLocation,
        submission: SurveySubmission,
    ) -> None:
        """승인 시 예약↔취소 스레드 간 양방향 permalink을 포스트한다."""
        with suppress(SlackApiError):
            res_permalink = self._reader.get_thread_url(
                location.channel, location.thread_ts
            )
            if res_permalink:
                self._writer.post_message(
                    channel=self._target_channel,
                    text=res_permalink,
                    thread_ts=thread_ts,
                )

            cancel_permalink = self._reader.get_thread_url(
                self._target_channel, thread_ts
            )
            if cancel_permalink:
                self._writer.post_message(
                    channel=location.channel,
                    text=cancel_permalink,
                    thread_ts=location.thread_ts,
                )
            logger.info(
                "cancellation_bidirectional_links_posted",
                booking_key=submission.booking_key,
            )

    def _find_reservation_data(
        self, booking_key: str, phone: str = ""
    ) -> ReservationLocation | None:
        """예약번호로 검색 → 실패 시 전화번호 fallback."""
        location = self._search_reservation_channels(booking_key)
        if location:
            return location
        if phone:
            logger.info(
                "reservation_search_fallback_phone",
                booking_key=booking_key,
            )
            return self._search_reservation_channels(phone)
        return None

    def _search_reservation_channels(
        self, search_text: str
    ) -> ReservationLocation | None:
        """DB 캐시 → Slack API 폴백으로 예약 스레드를 찾는다."""
        # Stage 1: DB lookup
        if self._thread_ref_store:
            location = self._thread_ref_store.get_by_booking_key(search_text)
            if location:
                parent_text = self._reader.get_parent_message(
                    location.channel_id, location.thread_ts
                )
                if parent_text:
                    return ReservationLocation(
                        data=parse_reservation_message(parent_text),
                        channel=location.channel_id,
                        thread_ts=location.thread_ts,
                    )

        # Stage 2: Slack API fallback
        for channel in self._reservation_channels:
            found_ts = self._reader.find_message_by_text(channel, search_text)
            if not found_ts:
                continue
            parent_text = self._reader.get_parent_message(channel, found_ts)
            if not parent_text:
                continue
            if self._thread_ref_store:
                self._thread_ref_store.save(search_text, channel, found_ts)
            return ReservationLocation(
                data=parse_reservation_message(parent_text),
                channel=channel,
                thread_ts=found_ts,
            )
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
