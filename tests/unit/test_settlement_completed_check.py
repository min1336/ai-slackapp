"""정산완료 체크 테스트

Writer: DB settlement_completed 체크 (_validate_not_already_processed 확장)
Orchestrator: Sheets 폴백 (_guard_settlement_completed)
"""

from __future__ import annotations

import pytest

from app.exceptions import SettlementCompletedError
from app.infrastructure.database.repository import SettlementRepository
from app.models.settlement import SettlementRow, SettlementStatus
from app.services.approval_service import ApprovalService
from app.services.rejection_service import RejectionService
from app.services.settlement_writer import SettlementWriter
from app.services.sync_processor import SyncProcessor
from tests.factories import SettlementDataFactory
from tests.fakes.fake_slack import FakeSlackReader, FakeSlackWriter
from tests.fakes.fake_spreadsheet import FakeSpreadsheet


@pytest.fixture
def fake_sheets():
    return FakeSpreadsheet()


def _make_writer(fake_db):
    sheets = FakeSpreadsheet()
    sync_proc = SyncProcessor(fake_db.get_session, sheets)
    return SettlementWriter(fake_db.get_session, sync_proc)


def _save_as_requested(fake_db, data):
    row = SettlementRow.from_settlement_data(
        data=data,
        status=SettlementStatus.REQUESTED,
        approver_name="",
        thread_url="http://example.com/thread",
    )
    with fake_db.get_session() as session:
        repo = SettlementRepository(session)
        repo.save(row)


def _mark_completed_in_db(fake_db, booking_key):
    with fake_db.get_session() as session:
        repo = SettlementRepository(session)
        existing = repo.get_by_booking_key(booking_key)
        if existing:
            existing.settlement_completed = True


class TestWriterDBCheck:
    """Writer._validate_not_already_processed()의 settlement_completed DB 체크"""

    def test_DB에_정산완료_있으면_SettlementCompletedError(
        self, fake_db, sample_settlement_data
    ):
        _save_as_requested(fake_db, sample_settlement_data)
        _mark_completed_in_db(fake_db, sample_settlement_data.booking_key)

        writer = _make_writer(fake_db)

        with pytest.raises(SettlementCompletedError) as exc_info:
            writer.save(
                data=sample_settlement_data,
                status=SettlementStatus.APPROVED,
                approver_name="승인자",
                thread_url="http://example.com/thread",
            )

        assert "정산완료" in exc_info.value.user_message
        assert exc_info.value.details["source"] == "db"

    def test_REJECTED_상태에서도_정산완료_체크(self, fake_db, sample_settlement_data):
        _save_as_requested(fake_db, sample_settlement_data)
        _mark_completed_in_db(fake_db, sample_settlement_data.booking_key)

        writer = _make_writer(fake_db)

        with pytest.raises(SettlementCompletedError):
            writer.save(
                data=sample_settlement_data,
                status=SettlementStatus.REJECTED,
                approver_name="반려자",
                thread_url="http://example.com/thread",
                rejection_reason="사유",
            )

    def test_REQUESTED_상태에서는_체크_스킵(self, fake_db, sample_settlement_data):
        writer = _make_writer(fake_db)

        # REQUESTED 상태에서는 정산완료 체크를 건너뜀
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

    def test_DB_completed_False이면_정상진행(self, fake_db, sample_settlement_data):
        _save_as_requested(fake_db, sample_settlement_data)

        writer = _make_writer(fake_db)

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


class TestOrchestratorSheetsGuard:
    """ApprovalService/RejectionService의 Sheets 폴백 체크"""

    @pytest.fixture
    def data(self):
        return SettlementDataFactory.create(
            requester_id="U_REQUESTER",
            original_channel_id="C_ORIGINAL",
            original_thread_ts="1234.5678",
            original_message_ts="1234.5679",
        )

    @pytest.fixture
    def reader(self):
        r = FakeSlackReader()
        r.user_names["U_APPROVER"] = "승인자"
        r.user_names["U_REQUESTER"] = "요청자"
        return r

    def test_승인시_Sheets_정산완료이면_차단_및_DB반영(
        self, fake_db, fake_sheets, reader, data
    ):
        _save_as_requested(fake_db, data)
        fake_sheets.completed_keys.add(data.booking_key)

        sync_proc = SyncProcessor(fake_db.get_session, fake_sheets)
        sw = SettlementWriter(fake_db.get_session, sync_proc)
        writer = FakeSlackWriter()
        svc = ApprovalService(
            reader,
            writer,
            sw,
            approvers=frozenset({"U_APPROVER"}),
            sheets=fake_sheets,
        )

        svc.approve(
            data=data,
            user_id="U_APPROVER",
            channel_id="C_APPROVAL",
            message_ts="msg.ts",
            thread_ts="thread.ts",
            original_blocks=[{"type": "section"}],
            is_transfer=False,
        )

        # ephemeral로 정산완료 메시지가 전송됨
        assert any("정산완료" in msg["text"] for msg in writer.ephemeral_messages)

        # DB에 settlement_completed가 반영됨
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(data.booking_key)
            assert found.settlement_completed is True

    def test_반려시_Sheets_정산완료이면_차단_및_DB반영(
        self, fake_db, fake_sheets, reader, data
    ):
        from app.models import RejectionMetadata

        _save_as_requested(fake_db, data)
        fake_sheets.completed_keys.add(data.booking_key)

        sync_proc = SyncProcessor(fake_db.get_session, fake_sheets)
        sw = SettlementWriter(fake_db.get_session, sync_proc)
        writer = FakeSlackWriter()
        svc = RejectionService(
            reader,
            writer,
            sw,
            approvers=frozenset({"U_APPROVER"}),
            sheets=fake_sheets,
        )

        metadata = RejectionMetadata(
            channel_id="C_APPROVAL",
            thread_ts="thread.ts",
            message_ts="msg.ts",
            requester_id="U_REQUESTER",
            button_data=data.model_dump_json(),
            original_channel_id="C_ORIGINAL",
            original_thread_ts="1234.5678",
            original_message_ts="1234.5679",
        )

        svc.reject(
            data=data,
            metadata=metadata,
            rejection_reason="테스트 사유",
            rejecter_id="U_APPROVER",
        )

        # post_message로 정산완료 알림이 전송됨
        assert any("정산완료" in msg["text"] for msg in writer.posted_messages)

        # DB에 settlement_completed가 반영됨
        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(data.booking_key)
            assert found.settlement_completed is True

    def test_Sheets_미완료이면_정상_승인(self, fake_db, fake_sheets, reader, data):
        # fake_sheets에 completed_keys 미설정 → 정상 진행
        sync_proc = SyncProcessor(fake_db.get_session, fake_sheets)
        sw = SettlementWriter(fake_db.get_session, sync_proc)
        svc = ApprovalService(
            reader,
            FakeSlackWriter(),
            sw,
            approvers=frozenset({"U_APPROVER"}),
            sheets=fake_sheets,
        )

        svc.approve(
            data=data,
            user_id="U_APPROVER",
            channel_id="C_APPROVAL",
            message_ts="msg.ts",
            thread_ts="thread.ts",
            original_blocks=[{"type": "section"}],
            is_transfer=False,
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(data.booking_key)
            assert found.status == SettlementStatus.APPROVED.value

    def test_sheets_None이면_체크_스킵(self, fake_db, reader, data):
        sheets = FakeSpreadsheet()
        sync_proc = SyncProcessor(fake_db.get_session, sheets)
        sw = SettlementWriter(fake_db.get_session, sync_proc)
        svc = ApprovalService(
            reader,
            FakeSlackWriter(),
            sw,
            approvers=frozenset({"U_APPROVER"}),
            # sheets 미전달 → None
        )

        svc.approve(
            data=data,
            user_id="U_APPROVER",
            channel_id="C_APPROVAL",
            message_ts="msg.ts",
            thread_ts="thread.ts",
            original_blocks=[{"type": "section"}],
            is_transfer=False,
        )

        with fake_db.get_session() as session:
            repo = SettlementRepository(session)
            found = repo.get_by_booking_key(data.booking_key)
            assert found.status == SettlementStatus.APPROVED.value
