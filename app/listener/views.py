from __future__ import annotations

import json

from slack_bolt import App

from app.constants import BlockId, ActionId
from app.views.blocks import build_approval_request_message


def register_view_handlers(app: App) -> None:
    @app.view(ActionId.REGISTRATION_SUBMIT)
    def handle_registration_submit(ack, body, client, view):
        ack()

        # private_metadata에서 정보 추출
        metadata = json.loads(view.get("private_metadata", "{}"))
        channel_id = metadata.get("channel_id", "")
        thread_ts = metadata.get("thread_ts", "")
        message_ts = metadata.get("message_ts", "")  # 편집 모드일 때만 있음
        user_name = metadata.get("user_name", "")
        booking_key = metadata.get("booking_key", "")
        company_name = metadata.get("company_name", "")
        customer_name = metadata.get("customer_name", "")

        # 입력 필드 값 추출
        values = view.get("state", {}).get("values", {})
        settlement_day = (
            values.get(BlockId.SETTLEMENT_DAY_BLOCK, {})
            .get(ActionId.SETTLEMENT_DAY_INPUT, {})
            .get("selected_date", "")
        )
        company_sub_name = (
            values.get(BlockId.COMPANY_SUB_NAME_BLOCK, {})
            .get(ActionId.COMPANY_SUB_NAME_INPUT, {})
            .get("value", "")
            or ""
        )
        settlement_cost = (
            values.get(BlockId.SETTLEMENT_COST_BLOCK, {})
            .get(ActionId.SETTLEMENT_COST_INPUT, {})
            .get("value", "")
        )
        carmore_cost = (
            values.get(BlockId.CARMORE_COST_BLOCK, {})
            .get(ActionId.CARMORE_COST_INPUT, {})
            .get("value", "")
            or ""
        )
        user_refund_cost = (
            values.get(BlockId.USER_REFUND_COST_BLOCK, {})
            .get(ActionId.USER_REFUND_COST_INPUT, {})
            .get("value", "")
            or ""
        )

        # static_select에서 값 추출
        issue_type_selected = (
            values.get(BlockId.ISSUE_TYPE_BLOCK, {})
            .get(ActionId.ISSUE_TYPE_INPUT, {})
            .get("selected_option", {})
        )
        issue_type = issue_type_selected.get("text", {}).get("text", "") or ""

        seller_channel_selected = (
            values.get(BlockId.SELLER_CHANNEL_BLOCK, {})
            .get(ActionId.SELLER_CHANNEL_INPUT, {})
            .get("selected_option", {})
        )
        seller_channel = seller_channel_selected.get("text", {}).get("text", "") or ""

        description_selected = (
            values.get(BlockId.DESCRIPTION_BLOCK, {})
            .get(ActionId.DESCRIPTION_INPUT, {})
            .get("selected_option", {})
        )
        description = description_selected.get("text", {}).get("text", "") or ""

        # 버튼에 전달할 데이터 (스프레드시트 저장용)
        button_data = json.dumps(
            {
                "user_name": user_name,
                "booking_key": booking_key,
                "company_name": company_name,
                "customer_name": customer_name,
                "settlement_day": settlement_day,
                "issue_type": issue_type,
                "settlement_cost": settlement_cost,
                "company_sub_name": company_sub_name,
                "carmore_cost": carmore_cost,
                "user_refund_cost": user_refund_cost,
                "seller_channel": seller_channel,
                "description": description,
            },
            ensure_ascii=False,
        )

        # 승인 요청 메시지 블록 생성
        blocks = build_approval_request_message(
            user_name=user_name,
            booking_key=booking_key,
            company_name=company_name,
            customer_name=customer_name,
            settlement_day=settlement_day,
            issue_type=issue_type,
            settlement_cost=settlement_cost,
            company_sub_name=company_sub_name,
            carmore_cost=carmore_cost,
            user_refund_cost=user_refund_cost,
            seller_channel=seller_channel,
            description=description,
            button_data=button_data,
        )

        # 편집 모드면 기존 메시지 업데이트, 아니면 새 메시지 생성
        if message_ts:
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text="정산 이슈 등록 요청 (수정됨)",
                blocks=blocks,
            )
        else:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts if thread_ts else None,
                text="정산 이슈 등록 요청",
                blocks=blocks,
            )
