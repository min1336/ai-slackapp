from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from slack_sdk.errors import SlackApiError

from app.constants import is_transfer_description, request_type_label
from app.constants.ui_texts import HeaderText
from app.core import get_logger
from app.exceptions import AlreadyProcessedError, AppError, SettlementCompletedError
from app.models import (
    RejectionMetadata,
    SettlementData,
    SettlementStatus,
)
from app.views.blocks import (
    build_approval_request_message,
    build_minimal_approval_message,
    build_minimal_processing_message,
    build_minimal_rejected_message,
    build_rejected_message,
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


class RejectionService:
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

    def reject(
        self,
        *,
        data: SettlementData,
        metadata: RejectionMetadata,
        rejection_reason: str,
        rejecter_id: str,
    ) -> None:
        processing_shown = False
        original_approval_blocks: list = []

        try:
            is_transfer = is_transfer_description(data.description or "")
            request_type = request_type_label(is_transfer)
            title = (
                HeaderText.TRANSFER_REGISTER
                if is_transfer
                else HeaderText.SETTLEMENT_ISSUE_REGISTER
            )

            rejecter_name = self._reader.get_user_name(rejecter_id)
            requester_name = self._reader.get_user_name(metadata.requester_id)
            message_url = self._reader.get_thread_url(
                metadata.original_channel_id,
                metadata.original_message_ts,
            )

            original_approval_blocks = build_minimal_approval_message(
                requester_name=requester_name,
                thread_url=message_url,
                button_data=metadata.button_data,
                is_transfer=is_transfer,
            )

            self._show_processing(metadata, is_transfer)
            processing_shown = True

            self._guard_settlement_completed(data.booking_key)

            self._settlement_writer.save(
                data=data,
                status=SettlementStatus.REJECTED,
                approver_name=rejecter_name,
                thread_url=message_url,
                rejection_reason=rejection_reason,
            )

            self._update_approval_channel(
                metadata,
                requester_name,
                message_url,
                rejecter_name,
                request_type,
                is_transfer,
            )
            self._update_original_thread(
                data,
                metadata,
                title,
                rejecter_name,
                rejection_reason,
                request_type,
            )
            self._mention_requester(metadata, request_type, rejection_reason)

            logger.info("rejection_completed", booking_key=data.booking_key)
        except AlreadyProcessedError as e:
            logger.info(
                "rejection_already_processed",
                booking_key=data.booking_key,
            )
            self._restore_rejection(
                metadata,
                original_approval_blocks,
                processing_shown,
            )
            self._notify_user_safe(rejecter_id, e.user_message)
        except AppError as e:
            logger.exception("rejection_failed", booking_key=data.booking_key)
            self._restore_rejection(
                metadata,
                original_approval_blocks,
                processing_shown,
            )
            self._notify_user_safe(rejecter_id, e.user_message)
        except SlackApiError:
            logger.exception("slack_api_failed")
            self._restore_rejection(
                metadata,
                original_approval_blocks,
                processing_shown,
            )
            self._notify_user_safe(
                rejecter_id,
                "⚠️ 슬랙 통신 오류가 발생했습니다.",
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

    def _show_processing(self, metadata: RejectionMetadata, is_transfer: bool) -> None:
        self._writer.update_message(
            channel=metadata.channel_id,
            ts=metadata.message_ts,
            text="처리 중...",
            blocks=build_minimal_processing_message(is_transfer=is_transfer),
        )

    def _update_approval_channel(
        self,
        metadata: RejectionMetadata,
        requester_name: str,
        message_url: str,
        rejecter_name: str,
        request_type: str,
        is_transfer: bool,
    ) -> None:
        approval_blocks = build_minimal_rejected_message(
            requester_name=requester_name,
            thread_url=message_url,
            rejecter_name=rejecter_name,
            is_transfer=is_transfer,
        )
        self._writer.update_message(
            channel=metadata.channel_id,
            ts=metadata.message_ts,
            text=f"{request_type} 반려됨",
            blocks=approval_blocks,
        )

    def _update_original_thread(
        self,
        data: SettlementData,
        metadata: RejectionMetadata,
        title: str,
        rejecter_name: str,
        rejection_reason: str,
        request_type: str,
    ) -> None:
        detail_blocks = build_approval_request_message(
            data, title=title, include_buttons=False
        )
        thread_blocks = build_rejected_message(
            detail_blocks, rejecter_name, rejection_reason
        )
        self._writer.update_message(
            channel=metadata.original_channel_id,
            ts=metadata.original_message_ts,
            text=f"{request_type} 반려됨",
            blocks=thread_blocks,
        )

    def _mention_requester(
        self,
        metadata: RejectionMetadata,
        request_type: str,
        rejection_reason: str,
    ) -> None:
        if metadata.requester_id:
            self._writer.post_message(
                channel=metadata.original_channel_id,
                thread_ts=metadata.original_thread_ts or None,
                text=(
                    f"<@{metadata.requester_id}>"
                    f" {request_type}가 반려되었습니다.\n"
                    f"*반려 사유:* {rejection_reason}"
                ),
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

    def _restore_rejection(
        self,
        metadata: RejectionMetadata | None,
        original_blocks: list,
        processing_shown: bool,
    ) -> None:
        if not (processing_shown and metadata and original_blocks):
            return
        with suppress(SlackApiError):
            self._writer.update_message(
                channel=metadata.channel_id,
                ts=metadata.message_ts,
                text="승인 요청",
                blocks=original_blocks,
            )

    def _notify_user_safe(self, user_id: str, message: str) -> None:
        if not user_id:
            return
        with suppress(SlackApiError):
            self._writer.post_message(channel=user_id, text=message)
