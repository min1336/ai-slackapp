from __future__ import annotations

import re

from slack_bolt import App
from slack_sdk.errors import SlackApiError

from app.config import get_app_config
from app.constants import Command
from app.core import get_logger
from app.services.message_parser import (
    is_transfer_reservation_message,
    parse_settlement_message,
    parse_transfer_reservation_message,
)
from app.services.slack_service import get_parent_message, get_thread_url
from app.services.thread_discovery_service import (
    find_issue_thread,
    register_origin_thread,
    save_thread_reference,
)
from app.views.blocks import (
    build_parsing_result_message,
    build_transfer_parsing_result_message,
)

logger = get_logger(__name__)


def register_message_handlers(app: App) -> None:
    @app.message(re.compile(rf"^{re.escape(Command.SETTLEMENT_ISSUE)}$"))
    def handle_read(message, client, say):
        channel_id = message.get("channel")
        thread_ts = message.get("thread_ts")
        message_ts = message.get("ts")

        # 예약 채널에서만 처리 (정산이슈 명령 + 스레드 탐색이 같은 채널)
        reservation_channel = get_app_config().slack_channels.reservation
        if reservation_channel and channel_id != reservation_channel:
            return

        if not thread_ts:
            say(
                "스레드 댓글에서만 사용할 수 있어요!",
                thread_ts=message_ts,
            )
            return

        parent_text = get_parent_message(
            client=client,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )

        if not parent_text:
            say(
                "원본 메시지를 불러올 수 없네요. 다시 시도해주세요!",
                thread_ts=thread_ts,
            )
            return

        parsed = parse_settlement_message(parent_text)

        logger.info("settlement_parse_requested", booking_key=parsed.booking_key)

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

        # 스레드 레퍼런스 등록 (이관 시 이 스레드를 찾을 수 있도록)
        if parsed.booking_key:
            register_origin_thread(
                booking_key=parsed.booking_key,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )

    @app.message("")
    def handle_auto_detect_transfer(message, say, client):
        channel_id = message.get("channel")

        # 이관 예약 채널에서만 처리
        transfer_channel = get_app_config().slack_channels.transfer_reservation
        if not transfer_channel:
            logger.warning("transfer_channel_not_configured")
            return

        if channel_id != transfer_channel:
            return

        text = message.get("text", "")
        if not text:
            return

        # 이관 예약 메시지 패턴 확인
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

        # 정산이슈 스레드 탐색
        thread = find_issue_thread(parsed.booking_key, client)

        if thread:
            # 정산이슈 스레드에 포스트
            transfer_msg_url = get_thread_url(client, channel_id, message_ts)
            try:
                client.chat_postMessage(
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
                # 이관 후 예약번호도 같은 스레드에 매핑 (체인 연결)
                if parsed.new_booking_key:
                    save_thread_reference(
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
                # 폴백: 이관채널 스레드에 포스트

        # 스레드 못 찾음 또는 포스트 실패 → 이관채널 스레드에 폴백
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
