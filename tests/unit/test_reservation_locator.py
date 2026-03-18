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


def _make_reader_with_reservation(
    channel: str = RESERVATION_CH,
    thread_ts: str = "thread-1",
    text: str = SAMPLE_RESERVATION_MSG,
    *,
    bold: bool = False,
) -> FakeSlackReader:
    """채널에 예약 메시지가 있는 FakeSlackReader를 생성한다."""
    reader = FakeSlackReader()
    msg_text = text
    if bold:
        msg_text = text.replace("R12345", "*R12345*")
    reader.channel_messages[channel] = [{"text": msg_text, "ts": thread_ts}]
    reader.parent_messages[(channel, thread_ts)] = text
    return reader


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
        reader = _make_reader_with_reservation()
        loc = _locator(reader=reader)
        result = loc.find("R12345")

        assert result is not None
        assert result.channel == RESERVATION_CH
        assert result.thread_ts == "thread-1"
        assert result.data.booking_key == "R12345"

    def test_예약번호_실패_전화번호_fallback(self):
        reader = _make_reader_with_reservation()
        loc = _locator(reader=reader)
        result = loc.find("R99999", phone="010-1234-5678")

        assert result is not None
        assert result.data.customer_name == "홍길동"

    def test_검색_실패_시_None(self):
        loc = _locator()
        result = loc.find("NONEXIST")
        assert result is None

    def test_여러_채널_순회(self):
        second_ch = "C-RESERVE-2"
        reader = _make_reader_with_reservation(channel=second_ch, thread_ts="thread-2")
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

        reader = _make_reader_with_reservation(thread_ts="found-thread")
        loc = _locator(reader=reader, store=store)
        loc.find("R12345")

        cached = store.get_by_booking_key("R12345")
        assert cached is not None
        assert cached.thread_ts == "found-thread"

    def test_DB_에러_시_Slack_폴백(self):
        """DB 세션 생성 실패 시에도 Slack API 폴백으로 예약을 찾는다."""

        def _broken_session():
            raise ValueError("DATABASE_URL is not configured")

        store = ThreadReferenceStore(_broken_session)
        reader = _make_reader_with_reservation()

        loc = _locator(reader=reader, store=store)
        result = loc.find("R12345")

        assert result is not None
        assert result.channel == RESERVATION_CH
        assert result.thread_ts == "thread-1"

    def test_DB_저장_에러_시_결과_정상_반환(self):
        """Slack 폴백 후 DB 캐시 저장이 실패해도 결과는 정상 반환한다."""

        def _broken_session():
            raise ValueError("DATABASE_URL is not configured")

        store = ThreadReferenceStore(_broken_session)
        reader = _make_reader_with_reservation()

        loc = _locator(reader=reader, store=store)
        result = loc.find("R12345")

        assert result is not None
        assert result.data.booking_key == "R12345"

    def test_빈텍스트_메시지_스킵(self):
        """text=""인 메시지(Jotform 등)는 스킵하고 실제 예약 메시지를 찾는다."""
        reader = FakeSlackReader()
        reader.channel_messages[RESERVATION_CH] = [
            {"text": "", "ts": "jotform-ts"},  # Jotform: text 비어있음
            {"text": SAMPLE_RESERVATION_MSG, "ts": "reserve-ts"},
        ]
        reader.parent_messages[(RESERVATION_CH, "reserve-ts")] = SAMPLE_RESERVATION_MSG

        loc = _locator(reader=reader)
        result = loc.find("R12345")

        assert result is not None
        assert result.thread_ts == "reserve-ts"
        assert result.data.booking_key == "R12345"

    def test_볼드_마크다운_포맷_매칭(self):
        """Slack 볼드(*text*) 포맷이 있어도 substring 매칭으로 예약을 찾는다."""
        reader = _make_reader_with_reservation(bold=True)
        loc = _locator(reader=reader)
        result = loc.find("R12345")

        assert result is not None
        assert result.data.booking_key == "R12345"

    def test_store_없이_기존_동작(self):
        reader = _make_reader_with_reservation()
        loc = _locator(reader=reader, store=None)
        result = loc.find("R12345")

        assert result is not None
