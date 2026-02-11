"""ThreadReferenceStore 서비스 컴포넌트 테스트

정상 경로 + SQLAlchemyError 에러 경로 커버.
"""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.database.repository import ThreadReferenceRepository
from app.models import ThreadLocation
from app.services.thread_reference_store import ThreadReferenceStore

# ── get_by_booking_key ──────────────────────────


class TestGetByBookingKey:
    def test_존재하는_키_ThreadLocation_반환(self, fake_db):
        store = ThreadReferenceStore(fake_db.get_session)
        store.save("BK-001", "C123", "1234.5678")

        result = store.get_by_booking_key("BK-001")

        assert result == ThreadLocation(channel_id="C123", thread_ts="1234.5678")

    def test_없는_키_None_반환(self, fake_db):
        store = ThreadReferenceStore(fake_db.get_session)

        assert store.get_by_booking_key("NONEXISTENT") is None

    def test_SQLAlchemyError시_None_반환(self, fake_db, monkeypatch):
        store = ThreadReferenceStore(fake_db.get_session)

        def _raise(*_args, **_kwargs):
            raise SQLAlchemyError("DB 연결 실패")

        monkeypatch.setattr(store, "_get_ref", _raise)

        assert store.get_by_booking_key("BK-001") is None


# ── save ────────────────────────────────────────


class TestSave:
    def test_신규_저장(self, fake_db):
        store = ThreadReferenceStore(fake_db.get_session)

        store.save("BK-001", "C123", "1234.5678")

        result = store.get_by_booking_key("BK-001")
        assert result is not None
        assert result.channel_id == "C123"
        assert result.thread_ts == "1234.5678"

    def test_root_booking_key_지정(self, fake_db):
        store = ThreadReferenceStore(fake_db.get_session)

        store.save("BK-002", "C123", "1234.5678", root_booking_key="BK-001")

        with fake_db.get_session() as session:
            ref = ThreadReferenceRepository(session).get_by_booking_key("BK-002")
            assert ref.root_booking_key == "BK-001"

    def test_동일키_저장시_기존_유지(self, fake_db):
        store = ThreadReferenceStore(fake_db.get_session)
        store.save("BK-001", "C123", "1111.1111")
        store.save("BK-001", "C999", "9999.9999")

        result = store.get_by_booking_key("BK-001")
        assert result.channel_id == "C123"
        assert result.thread_ts == "1111.1111"

    def test_SQLAlchemyError시_예외_미전파(self, fake_db, monkeypatch):
        store = ThreadReferenceStore(fake_db.get_session)

        def _raise(*_args, **_kwargs):
            raise SQLAlchemyError("DB 저장 실패")

        monkeypatch.setattr(store, "_save_ref", _raise)

        # 예외가 전파되지 않아야 함
        store.save("BK-001", "C123", "1234.5678")
