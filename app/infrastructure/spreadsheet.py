from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Lock

import gspread
from gspread import Worksheet
from gspread.exceptions import APIError, GSpreadException

from app.core import get_logger
from app.exceptions import SpreadsheetError
from app.infrastructure.column_mapper import ColumnMapper, ColumnMapping
from app.infrastructure.retry import TTLCache, retry_on_rate_limit
from app.models import SETTLEMENT_FIELDS, SettlementRow

logger = get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


def _is_cell_not_found(error: Exception) -> bool:
    return error.__class__.__name__ == "CellNotFound"


def _merge_with_existing_row(
    existing_row: list[str],
    mapped_row: list[str],
    mapping: ColumnMapping,
) -> list[str]:
    merged_row = existing_row.copy()
    if len(merged_row) < len(mapped_row):
        merged_row.extend([""] * (len(mapped_row) - len(merged_row)))

    for idx in mapping.field_to_index.values():
        if idx >= len(merged_row):
            merged_row.extend([""] * (idx + 1 - len(merged_row)))
        merged_row[idx] = mapped_row[idx] if idx < len(mapped_row) else ""

    return merged_row


class SpreadsheetService:
    """SpreadsheetGateway 구현체 — gspread 기반 Google Sheets 접근."""

    def __init__(
        self,
        client_factory: Callable[[], gspread.Spreadsheet],
        sheet_name_resolver: Callable[[str], str],
        field_to_header_resolver: Callable[[str], dict[str, str]],
        header_row_resolver: Callable[[str], int] | None = None,
        *,
        client_refresh_minutes: int = 55,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._client_factory = client_factory
        self._sheet_name = sheet_name_resolver
        self._field_to_header = field_to_header_resolver
        self._header_row = header_row_resolver or (lambda _: 1)

        self._client: gspread.Spreadsheet | None = None
        self._client_lock = Lock()
        self._client_created_at: datetime | None = None
        self._client_refresh_minutes = client_refresh_minutes

        self._worksheet_cache: TTLCache[str, Worksheet] = TTLCache(
            ttl=cache_ttl_seconds
        )
        self._mapping_cache: TTLCache[str, ColumnMapping] = TTLCache(
            ttl=cache_ttl_seconds
        )

    def _get_client(self) -> gspread.Spreadsheet:
        with self._client_lock:
            now = datetime.now()
            should_refresh = (
                self._client is None
                or self._client_created_at is None
                or (now - self._client_created_at)
                > timedelta(minutes=self._client_refresh_minutes)
            )

            if should_refresh:
                self._client = self._client_factory()
                self._client_created_at = now
                self._worksheet_cache.clear()
                self._mapping_cache.clear()
                logger.debug("spreadsheet_client_refreshed")

            return self._client  # type: ignore[return-value]

    def _get_worksheet(self, sheet_name: str) -> Worksheet:
        cached = self._worksheet_cache.get(sheet_name)
        if cached is not None:
            return cached
        ws = self._get_client().worksheet(sheet_name)
        self._worksheet_cache.set(sheet_name, ws)
        return ws

    def _resolve_mapping(self, worksheet: Worksheet, sheet_type: str) -> ColumnMapping:
        cache_key = f"{worksheet.title}:{sheet_type}"
        cached = self._mapping_cache.get(cache_key)
        if cached is not None:
            return cached

        headers = worksheet.row_values(self._header_row(sheet_type))
        field_to_header = self._field_to_header(sheet_type)
        configured = tuple(f for f in SETTLEMENT_FIELDS if f in field_to_header)

        if sheet_type == "settlement":
            required = (*configured, "settlement_completed")
        elif sheet_type == "issue_log":
            required = (*configured, "sync_key")
        else:
            raise ValueError(f"Unknown sheet_type: {sheet_type}")

        mapper = ColumnMapper(field_to_header)
        mapping = mapper.resolve(headers, required)
        self._mapping_cache.set(cache_key, mapping)
        return mapping

    @retry_on_rate_limit()
    def save_settlement_row(
        self,
        row: SettlementRow,
        sheet_name: str | None = None,
        *,
        is_update: bool = False,
    ) -> None:
        if sheet_name is None:
            sheet_name = self._sheet_name("settlement")

        try:
            worksheet = self._get_worksheet(sheet_name)
            mapping = self._resolve_mapping(worksheet, "settlement")

            if is_update:
                existing_row_number = self.find_row_by_booking_key(
                    row.booking_key,
                    sheet_name,
                    worksheet,
                    mapping,
                )
                if existing_row_number:
                    self._update_settlement_row(
                        row, existing_row_number, worksheet, mapping
                    )
                else:
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
        except (SpreadsheetError, APIError):
            raise
        except (GSpreadException, ValueError, KeyError) as e:
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

    def _find_by_sync_key(
        self, worksheet: Worksheet, mapping: ColumnMapping, sync_key: str
    ) -> bool:
        try:
            sync_key_col = mapping.column_of("sync_key")
            matches = worksheet.findall(sync_key)
            return any(cell.col == sync_key_col for cell in matches)
        except (GSpreadException, KeyError) as e:
            if isinstance(e, GSpreadException) and _is_cell_not_found(e):
                return False
            logger.warning(
                "sync_key_search_failed",
                sync_key=sync_key,
                error=str(e),
            )
            return False

    @retry_on_rate_limit()
    def append_issue_log_row(self, row: SettlementRow, sync_key: str) -> None:
        sheet_name = self._sheet_name("issue_log")

        try:
            worksheet = self._get_worksheet(sheet_name)
            mapping = self._resolve_mapping(worksheet, "issue_log")

            if self._find_by_sync_key(worksheet, mapping, sync_key):
                logger.info(
                    "issue_log_row_already_exists",
                    sync_key=sync_key,
                    booking_key=row.booking_key,
                )
                return

            row_data = mapping.dict_to_row(row.to_dict(), extra={"sync_key": sync_key})
            worksheet.append_row(row_data)
        except (SpreadsheetError, APIError):
            raise
        except (GSpreadException, ValueError, KeyError) as e:
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
        self,
        booking_key: str,
        sheet_name: str | None = None,
        worksheet: Worksheet | None = None,
        mapping: ColumnMapping | None = None,
    ) -> int | None:
        """booking_key로 활성(정산완료=FALSE) 행 번호를 찾는다."""
        try:
            if sheet_name is None:
                sheet_name = self._sheet_name("settlement")
            if worksheet is None:
                worksheet = self._get_worksheet(sheet_name)
            if mapping is None:
                mapping = self._resolve_mapping(worksheet, "settlement")
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
        except GSpreadException as e:
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

    @retry_on_rate_limit()
    def is_settlement_completed(self, booking_key: str) -> bool:
        try:
            sheet_name = self._sheet_name("settlement")
            worksheet = self._get_worksheet(sheet_name)
            mapping = self._resolve_mapping(worksheet, "settlement")
            matches = worksheet.findall(booking_key)

            booking_col = mapping.column_of("booking_key")
            has_completed = False
            has_active = False
            for cell in matches:
                if cell.col != booking_col:
                    continue
                data = mapping.row_to_dict(worksheet.row_values(cell.row))
                if data.get("settlement_completed") == "TRUE":
                    has_completed = True
                else:
                    has_active = True

            # 과거 완료(TRUE) 히스토리가 있더라도 활성(FALSE) 행이 존재하면
            # 현재 처리 가능한 건으로 본다.
            return has_completed and not has_active
        except (APIError, GSpreadException, ValueError, KeyError):
            logger.warning(
                "settlement_completed_check_failed",
                booking_key=booking_key,
            )
            return False

    @retry_on_rate_limit()
    def update_settlement_transfer(
        self, booking_key: str, note: str, transfer_status: str
    ) -> None:
        """비고 + 이관상태 컬럼을 타겟 업데이트한다."""
        try:
            sheet_name = self._sheet_name("settlement")
            worksheet = self._get_worksheet(sheet_name)
            mapping = self._resolve_mapping(worksheet, "settlement")
            row_number = self.find_row_by_booking_key(
                booking_key, sheet_name, worksheet, mapping
            )
            if not row_number:
                return
            note_col = mapping.column_of("note")
            transfer_col = mapping.column_of("transfer_status")
            worksheet.update_cell(row_number, note_col, note)
            worksheet.update_cell(row_number, transfer_col, transfer_status)
        except (APIError, SpreadsheetError):
            raise
        except (GSpreadException, ValueError, KeyError) as e:
            logger.exception(
                "settlement_transfer_update_failed",
                booking_key=booking_key,
                error=str(e),
            )
            raise SpreadsheetError(
                message=f"Failed to update settlement transfer: {e}",
                details={
                    "booking_key": booking_key,
                    "original_error": str(e),
                },
            ) from e

    @retry_on_rate_limit()
    def get_completed_booking_keys(self) -> set[str]:
        try:
            sheet_name = self._sheet_name("settlement")
            worksheet = self._get_worksheet(sheet_name)
            mapping = self._resolve_mapping(worksheet, "settlement")

            all_rows = worksheet.get_all_values()
            header_row = self._header_row("settlement")
            if len(all_rows) <= header_row:
                return set()

            completed_keys: set[str] = set()
            for row_values in all_rows[header_row:]:
                data = mapping.row_to_dict(row_values)
                if data.get("settlement_completed") == "TRUE":
                    booking_key = data.get("booking_key", "")
                    if booking_key:
                        completed_keys.add(booking_key)

            return completed_keys
        except (APIError, GSpreadException, ValueError, KeyError) as e:
            logger.warning("get_completed_booking_keys_failed", error=str(e))
            return set()

    def _update_settlement_row(
        self,
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
            for cell, value in zip(cell_list, merged_row, strict=True):
                cell.value = value

            worksheet.update_cells(cell_list)
        except APIError:
            raise
        except (GSpreadException, ValueError, KeyError) as e:
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
