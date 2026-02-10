from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.models import SettlementRow


@runtime_checkable
class SpreadsheetGateway(Protocol):
    def save_settlement_row(
        self,
        row: SettlementRow,
        sheet_name: str | None = None,
        *,
        is_update: bool = False,
    ) -> None: ...

    def append_issue_log_row(self, row: SettlementRow, sync_key: str) -> None: ...

    def find_row_by_booking_key(
        self, booking_key: str, sheet_name: str | None = None
    ) -> int | None: ...
