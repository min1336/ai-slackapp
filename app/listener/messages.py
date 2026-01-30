from __future__ import annotations

import re

from slack_bolt import App

from app.config import config
from app.constants import Command
from app.core import get_logger
from app.services.message_parser import (
    is_transfer_reservation_message,
    parse_settlement_message,
    parse_transfer_reservation_message,
)
from app.services.slack_service import get_parent_message
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

        logger.info(f"정산 파싱 요청: {parsed.booking_key}")

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

    @app.message("")
    def handle_auto_detect_transfer(message, say):
        """특정 채널의 이관 예약 메시지 자동 감지"""
        channel_id = message.get("channel")

        # 이관 예약 채널에서만 처리
        transfer_channel = config.slack_channels.transfer_reservation
        if not transfer_channel:
            logger.warning("이관 예약 채널이 설정되지 않음")
            return

        if channel_id != transfer_channel:
            return

        text = message.get("text", "")
        if not text:
            return

        # 이관 예약 메시지 패턴 확인
        if not is_transfer_reservation_message(text):
            return

        logger.info(f"이관 예약 메시지 감지: {text[:50]}...")
        parsed = parse_transfer_reservation_message(text)

        logger.info(
            f"이관 예약 파싱 완료 - 예약번호: {parsed.booking_key}, "
            f"예약자: {parsed.customer_name}, 업체: {parsed.company_sub_name}, "
            f"원금: {parsed.settlement_cost}, 카모아 부담금: {parsed.carmore_cost}"
        )

        message_ts = message.get("ts")
        try:
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
        except Exception as e:
            logger.error(f"이관 예약 메시지 전송 실패: {e}", exc_info=True)
