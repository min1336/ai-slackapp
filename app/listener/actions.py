from __future__ import annotations

from pydantic import ValidationError
from slack_bolt import App
from slack_sdk.errors import SlackApiError

from app.config import get_app_config
from app.constants import ActionId, BlockId, IssueType
from app.constants.options import Description
from app.core import get_logger
from app.listener.payload import Blocks, MessageContext, action_value, message_context
from app.models import ModalMetadata, SettlementData, SettlementStatus
from app.services.message_parser import ParsedTransferReservation
from app.services.settlement_service import save_settlement
from app.services.slack_service import (
    extract_date_value,
    extract_select_value,
    extract_text_value,
    get_spreadsheet_url,
    get_thread_url,
    get_user_name,
    send_dm,
)
from app.views.blocks import (
    build_approved_message,
    build_registration_modal,
    build_rejected_message,
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


def _build_decision_message(
    *,
    status: SettlementStatus,
    original_blocks: Blocks,
    approver_name: str,
) -> tuple[str, Blocks]:
    if status == SettlementStatus.APPROVED:
        return "정산 이슈 승인됨", build_approved_message(
            original_blocks, approver_name
        )
    return "정산 이슈 반려됨", build_rejected_message(original_blocks, approver_name)


def _build_approval_dm_text(
    *,
    prefix: str,
    data: SettlementData,
    approver_name: str,
    thread_url: str,
) -> str:
    return (
        f"✅ {prefix} 승인되었습니다.\n"
        f"• 예약번호: {data.booking_key}\n"
        f"• 업체명: {data.company_name}\n"
        f"• 고객명: {data.customer_name}\n"
        f"• 승인자: {approver_name}\n"
        f"• 스레드: {thread_url}\n"
        f"• 스프레드시트: {get_spreadsheet_url()}"
    )


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
    parsed = SettlementData.model_validate_json(action_value(body))
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


def _handle_settlement_decision(
    *,
    body: dict,
    client,
    status: SettlementStatus,
    approvers: Approvers,
) -> None:
    context = message_context(body)
    if not _has_permission(
        client=client,
        approvers=approvers,
        context=context,
        denied_text=f"⚠️ {status.value} 권한이 없습니다.",
    ):
        return

    approver_name = get_user_name(client, context.user_id)
    thread_url = get_thread_url(client, context.channel_id, context.thread_ts)
    data = SettlementData.model_validate_json(action_value(body))

    save_settlement(
        data=data,
        status=status,
        approver_name=approver_name,
        thread_url=thread_url,
    )

    original_blocks = body.get("message", {}).get("blocks", [])
    text, new_blocks = _build_decision_message(
        status=status,
        original_blocks=original_blocks,
        approver_name=approver_name,
    )
    client.chat_update(
        channel=context.channel_id,
        ts=context.message_ts,
        text=text,
        blocks=new_blocks,
    )

    if status == SettlementStatus.APPROVED:
        dm_text = _build_approval_dm_text(
            prefix="정산 이슈가",
            data=data,
            approver_name=approver_name,
            thread_url=thread_url,
        )
        send_dm(client, context.user_id, dm_text)


def _is_custom_value(value: str, options: list) -> bool:
    """주어진 값이 사전 정의된 옵션에 없는 커스텀 값인지 확인"""
    from app.constants import find_option_by_text

    return bool(value) and find_option_by_text(options, value) is None


def _open_settlement_edit_modal(
    *,
    body: dict,
    client,
    approvers: Approvers,
) -> None:
    context = message_context(body)
    if not _has_permission(
        client=client,
        approvers=approvers,
        context=context,
        denied_text="⚠️ 편집 권한이 없습니다.",
    ):
        return

    from app.constants import DESCRIPTION_OPTIONS, ISSUE_TYPE_OPTIONS

    data = SettlementData.model_validate_json(action_value(body))
    metadata = ModalMetadata(
        channel_id=context.channel_id,
        thread_ts=context.thread_ts,
        message_ts=context.message_ts,
        user_name=data.user_name,
        booking_key=data.booking_key,
        company_name=data.company_name,
        customer_name=data.customer_name,
    )

    # 커스텀 값 감지: 사전 정의 옵션에 없으면 텍스트 입력으로 표시
    is_custom_issue = _is_custom_value(data.issue_type, ISSUE_TYPE_OPTIONS)
    is_custom_description = _is_custom_value(data.description, DESCRIPTION_OPTIONS)

    modal = build_registration_modal(
        user_name=data.user_name,
        booking_key=data.booking_key,
        company_name=data.company_name,
        customer_name=data.customer_name,
        metadata=metadata.model_dump_json(),
        settlement_day=data.settlement_day,
        issue_type="" if is_custom_issue else data.issue_type,
        company_sub_name=data.company_sub_name,
        settlement_cost=data.settlement_cost,
        carmore_cost=data.carmore_cost,
        user_refund_cost=data.user_refund_cost,
        seller_channel=data.seller_channel,
        description="" if is_custom_description else data.description,
        note=data.note,
        is_edit=True,
        show_issue_type_text=is_custom_issue,
        show_description_text=is_custom_description,
        custom_issue_type=data.issue_type if is_custom_issue else "",
        custom_description=data.description if is_custom_description else "",
    )
    client.views_open(
        trigger_id=body["trigger_id"],
        view=modal,
    )


def _handle_transfer_decision(
    *,
    body: dict,
    client,
    status: SettlementStatus,
    approvers: Approvers,
) -> None:
    context = message_context(body)
    if not _has_permission(
        client=client,
        approvers=approvers,
        context=context,
        denied_text=f"⚠️ {status.value} 권한이 없습니다.",
    ):
        return

    try:
        approver_name = get_user_name(client, context.user_id)
        thread_url = get_thread_url(client, context.channel_id, context.thread_ts)
        data = SettlementData.model_validate_json(action_value(body))

        logger.info("업체이관 %s 시작: %s", status.value, data.booking_key)
        logger.debug("데이터: %s", data.model_dump_json(indent=2))

        save_settlement(
            data=data,
            status=status,
            approver_name=approver_name,
            thread_url=thread_url,
        )

        original_blocks = body.get("message", {}).get("blocks", [])
        text, new_blocks = _build_decision_message(
            status=status,
            original_blocks=original_blocks,
            approver_name=approver_name,
        )
        client.chat_update(
            channel=context.channel_id,
            ts=context.message_ts,
            text=text,
            blocks=new_blocks,
        )

        if status == SettlementStatus.APPROVED:
            dm_text = _build_approval_dm_text(
                prefix="업체이관 정산이",
                data=data,
                approver_name=approver_name,
                thread_url=thread_url,
            )
            send_dm(client, context.user_id, dm_text)

        logger.info("업체이관 %s 완료: %s", status.value, data.booking_key)
    except (SlackApiError, ValidationError, KeyError):
        logger.exception("업체이관 %s 중 에러 발생", status.value)
        _notify_processing_error(
            client=client,
            context=context,
            prefix=status.value,
        )


def _open_transfer_edit_modal(
    *,
    body: dict,
    client,
    approvers: Approvers,
) -> None:
    """Transfer 편집 모달 열기 - 통합 build_registration_modal 사용"""
    context = message_context(body)
    if not _has_permission(
        client=client,
        approvers=approvers,
        context=context,
        denied_text="⚠️ 편집 권한이 없습니다.",
    ):
        return

    try:
        from app.constants import DESCRIPTION_OPTIONS, ISSUE_TYPE_OPTIONS

        data = SettlementData.model_validate_json(action_value(body))
        logger.info("업체이관 편집 시작: %s", data.booking_key)
        logger.debug("데이터: %s", data.model_dump_json(indent=2))

        metadata = ModalMetadata(
            channel_id=context.channel_id,
            thread_ts=context.thread_ts,
            message_ts=context.message_ts,
            user_name=data.user_name,
            booking_key=data.booking_key,
            company_name=data.company_name,
            customer_name=data.customer_name,
        )

        # 커스텀 값 감지: 사전 정의 옵션에 없으면 텍스트 입력으로 표시
        is_custom_issue = _is_custom_value(data.issue_type, ISSUE_TYPE_OPTIONS)
        is_custom_description = _is_custom_value(data.description, DESCRIPTION_OPTIONS)

        # 통합 모달 사용 (Transfer 편집도 동일한 모달)
        modal = build_registration_modal(
            user_name=data.user_name,
            booking_key=data.booking_key,
            company_name=data.company_name,
            customer_name=data.customer_name,
            metadata=metadata.model_dump_json(),
            settlement_day=data.settlement_day,
            issue_type="" if is_custom_issue else data.issue_type,
            company_sub_name=data.company_sub_name,
            settlement_cost=data.settlement_cost,
            carmore_cost=data.carmore_cost,
            user_refund_cost=data.user_refund_cost,
            seller_channel=data.seller_channel,
            description="" if is_custom_description else data.description,
            note=data.note,
            is_edit=True,
            show_issue_type_text=is_custom_issue,
            show_description_text=is_custom_description,
            custom_issue_type=data.issue_type if is_custom_issue else "",
            custom_description=data.description if is_custom_description else "",
        )
        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal,
        )
        logger.info("업체이관 편집 모달 열기 완료: %s", data.booking_key)
    except (SlackApiError, ValidationError, KeyError):
        logger.exception("업체이관 편집 중 에러 발생")
        _notify_processing_error(
            client=client,
            context=context,
            prefix="편집",
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
        is_edit=bool(metadata.message_ts),
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
        _handle_settlement_decision(
            body=body,
            client=client,
            status=SettlementStatus.APPROVED,
            approvers=approvers,
        )

    @app.action(ActionId.SETTLEMENT_REJECT)
    def handle_settlement_reject(ack, body, client):
        ack()
        _handle_settlement_decision(
            body=body,
            client=client,
            status=SettlementStatus.REJECTED,
            approvers=approvers,
        )

    @app.action(ActionId.TRANSFER_APPROVE)
    def handle_transfer_approve(ack, body, client):
        ack()
        _handle_transfer_decision(
            body=body,
            client=client,
            status=SettlementStatus.APPROVED,
            approvers=approvers,
        )

    @app.action(ActionId.TRANSFER_REJECT)
    def handle_transfer_reject(ack, body, client):
        ack()
        _handle_transfer_decision(
            body=body,
            client=client,
            status=SettlementStatus.REJECTED,
            approvers=approvers,
        )

    @app.action(ActionId.TRANSFER_EDIT)
    def handle_transfer_edit(ack, body, client):
        ack()
        _open_transfer_edit_modal(body=body, client=client, approvers=approvers)

    @app.action(ActionId.SETTLEMENT_EDIT)
    def handle_settlement_edit(ack, body, client):
        ack()
        _open_settlement_edit_modal(body=body, client=client, approvers=approvers)
