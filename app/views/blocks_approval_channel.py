from __future__ import annotations

from app.constants import ActionId, CommonText, request_type_label
from app.views.blocks import Block, Blocks


def _build_minimal_base_blocks(
    requester_name: str,
    thread_url: str,
    request_type: str,
    *,
    is_pending: bool = False,
) -> Blocks:
    """승인 채널 메시지의 공통 블록 (요청자 + 스레드 링크).

    is_pending=True -> header 블록 (대기 중), False -> 취소선 section (완료).
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
    request_type = request_type_label(is_transfer)
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
    request_type = request_type_label(is_transfer)
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
    request_type = request_type_label(is_transfer)
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
    request_type = request_type_label(is_transfer)
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
