from __future__ import annotations

from app.infrastructure.spreadsheet import append_settlement_row as _append_row
from app.models import SettlementData, SettlementRow, SettlementStatus


def save_settlement(
    data: SettlementData,
    status: SettlementStatus,
    approver_name: str,
    thread_url: str,
) -> bool:
    row = SettlementRow.from_settlement_data(
        data=data,
        status=status,
        approver_name=approver_name,
        thread_url=thread_url,
    )
    return _append_row(row)
