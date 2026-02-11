"""Slack Reader/Writer Fake 구현체"""

from __future__ import annotations

from typing import Any


class FakeSlackReader:
    """SlackMessageReader Protocol 호환 Fake.

    dict에 미리 넣어둔 값을 반환하므로 실제 Slack API 호출 없이 테스트 가능.
    """

    def __init__(self) -> None:
        self.user_names: dict[str, str] = {}
        self.thread_urls: dict[tuple[str, str], str] = {}
        self.parent_messages: dict[tuple[str, str], str | None] = {}
        self.messages_by_text: dict[tuple[str, str], str | None] = {}

    def get_user_name(self, user_id: str) -> str:
        return self.user_names.get(user_id, "")

    def get_thread_url(self, channel_id: str, thread_ts: str) -> str:
        return self.thread_urls.get((channel_id, thread_ts), "")

    def get_parent_message(self, channel_id: str, thread_ts: str) -> str | None:
        return self.parent_messages.get((channel_id, thread_ts))

    def find_message_by_text(
        self,
        channel_id: str,
        search_text: str,
        *,
        max_pages: int = 10,
    ) -> str | None:
        return self.messages_by_text.get((channel_id, search_text))


class FakeSlackWriter:
    """SlackMessageWriter Protocol 호환 Fake.

    모든 쓰기 호출을 리스트에 기록하여 테스트에서 검증 가능.
    """

    def __init__(self) -> None:
        self.posted_messages: list[dict[str, Any]] = []
        self.updated_messages: list[dict[str, Any]] = []
        self.deleted_messages: list[dict[str, Any]] = []
        self.ephemeral_messages: list[dict[str, Any]] = []
        self._next_ts_counter: int = 1000

    def post_message(
        self,
        *,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        thread_ts: str | None = None,
    ) -> str:
        ts = f"{self._next_ts_counter}.000000"
        self._next_ts_counter += 1
        self.posted_messages.append(
            {
                "channel": channel,
                "text": text,
                "blocks": blocks,
                "thread_ts": thread_ts,
                "ts": ts,
            }
        )
        return ts

    def update_message(
        self,
        *,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        self.updated_messages.append(
            {
                "channel": channel,
                "ts": ts,
                "text": text,
                "blocks": blocks,
            }
        )

    def delete_message(self, *, channel: str, ts: str) -> None:
        self.deleted_messages.append({"channel": channel, "ts": ts})

    def post_ephemeral(
        self,
        *,
        channel: str,
        user: str,
        text: str,
        thread_ts: str | None = None,
    ) -> None:
        self.ephemeral_messages.append(
            {
                "channel": channel,
                "user": user,
                "text": text,
                "thread_ts": thread_ts,
            }
        )

    def clear(self) -> None:
        self.posted_messages.clear()
        self.updated_messages.clear()
        self.deleted_messages.clear()
        self.ephemeral_messages.clear()
        self._next_ts_counter = 1000
