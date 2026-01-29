from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class SlackProperties(BaseSettings):
    bot_token: str
    app_token: str
    signing_secret: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SLACK_",
        extra="ignore",
    )


class SpreadsheetProperties(BaseSettings):
    credentials_file: str = "credentials.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="GOOGLE_",
        extra="ignore",
    )


class SheetsConfig(BaseModel):
    settlement: str = "Sheet1"


class SpreadsheetConfig(BaseModel):
    id: str
    sheets: SheetsConfig = SheetsConfig()


class AppConfig(BaseModel):
    approvers: list[str] = []
    spreadsheet: SpreadsheetConfig


def _load_app_config() -> AppConfig:
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return AppConfig.model_validate(data)


slack = SlackProperties()
spreadsheet = SpreadsheetProperties()
config = _load_app_config()
