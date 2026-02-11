"""SettlementRegistrationService 테스트"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

from slack_sdk.errors import SlackApiError

from app.exceptions import DatabaseError
from app.models import SettlementData, SettlementStatus
from tests.factories import SettlementDataFactory
from tests.fakes.fake_slack import FakeSlackReader, FakeSlackWriter

_APPROVAL_CHANNEL = "C-APPROVAL"
_CHANNEL = "C-TEST"
_THREAD_TS = "111.222"
_REQUESTER_ID = "U-REQ"


# ── Fake ────────────────────────────────────────


class FakeSettlementWriter:
    """SettlementWriter Fake — save() 호출을 기록하고 실패를 설정할 수 있다."""

    def __init__(self, *, should_fail: bool = False) -> None:
        self.save_calls: list[dict[str, Any]] = []
        self._should_fail = should_fail

    def save(
        self,
        data: SettlementData,
        status: SettlementStatus,
        approver_name: str,
        thread_url: str,
        rejection_reason: str = "",
    ) -> None:
        if self._should_fail:
            raise DatabaseError("DB 저장 실패")
        self.save_calls.append(
            {
                "data": data,
                "status": status,
                "approver_name": approver_name,
                "thread_url": thread_url,
                "rejection_reason": rejection_reason,
            }
        )


# ── helpers ─────────────────────────────────────


def _make_reader(
    *,
    user_name: str = "테스터",
    thread_url: str = "https://slack.com/test/thread",
) -> FakeSlackReader:
    reader = FakeSlackReader()
    reader.user_names[_REQUESTER_ID] = user_name
    # post_message가 반환할 ts에 대해 미리 등록
    # FakeSlackWriter의 첫 ts는 "1000.000000"
    reader.thread_urls[(_CHANNEL, "1000.000000")] = thread_url
    return reader


def _make_service(
    *,
    reader: FakeSlackReader | None = None,
    writer: FakeSlackWriter | None = None,
    settlement_writer: FakeSettlementWriter | None = None,
):
    from app.services.settlement_registration_service import (
        SettlementRegistrationService,
    )

    return SettlementRegistrationService(
        reader=reader or _make_reader(),
        writer=writer or FakeSlackWriter(),
        settlement_writer=settlement_writer or FakeSettlementWriter(),
        approval_channel_id=_APPROVAL_CHANNEL,
    )


def _slack_error() -> SlackApiError:
    return SlackApiError("error", Mock())


# ============================================================================
# register() 테스트
# ============================================================================


class TestRegister:
    def test_정상등록(self):
        reader = _make_reader()
        writer = FakeSlackWriter()
        settlement_writer = FakeSettlementWriter()
        svc = _make_service(
            reader=reader, writer=writer, settlement_writer=settlement_writer
        )
        data = SettlementDataFactory.create()

        svc.register(
            data=data,
            channel_id=_CHANNEL,
            thread_ts=_THREAD_TS,
            requester_id=_REQUESTER_ID,
        )

        # 원본 스레드에 상세 메시지 (1번째 post)
        assert len(writer.posted_messages) == 2
        detail_msg = writer.posted_messages[0]
        assert detail_msg["channel"] == _CHANNEL
        assert detail_msg["thread_ts"] == _THREAD_TS

        # 승인 채널에 최소 정보 + 버튼 (2번째 post)
        approval_msg = writer.posted_messages[1]
        assert approval_msg["channel"] == _APPROVAL_CHANNEL

        # DB 저장 호출 확인
        assert len(settlement_writer.save_calls) == 1
        assert settlement_writer.save_calls[0]["status"] == SettlementStatus.REQUESTED

    def test_DB저장실패시_계속진행(self):
        reader = _make_reader()
        writer = FakeSlackWriter()
        settlement_writer = FakeSettlementWriter(should_fail=True)
        svc = _make_service(
            reader=reader, writer=writer, settlement_writer=settlement_writer
        )
        data = SettlementDataFactory.create()

        # DB 저장 실패해도 예외 전파 없이 승인 채널까지 게시
        svc.register(
            data=data,
            channel_id=_CHANNEL,
            thread_ts=_THREAD_TS,
            requester_id=_REQUESTER_ID,
        )

        # 승인 채널 메시지까지 정상 게시
        assert len(writer.posted_messages) == 2
        assert writer.posted_messages[1]["channel"] == _APPROVAL_CHANNEL

    def test_SlackApiError_발생시_cleanup_및_알림(self):
        reader = _make_reader()
        writer = FakeSlackWriter()
        # post_message의 두 번째 호출(승인 채널)에서 SlackApiError 발생
        original_post = writer.post_message

        call_count = 0

        def post_message_with_error(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise _slack_error()
            return original_post(**kwargs)

        writer.post_message = post_message_with_error
        svc = _make_service(reader=reader, writer=writer)
        data = SettlementDataFactory.create()

        # 예외가 전파되지 않음
        svc.register(
            data=data,
            channel_id=_CHANNEL,
            thread_ts=_THREAD_TS,
            requester_id=_REQUESTER_ID,
        )

        # 상세 메시지 cleanup (delete 호출)
        assert len(writer.deleted_messages) == 1

    def test_이관건등록(self):
        from app.constants.options import Description

        reader = _make_reader()
        writer = FakeSlackWriter()
        svc = _make_service(reader=reader, writer=writer)
        data = SettlementDataFactory.create(
            description=Description.TRANSFER_RESERVATION.value,
        )

        svc.register(
            data=data,
            channel_id=_CHANNEL,
            thread_ts=_THREAD_TS,
            requester_id=_REQUESTER_ID,
        )

        # 승인 채널 메시지에 transfer 관련 action_id 포함
        approval_msg = writer.posted_messages[1]
        approval_blocks = approval_msg["blocks"]
        actions = approval_blocks[-1]["elements"]
        assert "transfer" in actions[0]["action_id"].lower()


# ============================================================================
# _cleanup_detail_message() 테스트
# ============================================================================


class TestCleanupDetailMessage:
    def test_메시지ts없으면skip(self):
        writer = FakeSlackWriter()
        svc = _make_service(writer=writer)

        svc._cleanup_detail_message("C-TEST", "")

        assert len(writer.deleted_messages) == 0

    def test_삭제성공(self):
        writer = FakeSlackWriter()
        svc = _make_service(writer=writer)

        svc._cleanup_detail_message("C-TEST", "123.456")

        assert len(writer.deleted_messages) == 1
        assert writer.deleted_messages[0]["channel"] == "C-TEST"
        assert writer.deleted_messages[0]["ts"] == "123.456"


# ============================================================================
# _notify_user_safe() 테스트
# ============================================================================


class TestNotifyUserSafe:
    def test_user_id없으면skip(self):
        writer = FakeSlackWriter()
        svc = _make_service(writer=writer)

        svc._notify_user_safe("", "메시지")

        assert len(writer.posted_messages) == 0

    def test_알림실패시무시(self):
        writer = FakeSlackWriter()

        def post_with_error(**kwargs):
            raise _slack_error()

        writer.post_message = post_with_error
        svc = _make_service(writer=writer)

        # 예외가 전파되지 않아야 함
        svc._notify_user_safe("U-USER", "테스트 메시지")
