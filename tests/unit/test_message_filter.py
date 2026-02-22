from __future__ import annotations

import pytest

from app.config import get_env_config
from app.listener.messages import _is_bot_message, _should_process_message


class TestIsBotMessage:
    def test_bot_id_present(self):
        assert _is_bot_message({"bot_id": "B123"}) is True

    def test_subtype_bot_message(self):
        assert _is_bot_message({"subtype": "bot_message"}) is True

    def test_normal_user_message(self):
        assert _is_bot_message({"user": "U123", "text": "hello"}) is False

    def test_empty_dict(self):
        assert _is_bot_message({}) is False


class TestShouldProcessMessage:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        get_env_config.cache_clear()
        yield
        get_env_config.cache_clear()

    def test_dev_processes_user_message(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "dev")
        assert _should_process_message({"user": "U123", "text": "hi"}) is True

    def test_dev_processes_bot_message(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "dev")
        assert _should_process_message({"bot_id": "B123"}) is True

    def test_prod_skips_user_message(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "prod")
        assert _should_process_message({"user": "U123", "text": "hi"}) is False

    def test_prod_processes_bot_message(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "prod")
        assert _should_process_message({"bot_id": "B123"}) is True
