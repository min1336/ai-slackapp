from __future__ import annotations

from typing import TYPE_CHECKING

from app.core import get_logger
from app.models import ThreadLocation

if TYPE_CHECKING:
    from app.infrastructure.protocols import SlackMessageReader
    from app.services.thread_reference_store import ThreadReferenceStore

logger = get_logger(__name__)


class ThreadDiscoveryService:
    def __init__(
        self,
        thread_ref_store: ThreadReferenceStore,
        reader: SlackMessageReader,
        reservation_channel: str,
    ) -> None:
        self._store = thread_ref_store
        self._reader = reader
        self._reservation_channel = reservation_channel

    def find_issue_thread(self, booking_key: str) -> ThreadLocation | None:
        reservation_channel = self._reservation_channel
        if not reservation_channel:
            logger.warning("reservation_channel_not_configured")
            return None

        # 1단계: DB 조회
        location = self._store.get_by_booking_key(booking_key)
        if location:
            return location

        # 2단계: Slack API 폴백
        thread_ts = self._reader.find_message_by_text(reservation_channel, booking_key)
        if not thread_ts:
            logger.info("thread_not_found_in_slack", booking_key=booking_key)
            return None

        logger.info(
            "thread_found_via_slack_api",
            booking_key=booking_key,
            thread_ts=thread_ts,
        )

        # DB에 캐시 저장
        self.save_thread_reference(
            booking_key=booking_key,
            channel_id=reservation_channel,
            thread_ts=thread_ts,
        )

        return ThreadLocation(channel_id=reservation_channel, thread_ts=thread_ts)

    def save_thread_reference(
        self,
        booking_key: str,
        channel_id: str,
        thread_ts: str,
        root_booking_key: str | None = None,
    ) -> None:
        self._store.save(
            booking_key=booking_key,
            channel_id=channel_id,
            thread_ts=thread_ts,
            root_booking_key=root_booking_key,
        )

    def register_origin_thread(
        self,
        booking_key: str,
        channel_id: str,
        thread_ts: str,
    ) -> None:
        self.save_thread_reference(
            booking_key=booking_key,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )
