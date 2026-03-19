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
)
from app.constants.options import Description, IssueType, SlackOption
from app.views.blocks import (
    Block,
    Blocks,
    TextInputConfig,
    _build_booking_header_blocks,
)


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
    seller_channel_cost: str = "",
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
    # 동적 폼: "기타" 모드일 때 셀렉트에 "기타" 선택됨 표시
    issue_type_initial = None
    if show_issue_type_text:
        issue_type_initial = IssueType.OTHER.to_slack_option()
    elif issue_type:
        issue_type_initial = find_option_by_text(ISSUE_TYPE_OPTIONS, issue_type)

    seller_channel_initial = (
        find_option_by_text(SELLER_CHANNEL_OPTIONS, seller_channel)
        if seller_channel
        else None
    )

    description_initial = None
    if show_description_text:
        description_initial = Description.OTHER.to_slack_option()
    elif description:
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

    _add_datepicker_with_initial(
        blocks=blocks,
        block_id=BlockId.SETTLEMENT_DAY_BLOCK,
        label_text=LabelText.SETTLEMENT_DAY,
        action_id=ActionId.SETTLEMENT_DAY_INPUT,
        placeholder_text=CommonText.SELECT_DATE,
        initial_date=settlement_day,
    )

    # 동적 폼: 이슈사항 - 셀렉트 항상 렌더링, "기타" 선택 시 텍스트 입력 추가
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
    if show_issue_type_text:
        _add_text_input(
            blocks=blocks,
            block_id=BlockId.ISSUE_TYPE_TEXT_BLOCK,
            label_text=f"{LabelText.ISSUE_TYPE} - 직접 입력{CommonText.REQUIRED}",
            action_id=ActionId.ISSUE_TYPE_TEXT_INPUT,
            initial_value=custom_issue_type,
            is_optional=False,
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
                BlockId.SELLER_CHANNEL_COST_BLOCK,
                LabelText.SELLER_CHANNEL_COST,
                ActionId.SELLER_CHANNEL_COST_INPUT,
                seller_channel_cost,
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

    # 동적 폼: 내용 - 셀렉트 항상 렌더링, "기타" 선택 시 텍스트 입력 추가
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
    if show_description_text:
        _add_text_input(
            blocks=blocks,
            block_id=BlockId.DESCRIPTION_TEXT_BLOCK,
            label_text=f"{LabelText.DESCRIPTION} - 직접 입력{CommonText.REQUIRED}",
            action_id=ActionId.DESCRIPTION_TEXT_INPUT,
            initial_value=custom_description,
            is_optional=False,
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


def build_rejection_modal(metadata: str) -> dict:
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
                    "text": (f"{LabelText.REJECTION_REASON}{CommonText.REQUIRED}"),
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
