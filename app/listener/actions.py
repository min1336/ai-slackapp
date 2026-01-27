from __future__ import annotations

import json

from slack_bolt import App


def register_action_handlers(app: App) -> None:

    @app.action("open_registration_modal")
    def handle_open_registration_modal(ack, body, client):
        ack()

        value = body.get("actions", [{}])[0].get("value", "{}")
        parsed = json.loads(value)

        booking_key = parsed.get("booking_key", "")
        company_name = parsed.get("company_name", "")
        customer_name = parsed.get("customer_name", "")

        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "registration_submit",
                "title": {"type": "plain_text", "text": "정산 이슈 등록"},
                "submit": {"type": "plain_text", "text": "등록"},
                "close": {"type": "plain_text", "text": "취소"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "booking_key_block",
                        "label": {"type": "plain_text", "text": "예약번호"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "booking_key_input",
                            "initial_value": booking_key,
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "company_name_block",
                        "label": {"type": "plain_text", "text": "업체명"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "company_name_input",
                            "initial_value": company_name,
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "customer_name_block",
                        "label": {"type": "plain_text", "text": "고객명"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "customer_name_input",
                            "initial_value": customer_name,
                        },
                    },
                ],
            },
        )
