from __future__ import annotations

from app.config import database
from app.core import get_logger
from app.infrastructure.database import (
    ApprovalLogRepository,
    SettlementRepository,
    get_session,
    transactional,
)
from app.models import SettlementData, SettlementRow, SettlementStatus

logger = get_logger(__name__)


@transactional
def _mark_synced(session, settlement_id: int, log_id: int) -> None:
    """동기화 완료 표시 (별도 트랜잭션)."""
    SettlementRepository(session).mark_synced(settlement_id)
    ApprovalLogRepository(session).mark_synced(log_id)


def _sync_after_commit(settlement_id: int, log_id: int, row: SettlementRow) -> None:
    """커밋 후 Sheets 동기화."""
    from app.services.sync_service import sync_to_sheets

    try:
        sync_to_sheets(row)
        _mark_synced(settlement_id, log_id)
        logger.info(f"Sheets sync completed for {row.booking_key}")

    except Exception as e:
        logger.warning(f"Sheets sync failed for {row.booking_key}, will retry: {e}")


def save_settlement(
    data: SettlementData,
    status: SettlementStatus,
    approver_name: str,
    thread_url: str,
) -> bool:
    if status == SettlementStatus.REJECTED:
        return True

    if not database.is_configured:
        raise ValueError("DATABASE_URL is not configured")

    row = SettlementRow.from_settlement_data(
        data=data,
        status=status,
        approver_name=approver_name,
        thread_url=thread_url,
    )

    try:
        with get_session() as session:
            repo = SettlementRepository(session)
            settlement = repo.save(row)
            log = repo.add_log(row, settlement_id=settlement.id)
            settlement_id = settlement.id
            log_id = log.id
            session.after_commit(lambda: _sync_after_commit(settlement_id, log_id, row))

        return True

    except Exception as e:
        logger.exception(f"Settlement save failed: {e}")
        return False
