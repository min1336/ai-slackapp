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


def build_parsing_result_message(
    booking_key: str,
    company_name: str,
    customer_name: str,
    button_value: str,
) -> list[dict]:
    return [
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{LabelText.BOOKING_KEY}*"},
                {
                    "type": "plain_text",
                    "text": booking_key or CommonText.NONE,
                },
                {"type": "mrkdwn", "text": f"*{LabelText.COMPANY_NAME}*"},
                {
                    "type": "plain_text",
                    "text": company_name or CommonText.NONE,
                },
                {"type": "mrkdwn", "text": f"*{LabelText.BOOKER_NAME}*"},
                {
                    "type": "plain_text",
                    "text": customer_name or CommonText.NONE,
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
    is_edit: bool = False,
) -> dict:
    issue_type_initial = (
        find_option_by_text(ISSUE_TYPE_OPTIONS, issue_type) if issue_type else None
    )
    seller_channel_initial = (
        find_option_by_text(SELLER_CHANNEL_OPTIONS, seller_channel)
        if seller_channel
        else None
    )
    description_initial = (
        find_option_by_text(DESCRIPTION_OPTIONS, description) if description else None
    )

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": HeaderText.BOOKING_INFO},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{LabelText.USER_NAME}*"},
                {"type": "plain_text", "text": user_name},
                {"type": "mrkdwn", "text": f"*{LabelText.BOOKING_KEY}*"},
                {
                    "type": "plain_text",
                    "text": booking_key or CommonText.NONE,
                },
                {"type": "mrkdwn", "text": f"*{LabelText.COMPANY_NAME}*"},
                {
                    "type": "plain_text",
                    "text": company_name or CommonText.NONE,
                },
                {"type": "mrkdwn", "text": f"*{LabelText.CUSTOMER_NAME}*"},
                {
                    "type": "plain_text",
                    "text": customer_name or CommonText.NONE,
                },
            ],
        },
        {"type": "divider"},
    ]

    _add_datepicker_with_initial(
        blocks=blocks,
        block_id=BlockId.SETTLEMENT_DAY_BLOCK,
        label_text=LabelText.SETTLEMENT_DAY,
        action_id=ActionId.SETTLEMENT_DAY_INPUT,
        placeholder_text=CommonText.SELECT_DATE,
        initial_date=settlement_day,
    )

    _add_select_with_initial(
        blocks=blocks,
        block_id=BlockId.ISSUE_TYPE_BLOCK,
        label_text=LabelText.ISSUE_TYPE,
        action_id=ActionId.ISSUE_TYPE_INPUT,
        placeholder_text=CommonText.SELECT,
        options=ISSUE_TYPE_OPTIONS,
        initial_option=issue_type_initial,
        is_required=True,
    )

    _add_text_input(
        blocks=blocks,
        block_id=BlockId.COMPANY_SUB_NAME_BLOCK,
        label_text=LabelText.COMPANY_SUB_NAME,
        action_id=ActionId.COMPANY_SUB_NAME_INPUT,
        initial_value=company_sub_name,
        is_optional=True,
    )

    _add_text_input(
        blocks=blocks,
        block_id=BlockId.SETTLEMENT_COST_BLOCK,
        label_text=f"{LabelText.SETTLEMENT_COST}{CommonText.REQUIRED}",
        action_id=ActionId.SETTLEMENT_COST_INPUT,
        initial_value=settlement_cost,
    )

    _add_text_input(
        blocks=blocks,
        block_id=BlockId.CARMORE_COST_BLOCK,
        label_text=LabelText.CARMORE_COST,
        action_id=ActionId.CARMORE_COST_INPUT,
        initial_value=carmore_cost,
        is_optional=True,
    )

    _add_text_input(
        blocks=blocks,
        block_id=BlockId.USER_REFUND_COST_BLOCK,
        label_text=LabelText.USER_REFUND_COST,
        action_id=ActionId.USER_REFUND_COST_INPUT,
        initial_value=user_refund_cost,
        is_optional=True,
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

    _add_select_with_initial(
        blocks=blocks,
        block_id=BlockId.DESCRIPTION_BLOCK,
        label_text=LabelText.DESCRIPTION,
        action_id=ActionId.DESCRIPTION_INPUT,
        placeholder_text=CommonText.SELECT,
        options=DESCRIPTION_OPTIONS,
        initial_option=description_initial,
        is_required=True,
    )

    return {
        "type": "modal",
        "callback_id": ActionId.REGISTRATION_SUBMIT,
        "private_metadata": metadata,
        "title": {
            "type": "plain_text",
            "text": HeaderText.SETTLEMENT_ISSUE_EDIT
            if is_edit
            else HeaderText.SETTLEMENT_ISSUE_NEW,
        },
        "submit": {
            "type": "plain_text",
            "text": CommonText.MODIFIED if is_edit else CommonText.REGISTER,
        },
        "close": {"type": "plain_text", "text": CommonText.CANCEL},
        "blocks": blocks,
    }


def build_approval_request_message(
    user_name: str,
    booking_key: str,
    company_name: str,
    customer_name: str,
    settlement_day: str,
    issue_type: str,
    settlement_cost: str,
    company_sub_name: str,
    carmore_cost: str,
    user_refund_cost: str,
    seller_channel: str,
    description: str,
    button_data: str,
) -> list[dict]:
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": HeaderText.SETTLEMENT_ISSUE_REGISTER,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{LabelText.USER_NAME}*"},
                {"type": "plain_text", "text": user_name},
                {"type": "mrkdwn", "text": f"*{LabelText.BOOKING_KEY}*"},
                {
                    "type": "plain_text",
                    "text": booking_key or CommonText.NONE,
                },
                {"type": "mrkdwn", "text": f"*{LabelText.COMPANY_NAME}*"},
                {
                    "type": "plain_text",
                    "text": company_name or CommonText.NONE,
                },
                {"type": "mrkdwn", "text": f"*{LabelText.CUSTOMER_NAME}*"},
                {
                    "type": "plain_text",
                    "text": customer_name or CommonText.NONE,
                },
                {"type": "mrkdwn", "text": f"*{LabelText.SETTLEMENT_DAY}*"},
                {
                    "type": "plain_text",
                    "text": settlement_day or CommonText.NONE,
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
                    "text": settlement_cost or CommonText.NONE,
                },
                {
                    "type": "mrkdwn",
                    "text": f"*{LabelText.COMPANY_SUB_NAME}*",
                },
                {
                    "type": "plain_text",
                    "text": company_sub_name or CommonText.NONE,
                },
                {"type": "mrkdwn", "text": f"*{LabelText.CARMORE_COST}*"},
                {
                    "type": "plain_text",
                    "text": carmore_cost or CommonText.NONE,
                },
                {
                    "type": "mrkdwn",
                    "text": f"*{LabelText.USER_REFUND_COST}*",
                },
                {
                    "type": "plain_text",
                    "text": user_refund_cost or CommonText.NONE,
                },
                {"type": "mrkdwn", "text": f"*{LabelText.SELLER_CHANNEL}*"},
                {
                    "type": "plain_text",
                    "text": seller_channel or CommonText.NONE,
                },
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{LabelText.ISSUE_TYPE}*\n{issue_type or CommonText.NONE}\n\n*{LabelText.DESCRIPTION}*\n{description or CommonText.NONE}",
            },
        },
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
                    "action_id": ActionId.SETTLEMENT_APPROVE,
                    "value": button_data,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": CommonText.REJECT},
                    "style": "danger",
                    "action_id": ActionId.SETTLEMENT_REJECT,
                    "value": button_data,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": CommonText.EDIT},
                    "action_id": ActionId.SETTLEMENT_EDIT,
                    "value": button_data,
                },
            ],
        },
    ]


def _add_select_with_initial(
    blocks: list[dict],
    block_id: str,
    label_text: str,
    action_id: str,
    placeholder_text: str,
    options: list[dict],
    initial_option: dict | None = None,
    is_required: bool = True,
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

    blocks.append(
        {
            "type": "input",
            "block_id": block_id,
            "label": {
                "type": "plain_text",
                "text": f"{label_text}{CommonText.REQUIRED}"
                if is_required
                else label_text,
            },
            "element": element,
        }
    )


def _add_text_input(
    blocks: list[dict],
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


def _add_datepicker_with_initial(
    blocks: list[dict],
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


def build_approved_message(
    original_blocks: list[dict], approver_name: str
) -> list[dict]:
    new_blocks = [b for b in original_blocks if b.get("type") != "actions"]
    new_blocks[0] = {
        "type": "header",
        "text": {"type": "plain_text", "text": HeaderText.APPROVED},
    }
    new_blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"승인자: *{approver_name}*"}],
        }
    )
    return new_blocks


def build_rejected_message(
    original_blocks: list[dict], rejecter_name: str
) -> list[dict]:
    new_blocks = [b for b in original_blocks if b.get("type") != "actions"]
    new_blocks[0] = {
        "type": "header",
        "text": {"type": "plain_text", "text": HeaderText.REJECTED},
    }
    new_blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"반려자: *{rejecter_name}*"}],
        }
    )
    return new_blocks
