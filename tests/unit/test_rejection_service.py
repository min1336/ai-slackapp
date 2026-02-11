"""RejectionService 반려 워크플로우 테스트"""

from __future__ import annotations

import pytest

from app.models import RejectionMetadata
from app.services.rejection_service import RejectionService
from app.services.settlement_writer import SettlementWriter
from app.services.sync_processor import SyncProcessor
from tests.factories import SettlementDataFactory
from tests.fakes.fake_slack import FakeSlackReader, FakeSlackWriter


@pytest.fixture
def fake_reader():
    reader = FakeSlackReader()
    reader.user_names["U_REJECTER"] = "반려자"
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
    return RejectionService(
        fake_reader,
        fake_writer,
        settlement_writer,
        approvers=frozenset({"U_REJECTER"}),
    )


@pytest.fixture
def sample_data():
    return SettlementDataFactory.create(
        requester_id="U_REQUESTER",
        original_channel_id="C_ORIGINAL",
        original_thread_ts="100.100",
        original_message_ts="200.200",
    )


@pytest.fixture
def sample_metadata():
    return RejectionMetadata(
        channel_id="C_APPROVAL",
        thread_ts="",
        message_ts="300.300",
        requester_id="U_REQUESTER",
        button_data="{}",
        original_channel_id="C_ORIGINAL",
        original_thread_ts="100.100",
        original_message_ts="200.200",
    )


class TestHasPermission:
    def test_반려자는_True(self, service):
        assert service.has_permission(
            user_id="U_REJECTER",
            channel_id="C1",
            thread_ts="1.1",
            text="denied",
        )

    def test_비권한자는_False_ephemeral_전송(self, service, fake_writer):
        result = service.has_permission(
            user_id="U_OTHER",
            channel_id="C1",
            thread_ts="1.1",
            text="⚠️ 반려 권한이 없습니다.",
        )
        assert result is False
        assert len(fake_writer.ephemeral_messages) == 1
        assert fake_writer.ephemeral_messages[0]["user"] == "U_OTHER"


class TestReject:
    def test_반려_성공시_3단계_업데이트(
        self, service, fake_writer, sample_data, sample_metadata
    ):
        service.reject(
            data=sample_data,
            metadata=sample_metadata,
            rejection_reason="테스트 반려 사유",
            rejecter_id="U_REJECTER",
        )
        # 처리중 + 승인채널 반려 + 원본스레드 반려 = 3회 업데이트
        assert len(fake_writer.updated_messages) == 3
        # 요청자 멘션 메시지
        mention_msgs = [
            m for m in fake_writer.posted_messages if "<@U_REQUESTER>" in m["text"]
        ]
        assert len(mention_msgs) == 1
        assert "반려" in mention_msgs[0]["text"]
        assert "테스트 반려 사유" in mention_msgs[0]["text"]

    def test_AlreadyProcessedError시_원본_블록_복원(
        self, service, fake_writer, sample_data, sample_metadata
    ):
        # 첫 번째 반려
        service.reject(
            data=sample_data,
            metadata=sample_metadata,
            rejection_reason="사유1",
            rejecter_id="U_REJECTER",
        )
        fake_writer.clear()

        # 두 번째 반려 → AlreadyProcessedError
        service.reject(
            data=sample_data,
            metadata=sample_metadata,
            rejection_reason="사유2",
            rejecter_id="U_REJECTER",
        )
        # 복원 업데이트 (처리중 표시 후 복원)
        assert len(fake_writer.updated_messages) >= 1
        # DM으로 에러 알림
        dm_msgs = [
            m for m in fake_writer.posted_messages if m["channel"] == "U_REJECTER"
        ]
        assert len(dm_msgs) == 1
        assert "이미 처리된" in dm_msgs[0]["text"]
