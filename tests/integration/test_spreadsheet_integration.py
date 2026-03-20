from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.config import get_app_config
from app.exceptions import SpreadsheetError
from app.infrastructure import spreadsheet as spreadsheet_module
from app.models import SETTLEMENT_FIELDS, SettlementRow


def _spreadsheet_config():
    return get_app_config().settlement.spreadsheet


@dataclass
class FakeCell:
    row: int
    col: int
    value: str


class FakeWorksheet:
    def __init__(
        self,
        title: str,
        headers: list[str],
        data_rows: list[list[str]] | None = None,
    ) -> None:
        self.title = title
        self._rows: list[list[str]] = [headers.copy()]
        if data_rows:
            self._rows.extend(row.copy() for row in data_rows)

    @property
    def row_count(self) -> int:
        return len(self._rows)

    def row_values(self, row: int) -> list[str]:
        if row < 1 or row > len(self._rows):
            return []
        values = self._rows[row - 1].copy()
        while values and values[-1] == "":
            values.pop()
        return values

    def append_row(self, values: list[str]) -> None:
        self._rows.append(values.copy())

    def cell(self, row: int, col: int) -> FakeCell:
        return FakeCell(row=row, col=col, value=self._get_value(row, col))

    def range(
        self,
        row_start: int,
        col_start: int,
        row_end: int,
        col_end: int,
    ) -> list[FakeCell]:
        cells: list[FakeCell] = []
        for row in range(row_start, row_end + 1):
            for col in range(col_start, col_end + 1):
                cells.append(
                    FakeCell(
                        row=row,
                        col=col,
                        value=self._get_value(row, col),
                    )
                )
        return cells

    def update_cells(self, cells: list[FakeCell]) -> None:
        for cell in cells:
            self._set_value(cell.row, cell.col, cell.value)

    def findall(self, query: str) -> list[FakeCell]:
        matches: list[FakeCell] = []
        for row_idx, row in enumerate(self._rows, start=1):
            for col_idx, value in enumerate(row, start=1):
                if str(value) == str(query):
                    matches.append(FakeCell(row=row_idx, col=col_idx, value=str(value)))
        return matches

    def value_at_header(self, row_number: int, header: str) -> str:
        header_index = self._rows[0].index(header) + 1
        return self._get_value(row_number, header_index)

    def _get_value(self, row: int, col: int) -> str:
        if row < 1 or col < 1 or row > len(self._rows):
            return ""
        row_values = self._rows[row - 1]
        if col > len(row_values):
            return ""
        return row_values[col - 1]

    def _set_value(self, row: int, col: int, value: str) -> None:
        while len(self._rows) < row:
            self._rows.append([])
        row_values = self._rows[row - 1]
        if len(row_values) < col:
            row_values.extend([""] * (col - len(row_values)))
        row_values[col - 1] = value


class FakeSpreadsheetClient:
    def __init__(self, worksheets: dict[str, FakeWorksheet]) -> None:
        self._worksheets = worksheets

    def worksheet(self, name: str) -> FakeWorksheet:
        return self._worksheets[name]


def _sample_row(
    booking_key: str,
    *,
    status: str = "요청",
    user_name: str = "요청자",
    approver_name: str = "",
) -> SettlementRow:
    return SettlementRow(
        settlement_day="2025-01-28",
        user_name=user_name,
        customer_name="고객",
        booking_key=booking_key,
        company_name="업체",
        company_sub_name="서브업체",
        settlement_cost="100000",
        carmore_cost="1000",
        seller_channel_cost="0",
        user_refund_cost="0",
        issue_type="결제 오류",
        sales_channel="직접판매",
        description="설명",
        status=status,
        approver_name=approver_name,
        thread_url="http://example.com/thread",
        note="비고",
        reviewer_name=approver_name,
    )


def _headers_for_settlement(
    *,
    include_settlement_completed: bool = True,
    extra_header: str | None = None,
) -> list[str]:
    field_to_header = _spreadsheet_config().field_to_header("settlement")
    fields = [field for field in SETTLEMENT_FIELDS if field in field_to_header]
    if include_settlement_completed and "settlement_completed" in field_to_header:
        fields.append("settlement_completed")

    base_headers = [field_to_header[field] for field in fields]
    booking_header = field_to_header["booking_key"]
    leading_headers = [booking_header]
    if extra_header:
        leading_headers.append(extra_header)
    if include_settlement_completed and "settlement_completed" in field_to_header:
        leading_headers.append(field_to_header["settlement_completed"])

    trailing = [h for h in base_headers if h not in set(leading_headers)]
    return leading_headers + trailing


def _headers_for_issue_log(*, extra_header: str | None = None) -> list[str]:
    field_to_header = _spreadsheet_config().field_to_header("issue_log")
    fields = [field for field in SETTLEMENT_FIELDS if field in field_to_header]
    fields.append("sync_key")
    base_headers = [field_to_header[field] for field in fields]

    sync_key_header = field_to_header["sync_key"]
    leading_headers = [sync_key_header]
    if extra_header:
        leading_headers.append(extra_header)
    leading_headers.append(field_to_header["booking_key"])

    trailing = [h for h in base_headers if h not in set(leading_headers)]
    return leading_headers + trailing


def _row_values_from_fields(
    sheet_type: str,
    headers: list[str],
    field_values: dict[str, str],
    *,
    extra_values: dict[str, str] | None = None,
) -> list[str]:
    field_to_header = _spreadsheet_config().field_to_header(sheet_type)
    by_header = {
        field_to_header[field_name]: value
        for field_name, value in field_values.items()
        if field_name in field_to_header
    }
    if extra_values:
        by_header.update(extra_values)
    return [by_header.get(header, "") for header in headers]


def _make_service(
    client: FakeSpreadsheetClient,
) -> spreadsheet_module.SpreadsheetService:
    config = get_app_config()
    return spreadsheet_module.SpreadsheetService(
        client_factory=lambda: client,
        sheet_name_resolver=config.settlement.spreadsheet.sheet_name,
        field_to_header_resolver=config.settlement.spreadsheet.field_to_header,
    )


@pytest.mark.integration
def test_save_settlement_row_updates_mapped_columns_and_preserves_unmapped(
    monkeypatch,
) -> None:
    extra_header = "운영메모"
    headers = _headers_for_settlement(extra_header=extra_header)

    old_row = _sample_row("BK-001", status="요청", user_name="기존작성자")
    old_row.created_at = "2025-01-01 09:00:00"
    old_row.updated_at = "2025-01-01 09:00:00"
    old_data = old_row.to_dict()
    old_data["settlement_completed"] = "FALSE"

    worksheet = FakeWorksheet(
        title=_spreadsheet_config().sheet_name("settlement"),
        headers=headers,
        data_rows=[
            _row_values_from_fields(
                "settlement",
                headers,
                old_data,
                extra_values={extra_header: "KEEP"},
            )
        ],
    )
    client = FakeSpreadsheetClient(
        {_spreadsheet_config().sheet_name("settlement"): worksheet}
    )
    service = _make_service(client)

    new_row = _sample_row(
        "BK-001",
        status="승인",
        user_name="새작성자",
        approver_name="검토자",
    )
    service.save_settlement_row(new_row, is_update=True)

    field_to_header = _spreadsheet_config().field_to_header("settlement")
    assert worksheet.row_count == 2
    assert worksheet.value_at_header(2, extra_header) == "KEEP"
    assert worksheet.value_at_header(2, field_to_header["status"]) == "승인"
    assert worksheet.value_at_header(2, field_to_header["user_name"]) == "새작성자"
    if "created_at" in field_to_header:
        assert (
            worksheet.value_at_header(2, field_to_header["created_at"])
            == "2025-01-01 09:00:00"
        )
    if "approver_name" in field_to_header:
        assert (
            worksheet.value_at_header(2, field_to_header["approver_name"]) == "검토자"
        )


@pytest.mark.integration
def test_find_row_by_booking_key_skips_completed_rows(monkeypatch) -> None:
    headers = _headers_for_settlement()

    completed = _sample_row("BK-777", status="승인", approver_name="담당자")
    completed_data = completed.to_dict()
    completed_data["settlement_completed"] = "TRUE"

    active = _sample_row("BK-777", status="요청")
    active_data = active.to_dict()
    active_data["settlement_completed"] = "FALSE"

    worksheet = FakeWorksheet(
        title=_spreadsheet_config().sheet_name("settlement"),
        headers=headers,
        data_rows=[
            _row_values_from_fields("settlement", headers, completed_data),
            _row_values_from_fields("settlement", headers, active_data),
        ],
    )
    client = FakeSpreadsheetClient(
        {_spreadsheet_config().sheet_name("settlement"): worksheet}
    )
    service = _make_service(client)

    found = service.find_row_by_booking_key(
        "BK-777",
        _spreadsheet_config().sheet_name("settlement"),
    )
    assert found == 3


@pytest.mark.integration
def test_save_settlement_row_raises_when_required_header_missing(monkeypatch) -> None:
    headers = _headers_for_settlement(include_settlement_completed=False)
    worksheet = FakeWorksheet(
        title=_spreadsheet_config().sheet_name("settlement"),
        headers=headers,
    )
    client = FakeSpreadsheetClient(
        {_spreadsheet_config().sheet_name("settlement"): worksheet}
    )
    service = _make_service(client)

    row = _sample_row("BK-MISSING")
    with pytest.raises(SpreadsheetError, match="settlement_completed"):
        service.save_settlement_row(row)


@pytest.mark.integration
def test_append_issue_log_row_skips_existing_sync_key_and_preserves_unmapped(
    monkeypatch,
) -> None:
    extra_header = "운영메모"
    headers = _headers_for_issue_log(extra_header=extra_header)

    old_row = _sample_row("BK-LOG-1", status="요청")
    old_data = old_row.to_dict()
    old_data["sync_key"] = "42"
    worksheet = FakeWorksheet(
        title=_spreadsheet_config().sheet_name("issue_log"),
        headers=headers,
        data_rows=[
            _row_values_from_fields(
                "issue_log",
                headers,
                old_data,
                extra_values={extra_header: "LEGACY"},
            )
        ],
    )
    client = FakeSpreadsheetClient(
        {_spreadsheet_config().sheet_name("issue_log"): worksheet}
    )
    service = _make_service(client)

    new_row = _sample_row("BK-LOG-1", status="반려", approver_name="반려자")
    service.append_issue_log_row(new_row, sync_key="42")

    field_to_header = _spreadsheet_config().field_to_header("issue_log")
    assert worksheet.row_count == 2
    assert worksheet.value_at_header(2, extra_header) == "LEGACY"
    assert worksheet.value_at_header(2, field_to_header["status"]) == "요청"
    assert worksheet.value_at_header(2, field_to_header["approver_name"]) == ""
