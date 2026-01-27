from __future__ import annotations

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


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
