from __future__ import annotations

from collections.abc import Iterator

from slack_sdk import WebClient

from app.infrastructure.slack_client import (
    find_message_by_text as _find_message_by_text,
)
from app.infrastructure.slack_client import (
    get_thread_parent_message as _get_thread_parent_message,
)
from app.infrastructure.slack_client import (
    get_thread_permalink as _get_thread_permalink,
)
from app.infrastructure.slack_client import (
    get_user_real_name as _get_user_real_name,
)
from app.infrastructure.slack_client import (
    list_channel_messages as _list_channel_messages,
)


class SlackReader:
    def __init__(self, client: WebClient) -> None:
        self._client = client

    def get_user_name(self, user_id: str) -> str:
        return _get_user_real_name(self._client, user_id)

    def get_thread_url(self, channel_id: str, thread_ts: str) -> str:
        return _get_thread_permalink(self._client, channel_id, thread_ts)

    def get_parent_message(self, channel_id: str, thread_ts: str) -> str | None:
        return _get_thread_parent_message(self._client, channel_id, thread_ts)

    def find_message_by_text(
        self,
        channel_id: str,
        search_text: str,
        *,
        exclude_text: str | None = None,
        max_pages: int = 10,
    ) -> str | None:
        return _find_message_by_text(
            self._client,
            channel_id,
            search_text,
            exclude_text=exclude_text,
            max_pages=max_pages,
        )

    def list_channel_messages(
        self,
        channel_id: str,
        *,
        oldest: float = 0,
        max_pages: int = 10,
    ) -> Iterator[dict]:
        return _list_channel_messages(
            self._client, channel_id, oldest=oldest, max_pages=max_pages
        )
