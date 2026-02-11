from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core import get_logger
from app.exceptions import AlreadyProcessedError, DatabaseError
from app.infrastructure.database import SettlementRepository
from app.models import SettlementData, SettlementRow, SettlementStatus

if TYPE_CHECKING:
    from app.infrastructure.database import SessionFactory
    from app.services.sync_processor import SyncProcessor

logger = get_logger(__name__)


class SettlementWriter:
    def __init__(
        self,
        get_session: SessionFactory,
        sync_processor: SyncProcessor,
    ) -> None:
        self._get_session = get_session
        self._sync_processor = sync_processor

    def save(
        self,
        data: SettlementData,
        status: SettlementStatus,
        approver_name: str,
        thread_url: str,
        rejection_reason: str = "",
    ) -> None:
        row = SettlementRow.from_settlement_data(
            data=data,
            status=status,
            approver_name=approver_name,
            thread_url=thread_url,
            rejection_reason=rejection_reason,
        )

        if rejection_reason:
            logger.info("rejection_saved", rejection_reason=rejection_reason)

        try:
            self._persist(row, status)
        except AlreadyProcessedError:
            raise
        except IntegrityError as e:
            logger.exception(
                "settlement_integrity_error",
                booking_key=row.booking_key,
            )
            raise AlreadyProcessedError(
                message=(f"Settlement {row.booking_key} constraint violation"),
                details={"booking_key": row.booking_key},
            ) from e
        except SQLAlchemyError as e:
            logger.exception(
                "settlement_database_error",
                booking_key=row.booking_key,
            )
            raise DatabaseError(
                message=f"Failed to save settlement: {e}",
                details={"booking_key": row.booking_key},
            ) from e

    def _persist(self, row: SettlementRow, status: SettlementStatus) -> None:
        with self._get_session() as session:
            repo = SettlementRepository(session)
            self._validate_not_already_processed(repo, row.booking_key, status)

            settlement = repo.save(row)
            log = repo.add_log(row, settlement_id=settlement.id)
            is_update = settlement.sheets_synced_at is not None

            sync = self._sync_processor
            session.after_commit(
                lambda: sync.after_commit(
                    settlement.id, log.id, row, is_update=is_update
                )
            )

    @staticmethod
    def _validate_not_already_processed(
        repo: SettlementRepository,
        booking_key: str,
        status: SettlementStatus,
    ) -> None:
        if status not in (
            SettlementStatus.APPROVED,
            SettlementStatus.REJECTED,
        ):
            return

        existing = repo.get_active_by_booking_key(booking_key)
        if existing and existing.status != SettlementStatus.REQUESTED.value:
            raise AlreadyProcessedError(
                message=(
                    f"Settlement {booking_key} already processed: {existing.status}"
                ),
                details={
                    "booking_key": booking_key,
                    "current_status": existing.status,
                },
            )
