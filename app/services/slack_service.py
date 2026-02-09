from __future__ import annotations

from typing import Any

from slack_sdk import WebClient

from app.infrastructure.slack_client import (
    extract_date_value as _extract_date_value,
)
from app.infrastructure.slack_client import (
    extract_select_text as _extract_select_text,
)
from app.infrastructure.slack_client import (
    extract_text_value as _extract_text_value,
)
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
from app.infrastructure.slack_client import send_dm as _send_dm
from app.infrastructure.spreadsheet import get_spreadsheet_url as _get_spreadsheet_url


def get_user_name(client: WebClient, user_id: str) -> str:
    return _get_user_real_name(client, user_id)


def get_thread_url(client: WebClient, channel_id: str, thread_ts: str) -> str:
    return _get_thread_permalink(client, channel_id, thread_ts)


def get_parent_message(
    client: WebClient, channel_id: str, thread_ts: str
) -> str | None:
    return _get_thread_parent_message(client, channel_id, thread_ts)


def extract_text_value(values: dict[str, Any], block_id: str, action_id: str) -> str:
    return _extract_text_value(values, block_id, action_id)


def extract_date_value(values: dict[str, Any], block_id: str, action_id: str) -> str:
    return _extract_date_value(values, block_id, action_id)


def extract_select_value(values: dict[str, Any], block_id: str, action_id: str) -> str:
    return _extract_select_text(values, block_id, action_id)


def send_dm(
    client: WebClient,
    user_id: str,
    text: str,
    blocks: list[dict[str, Any]] | None = None,
) -> None:
    _send_dm(client, user_id, text, blocks)


def find_message_by_text(
    client: WebClient,
    channel_id: str,
    search_text: str,
    *,
    max_pages: int = 10,
) -> str | None:
    return _find_message_by_text(client, channel_id, search_text, max_pages=max_pages)


def get_spreadsheet_url() -> str:
    return _get_spreadsheet_url()
