from __future__ import annotations

import time
from collections.abc import Iterable
from typing import TYPE_CHECKING

from slack_sdk.errors import SlackApiError

from app.core import get_logger
from app.models import ThreadLocation
from app.services.message_parser import parse_settlement_message

if TYPE_CHECKING:
    from app.infrastructure.protocols import SlackMessageReader
    from app.services.thread_reference_store import ThreadReferenceStore

logger = get_logger(__name__)


class ThreadDiscoveryService:
    def __init__(
        self,
        thread_ref_store: ThreadReferenceStore,
        reader: SlackMessageReader,
        reservation_channels: list[str],
    ) -> None:
        self._store = thread_ref_store
        self._reader = reader
        self._reservation_channels = reservation_channels

    def find_issue_thread(
        self,
        booking_key: str,
        *,
        fallback_booking_keys: Iterable[str] = (),
    ) -> ThreadLocation | None:
        if not self._reservation_channels:
            logger.warning("reservation_channels_not_configured")
            return None

        candidate_keys = self._candidate_booking_keys(
            booking_key,
            fallback_booking_keys,
        )

        # 1단계: DB 조회
        location = self._find_issue_thread_in_db(candidate_keys)
        if location:
            return location

        # 2단계: Slack API 폴백 — 채널 순서대로 탐색, 첫 발견 즉시 반환
        for ch in self._reservation_channels:
            location = self._find_issue_thread_in_slack(
                reservation_channel=ch,
                target_booking_key=booking_key,
                candidate_keys=candidate_keys,
            )
            if location:
                return location

        logger.info(
            "thread_not_found_in_slack",
            booking_key=booking_key,
            fallback_booking_keys=list(candidate_keys[1:]),
        )
        return None

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

    def backfill_reservation_threads(
        self, days: int | None = 7, *, max_pages: int = 10
    ) -> int:
        """예약 채널 목록을 순차 스캔하여 ThreadReference DB를 채운다.

        Args:
            days: 스캔할 기간. None이면 전체 히스토리.
            max_pages: 채널당 최대 페이지 수 (1페이지 = 200메시지).
        """
        if not self._reservation_channels:
            logger.warning("backfill_skipped_no_channel")
            return 0

        oldest = 0.0 if days is None else time.time() - (days * 86400)
        saved = 0
        scanned = 0

        for ch in self._reservation_channels:
            try:
                messages = self._reader.list_channel_messages(
                    ch, oldest=oldest, max_pages=max_pages
                )
                for msg in messages:
                    scanned += 1
                    try:
                        text = msg.get("text", "")
                        parsed = parse_settlement_message(text)
                        booking_key = parsed.booking_key.strip()
                        if not booking_key:
                            continue

                        message_ts = msg.get("ts", "")
                        if not message_ts:
                            continue

                        if self._store.get_by_booking_key(booking_key):
                            continue

                        self._store.save(
                            booking_key=booking_key,
                            channel_id=ch,
                            thread_ts=message_ts,
                        )
                        saved += 1
                    except SlackApiError:
                        raise
                    except Exception:
                        logger.exception("backfill_message_error", ts=msg.get("ts"))
            except SlackApiError:
                logger.exception("backfill_channel_read_failed", channel_id=ch)
                continue  # 한 채널 실패 시 다음 채널 계속

        logger.info("backfill_completed", saved=saved, scanned=scanned)
        return saved

    def save_transfer_thread_reference(
        self,
        *,
        previous_booking_key: str,
        new_booking_key: str,
        channel_id: str,
        thread_ts: str,
    ) -> None:
        root_booking_key = (
            self._store.get_root_booking_key(previous_booking_key)
            or previous_booking_key
        )
        self.save_thread_reference(
            booking_key=new_booking_key,
            channel_id=channel_id,
            thread_ts=thread_ts,
            root_booking_key=root_booking_key,
        )

    def _candidate_booking_keys(
        self,
        booking_key: str,
        fallback_booking_keys: Iterable[str],
    ) -> tuple[str, ...]:
        candidates: list[str] = []
        for key in (booking_key, *fallback_booking_keys):
            normalized = key.strip()
            if normalized and normalized not in candidates:
                candidates.append(normalized)
        return tuple(candidates)

    def _find_issue_thread_in_db(
        self,
        candidate_keys: tuple[str, ...],
    ) -> ThreadLocation | None:
        for key in candidate_keys:
            location = self._store.get_by_booking_key(key)
            if location:
                return location
        return None

    def _find_issue_thread_in_slack(
        self,
        *,
        reservation_channel: str,
        target_booking_key: str,
        candidate_keys: tuple[str, ...],
    ) -> ThreadLocation | None:
        for key in candidate_keys:
            thread_ts = self._find_thread_ts_by_booking_key(
                reservation_channel=reservation_channel,
                booking_key=key,
            )
            if not thread_ts:
                continue

            logger.info(
                "thread_found_via_slack_api",
                booking_key=key,
                thread_ts=thread_ts,
            )
            self._save_discovered_reference(
                target_booking_key=target_booking_key,
                matched_booking_key=key,
                channel_id=reservation_channel,
                thread_ts=thread_ts,
            )
            return ThreadLocation(channel_id=reservation_channel, thread_ts=thread_ts)
        return None

    def _save_discovered_reference(
        self,
        *,
        target_booking_key: str,
        matched_booking_key: str,
        channel_id: str,
        thread_ts: str,
    ) -> None:
        root_booking_key = self._store.get_root_booking_key(target_booking_key)
        if not root_booking_key and matched_booking_key != target_booking_key:
            root_booking_key = self._store.get_root_booking_key(matched_booking_key)

        self.save_thread_reference(
            booking_key=target_booking_key,
            channel_id=channel_id,
            thread_ts=thread_ts,
            root_booking_key=root_booking_key,
        )

    def _find_thread_ts_by_booking_key(
        self,
        *,
        reservation_channel: str,
        booking_key: str,
    ) -> str | None:
        for query in self._search_queries_for_booking_key(booking_key):
            thread_ts = self._reader.find_message_by_text(
                reservation_channel,
                query,
                max_pages=50,
            )
            if thread_ts:
                return thread_ts
        return None

    @staticmethod
    def _search_queries_for_booking_key(booking_key: str) -> tuple[str, ...]:
        return (
            f"예약번호 : {booking_key}",
            f"예약번호:{booking_key}",
            booking_key,
        )
