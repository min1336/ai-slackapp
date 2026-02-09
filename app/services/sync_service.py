"""Google Sheets 동기화 서비스"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.constants import DateFormat
from app.core import get_logger
from app.infrastructure.database import (
    IssueLogRepository,
    SettlementRepository,
    get_session,
)
from app.infrastructure.protocols import SpreadsheetGateway
from app.infrastructure.spreadsheet import DefaultSpreadsheetGateway
from app.models import SettlementRow
from app.models.settlement import format_cost

logger = get_logger(__name__)

# get_session()과 동일한 시그니처의 콜러블 (contextmanager 반환)
SessionFactory = Callable[..., Any]


def _get_sheets() -> SpreadsheetGateway:
    return DefaultSpreadsheetGateway()


def recover_stale_sync_records(
    *,
    session_factory: SessionFactory | None = None,
) -> tuple[int, int]:
    """앱 시작 시 중단된 동기화 레코드 복구.

    이전 실행에서 in_progress 상태로 남은 레코드를 pending으로 되돌림.
    단일 인스턴스 환경에서 앱 재시작 시 안전하게 재처리 가능하도록 함.

    Returns:
        (복구된 정산 수, 복구된 로그 수)
    """
    _session = session_factory or get_session

    with _session() as session:
        settlements = SettlementRepository(session).recover_stale_records()
        logs = IssueLogRepository(session).recover_stale_records()

    if settlements or logs:
        logger.info("recovered_stale_records", settlements=settlements, logs=logs)

    return settlements, logs


def sync_to_sheets(
    row: SettlementRow,
    log_id: int,
    *,
    sheets: SpreadsheetGateway | None = None,
) -> bool:
    """정산 데이터를 Google Sheets로 동기화.

    정산 시트 (upsert) + 정산이슈로그 시트 (append) 모두 저장.
    예외 발생 시 실패로 처리.
    """
    _sheets = sheets or _get_sheets()

    try:
        _sheets.save_settlement_row(row)
        _sheets.append_issue_log_row(row, str(log_id))
        return True

    except Exception as e:
        logger.error("sheets_sync_failed", booking_key=row.booking_key, error=str(e))
        raise


def sync_pending_records(
    *,
    sheets: SpreadsheetGateway | None = None,
    session_factory: SessionFactory | None = None,
) -> tuple[int, int]:
    """미동기화 레코드 일괄 동기화 (배치 작업용).

    처리 흐름:
    1. claim_unsynced()로 조회 + in_progress 상태 변경 (같은 트랜잭션)
    2. 외부 API(Sheets) 호출은 트랜잭션 밖에서
    3. 성공/실패 시 DB 업데이트는 별도 트랜잭션에서

    Returns:
        (동기화된 정산 수, 동기화된 로그 수)
    """
    _sheets = sheets or _get_sheets()
    _session = session_factory or get_session

    synced_settlements = 0
    synced_logs = 0

    with _session() as session:
        settlements = SettlementRepository(session).claim_unsynced(limit=100)
        logs = IssueLogRepository(session).claim_unsynced(limit=100)

    for settlement in settlements:
        try:
            row = _entity_to_row(settlement, include_updated_at=True)
            _sheets.save_settlement_row(row)
            with _session() as session:
                SettlementRepository(session).mark_synced(settlement.id)
            synced_settlements += 1
        except Exception as e:
            logger.warning(
                "retry_sync_failed",
                record_type="settlement",
                booking_key=settlement.booking_key,
                error=str(e),
            )
            with _session() as session:
                SettlementRepository(session).mark_sync_failed(settlement.id, str(e))

    for log in logs:
        try:
            row = _entity_to_row(log, include_updated_at=False)
            _sheets.append_issue_log_row(row, str(log.id))
            with _session() as session:
                IssueLogRepository(session).mark_synced(log.id)
            synced_logs += 1
        except Exception as e:
            logger.warning(
                "retry_sync_failed",
                record_type="issue_log",
                booking_key=log.booking_key,
                error=str(e),
            )
            with _session() as session:
                IssueLogRepository(session).mark_sync_failed(log.id, str(e))

    if synced_settlements or synced_logs:
        logger.info(
            "sync_completed",
            settlements=synced_settlements,
            logs=synced_logs,
        )

    return synced_settlements, synced_logs


@runtime_checkable
class RowConvertible(Protocol):
    """SettlementRow로 변환 가능한 엔티티 프로토콜."""

    settlement_day: str
    user_name: str
    customer_name: str
    booking_key: str
    company_name: str
    company_sub_name: str
    settlement_cost: int | None
    carmore_cost: int | None
    user_refund_cost: int | None
    issue_type: str
    sales_channel: str
    description: str
    status: str
    approver_name: str
    thread_url: str
    reviewer_name: str
    rejection_reason: str
    created_at: datetime


def _entity_to_row(
    entity: RowConvertible, *, include_updated_at: bool = True
) -> SettlementRow:
    updated_at = ""
    if include_updated_at and hasattr(entity, "updated_at"):
        updated_at = entity.updated_at.strftime(DateFormat.DATETIME)

    return SettlementRow(
        settlement_day=entity.settlement_day,
        user_name=entity.user_name,
        customer_name=entity.customer_name,
        booking_key=entity.booking_key,
        company_name=entity.company_name,
        company_sub_name=entity.company_sub_name,
        settlement_cost=format_cost(entity.settlement_cost),
        carmore_cost=format_cost(entity.carmore_cost),
        user_refund_cost=format_cost(entity.user_refund_cost),
        issue_type=entity.issue_type,
        sales_channel=entity.sales_channel,
        description=entity.description,
        status=entity.status,
        approver_name=entity.approver_name,
        thread_url=entity.thread_url,
        created_at=entity.created_at.strftime(DateFormat.DATETIME),
        updated_at=updated_at,
        reviewer_name=entity.reviewer_name,
        rejection_reason=entity.rejection_reason,
        settlement_completed=(
            "TRUE" if getattr(entity, "settlement_completed", False) else "FALSE"
        ),
    )


class SyncError(Exception):
    pass
