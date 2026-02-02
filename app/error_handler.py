from __future__ import annotations

import logging

from slack_bolt import App
from slack_sdk import WebClient

from app.config import config
from app.core import get_logger
from app.exceptions import AppError, SlackError, SpreadsheetError, ValidationError

logger = get_logger(__name__)


def extract_context_from_body(body: dict) -> tuple[str | None, str | None, str | None]:
    """body에서 channel_id, user_id, thread_ts 추출."""
    channel_id = None
    user_id = None
    thread_ts = None

    if "channel" in body and isinstance(body["channel"], dict):
        channel_id = body["channel"].get("id")

    if not channel_id and "event" in body:
        channel_id = body["event"].get("channel")
        thread_ts = body["event"].get("thread_ts") or body["event"].get("ts")

    if "user" in body:
        if isinstance(body["user"], dict):
            user_id = body["user"].get("id")
        elif isinstance(body["user"], str):
            user_id = body["user"]

    if not user_id and "event" in body:
        user_id = body["event"].get("user")

    if not thread_ts and "message" in body:
        thread_ts = body["message"].get("thread_ts") or body["message"].get("ts")

    return channel_id, user_id, thread_ts


def is_user_error(error: Exception) -> bool:
    """사용자 실수(400대)인지 시스템 에러(500대)인지 구분."""
    return isinstance(error, ValidationError)


def get_error_emoji_and_type(error: Exception) -> tuple[str, str]:
    if isinstance(error, ValidationError):
        return "warning", "입력 오류"
    elif isinstance(error, SpreadsheetError):
        return "spreadsheet", "스프레드시트 오류"
    elif isinstance(error, SlackError):
        return "speech_balloon", "슬랙 오류"
    elif isinstance(error, AppError):
        return "x", "애플리케이션 오류"
    else:
        return "fire", "예상치 못한 오류"


def send_monitoring_alert(
    client: WebClient,
    error: Exception,
    body: dict,
    channel_id: str | None,
    user_id: str | None,
) -> None:
    error_channel_id = config.error_channel_id
    if not error_channel_id:
        logger.debug("error_channel_id not configured, skipping monitoring alert")
        return

    emoji, error_type = get_error_emoji_and_type(error)

    details_text = ""
    if isinstance(error, AppError) and error.details:
        details_text = "\n".join(f"• {k}: {v}" for k, v in error.details.items())

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":{emoji}: {error_type} 발생",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*에러 타입:*\n`{type(error).__name__}`"},
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*사용자:*\n<@{user_id}>"
                        if user_id
                        else "*사용자:*\n알 수 없음"
                    ),
                },
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*메시지:*\n```{str(error)}```"},
        },
    ]

    if details_text:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*상세 정보:*\n{details_text}"},
            }
        )

    if channel_id:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"채널: <#{channel_id}>"}],
            }
        )

    try:
        client.chat_postMessage(
            channel=error_channel_id,
            text=f"{error_type} 발생: {str(error)}",
            blocks=blocks,
        )
    except Exception as e:
        logger.error(f"Failed to send monitoring alert: {e}")


def register_error_handler(app: App) -> None:
    @app.error
    def handle_error(
        error: Exception,
        body: dict,
        client: WebClient,
        logger: logging.Logger,
    ) -> None:
        channel_id, user_id, thread_ts = extract_context_from_body(body)

        if is_user_error(error):
            # 400대 에러: 사용자 실수이므로 info 로그만, 모니터링 알림 불필요
            logger.info(
                f"User error: {error}",
                extra={
                    "error_type": type(error).__name__,
                    "channel_id": channel_id,
                    "user_id": user_id,
                },
            )
        else:
            # 500대 에러: 시스템 에러이므로 exception 로그 + 모니터링 알림
            logger.exception(
                f"System error: {error}",
                extra={
                    "error_type": type(error).__name__,
                    "channel_id": channel_id,
                    "user_id": user_id,
                },
            )
            send_monitoring_alert(client, error, body, channel_id, user_id)

        if channel_id and user_id:
            emoji, _ = get_error_emoji_and_type(error)
            user_message = (
                error.user_message
                if isinstance(error, AppError)
                else "예상치 못한 오류가 발생했습니다. 관리자에게 문의해주세요."
            )

            try:
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text=f":{emoji}: {user_message}",
                    thread_ts=thread_ts,
                )
            except Exception as e:
                logger.error(f"Failed to send ephemeral error message: {e}")
