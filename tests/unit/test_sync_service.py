"""SyncService 동기화 재시도 테스트 (constructor DI)"""

from __future__ import annotations

import pytest

from app.exceptions import SpreadsheetError
from app.infrastructure.database.repository import (
    IssueLogRepository,
    SettlementRepository,
)
from app.models import SettlementRow, SettlementStatus
from app.services.sync_processor import SyncProcessor
from app.services.sync_service import SyncService
from tests.fakes.fake_spreadsheet import FakeSpreadsheet


@pytest.fixture
def fake_sheets():
    return FakeSpreadsheet()


@pytest.fixture
def sync_processor(fake_db, fake_sheets):
    return SyncProcessor(fake_db.get_session, fake_sheets)


@pytest.fixture
def sync_service(sync_processor, fake_sheets):
    return SyncService(sync_processor, fake_sheets)


def _create_records(fake_db, row: SettlementRow) -> tuple[int, int]:
    with fake_db.get_session() as session:
        repo = SettlementRepository(session)
        settlement = repo.save(row)
        log = repo.add_log(row, settlement_id=settlement.id)
        return settlement.id, log.id


def test_sync_pending_records_success(fake_db, sync_service, sample_settlement_data):
    row = SettlementRow.from_settlement_data(
        data=sample_settlement_data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="http://example.com/thread",
    )
    settlement_id, log_id = _create_records(fake_db, row)

    synced_settlements, synced_logs = sync_service.sync_pending_records(
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
    processor = SyncProcessor(fake_db.get_session, fake_sheets)
    svc = SyncService(processor, fake_sheets)

    row = SettlementRow.from_settlement_data(
        data=sample_settlement_data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="http://example.com/thread",
    )
    settlement_id, log_id = _create_records(fake_db, row)

    synced_settlements, synced_logs = svc.sync_pending_records(
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


def test_sync_pending_records_settlement_only_failure(fake_db, sample_settlement_data):
    """정산 시트 실패 시에도 승인 로그는 독립적으로 동기화된다."""

    class SettlementOnlyFailSheet(FakeSpreadsheet):
        """save_settlement_row만 실패하는 Fake."""

        def save_settlement_row(self, row, sheet_name=None, *, is_update=False):
            raise SpreadsheetError(
                message="Settlement sheet failure",
                details={"booking_key": row.booking_key},
            )

    failing_sheets = SettlementOnlyFailSheet()
    processor = SyncProcessor(fake_db.get_session, failing_sheets)
    svc = SyncService(processor, failing_sheets)

    row = SettlementRow.from_settlement_data(
        data=sample_settlement_data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="http://example.com/thread",
    )
    settlement_id, log_id = _create_records(fake_db, row)

    synced_settlements, synced_logs = svc.sync_pending_records(
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


# ── reverse_sync_settlement_completed ──────────


class TestReverseSyncSettlementCompleted:
    def test_정상_역동기화(
        self, fake_db, sync_service, fake_sheets, sample_settlement_data
    ):
        row = SettlementRow.from_settlement_data(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )
        s_id, _ = _create_records(fake_db, row)
        fake_sheets.completed_keys.add(row.booking_key)

        result = sync_service.reverse_sync_settlement_completed()

        assert result == 1
        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            assert s.settlement_completed is True

    def test_이미_완료된_건_재처리_안됨(
        self, fake_db, sync_service, fake_sheets, sample_settlement_data
    ):
        row = SettlementRow.from_settlement_data(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )
        s_id, _ = _create_records(fake_db, row)
        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            s.settlement_completed = True
        fake_sheets.completed_keys.add(row.booking_key)

        result = sync_service.reverse_sync_settlement_completed()

        assert result == 0

    def test_빈_시트_0_반환(self, sync_service):
        result = sync_service.reverse_sync_settlement_completed()

        assert result == 0

    def test_DB에_없는_booking_key_무시(self, sync_service, fake_sheets):
        fake_sheets.completed_keys.add("NONEXISTENT-KEY")

        result = sync_service.reverse_sync_settlement_completed()

        assert result == 0

    def test_Sheets_실패시_0_반환(self, sync_service, fake_sheets):
        fake_sheets.should_fail = True

        result = sync_service.reverse_sync_settlement_completed()

        assert result == 0

    def test_여러_건_일괄_처리(self, fake_db, sync_service, fake_sheets):
        from tests.factories import SettlementDataFactory

        keys = []
        for i in range(3):
            data = SettlementDataFactory.create(booking_key=f"REVERSE-{i}")
            row = SettlementRow.from_settlement_data(
                data=data,
                status=SettlementStatus.APPROVED,
                approver_name="승인자",
                thread_url="http://example.com/thread",
            )
            _create_records(fake_db, row)
            fake_sheets.completed_keys.add(row.booking_key)
            keys.append(row.booking_key)

        result = sync_service.reverse_sync_settlement_completed()

        assert result == 3
        with fake_db.get_session() as session:
            for key in keys:
                s = SettlementRepository(session).get_by_booking_key(key)
                assert s.settlement_completed is True


def test_from_entity_settlement_completed_변환(fake_db, sample_settlement_data):
    """SettlementRow.from_entity가 settlement_completed를 올바르게 변환하는지 확인."""
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
        converted = SettlementRow.from_entity(settlement)
        assert converted.settlement_completed == "FALSE"

        # settlement_completed=True → "TRUE"
        settlement.settlement_completed = True
        converted = SettlementRow.from_entity(settlement)
        assert converted.settlement_completed == "TRUE"
