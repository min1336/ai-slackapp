from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock

import gspread
from google.oauth2.service_account import Credentials
from gspread import Worksheet
from gspread.exceptions import APIError

from app.config import get_app_config, get_spreadsheet_settings
from app.core import get_logger
from app.exceptions import SpreadsheetError
from app.infrastructure.column_mapper import ColumnMapper, ColumnMapping
from app.infrastructure.retry import TTLCache, retry_on_rate_limit
from app.models import SETTLEMENT_FIELDS, SettlementRow

logger = get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

_spreadsheet_client: gspread.Spreadsheet | None = None
_client_lock = Lock()
_client_created_at: datetime | None = None
_CLIENT_REFRESH_MINUTES = 55
_CACHE_TTL_SECONDS = 300  # 5분

_worksheet_cache: TTLCache[str, Worksheet] = TTLCache(ttl=_CACHE_TTL_SECONDS)
_mapping_cache: TTLCache[str, ColumnMapping] = TTLCache(ttl=_CACHE_TTL_SECONDS)


def _get_worksheet(sheet_name: str) -> Worksheet:
    """워크시트를 TTL 캐시로 반환 (5분 유지)."""
    cached = _worksheet_cache.get(sheet_name)
    if cached is not None:
        return cached
    ws = get_spreadsheet_client().worksheet(sheet_name)
    _worksheet_cache.set(sheet_name, ws)
    return ws


def _resolve_mapping(worksheet: Worksheet, sheet_type: str) -> ColumnMapping:
    """워크시트의 헤더 행을 읽어 ColumnMapping을 반환 (TTL 캐시)."""
    cache_key = f"{worksheet.title}:{sheet_type}"
    cached = _mapping_cache.get(cache_key)
    if cached is not None:
        return cached

    headers = worksheet.row_values(1)
    if sheet_type == "settlement":
        required = (*SETTLEMENT_FIELDS, "settlement_completed")
    elif sheet_type == "issue_log":
        required = (*SETTLEMENT_FIELDS, "sync_key")
    else:
        raise ValueError(f"Unknown sheet_type: {sheet_type}")

    mapper = ColumnMapper(get_app_config().spreadsheet.field_to_header(sheet_type))
    mapping = mapper.resolve(headers, required)
    _mapping_cache.set(cache_key, mapping)
    return mapping


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
            _worksheet_cache.clear()
            _mapping_cache.clear()
            logger.debug("spreadsheet_client_refreshed")

        return _spreadsheet_client


@retry_on_rate_limit()
def save_settlement_row(
    row: SettlementRow,
    sheet_name: str | None = None,
    *,
    is_update: bool = False,
) -> None:
    if sheet_name is None:
        sheet_name = get_app_config().spreadsheet.sheet_name("settlement")

    try:
        worksheet = _get_worksheet(sheet_name)
        mapping = _resolve_mapping(worksheet, "settlement")

        if is_update:
            existing_row_number = find_row_by_booking_key(
                row.booking_key,
                sheet_name,
                worksheet,
                mapping,
            )
            if existing_row_number:
                update_settlement_row(row, existing_row_number, worksheet, mapping)
            else:
                # 시트에서 수동 삭제된 경우 → 폴백 INSERT
                row_data = mapping.dict_to_row(
                    row.to_dict(),
                    extra={"settlement_completed": "FALSE"},
                )
                worksheet.append_row(row_data)
        else:
            row_data = mapping.dict_to_row(
                row.to_dict(),
                extra={"settlement_completed": "FALSE"},
            )
            worksheet.append_row(row_data)
    except SpreadsheetError:
        raise
    except APIError:
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


@retry_on_rate_limit()
def append_issue_log_row(row: SettlementRow, sync_key: str) -> None:
    sheet_name = get_app_config().spreadsheet.sheet_name("issue_log")

    try:
        worksheet = _get_worksheet(sheet_name)
        mapping = _resolve_mapping(worksheet, "issue_log")
        row_data = mapping.dict_to_row(row.to_dict(), extra={"sync_key": sync_key})
        worksheet.append_row(row_data)
    except SpreadsheetError:
        raise
    except APIError:
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
            worksheet = _get_worksheet(sheet_name)
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
    except APIError:
        raise
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
    worksheet: Worksheet,
    mapping: ColumnMapping,
) -> None:
    try:
        existing_row = worksheet.row_values(row_number)
        existing_data = mapping.row_to_dict(existing_row)

        data = row.to_dict()
        data["created_at"] = existing_data.get("created_at", "")

        settlement_completed = (
            existing_data.get("settlement_completed", "FALSE") or "FALSE"
        )

        row_data = mapping.dict_to_row(
            data,
            extra={"settlement_completed": settlement_completed},
        )

        merged_row = _merge_with_existing_row(existing_row, row_data, mapping)

        cell_list = worksheet.range(row_number, 1, row_number, len(merged_row))
        for i, cell in enumerate(cell_list):
            cell.value = merged_row[i]

        worksheet.update_cells(cell_list)
    except APIError:
        raise
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


def _is_cell_not_found(error: Exception) -> bool:
    return error.__class__.__name__ == "CellNotFound"


class DefaultSpreadsheetGateway:
    """SpreadsheetGateway Protocol의 기본 구현체.

    기존 모듈-레벨 함수에 위임합니다.
    """

    def save_settlement_row(
        self,
        row: SettlementRow,
        sheet_name: str | None = None,
        *,
        is_update: bool = False,
    ) -> None:
        save_settlement_row(row, sheet_name, is_update=is_update)

    def append_issue_log_row(self, row: SettlementRow, sync_key: str) -> None:
        append_issue_log_row(row, sync_key)

    def find_row_by_booking_key(
        self, booking_key: str, sheet_name: str | None = None
    ) -> int | None:
        if sheet_name is None:
            sheet_name = get_app_config().spreadsheet.sheet_name("settlement")
        return find_row_by_booking_key(booking_key, sheet_name)
