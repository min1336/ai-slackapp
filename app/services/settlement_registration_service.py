from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from pydantic import ValidationError
from slack_sdk.errors import SlackApiError

from app.constants import is_transfer_description, request_type_label
from app.constants.ui_texts import HeaderText
from app.core import get_logger
from app.exceptions import AppError
from app.models import SettlementData, SettlementStatus
from app.views.blocks import (
    build_approval_request_message,
    build_minimal_approval_message,
)

if TYPE_CHECKING:
    from app.infrastructure.protocols import (
        SlackMessageReader,
        SlackMessageWriter,
    )
    from app.services.settlement_writer import SettlementWriter
    from app.services.transfer_lifecycle_service import TransferLifecycleService

logger = get_logger(__name__)


class SettlementRegistrationService:
    def __init__(
        self,
        reader: SlackMessageReader,
        writer: SlackMessageWriter,
        settlement_writer: SettlementWriter,
        approval_channel_id: str,
        transfer_lifecycle: TransferLifecycleService | None = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._settlement_writer = settlement_writer
        self._approval_channel_id = approval_channel_id
        self._transfer_lifecycle = transfer_lifecycle

    def register(
        self,
        *,
        data: SettlementData,
        channel_id: str,
        thread_ts: str,
        requester_id: str,
    ) -> None:
        is_transfer = is_transfer_description(data.description or "")
        request_type = request_type_label(is_transfer)
        title = (
            HeaderText.TRANSFER_REGISTER
            if is_transfer
            else HeaderText.SETTLEMENT_ISSUE_REGISTER
        )
        approval_channel_id = self._approval_channel_id

        detail_message_ts = ""
        try:
            # 1. 원본 스레드에 상세 정보 메시지 게시 (버튼 없이)
            detail_blocks = build_approval_request_message(
                data, title=title, include_buttons=False
            )
            detail_message_ts = self._writer.post_message(
                channel=channel_id,
                thread_ts=thread_ts or None,
                text=f"{request_type} 승인 요청",
                blocks=detail_blocks,
            )

            # 2. 상세 메시지의 permalink 생성
            message_url = self._reader.get_thread_url(channel_id, detail_message_ts)

            # 3. SettlementData에 원본 스레드 정보 추가
            data.original_channel_id = channel_id
            data.original_thread_ts = thread_ts
            data.original_message_ts = detail_message_ts

            # 3.5 요청 시점에 DB + 시트 기록
            self._save_to_db_safe(data, thread_url=message_url)

            # 3.6 이관 건이면 기존 정산 이관 처리
            self._mark_transfer_safe(data.booking_key)

            # 4. 요청자 이름 조회
            requester_name = self._reader.get_user_name(requester_id)

            # 5. 승인 채널에 최소 정보 + 버튼 + 상세 메시지 링크 게시
            approval_blocks = build_minimal_approval_message(
                requester_name=requester_name,
                thread_url=message_url,
                button_data=data.model_dump_json(),
                is_transfer=is_transfer,
            )
            self._writer.post_message(
                channel=approval_channel_id,
                text=f"{request_type} 승인 요청",
                blocks=approval_blocks,
            )
        except ValidationError:
            logger.exception("registration_validation_failed")
            self._cleanup_detail_message(channel_id, detail_message_ts)
            self._notify_user_safe(
                requester_id,
                "⚠️ 입력값이 올바르지 않습니다. 다시 시도해주세요.",
            )
        except SlackApiError:
            logger.exception("registration_slack_api_failed")
            self._cleanup_detail_message(channel_id, detail_message_ts)
            self._notify_user_safe(
                requester_id,
                f"⚠️ {request_type} 등록 중 슬랙 통신 오류가 발생했습니다.",
            )

    def _save_to_db_safe(self, data: SettlementData, *, thread_url: str) -> None:
        """DB + 시트에 요청 저장 (best-effort)."""
        try:
            self._settlement_writer.save(
                data=data,
                status=SettlementStatus.REQUESTED,
                approver_name="",
                thread_url=thread_url,
            )
        except AppError as e:
            logger.warning(
                "request_save_failed",
                booking_key=data.booking_key,
                error_type=type(e).__name__,
                error=str(e),
            )

    def _mark_transfer_safe(self, booking_key: str) -> None:
        """이관 건이면 기존 정산을 이관 처리한다 (best-effort)."""
        if self._transfer_lifecycle is None:
            return
        try:
            self._transfer_lifecycle.mark_transferred(booking_key)
        except Exception:
            logger.warning("transfer_mark_failed", booking_key=booking_key)

    def _cleanup_detail_message(self, channel_id: str, detail_message_ts: str) -> None:
        if not detail_message_ts:
            return
        with suppress(SlackApiError):
            self._writer.delete_message(channel=channel_id, ts=detail_message_ts)

    def _notify_user_safe(self, user_id: str, message: str) -> None:
        if not user_id:
            return
        with suppress(SlackApiError):
            self._writer.post_message(channel=user_id, text=message)
