"""SettlementWriter 비즈니스 로직 테스트 (constructor DI)"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from app.exceptions import AlreadyProcessedError, DatabaseError
from app.infrastructure.database.models import IssueLog, Settlement
from app.infrastructure.database.repository import SettlementRepository
from app.models.settlement import SettlementRow, SettlementStatus
from app.services.settlement_writer import SettlementWriter
from app.services.sync_processor import SyncProcessor
from tests.fakes.fake_database import FakeDatabase
from tests.fakes.fake_spreadsheet import FakeSpreadsheet


@pytest.fixture
def fake_sheets():
    return FakeSpreadsheet()


@pytest.fixture
def writer(fake_db, fake_sheets):
    """SettlementWriter — constructor DI로 Fake 주입"""
    sync_proc = SyncProcessor(fake_db.get_session, fake_sheets)
    return SettlementWriter(fake_db.get_session, sync_proc)


class TestSettlementWriterSave:
    """SettlementWriter.save() 테스트"""

    def test_승인시_DB에_저장한다(self, fake_db, writer, sample_settlement_data):
        writer.save(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found is not None
            assert found.user_name == sample_settlement_data.user_name

    def test_반려시_DB에_저장한다(self, fake_db, writer, sample_settlement_data):
        writer.save(
            data=sample_settlement_data,
            status=SettlementStatus.REJECTED,
            approver_name="반려자",
            thread_url="http://example.com/thread",
            rejection_reason="테스트 반려 사유",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found is not None
            assert found.status == SettlementStatus.REJECTED.value

    def test_승인시_settlement과_issue_log_모두_저장한다(
        self, fake_db, writer, sample_settlement_data
    ):
        writer.save(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )

        with fake_db.get_session() as session:
            settlement_count = session.execute(
                select(func.count()).select_from(Settlement)
            ).scalar()
            log_count = session.execute(
                select(func.count()).select_from(IssueLog)
            ).scalar()

            assert settlement_count == 1
            assert log_count == 1

    def test_저장된_데이터에_승인자_이름이_포함된다(
        self, fake_db, writer, sample_settlement_data
    ):
        approver = "김승인"
        writer.save(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name=approver,
            thread_url="http://example.com/thread",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.approver_name == approver

    def test_sheets_동기화_성공시_synced_True(
        self, fake_db, fake_sheets, sample_settlement_data
    ):
        # after_commit 훅에서 Sheets 동기화 성공
        sync_proc = SyncProcessor(fake_db.get_session, fake_sheets)
        w = SettlementWriter(fake_db.get_session, sync_proc)
        w.save(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.sheets_synced is True

    def test_sheets_동기화_실패시_synced_False(self, fake_db, sample_settlement_data):
        failing_sheets = FakeSpreadsheet()
        failing_sheets.should_fail = True
        sync_proc = SyncProcessor(fake_db.get_session, failing_sheets)
        w = SettlementWriter(fake_db.get_session, sync_proc)

        w.save(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.sheets_synced is False

    def test_요청시_DB에_저장한다(self, fake_db, writer, sample_settlement_data):
        writer.save(
            data=sample_settlement_data,
            status=SettlementStatus.REQUESTED,
            approver_name="",
            thread_url="http://example.com/thread",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found is not None
            assert found.status == SettlementStatus.REQUESTED.value

    def test_요청시_sheets_동기화_실행된다(
        self, fake_db, fake_sheets, sample_settlement_data
    ):
        sync_proc = SyncProcessor(fake_db.get_session, fake_sheets)
        w = SettlementWriter(fake_db.get_session, sync_proc)
        w.save(
            data=sample_settlement_data,
            status=SettlementStatus.REQUESTED,
            approver_name="",
            thread_url="http://example.com/thread",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.sheets_synced is True

    def test_반려시_sheets_동기화_실행된다(
        self, fake_db, fake_sheets, sample_settlement_data
    ):
        sync_proc = SyncProcessor(fake_db.get_session, fake_sheets)
        w = SettlementWriter(fake_db.get_session, sync_proc)
        w.save(
            data=sample_settlement_data,
            status=SettlementStatus.REJECTED,
            approver_name="반려자",
            thread_url="http://example.com/thread",
            rejection_reason="테스트 사유",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.sheets_synced is True

    def test_rejection_reason_저장된다(self, fake_db, writer, sample_settlement_data):
        writer.save(
            data=sample_settlement_data,
            status=SettlementStatus.REJECTED,
            approver_name="반려자",
            thread_url="http://example.com/thread",
            rejection_reason="고객 정보 오류",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.rejection_reason == "고객 정보 오류"

    def test_reviewer_name_저장된다(self, fake_db, writer, sample_settlement_data):
        writer.save(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="김검토",
            thread_url="http://example.com/thread",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.reviewer_name == "김검토"

    def test_요청시_reviewer_name_비어있다(
        self, fake_db, writer, sample_settlement_data
    ):
        writer.save(
            data=sample_settlement_data,
            status=SettlementStatus.REQUESTED,
            approver_name="",
            thread_url="http://example.com/thread",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.reviewer_name == ""

    def test_sheets_동기화_실패시_sync_error_기록(
        self, fake_db, sample_settlement_data
    ):
        failing_sheets = FakeSpreadsheet()
        failing_sheets.should_fail = True
        sync_proc = SyncProcessor(fake_db.get_session, failing_sheets)
        w = SettlementWriter(fake_db.get_session, sync_proc)

        w.save(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.sheets_sync_error is not None
            assert "Fake spreadsheet failure" in found.sheets_sync_error
            assert found.sync_status == "pending"


class TestRaceCondition:
    """승인/반려 Race Condition 방어 테스트"""

    @pytest.fixture
    def writer(self, fake_db):
        sheets = FakeSpreadsheet()
        sync_proc = SyncProcessor(fake_db.get_session, sheets)
        return SettlementWriter(fake_db.get_session, sync_proc)

    def _save_as_requested(self, fake_db, sample_settlement_data) -> None:
        row = SettlementRow.from_settlement_data(
            data=sample_settlement_data,
            status=SettlementStatus.REQUESTED,
            approver_name="",
            thread_url="http://example.com/thread",
        )
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            repo.save(row)
            repo.add_log(row)

    def _save_as_approved(self, fake_db, sample_settlement_data) -> None:
        row = SettlementRow.from_settlement_data(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            repo.save(row)
            repo.add_log(row)

    def test_이미_승인된_건에_승인하면_AlreadyProcessedError(
        self, fake_db, writer, sample_settlement_data
    ):
        self._save_as_approved(fake_db, sample_settlement_data)

        with pytest.raises(AlreadyProcessedError):
            writer.save(
                data=sample_settlement_data,
                status=SettlementStatus.APPROVED,
                approver_name="두번째 승인자",
                thread_url="http://example.com/thread",
            )

    def test_이미_반려된_건에_반려하면_AlreadyProcessedError(
        self, fake_db, writer, sample_settlement_data
    ):
        row = SettlementRow.from_settlement_data(
            data=sample_settlement_data,
            status=SettlementStatus.REJECTED,
            approver_name="반려자",
            thread_url="http://example.com/thread",
            rejection_reason="사유",
        )
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            repo.save(row)

        with pytest.raises(AlreadyProcessedError):
            writer.save(
                data=sample_settlement_data,
                status=SettlementStatus.REJECTED,
                approver_name="두번째 반려자",
                thread_url="http://example.com/thread",
                rejection_reason="다른 사유",
            )

    def test_이미_승인된_건에_반려하면_AlreadyProcessedError(
        self, fake_db, writer, sample_settlement_data
    ):
        self._save_as_approved(fake_db, sample_settlement_data)

        with pytest.raises(AlreadyProcessedError):
            writer.save(
                data=sample_settlement_data,
                status=SettlementStatus.REJECTED,
                approver_name="반려자",
                thread_url="http://example.com/thread",
                rejection_reason="사유",
            )

    def test_이미_반려된_건에_승인하면_AlreadyProcessedError(
        self, fake_db, writer, sample_settlement_data
    ):
        row = SettlementRow.from_settlement_data(
            data=sample_settlement_data,
            status=SettlementStatus.REJECTED,
            approver_name="반려자",
            thread_url="http://example.com/thread",
            rejection_reason="사유",
        )
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            repo.save(row)

        with pytest.raises(AlreadyProcessedError):
            writer.save(
                data=sample_settlement_data,
                status=SettlementStatus.APPROVED,
                approver_name="승인자",
                thread_url="http://example.com/thread",
            )

    def test_요청_상태에서_승인은_정상_처리(
        self, fake_db, writer, sample_settlement_data
    ):
        self._save_as_requested(fake_db, sample_settlement_data)

        writer.save(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.status == SettlementStatus.APPROVED.value


class TestExceptionTransformation:
    """예외 변환 테스트"""

    def test_save_transforms_sqlalchemy_error(self, sample_settlement_data):
        broken_db = FakeDatabase()
        Settlement.__table__.drop(broken_db.engine)

        sheets = FakeSpreadsheet()
        sync_proc = SyncProcessor(broken_db.get_session, sheets)
        w = SettlementWriter(broken_db.get_session, sync_proc)

        with pytest.raises(DatabaseError) as exc_info:
            w.save(
                data=sample_settlement_data,
                status=SettlementStatus.APPROVED,
                approver_name="테스터",
                thread_url="https://test.slack.com",
            )

        assert "저장 중 오류" in exc_info.value.user_message
        assert sample_settlement_data.booking_key in str(exc_info.value.details)

    def test_save_transforms_integrity_error(self, sample_settlement_data):
        broken_db = FakeDatabase()
        with broken_db.engine.connect() as conn:
            conn.execute(
                text(
                    "CREATE TRIGGER integrity_trap "
                    "BEFORE INSERT ON settlements "
                    "BEGIN "
                    "SELECT RAISE(ABORT, "
                    "'UNIQUE constraint failed: settlements.booking_key'); "
                    "END"
                )
            )
            conn.commit()

        sheets = FakeSpreadsheet()
        sync_proc = SyncProcessor(broken_db.get_session, sheets)
        w = SettlementWriter(broken_db.get_session, sync_proc)

        with pytest.raises(AlreadyProcessedError):
            w.save(
                data=sample_settlement_data,
                status=SettlementStatus.APPROVED,
                approver_name="테스터",
                thread_url="https://test.slack.com",
            )

    def test_mark_sync_failed_safe_never_raises(self, fake_db):
        """SyncProcessor.mark_sync_failed_safe()는 절대 예외를 발생시키지 않음"""
        sheets = FakeSpreadsheet()
        sync_proc = SyncProcessor(fake_db.get_session, sheets)

        # mark_sync_failed는 존재하지 않는 ID로 실패할 수 있지만
        # mark_sync_failed_safe는 예외를 삼킴
        sync_proc.mark_sync_failed_safe(999, 999, "test error")

    def test_sync_after_commit_catches_spreadsheet_error(
        self, fake_db, sample_settlement_row
    ):
        failing_sheets = FakeSpreadsheet()
        failing_sheets.should_fail = True
        sync_proc = SyncProcessor(fake_db.get_session, failing_sheets)

        # Should not raise
        sync_proc.after_commit(1, 1, sample_settlement_row)
