"""Google Sheets 동기화 서비스"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core import get_logger
from app.infrastructure.database import (
    ApprovalLogRepository,
    SettlementRepository,
    get_session,
)
from app.infrastructure.spreadsheet import (
    append_approval_log_row as sheets_append_log,
)
from app.infrastructure.spreadsheet import (
    save_settlement_row as sheets_save_settlement,
)

if TYPE_CHECKING:
    from app.models import SettlementRow

logger = get_logger(__name__)


def recover_stale_sync_records() -> tuple[int, int]:
    """앱 시작 시 중단된 동기화 레코드 복구.

    이전 실행에서 in_progress 상태로 남은 레코드를 pending으로 되돌림.
    단일 인스턴스 환경에서 앱 재시작 시 안전하게 재처리 가능하도록 함.

    Returns:
        (복구된 정산 수, 복구된 로그 수)
    """
    with get_session() as session:
        settlements = SettlementRepository(session).recover_stale_records()
        logs = ApprovalLogRepository(session).recover_stale_records()

    if settlements or logs:
        logger.info(f"Recovered stale records: {settlements} settlements, {logs} logs")

    return settlements, logs


def sync_to_sheets(row: SettlementRow, log_id: int) -> bool:
    """정산 데이터를 Google Sheets로 동기화.

    정산 시트 (upsert) + 승인 로그 시트 (append) 모두 저장.
    예외 발생 시 실패로 처리.
    """
    try:
        sheets_save_settlement(row)
        sheets_append_log(row, str(log_id))
        return True

    except Exception as e:
        logger.error(f"Sheets sync failed for {row.booking_key}: {e}")
        raise


def sync_pending_records() -> tuple[int, int]:
    """미동기화 레코드 일괄 동기화 (배치 작업용).

    처리 흐름:
    1. claim_unsynced()로 조회 + in_progress 상태 변경 (같은 트랜잭션)
    2. 외부 API(Sheets) 호출은 트랜잭션 밖에서
    3. 성공/실패 시 DB 업데이트는 별도 트랜잭션에서

    Returns:
        (동기화된 정산 수, 동기화된 로그 수)
    """
    synced_settlements = 0
    synced_logs = 0

    with get_session() as session:
        settlements = SettlementRepository(session).claim_unsynced(limit=100)
        logs = ApprovalLogRepository(session).claim_unsynced(limit=100)

    for settlement in settlements:
        try:
            row = _settlement_to_row(settlement)
            sheets_save_settlement(row)  # 실패 시 예외 발생
            with get_session() as session:
                SettlementRepository(session).mark_synced(settlement.id)
            synced_settlements += 1
        except Exception as e:
            logger.warning(
                f"Retry sync failed for settlement {settlement.booking_key}: {e}"
            )
            with get_session() as session:
                SettlementRepository(session).mark_sync_failed(settlement.id, str(e))

    for log in logs:
        try:
            row = _approval_log_to_row(log)
            sheets_append_log(row, str(log.id))  # 실패 시 예외 발생
            with get_session() as session:
                ApprovalLogRepository(session).mark_synced(log.id)
            synced_logs += 1
        except Exception as e:
            logger.warning(f"Retry sync failed for approval log {log.booking_key}: {e}")
            with get_session() as session:
                ApprovalLogRepository(session).mark_sync_failed(log.id, str(e))

    if synced_settlements or synced_logs:
        logger.info(
            f"Sync completed: {synced_settlements} settlements, {synced_logs} logs"
        )

    return synced_settlements, synced_logs


def _settlement_to_row(settlement) -> SettlementRow:
    """Settlement 엔티티를 SettlementRow로 변환."""
    from app.models import SettlementRow

    return SettlementRow(
        settlement_day=settlement.settlement_day,
        user_name=settlement.user_name,
        customer_name=settlement.customer_name,
        booking_key=settlement.booking_key,
        company_name=settlement.company_name,
        company_sub_name=settlement.company_sub_name,
        settlement_cost=_format_cost(settlement.settlement_cost),
        carmore_cost=_format_cost(settlement.carmore_cost),
        user_refund_cost=_format_cost(settlement.user_refund_cost),
        issue_type=settlement.issue_type,
        sales_channel=settlement.sales_channel,
        description=settlement.description,
        status=settlement.status,
        approver_name=settlement.approver_name,
        thread_url=settlement.thread_url,
        created_at=settlement.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        updated_at=settlement.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _approval_log_to_row(log) -> SettlementRow:
    """ApprovalLog 엔티티를 SettlementRow로 변환."""
    from app.models import SettlementRow

    return SettlementRow(
        settlement_day=log.settlement_day,
        user_name=log.user_name,
        customer_name=log.customer_name,
        booking_key=log.booking_key,
        company_name=log.company_name,
        company_sub_name=log.company_sub_name,
        settlement_cost=_format_cost(log.settlement_cost),
        carmore_cost=_format_cost(log.carmore_cost),
        user_refund_cost=_format_cost(log.user_refund_cost),
        issue_type=log.issue_type,
        sales_channel=log.sales_channel,
        description=log.description,
        status=log.status,
        approver_name=log.approver_name,
        thread_url=log.thread_url,
        created_at=log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _format_cost(value: int | None) -> str:
    """정수 금액을 문자열로 변환. None이면 빈 문자열."""
    if value is None:
        return ""
    return str(value)


class SyncError(Exception):
    """동기화 실패 예외"""

    pass
