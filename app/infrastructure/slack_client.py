from __future__ import annotations

from collections.abc import Iterator

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def get_user_real_name(client: WebClient, user_id: str) -> str:
    try:
        result = client.users_info(user=user_id)
        return result["user"]["real_name"]
    except (SlackApiError, KeyError):
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


def list_channel_messages(
    client: WebClient,
    channel_id: str,
    *,
    oldest: float = 0,
    latest: float = 0,
    max_pages: int = 10,
    page_size: int = 200,
) -> Iterator[dict]:
    """채널의 top-level 메시지를 페이지네이션하며 yield한다."""
    cursor = None
    for _ in range(max_pages):
        kwargs: dict = {
            "channel": channel_id,
            "limit": page_size,
        }
        if oldest:
            kwargs["oldest"] = str(int(oldest))
        if latest:
            kwargs["latest"] = str(int(latest))
        if cursor:
            kwargs["cursor"] = cursor

        result = client.conversations_history(**kwargs)

        yield from result.get("messages", [])

        metadata = result.get("response_metadata", {})
        cursor = metadata.get("next_cursor")
        if not cursor:
            break


def find_message_by_text(
    client: WebClient,
    channel_id: str,
    search_text: str,
    *,
    exclude_text: str | None = None,
    max_pages: int = 10,
    page_size: int = 100,
) -> str | None:
    cursor = None
    for _ in range(max_pages):
        try:
            kwargs: dict = {
                "channel": channel_id,
                "limit": page_size,
            }
            if cursor:
                kwargs["cursor"] = cursor

            result = client.conversations_history(**kwargs)
        except SlackApiError:
            return None

        for msg in result.get("messages", []):
            text = msg.get("text", "")
            normalized = text.replace("*", "")
            if search_text in normalized:
                if exclude_text and exclude_text in normalized:
                    continue
                return msg.get("ts")
            for block in msg.get("blocks", []):
                for field in block.get("fields", []):
                    if search_text in str(field.get("text", "")):
                        return msg.get("ts")
            for att in msg.get("attachments", []):
                for field in att.get("fields", []):
                    if search_text in str(field.get("value", "")):
                        return msg.get("ts")

        # 다음 페이지
        metadata = result.get("response_metadata", {})
        cursor = metadata.get("next_cursor")
        if not cursor:
            break

    return None
