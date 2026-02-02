"""sync_service 동기화 재시도 테스트"""

from __future__ import annotations

import pytest

from app.infrastructure.database.repository import (
    ApprovalLogRepository,
    SettlementRepository,
)
from app.models import SettlementRow, SettlementStatus
from app.services.sync_service import sync_pending_records
from tests.fakes.fake_database import FakeDatabase


@pytest.fixture
def fake_db():
    return FakeDatabase()


def _create_records(fake_db: FakeDatabase, row: SettlementRow) -> tuple[int, int]:
    with fake_db.get_session() as session:
        repo = SettlementRepository(session)
        settlement = repo.save(row)
        log = repo.add_log(row, settlement_id=settlement.id)
        return settlement.id, log.id


def test_sync_pending_records_success(monkeypatch, fake_db, sample_settlement_data):
    monkeypatch.setattr("app.services.sync_service.get_session", fake_db.get_session)
    monkeypatch.setattr(
        "app.services.sync_service.sheets_save_settlement",
        lambda row: None,  # 성공 시 예외 없음
    )
    monkeypatch.setattr(
        "app.services.sync_service.sheets_append_log",
        lambda row, sync_key: None,  # 성공 시 예외 없음
    )

    row = SettlementRow.from_settlement_data(
        data=sample_settlement_data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="http://example.com/thread",
    )
    settlement_id, log_id = _create_records(fake_db, row)

    synced_settlements, synced_logs = sync_pending_records()

    assert synced_settlements == 1
    assert synced_logs == 1
    with fake_db.get_session() as session:
        settlement = SettlementRepository(session).get(settlement_id)
        log = ApprovalLogRepository(session).get(log_id)
        assert settlement is not None
        assert log is not None
        assert settlement.sheets_synced is True
        assert settlement.sync_status == "completed"
        assert log.sheets_synced is True
        assert log.sync_status == "completed"


def _raise_error(row):
    raise Exception("Sheets API error")


def test_sync_pending_records_settlement_failure(
    monkeypatch, fake_db, sample_settlement_data
):
    monkeypatch.setattr("app.services.sync_service.get_session", fake_db.get_session)
    monkeypatch.setattr(
        "app.services.sync_service.sheets_save_settlement",
        _raise_error,  # 실패 시 예외 발생
    )
    monkeypatch.setattr(
        "app.services.sync_service.sheets_append_log",
        lambda row, sync_key: None,  # 성공
    )

    row = SettlementRow.from_settlement_data(
        data=sample_settlement_data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="http://example.com/thread",
    )
    settlement_id, log_id = _create_records(fake_db, row)

    synced_settlements, synced_logs = sync_pending_records()

    assert synced_settlements == 0
    assert synced_logs == 1
    with fake_db.get_session() as session:
        settlement = SettlementRepository(session).get(settlement_id)
        log = ApprovalLogRepository(session).get(log_id)
        assert settlement is not None
        assert log is not None
        assert settlement.sheets_synced is False
        assert settlement.sync_status == "pending"  # 실패 시 재시도 가능하도록 pending
        assert settlement.sheets_sync_error
        assert log.sheets_synced is True
        assert log.sync_status == "completed"
