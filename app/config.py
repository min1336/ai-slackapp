from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict
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
    issue_log: str = "정산이슈로그"


class SlackChannelsConfig(BaseModel):
    transfer_reservation: str = ""
    error: str = ""  # 에러 모니터링 채널
    approval: str = ""  # 승인 전용 채널

    model_config = ConfigDict(populate_by_name=True)


class SpreadsheetConfig(BaseModel):
    id: str
    sheets: SheetsConfig = SheetsConfig()
    columns: dict[str, str] = {
        "settlement_day": "정산기준일",
        "user_name": "작성자",
        "issue_type": "이슈사항",
        "customer_name": "고객명",
        "booking_key": "예약번호",
        "company_name": "업체명1",
        "company_sub_name": "업체명2(대신배차)",
        "settlement_cost": "정산기준금액",
        "carmore_cost": "카모아 부담비용",
        "user_refund_cost": "고객환불금액",
        "sales_channel": "판매채널",
        "description": "내용",
        "status": "처리",
        "approver_name": "승인자",
        "created_at": "등록시간",
        "updated_at": "수정시간",
        "thread_url": "스레드 링크",
        "note": "비고",
        "reviewer_name": "반려자",
        "rejection_reason": "고객 정보 오류",
        "settlement_completed": "정산완료",
        "sync_key": "sync_key",
    }


class AppConfig(BaseModel):
    approvers: list[str] = []
    spreadsheet: SpreadsheetConfig
    slack_channels: SlackChannelsConfig = SlackChannelsConfig()
    sync_interval_seconds: int = 300

    @property
    def error_channel_id(self) -> str:
        """에러 모니터링 채널 ID."""
        return self.slack_channels.error

    @property
    def approval_channel_id(self) -> str:
        """승인 전용 채널 ID."""
        return self.slack_channels.approval


def _load_app_config() -> AppConfig:
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return AppConfig.model_validate(data)


slack = SlackProperties()
spreadsheet = SpreadsheetProperties()
database = DatabaseProperties()
config = _load_app_config()


@lru_cache
def get_app_config() -> AppConfig:
    """AppConfig 싱글톤 반환."""
    return config


@lru_cache
def get_slack_settings() -> SlackProperties:
    """SlackProperties 싱글톤 반환."""
    return slack


@lru_cache
def get_spreadsheet_settings() -> SpreadsheetProperties:
    """SpreadsheetProperties 싱글톤 반환."""
    return spreadsheet


@lru_cache
def get_database_settings() -> DatabaseProperties:
    """DatabaseProperties 싱글톤 반환."""
    return database
