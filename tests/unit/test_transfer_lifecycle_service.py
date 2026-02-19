"""TransferLifecycleService 이관 생명주기 관리 테스트"""

from __future__ import annotations

import pytest

from app.infrastructure.database import SettlementRepository
from app.models import SettlementRow, SettlementStatus
from app.services.thread_reference_store import ThreadReferenceStore
from app.services.transfer_lifecycle_service import TransferLifecycleService
from tests.factories import SettlementDataFactory
from tests.fakes.fake_database import FakeDatabase
from tests.fakes.fake_spreadsheet import FakeSpreadsheet


def _make_row(
    booking_key: str = "A0001",
    note: str = "",
) -> SettlementRow:
    data = SettlementDataFactory.create(booking_key=booking_key, note=note)
    return SettlementRow.from_settlement_data(
        data=data,
        status=SettlementStatus.APPROVED,
        approver_name="승인자",
        thread_url="https://slack.com/thread",
    )


@pytest.fixture
def fake_db():
    return FakeDatabase()


@pytest.fixture
def fake_sheets():
    return FakeSpreadsheet()


@pytest.fixture
def thread_store(fake_db):
    return ThreadReferenceStore(fake_db.get_session)


@pytest.fixture
def service(fake_db, thread_store, fake_sheets):
    return TransferLifecycleService(fake_db.get_session, thread_store, fake_sheets)


class TestMarkTransferred:
    def test_이관건이면_root의_transferred_to_설정_및_Sheets_비고_업데이트(
        self, service, fake_db, thread_store, fake_sheets
    ):
        # Given: A0001 정산이 존재하고, B0001이 A0001에서 이관된 건
        row = _make_row("A0001", note="기존비고")
        with fake_db.get_session() as session:
            SettlementRepository(session).save(row)
        fake_sheets.settlement_rows["A0001"] = row.to_dict()

        thread_store.save("A0001", "C1", "1.1")
        thread_store.save("B0001", "C1", "1.1", root_booking_key="A0001")

        # When
        service.mark_transferred("B0001")

        # Then: DB에서 A0001의 transferred_to = "B0001"
        with fake_db.get_session() as session:
            settlement = SettlementRepository(session).get_active_by_booking_key(
                "A0001"
            )
            assert settlement is not None
            assert settlement.transferred_to == "B0001"

        # Sheets 비고에 이관 표시 추가
        assert "[이관→B0001]" in fake_sheets.settlement_rows["A0001"]["note"]

    def test_ThreadRef_없으면_no_op(self, service, fake_db, fake_sheets):
        # Given: ThreadReference에 B0001 없음
        row = _make_row("A0001")
        with fake_db.get_session() as session:
            SettlementRepository(session).save(row)

        # When: no-op
        service.mark_transferred("B0001")

        # Then: A0001 변경 없음
        with fake_db.get_session() as session:
            settlement = SettlementRepository(session).get_active_by_booking_key(
                "A0001"
            )
            if settlement:
                assert settlement.transferred_to is None

    def test_root가_자기자신이면_no_op(
        self, service, fake_db, thread_store, fake_sheets
    ):
        # Given: A0001의 root_booking_key가 자기 자신 (이관 아님)
        row = _make_row("A0001")
        with fake_db.get_session() as session:
            SettlementRepository(session).save(row)

        thread_store.save("A0001", "C1", "1.1")

        # When
        service.mark_transferred("A0001")

        # Then: 변경 없음
        with fake_db.get_session() as session:
            settlement = SettlementRepository(session).get_active_by_booking_key(
                "A0001"
            )
            assert settlement is not None
            assert settlement.transferred_to is None

    def test_root의_활성_Settlement_없으면_no_op(
        self, service, fake_db, thread_store, fake_sheets
    ):
        # Given: A0001의 DB 레코드가 없음
        thread_store.save("A0001", "C1", "1.1")
        thread_store.save("B0001", "C1", "1.1", root_booking_key="A0001")

        # When: no-op (예외 없이)
        service.mark_transferred("B0001")

        # Then: Sheets도 변경 없음
        assert "A0001" not in fake_sheets.settlement_rows


class TestRevertTransfer:
    def test_반려시_root의_transferred_to_해제_및_Sheets_비고_복구(
        self, service, fake_db, thread_store, fake_sheets
    ):
        # Given: A0001이 B0001로 이관된 상태
        row = _make_row("A0001", note="기존비고")
        with fake_db.get_session() as session:
            SettlementRepository(session).save(row)
        fake_sheets.settlement_rows["A0001"] = row.to_dict()

        thread_store.save("A0001", "C1", "1.1")
        thread_store.save("B0001", "C1", "1.1", root_booking_key="A0001")

        # 이관 마킹
        service.mark_transferred("B0001")

        # When: B0001 반려 → 이관 복구
        service.revert_transfer("B0001")

        # Then: DB에서 A0001의 transferred_to = None
        with fake_db.get_session() as session:
            settlement = SettlementRepository(session).get_active_by_booking_key(
                "A0001"
            )
            assert settlement is not None
            assert settlement.transferred_to is None

        # Sheets 비고에서 이관 표시 제거
        assert "[이관→B0001]" not in fake_sheets.settlement_rows["A0001"]["note"]

    def test_root가_이관상태_아니면_no_op(
        self, service, fake_db, thread_store, fake_sheets
    ):
        # Given: A0001이 이관 상태가 아님
        row = _make_row("A0001", note="기존비고")
        with fake_db.get_session() as session:
            SettlementRepository(session).save(row)
        fake_sheets.settlement_rows["A0001"] = row.to_dict()

        thread_store.save("A0001", "C1", "1.1")
        thread_store.save("B0001", "C1", "1.1", root_booking_key="A0001")

        # When: 이관 마킹 안 한 상태에서 복구 시도
        service.revert_transfer("B0001")

        # Then: 비고 변경 없음
        assert fake_sheets.settlement_rows["A0001"]["note"] == "기존비고"
