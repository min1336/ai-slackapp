"""ThreadDiscoveryService 스레드 탐색 테스트 (constructor DI)"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from slack_sdk.errors import SlackApiError

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
    return ThreadDiscoveryService(store, fake_reader, reservation_channels=["C_ISSUE"])


class TestFindIssueThread:
    def test_채널_미설정시_None_반환(self, store, fake_reader):
        svc = ThreadDiscoveryService(store, fake_reader, reservation_channels=[])
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

    def test_보조_예약번호로_폴백_탐색한다(self, fake_reader, service):
        fake_reader.messages_by_text[("C_ISSUE", "BK-NEW")] = "444.444"

        result = service.find_issue_thread(
            "BK-OLD",
            fallback_booking_keys=("BK-NEW",),
        )

        assert result == ThreadLocation(channel_id="C_ISSUE", thread_ts="444.444")

    def test_예약번호_라벨_쿼리로도_폴백_탐색한다(self, fake_reader, service):
        fake_reader.messages_by_text[("C_ISSUE", "예약번호 : BK-LABELED")] = "555.111"

        result = service.find_issue_thread("BK-LABELED")

        assert result == ThreadLocation(channel_id="C_ISSUE", thread_ts="555.111")

    def test_멀티채널_첫_채널_미스시_두번째_채널에서_발견한다(self, store, fake_reader):
        svc = ThreadDiscoveryService(
            store, fake_reader, reservation_channels=["C_A", "C_B"]
        )
        fake_reader.messages_by_text[("C_B", "BK-001")] = "222.222"

        result = svc.find_issue_thread("BK-001")

        assert result == ThreadLocation(channel_id="C_B", thread_ts="222.222")


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


class TestGetChainBookingKeys:
    def test_체인_멤버_전체_조회(self, fake_db, store):
        store.save("A-001", "C_ISSUE", "111.111")
        store.save("B-001", "C_ISSUE", "111.111", root_booking_key="A-001")
        store.save("C-001", "C_ISSUE", "111.111", root_booking_key="A-001")

        keys = store.get_chain_booking_keys("A-001")

        assert set(keys) == {"A-001", "B-001", "C-001"}

    def test_체인_없으면_빈_리스트(self, store):
        keys = store.get_chain_booking_keys("NONEXISTENT")

        assert keys == []


class TestBackfillReservationThreads:
    def test_백필로_채널_메시지에서_booking_key를_캐시한다(
        self, fake_db, fake_reader, service
    ):
        fake_reader.channel_messages["C_ISSUE"] = [
            {"text": "예약번호 : BK-100\n업체명 : 테스트업체", "ts": "100.100"},
            {"text": "예약번호 : BK-200\n업체명 : 다른업체", "ts": "200.200"},
        ]

        saved = service.backfill_reservation_threads(days=7)

        assert saved == 2
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref1 = repo.get_by_booking_key("BK-100")
            ref2 = repo.get_by_booking_key("BK-200")
            assert ref1 is not None
            assert ref1.thread_ts == "100.100"
            assert ref1.channel_id == "C_ISSUE"
            assert ref2 is not None
            assert ref2.thread_ts == "200.200"

    def test_이미_DB에_있는_건은_스킵한다(self, fake_db, fake_reader, service):
        # Given — DB에 이미 있는 건
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            repo.save(
                booking_key="BK-100",
                channel_id="C_ISSUE",
                thread_ts="100.100",
            )

        fake_reader.channel_messages["C_ISSUE"] = [
            {"text": "예약번호 : BK-100\n업체명 : 테스트업체", "ts": "100.100"},
            {"text": "예약번호 : BK-NEW\n업체명 : 신규업체", "ts": "200.200"},
        ]

        saved = service.backfill_reservation_threads(days=7)

        assert saved == 1  # BK-NEW만 저장

    def test_파싱_안되는_메시지는_스킵한다(self, fake_reader, service):
        fake_reader.channel_messages["C_ISSUE"] = [
            {"text": "아무 관련 없는 메시지", "ts": "100.100"},
            {"text": "", "ts": "200.200"},
        ]

        saved = service.backfill_reservation_threads(days=7)

        assert saved == 0

    def test_days_None이면_oldest_0으로_전체_히스토리_스캔한다(
        self, fake_db, fake_reader, service
    ):
        fake_reader.channel_messages["C_ISSUE"] = [
            {"text": "예약번호 : BK-OLD\n업체명 : 오래전", "ts": "10.010"},
        ]
        captured: dict = {}
        original = fake_reader.list_channel_messages

        def _capture(channel_id, *, oldest=0, max_pages=10):
            captured["oldest"] = oldest
            captured["max_pages"] = max_pages
            return original(channel_id, oldest=oldest, max_pages=max_pages)

        fake_reader.list_channel_messages = _capture

        saved = service.backfill_reservation_threads(days=None, max_pages=500)

        assert saved == 1
        assert captured["oldest"] == 0.0
        assert captured["max_pages"] == 500

    def test_채널_미설정시_0_반환(self, store, fake_reader):
        svc = ThreadDiscoveryService(store, fake_reader, reservation_channels=[])

        saved = svc.backfill_reservation_threads(days=7)

        assert saved == 0

    def test_API_에러시_0_반환(self, fake_reader, service):
        def _raise_on_call(*_args, **_kwargs):
            raise SlackApiError(message="channel_not_found", response=Mock())

        fake_reader.list_channel_messages = _raise_on_call

        saved = service.backfill_reservation_threads(days=7)

        assert saved == 0

    def test_iteration_중_API_에러시_저장된_건수만_반환(
        self, fake_db, fake_reader, service
    ):
        def _yield_then_raise(channel_id, *, oldest=0, max_pages=10):
            yield {"text": "예약번호 : BK-OK\n업체명 : 성공", "ts": "100.100"}
            raise SlackApiError(message="rate_limited", response=Mock())

        fake_reader.list_channel_messages = _yield_then_raise

        saved = service.backfill_reservation_threads(days=7)

        assert saved == 1
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            assert repo.get_by_booking_key("BK-OK") is not None

    def test_메시지_처리_중_예외시_나머지_메시지는_계속_처리한다(
        self, fake_db, fake_reader, service, monkeypatch
    ):
        fake_reader.channel_messages["C_ISSUE"] = [
            {"text": "예약번호 : BK-FAIL\n업체명 : 실패건", "ts": "100.100"},
            {"text": "예약번호 : BK-OK\n업체명 : 성공건", "ts": "200.200"},
        ]

        original_parse = __import__(
            "app.services.message_parser", fromlist=["parse_settlement_message"]
        ).parse_settlement_message
        call_count = 0

        def _parse_with_error(text):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("unexpected parse error")
            return original_parse(text)

        monkeypatch.setattr(
            "app.services.message_parser.parse_settlement_message",
            _parse_with_error,
        )

        saved = service.backfill_reservation_threads(days=7)

        assert saved == 1
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            assert repo.get_by_booking_key("BK-OK") is not None
            assert repo.get_by_booking_key("BK-FAIL") is None

    def test_멀티채널_모든_채널을_스캔한다(self, fake_db, store, fake_reader):
        svc = ThreadDiscoveryService(
            store, fake_reader, reservation_channels=["C_A", "C_B"]
        )
        fake_reader.channel_messages["C_A"] = [
            {"text": "예약번호 : BK-A1\n업체명 : 업체A", "ts": "100.100"},
        ]
        fake_reader.channel_messages["C_B"] = [
            {"text": "예약번호 : BK-B1\n업체명 : 업체B", "ts": "200.200"},
        ]

        saved = svc.backfill_reservation_threads(days=7)

        assert saved == 2
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref_a = repo.get_by_booking_key("BK-A1")
            ref_b = repo.get_by_booking_key("BK-B1")
            assert ref_a is not None and ref_a.channel_id == "C_A"
            assert ref_b is not None and ref_b.channel_id == "C_B"

    def test_멀티채널_한_채널_실패시_나머지_계속_스캔한다(
        self, fake_db, store, fake_reader
    ):
        svc = ThreadDiscoveryService(
            store, fake_reader, reservation_channels=["C_FAIL", "C_OK"]
        )
        original_list = fake_reader.list_channel_messages

        def _selective_fail(channel_id, *, oldest=0, max_pages=10):
            if channel_id == "C_FAIL":
                raise SlackApiError(message="channel_not_found", response=Mock())
            return original_list(channel_id, oldest=oldest, max_pages=max_pages)

        fake_reader.list_channel_messages = _selective_fail
        fake_reader.channel_messages["C_OK"] = [
            {"text": "예약번호 : BK-OK\n업체명 : 업체", "ts": "100.100"},
        ]

        saved = svc.backfill_reservation_threads(days=7)

        assert saved == 1
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            assert repo.get_by_booking_key("BK-OK") is not None


class TestTransferThreadReference:
    def test_이관_체인_저장시_root를_최초키로_유지한다(self, fake_db, service):
        service.save_thread_reference(
            booking_key="A-001",
            channel_id="C_ISSUE",
            thread_ts="111.111",
        )
        service.save_thread_reference(
            booking_key="B-001",
            channel_id="C_ISSUE",
            thread_ts="111.111",
            root_booking_key="A-001",
        )

        service.save_transfer_thread_reference(
            previous_booking_key="B-001",
            new_booking_key="C-001",
            channel_id="C_ISSUE",
            thread_ts="111.111",
        )

        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("C-001")
            assert ref is not None
            assert ref.root_booking_key == "A-001"

    def test_fallback로_스레드_탐색해도_new_key_root가_old로_저장된다(
        self, fake_db, fake_reader, service
    ):
        fake_reader.messages_by_text[("C_ISSUE", "NEW-001")] = "555.555"

        thread = service.find_issue_thread(
            "OLD-001",
            fallback_booking_keys=("NEW-001",),
        )

        assert thread is not None
        service.save_transfer_thread_reference(
            previous_booking_key="OLD-001",
            new_booking_key="NEW-001",
            channel_id=thread.channel_id,
            thread_ts=thread.thread_ts,
        )

        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.get_by_booking_key("NEW-001")
            assert ref is not None
            assert ref.root_booking_key == "OLD-001"
