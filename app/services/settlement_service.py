from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import database
from app.core import get_logger
from app.infrastructure.database import (
    IssueLogRepository,
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
    IssueLogRepository(session).mark_synced(log_id)


def _sync_after_commit(settlement_id: int, log_id: int, row: SettlementRow) -> None:
    from app.services.sync_service import sync_to_sheets

    try:
        sync_to_sheets(row, log_id)
        _mark_synced(settlement_id, log_id)
        logger.info("sheets_sync_completed", booking_key=row.booking_key)

    except Exception as e:
        logger.warning("sheets_sync_failed", booking_key=row.booking_key, error=str(e))


# TODO: 승인/반려 처리 중 Sheets에서 정산완료가 동시 변경되는 edge case 존재.
# 현재는 무시 — 발생 확률 낮음 (승인 전 정산완료 체크는 운영상 없음).
# 향후 필요시 Sheets 조회 + 경고 메시지 추가 검토.
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
        rejection_reason=rejection_reason,
    )

    if rejection_reason:
        logger.info("rejection_saved", rejection_reason=rejection_reason)

    _session = session_factory or get_session

    with _session() as session:
        repo = SettlementRepository(session)
        settlement = repo.save(row)
        log = repo.add_log(row, settlement_id=settlement.id)
        settlement_id = settlement.id
        log_id = log.id

        # 모든 상태(요청/승인/반려)에서 Sheets 동기화 실행
        session.after_commit(lambda: _sync_after_commit(settlement_id, log_id, row))
