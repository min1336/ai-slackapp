from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.infrastructure.database.models import IssueLog, Settlement, ThreadReference

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import SettlementRow
from app.models import TransferStatus


def _parse_cost(value: str) -> int | None:
    if not value:
        return None
    # 콤마, 원, 공백 제거
    cleaned = value.replace(",", "").replace("원", "").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


_COST_FIELDS = frozenset({"settlement_cost", "carmore_cost", "user_refund_cost"})

_SHARED_FIELDS: tuple[str, ...] = (
    "settlement_day",
    "user_name",
    "customer_name",
    "company_name",
    "company_sub_name",
    "settlement_cost",
    "carmore_cost",
    "user_refund_cost",
    "issue_type",
    "sales_channel",
    "description",
    "status",
    "transfer_status",
    "approver_name",
    "thread_url",
    "note",
    "reviewer_name",
    "rejection_reason",
)


def _row_to_model_dict(row: SettlementRow) -> dict[str, Any]:
    return {
        field: (
            _parse_cost(getattr(row, field))
            if field in _COST_FIELDS
            else getattr(row, field)
        )
        for field in _SHARED_FIELDS
    }


class SettlementRepository:
    """정산 데이터 저장소

    Python/SQLAlchemy 네이밍 컨벤션:
    - save(): upsert (insert or update)
    - add(): insert only
    - get(): 단일 조회
    - get_by_*(): 조건 조회
    - list_*(): 목록 조회
    - delete(): 삭제
    """

    def __init__(self, session: Session):
        self.session = session

    def save(self, row: SettlementRow) -> Settlement:
        existing = self.get_active_by_booking_key(row.booking_key)
        if existing:
            for field, value in _row_to_model_dict(row).items():
                setattr(existing, field, value)
            existing.updated_at = datetime.now()
            existing.sheets_synced = False
            self.session.flush()
            return existing

        settlement = Settlement(
            booking_key=row.booking_key,
            **_row_to_model_dict(row),
            settlement_completed=False,
        )
        self.session.add(settlement)
        self.session.flush()
        return settlement

    def add_log(
        self,
        row: SettlementRow,
        settlement_id: int | None = None,
    ) -> IssueLog:
        log = IssueLog(
            settlement_id=settlement_id,
            booking_key=row.booking_key,
            **_row_to_model_dict(row),
        )
        self.session.add(log)
        self.session.flush()
        return log

    def get(self, settlement_id: int) -> Settlement | None:
        return self.session.get(Settlement, settlement_id)

    def get_by_booking_key(self, booking_key: str) -> Settlement | None:
        stmt = select(Settlement).where(Settlement.booking_key == booking_key)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def get_active_by_booking_key(self, booking_key: str) -> Settlement | None:
        stmt = select(Settlement).where(
            Settlement.booking_key == booking_key,
            Settlement.settlement_completed == False,  # noqa: E712
        )
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def has_completed_settlement(self, booking_key: str) -> bool:
        stmt = (
            select(Settlement.id)
            .where(
                Settlement.booking_key == booking_key,
                Settlement.settlement_completed == True,  # noqa: E712
            )
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def mark_completed_by_booking_keys(self, booking_keys: set[str]) -> list[str]:
        if not booking_keys:
            return []

        stmt = select(Settlement).where(
            Settlement.booking_key.in_(booking_keys),
            Settlement.settlement_completed == False,  # noqa: E712
        )
        records = list(self.session.execute(stmt).scalars().all())

        completed: list[str] = []
        for record in records:
            record.settlement_completed = True
            completed.append(record.booking_key)

        return completed

    def mark_transferred(self, booking_key: str, transferred_to: str) -> bool:
        """활성 정산을 이관 처리한다. 성공 시 True."""
        settlement = self.get_active_by_booking_key(booking_key)
        if not settlement:
            return False
        settlement.transferred_to = transferred_to
        settlement.transfer_status = TransferStatus.TRANSFERRED.value
        return True

    def clear_transferred(self, booking_key: str) -> str | None:
        """이관 상태를 복구한다. 복구된 경우 원래 note 반환."""
        settlement = self.get_active_by_booking_key(booking_key)
        if not settlement or not settlement.transferred_to:
            return None
        settlement.transferred_to = None
        settlement.transfer_status = TransferStatus.REVERTED.value
        return settlement.note or ""

    def list_unsynced(self, limit: int = 100) -> list[Settlement]:
        """동기화 안 된 정산 목록 조회. (하위 호환용, claim_unsynced 사용 권장)"""
        stmt = (
            select(Settlement)
            .where(Settlement.sheets_synced == False)  # noqa: E712
            .limit(limit)
        )
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def claim_unsynced(self, limit: int = 100) -> list[Settlement]:
        """미동기화 레코드 조회 및 in_progress로 변경.

        조회와 상태 변경이 같은 트랜잭션에서 수행되어 중복 처리 방지.
        """
        stmt = (
            select(Settlement).where(Settlement.sync_status == "pending").limit(limit)
        )
        records = list(self.session.execute(stmt).scalars().all())

        for record in records:
            record.sync_status = "in_progress"

        return records

    def mark_synced(self, settlement_id: int) -> None:
        settlement = self.get(settlement_id)
        if settlement:
            settlement.sync_status = "completed"
            settlement.sheets_synced = True
            settlement.sheets_synced_at = datetime.now()
            settlement.sheets_sync_error = None

    def mark_sync_failed(self, settlement_id: int, error: str) -> None:
        """동기화 실패 표시. pending으로 되돌려 재시도 가능."""
        settlement = self.get(settlement_id)
        if settlement:
            settlement.sync_status = "pending"
            settlement.sheets_sync_error = error

    def recover_stale_records(self) -> int:
        """in_progress 상태의 레코드를 pending으로 복구.

        앱 시작 시 호출하여 이전 실행에서 중단된 레코드 복구.
        Returns:
            복구된 레코드 수
        """
        stmt = select(Settlement).where(Settlement.sync_status == "in_progress")
        records = list(self.session.execute(stmt).scalars().all())

        for record in records:
            record.sync_status = "pending"

        return len(records)


class IssueLogRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, log_id: int) -> IssueLog | None:
        return self.session.get(IssueLog, log_id)

    def list_unsynced(self, limit: int = 100) -> list[IssueLog]:
        """동기화 안 된 로그 목록 조회. (하위 호환용, claim_unsynced 사용 권장)"""
        stmt = (
            select(IssueLog)
            .where(IssueLog.sheets_synced == False)  # noqa: E712
            .limit(limit)
        )
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def claim_unsynced(self, limit: int = 100) -> list[IssueLog]:
        """미동기화 레코드 조회 및 in_progress로 변경.

        조회와 상태 변경이 같은 트랜잭션에서 수행되어 중복 처리 방지.
        """
        stmt = select(IssueLog).where(IssueLog.sync_status == "pending").limit(limit)
        records = list(self.session.execute(stmt).scalars().all())

        for record in records:
            record.sync_status = "in_progress"

        return records

    def mark_synced(self, log_id: int) -> None:
        log = self.get(log_id)
        if log:
            log.sync_status = "completed"
            log.sheets_synced = True
            log.sheets_synced_at = datetime.now()
            log.sheets_sync_error = None

    def mark_sync_failed(self, log_id: int, error: str) -> None:
        # pending으로 되돌려 재시도 가능
        log = self.get(log_id)
        if log:
            log.sync_status = "pending"
            log.sheets_sync_error = error

    def recover_stale_records(self) -> int:
        """in_progress 상태의 레코드를 pending으로 복구.

        앱 시작 시 호출하여 이전 실행에서 중단된 레코드 복구.
        Returns:
            복구된 레코드 수
        """
        stmt = select(IssueLog).where(IssueLog.sync_status == "in_progress")
        records = list(self.session.execute(stmt).scalars().all())

        for record in records:
            record.sync_status = "pending"

        return len(records)


class ThreadReferenceRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_booking_key(self, booking_key: str) -> ThreadReference | None:
        stmt = select(ThreadReference).where(
            ThreadReference.booking_key == booking_key,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_by_root_booking_key(self, root_booking_key: str) -> list[ThreadReference]:
        stmt = select(ThreadReference).where(
            ThreadReference.root_booking_key == root_booking_key
        )
        return list(self.session.execute(stmt).scalars().all())

    def save(
        self,
        booking_key: str,
        channel_id: str,
        thread_ts: str,
        root_booking_key: str | None = None,
    ) -> ThreadReference:
        existing = self.get_by_booking_key(booking_key)
        if existing:
            return existing

        ref = ThreadReference(
            booking_key=booking_key,
            channel_id=channel_id,
            thread_ts=thread_ts,
            root_booking_key=root_booking_key or booking_key,
        )
        self.session.add(ref)
        self.session.flush()
        return ref
