from __future__ import annotations

from typing import Any

from slack_sdk import WebClient

from app.core import get_logger

logger = get_logger(__name__)


class SlackWriter:
    def __init__(self, client: WebClient) -> None:
        self._client = client

    def post_message(
        self,
        *,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        thread_ts: str | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if blocks is not None:
            kwargs["blocks"] = blocks
        if thread_ts is not None:
            kwargs["thread_ts"] = thread_ts
        response = self._client.chat_postMessage(**kwargs)
        return response.get("ts", "")

    def update_message(
        self,
        *,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "channel": channel,
            "ts": ts,
            "text": text,
        }
        if blocks is not None:
            kwargs["blocks"] = blocks
        self._client.chat_update(**kwargs)

    def delete_message(self, *, channel: str, ts: str) -> None:
        self._client.chat_delete(channel=channel, ts=ts)

    def post_ephemeral(
        self,
        *,
        channel: str,
        user: str,
        text: str,
        thread_ts: str | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "channel": channel,
            "user": user,
            "text": text,
        }
        if thread_ts is not None:
            kwargs["thread_ts"] = thread_ts
        self._client.chat_postEphemeral(**kwargs)

    def upload_file(
        self,
        *,
        channel: str,
        thread_ts: str,
        content: bytes,
        filename: str,
        title: str = "",
    ) -> None:
        self._client.files_upload_v2(
            channel=channel,
            thread_ts=thread_ts,
            content=content,
            filename=filename,
            title=title or filename,
        )

    def upload_files(
        self,
        *,
        channel: str,
        thread_ts: str,
        file_uploads: list[dict[str, Any]],
    ) -> None:
        self._client.files_upload_v2(
            channel=channel,
            thread_ts=thread_ts,
            file_uploads=file_uploads,
        )

    def add_reaction(self, *, channel: str, timestamp: str, name: str) -> None:
        self._client.reactions_add(channel=channel, timestamp=timestamp, name=name)
