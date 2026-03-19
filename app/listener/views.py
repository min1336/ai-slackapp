from __future__ import annotations

from typing import TYPE_CHECKING

from slack_bolt import App

from app.constants import ActionId, BlockId
from app.listener.payload import (
    extract_date_value,
    extract_select_value,
    extract_text_value,
)
from app.models import (
    ModalMetadata,
    RejectionMetadata,
    SettlementData,
)

if TYPE_CHECKING:
    from app.container import ServiceContainer


def register_view_handlers(app: App, container: ServiceContainer) -> None:
    registration = container.registration
    rejection = container.rejection

    @app.view(ActionId.REGISTRATION_SUBMIT)
    def handle_registration_submit(ack, view, body):
        ack()

        metadata = ModalMetadata.model_validate_json(view.get("private_metadata", "{}"))
        values = view.get("state", {}).get("values", {})
        text_value = extract_text_value
        date_value = extract_date_value
        select_value = extract_select_value

        # user_name: input 필드 값이 없으면 metadata에서 사용
        user_name_from_input = text_value(
            values, BlockId.USER_NAME_BLOCK, ActionId.USER_NAME_INPUT
        )
        user_name = user_name_from_input or metadata.user_name

        # 동적 폼: 텍스트 입력 우선, 없으면 셀렉트 값 사용
        issue_type = text_value(
            values,
            BlockId.ISSUE_TYPE_TEXT_BLOCK,
            ActionId.ISSUE_TYPE_TEXT_INPUT,
        ) or select_value(values, BlockId.ISSUE_TYPE_BLOCK, ActionId.ISSUE_TYPE_INPUT)

        description = text_value(
            values,
            BlockId.DESCRIPTION_TEXT_BLOCK,
            ActionId.DESCRIPTION_TEXT_INPUT,
        ) or select_value(values, BlockId.DESCRIPTION_BLOCK, ActionId.DESCRIPTION_INPUT)

        note = text_value(values, BlockId.NOTE_BLOCK, ActionId.NOTE_INPUT) or None
        requester_id = body.get("user", {}).get("id", "")

        data = SettlementData(
            user_name=user_name,
            booking_key=text_value(
                values,
                BlockId.BOOKING_KEY_BLOCK,
                ActionId.BOOKING_KEY_INPUT,
            ),
            company_name=text_value(
                values,
                BlockId.COMPANY_NAME_BLOCK,
                ActionId.COMPANY_NAME_INPUT,
            ),
            customer_name=text_value(
                values,
                BlockId.CUSTOMER_NAME_BLOCK,
                ActionId.CUSTOMER_NAME_INPUT,
            ),
            settlement_day=date_value(
                values,
                BlockId.SETTLEMENT_DAY_BLOCK,
                ActionId.SETTLEMENT_DAY_INPUT,
            ),
            issue_type=issue_type,
            settlement_cost=text_value(
                values,
                BlockId.SETTLEMENT_COST_BLOCK,
                ActionId.SETTLEMENT_COST_INPUT,
            ),
            company_sub_name=text_value(
                values,
                BlockId.COMPANY_SUB_NAME_BLOCK,
                ActionId.COMPANY_SUB_NAME_INPUT,
            )
            or None,
            carmore_cost=text_value(
                values,
                BlockId.CARMORE_COST_BLOCK,
                ActionId.CARMORE_COST_INPUT,
            ),
            seller_channel_cost=text_value(
                values,
                BlockId.SELLER_CHANNEL_COST_BLOCK,
                ActionId.SELLER_CHANNEL_COST_INPUT,
            ),
            user_refund_cost=text_value(
                values,
                BlockId.USER_REFUND_COST_BLOCK,
                ActionId.USER_REFUND_COST_INPUT,
            ),
            seller_channel=select_value(
                values,
                BlockId.SELLER_CHANNEL_BLOCK,
                ActionId.SELLER_CHANNEL_INPUT,
            )
            or None,
            description=description or None,
            note=note,
            requester_id=requester_id,
        )

        registration.register(
            data=data,
            channel_id=metadata.channel_id,
            thread_ts=metadata.thread_ts,
            requester_id=requester_id,
        )

    @app.view(ActionId.REJECTION_SUBMIT)
    def handle_rejection_submit(ack, view, body):
        ack()

        metadata = RejectionMetadata.model_validate_json(
            view.get("private_metadata", "{}")
        )
        values = view.get("state", {}).get("values", {})
        rejection_reason = extract_text_value(
            values,
            BlockId.REJECTION_REASON_BLOCK,
            ActionId.REJECTION_REASON_INPUT,
        )
        rejecter_id = body.get("user", {}).get("id", "")
        data = SettlementData.model_validate_json(metadata.button_data)

        rejection.reject(
            data=data,
            metadata=metadata,
            rejection_reason=rejection_reason,
            rejecter_id=rejecter_id,
        )
