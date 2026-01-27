from __future__ import annotations

import re

from slack_bolt import App

from app.services.message_parser import parse_settlement_message
from app.services.slack_helper import get_thread_parent_message


def register_message_handlers(app: App) -> None:

    @app.message(re.compile(r"^!읽기"))
    def handle_read(message, client, say):
        channel_id = message.get("channel")
        thread_ts = message.get("thread_ts")
        message_ts = message.get("ts")

        if not thread_ts:
            say("스레드에서 `!읽기`를 입력해주세요.", thread_ts=message_ts)
            return

        parent_text = get_thread_parent_message(
            client=client,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )

        if not parent_text:
            say("원문을 읽을 수 없습니다.", thread_ts=thread_ts)
            return

        parsed = parse_settlement_message(parent_text)

        say(
            f"*파싱 결과*\n"
            f"• 예약번호: {parsed.booking_key or '(없음)'}\n"
            f"• 업체명: {parsed.company_name or '(없음)'}\n"
            f"• 고객명: {parsed.customer_name or '(없음)'}",
            thread_ts=thread_ts,
        )
