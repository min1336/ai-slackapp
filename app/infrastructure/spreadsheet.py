from __future__ import annotations

import logging

import gspread
from google.oauth2.service_account import Credentials

from app.config import config, spreadsheet
from app.models import SettlementRow

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


def get_spreadsheet_client() -> gspread.Spreadsheet:
    credentials = Credentials.from_service_account_file(
        spreadsheet.credentials_file,
        scopes=SCOPES,
    )
    gc = gspread.authorize(credentials)
    return gc.open_by_key(config.spreadsheet.id)


def append_settlement_row(row: SettlementRow, sheet_name: str | None = None) -> bool:
    if sheet_name is None:
        sheet_name = config.spreadsheet.sheets.settlement

    try:
        spreadsheet = get_spreadsheet_client()
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.append_row(row.to_row())
        return True
    except Exception as e:
        logger.exception(f"스프레드시트 행 추가 실패 (sheet: {sheet_name}): {str(e)}")
        logger.debug(f"실패한 행 데이터: {row.to_row()}")
        return False


def append_approval_log_row(row: SettlementRow) -> bool:
    """승인로그 시트에 행 추가 (정산 시트와 동일한 컬럼 구조)"""
    sheet_name = config.spreadsheet.sheets.approval_log

    try:
        spreadsheet = get_spreadsheet_client()
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.append_row(row.to_row())
        return True
    except Exception as e:
        logger.exception(f"승인로그 시트 행 추가 실패 (sheet: {sheet_name}): {str(e)}")
        logger.debug(f"실패한 행 데이터: {row.to_row()}")
        return False
