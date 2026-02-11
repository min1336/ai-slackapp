"""Global error handler 테스트"""

from __future__ import annotations

from unittest.mock import MagicMock

from slack_sdk.errors import SlackApiError

from app.error_handler import (
    _handle_error_impl,
    extract_context_from_body,
    get_error_emoji_and_type,
    is_user_error,
    send_monitoring_alert,
)
from app.exceptions import AppError, SlackError, SpreadsheetError, ValidationError


def _make_client() -> MagicMock:
    """WebClient MagicMock 생성."""
    return MagicMock()


def _make_body(
    *,
    channel_id: str | None = None,
    user_id: str | None = None,
    thread_ts: str | None = None,
) -> dict:
    """Slack body dict 생성."""
    body: dict = {}
    if channel_id:
        body["channel"] = {"id": channel_id}
    if user_id:
        body["user"] = {"id": user_id}
    if thread_ts:
        body["message"] = {"thread_ts": thread_ts}
    return body


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


# ============================================================================
# send_monitoring_alert 테스트
# ============================================================================


class TestSendMonitoringAlert:
    def test_시스템에러_알림전송(self):
        client = _make_client()
        error = SpreadsheetError("시트 에러")

        send_monitoring_alert(
            client, error, {}, "C111", "U222", error_channel_id="C-MON"
        )

        client.chat_postMessage.assert_called_once()
        assert client.chat_postMessage.call_args.kwargs["channel"] == "C-MON"

    def test_에러채널_미설정시_skip(self):
        client = _make_client()
        error = SpreadsheetError("시트 에러")

        send_monitoring_alert(client, error, {}, None, None, error_channel_id="")

        client.chat_postMessage.assert_not_called()

    def test_상세정보_포함(self):
        client = _make_client()
        error = AppError("에러 발생", details={"booking_key": "BK-1", "step": "save"})

        send_monitoring_alert(client, error, {}, None, None, error_channel_id="C-MON")

        blocks = client.chat_postMessage.call_args.kwargs["blocks"]
        details_block = next(
            (
                b
                for b in blocks
                if b.get("type") == "section"
                and "상세 정보" in b.get("text", {}).get("text", "")
            ),
            None,
        )
        assert details_block is not None
        assert "booking_key" in details_block["text"]["text"]

    def test_채널정보_포함(self):
        client = _make_client()
        error = AppError("에러")

        send_monitoring_alert(
            client, error, {}, "C-SRC", None, error_channel_id="C-MON"
        )

        blocks = client.chat_postMessage.call_args.kwargs["blocks"]
        context_block = next((b for b in blocks if b.get("type") == "context"), None)
        assert context_block is not None
        assert "C-SRC" in context_block["elements"][0]["text"]

    def test_slack_api_실패시_로깅만(self):
        client = _make_client()
        client.chat_postMessage.side_effect = SlackApiError(
            "error", MagicMock(status_code=500, data={"ok": False})
        )
        error = AppError("에러")

        # 예외가 전파되지 않아야 함
        send_monitoring_alert(client, error, {}, None, None, error_channel_id="C-MON")


# ============================================================================
# _handle_error_impl 테스트
# ============================================================================


class TestHandleErrorImpl:
    def test_user_error시_info로그_모니터링미전송(self):
        client = _make_client()
        error = ValidationError("잘못된 입력")
        body = _make_body(channel_id="C111", user_id="U222")

        _handle_error_impl(error, body, client, error_channel_id="C-MON")

        # 모니터링 알림 미전송 (user error)
        client.chat_postMessage.assert_not_called()
        # 에페메랄은 전송
        client.chat_postEphemeral.assert_called_once()

    def test_system_error시_exception로그_모니터링전송(self):
        client = _make_client()
        error = SpreadsheetError("시트 에러")
        body = _make_body(channel_id="C111", user_id="U222")

        _handle_error_impl(error, body, client, error_channel_id="C-MON")

        # 모니터링 알림 전송
        client.chat_postMessage.assert_called_once()
        assert client.chat_postMessage.call_args.kwargs["channel"] == "C-MON"
        # 에페메랄도 전송
        client.chat_postEphemeral.assert_called_once()

    def test_사용자_에페메랄_전송(self):
        client = _make_client()
        error = ValidationError("입력 오류")
        body = _make_body(channel_id="C111", user_id="U222")

        _handle_error_impl(error, body, client, error_channel_id="")

        client.chat_postEphemeral.assert_called_once()
        kwargs = client.chat_postEphemeral.call_args.kwargs
        assert kwargs["channel"] == "C111"
        assert kwargs["user"] == "U222"
        assert "입력값이 올바르지 않습니다" in kwargs["text"]

    def test_채널없으면_에페메랄_미전송(self):
        client = _make_client()
        error = ValidationError("입력 오류")
        body = _make_body(user_id="U222")  # channel 없음

        _handle_error_impl(error, body, client, error_channel_id="")

        client.chat_postEphemeral.assert_not_called()

    def test_user_id없으면_에페메랄_미전송(self):
        client = _make_client()
        error = ValidationError("입력 오류")
        body = _make_body(channel_id="C111")  # user 없음

        _handle_error_impl(error, body, client, error_channel_id="")

        client.chat_postEphemeral.assert_not_called()

    def test_에페메랄_실패시_로깅만(self):
        client = _make_client()
        client.chat_postEphemeral.side_effect = SlackApiError(
            "error", MagicMock(status_code=500, data={"ok": False})
        )
        error = ValidationError("입력 오류")
        body = _make_body(channel_id="C111", user_id="U222")

        # 예외가 전파되지 않아야 함
        _handle_error_impl(error, body, client, error_channel_id="")
