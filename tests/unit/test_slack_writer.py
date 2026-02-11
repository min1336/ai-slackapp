"""SlackWriter 서비스 컴포넌트 테스트

kwargs 조립 로직 (Optional 경계)과 에러 전파 검증.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from slack_sdk.errors import SlackApiError

from app.services.slack_writer import SlackWriter


def _slack_error(msg: str = "error") -> SlackApiError:
    return SlackApiError(message=msg, response=Mock())


@pytest.fixture
def mock_client():
    return Mock()


@pytest.fixture
def writer(mock_client):
    return SlackWriter(mock_client)


# ── post_message ────────────────────────────────


class TestPostMessage:
    def test_기본_메시지_전송_ts_반환(self, writer, mock_client):
        mock_client.chat_postMessage.return_value = {"ts": "1234.5678"}

        result = writer.post_message(channel="C123", text="테스트")

        assert result == "1234.5678"
        mock_client.chat_postMessage.assert_called_once_with(
            channel="C123", text="테스트"
        )

    def test_blocks_포함시_kwargs에_blocks_추가(self, writer, mock_client):
        mock_client.chat_postMessage.return_value = {"ts": "1234.5678"}
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "B"}}]

        writer.post_message(channel="C123", text="fb", blocks=blocks)

        kw = mock_client.chat_postMessage.call_args.kwargs
        assert kw["blocks"] == blocks

    def test_blocks_None이면_kwargs에_미포함(self, writer, mock_client):
        mock_client.chat_postMessage.return_value = {"ts": "1234.5678"}

        writer.post_message(channel="C123", text="텍스트")

        kw = mock_client.chat_postMessage.call_args.kwargs
        assert "blocks" not in kw

    def test_thread_ts_포함시_kwargs에_추가(self, writer, mock_client):
        mock_client.chat_postMessage.return_value = {"ts": "1234.5678"}

        writer.post_message(channel="C123", text="답글", thread_ts="9999.0000")

        kw = mock_client.chat_postMessage.call_args.kwargs
        assert kw["thread_ts"] == "9999.0000"

    def test_thread_ts_None이면_kwargs에_미포함(self, writer, mock_client):
        mock_client.chat_postMessage.return_value = {"ts": "1234.5678"}

        writer.post_message(channel="C123", text="텍스트")

        kw = mock_client.chat_postMessage.call_args.kwargs
        assert "thread_ts" not in kw

    def test_응답에_ts_없으면_빈문자열_반환(self, writer, mock_client):
        mock_client.chat_postMessage.return_value = {"ok": True}

        assert writer.post_message(channel="C123", text="텍스트") == ""

    def test_SlackApiError_그대로_전파(self, writer, mock_client):
        mock_client.chat_postMessage.side_effect = _slack_error()

        with pytest.raises(SlackApiError):
            writer.post_message(channel="C123", text="텍스트")


# ── update_message ──────────────────────────────


class TestUpdateMessage:
    def test_기본_업데이트(self, writer, mock_client):
        writer.update_message(channel="C123", ts="1234.5678", text="수정됨")

        mock_client.chat_update.assert_called_once_with(
            channel="C123", ts="1234.5678", text="수정됨"
        )

    def test_blocks_포함시_전달(self, writer, mock_client):
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "B"}}]

        writer.update_message(
            channel="C123", ts="1234.5678", text="수정됨", blocks=blocks
        )

        kw = mock_client.chat_update.call_args.kwargs
        assert kw["blocks"] == blocks

    def test_blocks_None이면_미포함(self, writer, mock_client):
        writer.update_message(channel="C123", ts="1234.5678", text="수정됨")

        kw = mock_client.chat_update.call_args.kwargs
        assert "blocks" not in kw

    def test_SlackApiError_전파(self, writer, mock_client):
        mock_client.chat_update.side_effect = _slack_error()

        with pytest.raises(SlackApiError):
            writer.update_message(channel="C123", ts="1234.5678", text="수정됨")


# ── delete_message ──────────────────────────────


class TestDeleteMessage:
    def test_삭제_호출(self, writer, mock_client):
        writer.delete_message(channel="C123", ts="1234.5678")

        mock_client.chat_delete.assert_called_once_with(channel="C123", ts="1234.5678")

    def test_SlackApiError_전파(self, writer, mock_client):
        mock_client.chat_delete.side_effect = _slack_error()

        with pytest.raises(SlackApiError):
            writer.delete_message(channel="C123", ts="1234.5678")


# ── post_ephemeral ──────────────────────────────


class TestPostEphemeral:
    def test_기본_에페메랄_전송(self, writer, mock_client):
        writer.post_ephemeral(channel="C123", user="U123", text="임시 메시지")

        mock_client.chat_postEphemeral.assert_called_once_with(
            channel="C123", user="U123", text="임시 메시지"
        )

    def test_thread_ts_포함시_전달(self, writer, mock_client):
        writer.post_ephemeral(
            channel="C123",
            user="U123",
            text="임시 메시지",
            thread_ts="9999.0000",
        )

        kw = mock_client.chat_postEphemeral.call_args.kwargs
        assert kw["thread_ts"] == "9999.0000"

    def test_thread_ts_None이면_미포함(self, writer, mock_client):
        writer.post_ephemeral(channel="C123", user="U123", text="임시 메시지")

        kw = mock_client.chat_postEphemeral.call_args.kwargs
        assert "thread_ts" not in kw

    def test_SlackApiError_전파(self, writer, mock_client):
        mock_client.chat_postEphemeral.side_effect = _slack_error()

        with pytest.raises(SlackApiError):
            writer.post_ephemeral(channel="C123", user="U123", text="임시 메시지")
