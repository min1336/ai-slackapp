from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import database
from app.core import get_logger
from app.infrastructure.database import (
    ApprovalLogRepository,
    SettlementRepository,
    get_session,
    transactional,
)
from app.models import SettlementData, SettlementRow, SettlementStatus

if TYPE_CHECKING:
    from app.services.sync_service import SessionFactory

logger = get_logger(__name__)


@transactional
def _mark_synced(session, settlement_id: int, log_id: int) -> None:
    SettlementRepository(session).mark_synced(settlement_id)
    ApprovalLogRepository(session).mark_synced(log_id)


def _sync_after_commit(settlement_id: int, log_id: int, row: SettlementRow) -> None:
    from app.services.sync_service import sync_to_sheets

    try:
        sync_to_sheets(row, log_id)
        _mark_synced(settlement_id, log_id)
        logger.info(f"Sheets sync completed for {row.booking_key}")

    except Exception as e:
        logger.warning(f"Sheets sync failed for {row.booking_key}, will retry: {e}")


def save_settlement(
    data: SettlementData,
    status: SettlementStatus,
    approver_name: str,
    thread_url: str,
    rejection_reason: str = "",
    *,
    session_factory: SessionFactory | None = None,
) -> None:
    if not database.is_configured:
        raise ValueError("DATABASE_URL is not configured")

    row = SettlementRow.from_settlement_data(
        data=data,
        status=status,
        approver_name=approver_name,
        thread_url=thread_url,
    )

    if rejection_reason:
        logger.info(f"반려 사유: {rejection_reason}")

    _session = session_factory or get_session

    with _session() as session:
        repo = SettlementRepository(session)
        settlement = repo.save(row)
        log = repo.add_log(row, settlement_id=settlement.id)
        settlement_id = settlement.id
        log_id = log.id

        # 승인만 Sheets 동기화 (반려는 DB 저장만)
        if status == SettlementStatus.APPROVED:
            session.after_commit(lambda: _sync_after_commit(settlement_id, log_id, row))
