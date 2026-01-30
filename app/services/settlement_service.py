from __future__ import annotations

from app.infrastructure.spreadsheet import (
    append_approval_log_row as _append_log_row,
)
from app.infrastructure.spreadsheet import append_settlement_row as _append_row
from app.models import SettlementData, SettlementRow, SettlementStatus


def save_settlement(
    data: SettlementData,
    status: SettlementStatus,
    approver_name: str,
    thread_url: str,
) -> bool:
    if status == SettlementStatus.REJECTED:
        return True

    row = SettlementRow.from_settlement_data(
        data=data,
        status=status,
        approver_name=approver_name,
        thread_url=thread_url,
    )

    settlement_saved = _append_row(row)
    log_saved = _append_log_row(row)

    return settlement_saved and log_saved
