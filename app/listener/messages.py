from __future__ import annotations

import json
import re

from slack_bolt import App

from app.constants import Command
from app.services.message_parser import parse_settlement_message
from app.services.slack_helper import get_thread_parent_message
from app.views.blocks import build_parsing_result_message


def register_message_handlers(app: App) -> None:
    @app.message(re.compile(rf"^{re.escape(Command.SETTLEMENT_ISSUE)}$"))
    def handle_read(message, client, say):
        channel_id = message.get("channel")
        thread_ts = message.get("thread_ts")
        message_ts = message.get("ts")

        if not thread_ts:
            say(
                f"스레드에서 `{Command.SETTLEMENT_ISSUE}`를 입력해주세요.",
                thread_ts=message_ts,
            )
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
        button_value = json.dumps(parsed.model_dump(), ensure_ascii=False)

        say(
            text="파싱 결과",
            blocks=build_parsing_result_message(
                booking_key=parsed.booking_key,
                company_name=parsed.company_name,
                customer_name=parsed.customer_name,
                button_value=button_value,
            ),
            thread_ts=thread_ts,
        )
