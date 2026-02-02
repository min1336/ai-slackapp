"""settlement_service 비즈니스 로직 테스트"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.infrastructure.database.models import ApprovalLog, Settlement
from app.infrastructure.database.repository import SettlementRepository
from app.models.settlement import SettlementStatus
from app.services.settlement_service import save_settlement
from tests.fakes.fake_database import FakeDatabase


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
        monkeypatch.setattr(
            "app.services.settlement_service.get_session",
            fake_db.get_session,
        )

        # When
        result = save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )

        # Then
        assert result is True
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found is not None
            assert found.user_name == sample_settlement_data.user_name

    def test_반려시_저장하지_않고_성공_반환한다(
        self, monkeypatch, fake_db, sample_settlement_data
    ):
        # Given - DATABASE_URL 미설정이어도 반려는 저장 안하므로 성공
        monkeypatch.setattr("app.config.database.host", "")

        # When
        result = save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.REJECTED,
            approver_name="반려자",
            thread_url="http://example.com/thread",
        )

        # Then
        assert result is True

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

    def test_승인시_settlement과_approval_log_모두_저장한다(
        self, monkeypatch, fake_db, sample_settlement_data
    ):
        # Given
        monkeypatch.setattr("app.config.database.host", "test-host")
        monkeypatch.setattr("app.config.database.password", "test-password")
        monkeypatch.setattr(
            "app.services.settlement_service.get_session",
            fake_db.get_session,
        )

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
        )

        # Then - 두 테이블 모두에 저장됨
        with fake_db.get_session() as session:
            settlement_count = session.execute(
                select(func.count()).select_from(Settlement)
            ).scalar()
            log_count = session.execute(
                select(func.count()).select_from(ApprovalLog)
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
        monkeypatch.setattr(
            "app.services.settlement_service.get_session",
            fake_db.get_session,
        )

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name=approver,
            thread_url="http://example.com/thread",
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
        # 모든 get_session 호출을 fake_db로 대체 (save + _mark_synced 모두)
        monkeypatch.setattr(
            "app.services.settlement_service.get_session",
            fake_db.get_session,
        )
        monkeypatch.setattr(
            "app.infrastructure.database.connection.get_session",
            fake_db.get_session,
        )
        monkeypatch.setattr(
            "app.services.sync_service.sync_to_sheets",
            lambda row: True,  # Sheets 동기화 성공
        )

        # When
        save_settlement(
            data=sample_settlement_data,
            status=SettlementStatus.APPROVED,
            approver_name="승인자",
            thread_url="http://example.com/thread",
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
        monkeypatch.setattr(
            "app.services.settlement_service.get_session",
            fake_db.get_session,
        )

        def fail_sync(row):
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
        )

        # Then - 동기화 실패 → sheets_synced=False, Background worker가 재시도
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(sample_settlement_data.booking_key)
            assert found.sheets_synced is False
