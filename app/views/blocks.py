from __future__ import annotations

from app.views.options import (
    ISSUE_TYPE_OPTIONS,
    SELLER_CHANNEL_OPTIONS,
    DESCRIPTION_OPTIONS,
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
                {"type": "mrkdwn", "text": "*예약번호*"},
                {"type": "plain_text", "text": booking_key or "(없음)"},
                {"type": "mrkdwn", "text": "*업체명*"},
                {"type": "plain_text", "text": company_name or "(없음)"},
                {"type": "mrkdwn", "text": "*예약자명*"},
                {"type": "plain_text", "text": customer_name or "(없음)"},
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "등록"},
                    "style": "primary",
                    "action_id": "open_registration_modal",
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
    # 편집 모드용 기존 값들
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
    issue_type_initial = find_option_by_text(ISSUE_TYPE_OPTIONS, issue_type) if issue_type else None
    seller_channel_initial = find_option_by_text(SELLER_CHANNEL_OPTIONS, seller_channel) if seller_channel else None
    description_initial = find_option_by_text(DESCRIPTION_OPTIONS, description) if description else None

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📋 예약 정보"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*정산 이슈 등록자*"},
                {"type": "plain_text", "text": user_name},
                {"type": "mrkdwn", "text": "*예약번호*"},
                {"type": "plain_text", "text": booking_key or "(없음)"},
                {"type": "mrkdwn", "text": "*업체명*"},
                {"type": "plain_text", "text": company_name or "(없음)"},
                {"type": "mrkdwn", "text": "*고객명*"},
                {"type": "plain_text", "text": customer_name or "(없음)"},
            ],
        },
        {"type": "divider"},
    ]

    # 정산기준일
    datepicker_element = {
        "type": "datepicker",
        "action_id": "settlement_standard_day_input",
        "placeholder": {"type": "plain_text", "text": "날짜 선택"},
    }
    if settlement_day:
        datepicker_element["initial_date"] = settlement_day
    blocks.append({
        "type": "input",
        "block_id": "settlement_standard_day_block",
        "label": {"type": "plain_text", "text": "정산기준일 (필수)"},
        "element": datepicker_element,
    })

    # 이슈사항
    issue_type_element = {
        "type": "static_select",
        "action_id": "issue_type_input",
        "placeholder": {"type": "plain_text", "text": "선택하세요"},
        "options": ISSUE_TYPE_OPTIONS,
    }
    if issue_type_initial:
        issue_type_element["initial_option"] = issue_type_initial
    blocks.append({
        "type": "input",
        "block_id": "issue_type_block",
        "label": {"type": "plain_text", "text": "이슈사항 (필수)"},
        "element": issue_type_element,
    })

    # 업체명2
    blocks.append({
        "type": "input",
        "block_id": "company_sub_name_block",
        "label": {"type": "plain_text", "text": "업체명2(대신배차)"},
        "optional": True,
        "element": {
            "type": "plain_text_input",
            "action_id": "company_sub_name_input",
            "initial_value": company_sub_name,
        },
    })

    # 정산기준금액
    blocks.append({
        "type": "input",
        "block_id": "settlement_standard_cost_block",
        "label": {"type": "plain_text", "text": "정산기준금액 (필수)"},
        "element": {
            "type": "plain_text_input",
            "action_id": "settlement_standard_cost_input",
            "initial_value": settlement_cost,
        },
    })

    # 카모아 부담비용
    blocks.append({
        "type": "input",
        "block_id": "carmore_cost_block",
        "label": {"type": "plain_text", "text": "카모아 부담비용"},
        "optional": True,
        "element": {
            "type": "plain_text_input",
            "action_id": "carmore_cost_input",
            "initial_value": carmore_cost,
        },
    })

    # 고객 환불 금액
    blocks.append({
        "type": "input",
        "block_id": "user_refund_cost_block",
        "label": {"type": "plain_text", "text": "고객 환불 금액"},
        "optional": True,
        "element": {
            "type": "plain_text_input",
            "action_id": "user_refund_cost_input",
            "initial_value": user_refund_cost,
        },
    })

    # 판매채널
    seller_channel_element = {
        "type": "static_select",
        "action_id": "seller_channel_input",
        "placeholder": {"type": "plain_text", "text": "선택하세요"},
        "options": SELLER_CHANNEL_OPTIONS,
    }
    if seller_channel_initial:
        seller_channel_element["initial_option"] = seller_channel_initial
    blocks.append({
        "type": "input",
        "block_id": "seller_channel_block",
        "label": {"type": "plain_text", "text": "판매채널 (필수)"},
        "element": seller_channel_element,
    })

    # 내용
    description_element = {
        "type": "static_select",
        "action_id": "description_input",
        "placeholder": {"type": "plain_text", "text": "선택하세요"},
        "options": DESCRIPTION_OPTIONS,
    }
    if description_initial:
        description_element["initial_option"] = description_initial
    blocks.append({
        "type": "input",
        "block_id": "description_block",
        "label": {"type": "plain_text", "text": "내용 (필수)"},
        "element": description_element,
    })

    return {
        "type": "modal",
        "callback_id": "registration_submit",
        "private_metadata": metadata,
        "title": {"type": "plain_text", "text": "정산 이슈 편집" if is_edit else "정산 이슈 등록"},
        "submit": {"type": "plain_text", "text": "수정" if is_edit else "등록"},
        "close": {"type": "plain_text", "text": "취소"},
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
            "text": {"type": "plain_text", "text": "📝 정산 이슈를 등록하시겠습니까?"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*이슈 등록자*"},
                {"type": "plain_text", "text": user_name},
                {"type": "mrkdwn", "text": "*예약번호*"},
                {"type": "plain_text", "text": booking_key or "(없음)"},
                {"type": "mrkdwn", "text": "*업체명*"},
                {"type": "plain_text", "text": company_name or "(없음)"},
                {"type": "mrkdwn", "text": "*고객명*"},
                {"type": "plain_text", "text": customer_name or "(없음)"},
                {"type": "mrkdwn", "text": "*정산기준일*"},
                {"type": "plain_text", "text": settlement_day or "(없음)"},
            ],
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*정산기준금액*"},
                {"type": "plain_text", "text": settlement_cost or "(없음)"},
                {"type": "mrkdwn", "text": "*업체명2(대신배차)*"},
                {"type": "plain_text", "text": company_sub_name or "(없음)"},
                {"type": "mrkdwn", "text": "*카모아 부담비용*"},
                {"type": "plain_text", "text": carmore_cost or "(없음)"},
                {"type": "mrkdwn", "text": "*고객 환불 금액*"},
                {"type": "plain_text", "text": user_refund_cost or "(없음)"},
                {"type": "mrkdwn", "text": "*판매채널*"},
                {"type": "plain_text", "text": seller_channel or "(없음)"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*이슈사항*\n{issue_type or '(없음)'}\n\n*내용*\n{description or '(없음)'}",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "승인"},
                    "style": "primary",
                    "action_id": "settlement_approve",
                    "value": button_data,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "반려"},
                    "style": "danger",
                    "action_id": "settlement_reject",
                    "value": button_data,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "편집"},
                    "action_id": "settlement_edit",
                    "value": button_data,
                },
            ],
        },
    ]


def build_approved_message(original_blocks: list[dict], approver_name: str) -> list[dict]:
    new_blocks = [b for b in original_blocks if b.get("type") != "actions"]
    new_blocks[0] = {
        "type": "header",
        "text": {"type": "plain_text", "text": "✅ 정산 이슈가 승인되었습니다."},
    }
    new_blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"승인자: *{approver_name}*"}
        ],
    })
    return new_blocks


def build_rejected_message(original_blocks: list[dict], rejecter_name: str) -> list[dict]:
    new_blocks = [b for b in original_blocks if b.get("type") != "actions"]
    new_blocks[0] = {
        "type": "header",
        "text": {"type": "plain_text", "text": "❌ 정산 이슈가 반려되었습니다."},
    }
    new_blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"반려자: *{rejecter_name}*"}
        ],
    })
    return new_blocks
