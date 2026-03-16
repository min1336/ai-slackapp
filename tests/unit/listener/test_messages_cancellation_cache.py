from __future__ import annotations

from app.listener.messages import _cache_cancellation_thread_ref
from app.services.cancellation_thread_store import CancellationThreadStore
from tests.fakes.fake_database import FakeDatabase


class TestCacheCancellationThreadRef:
    def test_예약_원본_메시지면_캐시한다(self):
        fake_db = FakeDatabase()
        store = CancellationThreadStore(fake_db.get_session)
        message = {
            "channel": "C-RESV",
            "ts": "1234.5678",
            "text": "예약번호 : R9999\n예약자명 : 홍길동",
        }

        _cache_cancellation_thread_ref(message, store)

        cached = store.get_by_booking_key("R9999")
        assert cached is not None
        assert cached.channel_id == "C-RESV"
        assert cached.thread_ts == "1234.5678"

    def test_스레드_댓글은_캐시하지_않는다(self):
        fake_db = FakeDatabase()
        store = CancellationThreadStore(fake_db.get_session)
        message = {
            "channel": "C-RESV",
            "ts": "1234.5678",
            "thread_ts": "1111.2222",
            "text": "예약번호 : R9999",
        }

        _cache_cancellation_thread_ref(message, store)

        assert store.get_by_booking_key("R9999") is None

    def test_예약번호가_없으면_캐시하지_않는다(self):
        fake_db = FakeDatabase()
        store = CancellationThreadStore(fake_db.get_session)
        message = {
            "channel": "C-RESV",
            "ts": "1234.5678",
            "text": "일반 안내 메시지",
        }

        _cache_cancellation_thread_ref(message, store)

        assert store.get_by_booking_key("") is None

    def test_store_None이면_아무것도_안한다(self):
        message = {
            "channel": "C-RESV",
            "ts": "1234.5678",
            "text": "예약번호 : R9999",
        }

        _cache_cancellation_thread_ref(message, None)  # no error
