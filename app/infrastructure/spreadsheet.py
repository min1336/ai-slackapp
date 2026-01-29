from __future__ import annotations

import gspread
from google.oauth2.service_account import Credentials

from app.config import settings
from app.models import SettlementRow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


def get_spreadsheet_client() -> gspread.Spreadsheet:
    credentials = Credentials.from_service_account_file(
        settings.GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES,
    )
    gc = gspread.authorize(credentials)
    return gc.open_by_key(settings.SPREADSHEET_ID)


def append_settlement_row(row: SettlementRow, sheet_name: str | None = None) -> bool:
    if sheet_name is None:
        sheet_name = settings.SHEET_NAME

    try:
        spreadsheet = get_spreadsheet_client()
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.append_row(row.to_row())
        return True
    except Exception:
        return False
