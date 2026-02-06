from __future__ import annotations

from pydantic import ValidationError
from slack_bolt import App
from slack_sdk.errors import SlackApiError

from app.config import get_app_config
from app.constants import ActionId, BlockId, IssueType
from app.constants.options import Description
from app.constants.ui_texts import HeaderText
from app.core import get_logger
from app.listener.payload import MessageContext, action_value, message_context
from app.models import (
    ModalMetadata,
    RejectionMetadata,
    SettlementData,
    SettlementStatus,
)
from app.services.message_parser import ParsedSettlement, ParsedTransferReservation
from app.services.settlement_service import save_settlement
from app.services.slack_service import (
    extract_date_value,
    extract_select_value,
    extract_text_value,
    get_thread_url,
    get_user_name,
)
from app.views.blocks import (
    build_approval_request_message,
    build_approved_message,
    build_minimal_approved_message,
    build_registration_modal,
    build_rejection_modal,
)

logger = get_logger(__name__)
Approvers = frozenset[str]


def _has_permission(
    *,
    client,
    approvers: Approvers,
    context: MessageContext,
    denied_text: str,
) -> bool:
    if context.user_id in approvers:
        return True
    client.chat_postEphemeral(
        channel=context.channel_id,
        user=context.user_id,
        text=denied_text,
        thread_ts=context.thread_ts_or_none,
    )
    return False


def _notify_processing_error(
    *,
    client,
    context: MessageContext,
    prefix: str,
) -> None:
    client.chat_postEphemeral(
        channel=context.channel_id,
        user=context.user_id,
        text=f"⚠️ {prefix} 처리 중 오류가 발생했습니다.",
        thread_ts=context.thread_ts_or_none,
    )


def _open_registration_modal(body: dict, client) -> None:
    parsed = ParsedSettlement.model_validate_json(action_value(body))
    context = message_context(body)
    user_name = get_user_name(client, context.user_id)

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


def _open_transfer_modal(body: dict, client) -> None:
    """Transfer 모달 열기 (통합 버전) - 정산유형만 "대신배차"로 prefill"""
    parsed = ParsedTransferReservation.model_validate_json(action_value(body))
    context = message_context(body)
    user_name = get_user_name(client, context.user_id)

    metadata = ModalMetadata(
        channel_id=context.channel_id,
        thread_ts=context.thread_ts,
        user_name=user_name,
        booking_key=parsed.booking_key,
        company_name="",
        customer_name=parsed.customer_name,
    )

    # Transfer 모달: 정산유형만 "대신배차"로 prefill, 나머지 필드는 파싱 데이터 사용
    modal = build_registration_modal(
        user_name=user_name,
        booking_key=parsed.booking_key,
        company_name="",  # Transfer의 경우 업체명은 직접 입력
        customer_name=parsed.customer_name,
        metadata=metadata.model_dump_json(),
        issue_type=IssueType.INSTEAD_DISPATCH.value,  # 대신배차로 prefill
        company_sub_name=parsed.company_sub_name or "",
        settlement_cost=parsed.settlement_cost or "",
        carmore_cost=parsed.carmore_cost or "",
    )
    client.views_open(
        trigger_id=body["trigger_id"],
        view=modal,
    )


def _handle_settlement_approve(
    *,
    body: dict,
    client,
    approvers: Approvers,
) -> None:
    """정산 이슈 승인 처리"""
    context = message_context(body)
    if not _has_permission(
        client=client,
        approvers=approvers,
        context=context,
        denied_text="⚠️ 승인 권한이 없습니다.",
    ):
        return

    try:
        approver_name = get_user_name(client, context.user_id)
        data = SettlementData.model_validate_json(action_value(body))

        # 상세 메시지 URL (원본 스레드의 상세 메시지)
        message_url = get_thread_url(
            client, data.original_channel_id, data.original_message_ts
        )

        save_settlement(
            data=data,
            status=SettlementStatus.APPROVED,
            approver_name=approver_name,
            thread_url=message_url,
        )

        # 1) 승인 채널 메시지 업데이트
        requester_name = get_user_name(client, data.requester_id)
        approval_blocks = build_minimal_approved_message(
            requester_name=requester_name,
            thread_url=message_url,
            approver_name=approver_name,
            is_transfer=False,
        )
        client.chat_update(
            channel=context.channel_id,
            ts=context.message_ts,
            text="정산 이슈 승인됨",
            blocks=approval_blocks,
        )

        # 2) 원본 스레드 상세 메시지 업데이트 (상세 정보 유지 + 승인 상태)
        original_blocks = build_approval_request_message(
            data, title=HeaderText.SETTLEMENT_ISSUE_REGISTER, include_buttons=False
        )
        thread_blocks = build_approved_message(original_blocks, approver_name)
        client.chat_update(
            channel=data.original_channel_id,
            ts=data.original_message_ts,
            text="정산 이슈 승인됨",
            blocks=thread_blocks,
        )

        # 3) 원본 스레드에 요청자 멘션
        if data.requester_id:
            client.chat_postMessage(
                channel=data.original_channel_id,
                thread_ts=data.original_thread_ts or None,
                text=f"<@{data.requester_id}> 정산 이슈가 승인되었습니다.",
            )
    except (SlackApiError, ValidationError, KeyError):
        logger.exception("settlement_approve_failed")
        _notify_processing_error(
            client=client,
            context=context,
            prefix="승인",
        )


def _open_rejection_modal(
    *,
    body: dict,
    client,
    approvers: Approvers,
) -> None:
    """반려 사유 입력 모달 열기"""
    context = message_context(body)
    if not _has_permission(
        client=client,
        approvers=approvers,
        context=context,
        denied_text="⚠️ 반려 권한이 없습니다.",
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
        # 원본 스레드 정보 (승인 채널 워크플로우용)
        original_channel_id=data.original_channel_id or "",
        original_thread_ts=data.original_thread_ts or "",
        original_message_ts=data.original_message_ts or "",
    )

    modal = build_rejection_modal(metadata=metadata.model_dump_json())
    client.views_open(
        trigger_id=body["trigger_id"],
        view=modal,
    )


def _handle_transfer_approve(
    *,
    body: dict,
    client,
    approvers: Approvers,
) -> None:
    """업체이관 승인 처리"""
    context = message_context(body)
    if not _has_permission(
        client=client,
        approvers=approvers,
        context=context,
        denied_text="⚠️ 승인 권한이 없습니다.",
    ):
        return

    try:
        approver_name = get_user_name(client, context.user_id)
        data = SettlementData.model_validate_json(action_value(body))

        logger.info("transfer_approve_started", booking_key=data.booking_key)
        logger.debug("transfer_approve_data", data=data.model_dump())

        # 상세 메시지 URL (원본 스레드의 상세 메시지)
        message_url = get_thread_url(
            client, data.original_channel_id, data.original_message_ts
        )

        save_settlement(
            data=data,
            status=SettlementStatus.APPROVED,
            approver_name=approver_name,
            thread_url=message_url,
        )

        # 1) 승인 채널 메시지 업데이트
        requester_name = get_user_name(client, data.requester_id)
        approval_blocks = build_minimal_approved_message(
            requester_name=requester_name,
            thread_url=message_url,
            approver_name=approver_name,
            is_transfer=True,
        )
        client.chat_update(
            channel=context.channel_id,
            ts=context.message_ts,
            text="업체이관 승인됨",
            blocks=approval_blocks,
        )

        # 2) 원본 스레드 상세 메시지 업데이트 (상세 정보 유지 + 승인 상태)
        original_blocks = build_approval_request_message(
            data, title=HeaderText.TRANSFER_REGISTER, include_buttons=False
        )
        thread_blocks = build_approved_message(original_blocks, approver_name)
        client.chat_update(
            channel=data.original_channel_id,
            ts=data.original_message_ts,
            text="업체이관 승인됨",
            blocks=thread_blocks,
        )

        # 3) 원본 스레드에 요청자 멘션
        if data.requester_id:
            client.chat_postMessage(
                channel=data.original_channel_id,
                thread_ts=data.original_thread_ts or None,
                text=f"<@{data.requester_id}> 업체이관이 승인되었습니다.",
            )

        logger.info("transfer_approve_completed", booking_key=data.booking_key)
    except (SlackApiError, ValidationError, KeyError):
        logger.exception("transfer_approve_failed")
        _notify_processing_error(
            client=client,
            context=context,
            prefix="승인",
        )


def _extract_current_modal_state(view: dict) -> dict:
    """views_update 시 현재 입력값 보존을 위해 모든 필드값 추출"""
    values = view.get("state", {}).get("values", {})
    text_value = extract_text_value
    date_value = extract_date_value
    select_value = extract_select_value

    return {
        "booking_key": text_value(
            values, BlockId.BOOKING_KEY_BLOCK, ActionId.BOOKING_KEY_INPUT
        ),
        "customer_name": text_value(
            values, BlockId.CUSTOMER_NAME_BLOCK, ActionId.CUSTOMER_NAME_INPUT
        ),
        "settlement_day": date_value(
            values, BlockId.SETTLEMENT_DAY_BLOCK, ActionId.SETTLEMENT_DAY_INPUT
        ),
        "issue_type": select_value(
            values, BlockId.ISSUE_TYPE_BLOCK, ActionId.ISSUE_TYPE_INPUT
        ),
        "custom_issue_type": text_value(
            values, BlockId.ISSUE_TYPE_TEXT_BLOCK, ActionId.ISSUE_TYPE_TEXT_INPUT
        ),
        "company_name": text_value(
            values, BlockId.COMPANY_NAME_BLOCK, ActionId.COMPANY_NAME_INPUT
        ),
        "company_sub_name": text_value(
            values, BlockId.COMPANY_SUB_NAME_BLOCK, ActionId.COMPANY_SUB_NAME_INPUT
        ),
        "settlement_cost": text_value(
            values, BlockId.SETTLEMENT_COST_BLOCK, ActionId.SETTLEMENT_COST_INPUT
        ),
        "carmore_cost": text_value(
            values, BlockId.CARMORE_COST_BLOCK, ActionId.CARMORE_COST_INPUT
        ),
        "user_refund_cost": text_value(
            values, BlockId.USER_REFUND_COST_BLOCK, ActionId.USER_REFUND_COST_INPUT
        ),
        "seller_channel": select_value(
            values, BlockId.SELLER_CHANNEL_BLOCK, ActionId.SELLER_CHANNEL_INPUT
        ),
        "description": select_value(
            values, BlockId.DESCRIPTION_BLOCK, ActionId.DESCRIPTION_INPUT
        ),
        "custom_description": text_value(
            values, BlockId.DESCRIPTION_TEXT_BLOCK, ActionId.DESCRIPTION_TEXT_INPUT
        ),
        "note": text_value(values, BlockId.NOTE_BLOCK, ActionId.NOTE_INPUT),
    }


def _handle_dynamic_form_change(body: dict, client) -> None:
    """동적 폼 변경 핸들러: "기타" 선택 시 텍스트 입력으로 전환"""
    view = body.get("view", {})
    view_id = view.get("id")
    view_hash = view.get("hash")
    private_metadata = view.get("private_metadata", "{}")

    # 현재 모달 상태 추출
    state = _extract_current_modal_state(view)
    metadata = ModalMetadata.model_validate_json(private_metadata)

    # "기타" 선택 여부 확인
    show_issue_type_text = state["issue_type"] == IssueType.OTHER.value
    show_description_text = state["description"] == Description.OTHER.value

    # 모달 재빌드
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
        description="" if show_description_text else state["description"],
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


def register_action_handlers(app: App) -> None:
    approvers = frozenset(get_app_config().approvers)

    @app.action(ActionId.OPEN_REGISTRATION_MODAL)
    def handle_open_registration_modal(ack, body, client):
        ack()
        _open_registration_modal(body, client)

    @app.action(ActionId.OPEN_TRANSFER_MODAL)
    def handle_open_transfer_modal(ack, body, client):
        ack()
        _open_transfer_modal(body, client)

    @app.action(ActionId.ISSUE_TYPE_INPUT)
    def handle_issue_type_change(ack, body, client):
        ack()
        _handle_dynamic_form_change(body, client)

    @app.action(ActionId.DESCRIPTION_INPUT)
    def handle_description_change(ack, body, client):
        ack()
        _handle_dynamic_form_change(body, client)

    @app.action(ActionId.SETTLEMENT_APPROVE)
    def handle_settlement_approve(ack, body, client):
        ack()
        _handle_settlement_approve(
            body=body,
            client=client,
            approvers=approvers,
        )

    @app.action(ActionId.SETTLEMENT_REJECT)
    def handle_settlement_reject(ack, body, client):
        ack()
        _open_rejection_modal(
            body=body,
            client=client,
            approvers=approvers,
        )

    @app.action(ActionId.TRANSFER_APPROVE)
    def handle_transfer_approve(ack, body, client):
        ack()
        _handle_transfer_approve(
            body=body,
            client=client,
            approvers=approvers,
        )

    @app.action(ActionId.TRANSFER_REJECT)
    def handle_transfer_reject(ack, body, client):
        ack()
        _open_rejection_modal(
            body=body,
            client=client,
            approvers=approvers,
        )
