from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import get_app_config
from app.core import get_logger
from app.infrastructure.database import (
    ThreadReferenceRepository,
    get_session,
)
from app.models import ThreadLocation
from app.services.slack_service import find_message_by_text

if TYPE_CHECKING:
    from collections.abc import Generator
    from contextlib import contextmanager

    from slack_sdk import WebClient

    from app.infrastructure.database.connection import SessionWithAfterCommit

    type SessionFactory = contextmanager[Generator[SessionWithAfterCommit, None, None]]

logger = get_logger(__name__)


def find_issue_thread(
    booking_key: str,
    client: WebClient,
    *,
    session_factory: SessionFactory | None = None,
) -> ThreadLocation | None:
    config = get_app_config()
    reservation_channel = config.slack_channels.reservation
    if not reservation_channel:
        logger.warning("reservation_channel_not_configured")
        return None

    _session = session_factory or get_session

    # 1단계: DB 조회
    try:
        with _session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key(booking_key)
            if ref:
                logger.info(
                    "thread_ref_found_in_db",
                    booking_key=booking_key,
                    thread_ts=ref.thread_ts,
                )
                return ThreadLocation(
                    channel_id=ref.channel_id,
                    thread_ts=ref.thread_ts,
                )
    except Exception:
        logger.exception("thread_ref_db_lookup_failed", booking_key=booking_key)

    # 2단계: Slack API 폴백
    thread_ts = find_message_by_text(client, reservation_channel, booking_key)
    if not thread_ts:
        logger.info("thread_not_found_in_slack", booking_key=booking_key)
        return None

    logger.info(
        "thread_found_via_slack_api",
        booking_key=booking_key,
        thread_ts=thread_ts,
    )

    # DB에 캐시 저장
    save_thread_reference(
        booking_key=booking_key,
        channel_id=reservation_channel,
        thread_ts=thread_ts,
        session_factory=session_factory,
    )

    return ThreadLocation(channel_id=reservation_channel, thread_ts=thread_ts)


def save_thread_reference(
    booking_key: str,
    channel_id: str,
    thread_ts: str,
    root_booking_key: str | None = None,
    *,
    session_factory: SessionFactory | None = None,
) -> None:
    _session = session_factory or get_session
    try:
        with _session() as session:
            repo = ThreadReferenceRepository(session)
            repo.save(
                booking_key=booking_key,
                channel_id=channel_id,
                thread_ts=thread_ts,
                root_booking_key=root_booking_key,
            )
    except Exception:
        logger.exception(
            "thread_ref_save_failed",
            booking_key=booking_key,
        )


def register_origin_thread(
    booking_key: str,
    channel_id: str,
    thread_ts: str,
    *,
    session_factory: SessionFactory | None = None,
) -> None:
    save_thread_reference(
        booking_key=booking_key,
        channel_id=channel_id,
        thread_ts=thread_ts,
        session_factory=session_factory,
    )
