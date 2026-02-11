"""ThreadDiscoveryService 스레드 탐색 테스트 (constructor DI)"""

from __future__ import annotations

import pytest

from app.infrastructure.database.repository import ThreadReferenceRepository
from app.models import ThreadLocation
from app.services.thread_discovery_service import ThreadDiscoveryService
from app.services.thread_reference_store import ThreadReferenceStore
from tests.fakes.fake_slack import FakeSlackReader


@pytest.fixture
def fake_reader():
    return FakeSlackReader()


@pytest.fixture
def store(fake_db):
    return ThreadReferenceStore(fake_db.get_session)


@pytest.fixture
def service(store, fake_reader):
    return ThreadDiscoveryService(store, fake_reader, reservation_channel="C_ISSUE")


class TestFindIssueThread:
    def test_채널_미설정시_None_반환(self, store, fake_reader):
        svc = ThreadDiscoveryService(store, fake_reader, reservation_channel="")
        result = svc.find_issue_thread("BK-001")

        assert result is None

    def test_DB에_있으면_즉시_반환(self, fake_db, service):
        # Given — DB에 레퍼런스 저장
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            repo.save(
                booking_key="BK-001",
                channel_id="C_ISSUE",
                thread_ts="111.111",
            )

        # When
        result = service.find_issue_thread("BK-001")

        # Then
        assert result == ThreadLocation(channel_id="C_ISSUE", thread_ts="111.111")

    def test_DB_미스시_Slack_API_폴백(self, fake_reader, service):
        fake_reader.messages_by_text[("C_ISSUE", "BK-001")] = "222.222"

        result = service.find_issue_thread("BK-001")

        assert result == ThreadLocation(channel_id="C_ISSUE", thread_ts="222.222")

    def test_Slack_API_폴백_후_DB에_캐시_저장(self, fake_db, fake_reader, service):
        fake_reader.messages_by_text[("C_ISSUE", "BK-001")] = "333.333"

        service.find_issue_thread("BK-001")

        # DB에 캐시되었는지 확인
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("BK-001")
            assert ref is not None
            assert ref.thread_ts == "333.333"
            assert ref.channel_id == "C_ISSUE"

    def test_Slack_API에서도_못_찾으면_None(self, service):
        # FakeSlackReader는 기본적으로 None 반환
        result = service.find_issue_thread("BK-001")

        assert result is None


class TestSaveThreadReference:
    def test_기본_저장(self, fake_db, service):
        service.save_thread_reference(
            booking_key="BK-001",
            channel_id="C123",
            thread_ts="111.111",
        )

        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("BK-001")
            assert ref is not None
            assert ref.root_booking_key == "BK-001"

    def test_root_booking_key_지정(self, fake_db, service):
        service.save_thread_reference(
            booking_key="BK-002",
            channel_id="C123",
            thread_ts="111.111",
            root_booking_key="BK-001",
        )

        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("BK-002")
            assert ref is not None
            assert ref.root_booking_key == "BK-001"


class TestRegisterOriginThread:
    def test_최초_스레드_등록(self, fake_db, service):
        service.register_origin_thread(
            booking_key="BK-001",
            channel_id="C_ISSUE",
            thread_ts="111.111",
        )

        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("BK-001")
            assert ref is not None
            assert ref.channel_id == "C_ISSUE"
            assert ref.thread_ts == "111.111"
            assert ref.root_booking_key == "BK-001"

    def test_중복_등록은_안전하게_무시된다(self, fake_db, service):
        for _ in range(3):
            service.register_origin_thread(
                booking_key="BK-001",
                channel_id="C_ISSUE",
                thread_ts="111.111",
            )

        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("BK-001")
            assert ref is not None
