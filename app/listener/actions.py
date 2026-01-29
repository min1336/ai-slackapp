from __future__ import annotations

import json

from slack_bolt import App

from app.config import settings
from app.constants import ActionId
from app.services.slack_helper import get_thread_permalink, get_user_real_name
from app.services.spreadsheet import (
    SettlementRow,
    SettlementStatus,
    append_settlement_row,
)
from app.views.blocks import (
    build_approved_message,
    build_registration_modal,
    build_rejected_message,
)


def register_action_handlers(app: App) -> None:
    @app.action(ActionId.OPEN_REGISTRATION_MODAL)
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

        metadata = json.dumps(
            {
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "user_name": user_name,
                "booking_key": booking_key,
                "company_name": company_name,
                "customer_name": customer_name,
            },
            ensure_ascii=False,
        )

        modal = build_registration_modal(
            user_name=user_name,
            booking_key=booking_key,
            company_name=company_name,
            customer_name=customer_name,
            metadata=metadata,
        )

        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal,
        )

    def _handle_settlement_decision(body, client, status: SettlementStatus) -> None:
        user_id = body["user"]["id"]
        channel_id = body.get("channel", {}).get("id", "")
        message_ts = body.get("message", {}).get("ts", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        if user_id not in settings.approver_ids:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=f"⚠️ {status.value} 권한이 없습니다.",
                thread_ts=thread_ts or None,
            )
            return

        approver_name = get_user_real_name(client, user_id)
        thread_url = get_thread_permalink(client, channel_id, thread_ts)

        # 버튼 value에서 데이터 추출
        value = body.get("actions", [{}])[0].get("value", "{}")
        data = json.loads(value)

        # 스프레드시트에 저장
        row = SettlementRow.from_button_data(
            data=data,
            status=status,
            approver_name=approver_name,
            thread_url=thread_url,
        )
        append_settlement_row(row)

        # 메시지 업데이트
        original_blocks = body.get("message", {}).get("blocks", [])
        if status == SettlementStatus.APPROVED:
            new_blocks = build_approved_message(original_blocks, approver_name)
            text = "정산 이슈 승인됨"
        else:
            new_blocks = build_rejected_message(original_blocks, approver_name)
            text = "정산 이슈 반려됨"

        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text=text,
            blocks=new_blocks,
        )

    @app.action(ActionId.SETTLEMENT_APPROVE)
    def handle_settlement_approve(ack, body, client):
        ack()
        _handle_settlement_decision(body, client, SettlementStatus.APPROVED)

    @app.action(ActionId.SETTLEMENT_REJECT)
    def handle_settlement_reject(ack, body, client):
        ack()
        _handle_settlement_decision(body, client, SettlementStatus.REJECTED)

    @app.action(ActionId.SETTLEMENT_EDIT)
    def handle_settlement_edit(ack, body, client):
        ack()

        user_id = body["user"]["id"]
        channel_id = body.get("channel", {}).get("id", "")
        message_ts = body.get("message", {}).get("ts", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        if user_id not in settings.approver_ids:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="⚠️ 편집 권한이 없습니다.",
                thread_ts=thread_ts or None,
            )
            return

        # 버튼 value에서 기존 데이터 추출
        value = body.get("actions", [{}])[0].get("value", "{}")
        data = json.loads(value)

        metadata = json.dumps(
            {
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "message_ts": message_ts,
                "user_name": data.get("user_name", ""),
                "booking_key": data.get("booking_key", ""),
                "company_name": data.get("company_name", ""),
                "customer_name": data.get("customer_name", ""),
            },
            ensure_ascii=False,
        )

        modal = build_registration_modal(
            user_name=data.get("user_name", ""),
            booking_key=data.get("booking_key", ""),
            company_name=data.get("company_name", ""),
            customer_name=data.get("customer_name", ""),
            metadata=metadata,
            settlement_day=data.get("settlement_day", ""),
            issue_type=data.get("issue_type", ""),
            company_sub_name=data.get("company_sub_name", ""),
            settlement_cost=data.get("settlement_cost", ""),
            carmore_cost=data.get("carmore_cost", ""),
            user_refund_cost=data.get("user_refund_cost", ""),
            seller_channel=data.get("seller_channel", ""),
            description=data.get("description", ""),
            is_edit=True,
        )

        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal,
        )
