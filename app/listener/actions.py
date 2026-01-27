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

        user_id = body["user"]["id"]
        user_info = client.users_info(user=user_id)
        user_name = user_info["user"]["real_name"]

        channel_id = body.get("channel", {}).get("id", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        metadata = json.dumps({
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "user_name": user_name,
            "booking_key": booking_key,
            "company_name": company_name,
            "customer_name": customer_name,
        }, ensure_ascii=False)

        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "registration_submit",
                "private_metadata": metadata,
                "title": {"type": "plain_text", "text": "정산 이슈 등록"},
                "submit": {"type": "plain_text", "text": "등록"},
                "close": {"type": "plain_text", "text": "취소"},
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "📋 예약 정보"},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": "*정산 이슈 등록자*"},
                            {"type": "plain_text", "text": user_name},
                            {"type": "mrkdwn", "text": "*예약번호*"},
                            {"type": "plain_text", "text": booking_key or "(없음)"},
                            {"type": "mrkdwn", "text": "*업체명*"},
                            {"type": "plain_text", "text": company_name or "(없음)"},
                            {"type": "mrkdwn", "text": "*고객명*"},
                            {"type": "plain_text", "text": customer_name or "(없음)"},
                        ],
                    },
                    {"type": "divider"},
                    {
                        "type": "input",
                        "block_id": "settlement_standard_day_block",
                        "label": {"type": "plain_text", "text": "정산기준일"},
                        "element": {
                            "type": "datepicker",
                            "action_id": "settlement_standard_day_input",
                            "placeholder": {"type": "plain_text", "text": "날짜 선택"},
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "company_sub_name_block",
                        "label": {"type": "plain_text", "text": "업체명2(대신배차)"},
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "company_sub_name_input",
                            "initial_value": "",
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "settlement_standard_cost_block",
                        "label": {"type": "plain_text", "text": "정산기준금액"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "settlement_standard_cost_input",
                            "initial_value": "",
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "carmore_cost_block",
                        "label": {"type": "plain_text", "text": "카모아 부담비용"},
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "carmore_cost_input",
                            "initial_value": "",
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "user_refund_cost_block",
                        "label": {"type": "plain_text", "text": "고객 환불 금액"},
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "user_refund_cost_input",
                            "initial_value": "",
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "description_block",
                        "label": {"type": "plain_text", "text": "정산 이슈 내용"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "description_input",
                            "multiline": True,
                            "initial_value": "",
                        },
                    },
                ],
            },
        )
