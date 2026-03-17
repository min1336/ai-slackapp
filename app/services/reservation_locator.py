from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from app.core import get_logger
from app.services.message_parser import parse_reservation_message

if TYPE_CHECKING:
    from app.infrastructure.protocols import SlackMessageReader
    from app.models.cancellation import ReservationData
    from app.services.thread_reference_store import ThreadReferenceStore

logger = get_logger(__name__)


class ReservationLocation(NamedTuple):
    """예약 데이터 + 해당 스레드 위치."""

    data: ReservationData
    channel: str
    thread_ts: str


class ReservationLocator:
    """예약 스레드를 검색하고 예약 데이터를 반환하는 컴포넌트.

    DB 캐시 → Slack conversations.history 폴백 순서로 검색한다.
    """

    def __init__(
        self,
        reader: SlackMessageReader,
        reservation_channels: list[str],
        thread_ref_store: ThreadReferenceStore | None = None,
    ) -> None:
        self._reader = reader
        self._reservation_channels = reservation_channels
        self._thread_ref_store = thread_ref_store

    def find(self, booking_key: str, phone: str = "") -> ReservationLocation | None:
        """예약번호로 검색 → 실패 시 전화번호 fallback."""
        location = self._search(booking_key)
        if location:
            return location
        if phone:
            logger.info(
                "reservation_search_fallback_phone",
                booking_key=booking_key,
            )
            return self._search(phone)
        return None

    def _search(self, search_text: str) -> ReservationLocation | None:
        """DB 캐시 → conversations.history 폴백으로 예약 스레드를 찾는다."""
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

        for channel in self._reservation_channels:
            found_ts = self._reader.find_message_by_text(
                channel, search_text, max_pages=50
            )
            if not found_ts:
                continue
            loc = self._build_location(search_text, channel, found_ts)
            if loc:
                return loc
        return None

    def _build_location(
        self, search_text: str, channel: str, found_ts: str
    ) -> ReservationLocation | None:
        """채널+ts에서 parent 메시지를 읽어 ReservationLocation을 생성한다."""
        parent_text = self._reader.get_parent_message(channel, found_ts)
        if not parent_text:
            return None
        if self._thread_ref_store:
            self._thread_ref_store.save(search_text, channel, found_ts)
        return ReservationLocation(
            data=parse_reservation_message(parent_text),
            channel=channel,
            thread_ts=found_ts,
        )
