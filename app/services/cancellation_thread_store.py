from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from app.core import get_logger
from app.infrastructure.database import CancellationThreadRefRepository
from app.models import ThreadLocation

if TYPE_CHECKING:
    from app.infrastructure.database import SessionFactory

logger = get_logger(__name__)


class CancellationThreadStore:
    """결항 교차검증용 스레드 위치 캐시. ThreadReferenceStore와 동일 패턴."""

    def __init__(self, get_session: SessionFactory) -> None:
        self._get_session = get_session

    def get_by_booking_key(self, booking_key: str) -> ThreadLocation | None:
        try:
            with self._get_session() as session:
                ref = CancellationThreadRefRepository(session).get_by_booking_key(
                    booking_key
                )
                if ref:
                    return ThreadLocation(
                        channel_id=ref.channel_id, thread_ts=ref.thread_ts
                    )
        except SQLAlchemyError:
            logger.exception("cancel_thread_ref_lookup_failed", booking_key=booking_key)
        return None

    def save(self, booking_key: str, channel_id: str, thread_ts: str) -> None:
        try:
            with self._get_session() as session:
                CancellationThreadRefRepository(session).save(
                    booking_key, channel_id, thread_ts
                )
        except SQLAlchemyError:
            logger.exception("cancel_thread_ref_save_failed", booking_key=booking_key)
