from __future__ import annotations

from pydantic import ValidationError
from slack_bolt import App
from slack_sdk.errors import SlackApiError

from app.config import get_app_config
from app.constants import ActionId, BlockId, is_transfer_description
from app.constants.ui_texts import HeaderText
from app.core import get_logger
from app.models import (
    ModalMetadata,
    RejectionMetadata,
    SettlementData,
    SettlementStatus,
)
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
    build_minimal_approval_message,
    build_minimal_processing_message,
    build_minimal_rejected_message,
    build_rejected_message,
)

logger = get_logger(__name__)


def register_view_handlers(app: App) -> None:
    @app.view(ActionId.REGISTRATION_SUBMIT)
    def handle_registration_submit(ack, client, view, body):
        ack()

        metadata = ModalMetadata.model_validate_json(view.get("private_metadata", "{}"))
        values = view.get("state", {}).get("values", {})
        text_value = extract_text_value
        date_value = extract_date_value
        select_value = extract_select_value

        # user_name: input 필드 값이 없으면 metadata에서 사용 (업체이관의 경우)
        user_name_from_input = text_value(
            values, BlockId.USER_NAME_BLOCK, ActionId.USER_NAME_INPUT
        )
        user_name = user_name_from_input if user_name_from_input else metadata.user_name

        # 동적 폼: 텍스트 입력 우선, 없으면 셀렉트 값 사용
        issue_type = text_value(
            values, BlockId.ISSUE_TYPE_TEXT_BLOCK, ActionId.ISSUE_TYPE_TEXT_INPUT
        ) or select_value(values, BlockId.ISSUE_TYPE_BLOCK, ActionId.ISSUE_TYPE_INPUT)

        description = text_value(
            values, BlockId.DESCRIPTION_TEXT_BLOCK, ActionId.DESCRIPTION_TEXT_INPUT
        ) or select_value(values, BlockId.DESCRIPTION_BLOCK, ActionId.DESCRIPTION_INPUT)

        # 비고 필드
        note = text_value(values, BlockId.NOTE_BLOCK, ActionId.NOTE_INPUT) or None

        # 모달 제출자 ID 저장
        requester_id = body.get("user", {}).get("id", "")

        data = SettlementData(
            user_name=user_name,
            booking_key=text_value(
                values, BlockId.BOOKING_KEY_BLOCK, ActionId.BOOKING_KEY_INPUT
            ),
            company_name=text_value(
                values, BlockId.COMPANY_NAME_BLOCK, ActionId.COMPANY_NAME_INPUT
            ),
            customer_name=text_value(
                values, BlockId.CUSTOMER_NAME_BLOCK, ActionId.CUSTOMER_NAME_INPUT
            ),
            settlement_day=date_value(
                values, BlockId.SETTLEMENT_DAY_BLOCK, ActionId.SETTLEMENT_DAY_INPUT
            ),
            issue_type=issue_type,
            settlement_cost=text_value(
                values, BlockId.SETTLEMENT_COST_BLOCK, ActionId.SETTLEMENT_COST_INPUT
            ),
            company_sub_name=text_value(
                values,
                BlockId.COMPANY_SUB_NAME_BLOCK,
                ActionId.COMPANY_SUB_NAME_INPUT,
            )
            or None,
            carmore_cost=text_value(
                values, BlockId.CARMORE_COST_BLOCK, ActionId.CARMORE_COST_INPUT
            ),
            user_refund_cost=text_value(
                values,
                BlockId.USER_REFUND_COST_BLOCK,
                ActionId.USER_REFUND_COST_INPUT,
            ),
            seller_channel=select_value(
                values, BlockId.SELLER_CHANNEL_BLOCK, ActionId.SELLER_CHANNEL_INPUT
            )
            or None,
            description=description or None,
            note=note,
            requester_id=requester_id,
        )

        # description으로 업체이관 여부 판단
        is_transfer = is_transfer_description(data.description or "")
        request_type = "업체 이관" if is_transfer else "정산 이슈"
        title = (
            HeaderText.TRANSFER_REGISTER
            if is_transfer
            else HeaderText.SETTLEMENT_ISSUE_REGISTER
        )

        # 승인 채널 ID
        approval_channel_id = get_app_config().approval_channel_id

        detail_message_ts = ""
        try:
            # 1. 원본 스레드에 상세 정보 메시지 게시 (버튼 없이)
            detail_blocks = build_approval_request_message(
                data, title=title, include_buttons=False
            )
            detail_response = client.chat_postMessage(
                channel=metadata.channel_id,
                thread_ts=metadata.thread_ts or None,
                text=f"{request_type} 승인 요청",
                blocks=detail_blocks,
            )
            detail_message_ts = detail_response.get("ts", "")

            # 2. 상세 메시지의 permalink 생성
            message_url = get_thread_url(client, metadata.channel_id, detail_message_ts)

            # 3. SettlementData에 원본 스레드 정보 추가
            data.original_channel_id = metadata.channel_id
            data.original_thread_ts = metadata.thread_ts
            data.original_message_ts = detail_message_ts

            # 3.5 요청 시점에 DB + 시트 기록
            try:
                save_settlement(
                    data=data,
                    status=SettlementStatus.REQUESTED,
                    approver_name="",
                    thread_url=message_url,
                )
            except Exception:
                logger.warning("request_save_failed", booking_key=data.booking_key)

            # 4. 요청자 이름 조회
            requester_name = get_user_name(client, requester_id)

            # 5. 승인 채널에 최소 정보 + 버튼 + 상세 메시지 링크 게시
            approval_blocks = build_minimal_approval_message(
                requester_name=requester_name,
                thread_url=message_url,
                button_data=data.model_dump_json(),
                is_transfer=is_transfer,
            )
            client.chat_postMessage(
                channel=approval_channel_id,
                text=f"{request_type} 승인 요청",
                blocks=approval_blocks,
            )
        except (SlackApiError, ValidationError, KeyError):
            logger.exception("registration_submit_failed")
            # 부분 실패 시 상세 메시지 삭제 (rollback)
            if detail_message_ts:
                try:
                    client.chat_delete(
                        channel=metadata.channel_id,
                        ts=detail_message_ts,
                    )
                except SlackApiError:
                    logger.warning("detail_message_delete_failed")
            # 사용자에게 에러 알림
            if requester_id:
                try:
                    client.chat_postMessage(
                        channel=requester_id,
                        text=f"⚠️ {request_type} 등록 중 오류가 발생했습니다. "
                        "다시 시도해주세요.",
                    )
                except SlackApiError:
                    logger.exception("error_notification_failed")

    @app.view(ActionId.REJECTION_SUBMIT)
    def handle_rejection_submit(ack, client, view, body):
        """반려 사유 제출 핸들러"""
        ack()

        try:
            # 메타데이터 파싱
            metadata = RejectionMetadata.model_validate_json(
                view.get("private_metadata", "{}")
            )

            # 반려 사유 추출
            values = view.get("state", {}).get("values", {})
            rejection_reason = extract_text_value(
                values, BlockId.REJECTION_REASON_BLOCK, ActionId.REJECTION_REASON_INPUT
            )

            # 반려자 정보
            rejecter_id = body.get("user", {}).get("id", "")
            rejecter_name = get_user_name(client, rejecter_id)

            # 버튼 데이터에서 SettlementData 복원
            data = SettlementData.model_validate_json(metadata.button_data)

            # 업체이관 여부 판단
            is_transfer = is_transfer_description(data.description or "")
            request_type = "업체 이관" if is_transfer else "정산 이슈"
            title = (
                HeaderText.TRANSFER_REGISTER
                if is_transfer
                else HeaderText.SETTLEMENT_ISSUE_REGISTER
            )

            # 즉시 처리 중 상태 표시 (버튼 제거 + 중복 클릭 방지)
            client.chat_update(
                channel=metadata.channel_id,
                ts=metadata.message_ts,
                text="처리 중...",
                blocks=build_minimal_processing_message(is_transfer=is_transfer),
            )

            # 상세 메시지 URL (원본 스레드의 상세 메시지)
            message_url = get_thread_url(
                client, metadata.original_channel_id, metadata.original_message_ts
            )

            # DB에 반려 저장
            save_settlement(
                data=data,
                status=SettlementStatus.REJECTED,
                approver_name=rejecter_name,
                thread_url=message_url,
                rejection_reason=rejection_reason,
            )

            # 1) 승인 채널 메시지 업데이트
            requester_name = get_user_name(client, metadata.requester_id)
            approval_blocks = build_minimal_rejected_message(
                requester_name=requester_name,
                thread_url=message_url,
                rejecter_name=rejecter_name,
                is_transfer=is_transfer,
            )
            client.chat_update(
                channel=metadata.channel_id,
                ts=metadata.message_ts,
                text=f"{request_type} 반려됨",
                blocks=approval_blocks,
            )

            # 2) 원본 스레드 상세 메시지 업데이트 (상세 정보 유지 + 반려 상태)
            original_blocks = build_approval_request_message(
                data, title=title, include_buttons=False
            )
            thread_blocks = build_rejected_message(
                original_blocks, rejecter_name, rejection_reason
            )
            client.chat_update(
                channel=metadata.original_channel_id,
                ts=metadata.original_message_ts,
                text=f"{request_type} 반려됨",
                blocks=thread_blocks,
            )

            # 3) 원본 스레드에 요청자 멘션
            if metadata.requester_id:
                client.chat_postMessage(
                    channel=metadata.original_channel_id,
                    thread_ts=metadata.original_thread_ts or None,
                    text=(
                        f"<@{metadata.requester_id}> {request_type}가 반려되었습니다.\n"
                        f"*반려 사유:* {rejection_reason}"
                    ),
                )

            logger.info("rejection_completed", booking_key=data.booking_key)
        except (SlackApiError, ValidationError, KeyError):
            logger.exception("rejection_submit_failed")
            # 사용자에게 에러 알림 (ephemeral 메시지는 view에서 불가, DM으로 전송)
            rejecter_id = body.get("user", {}).get("id", "")
            if rejecter_id:
                try:
                    client.chat_postMessage(
                        channel=rejecter_id,
                        text="⚠️ 반려 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
                    )
                except SlackApiError:
                    logger.exception("error_notification_failed")
