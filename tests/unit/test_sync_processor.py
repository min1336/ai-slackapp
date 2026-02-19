"""SyncProcessor 컴포넌트 테스트

에러 경로 + 배치 메서드 + mark_settlements_completed 커버.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.database.repository import (
    IssueLogRepository,
    SettlementRepository,
)
from app.models import SettlementRow, SettlementStatus
from app.services.sync_processor import SyncProcessor
from tests.fakes.fake_spreadsheet import FakeSpreadsheet


@pytest.fixture
def fake_sheets():
    return FakeSpreadsheet()


@pytest.fixture
def processor(fake_db, fake_sheets):
    return SyncProcessor(fake_db.get_session, fake_sheets)


def _make_row(sample_settlement_data) -> SettlementRow:
    return SettlementRow.from_settlement_data(
        data=sample_settlement_data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="http://example.com/thread",
    )


def _create_records(fake_db, row: SettlementRow) -> tuple[int, int]:
    with fake_db.get_session() as session:
        repo = SettlementRepository(session)
        settlement = repo.save(row)
        log = repo.add_log(row, settlement_id=settlement.id)
        return settlement.id, log.id


# ── sync_to_sheets ──────────────────────────────


class TestSyncToSheets:
    def test_정상_동기화(self, processor, fake_sheets, sample_settlement_data):
        row = _make_row(sample_settlement_data)

        result = processor.sync_to_sheets(row, log_id=1)

        assert result is True
        assert row.booking_key in fake_sheets.settlement_rows
        assert "1" in fake_sheets.issue_logs

    def test_is_update_플래그_전달(
        self, processor, fake_sheets, sample_settlement_data
    ):
        row = _make_row(sample_settlement_data)

        result = processor.sync_to_sheets(row, log_id=2, is_update=True)

        assert result is True


# ── mark_synced ─────────────────────────────────


class TestMarkSynced:
    def test_정상_synced_마킹(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        s_id, l_id = _create_records(fake_db, row)

        processor.mark_synced(s_id, l_id)

        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            lg = IssueLogRepository(session).get(l_id)
            assert s.sheets_synced is True
            assert s.sync_status == "completed"
            assert lg.sheets_synced is True
            assert lg.sync_status == "completed"


# ── mark_sync_failed ────────────────────────────


class TestMarkSyncFailed:
    def test_정상_실패_마킹(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        s_id, l_id = _create_records(fake_db, row)

        processor.mark_sync_failed(s_id, l_id, "시트 저장 실패")

        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            lg = IssueLogRepository(session).get(l_id)
            assert s.sync_status == "pending"
            assert s.sheets_sync_error == "시트 저장 실패"
            assert lg.sync_status == "pending"
            assert lg.sheets_sync_error == "시트 저장 실패"


# ── mark_sync_failed_safe ───────────────────────


class TestMarkSyncFailedSafe:
    def test_정상_실패_마킹(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        s_id, l_id = _create_records(fake_db, row)

        processor.mark_sync_failed_safe(s_id, l_id, "에러")

        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            assert s.sheets_sync_error == "에러"

    def test_내부예외_삼킴_로깅만(self, processor, monkeypatch):
        """mark_sync_failed 내부에서 예외 발생 시 삼키고 로깅."""

        def _raise(*_args, **_kwargs):
            raise RuntimeError("DB 연결 끊김")

        monkeypatch.setattr(processor, "mark_sync_failed", _raise)

        # 예외가 전파되지 않아야 함
        processor.mark_sync_failed_safe(999, 999, "원본 에러")


# ── after_commit ────────────────────────────────


class TestAfterCommit:
    def test_성공시_mark_synced(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        s_id, l_id = _create_records(fake_db, row)

        processor.after_commit(s_id, l_id, row)

        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            assert s.sheets_synced is True
            assert s.sync_status == "completed"

    def test_SpreadsheetError시_mark_sync_failed_safe(
        self, fake_db, processor, fake_sheets, sample_settlement_data
    ):
        row = _make_row(sample_settlement_data)
        s_id, l_id = _create_records(fake_db, row)
        fake_sheets.should_fail = True

        processor.after_commit(s_id, l_id, row)

        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            assert s.sheets_synced is False
            assert s.sheets_sync_error is not None

    def test_SQLAlchemyError시_mark_sync_failed_safe(
        self, fake_db, processor, sample_settlement_data, monkeypatch
    ):
        row = _make_row(sample_settlement_data)
        s_id, l_id = _create_records(fake_db, row)

        def _raise(*_args, **_kwargs):
            raise SQLAlchemyError("unexpected DB error")

        monkeypatch.setattr(processor, "mark_synced", _raise)

        processor.after_commit(s_id, l_id, row)

        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            assert "Unexpected" in (s.sheets_sync_error or "")


# ── claim_unsynced ──────────────────────────────


class TestClaimUnsynced:
    def test_미동기화_레코드_반환(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        _create_records(fake_db, row)

        settlements, logs = processor.claim_unsynced()

        assert len(settlements) == 1
        assert len(logs) == 1
        assert settlements[0].sync_status == "in_progress"
        assert logs[0].sync_status == "in_progress"

    def test_빈결과(self, processor):
        settlements, logs = processor.claim_unsynced()

        assert settlements == []
        assert logs == []


# ── recover_stale_records ───────────────────────


class TestRecoverStaleRecords:
    def test_stale_레코드_복구(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        s_id, l_id = _create_records(fake_db, row)

        # claim → in_progress
        processor.claim_unsynced()

        s_count, l_count = processor.recover_stale_records()

        assert s_count == 1
        assert l_count == 1
        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            lg = IssueLogRepository(session).get(l_id)
            assert s.sync_status == "pending"
            assert lg.sync_status == "pending"

    def test_복구할_레코드_없음(self, processor):
        s_count, l_count = processor.recover_stale_records()

        assert s_count == 0
        assert l_count == 0


# ── 배치 mark 메서드 ───────────────────────────


class TestBatchMarkMethods:
    def test_mark_settlement_synced(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        s_id, _ = _create_records(fake_db, row)

        processor.mark_settlement_synced(s_id)

        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            assert s.sheets_synced is True
            assert s.sync_status == "completed"

    def test_mark_settlement_failed(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        s_id, _ = _create_records(fake_db, row)

        processor.mark_settlement_failed(s_id, "에러 발생")

        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            assert s.sync_status == "pending"
            assert s.sheets_sync_error == "에러 발생"

    def test_mark_log_synced(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        _, l_id = _create_records(fake_db, row)

        processor.mark_log_synced(l_id)

        with fake_db.get_session() as session:
            lg = IssueLogRepository(session).get(l_id)
            assert lg.sheets_synced is True
            assert lg.sync_status == "completed"

    def test_mark_log_failed(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        _, l_id = _create_records(fake_db, row)

        processor.mark_log_failed(l_id, "로그 에러")

        with fake_db.get_session() as session:
            lg = IssueLogRepository(session).get(l_id)
            assert lg.sync_status == "pending"
            assert lg.sheets_sync_error == "로그 에러"


# ── mark_settlements_completed ─────────────────


class TestMarkSettlementsCompleted:
    def test_정상_일괄_완료(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        s_id, _ = _create_records(fake_db, row)

        result = processor.mark_settlements_completed({row.booking_key})

        assert result == [row.booking_key]
        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            assert s.settlement_completed is True

    def test_빈_집합이면_빈_리스트(self, processor):
        assert processor.mark_settlements_completed(set()) == []

    def test_이미_완료된_건_스킵(self, fake_db, processor, sample_settlement_data):
        row = _make_row(sample_settlement_data)
        s_id, _ = _create_records(fake_db, row)
        # 먼저 완료 처리
        with fake_db.get_session() as session:
            s = SettlementRepository(session).get(s_id)
            s.settlement_completed = True

        result = processor.mark_settlements_completed({row.booking_key})

        assert result == []

    def test_DB에_없는_키_무시(self, processor):
        result = processor.mark_settlements_completed({"NONEXISTENT"})

        assert result == []

    def test_여러_건_일괄_처리(self, fake_db, processor):
        from tests.factories import SettlementDataFactory

        keys = []
        for i in range(3):
            data = SettlementDataFactory.create(booking_key=f"BATCH-{i}")
            row = _make_row(data)
            _create_records(fake_db, row)
            keys.append(row.booking_key)

        result = processor.mark_settlements_completed(set(keys))

        assert sorted(result) == sorted(keys)
        with fake_db.get_session() as session:
            for key in keys:
                s = SettlementRepository(session).get_by_booking_key(key)
                assert s.settlement_completed is True
