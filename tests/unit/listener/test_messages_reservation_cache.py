from __future__ import annotations

from app.listener.messages import _cache_reservation_origin_thread


class _FakeDiscovery:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def register_origin_thread(
        self,
        *,
        booking_key: str,
        channel_id: str,
        thread_ts: str,
    ) -> None:
        self.calls.append(
            {
                "booking_key": booking_key,
                "channel_id": channel_id,
                "thread_ts": thread_ts,
            }
        )


class TestCacheReservationOriginThread:
    def test_예약_원본_메시지면_thread_reference를_저장한다(self):
        discovery = _FakeDiscovery()
        message = {
            "channel": "C-RESV",
            "ts": "1234.5678",
            "text": """
예약번호 : 1234
예약자명 : 김민수 (010-1111-2222)
업체 : 오마이렌트카본사
""",
        }

        _cache_reservation_origin_thread(message, discovery)

        assert discovery.calls == [
            {
                "booking_key": "1234",
                "channel_id": "C-RESV",
                "thread_ts": "1234.5678",
            }
        ]

    def test_스레드_댓글은_캐시하지_않는다(self):
        discovery = _FakeDiscovery()
        message = {
            "channel": "C-RESV",
            "ts": "1234.5678",
            "thread_ts": "1111.2222",
            "text": "예약번호 : 1234",
        }

        _cache_reservation_origin_thread(message, discovery)

        assert discovery.calls == []

    def test_예약번호가_없으면_캐시하지_않는다(self):
        discovery = _FakeDiscovery()
        message = {
            "channel": "C-RESV",
            "ts": "1234.5678",
            "text": "일반 안내 메시지",
        }

        _cache_reservation_origin_thread(message, discovery)

        assert discovery.calls == []
