from __future__ import annotations

from app.constants import BlockId
from app.listener.actions import _open_transfer_modal
from app.services.message_parser import ParsedTransferReservation
from tests.fakes.fake_slack import FakeSlackReader


class _FakeClient:
    def __init__(self) -> None:
        self.open_calls: list[dict] = []

    def views_open(self, *, trigger_id: str, view: dict) -> None:
        self.open_calls.append(
            {
                "trigger_id": trigger_id,
                "view": view,
            }
        )


def _make_body(value: str) -> dict:
    return {
        "trigger_id": "TRIGGER",
        "user": {"id": "U-TEST"},
        "channel": {"id": "C-TEST"},
        "message": {"ts": "1000.000000", "thread_ts": "999.000000"},
        "actions": [{"value": value}],
    }


def _find_booking_key_initial_value(view: dict) -> str:
    block = next(
        b for b in view["blocks"] if b.get("block_id") == BlockId.BOOKING_KEY_BLOCK
    )
    return block["element"].get("initial_value", "")


class TestOpenTransferModal:
    def test_이관전_예약번호가_기본값으로_사용된다(self):
        parsed = ParsedTransferReservation(
            booking_key="OLD-001",
            new_booking_key="NEW-001",
            customer_name="고객",
            company_sub_name="업체",
            settlement_cost="1000",
            carmore_cost="0",
        )
        body = _make_body(parsed.model_dump_json())
        client = _FakeClient()
        reader = FakeSlackReader()
        reader.user_names["U-TEST"] = "요청자"

        _open_transfer_modal(body, client, reader)

        opened = client.open_calls[0]["view"]
        assert _find_booking_key_initial_value(opened) == "OLD-001"

    def test_이관후_예약번호가_없어도_이관전_예약번호를_사용한다(self):
        parsed = ParsedTransferReservation(
            booking_key="OLD-001",
            customer_name="고객",
            company_sub_name="업체",
        )
        body = _make_body(parsed.model_dump_json())
        client = _FakeClient()
        reader = FakeSlackReader()
        reader.user_names["U-TEST"] = "요청자"

        _open_transfer_modal(body, client, reader)

        opened = client.open_calls[0]["view"]
        assert _find_booking_key_initial_value(opened) == "OLD-001"
