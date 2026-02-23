from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from app.core import get_logger
from app.infrastructure.database import ThreadReferenceRepository
from app.models import ThreadLocation

if TYPE_CHECKING:
    from app.infrastructure.database import SessionFactory

logger = get_logger(__name__)


class ThreadReferenceStore:
    def __init__(self, get_session: SessionFactory) -> None:
        self._get_session = get_session

    def get_by_booking_key(self, booking_key: str) -> ThreadLocation | None:
        try:
            return self._get_ref(booking_key)
        except SQLAlchemyError:
            logger.exception("thread_ref_db_lookup_failed", booking_key=booking_key)
        return None

    def get_root_booking_key(self, booking_key: str) -> str | None:
        """booking_key의 root_booking_key를 반환한다."""
        try:
            with self._get_session() as session:
                ref = ThreadReferenceRepository(session).get_by_booking_key(booking_key)
                return ref.root_booking_key if ref else None
        except SQLAlchemyError:
            logger.exception("thread_ref_root_lookup_failed", booking_key=booking_key)
        return None

    def get_chain_booking_keys(self, root_booking_key: str) -> list[str]:
        """root_booking_key에 속한 모든 체인 멤버의 booking_key 목록."""
        try:
            with self._get_session() as session:
                refs = ThreadReferenceRepository(session).list_by_root_booking_key(
                    root_booking_key
                )
                return [ref.booking_key for ref in refs]
        except SQLAlchemyError:
            logger.exception(
                "thread_ref_chain_lookup_failed",
                root_booking_key=root_booking_key,
            )
        return []

    def save(
        self,
        booking_key: str,
        channel_id: str,
        thread_ts: str,
        root_booking_key: str | None = None,
    ) -> None:
        try:
            self._save_ref(booking_key, channel_id, thread_ts, root_booking_key)
        except SQLAlchemyError:
            logger.exception("thread_ref_save_failed", booking_key=booking_key)

    def _get_ref(self, booking_key: str) -> ThreadLocation | None:
        with self._get_session() as session:
            ref = ThreadReferenceRepository(session).get_by_booking_key(booking_key)
            if ref:
                logger.info(
                    "thread_ref_found_in_db",
                    booking_key=booking_key,
                    thread_ts=ref.thread_ts,
                )
                return ThreadLocation(
                    channel_id=ref.channel_id, thread_ts=ref.thread_ts
                )
        return None

    def _save_ref(
        self,
        booking_key: str,
        channel_id: str,
        thread_ts: str,
        root_booking_key: str | None = None,
    ) -> None:
        with self._get_session() as session:
            ThreadReferenceRepository(session).save(
                booking_key=booking_key,
                channel_id=channel_id,
                thread_ts=thread_ts,
                root_booking_key=root_booking_key,
            )
