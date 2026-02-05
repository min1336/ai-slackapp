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
    actions = body.get("actions", [])
    if not isinstance(actions, list):
        return default
    action = next(iter(actions), {})
    if not isinstance(action, Mapping):
        return default
    value = action.get("value")
    return value if isinstance(value, str) else default


def message_context(body: Mapping[str, Any]) -> MessageContext:
    user = body.get("user", {})
    channel = body.get("channel", {})
    message = body.get("message", {})

    user_id = user.get("id", "") if isinstance(user, Mapping) else ""
    channel_id = channel.get("id", "") if isinstance(channel, Mapping) else ""
    message_ts = message.get("ts", "") if isinstance(message, Mapping) else ""
    thread_ts = message.get("thread_ts", "") if isinstance(message, Mapping) else ""

    return MessageContext(
        user_id=user_id,
        channel_id=channel_id,
        message_ts=message_ts,
        thread_ts=thread_ts,
    )
