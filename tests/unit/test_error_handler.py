"""Global error handler 테스트"""

from __future__ import annotations

from app.error_handler import (
    extract_context_from_body,
    get_error_emoji_and_type,
    is_user_error,
)
from app.exceptions import AppError, SlackError, SpreadsheetError, ValidationError


class TestExtractContextFromBody:
    """extract_context_from_body() 테스트"""

    def test_action_body에서_컨텍스트_추출(self):
        body = {
            "type": "block_actions",
            "user": {"id": "U123"},
            "channel": {"id": "C456"},
            "message": {"ts": "123.456", "thread_ts": "111.222"},
        }

        channel_id, user_id, thread_ts = extract_context_from_body(body)

        assert channel_id == "C456"
        assert user_id == "U123"
        assert thread_ts == "111.222"

    def test_message_event_body에서_컨텍스트_추출(self):
        body = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U123",
                "channel": "C456",
                "ts": "123.456",
            },
        }

        channel_id, user_id, thread_ts = extract_context_from_body(body)

        assert channel_id == "C456"
        assert user_id == "U123"
        assert thread_ts == "123.456"

    def test_message_event_with_thread_ts(self):
        body = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U123",
                "channel": "C456",
                "ts": "123.456",
                "thread_ts": "111.222",
            },
        }

        channel_id, user_id, thread_ts = extract_context_from_body(body)

        assert channel_id == "C456"
        assert user_id == "U123"
        assert thread_ts == "111.222"

    def test_view_submission_body에서_user_id_추출(self):
        body = {"type": "view_submission", "user": {"id": "U123"}, "view": {}}

        channel_id, user_id, thread_ts = extract_context_from_body(body)

        assert channel_id is None
        assert user_id == "U123"
        assert thread_ts is None

    def test_빈_body에서_None_반환(self):
        channel_id, user_id, thread_ts = extract_context_from_body({})

        assert channel_id is None
        assert user_id is None
        assert thread_ts is None

    def test_user_as_string(self):
        body = {"user": "U123"}

        channel_id, user_id, thread_ts = extract_context_from_body(body)

        assert user_id == "U123"

    def test_message_ts_fallback(self):
        body = {
            "type": "block_actions",
            "user": {"id": "U123"},
            "channel": {"id": "C456"},
            "message": {"ts": "123.456"},  # No thread_ts
        }

        channel_id, user_id, thread_ts = extract_context_from_body(body)

        assert thread_ts == "123.456"


class TestGetErrorEmojiAndType:
    """get_error_emoji_and_type() 테스트"""

    def test_validation_error(self):
        emoji, error_type = get_error_emoji_and_type(ValidationError("test"))
        assert emoji == "warning"
        assert error_type == "입력 오류"

    def test_spreadsheet_error(self):
        emoji, error_type = get_error_emoji_and_type(SpreadsheetError("test"))
        assert emoji == "spreadsheet"
        assert error_type == "스프레드시트 오류"

    def test_slack_error(self):
        emoji, error_type = get_error_emoji_and_type(SlackError("test"))
        assert emoji == "speech_balloon"
        assert error_type == "슬랙 오류"

    def test_app_error(self):
        emoji, error_type = get_error_emoji_and_type(AppError("test"))
        assert emoji == "x"
        assert error_type == "애플리케이션 오류"

    def test_unknown_error(self):
        emoji, error_type = get_error_emoji_and_type(RuntimeError("test"))
        assert emoji == "fire"
        assert error_type == "예상치 못한 오류"


class TestIsUserError:
    """is_user_error() 테스트 - 400대 vs 500대 구분"""

    def test_validation_error는_user_error(self):
        assert is_user_error(ValidationError("test")) is True

    def test_spreadsheet_error는_system_error(self):
        assert is_user_error(SpreadsheetError("test")) is False

    def test_slack_error는_system_error(self):
        assert is_user_error(SlackError("test")) is False

    def test_app_error는_system_error(self):
        assert is_user_error(AppError("test")) is False

    def test_unknown_error는_system_error(self):
        assert is_user_error(RuntimeError("test")) is False
