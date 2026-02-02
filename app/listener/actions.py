from __future__ import annotations

from slack_bolt import App

from app.config import config
from app.constants import ActionId
from app.constants.options import Description
from app.core import get_logger
from app.exceptions import ValidationError
from app.models import ModalMetadata, SettlementData, SettlementStatus
from app.services.message_parser import ParsedTransferReservation
from app.services.settlement_service import save_settlement
from app.services.slack_service import (
    get_spreadsheet_url,
    get_thread_url,
    get_user_name,
    send_dm,
)
from app.views.blocks import (
    build_approved_message,
    build_registration_modal,
    build_rejected_message,
    build_transfer_registration_modal,
)

logger = get_logger(__name__)


def _check_approver_permission(user_id: str, action_name: str) -> None:
    if user_id not in config.approvers:
        raise ValidationError(
            message=f"User {user_id} does not have {action_name} permission",
            user_message=f"⚠️ {action_name} 권한이 없습니다.",
            details={"user_id": user_id, "action": action_name},
        )


def register_action_handlers(app: App) -> None:
    @app.action(ActionId.OPEN_REGISTRATION_MODAL)
    def handle_open_registration_modal(ack, body, client):
        ack()

        value = body.get("actions", [{}])[0].get("value", "{}")
        parsed = SettlementData.model_validate_json(value)

        user_id = body["user"]["id"]
        user_name = get_user_name(client, user_id)

        channel_id = body.get("channel", {}).get("id", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        metadata = ModalMetadata(
            channel_id=channel_id,
            thread_ts=thread_ts,
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

    @app.action(ActionId.OPEN_TRANSFER_REGISTRATION_MODAL_UNABLE_DISPATCH)
    def handle_open_transfer_registration_modal_unable_dispatch(ack, body, client):
        _handle_transfer_registration_modal(ack, body, client, "unable_dispatch")

    @app.action(ActionId.OPEN_TRANSFER_REGISTRATION_MODAL_RESERVATION)
    def handle_open_transfer_registration_modal_reservation(ack, body, client):
        _handle_transfer_registration_modal(ack, body, client, "reservation")

    def _handle_transfer_registration_modal(ack, body, client, description_type: str):
        ack()

        value = body.get("actions", [{}])[0].get("value", "{}")
        parsed = ParsedTransferReservation.model_validate_json(value)

        user_id = body["user"]["id"]
        user_name = get_user_name(client, user_id)

        channel_id = body.get("channel", {}).get("id", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        metadata = ModalMetadata(
            channel_id=channel_id,
            thread_ts=thread_ts,
            user_name=user_name,
            booking_key=parsed.booking_key,
            company_name="",  # 이관 건은 업체명이 비어있음
            customer_name=parsed.customer_name,
        )

        modal = build_transfer_registration_modal(
            parsed_data=parsed,
            user_name=user_name,
            metadata=metadata.model_dump_json(),
            description_type=description_type,
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

        # Permission check - raises ValidationError if not authorized
        _check_approver_permission(user_id, status.value)

        approver_name = get_user_name(client, user_id)
        thread_url = get_thread_url(client, channel_id, thread_ts)

        # 버튼 value에서 데이터 추출
        value = body.get("actions", [{}])[0].get("value", "{}")
        data = SettlementData.model_validate_json(value)

        # 스프레드시트에 저장 - raises SpreadsheetError on failure
        save_settlement(
            data=data,
            status=status,
            approver_name=approver_name,
            thread_url=thread_url,
        )

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

        # 승인 완료 시 승인자에게 DM 전송 - raises SlackError on failure
        if status == SettlementStatus.APPROVED:
            dm_text = (
                f"✅ 정산 이슈가 승인되었습니다.\n"
                f"• 예약번호: {data.booking_key}\n"
                f"• 업체명: {data.company_name}\n"
                f"• 고객명: {data.customer_name}\n"
                f"• 승인자: {approver_name}\n"
                f"• 스레드: {thread_url}\n"
                f"• 스프레드시트: {get_spreadsheet_url()}"
            )
            send_dm(client, user_id, dm_text)

    @app.action(ActionId.SETTLEMENT_APPROVE)
    def handle_settlement_approve(ack, body, client):
        ack()
        _handle_settlement_decision(body, client, SettlementStatus.APPROVED)

    @app.action(ActionId.SETTLEMENT_REJECT)
    def handle_settlement_reject(ack, body, client):
        ack()
        _handle_settlement_decision(body, client, SettlementStatus.REJECTED)

    @app.action(ActionId.TRANSFER_APPROVE)
    def handle_transfer_approve(ack, body, client):
        ack()
        _handle_transfer_decision(body, client, SettlementStatus.APPROVED)

    @app.action(ActionId.TRANSFER_REJECT)
    def handle_transfer_reject(ack, body, client):
        ack()
        _handle_transfer_decision(body, client, SettlementStatus.REJECTED)

    @app.action(ActionId.TRANSFER_EDIT)
    def handle_transfer_edit(ack, body, client):
        ack()
        _handle_transfer_edit_logic(body, client)

    @app.action(ActionId.SETTLEMENT_EDIT)
    def handle_settlement_edit(ack, body, client):
        ack()

        user_id = body["user"]["id"]
        channel_id = body.get("channel", {}).get("id", "")
        message_ts = body.get("message", {}).get("ts", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        # Permission check - raises ValidationError if not authorized
        _check_approver_permission(user_id, "편집")

        # 버튼 value에서 기존 데이터 추출
        value = body.get("actions", [{}])[0].get("value", "{}")
        data = SettlementData.model_validate_json(value)

        metadata = ModalMetadata(
            channel_id=channel_id,
            thread_ts=thread_ts,
            message_ts=message_ts,
            user_name=data.user_name,
            booking_key=data.booking_key,
            company_name=data.company_name,
            customer_name=data.customer_name,
        )

        modal = build_registration_modal(
            user_name=data.user_name,
            booking_key=data.booking_key,
            company_name=data.company_name,
            customer_name=data.customer_name,
            metadata=metadata.model_dump_json(),
            settlement_day=data.settlement_day,
            issue_type=data.issue_type,
            company_sub_name=data.company_sub_name,
            settlement_cost=data.settlement_cost,
            carmore_cost=data.carmore_cost,
            user_refund_cost=data.user_refund_cost,
            seller_channel=data.seller_channel,
            description=data.description,
            is_edit=True,
        )

        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal,
        )

    def _handle_transfer_decision(body, client, status: SettlementStatus) -> None:
        user_id = body["user"]["id"]
        channel_id = body.get("channel", {}).get("id", "")
        message_ts = body.get("message", {}).get("ts", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        # Permission check - raises ValidationError if not authorized
        _check_approver_permission(user_id, status.value)

        approver_name = get_user_name(client, user_id)
        thread_url = get_thread_url(client, channel_id, thread_ts)

        value = body.get("actions", [{}])[0].get("value", "{}")
        data = SettlementData.model_validate_json(value)

        logger.info(f"업체이관 {status.value} 시작: {data.booking_key}")
        logger.debug(f"데이터: {data.model_dump_json(indent=2)}")

        # Save to spreadsheet - raises SpreadsheetError on failure
        save_settlement(
            data=data,
            status=status,
            approver_name=approver_name,
            thread_url=thread_url,
        )

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

        # 승인 완료 시 승인자에게 DM 전송 - raises SlackError on failure
        if status == SettlementStatus.APPROVED:
            dm_text = (
                f"✅ 업체이관 정산이 승인되었습니다.\n"
                f"• 예약번호: {data.booking_key}\n"
                f"• 업체명: {data.company_name}\n"
                f"• 고객명: {data.customer_name}\n"
                f"• 승인자: {approver_name}\n"
                f"• 스레드: {thread_url}\n"
                f"• 스프레드시트: {get_spreadsheet_url()}"
            )
            send_dm(client, user_id, dm_text)

        logger.info(f"업체이관 {status.value} 완료: {data.booking_key}")

    def _handle_transfer_edit_logic(body, client):
        user_id = body["user"]["id"]
        channel_id = body.get("channel", {}).get("id", "")
        message_ts = body.get("message", {}).get("ts", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")

        # Permission check - raises ValidationError if not authorized
        _check_approver_permission(user_id, "편집")

        value = body.get("actions", [{}])[0].get("value", "{}")
        data = SettlementData.model_validate_json(value)

        logger.info(f"업체이관 편집 시작: {data.booking_key}")
        logger.debug(f"데이터: {data.model_dump_json(indent=2)}")

        parsed_data = ParsedTransferReservation(
            booking_key=data.booking_key,
            customer_name=data.customer_name,
            company_name=data.company_name,
            company_sub_name=data.company_sub_name,
            settlement_cost=data.settlement_cost,
            carmore_cost=data.carmore_cost,
        )

        is_reservation_change = (
            Description.TRANSFER_RESERVATION.value in data.description
        )

        metadata = ModalMetadata(
            channel_id=channel_id,
            thread_ts=thread_ts,
            message_ts=message_ts,
            user_name=data.user_name,
            booking_key=data.booking_key,
            company_name=data.company_name,
            customer_name=data.customer_name,
        )

        modal = build_transfer_registration_modal(
            parsed_data=parsed_data,
            user_name=data.user_name,
            metadata=metadata.model_dump_json(),
            description_type=(
                "reservation" if is_reservation_change else "unable_dispatch"
            ),
            company_name_param=data.company_name,
            settlement_day=data.settlement_day,
            company_sub_name=data.company_sub_name,
            settlement_cost=data.settlement_cost,
            carmore_cost=data.carmore_cost,
            user_refund_cost=data.user_refund_cost,
            seller_channel=data.seller_channel,
            is_edit=True,
        )

        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal,
        )

        logger.info(f"업체이관 편집 모달 열기 완료: {data.booking_key}")
