"""Repository 테스트 (인메모리 SQLite 사용)"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import IssueLog, Settlement
from app.infrastructure.database.repository import SettlementRepository
from app.models.settlement import SettlementRow
from tests.fakes.fake_database import FakeDatabase


@pytest.fixture
def fake_db():
    """각 테스트마다 새로운 인메모리 DB 생성"""
    return FakeDatabase()


@pytest.fixture
def sample_row():
    """테스트용 SettlementRow"""
    return SettlementRow(
        settlement_day="2024-01-15",
        user_name="홍길동",
        customer_name="김고객",
        booking_key="BK-001",
        company_name="테스트회사",
        company_sub_name="부서",
        settlement_cost="100000",
        carmore_cost="5000",
        user_refund_cost="0",
        issue_type="환불",
        sales_channel="온라인",
        description="테스트 정산",
        status="승인",
        approver_name="박승인",
        thread_url="http://example.com/thread",
    )


class TestSettlementRepository:
    """SettlementRepository 테스트"""

    def test_save_새로운_정산을_저장한다(self, fake_db, sample_row):
        # Given
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)

            # When
            settlement = repo.save(sample_row)

        # Then
        with fake_db.get_session() as session:
            saved = session.get(Settlement, settlement.id)
            assert saved is not None
            assert saved.booking_key == "BK-001"
            assert saved.user_name == "홍길동"
            assert saved.status == "승인"

    def test_save_금액_필드를_정수로_변환한다(self, fake_db, sample_row):
        # Given
        sample_row.settlement_cost = "1,000,000원"
        sample_row.carmore_cost = "50,000"
        sample_row.user_refund_cost = ""

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)

            # When
            settlement = repo.save(sample_row)

        # Then
        with fake_db.get_session() as session:
            saved = session.get(Settlement, settlement.id)
            assert saved.settlement_cost == 1000000
            assert saved.carmore_cost == 50000
            assert saved.user_refund_cost is None

    def test_save_동일_booking_key는_업데이트한다(self, fake_db, sample_row):
        # Given - 먼저 저장
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            first = repo.save(sample_row)
            first_id = first.id

        # When - 같은 booking_key로 다시 저장 (approver만 변경)
        sample_row.approver_name = "새승인자"
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            second = repo.save(sample_row)

        # Then - 같은 ID, 업데이트된 값
        assert second.id == first_id
        with fake_db.get_session() as session:
            saved = session.get(Settlement, first_id)
            assert saved.approver_name == "새승인자"
            assert saved.sheets_synced is False  # 다시 동기화 필요

    def test_add_log는_항상_새_로그를_추가한다(self, fake_db, sample_row):
        # Given
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            settlement = repo.save(sample_row)

            # When - 같은 row로 두 번 로그 추가
            log1 = repo.add_log(sample_row, settlement_id=settlement.id)
            log2 = repo.add_log(sample_row, settlement_id=settlement.id)

        # Then - 두 개의 서로 다른 로그
        assert log1.id != log2.id
        with fake_db.get_session() as session:
            logs = session.execute(select(IssueLog)).scalars().all()
            assert len(logs) == 2

    def test_트랜잭션_롤백_테스트(self, fake_db, sample_row):
        # Given
        try:
            with fake_db.get_session() as session:
                repo = SettlementRepository(session)
                repo.save(sample_row)

                # When - 트랜잭션 중 예외 발생
                raise ValueError("의도적 에러")
        except ValueError:
            pass

        # Then - 롤백되어 저장 안됨
        with fake_db.get_session() as session:
            settlements = session.execute(select(Settlement)).scalars().all()
            assert len(settlements) == 0

    def test_mark_synced_동기화_완료_표시(self, fake_db, sample_row):
        # Given
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            settlement = repo.save(sample_row)
            settlement_id = settlement.id

        # When
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            repo.mark_synced(settlement_id)

        # Then
        with fake_db.get_session() as session:
            saved = session.get(Settlement, settlement_id)
            assert saved.sheets_synced is True
            assert saved.sheets_synced_at is not None

    def test_list_unsynced_동기화_안된_정산_조회(self, fake_db, sample_row):
        # Given - 2개 저장, 1개만 동기화
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            s1 = repo.save(sample_row)

            sample_row.booking_key = "BK-002"
            repo.save(sample_row)

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            repo.mark_synced(s1.id)

        # When
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            unsynced = repo.list_unsynced()

        # Then - 1개만 미동기화
        assert len(unsynced) == 1
        assert unsynced[0].booking_key == "BK-002"

    def test_get_ID로_정산_조회(self, fake_db, sample_row):
        # Given
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            settlement = repo.save(sample_row)
            settlement_id = settlement.id

        # When
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get(settlement_id)

        # Then
        assert found is not None
        assert found.booking_key == "BK-001"

    def test_get_by_booking_key_예약번호로_조회(self, fake_db, sample_row):
        # Given
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            repo.save(sample_row)

        # When
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key("BK-001")

        # Then
        assert found is not None
        assert found.user_name == "홍길동"
