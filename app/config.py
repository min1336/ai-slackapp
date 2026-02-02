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


class DatabaseProperties(BaseSettings):
    user: str = "postgres"
    password: str = ""
    host: str = ""
    port: int = 5432
    dbname: str = "postgres"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DATABASE_",
        extra="ignore",
    )

    @property
    def is_configured(self) -> bool:
        """DB 설정 여부 확인."""
        return bool(self.host and self.password)

    @property
    def url(self) -> str:
        """SQLAlchemy connection URL 생성."""
        if not self.is_configured:
            return ""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"


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
    sync_interval_seconds: int = 300


def _load_app_config() -> AppConfig:
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return AppConfig.model_validate(data)


slack = SlackProperties()
spreadsheet = SpreadsheetProperties()
database = DatabaseProperties()
config = _load_app_config()
