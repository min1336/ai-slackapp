"""sync_service 동기화 재시도 테스트"""

from __future__ import annotations

import pytest

from app.exceptions import SpreadsheetError
from app.infrastructure.database.repository import (
    IssueLogRepository,
    SettlementRepository,
)
from app.models import SettlementRow, SettlementStatus
from app.services.sync_service import _entity_to_row, sync_pending_records
from tests.fakes.fake_database import FakeDatabase
from tests.fakes.fake_spreadsheet import FakeSpreadsheet


@pytest.fixture
def fake_db():
    return FakeDatabase()


@pytest.fixture
def fake_sheets():
    return FakeSpreadsheet()


def _create_records(fake_db: FakeDatabase, row: SettlementRow) -> tuple[int, int]:
    with fake_db.get_session() as session:
        repo = SettlementRepository(session)
        settlement = repo.save(row)
        log = repo.add_log(row, settlement_id=settlement.id)
        return settlement.id, log.id


def test_sync_pending_records_success(fake_db, fake_sheets, sample_settlement_data):
    row = SettlementRow.from_settlement_data(
        data=sample_settlement_data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="http://example.com/thread",
    )
    settlement_id, log_id = _create_records(fake_db, row)

    synced_settlements, synced_logs = sync_pending_records(
        sheets=fake_sheets,
        session_factory=fake_db.get_session,
        record_delay=0,
    )

    assert synced_settlements == 1
    assert synced_logs == 1
    with fake_db.get_session() as session:
        settlement = SettlementRepository(session).get(settlement_id)
        log = IssueLogRepository(session).get(log_id)
        assert settlement is not None
        assert log is not None
        assert settlement.sheets_synced is True
        assert settlement.sync_status == "completed"
        assert log.sheets_synced is True
        assert log.sync_status == "completed"


def test_sync_pending_records_all_failure(fake_db, fake_sheets, sample_settlement_data):
    """모든 시트 동기화가 실패하면 모든 레코드가 pending 상태로 유지된다."""
    fake_sheets.should_fail = True

    row = SettlementRow.from_settlement_data(
        data=sample_settlement_data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="http://example.com/thread",
    )
    settlement_id, log_id = _create_records(fake_db, row)

    synced_settlements, synced_logs = sync_pending_records(
        sheets=fake_sheets,
        session_factory=fake_db.get_session,
        record_delay=0,
    )

    assert synced_settlements == 0
    assert synced_logs == 0
    with fake_db.get_session() as session:
        settlement = SettlementRepository(session).get(settlement_id)
        log = IssueLogRepository(session).get(log_id)
        assert settlement is not None
        assert log is not None
        assert settlement.sheets_synced is False
        assert settlement.sync_status == "pending"
        assert settlement.sheets_sync_error
        assert log.sheets_synced is False
        assert log.sync_status == "pending"


def test_sync_pending_records_settlement_only_failure(
    fake_db, fake_sheets, sample_settlement_data
):
    """정산 시트 실패 시에도 승인 로그는 독립적으로 동기화된다."""

    class SettlementOnlyFailSheet(FakeSpreadsheet):
        """save_settlement_row만 실패하는 Fake."""

        def save_settlement_row(self, row, sheet_name=None, *, is_update=False):
            raise SpreadsheetError(
                message="Settlement sheet failure",
                details={"booking_key": row.booking_key},
            )

    failing_sheets = SettlementOnlyFailSheet()

    row = SettlementRow.from_settlement_data(
        data=sample_settlement_data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="http://example.com/thread",
    )
    settlement_id, log_id = _create_records(fake_db, row)

    synced_settlements, synced_logs = sync_pending_records(
        sheets=failing_sheets,
        session_factory=fake_db.get_session,
        record_delay=0,
    )

    # 정산은 실패, 로그는 성공
    assert synced_settlements == 0
    assert synced_logs == 1
    with fake_db.get_session() as session:
        settlement = SettlementRepository(session).get(settlement_id)
        log = IssueLogRepository(session).get(log_id)
        assert settlement.sheets_synced is False
        assert settlement.sync_status == "pending"
        assert settlement.sheets_sync_error
        assert log.sheets_synced is True
        assert log.sync_status == "completed"


def test_entity_to_row_settlement_completed_변환(fake_db, sample_settlement_data):
    """_entity_to_row가 settlement_completed를 올바르게 변환하는지 확인."""
    row = SettlementRow.from_settlement_data(
        data=sample_settlement_data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="http://example.com/thread",
    )

    with fake_db.get_session() as session:
        repo = SettlementRepository(session)
        settlement = repo.save(row)

        # 기본값: settlement_completed=False → "FALSE"
        converted = _entity_to_row(settlement)
        assert converted.settlement_completed == "FALSE"

        # settlement_completed=True → "TRUE"
        settlement.settlement_completed = True
        converted = _entity_to_row(settlement)
        assert converted.settlement_completed == "TRUE"
