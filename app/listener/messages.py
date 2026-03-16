from __future__ import annotations

import re
from typing import TYPE_CHECKING

from slack_bolt import App
from slack_sdk.errors import SlackApiError

from app.config import get_env_config
from app.constants import Command
from app.core import get_logger
from app.services.message_parser import (
    is_transfer_reservation_message,
    parse_settlement_message,
    parse_transfer_reservation_message,
)
from app.views.blocks import (
    build_parsing_result_message,
    build_transfer_parsing_result_message,
)

if TYPE_CHECKING:
    from app.container import ServiceContainer

logger = get_logger(__name__)


def _is_bot_message(message: dict) -> bool:
    return bool(message.get("bot_id")) or message.get("subtype") == "bot_message"


def _should_process_message(message: dict) -> bool:
    if get_env_config().is_dev:
        return True
    return _is_bot_message(message)


def _route_channel_message(
    *,
    message: dict,
    channel_id: str,
    transfer_channel: str,
    reservation_channels: list[str],
) -> str:
    """메시지 라우팅 결정: 'transfer', 'reservation', 'ignore'."""
    is_transfer_ch = bool(transfer_channel and channel_id == transfer_channel)
    is_reservation_ch = channel_id in reservation_channels

    if is_transfer_ch and _should_process_message(message):
        text = message.get("text", "")
        if text and is_transfer_reservation_message(text):
            return "transfer"

    if is_reservation_ch:
        return "reservation"

    return "ignore"


def _handle_transfer_message(message, say, *, discovery, reader, writer) -> None:
    """이관 메시지 처리: 파싱 → 기존 스레드 탐색 → 포스트."""
    text = message.get("text", "")
    channel_id = message.get("channel")
    message_ts = message.get("ts")

    logger.info("transfer_message_detected", text_preview=text[:50])
    parsed = parse_transfer_reservation_message(text)

    logger.info(
        "transfer_parsed",
        booking_key=parsed.booking_key,
        customer_name=parsed.customer_name,
        company_sub_name=parsed.company_sub_name,
        settlement_cost=parsed.settlement_cost,
        carmore_cost=parsed.carmore_cost,
    )

    thread = discovery.find_issue_thread(
        parsed.booking_key,
        fallback_booking_keys=(parsed.new_booking_key,),
    )

    if thread:
        transfer_msg_url = reader.get_thread_url(channel_id, message_ts)
        try:
            writer.post_message(
                channel=thread.channel_id,
                thread_ts=thread.thread_ts,
                text="이관 예약 정보를 확인해주세요 🚗",
                blocks=build_transfer_parsing_result_message(
                    booking_key=parsed.booking_key,
                    customer_name=parsed.customer_name,
                    company_name=parsed.company_name,
                    company_sub_name=parsed.company_sub_name,
                    settlement_cost=parsed.settlement_cost,
                    carmore_cost=parsed.carmore_cost,
                    button_value=parsed.model_dump_json(),
                    transfer_message_url=transfer_msg_url,
                ),
            )
            if parsed.new_booking_key:
                discovery.save_transfer_thread_reference(
                    previous_booking_key=parsed.booking_key,
                    new_booking_key=parsed.new_booking_key,
                    channel_id=thread.channel_id,
                    thread_ts=thread.thread_ts,
                )
            return
        except SlackApiError:
            logger.exception(
                "issue_thread_post_failed",
                booking_key=parsed.booking_key,
                thread_ts=thread.thread_ts,
            )

    say(
        text="이관 예약 정보를 확인해주세요 🚗",
        blocks=build_transfer_parsing_result_message(
            booking_key=parsed.booking_key,
            customer_name=parsed.customer_name,
            company_name=parsed.company_name,
            company_sub_name=parsed.company_sub_name,
            settlement_cost=parsed.settlement_cost,
            carmore_cost=parsed.carmore_cost,
            button_value=parsed.model_dump_json(),
        ),
        thread_ts=message_ts,
    )


def _cache_reservation_origin_thread(message: dict, discovery) -> None:
    channel_id = message.get("channel")
    message_ts = message.get("ts")
    text = message.get("text", "")
    # 부모 메시지(원문)만 캐시: 스레드 댓글은 제외
    if not channel_id or not message_ts or not text or message.get("thread_ts"):
        return

    parsed = parse_settlement_message(text)
    booking_key = parsed.booking_key.strip()
    if not booking_key:
        logger.debug("reservation_cache_skip_no_booking_key", text_preview=text[:80])
        return

    discovery.register_origin_thread(
        booking_key=booking_key,
        channel_id=channel_id,
        thread_ts=message_ts,
    )
    logger.info(
        "reservation_thread_cached",
        booking_key=booking_key,
        thread_ts=message_ts,
    )


def _cache_cancellation_thread_ref(message: dict, cancel_thread_store) -> None:
    """예약 메시지 도착 시 결항 교차검증용 스레드 위치를 캐시한다."""
    if cancel_thread_store is None:
        return
    channel_id = message.get("channel")
    message_ts = message.get("ts")
    text = message.get("text", "")
    if not channel_id or not message_ts or not text or message.get("thread_ts"):
        return

    parsed = parse_settlement_message(text)
    booking_key = parsed.booking_key.strip()
    if not booking_key:
        return

    cancel_thread_store.save(booking_key, channel_id, message_ts)


_cancellation_poll_running = False
_RETRY_DELAYS = (30, 60)  # 재시도 대기(초): 30s, 60s


def _trigger_cancellation_poll(service, channel_id: str) -> None:
    """백그라운드 스레드에서 결항 이미지 폴링을 실행한다.

    첫 시도 후 미처리 건이 남으면 Drive 폴더 생성 지연을 고려해
    최대 2회 재시도한다 (30초, 60초 간격).
    """
    global _cancellation_poll_running  # noqa: PLW0603
    from threading import Thread
    from time import sleep

    if _cancellation_poll_running:
        logger.info("cancellation_poll_already_running", channel=channel_id)
        return

    _cancellation_poll_running = True

    def _run() -> None:
        global _cancellation_poll_running  # noqa: PLW0603
        sleep(5)  # Jotform→Sheet/Drive 동기화 대기
        try:
            remaining = service.poll_and_upload()
            for attempt, delay in enumerate(_RETRY_DELAYS, 1):
                if remaining <= 0:
                    break
                logger.info(
                    "cancellation_poll_retry_scheduled",
                    attempt=attempt,
                    remaining=remaining,
                    delay=delay,
                    channel=channel_id,
                )
                sleep(delay)
                remaining = service.poll_and_upload()
        except Exception:
            logger.exception("cancellation_poll_triggered_failed", channel=channel_id)
        finally:
            _cancellation_poll_running = False

    Thread(target=_run, daemon=True).start()


def register_message_handlers(app: App, container: ServiceContainer) -> None:
    discovery = container.discovery
    reader = container.reader
    writer = container.writer
    reservation_channels = container.reservation_channels
    transfer_channel = container.transfer_channel
    cancellation_channel = container.cancellation_target_channel
    cancellation_service = container.cancellation_image
    cancel_thread_store = container.cancel_thread_store

    _watched_channels: set[str] = set()
    if transfer_channel:
        _watched_channels.add(transfer_channel)
    if reservation_channels:
        _watched_channels.update(reservation_channels)
    if cancellation_channel:
        _watched_channels.add(cancellation_channel)

    @app.message(re.compile(rf"^{re.escape(Command.SETTLEMENT_ISSUE)}$"))
    def handle_read(message, say):
        channel_id = message.get("channel")
        thread_ts = message.get("thread_ts")
        message_ts = message.get("ts")

        if reservation_channels and channel_id not in reservation_channels:
            return

        if not thread_ts:
            say(
                "스레드 댓글에서만 사용할 수 있어요!",
                thread_ts=message_ts,
            )
            return

        parent_text = reader.get_parent_message(channel_id, thread_ts)

        if not parent_text:
            say(
                "원본 메시지를 불러올 수 없네요. 다시 시도해주세요!",
                thread_ts=thread_ts,
            )
            return

        parsed = parse_settlement_message(parent_text)

        logger.info(
            "settlement_parse_requested",
            booking_key=parsed.booking_key,
        )

        say(
            text="예약 정보를 확인해주세요 📋",
            blocks=build_parsing_result_message(
                booking_key=parsed.booking_key,
                company_name=parsed.company_name,
                customer_name=parsed.customer_name,
                button_value=parsed.model_dump_json(),
            ),
            thread_ts=thread_ts,
        )

        if parsed.booking_key:
            discovery.register_origin_thread(
                booking_key=parsed.booking_key,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )

    @app.message("")
    def handle_watched_channel_message(message, say):
        channel_id = message.get("channel")
        if not channel_id or channel_id not in _watched_channels:
            return

        logger.debug(
            "watched_channel_message",
            channel=channel_id,
            ts=message.get("ts"),
            subtype=message.get("subtype"),
        )

        route = _route_channel_message(
            message=message,
            channel_id=channel_id,
            transfer_channel=transfer_channel,
            reservation_channels=reservation_channels,
        )

        if route == "transfer":
            _handle_transfer_message(
                message,
                say,
                discovery=discovery,
                reader=reader,
                writer=writer,
            )
        elif route == "reservation" and _should_process_message(message):
            _cache_reservation_origin_thread(message, discovery)
            _cache_cancellation_thread_ref(message, cancel_thread_store)

        if (
            cancellation_service
            and cancellation_channel
            and channel_id == cancellation_channel
            and not message.get("thread_ts")  # 부모 메시지만
        ):
            logger.info(
                "cancellation_message_detected",
                channel=channel_id,
                ts=message.get("ts"),
            )
            _trigger_cancellation_poll(cancellation_service, channel_id)

    @app.event("message")
    def handle_message_subtypes(event):
        """@app.message()가 잡지 못하는 subtype 이벤트 처리."""
        channel_id = event.get("channel")
        subtype = event.get("subtype")

        logger.debug(
            "message_event_subtype",
            channel=channel_id,
            subtype=subtype,
            bot_id=event.get("bot_id"),
            text_preview=event.get("text", "")[:50],
        )

        # cancellation 채널의 subtype 메시지도 트리거
        if (
            cancellation_service
            and cancellation_channel
            and channel_id == cancellation_channel
            and subtype not in ("message_changed", "message_deleted")
            and not event.get("thread_ts")
        ):
            logger.info(
                "cancellation_message_detected_via_event",
                channel=channel_id,
                subtype=subtype,
            )
            _trigger_cancellation_poll(cancellation_service, channel_id)
