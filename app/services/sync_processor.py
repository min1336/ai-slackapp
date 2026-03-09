from __future__ import annotations

from typing import TYPE_CHECKING

from gspread.exceptions import APIError
from sqlalchemy.exc import SQLAlchemyError

from app.core import get_logger
from app.exceptions import SpreadsheetError
from app.infrastructure.database import (
    IssueLogRepository,
    SettlementRepository,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.infrastructure.database import SessionFactory
    from app.infrastructure.database.models import IssueLog, Settlement
    from app.infrastructure.protocols import SpreadsheetGateway
    from app.models import SettlementRow

logger = get_logger(__name__)


class SyncProcessor:
    def __init__(
        self,
        get_session: SessionFactory,
        sheets: SpreadsheetGateway,
        *,
        on_sync_failed: Callable[[str, str], None] | None = None,
    ) -> None:
        self._get_session = get_session
        self._sheets = sheets
        self._on_sync_failed = on_sync_failed

    # ── after_commit 즉시 동기화 ──

    def mark_synced(self, settlement_id: int, log_id: int) -> None:
        with self._get_session() as session:
            SettlementRepository(session).mark_synced(settlement_id)
            IssueLogRepository(session).mark_synced(log_id)

    def mark_sync_failed(self, settlement_id: int, log_id: int, error: str) -> None:
        with self._get_session() as session:
            SettlementRepository(session).mark_sync_failed(settlement_id, error)
            IssueLogRepository(session).mark_sync_failed(log_id, error)

    def mark_sync_failed_safe(
        self, settlement_id: int, log_id: int, error: str
    ) -> None:
        try:
            self.mark_sync_failed(settlement_id, log_id, error)
        except SQLAlchemyError as e:
            logger.error(
                "mark_sync_failed_error",
                settlement_id=settlement_id,
                log_id=log_id,
                error=str(e),
            )

    def _mark_settlement_synced_safe(self, settlement_id: int) -> None:
        try:
            self.mark_settlement_synced(settlement_id)
        except SQLAlchemyError as e:
            logger.error(
                "mark_settlement_synced_error",
                settlement_id=settlement_id,
                error=str(e),
            )

    def _mark_log_failed_safe(self, log_id: int, error: str) -> None:
        try:
            self.mark_log_failed(log_id, error)
        except SQLAlchemyError as e:
            logger.error(
                "mark_log_failed_error",
                log_id=log_id,
                error=str(e),
            )

    def _notify_sync_failed(self, booking_key: str, error: str) -> None:
        if not self._on_sync_failed:
            return
        try:
            self._on_sync_failed(booking_key, error)
        except Exception:  # 외부 콜백 — 실패해도 동기화 로직에 영향 없음
            logger.warning("sync_failed_notification_error", booking_key=booking_key)

    def after_commit(
        self,
        settlement_id: int,
        log_id: int,
        row: SettlementRow,
        *,
        is_update: bool = False,
    ) -> None:
        settlement_ok = False
        try:
            self._sheets.save_settlement_row(row, is_update=is_update)
            settlement_ok = True
            self._sheets.append_issue_log_row(row, str(log_id))
            self.mark_synced(settlement_id, log_id)
            logger.info("sheets_sync_completed", booking_key=row.booking_key)
        except (SpreadsheetError, APIError) as e:
            logger.warning(
                "sheets_sync_failed",
                booking_key=row.booking_key,
                error=str(e),
            )
            if settlement_ok:
                self._mark_settlement_synced_safe(settlement_id)
                self._mark_log_failed_safe(log_id, str(e))
            else:
                self.mark_sync_failed_safe(settlement_id, log_id, str(e))
            self._notify_sync_failed(row.booking_key, str(e))
        except SQLAlchemyError as e:
            logger.exception(
                "sheets_sync_unexpected_error",
                booking_key=row.booking_key,
            )
            self.mark_sync_failed_safe(settlement_id, log_id, f"Unexpected: {e}")
            self._notify_sync_failed(row.booking_key, str(e))

    # ── 배치 동기화용 (SyncService에서 위임) ──

    def claim_unsynced(
        self, limit: int = 100
    ) -> tuple[list[Settlement], list[IssueLog]]:
        """미동기화 레코드 claim + 반환."""
        with self._get_session() as session:
            settlements = SettlementRepository(session).claim_unsynced(limit=limit)
            logs = IssueLogRepository(session).claim_unsynced(limit=limit)
            return settlements, logs

    def recover_stale_records(self) -> tuple[int, int]:
        """in_progress 상태의 레코드를 pending으로 복구."""
        with self._get_session() as session:
            settlements = SettlementRepository(session).recover_stale_records()
            logs = IssueLogRepository(session).recover_stale_records()
            return settlements, logs

    def mark_settlement_synced(self, settlement_id: int) -> None:
        with self._get_session() as session:
            SettlementRepository(session).mark_synced(settlement_id)

    def mark_settlement_failed(self, settlement_id: int, error: str) -> None:
        with self._get_session() as session:
            SettlementRepository(session).mark_sync_failed(settlement_id, error)

    def mark_log_synced(self, log_id: int) -> None:
        with self._get_session() as session:
            IssueLogRepository(session).mark_synced(log_id)

    def mark_log_failed(self, log_id: int, error: str) -> None:
        with self._get_session() as session:
            IssueLogRepository(session).mark_sync_failed(log_id, error)

    def mark_settlements_completed(self, completed_keys: set[str]) -> list[str]:
        if not completed_keys:
            return []

        with self._get_session() as session:
            repo = SettlementRepository(session)
            return repo.mark_completed_by_booking_keys(completed_keys)
