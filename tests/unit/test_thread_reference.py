from __future__ import annotations

import pytest

from app.infrastructure.database.repository import ThreadReferenceRepository
from tests.fakes.fake_database import FakeDatabase


@pytest.fixture
def fake_db():
    return FakeDatabase()


class TestThreadReferenceRepository:
    def test_save_새로운_레퍼런스를_저장한다(self, fake_db):
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.save(
                booking_key="BK-001",
                channel_id="C123",
                thread_ts="1234567890.123456",
            )

        assert ref.booking_key == "BK-001"
        assert ref.channel_id == "C123"
        assert ref.thread_ts == "1234567890.123456"
        assert ref.root_booking_key == "BK-001"  # 기본값 = booking_key

    def test_save_root_booking_key를_지정할_수_있다(self, fake_db):
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            ref = repo.save(
                booking_key="BK-002",
                channel_id="C123",
                thread_ts="1234567890.123456",
                root_booking_key="BK-001",
            )

        assert ref.root_booking_key == "BK-001"

    def test_save_동일_booking_key는_기존_레코드를_반환한다(self, fake_db):
        # Given
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            first = repo.save(
                booking_key="BK-001",
                channel_id="C123",
                thread_ts="1111111111.111111",
            )
            first_id = first.id

        # When — 같은 booking_key로 다시 저장
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            second = repo.save(
                booking_key="BK-001",
                channel_id="C999",
                thread_ts="9999999999.999999",
            )

        # Then — 원본 유지 (upsert skip)
        assert second.id == first_id
        assert second.channel_id == "C123"
        assert second.thread_ts == "1111111111.111111"

    def test_get_by_booking_key_존재하는_키_조회(self, fake_db):
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            repo.save(
                booking_key="BK-001",
                channel_id="C123",
                thread_ts="1234567890.123456",
            )

        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            found = repo.get_by_booking_key("BK-001")

        assert found is not None
        assert found.channel_id == "C123"

    def test_get_by_booking_key_없는_키는_None(self, fake_db):
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            found = repo.get_by_booking_key("NONEXISTENT")

        assert found is None

    def test_이관_체인_A_B_C_추적(self, fake_db):
        thread_ts = "1111111111.111111"

        # A 등록 (원본)
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            repo.save(
                booking_key="A",
                channel_id="C123",
                thread_ts=thread_ts,
            )

        # A→B 이관 — B도 A의 스레드에 연결
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            repo.save(
                booking_key="B",
                channel_id="C123",
                thread_ts=thread_ts,
                root_booking_key="A",
            )

        # B→C 이관 — C도 A의 스레드에 연결
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            repo.save(
                booking_key="C",
                channel_id="C123",
                thread_ts=thread_ts,
                root_booking_key="A",
            )

        # 검증: A, B, C 모두 같은 thread_ts
        with fake_db.get_session() as session:
            repo = ThreadReferenceRepository(session)
            for key in ("A", "B", "C"):
                ref = repo.get_by_booking_key(key)
                assert ref is not None
                assert ref.thread_ts == thread_ts
                assert ref.root_booking_key == "A"
