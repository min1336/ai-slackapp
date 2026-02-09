from __future__ import annotations

from unittest.mock import MagicMock

from slack_sdk.errors import SlackApiError

from app.infrastructure.slack_client import find_message_by_text


def _make_history_response(messages, next_cursor=""):
    return {
        "messages": messages,
        "response_metadata": {"next_cursor": next_cursor},
    }


class TestFindMessageByText:
    def test_첫_페이지에서_발견(self):
        client = MagicMock()
        client.conversations_history.return_value = _make_history_response(
            [
                {"text": "다른 메시지", "ts": "111.111"},
                {"text": "예약번호 BK-001 입니다", "ts": "222.222"},
            ]
        )

        result = find_message_by_text(client, "C123", "BK-001")
        assert result == "222.222"

    def test_두번째_페이지에서_발견(self):
        client = MagicMock()
        client.conversations_history.side_effect = [
            _make_history_response(
                [{"text": "관계없는 메시지", "ts": "111.111"}],
                next_cursor="cursor_2",
            ),
            _make_history_response(
                [{"text": "예약 BK-001 관련", "ts": "333.333"}],
            ),
        ]

        result = find_message_by_text(client, "C123", "BK-001")
        assert result == "333.333"
        assert client.conversations_history.call_count == 2

    def test_max_pages_초과시_None(self):
        client = MagicMock()
        client.conversations_history.return_value = _make_history_response(
            [{"text": "무관한 메시지", "ts": "111.111"}],
            next_cursor="more",
        )

        result = find_message_by_text(client, "C123", "BK-001", max_pages=2)
        assert result is None
        assert client.conversations_history.call_count == 2

    def test_빈_채널은_None(self):
        client = MagicMock()
        client.conversations_history.return_value = _make_history_response([])

        result = find_message_by_text(client, "C123", "BK-001")
        assert result is None

    def test_SlackApiError_발생시_None(self):
        client = MagicMock()
        client.conversations_history.side_effect = SlackApiError(
            message="error",
            response=MagicMock(status_code=500),
        )

        result = find_message_by_text(client, "C123", "BK-001")
        assert result is None

    def test_cursor_없으면_다음_페이지_요청_안함(self):
        client = MagicMock()
        client.conversations_history.return_value = _make_history_response(
            [{"text": "무관한 메시지", "ts": "111.111"}],
        )

        result = find_message_by_text(client, "C123", "BK-001")
        assert result is None
        assert client.conversations_history.call_count == 1
