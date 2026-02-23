from __future__ import annotations

from pathlib import Path

from app.config import resolve_config_path

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestResolveConfigPath:
    """resolve_config_path() 우선순위: ENVIRONMENT > 기본값(dev)."""

    def test_default_is_dev(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)

        result = resolve_config_path()

        assert result == PROJECT_ROOT / "config.dev.yaml"

    def test_environment_selects_file(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "prod")

        result = resolve_config_path()

        assert result == PROJECT_ROOT / "config.prod.yaml"

    def test_environment_test(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "test")

        result = resolve_config_path()

        assert result == PROJECT_ROOT / "config.test.yaml"

    def test_app_config_file_is_ignored(self, monkeypatch):
        monkeypatch.setenv("APP_CONFIG_FILE", "config.test.yaml")
        monkeypatch.setenv("ENVIRONMENT", "prod")

        result = resolve_config_path()

        assert result == PROJECT_ROOT / "config.prod.yaml"
