from __future__ import annotations

from app.listener.messages import _route_channel_message


class TestRouteChannelMessage:
    """_route_channel_message 라우팅 결정 테스트.

    동일 채널 시나리오(dev 환경)에서 이관 메시지가 transfer로 라우팅되는지 검증.
    """

    def test_동일채널_이관메시지는_transfer로_라우팅(self):
        result = _route_channel_message(
            message={"text": "이관 전 예약번호 : 7777", "ts": "1.0"},
            channel_id="C-SAME",
            transfer_channel="C-SAME",
            reservation_channel="C-SAME",
        )
        assert result == "transfer"

    def test_동일채널_일반메시지는_reservation으로_라우팅(self):
        result = _route_channel_message(
            message={"text": "예약번호 : 1234", "ts": "1.0"},
            channel_id="C-SAME",
            transfer_channel="C-SAME",
            reservation_channel="C-SAME",
        )
        assert result == "reservation"

    def test_다른채널_이관메시지는_transfer로_라우팅(self):
        result = _route_channel_message(
            message={"text": "이관 전 예약번호 : 7777", "ts": "1.0"},
            channel_id="C-TRAN",
            transfer_channel="C-TRAN",
            reservation_channel="C-RESV",
        )
        assert result == "transfer"

    def test_다른채널_예약메시지는_reservation으로_라우팅(self):
        result = _route_channel_message(
            message={"text": "예약번호 : 1234", "ts": "1.0"},
            channel_id="C-RESV",
            transfer_channel="C-TRAN",
            reservation_channel="C-RESV",
        )
        assert result == "reservation"

    def test_transfer_미설정시_reservation으로_라우팅(self):
        result = _route_channel_message(
            message={"text": "이관 전 예약번호 : 7777", "ts": "1.0"},
            channel_id="C-RESV",
            transfer_channel="",
            reservation_channel="C-RESV",
        )
        assert result == "reservation"

    def test_무관한채널은_ignore로_라우팅(self):
        result = _route_channel_message(
            message={"text": "이관 전 예약번호 : 7777", "ts": "1.0"},
            channel_id="C-OTHER",
            transfer_channel="C-TRAN",
            reservation_channel="C-RESV",
        )
        assert result == "ignore"
