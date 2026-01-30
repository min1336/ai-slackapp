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
    settlement: str = "정산"
    approval_log: str = "승인로그"


class SlackChannelsConfig(BaseModel):
    transfer_reservation: str = ""

    class Config:
        # 필드명을 snake_case에서 YAML 키로 매핑
        populate_by_name = True


class SpreadsheetConfig(BaseModel):
    id: str
    sheets: SheetsConfig = SheetsConfig()


class AppConfig(BaseModel):
    approvers: list[str] = []
    spreadsheet: SpreadsheetConfig
    slack_channels: SlackChannelsConfig = SlackChannelsConfig()


def _load_app_config() -> AppConfig:
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return AppConfig.model_validate(data)


slack = SlackProperties()
spreadsheet = SpreadsheetProperties()
config = _load_app_config()
