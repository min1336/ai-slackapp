from __future__ import annotations

from app.constants import (
    DESCRIPTION_OPTIONS,
    ISSUE_TYPE_OPTIONS,
    SELLER_CHANNEL_OPTIONS,
    ActionId,
    BlockId,
    CommonText,
    HeaderText,
    LabelText,
    find_option_by_text,
    is_transfer_description,
)
from app.constants.options import SlackOption
from app.models import SettlementData

Block = dict[str, object]
Blocks = list[Block]
TextInputConfig = tuple[str, str, str, str | None, bool]


def _display_text(value: str | None) -> str:
    return value or CommonText.NONE


def _display_cost(value: int | None) -> str:
    """int 금액을 표시용 문자열로 변환."""
    if value is None:
        return CommonText.NONE
    return str(value)


def _add_text_inputs(blocks: Blocks, configs: list[TextInputConfig]) -> None:
    for block_id, label_text, action_id, initial_value, is_optional in configs:
        _add_text_input(
            blocks=blocks,
            block_id=block_id,
            label_text=label_text,
            action_id=action_id,
            initial_value=initial_value,
            is_optional=is_optional,
        )


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


def build_registration_modal(
    user_name: str,
    booking_key: str,
    company_name: str,
    customer_name: str,
    metadata: str,
    settlement_day: str = "",
    issue_type: str = "",
    company_sub_name: str = "",
    settlement_cost: str = "",
    carmore_cost: str = "",
    user_refund_cost: str = "",
    seller_channel: str = "",
    description: str = "",
    note: str = "",
    # 동적 폼 상태
    show_issue_type_text: bool = False,
    show_description_text: bool = False,
    custom_issue_type: str = "",
    custom_description: str = "",
) -> dict:
    """통합 등록 모달 빌더 (일반 정산 + Transfer 통합)"""
    # 동적 폼: 텍스트 입력 중이면 셀렉트 initial 설정 안함
    issue_type_initial = None
    if not show_issue_type_text and issue_type:
        issue_type_initial = find_option_by_text(ISSUE_TYPE_OPTIONS, issue_type)

    seller_channel_initial = (
        find_option_by_text(SELLER_CHANNEL_OPTIONS, seller_channel)
        if seller_channel
        else None
    )

    description_initial = None
    if not show_description_text and description:
        description_initial = find_option_by_text(DESCRIPTION_OPTIONS, description)

    blocks = _build_booking_header_blocks(user_name)

    _add_text_inputs(
        blocks,
        [
            (
                BlockId.BOOKING_KEY_BLOCK,
                f"{LabelText.BOOKING_KEY}{CommonText.REQUIRED}",
                ActionId.BOOKING_KEY_INPUT,
                booking_key,
                False,
            ),
            (
                BlockId.CUSTOMER_NAME_BLOCK,
                f"{LabelText.CUSTOMER_NAME}{CommonText.REQUIRED}",
                ActionId.CUSTOMER_NAME_INPUT,
                customer_name,
                False,
            ),
        ],
    )

    _add_datepicker_with_initial(
        blocks=blocks,
        block_id=BlockId.SETTLEMENT_DAY_BLOCK,
        label_text=LabelText.SETTLEMENT_DAY,
        action_id=ActionId.SETTLEMENT_DAY_INPUT,
        placeholder_text=CommonText.SELECT_DATE,
        initial_date=settlement_day,
    )

    # 동적 폼: 이슈사항 - "기타" 선택 시 텍스트 입력으로 전환
    if show_issue_type_text:
        _add_text_input(
            blocks=blocks,
            block_id=BlockId.ISSUE_TYPE_TEXT_BLOCK,
            label_text=f"{LabelText.ISSUE_TYPE}{CommonText.REQUIRED}",
            action_id=ActionId.ISSUE_TYPE_TEXT_INPUT,
            initial_value=custom_issue_type,
            is_optional=False,
        )
    else:
        _add_select_with_initial(
            blocks=blocks,
            block_id=BlockId.ISSUE_TYPE_BLOCK,
            label_text=LabelText.ISSUE_TYPE,
            action_id=ActionId.ISSUE_TYPE_INPUT,
            placeholder_text=CommonText.SELECT,
            options=ISSUE_TYPE_OPTIONS,
            initial_option=issue_type_initial,
            is_required=True,
            dispatch_action=True,
        )

    _add_text_inputs(
        blocks,
        [
            (
                BlockId.COMPANY_NAME_BLOCK,
                f"{LabelText.COMPANY_NAME}{CommonText.REQUIRED}",
                ActionId.COMPANY_NAME_INPUT,
                company_name,
                False,
            ),
            (
                BlockId.COMPANY_SUB_NAME_BLOCK,
                LabelText.COMPANY_SUB_NAME,
                ActionId.COMPANY_SUB_NAME_INPUT,
                company_sub_name,
                True,
            ),
            (
                BlockId.SETTLEMENT_COST_BLOCK,
                f"{LabelText.SETTLEMENT_COST}{CommonText.REQUIRED}",
                ActionId.SETTLEMENT_COST_INPUT,
                settlement_cost,
                False,
            ),
            (
                BlockId.CARMORE_COST_BLOCK,
                LabelText.CARMORE_COST,
                ActionId.CARMORE_COST_INPUT,
                carmore_cost,
                True,
            ),
            (
                BlockId.USER_REFUND_COST_BLOCK,
                LabelText.USER_REFUND_COST,
                ActionId.USER_REFUND_COST_INPUT,
                user_refund_cost,
                True,
            ),
        ],
    )

    _add_select_with_initial(
        blocks=blocks,
        block_id=BlockId.SELLER_CHANNEL_BLOCK,
        label_text=LabelText.SELLER_CHANNEL,
        action_id=ActionId.SELLER_CHANNEL_INPUT,
        placeholder_text=CommonText.SELECT,
        options=SELLER_CHANNEL_OPTIONS,
        initial_option=seller_channel_initial,
        is_required=True,
    )

    # 동적 폼: 내용 - "기타" 선택 시 텍스트 입력으로 전환
    if show_description_text:
        _add_text_input(
            blocks=blocks,
            block_id=BlockId.DESCRIPTION_TEXT_BLOCK,
            label_text=f"{LabelText.DESCRIPTION}{CommonText.REQUIRED}",
            action_id=ActionId.DESCRIPTION_TEXT_INPUT,
            initial_value=custom_description,
            is_optional=False,
        )
    else:
        _add_select_with_initial(
            blocks=blocks,
            block_id=BlockId.DESCRIPTION_BLOCK,
            label_text=LabelText.DESCRIPTION,
            action_id=ActionId.DESCRIPTION_INPUT,
            placeholder_text=CommonText.SELECT,
            options=DESCRIPTION_OPTIONS,
            initial_option=description_initial,
            is_required=True,
            dispatch_action=True,
        )

    # 비고 필드 (선택 입력, multiline)
    _add_multiline_text_input(
        blocks=blocks,
        block_id=BlockId.NOTE_BLOCK,
        label_text=LabelText.NOTE,
        action_id=ActionId.NOTE_INPUT,
        initial_value=note,
        is_optional=True,
    )

    return {
        "type": "modal",
        "callback_id": ActionId.REGISTRATION_SUBMIT,
        "private_metadata": metadata,
        "title": {"type": "plain_text", "text": HeaderText.SETTLEMENT_ISSUE_NEW},
        "submit": {"type": "plain_text", "text": CommonText.REGISTER},
        "close": {"type": "plain_text", "text": CommonText.CANCEL},
        "blocks": blocks,
    }


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
                        "text": {"type": "plain_text", "text": CommonText.REJECT},
                        "style": "danger",
                        "action_id": reject_action,
                        "value": button_data,
                    },
                ],
            }
        )

    return blocks


def _add_select_with_initial(
    blocks: Blocks,
    block_id: str,
    label_text: str,
    action_id: str,
    placeholder_text: str,
    options: list[SlackOption],
    initial_option: SlackOption | None = None,
    is_required: bool = True,
    dispatch_action: bool = False,
) -> None:
    """static_select 블록 초기화와 함께 추가"""
    element = {
        "type": "static_select",
        "action_id": action_id,
        "placeholder": {"type": "plain_text", "text": placeholder_text},
        "options": options,
    }

    if initial_option:
        element["initial_option"] = initial_option

    input_block: Block = {
        "type": "input",
        "block_id": block_id,
        "label": {
            "type": "plain_text",
            "text": f"{label_text}{CommonText.REQUIRED}" if is_required else label_text,
        },
        "element": element,
    }

    # dispatch_action이 True면 선택 즉시 서버에 이벤트 전송
    if dispatch_action:
        input_block["dispatch_action"] = True

    blocks.append(input_block)


def _add_text_input(
    blocks: Blocks,
    block_id: str,
    label_text: str,
    action_id: str,
    initial_value: str | None = None,
    is_optional: bool = False,
) -> None:
    """text input 블록 추가"""
    element = {
        "type": "plain_text_input",
        "action_id": action_id,
    }

    if initial_value:
        element["initial_value"] = initial_value

    blocks.append(
        {
            "type": "input",
            "block_id": block_id,
            "label": {"type": "plain_text", "text": label_text},
            "optional": is_optional,
            "element": element,
        }
    )


def _add_multiline_text_input(
    blocks: Blocks,
    block_id: str,
    label_text: str,
    action_id: str,
    initial_value: str | None = None,
    is_optional: bool = True,
) -> None:
    """multiline text input 블록 추가 (비고 필드용)"""
    element: Block = {
        "type": "plain_text_input",
        "action_id": action_id,
        "multiline": True,
    }

    if initial_value:
        element["initial_value"] = initial_value

    blocks.append(
        {
            "type": "input",
            "block_id": block_id,
            "label": {"type": "plain_text", "text": label_text},
            "optional": is_optional,
            "element": element,
        }
    )


def _add_datepicker_with_initial(
    blocks: Blocks,
    block_id: str,
    label_text: str,
    action_id: str,
    placeholder_text: str,
    initial_date: str | None = None,
) -> None:
    """datepicker 블록 초기화와 함께 추가"""
    element = {
        "type": "datepicker",
        "action_id": action_id,
        "placeholder": {"type": "plain_text", "text": placeholder_text},
    }

    if initial_date:
        element["initial_date"] = initial_date

    blocks.append(
        {
            "type": "input",
            "block_id": block_id,
            "label": {
                "type": "plain_text",
                "text": f"{label_text}{CommonText.REQUIRED}",
            },
            "element": element,
        }
    )


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


def build_rejection_modal(metadata: str) -> dict:
    """반려 사유 입력 모달 빌더"""
    return {
        "type": "modal",
        "callback_id": ActionId.REJECTION_SUBMIT,
        "private_metadata": metadata,
        "title": {"type": "plain_text", "text": HeaderText.REJECTION_MODAL},
        "submit": {"type": "plain_text", "text": CommonText.REJECT},
        "close": {"type": "plain_text", "text": CommonText.CANCEL},
        "blocks": [
            {
                "type": "input",
                "block_id": BlockId.REJECTION_REASON_BLOCK,
                "label": {
                    "type": "plain_text",
                    "text": f"{LabelText.REJECTION_REASON}{CommonText.REQUIRED}",
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": ActionId.REJECTION_REASON_INPUT,
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "반려 사유를 입력하세요",
                    },
                },
            }
        ],
    }


# ============================================================================
# 승인 채널 통합 기능용 블록 빌더
# ============================================================================


def _build_minimal_base_blocks(
    requester_name: str,
    thread_url: str,
    request_type: str,
    *,
    is_pending: bool = False,
) -> Blocks:
    """승인 채널 메시지의 공통 블록 (요청자 + 스레드 링크).

    is_pending=True → header 블록 (대기 중), False → 취소선 section (완료).
    """
    if is_pending:
        header_block: Block = {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{request_type} 승인 요청"},
        }
    else:
        header_block = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"~*{request_type} 승인 요청*~"},
        }

    return [
        header_block,
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*요청자*"},
                {"type": "plain_text", "text": requester_name},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<{thread_url}|📎 원본 스레드 바로가기>",
            },
        },
    ]


def build_minimal_approval_message(
    requester_name: str,
    thread_url: str,
    button_data: str,
    is_transfer: bool = False,
) -> Blocks:
    """승인 채널용 최소 정보 메시지 (스레드 링크 + 요청자 + 버튼)"""
    request_type = "업체 이관" if is_transfer else "정산 이슈"
    approve_action = (
        ActionId.TRANSFER_APPROVE if is_transfer else ActionId.SETTLEMENT_APPROVE
    )
    reject_action = (
        ActionId.TRANSFER_REJECT if is_transfer else ActionId.SETTLEMENT_REJECT
    )

    blocks = _build_minimal_base_blocks(
        requester_name, thread_url, request_type, is_pending=True
    )
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": CommonText.APPROVE},
                    "style": "primary",
                    "action_id": approve_action,
                    "value": button_data,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": CommonText.REJECT},
                    "style": "danger",
                    "action_id": reject_action,
                    "value": button_data,
                },
            ],
        }
    )
    return blocks


def build_minimal_approved_message(
    requester_name: str,
    thread_url: str,
    approver_name: str,
    is_transfer: bool = False,
) -> Blocks:
    """승인 채널 승인 완료 메시지 (버튼 제거, 승인됨 표시)"""
    request_type = "업체 이관" if is_transfer else "정산 이슈"
    blocks = _build_minimal_base_blocks(requester_name, thread_url, request_type)
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"✅ *승인됨* | 승인자: {approver_name}",
            },
        }
    )
    return blocks


def build_minimal_processing_message(
    is_transfer: bool = False,
) -> Blocks:
    """승인 채널 처리 중 메시지 (버튼 제거, 처리 중 표시)"""
    request_type = "업체 이관" if is_transfer else "정산 이슈"
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{request_type} 승인 요청",
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "⏳ *처리 중...*"},
        },
    ]


def build_minimal_rejected_message(
    requester_name: str,
    thread_url: str,
    rejecter_name: str,
    is_transfer: bool = False,
) -> Blocks:
    """승인 채널 반려 완료 메시지 (버튼 제거, 반려됨 표시)"""
    request_type = "업체 이관" if is_transfer else "정산 이슈"
    blocks = _build_minimal_base_blocks(requester_name, thread_url, request_type)
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"❌ *반려됨* | 반려자: {rejecter_name}",
            },
        }
    )
    return blocks
