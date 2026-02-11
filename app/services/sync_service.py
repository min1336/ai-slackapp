from __future__ import annotations

import time
from typing import TYPE_CHECKING

from gspread.exceptions import APIError
from sqlalchemy.exc import SQLAlchemyError

from app.core import get_logger
from app.exceptions import SpreadsheetError
from app.models import SettlementRow

if TYPE_CHECKING:
    from app.infrastructure.protocols import SpreadsheetGateway
    from app.services.sync_processor import SyncProcessor

logger = get_logger(__name__)


class SyncService:
    def __init__(
        self,
        processor: SyncProcessor,
        sheets: SpreadsheetGateway,
    ) -> None:
        self._processor = processor
        self._sheets = sheets

    def recover_stale_sync_records(self) -> tuple[int, int]:
        settlements, logs = self._processor.recover_stale_records()

        if settlements or logs:
            logger.info(
                "recovered_stale_records",
                settlements=settlements,
                logs=logs,
            )

        return settlements, logs

    def sync_pending_records(
        self,
        *,
        record_delay: float = 2.0,
    ) -> tuple[int, int]:
        synced_settlements = 0
        synced_logs = 0

        settlements, logs = self._processor.claim_unsynced()

        for i, settlement in enumerate(settlements):
            if i > 0 and record_delay > 0:
                time.sleep(record_delay)
            try:
                row = SettlementRow.from_entity(settlement, include_updated_at=True)
                is_update = settlement.sheets_synced_at is not None
                self._sheets.save_settlement_row(row, is_update=is_update)
                self._processor.mark_settlement_synced(settlement.id)
                synced_settlements += 1
            except (SpreadsheetError, APIError, SQLAlchemyError) as e:
                logger.warning(
                    "retry_sync_failed",
                    record_type="settlement",
                    booking_key=settlement.booking_key,
                    error=str(e),
                )
                self._processor.mark_settlement_failed(settlement.id, str(e))

        for i, log in enumerate(logs):
            if i > 0 and record_delay > 0:
                time.sleep(record_delay)
            try:
                row = SettlementRow.from_entity(log, include_updated_at=False)
                self._sheets.append_issue_log_row(row, str(log.id))
                self._processor.mark_log_synced(log.id)
                synced_logs += 1
            except (SpreadsheetError, APIError, SQLAlchemyError) as e:
                logger.warning(
                    "retry_sync_failed",
                    record_type="issue_log",
                    booking_key=log.booking_key,
                    error=str(e),
                )
                self._processor.mark_log_failed(log.id, str(e))

        if synced_settlements or synced_logs:
            logger.info(
                "sync_completed",
                settlements=synced_settlements,
                logs=synced_logs,
            )

        return synced_settlements, synced_logs

    def lazy_sync_settlement_completed(
        self,
        booking_key: str,
    ) -> bool:
        """Sheets에서 삭제된(정산완료) 행을 DB에 반영한다.

        현재 미활성 상태 — 호출부가 없음.
        Sheets 정산완료 프로세스가 확정되면 listener 또는 스케줄러에서 호출 예정.
        """
        return self._processor.lazy_complete_settlement(booking_key)
