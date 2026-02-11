"""slack_client.py 인프라 함수 테스트

get_user_real_name, get_thread_permalink, get_thread_parent_message 커버리지 + 경계값.
find_message_by_text 추가 경계 케이스 (기존 test_find_message_by_text.py 보완).
"""

from __future__ import annotations

from unittest.mock import Mock

from slack_sdk.errors import SlackApiError

from app.infrastructure.slack_client import (
    find_message_by_text,
    get_thread_parent_message,
    get_thread_permalink,
    get_user_real_name,
)


def _slack_error(msg: str = "error") -> SlackApiError:
    return SlackApiError(message=msg, response=Mock())


# ── get_user_real_name ──────────────────────────


class TestGetUserRealName:
    def test_정상_사용자명_반환(self):
        client = Mock()
        client.users_info.return_value = {
            "user": {"real_name": "홍길동"},
        }

        result = get_user_real_name(client, "U123")

        assert result == "홍길동"
        client.users_info.assert_called_once_with(user="U123")

    def test_SlackApiError시_빈문자열_반환(self):
        client = Mock()
        client.users_info.side_effect = _slack_error()

        assert get_user_real_name(client, "U123") == ""

    def test_응답에_user키_없으면_빈문자열_반환(self):
        """비정상 응답 {"ok": true} → KeyError 안전 처리."""
        client = Mock()
        client.users_info.return_value = {"ok": True}

        assert get_user_real_name(client, "U123") == ""


# ── get_thread_permalink ────────────────────────


class TestGetThreadPermalink:
    def test_정상_permalink_반환(self):
        client = Mock()
        client.chat_getPermalink.return_value = {
            "permalink": "https://workspace.slack.com/archives/C123/p1234",
        }

        result = get_thread_permalink(client, "C123", "1234.5678")

        assert "archives/C123" in result

    def test_thread_ts_빈문자열이면_API_미호출_빈문자열(self):
        client = Mock()

        result = get_thread_permalink(client, "C123", "")

        assert result == ""
        client.chat_getPermalink.assert_not_called()

    def test_SlackApiError시_빈문자열_반환(self):
        client = Mock()
        client.chat_getPermalink.side_effect = _slack_error()

        assert get_thread_permalink(client, "C123", "1234.5678") == ""

    def test_응답에_permalink_없으면_빈문자열(self):
        client = Mock()
        client.chat_getPermalink.return_value = {"ok": True}

        assert get_thread_permalink(client, "C123", "1234.5678") == ""


# ── get_thread_parent_message ───────────────────


class TestGetThreadParentMessage:
    def test_정상_부모메시지_텍스트_반환(self):
        client = Mock()
        client.conversations_replies.return_value = {
            "messages": [{"text": "원본 메시지 텍스트"}],
        }

        result = get_thread_parent_message(client, "C123", "1234.5678")

        assert result == "원본 메시지 텍스트"
        client.conversations_replies.assert_called_once_with(
            channel="C123", ts="1234.5678", limit=1, inclusive=True
        )

    def test_messages_빈리스트면_None(self):
        client = Mock()
        client.conversations_replies.return_value = {"messages": []}

        assert get_thread_parent_message(client, "C123", "1234.5678") is None

    def test_messages_키_없으면_None(self):
        client = Mock()
        client.conversations_replies.return_value = {"ok": True}

        assert get_thread_parent_message(client, "C123", "1234.5678") is None

    def test_text_키_없으면_빈문자열(self):
        """attachment-only 메시지 등 text가 없는 경우."""
        client = Mock()
        client.conversations_replies.return_value = {
            "messages": [{"attachments": [{"text": "첨부"}]}],
        }

        assert get_thread_parent_message(client, "C123", "1234.5678") == ""

    def test_SlackApiError시_None(self):
        client = Mock()
        client.conversations_replies.side_effect = _slack_error()

        assert get_thread_parent_message(client, "C123", "1234.5678") is None


# ── find_message_by_text 추가 경계 케이스 ──────


class TestFindMessageByTextEdgeCases:
    """기존 test_find_message_by_text.py에 없는 경계 케이스."""

    @staticmethod
    def _response(messages, next_cursor=""):
        return {
            "messages": messages,
            "response_metadata": {"next_cursor": next_cursor},
        }

    def test_messages_빈리스트면_다음페이지_탐색(self):
        client = Mock()
        client.conversations_history.side_effect = [
            self._response([], next_cursor="page2"),
            self._response([{"text": "BK-001 관련", "ts": "222.222"}]),
        ]

        result = find_message_by_text(client, "C123", "BK-001")

        assert result == "222.222"
        assert client.conversations_history.call_count == 2

    def test_max_pages_1이면_한페이지만_탐색(self):
        client = Mock()
        client.conversations_history.return_value = self._response(
            [{"text": "무관", "ts": "111.111"}], next_cursor="more"
        )

        result = find_message_by_text(client, "C123", "BK-001", max_pages=1)

        assert result is None
        assert client.conversations_history.call_count == 1

    def test_text_부분문자열_매칭(self):
        """'in' 연산자로 부분 매칭 확인."""
        client = Mock()
        client.conversations_history.return_value = self._response(
            [{"text": "예약번호: BK-001 고객님 문의", "ts": "333.333"}]
        )

        result = find_message_by_text(client, "C123", "BK-001")

        assert result == "333.333"
