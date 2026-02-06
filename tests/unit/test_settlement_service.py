"""settlement_service 비즈니스 로직 테스트"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.infrastructure.database.models import IssueLog, Settlement
from app.infrastructure.database.repository import SettlementRepository
from app.models.settlement import SettlementStatus
from app.services.settlement_service import (
    _lazy_sync_settlement_completed,
    save_settlement,
)
from tests.fakes.fake_database import FakeDatabase
from tests.fakes.fake_spreadsheet import FakeSpreadsheet


@pytest.fixture
def fake_db():
    """각 테스트마다 새로운 인메모리 DB 생성"""
    return FakeDatabase()


class TestSaveSettlement:
    """save_settlement() 함수 테스트"""

    def test_승인시_DB에_저장한다(self, monkeypatch, fake_db, sample_settlement_data):
        # Given
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")

        # When - no exception means success
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
            session_factory=fake_db.get_session,
        )

        # Then
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found is not None
            assert found.user_name == sample_settlement_data.user_name

    def test_반려시_DB에_저장한다(self, monkeypatch, fake_db, sample_settlement_data):
        # Given
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.REJECTED,
            approver_name="반려자",
            thread_url="http://example.com/thread",
            rejection_reason="테스트 반려 사유",
            session_factory=fake_db.get_session,
        )

        # Then - 반려도 DB에 저장됨
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found is not None
            assert found.status == SettlementStatus.REJECTED.value

    def test_DATABASE_URL_미설정시_ValueError_발생(
        self, monkeypatch, sample_settlement_data
    ):
        # Given
        monkeypatch.setattr("app.config.database.host", "")

        # When & Then
        with pytest.raises(ValueError, match="DATABASE_URL is not configured"):
            save_settlement(
                data=sample_settlement_data,
                status=SettlementStatus.APPROVED,
                approver_name="승인자",
                thread_url="http://example.com/thread",
            )

    def test_승인시_settlement과_issue_log_모두_저장한다(
        self, monkeypatch, fake_db, sample_settlement_data
    ):
        # Given
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
            session_factory=fake_db.get_session,
        )

        # Then - 두 테이블 모두에 저장됨
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
        self, monkeypatch, fake_db, sample_settlement_data
    ):
        # Given
        approver = "김승인"
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name=approver,
            thread_url="http://example.com/thread",
            session_factory=fake_db.get_session,
        )

        # Then
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.approver_name == approver

    def test_sheets_동기화_성공시_synced_True(
        self, monkeypatch, fake_db, sample_settlement_data
    ):
        # Given - after_commit 훅으로 Sheets 동기화 성공 시
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")
        # _mark_synced는 @transactional 데코레이터를 사용하므로 connection 모듈도 패치
        monkeypatch.setattr(
            "app.infrastructure.database.connection.get_session",
            fake_db.get_session,
        )
        monkeypatch.setattr(
            "app.services.sync_service.sync_to_sheets",
            lambda row, log_id: True,  # Sheets 동기화 성공
        )

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
            session_factory=fake_db.get_session,
        )

        # Then - after_commit 훅에서 동기화 성공 → sheets_synced=True
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.sheets_synced is True

    def test_sheets_동기화_실패시_synced_False(
        self, monkeypatch, fake_db, sample_settlement_data
    ):
        # Given - after_commit 훅에서 Sheets 동기화 실패 시
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")

        def fail_sync(row, log_id):
            raise ConnectionError("Sheets API unavailable")

        monkeypatch.setattr(
            "app.services.sync_service.sync_to_sheets",
            fail_sync,
        )

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
            session_factory=fake_db.get_session,
        )

        # Then - 동기화 실패 → sheets_synced=False, Background worker가 재시도
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.sheets_synced is False

    def test_요청시_DB에_저장한다(self, monkeypatch, fake_db, sample_settlement_data):
        # Given
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.REQUESTED,
            approver_name="",
            thread_url="http://example.com/thread",
            session_factory=fake_db.get_session,
        )

        # Then
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found is not None
            assert found.status == SettlementStatus.REQUESTED.value

    def test_요청시_sheets_동기화_실행된다(
        self, monkeypatch, fake_db, sample_settlement_data
    ):
        # Given
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")
        monkeypatch.setattr(
            "app.infrastructure.database.connection.get_session",
            fake_db.get_session,
        )
        monkeypatch.setattr(
            "app.services.sync_service.sync_to_sheets",
            lambda row, log_id: True,
        )

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.REQUESTED,
            approver_name="",
            thread_url="http://example.com/thread",
            session_factory=fake_db.get_session,
        )

        # Then - REQUESTED도 sheets_synced=True
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.sheets_synced is True

    def test_반려시_sheets_동기화_실행된다(
        self, monkeypatch, fake_db, sample_settlement_data
    ):
        # Given
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")
        monkeypatch.setattr(
            "app.infrastructure.database.connection.get_session",
            fake_db.get_session,
        )
        monkeypatch.setattr(
            "app.services.sync_service.sync_to_sheets",
            lambda row, log_id: True,
        )

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.REJECTED,
            approver_name="반려자",
            thread_url="http://example.com/thread",
            rejection_reason="테스트 사유",
            session_factory=fake_db.get_session,
        )

        # Then - REJECTED도 sheets_synced=True
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.sheets_synced is True

    def test_rejection_reason_저장된다(
        self, monkeypatch, fake_db, sample_settlement_data
    ):
        # Given
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.REJECTED,
            approver_name="반려자",
            thread_url="http://example.com/thread",
            rejection_reason="고객 정보 오류",
            session_factory=fake_db.get_session,
        )

        # Then
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.rejection_reason == "고객 정보 오류"

    def test_reviewer_name_저장된다(self, monkeypatch, fake_db, sample_settlement_data):
        # Given
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")

        # When - 승인 시 reviewer_name = approver_name
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="김검토",
            thread_url="http://example.com/thread",
            session_factory=fake_db.get_session,
        )

        # Then - reviewer_name = approver_name (검토자)
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.reviewer_name == "김검토"

    def test_요청시_reviewer_name_비어있다(
        self, monkeypatch, fake_db, sample_settlement_data
    ):
        # Given
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")

        # When - 요청 시 아직 검토자 없음
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.REQUESTED,
            approver_name="",
            thread_url="http://example.com/thread",
            session_factory=fake_db.get_session,
        )

        # Then - reviewer_name = "" (빈 문자열)
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.reviewer_name == ""


class TestLazySyncSettlementCompleted:
    """_lazy_sync_settlement_completed() 함수 테스트"""

    def _save_and_mark_synced(self, fake_db, sample_settlement_data) -> str:
        """헬퍼: DB에 정산 저장 후 sheets_synced=True로 표시"""
        from app.models import SettlementRow

        row = SettlementRow.from_settlement_data(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            settlement = repo.save(row)
            settlement.sheets_synced = True
            session.commit()

        return sample_settlement_data.booking_key

    def test_정산완료된_건은_DB_completed_처리(self, fake_db, sample_settlement_data):
        # Given - DB에 정산 저장 + sheets_synced=True
        booking_key = self._save_and_mark_synced(fake_db, sample_settlement_data)

        # Sheets에서 정산완료 처리됨 (활성 행 없음)
        fake_sheets = FakeSpreadsheet()
        fake_sheets.settlement_rows[booking_key] = ["row"]
        fake_sheets.completed_keys.add(booking_key)

        # When
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            result = _lazy_sync_settlement_completed(booking_key, repo, fake_sheets)
            session.commit()

        # Then - settlement_completed=True로 갱신됨
        assert result is True
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(booking_key)
            assert found.settlement_completed is True

    def test_동기화_안된_건은_건너뜀(self, fake_db, sample_settlement_data):
        # Given - DB에 정산 저장, sheets_synced=False (기본값)
        from app.models import SettlementRow

        row = SettlementRow.from_settlement_data(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            repo.save(row)
            session.commit()

        booking_key = sample_settlement_data.booking_key

        # Sheets에서 정산완료 처리됨 (하지만 DB 동기화 안 됨)
        fake_sheets = FakeSpreadsheet()
        fake_sheets.completed_keys.add(booking_key)

        # When
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            result = _lazy_sync_settlement_completed(booking_key, repo, fake_sheets)

        # Then - sheets_synced=False이므로 Sheets 조회 안 함
        assert result is False
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(booking_key)
            assert found.settlement_completed is False
