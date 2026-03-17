from __future__ import annotations

from app.services.reservation_locator import ReservationLocator
from app.services.thread_reference_store import ThreadReferenceStore
from tests.fakes.fake_database import FakeDatabase
from tests.fakes.fake_slack import FakeSlackReader

RESERVATION_CH = "C-RESERVE"

SAMPLE_RESERVATION_MSG = """\
[카모아 예약]
    예약번호 : R12345
    예약자명 : 홍길동
    예약자연락처 : 010-1234-5678
    예약기간 : 2026.2.27 (금) 오후 9시 00분 ~ 2026.3.2 (월) 오후 7시 30분 (2일 22시간 30분)
    업체 : 패밀리렌트카 본사 [제주] - 입판가 정산
<결제정보>
    총 결제금액 : 185,704원"""


def _locator(
    *,
    reader: FakeSlackReader | None = None,
    channels: list[str] | None = None,
    store: ThreadReferenceStore | None = None,
) -> ReservationLocator:
    return ReservationLocator(
        reader=reader or FakeSlackReader(),
        reservation_channels=channels or [RESERVATION_CH],
        thread_ref_store=store,
    )


class TestFind:
    def test_Slack_API로_예약_검색(self):
        reader = FakeSlackReader()
        reader.messages_by_text[(RESERVATION_CH, "R12345")] = "thread-1"
        reader.parent_messages[(RESERVATION_CH, "thread-1")] = SAMPLE_RESERVATION_MSG

        loc = _locator(reader=reader)
        result = loc.find("R12345")

        assert result is not None
        assert result.channel == RESERVATION_CH
        assert result.thread_ts == "thread-1"
        assert result.data.booking_key == "R12345"

    def test_예약번호_실패_전화번호_fallback(self):
        reader = FakeSlackReader()
        reader.messages_by_text[(RESERVATION_CH, "010-1234-5678")] = "thread-1"
        reader.parent_messages[(RESERVATION_CH, "thread-1")] = SAMPLE_RESERVATION_MSG

        loc = _locator(reader=reader)
        result = loc.find("R99999", phone="010-1234-5678")

        assert result is not None
        assert result.data.customer_name == "홍길동"

    def test_검색_실패_시_None(self):
        loc = _locator()
        result = loc.find("NONEXIST")
        assert result is None

    def test_여러_채널_순회(self):
        reader = FakeSlackReader()
        second_ch = "C-RESERVE-2"
        reader.messages_by_text[(second_ch, "R12345")] = "thread-2"
        reader.parent_messages[(second_ch, "thread-2")] = SAMPLE_RESERVATION_MSG

        loc = _locator(reader=reader, channels=[RESERVATION_CH, second_ch])
        result = loc.find("R12345")

        assert result is not None
        assert result.channel == second_ch

    def test_DB_캐시_우선_사용(self):
        fake_db = FakeDatabase()
        store = ThreadReferenceStore(fake_db.get_session)
        store.save("R12345", RESERVATION_CH, "cached-thread")

        reader = FakeSlackReader()
        reader.parent_messages[(RESERVATION_CH, "cached-thread")] = (
            SAMPLE_RESERVATION_MSG
        )

        loc = _locator(reader=reader, store=store)
        result = loc.find("R12345")

        assert result is not None
        assert result.thread_ts == "cached-thread"

    def test_Slack_폴백_후_DB_캐시_저장(self):
        fake_db = FakeDatabase()
        store = ThreadReferenceStore(fake_db.get_session)

        reader = FakeSlackReader()
        reader.messages_by_text[(RESERVATION_CH, "R12345")] = "found-thread"
        reader.parent_messages[(RESERVATION_CH, "found-thread")] = (
            SAMPLE_RESERVATION_MSG
        )

        loc = _locator(reader=reader, store=store)
        loc.find("R12345")

        cached = store.get_by_booking_key("R12345")
        assert cached is not None
        assert cached.thread_ts == "found-thread"

    def test_store_없이_기존_동작(self):
        reader = FakeSlackReader()
        reader.messages_by_text[(RESERVATION_CH, "R12345")] = "thread-1"
        reader.parent_messages[(RESERVATION_CH, "thread-1")] = SAMPLE_RESERVATION_MSG

        loc = _locator(reader=reader, store=None)
        result = loc.find("R12345")

        assert result is not None
