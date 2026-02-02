from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.database.models import ApprovalLog, Settlement

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import SettlementRow


def _parse_cost(value: str) -> int | None:
    """문자열 금액을 정수로 변환. 빈 문자열이면 None 반환."""
    if not value or not value.strip():
        return None
    # 콤마, 원, 공백 제거
    cleaned = value.replace(",", "").replace("원", "").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


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
        """정산 저장 (upsert by booking_key)."""
        stmt = insert(Settlement).values(
            booking_key=row.booking_key,
            settlement_day=row.settlement_day,
            user_name=row.user_name,
            customer_name=row.customer_name,
            company_name=row.company_name,
            company_sub_name=row.company_sub_name,
            settlement_cost=_parse_cost(row.settlement_cost),
            carmore_cost=_parse_cost(row.carmore_cost),
            user_refund_cost=_parse_cost(row.user_refund_cost),
            issue_type=row.issue_type,
            sales_channel=row.sales_channel,
            description=row.description,
            status=row.status,
            approver_name=row.approver_name,
            thread_url=row.thread_url,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["booking_key"],
            set_={
                "settlement_day": row.settlement_day,
                "user_name": row.user_name,
                "customer_name": row.customer_name,
                "company_name": row.company_name,
                "company_sub_name": row.company_sub_name,
                "settlement_cost": _parse_cost(row.settlement_cost),
                "carmore_cost": _parse_cost(row.carmore_cost),
                "user_refund_cost": _parse_cost(row.user_refund_cost),
                "issue_type": row.issue_type,
                "sales_channel": row.sales_channel,
                "description": row.description,
                "status": row.status,
                "approver_name": row.approver_name,
                "thread_url": row.thread_url,
                "updated_at": datetime.now(),
                "sheets_synced": False,
            },
        ).returning(Settlement)

        result = self.session.execute(stmt)
        return result.scalar_one()

    def add_log(
        self, row: SettlementRow, settlement_id: int | None = None
    ) -> ApprovalLog:
        """승인 로그 추가."""
        log = ApprovalLog(
            settlement_id=settlement_id,
            booking_key=row.booking_key,
            settlement_day=row.settlement_day,
            user_name=row.user_name,
            customer_name=row.customer_name,
            company_name=row.company_name,
            company_sub_name=row.company_sub_name,
            settlement_cost=_parse_cost(row.settlement_cost),
            carmore_cost=_parse_cost(row.carmore_cost),
            user_refund_cost=_parse_cost(row.user_refund_cost),
            issue_type=row.issue_type,
            sales_channel=row.sales_channel,
            description=row.description,
            status=row.status,
            approver_name=row.approver_name,
            thread_url=row.thread_url,
        )
        self.session.add(log)
        self.session.flush()
        return log

    def get(self, settlement_id: int) -> Settlement | None:
        """ID로 정산 조회."""
        return self.session.get(Settlement, settlement_id)

    def get_by_booking_key(self, booking_key: str) -> Settlement | None:
        """예약번호로 정산 조회."""
        stmt = select(Settlement).where(Settlement.booking_key == booking_key)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def list_unsynced(self, limit: int = 100) -> list[Settlement]:
        """동기화 안 된 정산 목록 조회."""
        stmt = (
            select(Settlement)
            .where(Settlement.sheets_synced == False)  # noqa: E712
            .limit(limit)
        )
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def mark_synced(self, settlement_id: int) -> None:
        """동기화 완료 표시."""
        settlement = self.get(settlement_id)
        if settlement:
            settlement.sheets_synced = True
            settlement.sheets_synced_at = datetime.now()
            settlement.sheets_sync_error = None

    def mark_sync_failed(self, settlement_id: int, error: str) -> None:
        """동기화 실패 표시."""
        settlement = self.get(settlement_id)
        if settlement:
            settlement.sheets_sync_error = error


class ApprovalLogRepository:
    """승인 로그 저장소"""

    def __init__(self, session: Session):
        self.session = session

    def get(self, log_id: int) -> ApprovalLog | None:
        """ID로 로그 조회."""
        return self.session.get(ApprovalLog, log_id)

    def list_unsynced(self, limit: int = 100) -> list[ApprovalLog]:
        """동기화 안 된 로그 목록 조회."""
        stmt = (
            select(ApprovalLog)
            .where(ApprovalLog.sheets_synced == False)  # noqa: E712
            .limit(limit)
        )
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def mark_synced(self, log_id: int) -> None:
        """동기화 완료 표시."""
        log = self.get(log_id)
        if log:
            log.sheets_synced = True
            log.sheets_synced_at = datetime.now()
            log.sheets_sync_error = None

    def mark_sync_failed(self, log_id: int, error: str) -> None:
        """동기화 실패 표시."""
        log = self.get(log_id)
        if log:
            log.sheets_sync_error = error
