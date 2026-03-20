from __future__ import annotations

import threading
from contextlib import suppress
from typing import TYPE_CHECKING

from slack_sdk.errors import SlackApiError

from app.core import get_logger
from app.models.analysis import CrossVerificationResult
from app.views.analysis import (
    build_analysis_result_blocks,
    build_cross_verification_blocks,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from app.infrastructure.protocols import (
        SlackMessageReader,
        SlackMessageWriter,
        SurveySheetGateway,
    )
    from app.models import SurveySubmission
    from app.models.analysis import AnalysisResult
    from app.services.cross_verifier import CrossVerifier
    from app.services.drive_file_collector import DriveFileCollector
    from app.services.image_analyzer import ImageAnalyzer
    from app.services.reservation_locator import ReservationLocation, ReservationLocator

_PDF_EMOJI = "pdf"


class CancellationImageService:
    """설문 응답 폴링 → Drive 이미지 검색 → Slack 스레드 업로드."""

    def __init__(
        self,
        survey_sheet: SurveySheetGateway,
        file_collector: DriveFileCollector,
        writer: SlackMessageWriter,
        reader: SlackMessageReader,
        target_channel: str,
        analyzer: ImageAnalyzer | None = None,
        cross_verifier: CrossVerifier | None = None,
        reservation_locator: ReservationLocator | None = None,
        overseas_prefixes: list[str] | None = None,
        overseas_mention: str = "",
        overseas_reaction: str = "",
    ) -> None:
        self._survey_sheet = survey_sheet
        self._file_collector = file_collector
        self._writer = writer
        self._reader = reader
        self._target_channel = target_channel
        self._analyzer = analyzer
        self._cross_verifier = cross_verifier
        self._reservation_locator = reservation_locator
        self._poll_lock = threading.Lock()
        self._overseas_prefixes = tuple(
            p.upper() for p in (overseas_prefixes or ()) if p
        )
        self._overseas_mention = overseas_mention
        self._overseas_reaction = overseas_reaction

    def poll_and_upload(self) -> int:
        """새 설문 응답을 폴링하고 이미지를 업로드한다. 미처리 건수를 반환."""
        if not self._poll_lock.acquire(blocking=False):
            return -1
        try:
            return self._poll_and_upload_locked()
        finally:
            self._poll_lock.release()

    def _poll_and_upload_locked(self) -> int:
        submissions = self._survey_sheet.get_all_submissions()
        if not submissions:
            return 0

        # 같은 booking_key 중 최신 제출만 처리, 이전 제출은 마킹만
        latest_by_key: dict[str, SurveySubmission] = {}
        for sub in submissions:
            prev = latest_by_key.get(sub.booking_key)
            if prev is None or sub.submission_date > prev.submission_date:
                latest_by_key[sub.booking_key] = sub

        processed = 0
        for sub in submissions:
            if sub is latest_by_key.get(sub.booking_key):
                if self._process_submission(sub):
                    self._survey_sheet.mark_processed(sub.submission_id)
                    processed += 1
            else:
                # 이전 제출 → 처리 완료로 마킹만
                self._survey_sheet.mark_processed(sub.submission_id)
                processed += 1

        return len(submissions) - processed

    def _process_submission(self, sub: SurveySubmission) -> bool:
        thread_ts = self._reader.find_message_by_text(
            self._target_channel, sub.booking_key
        )
        if not thread_ts:
            return False

        collected = self._file_collector.collect(sub.folder_name)
        if collected is None:
            return False

        # 운영현황 행 선점: 이미 존재하면 중복 처리 방지 (Slack 업로드/댓글 스킵)
        if not self._survey_sheet.write_formatted_row(sub):
            return True

        self._writer.upload_files(
            channel=self._target_channel,
            thread_ts=thread_ts,
            file_uploads=[
                {"content": data, "filename": name, "title": name}
                for name, data in collected.images
            ],
        )
        collected_images = [data for _, data in collected.images]

        if collected.has_pdf:
            with suppress(SlackApiError):
                self._writer.add_reaction(
                    channel=self._target_channel,
                    timestamp=thread_ts,
                    name=_PDF_EMOJI,
                )

        if self._is_overseas(sub.booking_key):
            self._handle_overseas(thread_ts, sub.booking_key)
            return True

        if self._analyzer and collected_images:
            self._analyze_and_report(collected_images, sub, thread_ts)

        return True

    def _is_overseas(self, booking_key: str) -> bool:
        if not self._overseas_prefixes:
            return False
        key_upper = booking_key.upper()
        return any(key_upper.startswith(p) for p in self._overseas_prefixes)

    def _handle_overseas(self, thread_ts: str, booking_key: str) -> None:
        if self._overseas_mention:
            try:
                self._writer.post_message(
                    channel=self._target_channel,
                    text=(
                        f"{self._overseas_mention}"
                        f" [{booking_key}] 해외 결항 건"
                        " — 확인 부탁드립니다."
                    ),
                    thread_ts=thread_ts,
                )
            except SlackApiError:
                logger.exception("overseas_mention_failed", booking_key=booking_key)
        if self._overseas_reaction:
            with suppress(SlackApiError):
                self._writer.add_reaction(
                    channel=self._target_channel,
                    timestamp=thread_ts,
                    name=self._overseas_reaction,
                )

    def _analyze_and_report(
        self,
        image_data: list[bytes],
        submission: SurveySubmission,
        thread_ts: str,
    ) -> None:
        # 분석 — optional (AI API 실패 시 업로드만 유지)
        try:
            result = self._analyzer.analyze(image_data, submission)  # type: ignore[union-attr]
        except Exception:
            return

        # 이미지 품질 부적합 → X 리액션 + 사유, 즉시 종료
        if not result.is_valid:
            with suppress(SlackApiError):
                self._writer.add_reaction(
                    channel=self._target_channel,
                    timestamp=thread_ts,
                    name="x",
                )
            reason_text = "부적합 사유:\n" + "\n".join(
                f"- {r}" for r in result.rejection_reasons
            )
            self._writer.post_message(
                channel=self._target_channel,
                text=reason_text,
                thread_ts=thread_ts,
            )
            return

        # 결과 포스트 + 시트 기록 — critical (실패 시 전파)
        blocks = build_analysis_result_blocks(result)
        self._writer.post_message(
            channel=self._target_channel,
            text="검증 결과",
            thread_ts=thread_ts,
            blocks=blocks,
        )
        self._survey_sheet.write_analysis_result(submission.submission_id, result)

        # 교차검증 — optional (실패해도 분석 결과는 이미 포스트됨)
        if self._cross_verifier:
            try:
                self._cross_verify_and_report(result, submission, thread_ts)
            except Exception:
                return

    def _cross_verify_and_report(
        self,
        analysis_result: AnalysisResult,
        submission: SurveySubmission,
        thread_ts: str,
    ) -> None:
        """예약 데이터를 찾아 교차검증하고 결과를 스레드에 포스트한다."""
        if self._reservation_locator is None:
            location = None
        else:
            location = self._reservation_locator.find(
                submission.booking_key, submission.phone
            )

        if location is None:
            result = CrossVerificationResult(
                verdict="보류",
                reason="예약 스레드를 찾지 못했습니다.",
            )
        else:
            result = self._cross_verifier.verify(  # type: ignore[union-attr]
                analysis_result, location.data, submission
            )

        self._survey_sheet.write_verification_result(submission.submission_id, result)

        if result.verdict == "승인" and location is not None:
            self._post_bidirectional_links(thread_ts, location, submission)
        elif result.verdict != "승인":
            blocks = build_cross_verification_blocks(result)
            self._writer.post_message(
                channel=self._target_channel,
                text=f"교차검증: {result.verdict}",
                thread_ts=thread_ts,
                blocks=blocks,
            )

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
