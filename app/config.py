from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SLACK_BOT_TOKEN: str
    SLACK_APP_TOKEN: str
    SLACK_SIGNING_SECRET: str | None = None
    APPROVERS: str = ""

    # Google Sheets
    GOOGLE_CREDENTIALS_FILE: str = "credentials.json"
    SPREADSHEET_ID: str = ""
    SHEET_NAME: str = "Sheet1"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def approver_ids(self) -> list[str]:
        if not self.APPROVERS:
            return []
        return [uid.strip() for uid in self.APPROVERS.split(",") if uid.strip()]


settings = Settings()
