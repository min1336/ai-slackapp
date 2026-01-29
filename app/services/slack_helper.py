from __future__ import annotations

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.web import SlackResponse


def get_user_real_name(client: WebClient, user_id: str) -> str:
    try:
        result = client.users_info(user=user_id)
        return result["user"]["real_name"]
    except SlackApiError:
        return ""


def get_thread_permalink(client: WebClient, channel_id: str, thread_ts: str) -> str:
    if not thread_ts:
        return ""
    try:
        result = client.chat_getPermalink(channel=channel_id, message_ts=thread_ts)
        return result.get("permalink", "")
    except SlackApiError:
        return ""


def get_thread_parent_message(
    client: WebClient,
    channel_id: str,
    thread_ts: str,
) -> str | None:
    try:
        result = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            limit=1,
            inclusive=True,
        )
        messages = result.get("messages", [])
        if messages:
            return messages[0].get("text", "")
    except SlackApiError:
        pass
    return None


def send_ephemeral_message(
    client: WebClient,
    channel_id: str,
    user_id: str,
    text: str,
    blocks: list | None = None,
    thread_ts: str | None = None,
) -> bool:
    """
    임시 메시지(본인만 보이는)를 전송합니다.

    Returns:
        성공 여부
    """
    try:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=text,
            blocks=blocks,
            thread_ts=thread_ts,
        )
        return True
    except SlackApiError:
        return False


def post_message(
    client: WebClient,
    channel_id: str,
    text: str,
    blocks: list | None = None,
    thread_ts: str | None = None,
) -> SlackResponse | None:
    """
    채널에 메시지를 전송합니다.

    Returns:
        API 응답 또는 None
    """
    try:
        return client.chat_postMessage(
            channel=channel_id,
            text=text,
            blocks=blocks,
            thread_ts=thread_ts,
        )
    except SlackApiError:
        return None


def update_message(
    client: WebClient,
    channel_id: str,
    ts: str,
    text: str,
    blocks: list | None = None,
) -> bool:
    """
    기존 메시지를 업데이트합니다.

    Returns:
        성공 여부
    """
    try:
        client.chat_update(
            channel=channel_id,
            ts=ts,
            text=text,
            blocks=blocks,
        )
        return True
    except SlackApiError:
        return False
