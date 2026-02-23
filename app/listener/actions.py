from __future__ import annotations

from typing import TYPE_CHECKING

from slack_bolt import App

from app.constants import ActionId, BlockId, IssueType
from app.constants.options import Description
from app.listener.payload import (
    action_value,
    extract_date_value,
    extract_select_value,
    extract_text_value,
    message_context,
)
from app.models import (
    ModalMetadata,
    RejectionMetadata,
    SettlementData,
)
from app.services.message_parser import ParsedSettlement, ParsedTransferReservation
from app.views.blocks import build_registration_modal, build_rejection_modal

if TYPE_CHECKING:
    from app.container import ServiceContainer

# (field_name, block_id, action_id, extractor)
_MODAL_FIELD_EXTRACTORS = (
    (
        "booking_key",
        BlockId.BOOKING_KEY_BLOCK,
        ActionId.BOOKING_KEY_INPUT,
        extract_text_value,
    ),
    (
        "customer_name",
        BlockId.CUSTOMER_NAME_BLOCK,
        ActionId.CUSTOMER_NAME_INPUT,
        extract_text_value,
    ),
    (
        "settlement_day",
        BlockId.SETTLEMENT_DAY_BLOCK,
        ActionId.SETTLEMENT_DAY_INPUT,
        extract_date_value,
    ),
    (
        "issue_type",
        BlockId.ISSUE_TYPE_BLOCK,
        ActionId.ISSUE_TYPE_INPUT,
        extract_select_value,
    ),
    (
        "custom_issue_type",
        BlockId.ISSUE_TYPE_TEXT_BLOCK,
        ActionId.ISSUE_TYPE_TEXT_INPUT,
        extract_text_value,
    ),
    (
        "company_name",
        BlockId.COMPANY_NAME_BLOCK,
        ActionId.COMPANY_NAME_INPUT,
        extract_text_value,
    ),
    (
        "company_sub_name",
        BlockId.COMPANY_SUB_NAME_BLOCK,
        ActionId.COMPANY_SUB_NAME_INPUT,
        extract_text_value,
    ),
    (
        "settlement_cost",
        BlockId.SETTLEMENT_COST_BLOCK,
        ActionId.SETTLEMENT_COST_INPUT,
        extract_text_value,
    ),
    (
        "carmore_cost",
        BlockId.CARMORE_COST_BLOCK,
        ActionId.CARMORE_COST_INPUT,
        extract_text_value,
    ),
    (
        "user_refund_cost",
        BlockId.USER_REFUND_COST_BLOCK,
        ActionId.USER_REFUND_COST_INPUT,
        extract_text_value,
    ),
    (
        "seller_channel",
        BlockId.SELLER_CHANNEL_BLOCK,
        ActionId.SELLER_CHANNEL_INPUT,
        extract_select_value,
    ),
    (
        "description",
        BlockId.DESCRIPTION_BLOCK,
        ActionId.DESCRIPTION_INPUT,
        extract_select_value,
    ),
    (
        "custom_description",
        BlockId.DESCRIPTION_TEXT_BLOCK,
        ActionId.DESCRIPTION_TEXT_INPUT,
        extract_text_value,
    ),
    ("note", BlockId.NOTE_BLOCK, ActionId.NOTE_INPUT, extract_text_value),
)


def _open_registration_modal(body: dict, client, reader) -> None:
    parsed = ParsedSettlement.model_validate_json(action_value(body))
    context = message_context(body)
    user_name = reader.get_user_name(context.user_id)

    metadata = ModalMetadata(
        channel_id=context.channel_id,
        thread_ts=context.thread_ts,
        user_name=user_name,
        booking_key=parsed.booking_key,
        company_name=parsed.company_name,
        customer_name=parsed.customer_name,
    )

    modal = build_registration_modal(
        user_name=user_name,
        booking_key=parsed.booking_key,
        company_name=parsed.company_name,
        customer_name=parsed.customer_name,
        metadata=metadata.model_dump_json(),
    )
    client.views_open(
        trigger_id=body["trigger_id"],
        view=modal,
    )


def _open_transfer_modal(body: dict, client, reader) -> None:
    parsed = ParsedTransferReservation.model_validate_json(action_value(body))
    context = message_context(body)
    user_name = reader.get_user_name(context.user_id)
    booking_key = parsed.booking_key

    metadata = ModalMetadata(
        channel_id=context.channel_id,
        thread_ts=context.thread_ts,
        user_name=user_name,
        booking_key=booking_key,
        company_name="",
        customer_name=parsed.customer_name,
    )

    modal = build_registration_modal(
        user_name=user_name,
        booking_key=booking_key,
        company_name="",
        customer_name=parsed.customer_name,
        metadata=metadata.model_dump_json(),
        issue_type=IssueType.INSTEAD_DISPATCH.value,
        company_sub_name=parsed.company_sub_name or "",
        settlement_cost=parsed.settlement_cost or "",
        carmore_cost=parsed.carmore_cost or "",
    )
    client.views_open(
        trigger_id=body["trigger_id"],
        view=modal,
    )


def _open_rejection_modal(body: dict, client, rejection_service) -> None:
    context = message_context(body)
    if not rejection_service.has_permission(
        user_id=context.user_id,
        channel_id=context.channel_id,
        thread_ts=context.thread_ts,
        text="⚠️ 반려 권한이 없습니다.",
    ):
        return

    button_data = action_value(body)
    data = SettlementData.model_validate_json(button_data)

    metadata = RejectionMetadata(
        channel_id=context.channel_id,
        thread_ts=context.thread_ts,
        message_ts=context.message_ts,
        requester_id=data.requester_id,
        button_data=button_data,
        original_channel_id=data.original_channel_id or "",
        original_thread_ts=data.original_thread_ts or "",
        original_message_ts=data.original_message_ts or "",
    )

    modal = build_rejection_modal(metadata=metadata.model_dump_json())
    client.views_open(
        trigger_id=body["trigger_id"],
        view=modal,
    )


def _extract_current_modal_state(view: dict) -> dict:
    values = view.get("state", {}).get("values", {})
    return {
        name: extractor(values, block_id, action_id)
        for name, block_id, action_id, extractor in _MODAL_FIELD_EXTRACTORS
    }


def _handle_dynamic_form_change(body: dict, client) -> None:
    view = body.get("view", {})
    view_id = view.get("id")
    view_hash = view.get("hash")
    private_metadata = view.get("private_metadata", "{}")

    state = _extract_current_modal_state(view)
    metadata = ModalMetadata.model_validate_json(private_metadata)

    show_issue_type_text = state["issue_type"] == IssueType.OTHER.value
    show_description_text = state["description"] == Description.OTHER.value

    modal = build_registration_modal(
        user_name=metadata.user_name,
        booking_key=state["booking_key"] or metadata.booking_key,
        company_name=state["company_name"] or metadata.company_name,
        customer_name=state["customer_name"] or metadata.customer_name,
        metadata=private_metadata,
        settlement_day=state["settlement_day"],
        issue_type="" if show_issue_type_text else state["issue_type"],
        company_sub_name=state["company_sub_name"],
        settlement_cost=state["settlement_cost"],
        carmore_cost=state["carmore_cost"],
        user_refund_cost=state["user_refund_cost"],
        seller_channel=state["seller_channel"],
        description=("" if show_description_text else state["description"]),
        note=state["note"],
        show_issue_type_text=show_issue_type_text,
        show_description_text=show_description_text,
        custom_issue_type=state["custom_issue_type"],
        custom_description=state["custom_description"],
    )

    client.views_update(
        view_id=view_id,
        hash=view_hash,
        view=modal,
    )


def register_action_handlers(app: App, container: ServiceContainer) -> None:
    approval = container.approval
    rejection = container.rejection
    reader = container.reader

    @app.action(ActionId.OPEN_REGISTRATION_MODAL)
    def handle_open_registration_modal(ack, body, client):
        ack()
        _open_registration_modal(body, client, reader)

    @app.action(ActionId.OPEN_TRANSFER_MODAL)
    def handle_open_transfer_modal(ack, body, client):
        ack()
        _open_transfer_modal(body, client, reader)

    @app.action(ActionId.ISSUE_TYPE_INPUT)
    def handle_issue_type_change(ack, body, client):
        ack()
        _handle_dynamic_form_change(body, client)

    @app.action(ActionId.DESCRIPTION_INPUT)
    def handle_description_change(ack, body, client):
        ack()
        _handle_dynamic_form_change(body, client)

    @app.action(ActionId.SETTLEMENT_APPROVE)
    def handle_settlement_approve(ack, body):
        ack()
        ctx = message_context(body)
        data = SettlementData.model_validate_json(action_value(body))
        original_blocks = body.get("message", {}).get("blocks", [])
        approval.approve(
            data=data,
            user_id=ctx.user_id,
            channel_id=ctx.channel_id,
            message_ts=ctx.message_ts,
            thread_ts=ctx.thread_ts,
            original_blocks=original_blocks,
            is_transfer=False,
        )

    @app.action(ActionId.SETTLEMENT_REJECT)
    def handle_settlement_reject(ack, body, client):
        ack()
        _open_rejection_modal(body, client, rejection)

    @app.action(ActionId.TRANSFER_APPROVE)
    def handle_transfer_approve(ack, body):
        ack()
        ctx = message_context(body)
        data = SettlementData.model_validate_json(action_value(body))
        original_blocks = body.get("message", {}).get("blocks", [])
        approval.approve(
            data=data,
            user_id=ctx.user_id,
            channel_id=ctx.channel_id,
            message_ts=ctx.message_ts,
            thread_ts=ctx.thread_ts,
            original_blocks=original_blocks,
            is_transfer=True,
        )

    @app.action(ActionId.TRANSFER_REJECT)
    def handle_transfer_reject(ack, body, client):
        ack()
        _open_rejection_modal(body, client, rejection)
