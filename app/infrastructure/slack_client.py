from __future__ import annotations

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.web import SlackResponse

from app.exceptions import SlackError


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


def extract_text_value(values: dict, block_id: str, action_id: str) -> str:
    return values.get(block_id, {}).get(action_id, {}).get("value", "") or ""


def extract_date_value(values: dict, block_id: str, action_id: str) -> str:
    return values.get(block_id, {}).get(action_id, {}).get("selected_date", "") or ""


def extract_select_text(values: dict, block_id: str, action_id: str) -> str:
    selected = values.get(block_id, {}).get(action_id, {}).get("selected_option", {})
    return selected.get("text", {}).get("text", "") or "" if selected else ""


def send_ephemeral_message(
    client: WebClient,
    channel_id: str,
    user_id: str,
    text: str,
    blocks: list | None = None,
    thread_ts: str | None = None,
) -> None:
    try:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=text,
            blocks=blocks,
            thread_ts=thread_ts,
        )
    except SlackApiError as e:
        raise SlackError(
            message=f"Failed to send ephemeral message: {e}",
            details={
                "channel_id": channel_id,
                "user_id": user_id,
                "original_error": str(e),
            },
        ) from e


def post_message(
    client: WebClient,
    channel_id: str,
    text: str,
    blocks: list | None = None,
    thread_ts: str | None = None,
) -> SlackResponse:
    try:
        return client.chat_postMessage(
            channel=channel_id,
            text=text,
            blocks=blocks,
            thread_ts=thread_ts,
        )
    except SlackApiError as e:
        raise SlackError(
            message=f"Failed to post message: {e}",
            details={
                "channel_id": channel_id,
                "original_error": str(e),
            },
        ) from e


def update_message(
    client: WebClient,
    channel_id: str,
    ts: str,
    text: str,
    blocks: list | None = None,
) -> None:
    try:
        client.chat_update(
            channel=channel_id,
            ts=ts,
            text=text,
            blocks=blocks,
        )
    except SlackApiError as e:
        raise SlackError(
            message=f"Failed to update message: {e}",
            details={
                "channel_id": channel_id,
                "message_ts": ts,
                "original_error": str(e),
            },
        ) from e


def send_dm(
    client: WebClient,
    user_id: str,
    text: str,
    blocks: list | None = None,
) -> None:
    try:
        im = client.conversations_open(users=[user_id])
        channel_id = im["channel"]["id"]

        client.chat_postMessage(
            channel=channel_id,
            text=text,
            blocks=blocks,
        )
    except SlackApiError as e:
        raise SlackError(
            message=f"Failed to send DM: {e}",
            details={
                "user_id": user_id,
                "original_error": str(e),
            },
        ) from e
