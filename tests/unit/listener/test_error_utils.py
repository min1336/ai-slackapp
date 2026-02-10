"""Test error handling utilities."""

from __future__ import annotations

from unittest.mock import Mock

from slack_sdk.errors import SlackApiError

from app.listener.error_utils import notify_user_safe, restore_message_safe


class TestNotifyUserSafe:
    """Test notify_user_safe utility."""

    def test_sends_dm_to_user(self):
        """사용자에게 DM 전송"""
        mock_client = Mock()
        notify_user_safe(mock_client, "U123", "Test message")

        mock_client.chat_postMessage.assert_called_once_with(
            channel="U123",
            text="Test message",
        )

    def test_ignores_slack_api_errors(self):
        """Slack API 에러는 무시"""
        mock_client = Mock()
        mock_client.chat_postMessage.side_effect = SlackApiError(
            "error", response={"error": "test"}
        )

        # Should not raise
        notify_user_safe(mock_client, "U123", "Test")

    def test_skips_if_user_id_empty(self):
        """user_id가 비어있으면 스킵"""
        mock_client = Mock()
        notify_user_safe(mock_client, "", "Test")

        mock_client.chat_postMessage.assert_not_called()


class TestRestoreMessageSafe:
    """Test restore_message_safe utility."""

    def test_updates_message_blocks(self):
        """메시지 블록 업데이트"""
        mock_client = Mock()
        blocks = [{"type": "section"}]

        restore_message_safe(
            mock_client,
            channel_id="C123",
            message_ts="1234.5678",
            blocks=blocks,
            text="Test",
        )

        mock_client.chat_update.assert_called_once_with(
            channel="C123",
            ts="1234.5678",
            blocks=blocks,
            text="Test",
        )

    def test_ignores_slack_api_errors(self):
        """Slack API 에러는 무시"""
        mock_client = Mock()
        mock_client.chat_update.side_effect = SlackApiError(
            "error", response={"error": "test"}
        )

        # Should not raise
        restore_message_safe(
            mock_client,
            channel_id="C123",
            message_ts="1234.5678",
            blocks=[{"type": "section"}],
        )

    def test_skips_if_blocks_empty(self):
        """blocks가 비어있으면 스킵"""
        mock_client = Mock()
        restore_message_safe(
            mock_client,
            channel_id="C123",
            message_ts="1234.5678",
            blocks=[],
        )

        mock_client.chat_update.assert_not_called()

    def test_skips_if_message_ts_empty(self):
        """message_ts가 비어있으면 스킵"""
        mock_client = Mock()
        restore_message_safe(
            mock_client,
            channel_id="C123",
            message_ts="",
            blocks=[{"type": "section"}],
        )

        mock_client.chat_update.assert_not_called()
