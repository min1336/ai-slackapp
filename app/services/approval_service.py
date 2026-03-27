from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError
from slack_sdk.errors import SlackApiError

from app.constants.ui_texts import HeaderText
from app.core import get_logger
from app.exceptions import AlreadyProcessedError, AppError, SettlementCompletedError
from app.models import SettlementData, SettlementStatus
from app.views.blocks import (
    build_approval_request_message,
    build_approved_message,
    build_minimal_approved_message,
    build_minimal_processing_message,
)

if TYPE_CHECKING:
    from app.infrastructure.protocols import (
        SlackMessageReader,
        SlackMessageWriter,
        SpreadsheetGateway,
    )
    from app.services.settlement_writer import SettlementWriter

logger = get_logger(__name__)

Approvers = frozenset[str]


class ApprovalService:
    def __init__(
        self,
        reader: SlackMessageReader,
        writer: SlackMessageWriter,
        settlement_writer: SettlementWriter,
        approvers: Approvers,
        sheets: SpreadsheetGateway | None = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._settlement_writer = settlement_writer
        self._approvers = approvers
        self._sheets = sheets

    def approve(
        self,
        *,
        data: SettlementData,
        user_id: str,
        channel_id: str,
        message_ts: str,
        thread_ts: str,
        original_blocks: list,
        is_transfer: bool,
    ) -> None:
        if not self.has_permission(
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            text="⚠️ 승인 권한이 없습니다.",
        ):
            return

        title = (
            HeaderText.TRANSFER_REGISTER
            if is_transfer
            else HeaderText.SETTLEMENT_ISSUE_REGISTER
        )
        approved_text = "업체이관 승인됨" if is_transfer else "정산 이슈 승인됨"
        mention_text = (
            "업체이관이 승인되었습니다."
            if is_transfer
            else "정산 이슈가 승인되었습니다."
        )

        try:
            self._show_processing(channel_id, message_ts, is_transfer)

            approver_name = self._reader.get_user_name(user_id)
            message_url = self._reader.get_thread_url(
                data.original_channel_id, data.original_message_ts
            )

            self._guard_settlement_completed(data.booking_key)

            self._settlement_writer.save(
                data=data,
                status=SettlementStatus.APPROVED,
                approver_name=approver_name,
                thread_url=message_url,
            )

            self._update_approval_channel(
                channel_id,
                message_ts,
                data,
                approver_name,
                message_url,
                approved_text,
                is_transfer,
            )
            self._update_original_thread(data, title, approver_name, approved_text)
            self._mention_requester(data, mention_text)
        except AlreadyProcessedError as e:
            logger.info("approve_already_processed", is_transfer=is_transfer)
            self._restore_and_notify(
                channel_id,
                message_ts,
                user_id,
                original_blocks,
                f"⚠️ {e.user_message}",
            )
        except AppError as e:
            logger.exception("approve_failed", is_transfer=is_transfer)
            self._restore_and_notify(
                channel_id,
                message_ts,
                user_id,
                original_blocks,
                f"⚠️ {e.user_message}",
            )
        except (SlackApiError, ValidationError, KeyError):
            logger.exception("approve_failed", is_transfer=is_transfer)
            self._restore_and_notify(
                channel_id,
                message_ts,
                user_id,
                original_blocks,
                "⚠️ 승인 처리 중 오류가 발생했습니다.",
            )

    def has_permission(
        self,
        *,
        user_id: str,
        channel_id: str,
        thread_ts: str,
        text: str,
    ) -> bool:
        if user_id in self._approvers:
            return True
        self._writer.post_ephemeral(
            channel=channel_id,
            user=user_id,
            text=text,
            thread_ts=thread_ts or None,
        )
        return False

    def _show_processing(
        self, channel_id: str, message_ts: str, is_transfer: bool
    ) -> None:
        self._writer.update_message(
            channel=channel_id,
            ts=message_ts,
            text="처리 중...",
            blocks=build_minimal_processing_message(is_transfer=is_transfer),
        )

    def _update_approval_channel(
        self,
        channel_id: str,
        message_ts: str,
        data: SettlementData,
        approver_name: str,
        message_url: str,
        approved_text: str,
        is_transfer: bool,
    ) -> None:
        requester_name = self._reader.get_user_name(data.requester_id)
        approval_blocks = build_minimal_approved_message(
            requester_name=requester_name,
            thread_url=message_url,
            approver_name=approver_name,
            is_transfer=is_transfer,
        )
        self._writer.update_message(
            channel=channel_id,
            ts=message_ts,
            text=approved_text,
            blocks=approval_blocks,
        )

    def _update_original_thread(
        self,
        data: SettlementData,
        title: str,
        approver_name: str,
        approved_text: str,
    ) -> None:
        detail_blocks = build_approval_request_message(
            data, title=title, include_buttons=False
        )
        thread_blocks = build_approved_message(detail_blocks, approver_name)
        self._writer.update_message(
            channel=data.original_channel_id,
            ts=data.original_message_ts,
            text=approved_text,
            blocks=thread_blocks,
        )

    def _mention_requester(self, data: SettlementData, mention_text: str) -> None:
        if data.requester_id:
            self._writer.post_message(
                channel=data.original_channel_id,
                thread_ts=data.original_thread_ts or None,
                text=f"<@{data.requester_id}> {mention_text}",
            )

    def _guard_settlement_completed(self, booking_key: str) -> None:
        if self._sheets is None:
            return
        if self._sheets.is_settlement_completed(booking_key):
            self._settlement_writer.mark_settlement_completed(booking_key)
            raise SettlementCompletedError(
                message=f"Settlement {booking_key} already completed in Sheets",
                details={"booking_key": booking_key, "source": "sheets"},
            )

    def _restore_and_notify(
        self,
        channel_id: str,
        message_ts: str,
        user_id: str,
        original_blocks: list,
        error_text: str,
    ) -> None:
        try:
            if original_blocks and message_ts:
                self._writer.update_message(
                    channel=channel_id,
                    ts=message_ts,
                    text="승인 요청",
                    blocks=original_blocks,
                )
        except SlackApiError:
            logger.exception(
                "restore_message_failed",
                reason="승인 에러 후 메시지 복원 실패 — 버튼이 안 보일 수 있음",
                channel_id=channel_id,
                ts=message_ts,
            )
        try:
            self._writer.post_ephemeral(
                channel=channel_id,
                user=user_id,
                text=error_text,
            )
        except SlackApiError:
            logger.exception(
                "notify_user_failed",
                reason="승인 에러 알림 전송 실패 — 사용자가 모를 수 있음",
                channel_id=channel_id,
                user_id=user_id,
            )
