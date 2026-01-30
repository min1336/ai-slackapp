from __future__ import annotations

from slack_bolt import App

from app.constants import ActionId, BlockId
from app.models import ModalMetadata, SettlementData
from app.services.slack_service import (
    extract_date_value,
    extract_select_value,
    extract_text_value,
)
from app.views.blocks import build_approval_request_message


def register_view_handlers(app: App) -> None:
    @app.view(ActionId.REGISTRATION_SUBMIT)
    def handle_registration_submit(ack, client, view):
        ack()

        metadata = ModalMetadata.model_validate_json(view.get("private_metadata", "{}"))

        values = view.get("state", {}).get("values", {})

        data = SettlementData(
            user_name=extract_text_value(
                values, BlockId.USER_NAME_BLOCK, ActionId.USER_NAME_INPUT
            ),
            booking_key=extract_text_value(
                values, BlockId.BOOKING_KEY_BLOCK, ActionId.BOOKING_KEY_INPUT
            ),
            company_name=extract_text_value(
                values, BlockId.COMPANY_NAME_BLOCK, ActionId.COMPANY_NAME_INPUT
            ),
            customer_name=extract_text_value(
                values, BlockId.CUSTOMER_NAME_BLOCK, ActionId.CUSTOMER_NAME_INPUT
            ),
            settlement_day=extract_date_value(
                values, BlockId.SETTLEMENT_DAY_BLOCK, ActionId.SETTLEMENT_DAY_INPUT
            ),
            issue_type=extract_select_value(
                values, BlockId.ISSUE_TYPE_BLOCK, ActionId.ISSUE_TYPE_INPUT
            ),
            settlement_cost=extract_text_value(
                values, BlockId.SETTLEMENT_COST_BLOCK, ActionId.SETTLEMENT_COST_INPUT
            ),
            company_sub_name=extract_text_value(
                values,
                BlockId.COMPANY_SUB_NAME_BLOCK,
                ActionId.COMPANY_SUB_NAME_INPUT,
            ),
            carmore_cost=extract_text_value(
                values, BlockId.CARMORE_COST_BLOCK, ActionId.CARMORE_COST_INPUT
            ),
            user_refund_cost=extract_text_value(
                values,
                BlockId.USER_REFUND_COST_BLOCK,
                ActionId.USER_REFUND_COST_INPUT,
            ),
            seller_channel=extract_select_value(
                values, BlockId.SELLER_CHANNEL_BLOCK, ActionId.SELLER_CHANNEL_INPUT
            ),
            description=extract_select_value(
                values, BlockId.DESCRIPTION_BLOCK, ActionId.DESCRIPTION_INPUT
            ),
        )

        blocks = build_approval_request_message(
            user_name=data.user_name,
            booking_key=data.booking_key,
            company_name=data.company_name,
            customer_name=data.customer_name,
            settlement_day=data.settlement_day,
            issue_type=data.issue_type,
            settlement_cost=data.settlement_cost,
            company_sub_name=data.company_sub_name,
            carmore_cost=data.carmore_cost,
            user_refund_cost=data.user_refund_cost,
            seller_channel=data.seller_channel,
            description=data.description,
            button_data=data.model_dump_json(),
        )

        if metadata.message_ts:
            client.chat_update(
                channel=metadata.channel_id,
                ts=metadata.message_ts,
                text="정산 이슈 등록 요청 (수정됨)",
                blocks=blocks,
            )
        else:
            client.chat_postMessage(
                channel=metadata.channel_id,
                thread_ts=metadata.thread_ts or None,
                text="정산 이슈 등록 요청",
                blocks=blocks,
            )
