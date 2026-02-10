"""Common error handling utilities for listener layer."""

from __future__ import annotations

from slack_sdk.errors import SlackApiError

from app.core import get_logger

logger = get_logger(__name__)


def notify_user_safe(client, user_id: str, message: str) -> None:
    """사용자에게 DM 전송 (실패 시 로깅만)

    Args:
        client: Slack WebClient
        user_id: 사용자 ID
        message: 전송할 메시지
    """
    if not user_id:
        return

    try:
        client.chat_postMessage(
            channel=user_id,
            text=message,
        )
    except SlackApiError:
        logger.warning("user_notification_failed", user_id=user_id)


def restore_message_safe(
    client,
    *,
    channel_id: str,
    message_ts: str,
    blocks: list,
    text: str = "승인 요청",
) -> None:
    """메시지 블록 복원 (실패 시 로깅만)

    Best-effort 작업 - 실패해도 예외를 발생시키지 않음.

    Args:
        client: Slack WebClient
        channel_id: 채널 ID
        message_ts: 메시지 타임스탬프
        blocks: 복원할 Block Kit blocks
        text: 폴백 텍스트
    """
    if not blocks or not message_ts:
        return

    try:
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            blocks=blocks,
            text=text,
        )
    except SlackApiError:
        logger.warning(
            "message_restore_failed",
            channel_id=channel_id,
            message_ts=message_ts,
        )
