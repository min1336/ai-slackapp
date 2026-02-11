"""SlackReader 서비스 컴포넌트 테스트

SlackReader는 slack_client.py 함수에 대한 thin facade.
Mock WebClient를 통해 end-to-end 위임을 검증한다.
"""

from __future__ import annotations

from unittest.mock import Mock

from app.services.slack_reader import SlackReader


class TestSlackReader:
    def test_get_user_name_위임(self):
        client = Mock()
        client.users_info.return_value = {
            "user": {"real_name": "홍길동"},
        }
        reader = SlackReader(client)

        assert reader.get_user_name("U123") == "홍길동"
        client.users_info.assert_called_once_with(user="U123")

    def test_get_thread_url_위임(self):
        client = Mock()
        client.chat_getPermalink.return_value = {
            "permalink": "https://link",
        }
        reader = SlackReader(client)

        assert reader.get_thread_url("C123", "1234.5678") == "https://link"
        client.chat_getPermalink.assert_called_once_with(
            channel="C123", message_ts="1234.5678"
        )

    def test_get_parent_message_위임(self):
        client = Mock()
        client.conversations_replies.return_value = {
            "messages": [{"text": "부모 메시지"}],
        }
        reader = SlackReader(client)

        assert reader.get_parent_message("C123", "1234.5678") == "부모 메시지"

    def test_find_message_by_text_위임(self):
        client = Mock()
        client.conversations_history.return_value = {
            "messages": [{"text": "BK-001 관련", "ts": "5555.5555"}],
            "response_metadata": {"next_cursor": ""},
        }
        reader = SlackReader(client)

        assert reader.find_message_by_text("C123", "BK-001") == "5555.5555"

    def test_find_message_by_text_max_pages_전달(self):
        """max_pages=3 → 최대 3회 호출 후 중단."""
        client = Mock()
        client.conversations_history.return_value = {
            "messages": [{"text": "무관", "ts": "111.111"}],
            "response_metadata": {"next_cursor": "more"},
        }
        reader = SlackReader(client)

        result = reader.find_message_by_text("C123", "BK-001", max_pages=3)

        assert result is None
        assert client.conversations_history.call_count == 3
