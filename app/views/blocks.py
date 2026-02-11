from __future__ import annotations

from app.constants import (
    ActionId,
    CommonText,
    HeaderText,
    LabelText,
    is_transfer_description,
)
from app.models import SettlementData

Block = dict[str, object]
Blocks = list[Block]
TextInputConfig = tuple[str, str, str, str | None, bool]


def _display_text(value: str | None) -> str:
    return value or CommonText.NONE


def _display_cost(value: int | None) -> str:
    if value is None:
        return CommonText.NONE
    return str(value)


def _build_booking_header_blocks(user_name: str) -> Blocks:
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": HeaderText.BOOKING_INFO},
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{LabelText.USER_NAME}*"},
                {"type": "plain_text", "text": _display_text(user_name)},
            ],
        },
    ]


def build_parsing_result_message(
    booking_key: str,
    company_name: str,
    customer_name: str,
    button_value: str,
) -> Blocks:
    return [
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{LabelText.BOOKING_KEY}*"},
                {
                    "type": "plain_text",
                    "text": _display_text(booking_key),
                },
                {"type": "mrkdwn", "text": f"*{LabelText.COMPANY_NAME}*"},
                {
                    "type": "plain_text",
                    "text": _display_text(company_name),
                },
                {"type": "mrkdwn", "text": f"*{LabelText.BOOKER_NAME}*"},
                {
                    "type": "plain_text",
                    "text": _display_text(customer_name),
                },
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": CommonText.REGISTER,
                    },
                    "style": "primary",
                    "action_id": ActionId.OPEN_REGISTRATION_MODAL,
                    "value": button_value,
                }
            ],
        },
    ]


def build_transfer_parsing_result_message(
    booking_key: str,
    customer_name: str,
    company_name: str,
    company_sub_name: str,
    settlement_cost: str,
    carmore_cost: str,
    button_value: str,
    transfer_message_url: str = "",
) -> Blocks:
    """이관 예약 파싱 결과 메시지 빌더 (통합된 1개 버튼)"""
    blocks: Blocks = [
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*이관전 예약번호*"},
                {
                    "type": "plain_text",
                    "text": _display_text(booking_key),
                },
                {"type": "mrkdwn", "text": "*업체명*"},
                {
                    "type": "plain_text",
                    "text": _display_text(company_name),
                },
                {"type": "mrkdwn", "text": f"*{LabelText.COMPANY_SUB_NAME}*"},
                {
                    "type": "plain_text",
                    "text": _display_text(company_sub_name),
                },
                {"type": "mrkdwn", "text": f"*{LabelText.BOOKER_NAME}*"},
                {
                    "type": "plain_text",
                    "text": _display_text(customer_name),
                },
                {"type": "mrkdwn", "text": "*원금*"},
                {
                    "type": "plain_text",
                    "text": _display_text(settlement_cost),
                },
            ],
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*카모아 부담금*"},
                {
                    "type": "plain_text",
                    "text": _display_text(carmore_cost),
                },
            ],
        },
    ]

    if transfer_message_url:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{transfer_message_url}|이관 예약 메시지 바로가기>",
                    }
                ],
            }
        )

    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": CommonText.REGISTER,
                    },
                    "style": "primary",
                    "action_id": ActionId.OPEN_TRANSFER_MODAL,
                    "value": button_value,
                },
            ],
        },
    )

    return blocks


def build_approval_request_message(
    data: SettlementData,
    *,
    button_data: str = "",
    title: str = HeaderText.SETTLEMENT_ISSUE_REGISTER,
    include_buttons: bool = True,
) -> Blocks:
    """승인 요청 상세 메시지 빌더.

    Args:
        data: 정산 데이터 (SettlementData).
        button_data: 승인/반려 버튼에 전달할 JSON 문자열.
        title: 메시지 헤더 텍스트.
        include_buttons: 승인/반려 버튼 포함 여부.
    """
    is_transfer = is_transfer_description(data.description or "")

    blocks: Blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": title,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{LabelText.USER_NAME}*"},
                {"type": "plain_text", "text": _display_text(data.user_name)},
                {"type": "mrkdwn", "text": f"*{LabelText.BOOKING_KEY}*"},
                {
                    "type": "plain_text",
                    "text": _display_text(data.booking_key),
                },
                {"type": "mrkdwn", "text": f"*{LabelText.COMPANY_NAME}*"},
                {
                    "type": "plain_text",
                    "text": _display_text(data.company_name),
                },
                {"type": "mrkdwn", "text": f"*{LabelText.CUSTOMER_NAME}*"},
                {
                    "type": "plain_text",
                    "text": _display_text(data.customer_name),
                },
                {"type": "mrkdwn", "text": f"*{LabelText.SETTLEMENT_DAY}*"},
                {
                    "type": "plain_text",
                    "text": _display_text(data.settlement_day),
                },
            ],
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*{LabelText.SETTLEMENT_COST}*",
                },
                {
                    "type": "plain_text",
                    "text": _display_cost(data.settlement_cost),
                },
                {
                    "type": "mrkdwn",
                    "text": f"*{LabelText.COMPANY_SUB_NAME}*",
                },
                {
                    "type": "plain_text",
                    "text": _display_text(data.company_sub_name),
                },
                {"type": "mrkdwn", "text": f"*{LabelText.CARMORE_COST}*"},
                {
                    "type": "plain_text",
                    "text": _display_cost(data.carmore_cost),
                },
                {
                    "type": "mrkdwn",
                    "text": f"*{LabelText.USER_REFUND_COST}*",
                },
                {
                    "type": "plain_text",
                    "text": _display_cost(data.user_refund_cost),
                },
                {"type": "mrkdwn", "text": f"*{LabelText.SELLER_CHANNEL}*"},
                {
                    "type": "plain_text",
                    "text": _display_text(data.seller_channel),
                },
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{LabelText.ISSUE_TYPE}*\n"
                    f"{data.issue_type or CommonText.NONE}\n\n"
                    f"*{LabelText.DESCRIPTION}*\n"
                    f"{data.description or CommonText.NONE}\n\n"
                    f"*{LabelText.NOTE}*\n"
                    f"{data.note or CommonText.NONE}"
                ),
            },
        },
    ]

    if include_buttons:
        approve_action = (
            ActionId.TRANSFER_APPROVE if is_transfer else ActionId.SETTLEMENT_APPROVE
        )
        reject_action = (
            ActionId.TRANSFER_REJECT if is_transfer else ActionId.SETTLEMENT_REJECT
        )
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": CommonText.APPROVE,
                        },
                        "style": "primary",
                        "action_id": approve_action,
                        "value": button_data,
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": CommonText.REJECT,
                        },
                        "style": "danger",
                        "action_id": reject_action,
                        "value": button_data,
                    },
                ],
            }
        )

    return blocks


def build_approved_message(original_blocks: Blocks, approver_name: str) -> Blocks:
    return _build_decision_message(
        original_blocks=original_blocks,
        header_text=HeaderText.APPROVED,
        actor_label="승인자",
        actor_name=approver_name,
    )


def build_rejected_message(
    original_blocks: Blocks,
    rejecter_name: str,
    rejection_reason: str = "",
) -> Blocks:
    return _build_decision_message(
        original_blocks=original_blocks,
        header_text=HeaderText.REJECTED,
        actor_label="반려자",
        actor_name=rejecter_name,
        rejection_reason=rejection_reason,
    )


def _build_decision_message(
    *,
    original_blocks: Blocks,
    header_text: str,
    actor_label: str,
    actor_name: str,
    rejection_reason: str = "",
) -> Blocks:
    new_blocks = [b for b in original_blocks if b.get("type") != "actions"]
    header_block = {
        "type": "header",
        "text": {"type": "plain_text", "text": header_text},
    }
    if new_blocks and new_blocks[0].get("type") == "header":
        new_blocks[0] = header_block
    else:
        new_blocks.insert(0, header_block)

    # 반려 사유가 있으면 섹션으로 추가
    if rejection_reason:
        new_blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{LabelText.REJECTION_REASON}*\n{rejection_reason}",
                },
            }
        )

    new_blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"{actor_label}: *{actor_name}*"}],
        }
    )
    return new_blocks


# ============================================================================
# Re-exports — 하위 호환성 유지
# ============================================================================

from app.views.blocks_approval_channel import (  # noqa: E402, F401
    build_minimal_approval_message,
    build_minimal_approved_message,
    build_minimal_processing_message,
    build_minimal_rejected_message,
)
from app.views.blocks_modals import (  # noqa: E402, F401
    build_registration_modal,
    build_rejection_modal,
)
