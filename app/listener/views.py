from __future__ import annotations

import json

from slack_bolt import App


def register_view_handlers(app: App) -> None:
    @app.view("registration_submit")
    def handle_registration_submit(ack, body, client, view):
        ack()

        # private_metadata에서 정보 추출
        metadata = json.loads(view.get("private_metadata", "{}"))
        channel_id = metadata.get("channel_id", "")
        thread_ts = metadata.get("thread_ts", "")
        user_name = metadata.get("user_name", "")
        booking_key = metadata.get("booking_key", "")
        company_name = metadata.get("company_name", "")
        customer_name = metadata.get("customer_name", "")

        # 입력 필드 값 추출
        values = view.get("state", {}).get("values", {})
        settlement_day = values.get("settlement_standard_day_block", {}).get("settlement_standard_day_input", {}).get(
            "selected_date", "")
        company_sub_name = values.get("company_sub_name_block", {}).get("company_sub_name_input", {}).get("value",
                                                                                                          "") or ""
        settlement_cost = values.get("settlement_standard_cost_block", {}).get("settlement_standard_cost_input",
                                                                               {}).get("value", "")
        carmore_cost = values.get("carmore_cost_block", {}).get("carmore_cost_input", {}).get("value", "") or ""
        user_refund_cost = values.get("user_refund_cost_block", {}).get("user_refund_cost_input", {}).get("value",
                                                                                                          "") or ""
        description = values.get("description_block", {}).get("description_input", {}).get("value", "") or ""

        # 스레드에 승인 요청 메시지 전송
        # 주의: section.fields는 최대 10개까지만 허용
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📝 정산 이슈를 등록하시겠습니까?"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*이슈 등록자*"},
                    {"type": "plain_text", "text": user_name},
                    {"type": "mrkdwn", "text": "*예약번호*"},
                    {"type": "plain_text", "text": booking_key or "(없음)"},
                    {"type": "mrkdwn", "text": "*업체명*"},
                    {"type": "plain_text", "text": company_name or "(없음)"},
                    {"type": "mrkdwn", "text": "*고객명*"},
                    {"type": "plain_text", "text": customer_name or "(없음)"},
                    {"type": "mrkdwn", "text": "*정산기준일*"},
                    {"type": "plain_text", "text": settlement_day or "(없음)"},
                ],
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*정산기준금액*"},
                    {"type": "plain_text", "text": settlement_cost or "(없음)"},
                    {"type": "mrkdwn", "text": "*업체명2(대신배차)*"},
                    {"type": "plain_text", "text": company_sub_name or "(없음)"},
                    {"type": "mrkdwn", "text": "*카모아 부담비용*"},
                    {"type": "plain_text", "text": carmore_cost or "(없음)"},
                    {"type": "mrkdwn", "text": "*고객 환불 금액*"},
                    {"type": "plain_text", "text": user_refund_cost or "(없음)"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*정산 이슈 내용*\n{description or '(없음)'}",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "승인"},
                        "style": "primary",
                        "action_id": "settlement_approve",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "반려"},
                        "style": "danger",
                        "action_id": "settlement_reject",
                    },
                ],
            },
        ]

        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts if thread_ts else None,
            text="정산 이슈 등록 요청",
            blocks=blocks,
        )
