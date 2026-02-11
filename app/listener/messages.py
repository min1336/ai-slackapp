from __future__ import annotations

import re
from typing import TYPE_CHECKING

from slack_bolt import App
from slack_sdk.errors import SlackApiError

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


def register_message_handlers(app: App, container: ServiceContainer) -> None:
    discovery = container.discovery
    reader = container.reader
    writer = container.writer
    reservation_channel = container.reservation_channel
    transfer_channel = container.transfer_channel

    @app.message(re.compile(rf"^{re.escape(Command.SETTLEMENT_ISSUE)}$"))
    def handle_read(message, say):
        channel_id = message.get("channel")
        thread_ts = message.get("thread_ts")
        message_ts = message.get("ts")

        if reservation_channel and channel_id != reservation_channel:
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
    def handle_auto_detect_transfer(message, say):
        channel_id = message.get("channel")

        if not transfer_channel:
            logger.warning("transfer_channel_not_configured")
            return

        if channel_id != transfer_channel:
            return

        text = message.get("text", "")
        if not text:
            return

        if not is_transfer_reservation_message(text):
            return

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

        message_ts = message.get("ts")

        thread = discovery.find_issue_thread(parsed.booking_key)

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
                    discovery.save_thread_reference(
                        booking_key=parsed.new_booking_key,
                        channel_id=thread.channel_id,
                        thread_ts=thread.thread_ts,
                        root_booking_key=parsed.booking_key,
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
