from __future__ import annotations

import gspread
from google.oauth2.service_account import Credentials

from app.config import config, spreadsheet
from app.core import get_logger
from app.models import SettlementRow

logger = get_logger(__name__)

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


def save_settlement_row(row: SettlementRow, sheet_name: str | None = None) -> bool:
    if sheet_name is None:
        sheet_name = config.spreadsheet.sheets.settlement

    try:
        existing_row_number = find_row_by_booking_key(row.booking_key, sheet_name)

        if existing_row_number:
            spreadsheet = get_spreadsheet_client()
            worksheet = spreadsheet.worksheet(sheet_name)
            existing_created_at = worksheet.cell(existing_row_number, 15).value
            return update_settlement_row(
                row, existing_row_number, sheet_name, existing_created_at or ""
            )
        else:
            spreadsheet = get_spreadsheet_client()
            worksheet = spreadsheet.worksheet(sheet_name)
            worksheet.append_row(row.to_row())
            return True
    except Exception as e:
        logger.exception(f"스프레드시트 저장 실패 (sheet: {sheet_name}): {str(e)}")
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


def find_row_by_booking_key(booking_key: str, sheet_name: str) -> int | None:
    try:
        spreadsheet = get_spreadsheet_client()
        worksheet = spreadsheet.worksheet(sheet_name)
        cell = worksheet.find(booking_key)
        if cell:
            return cell.row
        return None
    except gspread.exceptions.CellNotFound:
        return None
    except Exception as e:
        logger.exception(
            f"booking_key 검색 실패: {e}",
            extra={"booking_key": booking_key, "sheet": sheet_name},
        )
        return None


def get_spreadsheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{config.spreadsheet.id}"


def update_settlement_row(
    row: SettlementRow, row_number: int, sheet_name: str, existing_created_at: str
) -> bool:
    try:
        spreadsheet = get_spreadsheet_client()
        worksheet = spreadsheet.worksheet(sheet_name)

        row_data = row.to_row()
        row_data[14] = existing_created_at

        cell_list = worksheet.range(row_number, 1, row_number, len(row_data))
        for i, cell in enumerate(cell_list):
            cell.value = row_data[i]

        worksheet.update_cells(cell_list)
        return True
    except Exception as e:
        logger.exception(
            f"스프레드시트 행 업데이트 실패: {e}",
            extra={"sheet": sheet_name, "row": row_number},
        )
        logger.debug(f"실패한 행 데이터: {row.to_row()}")
        return False
