from __future__ import annotations

from typing import TYPE_CHECKING

from gspread.exceptions import APIError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import get_database_settings
from app.core import get_logger
from app.exceptions import AlreadyProcessedError, DatabaseError, SpreadsheetError
from app.infrastructure.database import (
    IssueLogRepository,
    SettlementRepository,
    get_session,
    transactional,
)
from app.models import SettlementData, SettlementRow, SettlementStatus

if TYPE_CHECKING:
    from app.infrastructure.protocols import SpreadsheetGateway
    from app.services.sync_service import SessionFactory

logger = get_logger(__name__)


@transactional
def _mark_synced(session, settlement_id: int, log_id: int) -> None:
    SettlementRepository(session).mark_synced(settlement_id)
    IssueLogRepository(session).mark_synced(log_id)


@transactional
def _mark_sync_failed(session, settlement_id: int, log_id: int, error: str) -> None:
    SettlementRepository(session).mark_sync_failed(settlement_id, error)
    IssueLogRepository(session).mark_sync_failed(log_id, error)


def _mark_sync_failed_safe(settlement_id: int, log_id: int, error: str) -> None:
    """Best-effort DB 업데이트 - 절대 예외를 발생시키지 않음.

    Background 동기화 실패 시 DB 상태를 업데이트하려 시도하지만,
    실패해도 background worker가 재시도하므로 예외를 발생시키지 않음.
    """
    try:
        _mark_sync_failed(settlement_id, log_id, error)
    except Exception as e:
        # 최후의 안전망 - 로그만 하고 절대 실패하지 않음
        logger.error(
            "mark_sync_failed_error",
            settlement_id=settlement_id,
            log_id=log_id,
            error=str(e),
        )


def _sync_after_commit(
    settlement_id: int,
    log_id: int,
    row: SettlementRow,
    *,
    is_update: bool = False,
) -> None:
    from app.services.sync_service import sync_to_sheets

    try:
        sync_to_sheets(row, log_id, is_update=is_update)
        _mark_synced(settlement_id, log_id)
        logger.info("sheets_sync_completed", booking_key=row.booking_key)

    except (SpreadsheetError, APIError) as e:
        # Sheets/API 에러는 예상됨 - 로그만 하고 재시도 마킹
        logger.warning("sheets_sync_failed", booking_key=row.booking_key, error=str(e))
        _mark_sync_failed_safe(settlement_id, log_id, str(e))
    except SQLAlchemyError as e:
        # DB 에러 (mark_synced 실패 등) - 예상 외이므로 traceback 포함
        logger.exception("sheets_sync_unexpected_error", booking_key=row.booking_key)
        _mark_sync_failed_safe(settlement_id, log_id, f"Unexpected: {e}")


# ── Lazy Sync: Sheets 정산완료 → DB 반영 ──────────────────────────
#
# 설계 배경:
#   DB가 실질적 SSOT이지만, Sheets가 운영팀 UI 역할을 한다.
#   운영팀이 Sheets에서 "정산완료"를 TRUE로 바꾸면 DB에는 반영되지 않는다.
#   이 함수는 Sheets의 정산완료 상태를 DB에 반영하는 역할이다.
#
# 안전 가드:
#   sheets_synced=True인 레코드만 Sheets 조회 대상.
#   sheets_synced=False이면 DB→Sheets 동기화가 아직 안 됐으므로
#   Sheets를 조회해봐야 stale 데이터이다.
#
# 활성화 방법:
#   save_settlement()에서 repo.save() 호출 전에
#   _lazy_sync_settlement_completed()를 호출한다.
#   이렇게 하면 upsert 시 settlement_completed=True인 기존 행을
#   건너뛰고 새 행이 INSERT된다.
#
# 대안 — Batch Reverse Sync:
#   DB 리포팅이 필요해지면, 주기적으로 Sheets 전체를 스캔하여
#   정산완료 상태를 일괄 반영하는 별도 배치 구현을 검토한다.
# ─────────────────────────────────────────────────────────────────


def _lazy_sync_settlement_completed(
    booking_key: str,
    repo: SettlementRepository,
    sheets: SpreadsheetGateway,
) -> bool:
    """Sheets에서 정산완료 여부를 확인하고 DB에 반영한다.

    Returns:
        True면 해당 booking_key가 Sheets에서 정산완료 처리됨
        (= DB에도 settlement_completed=True로 갱신됨).
        False면 미완료이거나 조회 대상이 아님.
    """
    existing = repo.get_active_by_booking_key(booking_key)
    if existing is None:
        return False

    # 안전 가드: DB→Sheets 동기화가 완료된 건만 역방향 조회
    if not existing.sheets_synced:
        return False

    # Sheets에서 활성 행 존재 여부 확인
    # find_row_by_booking_key는 정산완료=FALSE인 행만 반환하므로,
    # 반환값 None = 활성 행 없음 = Sheets에서 정산완료 처리됨
    row_number = sheets.find_row_by_booking_key(booking_key)
    if row_number is not None:
        return False

    # Sheets에서 정산완료 처리됨 → DB에도 반영
    existing.settlement_completed = True
    logger.info(
        "lazy_sync_settlement_completed",
        booking_key=booking_key,
    )
    return True


def save_settlement(
    data: SettlementData,
    status: SettlementStatus,
    approver_name: str,
    thread_url: str,
    rejection_reason: str = "",
    *,
    session_factory: SessionFactory | None = None,
) -> None:
    if not get_database_settings().is_configured:
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

    try:
        with _session() as session:
            repo = SettlementRepository(session)

            if status in (SettlementStatus.APPROVED, SettlementStatus.REJECTED):
                existing = repo.get_active_by_booking_key(row.booking_key)
                if existing and existing.status != SettlementStatus.REQUESTED.value:
                    raise AlreadyProcessedError(
                        message=(
                            f"Settlement {row.booking_key}"
                            f" already processed: {existing.status}"
                        ),
                        details={
                            "booking_key": row.booking_key,
                            "current_status": existing.status,
                        },
                    )

            settlement = repo.save(row)
            log = repo.add_log(row, settlement_id=settlement.id)
            settlement_id = settlement.id
            log_id = log.id
            is_update = settlement.sheets_synced_at is not None

            # 모든 상태(요청/승인/반려)에서 Sheets 동기화 실행
            session.after_commit(
                lambda: _sync_after_commit(
                    settlement_id, log_id, row, is_update=is_update
                )
            )

    except AlreadyProcessedError:
        # 이미 도메인 예외이므로 그대로 재발생
        raise
    except IntegrityError as e:
        # DB 제약 조건 위반 → 비즈니스 에러로 변환
        logger.exception("settlement_integrity_error", booking_key=row.booking_key)
        raise AlreadyProcessedError(
            message=f"Settlement {row.booking_key} constraint violation",
            details={"booking_key": row.booking_key},
        ) from e
    except SQLAlchemyError as e:
        # 일반 DB 에러 → DatabaseError로 변환
        logger.exception("settlement_database_error", booking_key=row.booking_key)
        raise DatabaseError(
            message=f"Failed to save settlement: {e}",
            details={"booking_key": row.booking_key},
        ) from e
