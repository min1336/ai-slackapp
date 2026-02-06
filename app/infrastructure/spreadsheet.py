from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock

import gspread
from google.oauth2.service_account import Credentials
from gspread import Worksheet

from app.config import config, spreadsheet
from app.core import get_logger
from app.exceptions import SpreadsheetError
from app.models import SettlementColumnIndex, SettlementRow

logger = get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]
# 1-based column number for spreadsheet API
ISSUE_LOG_SYNC_KEY_COLUMN = SettlementColumnIndex.SYNC_KEY + 1
# 1-based column number for created_at
CREATED_AT_COLUMN = SettlementColumnIndex.CREATED_AT + 1
# 1-based column number for 정산완료 (21번째 컬럼, to_row() 20컬럼 뒤)
SETTLEMENT_COMPLETED_COLUMN = 21
# 1-based column number for booking_key
BOOKING_KEY_COLUMN = SettlementColumnIndex.BOOKING_KEY + 1

_spreadsheet_client: gspread.Spreadsheet | None = None
_client_lock = Lock()
_client_created_at: datetime | None = None
_CLIENT_REFRESH_MINUTES = 55


def get_spreadsheet_client() -> gspread.Spreadsheet:
    # 싱글톤, 55분마다 자동 갱신
    global _spreadsheet_client, _client_created_at

    with _client_lock:
        now = datetime.now()
        should_refresh = (
            _spreadsheet_client is None
            or _client_created_at is None
            or (now - _client_created_at) > timedelta(minutes=_CLIENT_REFRESH_MINUTES)
        )

        if should_refresh:
            credentials = Credentials.from_service_account_file(
                spreadsheet.credentials_file,
                scopes=SCOPES,
            )
            gc = gspread.authorize(credentials)
            _spreadsheet_client = gc.open_by_key(config.spreadsheet.id)
            _client_created_at = now
            logger.debug("spreadsheet_client_refreshed")

        return _spreadsheet_client


def save_settlement_row(row: SettlementRow, sheet_name: str | None = None) -> None:
    if sheet_name is None:
        sheet_name = config.spreadsheet.sheets.settlement

    try:
        existing_row_number = find_row_by_booking_key(row.booking_key, sheet_name)

        if existing_row_number:
            spreadsheet_client = get_spreadsheet_client()
            worksheet = spreadsheet_client.worksheet(sheet_name)
            created_at_cell = worksheet.cell(existing_row_number, CREATED_AT_COLUMN)
            existing_created_at = created_at_cell.value
            update_settlement_row(
                row, existing_row_number, sheet_name, existing_created_at or ""
            )
        else:
            spreadsheet_client = get_spreadsheet_client()
            worksheet = spreadsheet_client.worksheet(sheet_name)
            worksheet.append_row(row.to_row() + ["FALSE"])
    except SpreadsheetError:
        raise
    except Exception as e:
        logger.exception("spreadsheet_save_failed", sheet_name=sheet_name, error=str(e))
        logger.debug("failed_row_data", row_data=row.to_row())
        raise SpreadsheetError(
            message=f"Failed to save settlement row: {e}",
            details={
                "sheet_name": sheet_name,
                "booking_key": row.booking_key,
                "original_error": str(e),
            },
        ) from e


def append_issue_log_row(row: SettlementRow, sync_key: str) -> None:
    sheet_name = config.spreadsheet.sheets.issue_log

    try:
        spreadsheet_client = get_spreadsheet_client()
        worksheet = spreadsheet_client.worksheet(sheet_name)
        existing_row_number = find_row_by_sync_key(worksheet, sync_key)
        if existing_row_number:
            update_issue_log_row(row, existing_row_number, sync_key)
            return
        legacy_row_number = find_row_by_legacy_fingerprint(worksheet, row)
        if legacy_row_number:
            update_issue_log_row(row, legacy_row_number, sync_key)
            return
        worksheet.append_row(_to_issue_log_row(row, sync_key))
    except SpreadsheetError:
        raise
    except Exception as e:
        logger.exception("issue_log_append_failed", sheet_name=sheet_name, error=str(e))
        logger.debug("failed_row_data", row_data=_to_issue_log_row(row, sync_key))
        raise SpreadsheetError(
            message=f"Failed to append issue log: {e}",
            details={
                "sheet_name": sheet_name,
                "booking_key": row.booking_key,
                "original_error": str(e),
            },
        ) from e


def find_row_by_booking_key(booking_key: str, sheet_name: str) -> int | None:
    """booking_key로 활성(정산완료=FALSE) 행 번호를 찾는다.

    정산완료된 행은 무시하고, 활성 행만 반환한다.
    활성 행이 없으면 None (= 새 행 INSERT 필요).
    """
    try:
        spreadsheet_client = get_spreadsheet_client()
        worksheet = spreadsheet_client.worksheet(sheet_name)
        matches = worksheet.findall(booking_key)

        for cell in matches:
            if cell.col != BOOKING_KEY_COLUMN:
                continue
            completed = _get_cell(
                worksheet.row_values(cell.row),
                SETTLEMENT_COMPLETED_COLUMN - 1,
            )
            if completed != "TRUE":
                return cell.row

        return None
    except Exception as e:
        if _is_cell_not_found(e):
            return None
        logger.exception(
            "booking_key_search_failed",
            booking_key=booking_key,
            sheet_name=sheet_name,
            error=str(e),
        )
        raise SpreadsheetError(
            message=f"Failed to find row by booking key: {e}",
            details={
                "booking_key": booking_key,
                "sheet_name": sheet_name,
                "original_error": str(e),
            },
        ) from e


def get_spreadsheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{config.spreadsheet.id}"


def update_settlement_row(
    row: SettlementRow, row_number: int, sheet_name: str, existing_created_at: str
) -> None:
    try:
        spreadsheet_client = get_spreadsheet_client()
        worksheet = spreadsheet_client.worksheet(sheet_name)

        row_data = row.to_row()
        row_data[SettlementColumnIndex.CREATED_AT] = existing_created_at

        # 기존 정산완료 값 보존
        completed_cell = worksheet.cell(row_number, SETTLEMENT_COMPLETED_COLUMN)
        settlement_completed = completed_cell.value or "FALSE"
        row_data = row_data + [settlement_completed]

        cell_list = worksheet.range(row_number, 1, row_number, len(row_data))
        for i, cell in enumerate(cell_list):
            cell.value = row_data[i]

        worksheet.update_cells(cell_list)
    except Exception as e:
        logger.exception(
            "spreadsheet_row_update_failed",
            sheet_name=sheet_name,
            row_number=row_number,
            error=str(e),
        )
        logger.debug("failed_row_data", row_data=row.to_row())
        raise SpreadsheetError(
            message=f"Failed to update settlement row: {e}",
            details={
                "sheet_name": sheet_name,
                "row_number": row_number,
                "booking_key": row.booking_key,
                "original_error": str(e),
            },
        ) from e


def update_issue_log_row(row: SettlementRow, row_number: int, sync_key: str) -> None:
    sheet_name = config.spreadsheet.sheets.issue_log
    try:
        spreadsheet_client = get_spreadsheet_client()
        worksheet = spreadsheet_client.worksheet(sheet_name)

        row_data = _to_issue_log_row(row, sync_key)
        cell_list = worksheet.range(row_number, 1, row_number, len(row_data))
        for i, cell in enumerate(cell_list):
            cell.value = row_data[i]

        worksheet.update_cells(cell_list)
    except Exception as e:
        logger.exception(
            "issue_log_row_update_failed",
            sheet_name=sheet_name,
            row_number=row_number,
            error=str(e),
        )
        logger.debug("failed_row_data", row_data=_to_issue_log_row(row, sync_key))
        raise SpreadsheetError(
            message=f"Failed to update issue log row: {e}",
            details={
                "sheet_name": sheet_name,
                "row_number": row_number,
                "booking_key": row.booking_key,
                "original_error": str(e),
            },
        ) from e


def find_row_by_sync_key(worksheet: Worksheet, sync_key: str) -> int | None:
    try:
        matches = worksheet.findall(sync_key)
    except Exception as e:
        if _is_cell_not_found(e):
            return None
        logger.exception(
            "sync_key_search_failed",
            sync_key=sync_key,
            sheet_name=worksheet.title,
            error=str(e),
        )
        raise SpreadsheetError(
            message=f"Failed to find row by sync key: {e}",
            details={
                "sync_key": sync_key,
                "sheet_name": worksheet.title,
                "original_error": str(e),
            },
        ) from e

    for cell in matches:
        if cell.col == ISSUE_LOG_SYNC_KEY_COLUMN:
            return cell.row
        values = worksheet.row_values(cell.row)
        if _get_cell(values, ISSUE_LOG_SYNC_KEY_COLUMN - 1) == sync_key:
            return cell.row
    return None


def find_row_by_legacy_fingerprint(
    worksheet: Worksheet, row: SettlementRow
) -> int | None:
    try:
        matches = worksheet.findall(row.booking_key)
    except Exception as e:
        if _is_cell_not_found(e):
            return None
        logger.exception(
            "legacy_fingerprint_search_failed",
            booking_key=row.booking_key,
            sheet_name=worksheet.title,
            error=str(e),
        )
        raise SpreadsheetError(
            message=f"Failed to find row by legacy fingerprint: {e}",
            details={
                "booking_key": row.booking_key,
                "sheet_name": worksheet.title,
                "original_error": str(e),
            },
        ) from e

    for cell in matches:
        values = worksheet.row_values(cell.row)
        if _is_same_issue_log(values, row):
            return cell.row
    return None


def _to_issue_log_row(row: SettlementRow, sync_key: str) -> list[str]:
    return row.to_row() + [sync_key]


def _is_same_issue_log(values: list[str], row: SettlementRow) -> bool:
    # 레거시 중복 방지용 핑거프린트 비교
    return (
        _get_cell(values, SettlementColumnIndex.BOOKING_KEY) == row.booking_key
        and _get_cell(values, SettlementColumnIndex.STATUS) == row.status
        and _get_cell(values, SettlementColumnIndex.APPROVER_NAME) == row.approver_name
        and _get_cell(values, SettlementColumnIndex.CREATED_AT) == row.created_at
        and _get_cell(values, SettlementColumnIndex.THREAD_URL) == row.thread_url
    )


def _get_cell(values: list[str], index: int) -> str:
    if index < len(values):
        return values[index]
    return ""


def _is_cell_not_found(error: Exception) -> bool:
    return error.__class__.__name__ == "CellNotFound"


class DefaultSpreadsheetGateway:
    """SpreadsheetGateway Protocol의 기본 구현체.

    기존 모듈-레벨 함수에 위임합니다.
    """

    def save_settlement_row(
        self, row: SettlementRow, sheet_name: str | None = None
    ) -> None:
        save_settlement_row(row, sheet_name)

    def append_issue_log_row(self, row: SettlementRow, sync_key: str) -> None:
        append_issue_log_row(row, sync_key)

    def find_row_by_booking_key(
        self, booking_key: str, sheet_name: str | None = None
    ) -> int | None:
        if sheet_name is None:
            sheet_name = config.spreadsheet.sheets.settlement
        return find_row_by_booking_key(booking_key, sheet_name)
