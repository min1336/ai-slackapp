from __future__ import annotations

from typing import TYPE_CHECKING

from app.core import get_logger
from app.infrastructure.database import SettlementRepository

if TYPE_CHECKING:
    from app.infrastructure.database import SessionFactory
    from app.infrastructure.protocols import SpreadsheetGateway
    from app.services.thread_reference_store import ThreadReferenceStore

logger = get_logger(__name__)


class TransferLifecycleService:
    """이관 시 기존 정산 데이터의 생명주기를 관리한다.

    B0001 등록 시 A0001을 이관 처리하고,
    B0001 반려 시 A0001을 복구한다.
    """

    def __init__(
        self,
        get_session: SessionFactory,
        thread_ref_store: ThreadReferenceStore,
        sheets: SpreadsheetGateway,
    ) -> None:
        self._get_session = get_session
        self._thread_ref_store = thread_ref_store
        self._sheets = sheets

    def mark_transferred(self, new_booking_key: str) -> None:
        """이관 건이면 원본 정산을 이관 처리한다."""
        root_booking_key = self._thread_ref_store.get_root_booking_key(new_booking_key)
        if not root_booking_key or root_booking_key == new_booking_key:
            return

        with self._get_session() as session:
            repo = SettlementRepository(session)
            settlement = repo.get_active_by_booking_key(root_booking_key)
            if not settlement:
                return

            original_note = settlement.note or ""
            repo.mark_transferred(root_booking_key, new_booking_key)

        new_note = f"{original_note} [이관→{new_booking_key}]".strip()
        self._sheets.update_settlement_note(root_booking_key, new_note)

        logger.info(
            "transfer_marked",
            root_booking_key=root_booking_key,
            new_booking_key=new_booking_key,
        )

    def revert_transfer(self, rejected_booking_key: str) -> None:
        """반려된 이관 건의 원본 정산을 복구한다."""
        root_booking_key = self._thread_ref_store.get_root_booking_key(
            rejected_booking_key
        )
        if not root_booking_key or root_booking_key == rejected_booking_key:
            return

        with self._get_session() as session:
            repo = SettlementRepository(session)
            original_note = repo.clear_transferred(root_booking_key)

        if original_note is None:
            return

        self._sheets.update_settlement_note(root_booking_key, original_note)

        logger.info(
            "transfer_reverted",
            root_booking_key=root_booking_key,
            rejected_booking_key=rejected_booking_key,
        )
