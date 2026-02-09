from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypedDict

Block = dict[str, object]
Blocks = list[Block]


class SlackAction(TypedDict, total=False):
    value: str


class SlackUser(TypedDict, total=False):
    id: str


class SlackChannel(TypedDict, total=False):
    id: str


class SlackMessage(TypedDict, total=False):
    ts: str
    thread_ts: str
    blocks: Blocks


class ActionBody(TypedDict, total=False):
    user: SlackUser
    channel: SlackChannel
    message: SlackMessage
    actions: list[SlackAction]
    trigger_id: str


@dataclass(slots=True, frozen=True)
class MessageContext:
    user_id: str
    channel_id: str
    message_ts: str
    thread_ts: str

    @property
    def thread_ts_or_none(self) -> str | None:
        return self.thread_ts or None


def action_value(body: Mapping[str, Any], default: str = "{}") -> str:
    try:
        value = body["actions"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return default
    return value if isinstance(value, str) else default


def message_context(body: Mapping[str, Any]) -> MessageContext:
    def _extract(key: str, subkey: str) -> str:
        try:
            value = body[key][subkey]
        except (KeyError, TypeError):
            return ""
        return value if isinstance(value, str) else ""

    return MessageContext(
        user_id=_extract("user", "id"),
        channel_id=_extract("channel", "id"),
        message_ts=_extract("message", "ts"),
        thread_ts=_extract("message", "thread_ts"),
    )
