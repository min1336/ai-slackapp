from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock

import gspread
from google.oauth2.service_account import Credentials
from gspread import Worksheet

from app.config import get_app_config, get_spreadsheet_settings
from app.core import get_logger
from app.exceptions import SpreadsheetError
from app.infrastructure.column_mapper import ColumnMapper, ColumnMapping
from app.models import SETTLEMENT_FIELDS, SettlementRow

logger = get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

_spreadsheet_client: gspread.Spreadsheet | None = None
_client_lock = Lock()
_client_created_at: datetime | None = None
_CLIENT_REFRESH_MINUTES = 55


def _resolve_mapping(worksheet: Worksheet, sheet_type: str) -> ColumnMapping:
    """워크시트의 헤더 행을 읽어 ColumnMapping을 반환."""
    headers = worksheet.row_values(1)
    if sheet_type == "settlement":
        required = (*SETTLEMENT_FIELDS, "settlement_completed")
    elif sheet_type == "issue_log":
        required = (*SETTLEMENT_FIELDS, "sync_key")
    else:
        raise ValueError(f"Unknown sheet_type: {sheet_type}")

    mapper = ColumnMapper(get_app_config().spreadsheet.field_to_header(sheet_type))
    return mapper.resolve(headers, required)


def _merge_with_existing_row(
    existing_row: list[str],
    mapped_row: list[str],
    mapping: ColumnMapping,
) -> list[str]:
    """기존 행의 비매핑 컬럼을 보존하면서 매핑된 컬럼만 교체한다."""
    merged_row = existing_row.copy()
    if len(merged_row) < len(mapped_row):
        merged_row.extend([""] * (len(mapped_row) - len(merged_row)))

    for _, idx in mapping.field_to_index.items():
        if idx >= len(merged_row):
            merged_row.extend([""] * (idx + 1 - len(merged_row)))
        merged_row[idx] = mapped_row[idx] if idx < len(mapped_row) else ""

    return merged_row


def get_spreadsheet_client() -> gspread.Spreadsheet:
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
                get_spreadsheet_settings().credentials_file,
                scopes=SCOPES,
            )
            gc = gspread.authorize(credentials)
            _spreadsheet_client = gc.open_by_key(get_app_config().spreadsheet.id)
            _client_created_at = now
            logger.debug("spreadsheet_client_refreshed")

        return _spreadsheet_client


def save_settlement_row(row: SettlementRow, sheet_name: str | None = None) -> None:
    if sheet_name is None:
        sheet_name = get_app_config().spreadsheet.sheet_name("settlement")

    try:
        spreadsheet_client = get_spreadsheet_client()
        worksheet = spreadsheet_client.worksheet(sheet_name)
        mapping = _resolve_mapping(worksheet, "settlement")

        existing_row_number = find_row_by_booking_key(
            row.booking_key,
            sheet_name,
            worksheet,
            mapping,
        )

        if existing_row_number:
            created_at_cell = worksheet.cell(
                existing_row_number,
                mapping.column_of("created_at"),
            )
            existing_created_at = created_at_cell.value
            update_settlement_row(
                row,
                existing_row_number,
                existing_created_at or "",
                worksheet,
                mapping,
            )
        else:
            row_data = mapping.dict_to_row(
                row.to_dict(),
                extra={"settlement_completed": "FALSE"},
            )
            worksheet.append_row(row_data)
    except SpreadsheetError:
        raise
    except Exception as e:
        logger.exception(
            "spreadsheet_save_failed",
            sheet_name=sheet_name,
            error=str(e),
        )
        logger.debug("failed_row_data", row_data=row.to_dict())
        raise SpreadsheetError(
            message=f"Failed to save settlement row: {e}",
            details={
                "sheet_name": sheet_name,
                "booking_key": row.booking_key,
                "original_error": str(e),
            },
        ) from e


def append_issue_log_row(row: SettlementRow, sync_key: str) -> None:
    sheet_name = get_app_config().spreadsheet.sheet_name("issue_log")

    try:
        spreadsheet_client = get_spreadsheet_client()
        worksheet = spreadsheet_client.worksheet(sheet_name)
        mapping = _resolve_mapping(worksheet, "issue_log")

        existing_row_number = find_row_by_sync_key(worksheet, sync_key, mapping)
        if existing_row_number:
            update_issue_log_row(
                row,
                existing_row_number,
                sync_key,
                worksheet,
                mapping,
            )
            return
        legacy_row_number = find_row_by_legacy_fingerprint(worksheet, row, mapping)
        if legacy_row_number:
            update_issue_log_row(
                row,
                legacy_row_number,
                sync_key,
                worksheet,
                mapping,
            )
            return

        row_data = mapping.dict_to_row(row.to_dict(), extra={"sync_key": sync_key})
        worksheet.append_row(row_data)
    except SpreadsheetError:
        raise
    except Exception as e:
        logger.exception(
            "issue_log_append_failed",
            sheet_name=sheet_name,
            error=str(e),
        )
        logger.debug("failed_row_data", row_data=row.to_dict())
        raise SpreadsheetError(
            message=f"Failed to append issue log: {e}",
            details={
                "sheet_name": sheet_name,
                "booking_key": row.booking_key,
                "original_error": str(e),
            },
        ) from e


def find_row_by_booking_key(
    booking_key: str,
    sheet_name: str,
    worksheet: Worksheet | None = None,
    mapping: ColumnMapping | None = None,
) -> int | None:
    """booking_key로 활성(정산완료=FALSE) 행 번호를 찾는다.

    정산완료된 행은 무시하고, 활성 행만 반환한다.
    활성 행이 없으면 None (= 새 행 INSERT 필요).
    """
    try:
        if worksheet is None:
            spreadsheet_client = get_spreadsheet_client()
            worksheet = spreadsheet_client.worksheet(sheet_name)
        if mapping is None:
            mapping = _resolve_mapping(worksheet, "settlement")
        matches = worksheet.findall(booking_key)

        booking_col = mapping.column_of("booking_key")
        for cell in matches:
            if cell.col != booking_col:
                continue
            data = mapping.row_to_dict(worksheet.row_values(cell.row))
            if data.get("settlement_completed") != "TRUE":
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
    return f"https://docs.google.com/spreadsheets/d/{get_app_config().spreadsheet.id}"


def update_settlement_row(
    row: SettlementRow,
    row_number: int,
    existing_created_at: str,
    worksheet: Worksheet,
    mapping: ColumnMapping,
) -> None:
    try:
        data = row.to_dict()
        data["created_at"] = existing_created_at

        completed_cell = worksheet.cell(
            row_number, mapping.column_of("settlement_completed")
        )
        settlement_completed = completed_cell.value or "FALSE"

        row_data = mapping.dict_to_row(
            data,
            extra={"settlement_completed": settlement_completed},
        )

        existing_row = worksheet.row_values(row_number)
        merged_row = _merge_with_existing_row(existing_row, row_data, mapping)

        cell_list = worksheet.range(row_number, 1, row_number, len(merged_row))
        for i, cell in enumerate(cell_list):
            cell.value = merged_row[i]

        worksheet.update_cells(cell_list)
    except Exception as e:
        logger.exception(
            "spreadsheet_row_update_failed",
            sheet_name=worksheet.title,
            row_number=row_number,
            error=str(e),
        )
        logger.debug("failed_row_data", row_data=row.to_dict())
        raise SpreadsheetError(
            message=f"Failed to update settlement row: {e}",
            details={
                "sheet_name": worksheet.title,
                "row_number": row_number,
                "booking_key": row.booking_key,
                "original_error": str(e),
            },
        ) from e


def update_issue_log_row(
    row: SettlementRow,
    row_number: int,
    sync_key: str,
    worksheet: Worksheet,
    mapping: ColumnMapping,
) -> None:
    try:
        row_data = mapping.dict_to_row(row.to_dict(), extra={"sync_key": sync_key})
        existing_row = worksheet.row_values(row_number)
        merged_row = _merge_with_existing_row(existing_row, row_data, mapping)

        cell_list = worksheet.range(row_number, 1, row_number, len(merged_row))
        for i, cell in enumerate(cell_list):
            cell.value = merged_row[i]

        worksheet.update_cells(cell_list)
    except Exception as e:
        logger.exception(
            "issue_log_row_update_failed",
            sheet_name=worksheet.title,
            row_number=row_number,
            error=str(e),
        )
        logger.debug("failed_row_data", row_data=row.to_dict())
        raise SpreadsheetError(
            message=f"Failed to update issue log row: {e}",
            details={
                "sheet_name": worksheet.title,
                "row_number": row_number,
                "booking_key": row.booking_key,
                "original_error": str(e),
            },
        ) from e


def find_row_by_sync_key(
    worksheet: Worksheet,
    sync_key: str,
    mapping: ColumnMapping | None = None,
) -> int | None:
    if mapping is None:
        mapping = _resolve_mapping(worksheet, "issue_log")

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

    sync_key_col = mapping.column_of("sync_key")
    for cell in matches:
        if cell.col == sync_key_col:
            return cell.row
        data = mapping.row_to_dict(worksheet.row_values(cell.row))
        if data.get("sync_key") == sync_key:
            return cell.row
    return None


def find_row_by_legacy_fingerprint(
    worksheet: Worksheet,
    row: SettlementRow,
    mapping: ColumnMapping | None = None,
) -> int | None:
    if mapping is None:
        mapping = _resolve_mapping(worksheet, "issue_log")

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
        data = mapping.row_to_dict(worksheet.row_values(cell.row))
        if _is_same_issue_log(data, row):
            return cell.row
    return None


def _is_same_issue_log(data: dict[str, str], row: SettlementRow) -> bool:
    return (
        data.get("booking_key") == row.booking_key
        and data.get("status") == row.status
        and data.get("approver_name") == row.approver_name
        and data.get("created_at") == row.created_at
        and data.get("thread_url") == row.thread_url
    )


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
            sheet_name = get_app_config().spreadsheet.sheet_name("settlement")
        return find_row_by_booking_key(booking_key, sheet_name)
