from __future__ import annotations

from pydantic import ValidationError
from slack_bolt import App
from slack_sdk.errors import SlackApiError

from app.constants import ActionId, BlockId, HeaderText, is_transfer_description
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
from app.views.blocks import build_approval_request_message, build_rejected_message

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
        note = text_value(values, BlockId.NOTE_BLOCK, ActionId.NOTE_INPUT)

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
            ),
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
            ),
            description=description,
            note=note,
            requester_id=requester_id,
        )

        # description으로 업체이관 여부 판단하여 적절한 title 전달
        title = (
            HeaderText.TRANSFER_REGISTER
            if is_transfer_description(data.description)
            else HeaderText.SETTLEMENT_ISSUE_REGISTER
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
            title=title,
            note=data.note,
        )

        if metadata.message_ts:
            client.chat_update(
                channel=metadata.channel_id,
                ts=metadata.message_ts,
                text="정산 이슈 수정됨",
                blocks=blocks,
            )
        else:
            client.chat_postMessage(
                channel=metadata.channel_id,
                thread_ts=metadata.thread_ts or None,
                text="정산 이슈 승인 요청",
                blocks=blocks,
            )

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

            # 스레드 URL
            thread_url = get_thread_url(client, metadata.channel_id, metadata.thread_ts)

            # DB에 반려 저장
            save_settlement(
                data=data,
                status=SettlementStatus.REJECTED,
                approver_name=rejecter_name,
                thread_url=thread_url,
                rejection_reason=rejection_reason,
            )

            # SettlementData로 원본 형식의 블록 재생성 (스레드 메시지 조회 대신)
            title = (
                HeaderText.TRANSFER_REGISTER
                if is_transfer_description(data.description)
                else HeaderText.SETTLEMENT_ISSUE_REGISTER
            )
            original_blocks = build_approval_request_message(
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
                button_data="",  # 반려 메시지에서는 버튼 제거됨
                title=title,
                note=data.note,
            )

            # 승인 요청 메시지 업데이트 (반려 사유는 멘션 메시지에서만 표시)
            new_blocks = build_rejected_message(
                original_blocks=original_blocks,
                rejecter_name=rejecter_name,
            )
            client.chat_update(
                channel=metadata.channel_id,
                ts=metadata.message_ts,
                text="정산 이슈 반려됨",
                blocks=new_blocks,
            )

            # 원본 스레드에 요청자 멘션 메시지
            if metadata.requester_id:
                client.chat_postMessage(
                    channel=metadata.channel_id,
                    thread_ts=metadata.thread_ts or None,
                    text=(
                        f"<@{metadata.requester_id}> 정산 이슈가 반려되었습니다.\n"
                        f"*반려 사유:* {rejection_reason}"
                    ),
                )

            logger.info("반려 처리 완료: %s", data.booking_key)
        except (SlackApiError, ValidationError, KeyError):
            logger.exception("반려 처리 중 에러 발생")
            # 사용자에게 에러 알림 (ephemeral 메시지는 view에서 불가, DM으로 전송)
            rejecter_id = body.get("user", {}).get("id", "")
            if rejecter_id:
                try:
                    client.chat_postMessage(
                        channel=rejecter_id,
                        text="⚠️ 반려 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
                    )
                except SlackApiError:
                    logger.exception("에러 알림 전송 실패")
