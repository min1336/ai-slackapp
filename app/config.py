from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEV = "dev"
    PROD = "prod"


class EnvironmentConfig(BaseSettings):
    environment: Environment = Environment.DEV

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_dev(self) -> bool:
        return self.environment == Environment.DEV

    @property
    def is_prod(self) -> bool:
        return self.environment == Environment.PROD


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
        return bool(self.host and self.password)

    @property
    def url(self) -> str:
        if not self.is_configured:
            return ""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"


_BASE_COLUMNS: dict[str, str] = {
    "정산기준일": "settlement_day",
    "작성자": "user_name",
    "이슈사항": "issue_type",
    "고객명": "customer_name",
    "예약번호": "booking_key",
    "업체명1": "company_name",
    "업체명2(대신배차)": "company_sub_name",
    "정산기준금액": "settlement_cost",
    "카모아 부담비용": "carmore_cost",
    "고객환불금액": "user_refund_cost",
    "판매채널": "sales_channel",
    "내용": "description",
    "처리": "status",
    "승인자": "approver_name",
    "등록시간": "created_at",
    "수정시간": "updated_at",
    "스레드 링크": "thread_url",
    "비고": "note",
    "반려자": "reviewer_name",
    "고객 정보 오류": "rejection_reason",
}


def _default_settlement_columns() -> dict[str, str]:
    return {**_BASE_COLUMNS, "정산완료": "settlement_completed"}


def _default_issue_log_columns() -> dict[str, str]:
    return {**_BASE_COLUMNS, "sync_key": "sync_key"}


class SlackChannelsConfig(BaseModel):
    transfer_reservation: str = ""
    error: str = ""  # 에러 모니터링 채널
    approval: str = ""  # 승인 전용 채널
    reservation: str = ""  # 예약 채널 (!정산이슈 + 스레드 탐색)

    model_config = ConfigDict(populate_by_name=True)


class SpreadsheetSheetConfig(BaseModel):
    name: str
    columns: dict[str, str] = Field(default_factory=dict)


class SheetsConfig(BaseModel):
    settlement: SpreadsheetSheetConfig = SpreadsheetSheetConfig(
        name="정산",
        columns=_default_settlement_columns(),
    )
    issue_log: SpreadsheetSheetConfig = SpreadsheetSheetConfig(
        name="정산이슈로그",
        columns=_default_issue_log_columns(),
    )


class SpreadsheetConfig(BaseModel):
    id: str
    sheets: SheetsConfig = SheetsConfig()

    def _sheet_config(self, sheet_type: str) -> SpreadsheetSheetConfig:
        if sheet_type == "settlement":
            return self.sheets.settlement
        if sheet_type == "issue_log":
            return self.sheets.issue_log
        raise ValueError(f"Unknown sheet_type: {sheet_type}")

    def sheet_name(self, sheet_type: str) -> str:
        return self._sheet_config(sheet_type).name

    def field_to_header(self, sheet_type: str) -> dict[str, str]:
        """내부용: sheet_type별 field_name → header_name 매핑."""
        columns = self._sheet_config(sheet_type).columns
        return {v: k for k, v in columns.items()}


class AppConfig(BaseModel):
    approvers: list[str] = []
    spreadsheet: SpreadsheetConfig
    slack_channels: SlackChannelsConfig = SlackChannelsConfig()
    sync_schedule: str = "0 8 * * *"  # cron 표현식 (기본: 매일 08:00)

    @property
    def error_channel_id(self) -> str:
        return self.slack_channels.error

    @property
    def approval_channel_id(self) -> str:
        return self.slack_channels.approval


def resolve_config_path() -> Path:
    project_root = Path(__file__).parent.parent
    env = os.getenv("ENVIRONMENT", "dev")
    return project_root / f"config.{env}.yaml"


def _load_app_config() -> AppConfig:
    config_path = resolve_config_path()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            f"Check ENVIRONMENT (={os.getenv('ENVIRONMENT', 'dev')})."
        )
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return AppConfig.model_validate(data)


@lru_cache
def get_app_config() -> AppConfig:
    return _load_app_config()


@lru_cache
def get_slack_settings() -> SlackProperties:
    return SlackProperties()


@lru_cache
def get_spreadsheet_settings() -> SpreadsheetProperties:
    return SpreadsheetProperties()


@lru_cache
def get_database_settings() -> DatabaseProperties:
    return DatabaseProperties()


@lru_cache
def get_env_config() -> EnvironmentConfig:
    return EnvironmentConfig()
