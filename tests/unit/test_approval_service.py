"""ApprovalService 승인 워크플로우 테스트"""

from __future__ import annotations

import pytest

from app.services.approval_service import ApprovalService
from app.services.settlement_writer import SettlementWriter
from app.services.sync_processor import SyncProcessor
from tests.factories import SettlementDataFactory
from tests.fakes.fake_slack import FakeSlackReader, FakeSlackWriter


@pytest.fixture
def fake_reader():
    reader = FakeSlackReader()
    reader.user_names["U_APPROVER"] = "승인자"
    reader.user_names["U_REQUESTER"] = "요청자"
    return reader


@pytest.fixture
def fake_writer():
    return FakeSlackWriter()


@pytest.fixture
def settlement_writer(fake_db, fake_spreadsheet):
    sync = SyncProcessor(fake_db.get_session, fake_spreadsheet)
    return SettlementWriter(fake_db.get_session, sync)


@pytest.fixture
def service(fake_reader, fake_writer, settlement_writer):
    return ApprovalService(
        fake_reader,
        fake_writer,
        settlement_writer,
        approvers=frozenset({"U_APPROVER"}),
    )


@pytest.fixture
def sample_data():
    return SettlementDataFactory.create(
        requester_id="U_REQUESTER",
        original_channel_id="C_ORIGINAL",
        original_thread_ts="100.100",
        original_message_ts="200.200",
    )


class TestHasPermission:
    def test_승인자는_True(self, service):
        assert service.has_permission(
            user_id="U_APPROVER",
            channel_id="C1",
            thread_ts="1.1",
            text="denied",
        )

    def test_비승인자는_False_ephemeral_전송(self, service, fake_writer):
        result = service.has_permission(
            user_id="U_OTHER",
            channel_id="C1",
            thread_ts="1.1",
            text="⚠️ 승인 권한이 없습니다.",
        )
        assert result is False
        assert len(fake_writer.ephemeral_messages) == 1
        assert fake_writer.ephemeral_messages[0]["user"] == "U_OTHER"


class TestApprove:
    def test_권한_없으면_조기_반환(self, service, fake_writer, sample_data):
        service.approve(
            data=sample_data,
            user_id="U_NO_PERM",
            channel_id="C_APPROVAL",
            message_ts="300.300",
            thread_ts="",
            original_blocks=[{"type": "section"}],
            is_transfer=False,
        )
        # 승인 채널 업데이트 없음 (ephemeral만 1건)
        assert len(fake_writer.updated_messages) == 0
        assert len(fake_writer.ephemeral_messages) == 1

    def test_승인_성공시_메시지_업데이트(self, service, fake_writer, sample_data):
        service.approve(
            data=sample_data,
            user_id="U_APPROVER",
            channel_id="C_APPROVAL",
            message_ts="300.300",
            thread_ts="",
            original_blocks=[{"type": "section"}],
            is_transfer=False,
        )
        # 처리중 + 승인채널 + 원본스레드 = 3회 업데이트
        assert len(fake_writer.updated_messages) == 3
        # 요청자 멘션 메시지
        mention_msgs = [
            m for m in fake_writer.posted_messages if "<@U_REQUESTER>" in m["text"]
        ]
        assert len(mention_msgs) == 1

    def test_AlreadyProcessedError시_원본_블록_복원(
        self, service, fake_writer, settlement_writer, sample_data
    ):
        # 첫 번째 승인
        service.approve(
            data=sample_data,
            user_id="U_APPROVER",
            channel_id="C_APPROVAL",
            message_ts="300.300",
            thread_ts="",
            original_blocks=[{"type": "section"}],
            is_transfer=False,
        )
        fake_writer.clear()

        # 두 번째 승인 → AlreadyProcessedError
        service.approve(
            data=sample_data,
            user_id="U_APPROVER",
            channel_id="C_APPROVAL",
            message_ts="300.300",
            thread_ts="",
            original_blocks=[{"type": "section"}],
            is_transfer=False,
        )
        # 원본 블록 복원 업데이트
        restored = [
            m
            for m in fake_writer.updated_messages
            if m["blocks"] == [{"type": "section"}]
        ]
        assert len(restored) == 1
        # ephemeral 에러 알림
        assert len(fake_writer.ephemeral_messages) == 1
        assert "이미 처리된" in fake_writer.ephemeral_messages[0]["text"]
